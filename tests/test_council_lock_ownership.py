"""Claim-lock release must PROVE ownership (worker-pool blocker).

`codex_watch.submit_verdict` and `codex_watch.finalize_incomplete` used to
release the claim lock with a tokenless `locking.Lock`, which
`locking.release` BLIND-UNLINKS. With more than one concurrent worker that
lets whichever session finishes first delete another live worker's claim
lock — the lock is the single claim authority, so that is a cross-worker
primitive. Both call sites now recover the owner token from the
codex-signed AUDIT_CLAIMED event (`payload.lock_holder`, which pins a
COMMITMENT of the token, never the secret itself) and release
compare-and-delete; when ownership cannot be proven they touch nothing and
leave the lock to the lease-expiry / logged stale-lock paths.

Pool-split ownership-002 f0: request-cycle proof alone is still not CALLER
proof — a normal submission for request B used to run the GLOBAL
finalize_incomplete sweep and thereby release request A's separately held
LIVE lock with A's chain-proven token. A normal submission now finalizes
ONLY its own request; the cross-request sweep survives exclusively behind
the explicit recovery entry points (codex_watch startup / a direct
finalize_incomplete call).
"""
import json
import os

import pytest

from tests.council_util import (append, drive_to_claimed, make_cfg,
                                make_repo, make_root, make_verdict)
from tools.council import codex_watch, events, locking, storage
from tools.council.schemas import compute_verdict_payload_hash

RID = "lockown-req-001"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root, role="codex")
    monkeypatch.setenv("COUNCIL_ROOT", root)
    monkeypatch.setenv("COUNCIL_REPO_ROOTS", repo)
    return root, repo, head, cfg


def _signed(head, rid=RID, verdict="GO"):
    body = make_verdict(head, request_id=rid, verdict=verdict)
    body["schema_version"] = "source-verdict.v2"
    body["verdict_payload_hash"] = compute_verdict_payload_hash(body)
    return body


def _replace_lock_with_other_worker(root, rid):
    """Simulate worker A holding a LIVE claim lock that this session did
    not mint: remove the current lock and acquire a fresh one whose token
    appears in no AUDIT_CLAIMED event."""
    locking.clear_lock(root, rid)
    return locking.acquire(root, rid, "codex", rid, kind="claim")


def _healthy(root):
    return events.verify_chain(root).healthy


# -------------------- cross-REQUEST release (pool-split ownership-002 f0)

RID_A = "lockown-req-a"
RID_B = "lockown-req-b"


def test_submitting_request_b_leaves_request_a_lock_byte_intact(env):
    """The verdict's minimum regression, through the PUBLIC submit API:
    session A's request has its terminal event on the chain while A's
    unexpired token-bearing claim lock is still LIVE; session B then
    normally submits a DIFFERENT request. B must fully finalize while A's
    lock survives byte-for-byte — completing request B is never the
    releasing session for request A's live claim lock."""
    root, repo, head, cfg = env
    ctx_a = drive_to_claimed(root, cfg, repo, head, request_id=RID_A)
    append(root, cfg, "AUDIT_GO", "codex", RID_A, repo, head)
    lock_a_path = storage.lock_path(root, RID_A)
    with open(lock_a_path, "rb") as fh:
        lock_a_before = fh.read()
    holder = locking.read_lock(root, RID_A)
    assert holder["owner_token"] == ctx_a["lock"].owner_token
    assert locking.lease_is_expired(holder) is False

    drive_to_claimed(root, cfg, repo, head, request_id=RID_B)
    codex_watch.submit_verdict(root, cfg, _signed(head, rid=RID_B))

    # B fully finalized: verdict artifact, complete/, lock released
    assert os.path.exists(storage.verdict_path(root, RID_B))
    assert os.path.exists(storage.safe_request_path(root, "complete", RID_B))
    assert locking.read_lock(root, RID_B) is None
    # ...while A's live lock is BYTE-FOR-BYTE intact
    with open(lock_a_path, "rb") as fh:
        assert fh.read() == lock_a_before, \
            "request A's live claim lock was disturbed by B's submission"
    # and B's submission swept none of A's other artifacts either
    assert os.path.exists(storage.safe_request_path(root, "claimed", RID_A))
    assert _healthy(root)

    # cross-request recovery still exists — but ONLY behind the explicit,
    # independently invoked recovery entry point
    healed = codex_watch.finalize_incomplete(root, cfg)
    assert RID_A in healed
    assert locking.read_lock(root, RID_A) is None
    assert os.path.exists(storage.safe_request_path(root, "complete", RID_A))
    assert _healthy(root)


