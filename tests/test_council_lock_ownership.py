"""Claim-lock release must PROVE ownership (worker-pool blocker).

`codex_watch.submit_verdict` and `codex_watch.finalize_incomplete` used to
release the claim lock with a tokenless `locking.Lock`, which
`locking.release` BLIND-UNLINKS. With more than one concurrent worker that
lets whichever session finishes first delete another live worker's claim
lock — the lock is the single claim authority, so that is a cross-worker
primitive. Both call sites now recover the owner token from the
codex-signed AUDIT_CLAIMED event (`payload.lock_holder.owner_token`) and
release compare-and-delete; when ownership cannot be proven they touch
nothing and leave the lock to the lease-expiry / logged stale-lock paths.
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
