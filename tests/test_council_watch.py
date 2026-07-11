"""claude_watch behavior: verdict routing, hard validation, autonomy gate,
timeouts, cursor discipline; codex claim exclusivity."""
import os

import pytest

from tests.council_util import (append, drive_to_claimed, make_autonomy_block,
                                make_cfg, make_repo, make_root, make_verdict)
from tools.council import claude_watch, codex_watch, events, locking, policy, \
    storage
from tools.council.schemas import (CouncilError, LockHeld,
                                   compute_verdict_payload_hash)

RID = "watch-req-001"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    monkeypatch.setenv("COUNCIL_ROOT", root)
    monkeypatch.setenv("COUNCIL_REPO_ROOTS", repo)
    return root, repo, head, cfg


def _signed(head, **overrides):
    verdict = make_verdict(head, request_id=overrides.pop("request_id", RID),
                           **overrides)
    verdict["verdict_payload_hash"] = compute_verdict_payload_hash(verdict)
    return verdict


def _submit(root, cfg, head, verdict_kind, rid=RID, **request_overrides):
    ctx = drive_to_claimed(root, cfg, *_repo_head(cfg), request_id=rid,
                           **request_overrides)
    verdict = _signed(head, request_id=rid, verdict=verdict_kind)
    codex_watch.submit_verdict(root, cfg, verdict)
    locking.release(ctx["lock"])
    return ctx


def _repo_head(cfg):
    import subprocess
    repo = cfg.repo_roots[0]
    head = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    return repo, head


def test_blocked_verdict_prints_findings_and_stops(env, capsys):
    root, repo, head, cfg = env
    ctx = drive_to_claimed(root, cfg, repo, head, request_id=RID)
    verdict = _signed(head, verdict="BLOCKED",
                      blockers=["twin collision remains"],
                      findings=["probe wrote one cell"],
                      summary="still blocked")
    codex_watch.submit_verdict(root, cfg, verdict)
    locking.release(ctx["lock"])
    chain_before = len(events.read_chain(root))
    rc = claude_watch.main(["--once", "--request-id", RID])
    out = capsys.readouterr().out
    assert rc == 0
    assert "AUDIT_BLOCKED" in out and "fixes are required" in out
    assert "twin collision remains" in out
    # BLOCKED is the record: the watcher appends nothing
    assert len(events.read_chain(root)) == chain_before


def test_go_routes_to_human_gate_when_request_demands_it(env, capsys):
    root, repo, head, cfg = env
    _submit(root, cfg, head, "GO")
    rc = claude_watch.main(["--once", "--request-id", RID])
    out = capsys.readouterr().out
    assert rc == 0
    assert "HUMAN_APPROVAL_REQUIRED" in out
    types = [e["event_type"] for e in events.read_chain(root)]
    assert types[-2:] == ["POLICY_VALIDATION_REQUIRED",
                          "HUMAN_APPROVAL_REQUIRED"]


def test_go_with_conditions_never_auto_approves(env, capsys):
    root, repo, head, cfg = env
    policy.write_initial_policy(root)
    _submit(root, cfg, head, "GO_WITH_CONDITIONS",
            human_approval_required=False, autonomy=make_autonomy_block())
    rc = claude_watch.main(["--once", "--request-id", RID])
    out = capsys.readouterr().out
    assert rc == 0
    assert "HUMAN_APPROVAL_REQUIRED" in out
    assert "verdict_is_go" in out


def test_go_auto_approves_inside_policy(env, capsys):
    root, repo, head, cfg = env
    policy.write_initial_policy(root)
    _submit(root, cfg, head, "GO", human_approval_required=False,
            autonomy=make_autonomy_block())
    rc = claude_watch.main(["--once", "--request-id", RID])
    out = capsys.readouterr().out
    assert rc == 0
    assert "AUTO_APPROVED" in out
    types = [e["event_type"] for e in events.read_chain(root)]
    assert types[-2:] == ["POLICY_VALIDATION_REQUIRED", "AUTO_APPROVED"]
    assert "does not launch" in out  # the watcher never runs experiments


def test_other_requests_verdicts_are_ignored(env, capsys):
    root, repo, head, cfg = env
    _submit(root, cfg, head, "GO", rid="watch-req-other")
    rc = claude_watch.main(["--once", "--request-id", RID])
    out = capsys.readouterr().out
    assert rc == 0
    assert "no matching verdict" in out
    types = [e["event_type"] for e in events.read_chain(root)]
    assert "POLICY_VALIDATION_REQUIRED" not in types


