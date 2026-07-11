"""CLI round-trips and the human-only gate operations."""
import json
import os

import pytest

from tests.council_util import (append, drive_to_claimed, make_cfg,
                                make_repo, make_request, make_root,
                                make_verdict)
from tools.council import cli, codex_watch, events, locking, storage
from tools.council.schemas import compute_verdict_payload_hash

RID = "cli-req-001"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    monkeypatch.setenv("COUNCIL_ROOT", root)
    monkeypatch.setenv("COUNCIL_REPO_ROOTS", repo)
    return root, repo, head, make_cfg(repo, root)


def _drive_to_awaiting_human(root, cfg, repo, head):
    ctx = drive_to_claimed(root, cfg, repo, head, request_id=RID)
    verdict = make_verdict(head, request_id=RID, verdict="GO")
    verdict["verdict_payload_hash"] = compute_verdict_payload_hash(verdict)
    codex_watch.submit_verdict(root, cfg, verdict)
    locking.release(ctx["lock"])
    append(root, cfg, "HUMAN_APPROVAL_REQUIRED", "claude", RID, repo, head)


def test_init_creates_layout(env, capsys):
    root, _repo, _head, _cfg = env
    assert cli.main(["init"]) == 0
    for sub in ("requests/ready", "requests/claimed", "verdicts", "locks"):
        assert os.path.isdir(os.path.join(root, sub))


def test_verify_chain_and_rebuild_state(env, capsys):
    root, repo, head, cfg = env
    append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    assert cli.main(["verify-chain"]) == 0
    assert cli.main(["rebuild-state"]) == 0
    state = json.load(open(storage.state_path(root), encoding="utf-8"))
    assert state["requests"][RID]["state"] == "building"


def test_status_lists_requests(env, capsys):
    root, repo, head, cfg = env
    append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert RID in out and "building" in out


def test_publish_request_and_show(env, tmp_path, capsys):
    root, repo, head, cfg = env
    append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    append(root, cfg, "BUILD_READY", "claude", RID, repo, head)
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps(make_request(repo, head, RID)))
    assert cli.main(["--role", "claude", "publish-request", "--file",
                     str(request_file), "--reaudit"]) == 0
    assert cli.main(["show", RID]) == 0
    assert RID in capsys.readouterr().out


def test_approve_requires_human_role(env):
    root, repo, head, cfg = env
    _drive_to_awaiting_human(root, cfg, repo, head)
    assert cli.main(["--role", "claude", "approve", RID,
                     "--commit", head]) == 1
    assert cli.main(["--role", "codex", "approve", RID,
                     "--commit", head]) == 1


def test_approve_binds_to_exact_commit(env):
    root, repo, head, cfg = env
    _drive_to_awaiting_human(root, cfg, repo, head)
    assert cli.main(["--role", "human", "approve", RID,
                     "--commit", "b" * 40]) == 1
    assert cli.main(["--role", "human", "approve", RID,
                     "--commit", head]) == 0
    assert events.read_chain(root)[-1]["event_type"] == "EXPERIMENT_APPROVED"


def test_init_policy_is_owner_only(env):
    _root, _repo, _head, _cfg = env
    assert cli.main(["--role", "claude", "init-policy"]) == 1
    assert cli.main(["--role", "human", "init-policy"]) == 0
    assert cli.main(["--role", "human", "init-policy"]) == 1  # write-once


def test_record_subcommand(env):
    root, repo, head, cfg = env
    assert cli.main(["--role", "claude", "record", "--type", "BUILD_STARTED",
                     "--request-id", RID, "--repository", repo,
                     "--commit", head,
                     "--payload-json", '{"note": "via cli"}']) == 0
    chain = events.read_chain(root)
    assert chain[-1]["payload"]["note"] == "via cli"


def test_cancel_records_reason(env):
    root, repo, head, cfg = env
    append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    ready = storage.safe_request_path(root, "ready", RID)
    with open(ready, "w", encoding="utf-8") as fh:
        json.dump(make_request(repo, head, RID), fh)
    assert cli.main(["--role", "human", "cancel", RID,
                     "--reason", "superseded"]) == 0
    chain = events.read_chain(root)
    assert chain[-1]["event_type"] == "REQUEST_CANCELED"
    assert chain[-1]["payload"]["reason"] == "superseded"


def test_milestone_status_output(env, capsys):
    _root, _repo, _head, _cfg = env
    assert cli.main(["--role", "human", "init-policy"]) == 0
    capsys.readouterr()
    assert cli.main(["milestone-status"]) == 0
    out = capsys.readouterr().out
    assert "society milestone reached: False" in out
    assert "[ ] sequential_history_validated" in out
