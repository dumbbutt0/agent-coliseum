"""claude_watch behavior: verdict routing, hard validation, autonomy gate,
timeouts, cursor discipline; codex claim exclusivity."""
import os

import pytest

from tests.council_util import (append, drive_to_claimed, make_autonomy_block,
                                make_cfg, make_finding, make_repo, make_root,
                                make_verdict)
from tools.council import claude_watch, codex_watch, events, locking, policy, \
    storage
from tools.council.schemas import (CouncilError, LockHeld, SchemaViolation,
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


def _result_bindings(root, rid, head):
    """The H3 result-verdict bindings derived from the chain (for raw
    RESULT_* appends that also set custom findings/summary)."""
    from tests.council_util import _inject_test_bindings
    v = {}
    _inject_test_bindings(root, v, rid, head, True)
    v["schema_version"] = "result-verdict.v2"
    return v


def _signed(head, result_audit=False, **overrides):
    verdict = make_verdict(head, request_id=overrides.pop("request_id", RID),
                           **overrides)
    # new (2.0) verdict events are domain-separated (H2): stamp the
    # matching v2 schema_version the way submit_verdict does
    verdict["schema_version"] = ("result-verdict.v2" if result_audit
                                 else "source-verdict.v2")
    verdict["verdict_payload_hash"] = compute_verdict_payload_hash(verdict)
    return verdict


def _submit(root, cfg, head, verdict_kind, rid=RID, **request_overrides):
    ctx = drive_to_claimed(root, cfg, *_repo_head(cfg), request_id=rid,
                           **request_overrides)
    verdict = _signed(head, request_id=rid, verdict=verdict_kind)
    codex_watch.submit_verdict(root, cfg, verdict)
    # no manual lock release: the submit transaction releases the claim
    # lock itself (launcher audit cycle-3 blocker)
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
                      findings=[make_finding(
                          claim="probe wrote one cell",
                          reproduced=True, severity="HIGH",
                          blocks_requested_action=True)],
                      summary="still blocked")
    codex_watch.submit_verdict(root, cfg, verdict)
    assert locking.read_lock(root, RID) is None  # submit released the claim
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


def test_append_boundary_refuses_malformed_verdict_events(env):
    """launcher cycle-5 blocker: verdict EVENTS must carry a fully valid
    nested verdict — a malformed one never enters the chain at all."""
    root, repo, head, cfg = env
    ctx = drive_to_claimed(root, cfg, repo, head, request_id=RID)
    length = len(events.read_chain(root))
    from tools.council.schemas import compute_verdict_payload_hash
    cases = [
        {"verdict": "GO", "note": "missing everything"},   # missing fields
        _signed("c" * 40),                                 # commit mismatch
        _signed(head, request_id="watch-req-other"),       # nested rid off
        _signed(head, verdict="APPROVED"),                 # result vocab on
                                                           # a source event
    ]
    stale = _signed(head)
    stale["summary"] = "silently edited"                   # hash now stale
    cases.append(stale)
    mismatch = make_verdict(head, RID, verdict="BLOCKED")  # valid verdict,
    mismatch["verdict_payload_hash"] = \
        compute_verdict_payload_hash(mismatch)             # wrong event type
    cases.append(mismatch)
    for payload in cases:
        with pytest.raises(CouncilError):
            append(root, cfg, "AUDIT_GO", "codex", RID, repo, head, payload)
    assert len(events.read_chain(root)) == length  # nothing entered
    locking.release(ctx["lock"])


def test_append_boundary_refuses_malformed_result_verdict_events(env):
    root, repo, head, cfg = env
    _submit(root, cfg, head, "GO")
    assert claude_watch.main(["--once", "--request-id", RID]) == 0
    append(root, cfg, "EXPERIMENT_APPROVED", "human", RID, repo, head,
           {"approved_by": "human"})
    append(root, cfg, "EXPERIMENT_STARTED", "claude", RID, repo, head)
    append(root, cfg, "EXPERIMENT_COMPLETE", "claude", RID, repo, head)
    append(root, cfg, "RESULT_VALIDATION_REQUIRED", "claude", RID, repo,
           head)
    append(root, cfg, "RESULT_AUDIT_REQUESTED", "claude", RID, repo, head)
    length = len(events.read_chain(root))
    for payload in ({"verdict": "APPROVED"},               # missing fields
                    _signed(head, verdict="GO")):          # source vocab on
        with pytest.raises(CouncilError):                  # a result event
            append(root, cfg, "RESULT_APPROVED", "codex", RID, repo, head,
                   payload)
    assert len(events.read_chain(root)) == length


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


