"""Atomic request lifecycle and log.md mirror safety."""
import json
import os

import pytest

from tests.council_util import (append, make_cfg, make_repo, make_request,
                                make_root)
from tools.council import events, publish, storage
from tools.council.schemas import SchemaViolation, TransitionError

RID = "pub-req-001"


@pytest.fixture()
def env(tmp_path):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    append(root, cfg, "BUILD_READY", "claude", RID, repo, head)
    return root, repo, head, cfg


def test_publish_lands_in_ready_with_no_draft_residue(env):
    root, repo, head, cfg = env
    event = publish.publish_request(root, cfg,
                                    make_request(repo, head, RID))
    ready = storage.safe_request_path(root, "ready", RID)
    assert os.path.exists(ready)
    draft_dir = os.path.join(root, "requests", "draft")
    assert os.listdir(draft_dir) == []  # tmp fully renamed away
    stored = json.load(open(ready, encoding="utf-8"))
    assert stored["request_payload_hash"] \
        == event["payload"]["request_payload_hash"]
    assert event["event_type"] == "AUDIT_REQUESTED"


def test_refused_publish_leaves_no_orphan_in_ready(env):
    """2026-07-11 wart regression: a publish refused by the state machine
    (here: request still in `building` — no BUILD_READY) must not leave an
    unpinned request file behind in ready/."""
    root, repo, head, cfg = env
    other = "pub-req-orphan"
    append(root, cfg, "BUILD_STARTED", "claude", other, repo, head)
    with pytest.raises(TransitionError):
        publish.publish_request(root, cfg, make_request(repo, head, other))
    assert not os.path.exists(storage.safe_request_path(root, "ready", other))
    with pytest.raises(TransitionError):  # reaudit path refused the same way
        publish.publish_request(root, cfg, make_request(repo, head, other),
                                reaudit=True)
    assert not os.path.exists(storage.safe_request_path(root, "ready", other))


def test_published_source_request_stores_task_kind_explicitly(env):
    """council-protocol-delta-001 cycle-4 deferred regression: a source
    request published through the real path stores task_kind: source in the
    canonical file, covered by the pinned payload hash."""
    root, repo, head, cfg = env
    event = publish.publish_request(
        root, cfg, make_request(repo, head, RID, task_kind="source"))
    stored = json.load(open(storage.safe_request_path(root, "ready", RID),
                            encoding="utf-8"))
    assert stored["task_kind"] == "source"
    from tools.council.schemas import compute_request_payload_hash
    assert compute_request_payload_hash(stored) \
        == event["payload"]["request_payload_hash"]


def test_legacy_publish_without_task_kind_defaults_to_experiment(env):
    """Backward compatibility is intentional: absence of task_kind means
    experiment routing (all pre-delta requests keep their behavior)."""
    root, repo, head, cfg = env
    publish.publish_request(root, cfg, make_request(repo, head, RID))
    stored = json.load(open(storage.safe_request_path(root, "ready", RID),
                            encoding="utf-8"))
    assert "task_kind" not in stored


def test_reaudit_flag_emits_ready_for_reaudit(env):
    root, repo, head, cfg = env
    event = publish.publish_request(root, cfg,
                                    make_request(repo, head, RID),
                                    reaudit=True)
    assert event["event_type"] == "READY_FOR_REAUDIT"


def test_publish_binds_event_to_file_hash(env):
    root, repo, head, cfg = env
    event = publish.publish_request(root, cfg, make_request(repo, head, RID))
    ready = storage.safe_request_path(root, "ready", RID)
    stored = json.load(open(ready, encoding="utf-8"))
    from tools.council.schemas import compute_request_payload_hash
    assert compute_request_payload_hash(stored) \
        == event["payload"]["request_payload_hash"]


def test_publish_requires_clean_tree(env):
    root, repo, head, cfg = env
    with open(os.path.join(repo, "dirty.txt"), "w") as fh:
        fh.write("uncommitted\n")
    with pytest.raises(SchemaViolation):
        publish.publish_request(root, cfg, make_request(repo, head, RID))


def test_publish_requires_head_commit(env, tmp_path):
    root, repo, head, cfg = env
    request = make_request(repo, head, RID,
                           target_commit="a" * 40,
                           originating_blocked_commit=head)
    with pytest.raises(SchemaViolation):
        publish.publish_request(root, cfg, request)


def test_request_ids_are_single_use(env):
    root, repo, head, cfg = env
    publish.publish_request(root, cfg, make_request(repo, head, RID))
    with pytest.raises(SchemaViolation):
        publish.publish_request(root, cfg, make_request(repo, head, RID))


def test_log_md_mirror_appends_only(env):
    root, repo, head, cfg = env
    log = os.path.join(root, "log.md")
    before = open(log, encoding="utf-8").read()
    publish.publish_request(root, cfg, make_request(repo, head, RID))
    after = open(log, encoding="utf-8").read()
    assert after.startswith(before)  # history is a strict prefix
    assert "## [claude]" in after[len(before):]
    assert RID in after[len(before):]


def test_status_paused_refuses_publish(env):
    root, repo, head, cfg = env
    storage.write_control(root, "paused", ["claude"], "test", None)
    with pytest.raises(Exception):
        publish.publish_request(root, cfg, make_request(repo, head, RID))


def test_bounded_five_audit_cycles(env):
    root, repo, head, cfg = env
    from tools.council import state_machine
    # simulate five completed cycles by raw events, then a sixth publish
    for _cycle in range(5):
        append(root, cfg, "READY_FOR_REAUDIT", "claude", RID, repo, head,
               {"scope": ["scope item"]})
        append(root, cfg, "AUDIT_CLAIMED", "codex", RID, repo, head)
        append(root, cfg, "AUDIT_BLOCKED", "codex", RID, repo, head)
        append(root, cfg, "FIX_STARTED", "claude", RID, repo, head)
        append(root, cfg, "BUILD_READY", "claude", RID, repo, head)
    with pytest.raises(TransitionError):
        publish.publish_request(root, cfg, make_request(repo, head, RID))


def test_autonomous_scope_expansion_refused(env):
    root, repo, head, cfg = env
    append(root, cfg, "READY_FOR_REAUDIT", "claude", RID, repo, head,
           {"scope": ["narrow thing"]})
    append(root, cfg, "AUDIT_CLAIMED", "codex", RID, repo, head)
    append(root, cfg, "AUDIT_BLOCKED", "codex", RID, repo, head)
    append(root, cfg, "FIX_STARTED", "claude", RID, repo, head)
    append(root, cfg, "BUILD_READY", "claude", RID, repo, head)
    wider = make_request(repo, head, RID,
                         scope=["narrow thing", "brand new area"])
    with pytest.raises(SchemaViolation):
        publish.publish_request(root, cfg, wider, autonomous=True)
    # same scope is fine autonomously
    same = make_request(repo, head, RID, scope=["narrow thing"])
    event = publish.publish_request(root, cfg, same, autonomous=True)
    assert event["event_type"] == "AUDIT_REQUESTED"