def test_invalid_verdict_payload_rejected_and_logged(env, capsys):
    root, repo, head, cfg = env
    ctx = drive_to_claimed(root, cfg, repo, head, request_id=RID)
    # forge a GO event whose payload is NOT a valid verdict (raw append,
    # bypassing codex_watch validation)
    append(root, cfg, "AUDIT_GO", "codex", RID, repo, head,
           {"verdict": "GO", "note": "missing everything"})
    locking.release(ctx["lock"])
    rc = claude_watch.main(["--once", "--request-id", RID])
    err = capsys.readouterr().err
    assert rc == 0
    assert "invalid verdict ignored" in err
    assert events.read_chain(root)[-1]["event_type"] == "WATCHER_ERROR"


def test_wrong_audited_commit_rejected(env, capsys):
    root, repo, head, cfg = env
    ctx = drive_to_claimed(root, cfg, repo, head, request_id=RID)
    verdict = _signed("c" * 40)  # audited a different commit
    append(root, cfg, "AUDIT_GO", "codex", RID, repo, head, verdict)
    locking.release(ctx["lock"])
    rc = claude_watch.main(["--once", "--request-id", RID])
    err = capsys.readouterr().err
    assert rc == 0
    assert "invalid verdict ignored" in err
    assert events.read_chain(root)[-1]["event_type"] == "WATCHER_ERROR"


def test_validate_rejects_unclaimed_and_wrong_sender(env):
    root, repo, head, cfg = env
    verdict = _signed(head)
    forged = {"event_id": "x", "event_type": "AUDIT_GO", "sender": "claude",
              "request_id": RID, "payload": verdict, "target_commit": head,
              "repository": repo}
    with pytest.raises(CouncilError):
        claude_watch._validate_verdict_event(root, cfg, forged, RID)
    forged["sender"] = "codex"
    with pytest.raises(CouncilError):  # request never existed/claimed
        claude_watch._validate_verdict_event(root, cfg, forged, RID)


# --------------------- cycle-3 blocker: watcher-path request root of trust

def _tamper_request_file(root, rid, rehash: bool):
    """The cycle-3 Codex probe: post-verdict edit of the mutable request
    file that flips the human gate off (the escalation AUTO_APPROVED would
    grant) and rewrites target_commit. rehash=False leaves
    request_payload_hash stale; rehash=True recomputes it so the file is
    self-consistent — both must fail against the event-pinned hash."""
    import json
    from tests.council_util import make_autonomy_block
    from tools.council.schemas import compute_request_payload_hash
    for bucket in ("ready", "claimed", "complete"):
        path = storage.safe_request_path(root, bucket, rid)
        if os.path.exists(path):
            break
    with open(path, encoding="utf-8") as fh:
        request = json.load(fh)
    request["human_approval_required"] = False
    request["autonomy"] = make_autonomy_block()
    request["target_commit"] = "e" * 40
    if rehash:
        request["request_payload_hash"] = \
            compute_request_payload_hash(request)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(request, fh)


def _assert_watcher_paused_before_policy(root, repo, head, rc, chain_before):
    chain = events.read_chain(root)
    types = [e["event_type"] for e in chain]
    assert rc == 1
    assert "POLICY_VALIDATION_REQUIRED" not in types
    assert "AUTO_APPROVED" not in types
    last = chain[-1]
    assert last["event_type"] == "AUTONOMY_PAUSED"
    assert "root-of-trust" in last["payload"]["reason"]
    # coordinates come from the pinned publish event, not the tampered JSON
    assert last["repository"] == repo
    assert last["target_commit"] == head
    assert last["target_commit"] != "e" * 40
    # the pause is the ONLY event the watcher appended
    assert len(chain) == chain_before + 1


def test_watcher_pauses_on_stale_hash_request_tamper(env, capsys):
    """Real claude_watch.main from GO with a stale request_payload_hash:
    AUTONOMY_PAUSED before POLICY_VALIDATION_REQUIRED/AUTO_APPROVED."""
    root, repo, head, cfg = env
    policy.write_initial_policy(root)
    _submit(root, cfg, head, "GO")  # published human-gated
    _tamper_request_file(root, RID, rehash=False)
    chain_before = len(events.read_chain(root))
    rc = claude_watch.main(["--once", "--request-id", RID])
    err = capsys.readouterr().err
    assert "request integrity failure" in err
    _assert_watcher_paused_before_policy(root, repo, head, rc, chain_before)