def test_claim_event_pins_a_commitment_not_the_secret_token(env):
    """The chain must AUTHENTICATE the claim without REVEALING the secret
    owner token — a chain-visible token would let any chain reader act as
    the claiming session (releasing its lock, or forging the session
    binding the attribution fix relies on)."""
    root, repo, head, cfg = env
    ctx = drive_to_claimed(root, cfg, repo, head, request_id=RID)
    claimed = [e for e in events.read_chain(root)
               if e["event_type"] == "AUDIT_CLAIMED"
               and e["request_id"] == RID][-1]
    holder = claimed["payload"]["lock_holder"]
    token = ctx["lock"].owner_token
    assert "owner_token" not in holder
    assert holder["owner_token_sha256"] == \
        codex_watch.claim_token_commitment(token)
    assert token not in json.dumps(claimed)  # secret never on the chain
    # the commitment still proves ownership of the on-disk lock
    assert codex_watch.proven_owner_token(root, RID) == token
    locking.release(ctx["lock"])


# ------------------------------------------------------- the normal path

def test_submitting_session_releases_its_own_lock(env):
    """End to end: the claimant's own lock is proven and released."""
    root, repo, head, cfg = env
    ctx = drive_to_claimed(root, cfg, repo, head, request_id=RID)
    assert locking.read_lock(root, RID)["owner_token"] == \
        ctx["lock"].owner_token
    codex_watch.submit_verdict(root, cfg, _signed(head))
    assert locking.read_lock(root, RID) is None
    assert os.path.exists(storage.verdict_path(root, RID))
    assert _healthy(root)


def test_proven_owner_token_comes_from_the_claim_event(env):
    root, repo, head, cfg = env
    ctx = drive_to_claimed(root, cfg, repo, head, request_id=RID)
    assert codex_watch.proven_owner_token(root, RID) == \
        ctx["lock"].owner_token
    # a lock on disk that the chain does not vouch for proves nothing
    other_worker = _replace_lock_with_other_worker(root, RID)
    assert other_worker.owner_token != ctx["lock"].owner_token
    assert codex_watch.proven_owner_token(root, RID) is None


# ------------------------------------------- the cross-worker release case

def test_submit_cannot_unlink_a_foreign_live_claim_lock(env):
    """Worker A holds a live claim lock on R; a second actor runs the
    submit release path for R without A's token. A's lock SURVIVES."""
    root, repo, head, cfg = env
    drive_to_claimed(root, cfg, repo, head, request_id=RID)
    worker_a = _replace_lock_with_other_worker(root, RID)

    codex_watch.submit_verdict(root, cfg, _signed(head))

    holder = locking.read_lock(root, RID)
    assert holder is not None, "worker A's live claim lock was unlinked"
    assert holder["owner_token"] == worker_a.owner_token
    # the verdict itself is still authoritative and the artifacts finished
    assert os.path.exists(storage.verdict_path(root, RID))
    assert _healthy(root)
    locking.release(worker_a)