# --------------- claim-lock lifecycle through the REAL CLI (launcher cycle 3)

def _publish_fresh(root, cfg, repo, head, rid=RID):
    from tests.council_util import make_request
    append(root, cfg, "BUILD_STARTED", "claude", rid, repo, head)
    append(root, cfg, "BUILD_READY", "claude", rid, repo, head)
    from tools.council import publish
    publish.publish_request(root, cfg, make_request(repo, head, rid))


def test_cli_claim_submit_releases_lock_and_reaudit_claimable(
        env, tmp_path, monkeypatch, capsys):
    """Codex cycle-3 blocker regression, against the ACTUAL CLI in separate
    invocations: after --submit the claim lock is gone, exactly one verdict
    exists with all artifacts, a duplicate submit refuses, and a
    READY_FOR_REAUDIT of the SAME request id is claimable unattended."""
    import json as _json
    root, repo, head, cfg = env
    _publish_fresh(root, cfg, repo, head)
    assert codex_watch.main(["--claim", RID]) == 0
    vfile = tmp_path / "verdict.json"
    vfile.write_text(_json.dumps(
        make_verdict(head, RID, verdict="BLOCKED", blockers=["b1"])))
    assert codex_watch.main(["--submit", str(vfile)]) == 0
    # lock RELEASED by the submit transaction itself
    assert locking.read_lock(root, RID) is None
    chain = events.read_chain(root)
    assert [e["event_type"] for e in chain
            if e["request_id"] == RID].count("AUDIT_BLOCKED") == 1
    assert os.path.exists(storage.verdict_path(root, RID))
    assert os.path.exists(storage.safe_request_path(root, "complete", RID))
    with open(os.path.join(root, "log.md"), encoding="utf-8") as fh:
        assert "Verdict (structured): BLOCKED" in fh.read()
    # a second submit must refuse (the verdict event is the authority)
    assert codex_watch.main(["--submit", str(vfile)]) == 1
    # unattended re-audit of the SAME id: archive slot, republish, claim
    os.rename(storage.safe_request_path(root, "complete", RID),
              storage.safe_request_path(root, "complete", RID)
              .replace(".json", ".blocked-archived.json"))
    append(root, cfg, "FIX_STARTED", "claude", RID, repo, head)
    append(root, cfg, "BUILD_READY", "claude", RID, repo, head)
    from tests.council_util import make_request
    from tools.council import publish
    publish.publish_request(root, cfg, make_request(repo, head, RID),
                            reaudit=True)
    assert codex_watch.main(["--claim", RID]) == 0  # no stale lock in the way


