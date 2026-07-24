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


def test_m8_recovery_commands_preserve_role_boundaries(env):
    _root, repo, head, _cfg = env
    assert cli.main([
        "--role", "codex", "propose-m8-incomplete-recovery",
        "first-gladiator-m8-incomplete-result-001",
        "--tool-repository", repo, "--tool-commit", head,
        "--max-compute-minutes", "240", "--max-wall-minutes", "240",
        "--max-storage-mb", "1024"]) == 1
    assert cli.main([
        "--role", "human", "recover-m8-incomplete-handoff",
        "first-gladiator-m8-incomplete-result-001"]) == 1


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


def test_clear_lock_refuses_unexpired_lease(env):
    root, _repo, _head, _cfg = env
    held = locking.acquire(root, "lease-live", "codex", RID)
    try:
        assert cli.main(["--role", "claude", "clear-lock", "lease-live",
                         "--reason", "must not clear live owner"]) == 1
        assert locking.read_lock(root, "lease-live")["owner_token"] == \
            held.owner_token
    finally:
        locking.release(held)


def test_clear_lock_removes_only_the_expired_observed_owner(env):
    root, _repo, _head, _cfg = env
    locking.acquire(root, "lease-expired", "codex", "lease-expired",
                    lease_seconds=-1)
    assert cli.main(["--role", "claude", "clear-lock", "lease-expired",
                     "--reason", "expired test lease"]) == 0
    assert locking.read_lock(root, "lease-expired") is None
    last = events.read_chain(root)[-1]
    assert last["event_type"] == "WATCHER_ERROR"
    assert last["payload"]["operation"] == "clear_stale_lock"


def test_active_control_refuses_expired_launcher_clear(env):
    """001490 regression: an expired timestamp plus a PID hidden by an
    audit namespace cannot authorize deletion of the live singleton while
    Codex control remains active."""
    root, _repo, _head, _cfg = env
    held = locking.acquire(root, "_codex_launcher", "codex",
                           "codex-launcher", lease_seconds=-1)
    try:
        assert cli.main(["--role", "claude", "clear-lock",
                         "_codex_launcher", "--reason",
                         "pid not visible in nested namespace"]) == 1
        assert locking.read_lock(root, "_codex_launcher")["owner_token"] == \
            held.owner_token
    finally:
        locking.release(held)


def test_milestone_status_output(env, capsys):
    _root, _repo, _head, _cfg = env
    assert cli.main(["--role", "human", "init-policy"]) == 0
    capsys.readouterr()
    assert cli.main(["milestone-status"]) == 0
    out = capsys.readouterr().out
    assert "society milestone reached: False" in out
    assert "[ ] sequential_history_validated" in out