def test_watcher_pauses_on_recomputed_hash_request_tamper(env, capsys):
    """Codex's second variant: a SELF-CONSISTENT recomputed
    request_payload_hash still contradicts the event-pinned hash — the
    real watcher path must pause, never evaluate policy."""
    root, repo, head, cfg = env
    policy.write_initial_policy(root)
    _submit(root, cfg, head, "GO")
    _tamper_request_file(root, RID, rehash=True)
    chain_before = len(events.read_chain(root))
    rc = claude_watch.main(["--once", "--request-id", RID])
    err = capsys.readouterr().err
    assert "does not match the hash pinned" in err
    _assert_watcher_paused_before_policy(root, repo, head, rc, chain_before)


def test_watcher_pauses_on_blocked_verdict_with_tampered_request(env,
                                                                 capsys):
    """Fail-closed is unconditional: even a BLOCKED verdict for a tampered
    request pauses instead of printing findings from an untrusted file."""
    root, repo, head, cfg = env
    ctx = drive_to_claimed(root, cfg, repo, head, request_id=RID)
    verdict = _signed(head, verdict="BLOCKED", blockers=["x"],
                      summary="blocked")
    codex_watch.submit_verdict(root, cfg, verdict)
    locking.release(ctx["lock"])
    _tamper_request_file(root, RID, rehash=True)
    rc = claude_watch.main(["--once", "--request-id", RID])
    assert rc == 1
    assert events.read_chain(root)[-1]["event_type"] == "AUTONOMY_PAUSED"


def test_timeout_exits_cleanly(env):
    root, _repo, _head, _cfg = env
    rc = claude_watch.main(["--poll-seconds", "0.01",
                            "--timeout-seconds", "0.05"])
    assert rc == 0


def test_cursor_prevents_reprocessing(env, capsys):
    root, repo, head, cfg = env
    _submit(root, cfg, head, "GO")
    assert claude_watch.main(["--once", "--request-id", RID]) == 0
    length_after_first = len(events.read_chain(root))
    assert claude_watch.main(["--once", "--request-id", RID]) == 0
    # second pass consumed only the watcher's own appended events; it never
    # re-handles the GO (no second POLICY_VALIDATION_REQUIRED)
    types = [e["event_type"] for e in events.read_chain(root)]
    assert types.count("POLICY_VALIDATION_REQUIRED") == 1
    assert len(events.read_chain(root)) == length_after_first


def test_emergency_stop_stops_watcher(env, capsys):
    root, repo, head, cfg = env
    open(os.path.join(root, "STOP"), "w").close()
    rc = claude_watch.main(["--once", "--request-id", RID])
    out = capsys.readouterr().out
    assert rc == 0
    assert "emergency stop" in out
    assert events.read_chain(root)[-1]["event_type"] == "AUTONOMY_PAUSED"


def test_three_consecutive_errors_pause_autonomy(env, capsys):
    root, repo, head, cfg = env
    for i in range(1, 4):
        rid = f"watch-req-bad-{i}"
        ctx = drive_to_claimed(root, cfg, repo, head, request_id=rid)
        append(root, cfg, "AUDIT_GO", "codex", rid, repo, head,
               {"verdict": "GO", "invalid": True})
        locking.release(ctx["lock"])
    rc = claude_watch.main(["--once"])
    assert rc == 1
    chain = events.read_chain(root)
    assert chain[-1]["event_type"] == "AUTONOMY_PAUSED"
    assert "consecutive watcher errors" in chain[-1]["payload"]["reason"]


def test_duplicate_claim_refused(env):
    root, repo, head, cfg = env
    ctx = drive_to_claimed(root, cfg, repo, head, request_id=RID)
    with pytest.raises((LockHeld, Exception)):
        codex_watch.claim(root, cfg, RID)
    locking.release(ctx["lock"])


def test_milestone_event_stops_watcher(env, capsys):
    root, repo, head, cfg = env
    append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    append(root, cfg, "AUTONOMY_MILESTONE_REACHED", "claude", RID, repo,
           head, {"reason": "society milestone"})
    rc = claude_watch.main(["--once"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "milestone reached" in out