def test_cli_go_and_result_submissions_release_lock(env, tmp_path):
    """The release holds for GO and for result-audit submissions too."""
    import json as _json
    root, repo, head, cfg = env
    _publish_fresh(root, cfg, repo, head)
    assert codex_watch.main(["--claim", RID]) == 0
    vfile = tmp_path / "go.json"
    vfile.write_text(_json.dumps(make_verdict(head, RID, verdict="GO")))
    assert codex_watch.main(["--submit", str(vfile)]) == 0
    assert locking.read_lock(root, RID) is None
    # continue to result_audit and submit APPROVED through the CLI
    append(root, cfg, "POLICY_VALIDATION_REQUIRED", "claude", RID, repo, head)
    append(root, cfg, "HUMAN_APPROVAL_REQUIRED", "claude", RID, repo, head)
    append(root, cfg, "EXPERIMENT_APPROVED", "human", RID, repo, head)
    append(root, cfg, "EXPERIMENT_STARTED", "claude", RID, repo, head)
    append(root, cfg, "EXPERIMENT_COMPLETE", "claude", RID, repo, head)
    append(root, cfg, "RESULT_VALIDATION_REQUIRED", "claude", RID, repo, head)
    os.rename(storage.safe_request_path(root, "complete", RID),
              storage.safe_request_path(root, "claimed", RID))
    append(root, cfg, "RESULT_AUDIT_REQUESTED", "claude", RID, repo, head)
    rfile = tmp_path / "result.json"
    rfile.write_text(_json.dumps(
        make_verdict(head, RID, verdict="APPROVED")))
    assert codex_watch.main(["--submit", str(rfile), "--result-audit"]) == 0
    assert locking.read_lock(root, RID) is None
    from tools.council import state_machine
    chain = events.read_chain(root)
    assert state_machine.project(chain)[RID]["state"] == "result_approved"
    assert codex_watch.main(["--submit", str(rfile), "--result-audit"]) == 1


# ---- strict verdict types at every boundary (audit-002 cycle 1 blocker)

def test_wrong_type_verdict_refused_at_every_boundary(env, capsys):
    """Codex's probe: a correctly bound, self-consistently hashed verdict
    with wrong-typed structured fields must refuse at ALL four boundaries —
    append_event, generic cli record, codex_watch submit, and recovery."""
    import json as _json
    from tools.council import cli as council_cli
    from tools.council.schemas import (canonical_json, compute_event_hash,
                                       compute_verdict_payload_hash)
    root, repo, head, cfg = env
    ctx = drive_to_claimed(root, cfg, repo, head, request_id=RID)
    bad = make_verdict(head, RID)
    bad["blockers"] = "not-a-list"
    bad["findings"] = "not-a-list"
    bad["verdict_payload_hash"] = compute_verdict_payload_hash(bad)
    # 1. append boundary
    with pytest.raises(CouncilError):
        append(root, cfg, "AUDIT_GO", "codex", RID, repo, head, bad)
    # 2. generic cli record
    rc = council_cli.main(["--role", "codex", "record", "--type", "AUDIT_GO",
                           "--request-id", RID, "--repository", repo,
                           "--commit", head,
                           "--payload-json", _json.dumps(bad)])
    assert rc == 1
    # 3. codex_watch submit (recomputes the hash itself — still refused)
    with pytest.raises(CouncilError):
        codex_watch.submit_verdict(root, make_cfg(repo, root, role="codex"),
                                   bad)
    types = [e["event_type"] for e in events.read_chain(root)]
    assert "AUDIT_GO" not in types
    # 4. recovery over a hand-chained wrong-type historical event: zero
    # mutations (legacy-style injection; the append boundary refuses new)
    chain = events.read_chain(root)
    event = {
        "protocol_version": "1.0",
        "event_id": f"{len(chain) + 1:06d}-deadbeef",
        "event_type": "AUDIT_GO", "request_id": RID, "sender": "codex",
        "timestamp_utc": storage.utc_now(), "repository": repo,
        "target_commit": head, "payload": bad,
        "previous_event_hash": chain[-1]["event_hash"],
    }
    event["event_hash"] = compute_event_hash(event)
    storage.append_line(storage.events_path(root), canonical_json(event))
    healed = codex_watch.finalize_incomplete(
        root, make_cfg(repo, root, role="codex"))
    assert RID not in healed
    assert "invalid verdict payload" in capsys.readouterr().err
    assert os.path.exists(storage.safe_request_path(root, "claimed", RID))
    assert locking.read_lock(root, RID) is not None
    assert not os.path.exists(storage.verdict_path(root, RID))
    locking.release(ctx["lock"])


# ---- recovery authority requires validity (launcher cycle 5 blocker)

