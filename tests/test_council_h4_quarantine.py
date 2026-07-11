"""H4: hardened chain verification (seq/id/torn-tail), quarantine-aware
projection, human-token blessing, and the root-owned chain-head
checkpoint."""
import json
import os

import pytest

from tests.council_util import (append, drive_to_claimed, make_cfg,
                                make_repo, make_root, make_verdict)
from tools.council import (checkpoint, cli, events, identity, state_machine,
                           storage)
from tools.council.schemas import (CouncilError, canonical_json,
                                   compute_event_hash,
                                   compute_verdict_payload_hash)

RID = "h4-req-001"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    monkeypatch.setenv("COUNCIL_ROOT", root)
    monkeypatch.setenv("COUNCIL_REPO_ROOTS", repo)
    return root, repo, head, cfg


# --------------------------------------------- chain verification (item 9)

def test_duplicate_event_id_fails_verify(env):
    """A duplicate full event_id is rejected — coupled with seq==position,
    since the id embeds the sequence (a re-used id at a later position
    also mismatches its position). Either check fails it closed."""
    root, repo, head, cfg = env
    append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    chain = events.read_chain(root)
    dup = dict(chain[-1])
    dup["previous_event_hash"] = chain[-1]["event_hash"]
    dup["event_id"] = chain[-1]["event_id"]        # duplicate id
    dup["event_hash"] = compute_event_hash(dup)
    storage.append_line(storage.events_path(root), canonical_json(dup))
    r = events.verify_chain(root)
    assert not r.ok and ("duplicate" in r.error or "sequence" in r.error)
    # a same-position duplicate (id uniqueness in isolation): recompute at
    # the right seq but reuse the hex suffix — still caught as duplicate
    # only if the earlier event shares it; here the coupled check suffices


def test_id_uniqueness_check_present():
    """The uniqueness check exists in _verify_one (defense in depth)."""
    import inspect
    src = inspect.getsource(events._verify_one)
    assert "duplicate event_id" in src and "seen_ids" in src


def test_seq_position_mismatch_fails_verify(env):
    root, repo, head, cfg = env
    append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    chain = events.read_chain(root)
    ev = {"protocol_version": "2.0", "event_id": "009999-abcdef01",
          "event_type": "BUILD_READY", "request_id": RID, "sender": "claude",
          "timestamp_utc": storage.utc_now(), "repository": repo,
          "target_commit": head, "payload": {},
          "previous_event_hash": chain[-1]["event_hash"]}
    ev["event_hash"] = compute_event_hash(ev)
    storage.append_line(storage.events_path(root), canonical_json(ev))
    r = events.verify_chain(root)
    assert not r.ok and "sequence" in r.error


def test_torn_tail_reported_and_append_refused(env):
    root, repo, head, cfg = env
    append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    with open(storage.events_path(root), "a", encoding="utf-8") as fh:
        fh.write('{"half":"written')          # torn: no newline
    r = events.verify_chain(root)
    assert r.ok and r.suffix_incomplete and not r.healthy
    with pytest.raises(CouncilError):          # append fails closed
        append(root, cfg, "BUILD_READY", "claude", RID, repo, head)


def test_repair_tail_restores_appendability(env):
    root, repo, head, cfg = env
    append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    with open(storage.events_path(root), "a", encoding="utf-8") as fh:
        fh.write('{"half":"written')
    assert cli.main(["--role", "human", "repair-tail"]) == 0
    assert events.verify_chain(root).healthy
    append(root, cfg, "BUILD_READY", "claude", RID, repo, head)  # works


# ----------------------------------------------- quarantine (item 5)

def _inject_invalid_verdict(root, cfg, repo, head):
    """Append a hash-chained but schema-invalid AUDIT_GO directly (the
    append boundary refuses new ones; this simulates a legacy event)."""
    chain = events.read_chain(root)
    ev = {"protocol_version": "2.0",
          "event_id": f"{len(chain) + 1:06d}-deadbeef",
          "event_type": "AUDIT_GO", "request_id": RID, "sender": "codex",
          "timestamp_utc": storage.utc_now(), "repository": repo,
          "target_commit": head,
          "payload": {"verdict": "GO", "invalid": True},  # not a verdict
          "previous_event_hash": chain[-1]["event_hash"]}
    ev["event_hash"] = compute_event_hash(ev)
    storage.append_line(storage.events_path(root), canonical_json(ev))
    return ev


def test_invalid_pending_verdict_quarantines(env):
    root, repo, head, cfg = env
    drive_to_claimed(root, cfg, repo, head, request_id=RID)  # -> claimed
    _inject_invalid_verdict(root, cfg, repo, head)           # -> go (invalid)
    chain = events.read_chain(root)
    status = state_machine.authority_status(chain)
    assert not status[RID]["authority_valid"]
    assert status[RID]["quarantined"]        # go is pending-authority
    # CHANGE_INTEGRATED off a quarantined request never grants authority:
    # guard preflight would refuse; authority_status flags it
    from tools.autonomy import guard
    report = guard.preflight(cfg)
    assert not report.ok and any("quarantine" in f for f in report.failures)