def test_unprovable_release_is_recorded_and_left_to_lease_expiry(env):
    """The refusal is diagnosable (WATCHER_ERROR, no new event type) and
    the surviving lock stays eligible for the lease-expiry recovery path."""
    root, repo, head, cfg = env
    drive_to_claimed(root, cfg, repo, head, request_id=RID)
    worker_a = _replace_lock_with_other_worker(root, RID)
    codex_watch.submit_verdict(root, cfg, _signed(head))

    notes = [e for e in events.read_chain(root)
             if e["event_type"] == "WATCHER_ERROR"
             and e["request_id"] == RID
             and e["payload"].get("phase") == "claim_lock_release"]
    assert len(notes) == 1 and notes[0]["payload"]["reason"]
    assert notes[0]["sender"] == "codex"

    # still a normal, lease-bearing lock -> the sanctioned recovery path
    holder = locking.read_lock(root, RID)
    assert locking.lease_is_expired(holder) is False
    path = storage.lock_path(root, RID)
    holder["lease_expires_utc"] = "2000-01-01T00:00:00.000Z"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(holder, fh)
    assert locking.lease_is_expired(locking.read_lock(root, RID)) is True
    assert _healthy(root)
    locking.release(worker_a)


# ------------------------------------------------------ finalize_incomplete

def test_finalize_incomplete_releases_its_own_lock(env):
    """The healing path still clears a lock it can prove is the claim
    lock recorded in the chain."""
    root, repo, head, cfg = env
    ctx = drive_to_claimed(root, cfg, repo, head, request_id=RID)
    append(root, cfg, "AUDIT_GO", "codex", RID, repo, head)
    assert locking.read_lock(root, RID)["owner_token"] == \
        ctx["lock"].owner_token
    healed = codex_watch.finalize_incomplete(root, cfg)
    assert RID in healed
    assert locking.read_lock(root, RID) is None
    assert _healthy(root)


def test_finalize_incomplete_cannot_unlink_a_foreign_claim_lock(env):
    """Same rule for the recovery path: no token, no unlink."""
    root, repo, head, cfg = env
    drive_to_claimed(root, cfg, repo, head, request_id=RID)
    append(root, cfg, "AUDIT_GO", "codex", RID, repo, head)
    worker_a = _replace_lock_with_other_worker(root, RID)
    before = len(events.read_chain(root))

    codex_watch.finalize_incomplete(root, cfg)

    holder = locking.read_lock(root, RID)
    assert holder is not None, "worker A's claim lock was unlinked"
    assert holder["owner_token"] == worker_a.owner_token
    # finalize_incomplete appends NO events, by contract
    assert len(events.read_chain(root)) == before
    assert _healthy(root)
    locking.release(worker_a)


def test_finalize_incomplete_is_idempotent_over_a_foreign_lock(env):
    """Repeated recovery never escalates into a blind unlink."""
    root, repo, head, cfg = env
    drive_to_claimed(root, cfg, repo, head, request_id=RID)
    append(root, cfg, "AUDIT_GO", "codex", RID, repo, head)
    worker_a = _replace_lock_with_other_worker(root, RID)
    for _ in range(3):
        codex_watch.finalize_incomplete(root, cfg)
    assert locking.read_lock(root, RID)["owner_token"] == \
        worker_a.owner_token
    assert _healthy(root)
    locking.release(worker_a)


def test_release_claim_lock_reports_its_decision(env):
    root, repo, head, cfg = env
    drive_to_claimed(root, cfg, repo, head, request_id=RID)
    released, why = codex_watch.release_claim_lock(root, RID)
    assert released is True and "proven owner token" in why
    assert locking.read_lock(root, RID) is None
    # nothing to release is a no-op success, not a failure
    released, _why = codex_watch.release_claim_lock(root, RID)
    assert released is True

    worker_a = locking.acquire(root, RID, "codex", RID, kind="claim")
    released, why = codex_watch.release_claim_lock(root, RID)
    assert released is False and why
    assert locking.read_lock(root, RID)["owner_token"] == \
        worker_a.owner_token
    assert _healthy(root)
    locking.release(worker_a)