def test_recovery_never_promotes_invalid_historical_verdict(env, capsys):
    """A hash-chained but schema-invalid terminal event (legacy-style —
    the append boundary refuses new ones) must NEVER be promoted into
    verdict artifacts or lock clearance: recovery fails closed with zero
    mutations and reports the integrity failure for owner-led migration."""
    root, repo, head, cfg = env
    ctx = drive_to_claimed(root, cfg, repo, head, request_id=RID)
    from tools.council.schemas import canonical_json, compute_event_hash
    chain = events.read_chain(root)
    event = {
        "protocol_version": "1.0",
        "event_id": f"{len(chain) + 1:06d}-deadbeef",
        "event_type": "AUDIT_GO",
        "request_id": RID,
        "sender": "codex",
        "timestamp_utc": storage.utc_now(),
        "repository": repo,
        "target_commit": head,
        "payload": {"verdict": "GO", "invalid": True},
        "previous_event_hash": chain[-1]["event_hash"],
    }
    event["event_hash"] = compute_event_hash(event)
    storage.append_line(storage.events_path(root), canonical_json(event))
    assert events.verify_chain(root).ok  # chained — i.e. "legacy-valid"
    codex_cfg = make_cfg(repo, root, role="codex")
    length = len(events.read_chain(root))
    healed = codex_watch.finalize_incomplete(root, codex_cfg)
    err = capsys.readouterr().err
    assert RID not in healed
    assert "invalid verdict payload" in err
    assert "owner-led migration" in err
    # ZERO mutations: claimed file, lock, verdict json, chain untouched
    assert os.path.exists(storage.safe_request_path(root, "claimed", RID))
    assert locking.read_lock(root, RID) is not None
    assert not os.path.exists(storage.verdict_path(root, RID))
    assert len(events.read_chain(root)) == length
    locking.release(ctx["lock"])


# ------- post-event finalization is idempotent (launcher cycle 4 blocker)

def _terminal_events(root, rid=RID, etype=None):
    return [e for e in events.read_chain(root)
            if e["request_id"] == rid
            and e["event_type"] in ((etype,) if etype else
                                    ("AUDIT_BLOCKED", "AUDIT_GO",
                                     "AUDIT_GO_WITH_CONDITIONS",
                                     "RESULT_APPROVED", "RESULT_BLOCKED"))]


def test_artifact_failure_after_verdict_is_recoverable(
        env, tmp_path, monkeypatch, capsys):
    """Codex cycle-4 probe: verdict-JSON write fails AFTER the terminal
    event. The event stays the single authority, the lock is released
    anyway, a WATCHER_ERROR records the miss, and watcher-startup
    finalization reconstructs the artifacts FROM THE CHAIN — no second
    verdict, no manual lock deletion, and the same id re-audits cleanly."""
    import json as _json
    root, repo, head, cfg = env
    _publish_fresh(root, cfg, repo, head)
    assert codex_watch.main(["--claim", RID]) == 0
    codex_cfg = make_cfg(repo, root, role="codex")
    verdict = make_verdict(head, RID, verdict="BLOCKED", blockers=["b"])
    with monkeypatch.context() as m:
        def boom(path, obj):
            raise OSError("simulated disk failure")
        m.setattr(storage, "atomic_write_json", boom)
        with pytest.raises(CouncilError, match="IS authoritative"):
            codex_watch.submit_verdict(root, codex_cfg, verdict)
    chain = events.read_chain(root)
    terminal = _terminal_events(root, etype="AUDIT_BLOCKED")
    assert len(terminal) == 1                      # exactly one verdict
    assert locking.read_lock(root, RID) is None    # released DESPITE failure
    errors = [e for e in chain if e["event_type"] == "WATCHER_ERROR"]
    assert errors[-1]["payload"]["phase"] == "verdict_finalization"
    assert os.path.exists(storage.safe_request_path(root, "claimed", RID))
    assert not os.path.exists(storage.verdict_path(root, RID))
    # recovery on watcher restart — idempotent, chain-derived
    assert codex_watch.main(["--once"]) == 0
    assert "finalized incomplete verdict artifacts" in \
        capsys.readouterr().out
    with open(storage.verdict_path(root, RID), encoding="utf-8") as fh:
        assert _json.load(fh) == terminal[0]["payload"]
    assert os.path.exists(storage.safe_request_path(root, "complete", RID))
    assert not os.path.exists(storage.safe_request_path(root, "claimed", RID))
    assert len(_terminal_events(root)) == 1
    # the absent lock never permits a second verdict
    with pytest.raises(CouncilError):
        codex_watch.submit_verdict(root, codex_cfg, verdict)
    assert len(_terminal_events(root)) == 1
    # unattended re-audit of the same id still works after recovery
    os.rename(storage.safe_request_path(root, "complete", RID),
              storage.safe_request_path(root, "complete", RID)
              .replace(".json", ".blocked-archived.json"))
    append(root, cfg, "FIX_STARTED", "claude", RID, repo, head)
    append(root, cfg, "BUILD_READY", "claude", RID, repo, head)
    from tests.council_util import make_request
    from tools.council import publish
    publish.publish_request(root, cfg, make_request(repo, head, RID),
                            reaudit=True)
    assert codex_watch.main(["--claim", RID]) == 0