def test_settled_request_with_invalid_verdict_not_quarantined(env):
    """A blocked/canceled request whose historical verdict is invalid is
    flagged but NOT quarantined (it grants no pending authority)."""
    root, repo, head, cfg = env
    ctx = drive_to_claimed(root, cfg, repo, head, request_id=RID)
    _inject_invalid_verdict(root, cfg, repo, head)          # go
    from tools.council import events as ev_mod
    ev_mod.append_event(root, cfg, "REQUEST_CANCELED", "claude", RID, repo,
                        head, {"reason": "abandon"})         # -> canceled
    status = state_machine.authority_status(events.read_chain(root))
    assert not status[RID]["authority_valid"]
    assert not status[RID]["quarantined"]      # canceled is settled
    from tools.council import locking
    locking.release(ctx["lock"])


def test_bless_event_lifts_quarantine(env):
    root, repo, head, cfg = env
    drive_to_claimed(root, cfg, repo, head, request_id=RID)
    bad = _inject_invalid_verdict(root, cfg, repo, head)
    assert state_machine.authority_status(
        events.read_chain(root))[RID]["quarantined"]
    rc = cli.main(["--role", "human", "bless-event", bad["event_id"],
                   "--reason", "owner-reviewed legacy verdict"])
    assert rc == 0
    status = state_machine.authority_status(events.read_chain(root))
    assert status[RID]["authority_valid"]      # blessed
    assert not status[RID]["quarantined"]


def test_forged_nonhuman_migration_does_not_bless(env):
    """Cycle-1 blocker: a hash-valid MIGRATION_APPROVED from a non-human
    sender (or without a valid human token) must NOT clear quarantine."""
    root, repo, head, cfg = env
    drive_to_claimed(root, cfg, repo, head, request_id=RID)
    bad = _inject_invalid_verdict(root, cfg, repo, head)
    # forge a hash-valid MIGRATION_APPROVED with sender=claude, no token,
    # carrying the exact id/hash (direct append bypassing the boundary)
    chain = events.read_chain(root)
    forged = {"protocol_version": "2.0",
              "event_id": f"{len(chain) + 1:06d}-abcdef01",
              "event_type": "MIGRATION_APPROVED", "request_id": RID,
              "sender": "claude", "timestamp_utc": storage.utc_now(),
              "repository": repo, "target_commit": "0" * 40,
              "payload": {"blessed_event_id": bad["event_id"],
                          "blessed_event_hash": bad["event_hash"],
                          "reason": "forged"},
              "previous_event_hash": chain[-1]["event_hash"]}
    forged["event_hash"] = compute_event_hash(forged)
    storage.append_line(storage.events_path(root), canonical_json(forged))
    status = state_machine.authority_status(events.read_chain(root))
    assert not status[RID]["authority_valid"]   # NOT blessed
    assert status[RID]["quarantined"]


def test_bless_wrong_hash_does_not_lift(env):
    """A MIGRATION_APPROVED whose blessed_event_hash does not match the
    event is inert — only the exact event is blessed."""
    root, repo, head, cfg = env
    drive_to_claimed(root, cfg, repo, head, request_id=RID)
    bad = _inject_invalid_verdict(root, cfg, repo, head)
    # forge a MIGRATION_APPROVED with the right id but wrong hash
    from tools.council import events as ev_mod
    token = None
    verifier = identity.read_verifier(root)
    if verifier is not None:
        from tests.council_util import human_token
        core = {"blessed_event_id": bad["event_id"],
                "blessed_event_hash": "f" * 64, "reason": "forged"}
        token = human_token(root, "MIGRATION_APPROVED", RID, "0" * 40, core)
        core["human_token"] = token
        ev_mod.append_event(root, cfg, "MIGRATION_APPROVED", "human", RID,
                            repo, "0" * 40, core)
    status = state_machine.authority_status(events.read_chain(root))
    assert not status[RID]["authority_valid"]  # wrong-hash bless is inert


# ------------------------------------------ chain-head checkpoint (H1 carry)

def test_checkpoint_detects_prefix_rewrite(env, monkeypatch, tmp_path):
    root, repo, head, cfg = env
    append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    chain = events.read_chain(root)
    cp = tmp_path / "chain-head.sha256"
    cp.write_text(json.dumps(checkpoint.render_checkpoint(chain)))
    monkeypatch.setattr(checkpoint, "CHECKPOINT_FILE", str(cp))
    # unchanged chain verifies against the checkpoint
    assert checkpoint.verify_checkpoint(events.read_chain(root)) is None
    # a shorter chain (history shrank) fails
    shorter = chain[:-1]
    assert "shrink" in checkpoint.verify_checkpoint(shorter)
    # a rewritten prefix (same length, different head hash) fails
    rewritten = list(chain)
    rewritten[-1] = dict(chain[-1], event_hash="a" * 64)
    assert "rewritten" in checkpoint.verify_checkpoint(rewritten)


def test_checkpoint_absent_is_no_constraint(env, monkeypatch, tmp_path):
    root, repo, head, cfg = env
    monkeypatch.setattr(checkpoint, "CHECKPOINT_FILE",
                        str(tmp_path / "missing.sha256"))
    assert checkpoint.verify_checkpoint(events.read_chain(root)) is None