def test_rename_failure_after_go_verdict_is_recoverable(env, monkeypatch):
    """The claimed->complete rename fails after a GO: same guarantees, and
    direct finalize_incomplete() heals without any event."""
    root, repo, head, cfg = env
    _publish_fresh(root, cfg, repo, head)
    assert codex_watch.main(["--claim", RID]) == 0
    codex_cfg = make_cfg(repo, root, role="codex")
    verdict = make_verdict(head, RID, verdict="GO")
    real_rename = os.rename
    with monkeypatch.context() as m:
        def boom(src, dst):
            if os.sep + "claimed" + os.sep in str(src):
                raise OSError("simulated rename failure")
            return real_rename(src, dst)
        m.setattr(os, "rename", boom)
        with pytest.raises(CouncilError, match="IS authoritative"):
            codex_watch.submit_verdict(root, codex_cfg, verdict)
    assert locking.read_lock(root, RID) is None
    assert os.path.exists(storage.verdict_path(root, RID))  # write succeeded
    assert os.path.exists(storage.safe_request_path(root, "claimed", RID))
    chain_len = len(events.read_chain(root))
    healed = codex_watch.finalize_incomplete(root, codex_cfg)
    assert RID in healed
    assert os.path.exists(storage.safe_request_path(root, "complete", RID))
    assert not os.path.exists(storage.safe_request_path(root, "claimed", RID))
    assert len(events.read_chain(root)) == chain_len  # heals append NOTHING
    assert len(_terminal_events(root)) == 1


def test_result_verdict_artifact_failure_is_recoverable(env, monkeypatch):
    root, repo, head, cfg = env
    _drive_to_result_audit(root, cfg, repo, head)
    os.rename(storage.safe_request_path(root, "complete", RID),
              storage.safe_request_path(root, "claimed", RID))
    codex_cfg = make_cfg(repo, root, role="codex")
    verdict = make_verdict(head, RID, verdict="APPROVED")
    with monkeypatch.context() as m:
        def boom(path, obj):
            raise OSError("simulated disk failure")
        m.setattr(storage, "atomic_write_json", boom)
        with pytest.raises(CouncilError, match="IS authoritative"):
            codex_watch.submit_verdict(root, codex_cfg, verdict,
                                       result_audit=True)
    assert len(_terminal_events(root, etype="RESULT_APPROVED")) == 1
    healed = codex_watch.finalize_incomplete(root, codex_cfg)
    assert RID in healed
    import json as _json
    with open(storage.verdict_path(root, RID), encoding="utf-8") as fh:
        assert _json.load(fh)["verdict"] == "APPROVED"  # chain-derived
    assert os.path.exists(storage.safe_request_path(root, "complete", RID))
    from tools.council import state_machine
    assert state_machine.project(
        events.read_chain(root))[RID]["state"] == "result_approved"


def test_log_mirror_failure_never_fails_the_submission(env, monkeypatch):
    root, repo, head, cfg = env
    _publish_fresh(root, cfg, repo, head)
    assert codex_watch.main(["--claim", RID]) == 0
    codex_cfg = make_cfg(repo, root, role="codex")
    verdict = make_verdict(head, RID, verdict="GO")
    with monkeypatch.context() as m:
        def boom(root_, author, body):
            raise OSError("mirror unavailable")
        m.setattr(storage, "append_log_md", boom)
        event = codex_watch.submit_verdict(root, codex_cfg, verdict)
    assert event["event_type"] == "AUDIT_GO"
    assert len(_terminal_events(root)) == 1
    assert locking.read_lock(root, RID) is None
    assert os.path.exists(storage.verdict_path(root, RID))
    assert os.path.exists(storage.safe_request_path(root, "complete", RID))
    last = events.read_chain(root)[-1]
    assert last["event_type"] == "WATCHER_ERROR"
    assert last["payload"]["phase"] == "verdict_log_mirror"


# ------------------- source-task routing (council-protocol-delta cycle 2)

def test_source_go_stays_at_go_then_integrates_commit_bound(env, capsys):
    """Codex cycle-1 blocker regression: the real watcher must consume a
    source-task GO WITHOUT any experiment policy transition, leaving state
    `go` so a commit-bound CHANGE_INTEGRATED succeeds — and a different
    commit is refused."""
    root, repo, head, cfg = env
    _submit(root, cfg, head, "GO", task_kind="source")
    rc = claude_watch.main(["--once", "--request-id", RID])
    out = capsys.readouterr().out
    assert rc == 0
    assert "source task" in out and "state remains `go`" in out
    from tools.council import state_machine
    chain = events.read_chain(root)
    types = [e["event_type"] for e in chain]
    assert "POLICY_VALIDATION_REQUIRED" not in types
    assert "AUTO_APPROVED" not in types
    assert "HUMAN_APPROVAL_REQUIRED" not in types
    assert state_machine.project(chain)[RID]["state"] == "go"
    # a GO for one commit never authorizes integrating another
    with pytest.raises(CouncilError):
        append(root, cfg, "CHANGE_INTEGRATED", "claude", RID, repo, "e" * 40,
               {"integrated_commit": "e" * 40})
    append(root, cfg, "CHANGE_INTEGRATED", "claude", RID, repo, head,
           {"integrated_commit": head, "integration_method": "fast-forward"})
    chain = events.read_chain(root)
    assert state_machine.project(chain)[RID]["state"] == "integrated"


def test_source_conditional_verdict_gates_integration_on_human(env, capsys):
    """Codex cycle-2 blocker regression: after source GO_WITH_CONDITIONS,
    CHANGE_INTEGRATED is mechanically refused until a HUMAN records
    CONDITIONS_SATISFIED; the sign-off is commit-bound; and after it a
    wrong-commit integration still refuses while the audited commit
    integrates."""
    root, repo, head, cfg = env
    _submit(root, cfg, head, "GO_WITH_CONDITIONS", task_kind="source")
    rc = claude_watch.main(["--once", "--request-id", RID])
    out = capsys.readouterr().out
    assert rc == 0
    assert "conditions attached" in out and "approve-conditions" in out
    from tools.council import state_machine
    chain = events.read_chain(root)
    assert "POLICY_VALIDATION_REQUIRED" not in \
        [e["event_type"] for e in chain]
    assert state_machine.project(chain)[RID]["state"] == "go"
    # 1. no human sign-off -> integration refused
    with pytest.raises(CouncilError):
        append(root, cfg, "CHANGE_INTEGRATED", "claude", RID, repo, head,
               {"integrated_commit": head})
    # 2. claude cannot forge the sign-off (human-only role)
    with pytest.raises(CouncilError):
        append(root, cfg, "CONDITIONS_SATISFIED", "claude", RID, repo, head)
    # 3. the human sign-off itself is commit-bound
    with pytest.raises(CouncilError):
        append(root, cfg, "CONDITIONS_SATISFIED", "human", RID, repo,
               "e" * 40)
    # 4. authoritative human sign-off via the owner CLI
    from tools.council import cli as council_cli
    rc = council_cli.main(["--role", "human", "approve-conditions", RID,
                           "--commit", head])
    assert rc == 0
    # 5. wrong commit still refused; the audited commit integrates
    with pytest.raises(CouncilError):
        append(root, cfg, "CHANGE_INTEGRATED", "claude", RID, repo, "e" * 40,
               {"integrated_commit": "e" * 40})
    append(root, cfg, "CHANGE_INTEGRATED", "claude", RID, repo, head,
           {"integrated_commit": head, "integration_method": "fast-forward"})
    chain = events.read_chain(root)
    assert state_machine.project(chain)[RID]["state"] == "integrated"


def test_conditions_satisfied_requires_conditional_verdict(env):
    """The sign-off is meaningless (and refused) when the last verdict is
    an unconditional GO."""
    root, repo, head, cfg = env
    _submit(root, cfg, head, "GO", task_kind="source")
    assert claude_watch.main(["--once", "--request-id", RID]) == 0
    with pytest.raises(CouncilError):
        append(root, cfg, "CONDITIONS_SATISFIED", "human", RID, repo, head)


def test_experiment_go_still_enters_policy_validation(env, capsys):
    """The discriminator must not disturb experiment routing: an explicit
    task_kind=experiment request behaves exactly like the legacy default."""
    root, repo, head, cfg = env
    policy.write_initial_policy(root)
    _submit(root, cfg, head, "GO", task_kind="experiment",
            human_approval_required=False, autonomy=make_autonomy_block())
    rc = claude_watch.main(["--once", "--request-id", RID])
    assert rc == 0
    types = [e["event_type"] for e in events.read_chain(root)]
    assert types[-2:] == ["POLICY_VALIDATION_REQUIRED", "AUTO_APPROVED"]


def test_policy_continue_refuses_source_task(env, capsys):
    """The manual recovery path must not smuggle a source task into the
    experiment policy machinery either."""
    import argparse
    from tools.autonomy import cli as autonomy_cli
    root, repo, head, cfg = env
    _submit(root, cfg, head, "GO", task_kind="source")
    # consume the GO so state is `go` with the cursor advanced
    assert claude_watch.main(["--once", "--request-id", RID]) == 0
    rc = autonomy_cli.cmd_policy_continue(
        cfg, argparse.Namespace(request_id=RID))
    err = capsys.readouterr().err
    assert rc == 1
    assert "source task" in err
    types = [e["event_type"] for e in events.read_chain(root)]
    assert "POLICY_VALIDATION_REQUIRED" not in types


# ------------------------- result-verdict handling (council-protocol-delta)

def _drive_to_result_audit(root, cfg, repo, head):
    """GO through the human gate to result_audit, with the watcher cursor
    advanced past the GO event (the watcher handled it)."""
    _submit(root, cfg, head, "GO")
    assert claude_watch.main(["--once", "--request-id", RID]) == 0
    append(root, cfg, "EXPERIMENT_APPROVED", "human", RID, repo, head,
           {"approved_by": "human"})
    append(root, cfg, "EXPERIMENT_STARTED", "claude", RID, repo, head)
    append(root, cfg, "EXPERIMENT_COMPLETE", "claude", RID, repo, head)
    append(root, cfg, "RESULT_VALIDATION_REQUIRED", "claude", RID, repo, head)
    append(root, cfg, "RESULT_AUDIT_REQUESTED", "claude", RID, repo, head)


def test_result_audit_approved_submits_through_wrapper(env, capsys):
    """The 2026-07-11 defect regression: codex_watch --submit --result-audit
    must accept an APPROVED result verdict (no generic-record workaround)."""
    root, repo, head, cfg = env
    _drive_to_result_audit(root, cfg, repo, head)
    # the runner moves the request file back to claimed/ for the result
    # audit; mimic that protocol file operation
    os.rename(storage.safe_request_path(root, "complete", RID),
              storage.safe_request_path(root, "claimed", RID))
    codex_cfg = make_cfg(repo, root, role="codex")
    verdict = make_verdict(head, RID, verdict="APPROVED")
    event = codex_watch.submit_verdict(root, codex_cfg, verdict,
                                       result_audit=True)
    assert event["event_type"] == "RESULT_APPROVED"
    from tools.council import state_machine
    requests = state_machine.project(events.read_chain(root))
    assert requests[RID]["state"] == "result_approved"


def test_result_audit_approved_refused_on_source_audit_path(env):
    """APPROVED stays invalid for SOURCE audits — only the result-audit
    wrapper accepts it."""
    root, repo, head, cfg = env
    ctx = drive_to_claimed(root, cfg, repo, head, request_id=RID)
    codex_cfg = make_cfg(repo, root, role="codex")
    verdict = make_verdict(head, RID, verdict="APPROVED")
    with pytest.raises(CouncilError):
        codex_watch.submit_verdict(root, codex_cfg, verdict)
    locking.release(ctx["lock"])


def test_watcher_wakes_on_result_approved_and_records_milestone(env, capsys):
    """After RESULT_APPROVED the watcher records NEXT_MILESTONE_READY —
    the loop advances instead of sleeping forever."""
    root, repo, head, cfg = env
    _drive_to_result_audit(root, cfg, repo, head)
    append(root, cfg, "RESULT_APPROVED", "codex", RID, repo, head)
    rc = claude_watch.main(["--once", "--request-id", RID])
    out = capsys.readouterr().out
    assert rc == 0
    assert "NEXT_MILESTONE_READY recorded" in out
    chain = events.read_chain(root)
    assert chain[-1]["event_type"] == "NEXT_MILESTONE_READY"
    assert chain[-1]["payload"]["completed_request"] == RID


def test_watcher_result_approved_is_idempotent(env, capsys):
    """A cursor replay (crash/restart) must not duplicate
    NEXT_MILESTONE_READY."""
    root, repo, head, cfg = env
    _drive_to_result_audit(root, cfg, repo, head)
    saved = storage.read_cursor(root, "claude")
    append(root, cfg, "RESULT_APPROVED", "codex", RID, repo, head)
    assert claude_watch.main(["--once", "--request-id", RID]) == 0
    length = len(events.read_chain(root))
    # simulate a crash that lost the cursor advance: replay from before
    storage.write_cursor(root, "claude", saved["byte_offset"],
                         saved["last_event_hash"], saved["last_event_id"])
    rc = claude_watch.main(["--once", "--request-id", RID])
    out = capsys.readouterr().out
    assert rc == 0
    assert "already recorded" in out
    assert len(events.read_chain(root)) == length


def test_watcher_result_blocked_prints_and_stops(env, capsys):
    root, repo, head, cfg = env
    _drive_to_result_audit(root, cfg, repo, head)
    from tools.council.schemas import compute_verdict_payload_hash
    payload = {**make_verdict(head, RID, verdict="BLOCKED",
                              blockers=["evidence dir incomplete"],
                              summary="result blocked"),
               **_result_bindings(root, RID, head)}
    payload["verdict_payload_hash"] = compute_verdict_payload_hash(payload)
    append(root, cfg, "RESULT_BLOCKED", "codex", RID, repo, head, payload)
    length = len(events.read_chain(root))
    rc = claude_watch.main(["--once", "--request-id", RID])
    out = capsys.readouterr().out
    assert rc == 0
    assert "RESULT_BLOCKED" in out and "evidence dir incomplete" in out
    # the record is the verdict itself: the watcher appends nothing
    assert len(events.read_chain(root)) == length


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


def test_three_consecutive_errors_pause_autonomy(env, capsys, monkeypatch):
    """The append boundary now refuses malformed verdicts outright, so the
    watcher's consecutive-error machinery is exercised by forcing its own
    validation layer (defense in depth for legacy chains) to reject three
    otherwise-valid verdicts."""
    root, repo, head, cfg = env
    for i in range(1, 4):
        _submit(root, cfg, head, "GO", rid=f"watch-req-bad-{i}")

    def refuse(*_a, **_k):
        raise SchemaViolation("forced validation failure (legacy-chain "
                              "defense-in-depth probe)")
    monkeypatch.setattr(claude_watch, "_validate_verdict_event", refuse)
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
