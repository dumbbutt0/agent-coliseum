"""H5: lease locks (owner token, compare-and-delete, renewal, expiry) and
crash-safe transactions (STOP-during-claim compensation, idempotent
recovery)."""
import os

import pytest

from tests.council_util import (append, make_cfg, make_repo, make_request,
                                make_root)
from tools.council import codex_watch, events, locking, publish, storage, txn
from tools.council.schemas import CouncilError, LockHeld

RID = "h5-req-001"


@pytest.fixture()
def env(tmp_path):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    return root, repo, head, make_cfg(repo, root)


# --------------------------------------------------- lease locks (item 7)

def test_lock_has_token_and_lease(env):
    root, *_ = env
    lock = locking.acquire(root, "lock-n1", "codex", RID)
    holder = locking.read_lock(root, "lock-n1")
    assert holder["owner_token"] == lock.owner_token
    assert holder["schema_version"] == "lock.v1"
    assert holder["lease_expires_utc"].endswith("Z")
    locking.release(lock)
    assert locking.read_lock(root, "lock-n1") is None


def test_release_is_compare_and_delete(env):
    """A Lock with the WRONG token cannot remove a live lock; PID reuse
    cannot steal it (authority is the random token)."""
    root, *_ = env
    real = locking.acquire(root, "lock-n1", "codex", RID)
    imposter = locking.Lock(path=real.path, name="lock-n1", role="codex",
                            root=root, owner_token="f" * 32)
    locking.release(imposter)                    # wrong token: no-op
    assert locking.read_lock(root, "lock-n1") is not None
    locking.release(real)                         # owner: removed
    assert locking.read_lock(root, "lock-n1") is None


def test_pid_reuse_cannot_steal_lock(env):
    """Rewrite the holder's pid to a live pid — the token still gates
    release, so pid reuse is neutralized."""
    root, *_ = env
    real = locking.acquire(root, "lock-n1", "codex", RID)
    holder = locking.read_lock(root, "lock-n1")
    holder["pid"] = os.getpid()                   # attacker matches a pid
    storage.atomic_write_json(storage.lock_path(root, "lock-n1"), holder)
    # a fresh Lock without the token cannot release via compare-and-delete
    wrong = locking.Lock(path=real.path, name="lock-n1", role="codex",
                         root=root, owner_token="0" * 32)
    locking.release(wrong)
    assert locking.read_lock(root, "lock-n1") is not None
    locking.release(real)


def test_renew_requires_owner(env):
    root, *_ = env
    lock = locking.acquire(root, "lock-n1", "codex", RID, lease_seconds=10)
    before = locking.read_lock(root, "lock-n1")["lease_expires_utc"]
    locking.renew(lock, lease_seconds=99999)
    after = locking.read_lock(root, "lock-n1")["lease_expires_utc"]
    assert after > before
    imposter = locking.Lock(path=lock.path, name="lock-n1", role="codex",
                            root=root, owner_token="9" * 32)
    with pytest.raises(LockHeld):
        locking.renew(imposter)
    locking.release(lock)


def test_second_acquire_refused(env):
    root, *_ = env
    lock = locking.acquire(root, "lock-n1", "codex", RID)
    with pytest.raises(LockHeld):
        locking.acquire(root, "lock-n1", "codex", RID)
    locking.release(lock)


# ------------------------------------- crash-safe claim txn (item 6)

def _publish(root, cfg, repo, head, rid=RID):
    append(root, cfg, "BUILD_STARTED", "claude", rid, repo, head)
    append(root, cfg, "BUILD_READY", "claude", rid, repo, head)
    publish.publish_request(root, cfg, make_request(repo, head, rid))


def test_stop_during_claim_leaves_no_stranded_lock_or_move(env):
    """The plan's named case: a STOP engaged before the AUDIT_CLAIMED
    append must roll back — no stranded lock, request back in ready/, no
    half-move, and no journal residue."""
    root, repo, head, cfg = env
    _publish(root, cfg, repo, head)
    codex_cfg = make_cfg(repo, root, role="codex")
    open(os.path.join(root, "STOP"), "w").close()   # STOP mid-claim
    with pytest.raises(CouncilError):
        codex_watch.claim(root, codex_cfg, RID)
    # rolled back: request in ready/, not claimed/; lock gone; no journal
    assert os.path.exists(storage.safe_request_path(root, "ready", RID))
    assert not os.path.exists(
        storage.safe_request_path(root, "claimed", RID))
    assert locking.read_lock(root, RID) is None
    assert os.listdir(os.path.join(root, "txn")) == []
    # after STOP clears, a normal claim succeeds
    os.unlink(os.path.join(root, "STOP"))
    _event, lock = codex_watch.claim(root, codex_cfg, RID)
    assert events.read_chain(root)[-1]["event_type"] == "AUDIT_CLAIMED"
    locking.release(lock)


def test_recover_rolls_back_orphaned_claim_txn(env):
    """A crash after the move but before AUDIT_CLAIMED leaves a journal;
    recover() rolls the move back and releases the lock (idempotent)."""
    root, repo, head, cfg = env
    _publish(root, cfg, repo, head)
    # simulate the crash: lock + move + journal at 'moved', no event
    lock = locking.acquire(root, RID, "codex", RID, kind="claim")
    os.rename(storage.safe_request_path(root, "ready", RID),
              storage.safe_request_path(root, "claimed", RID))
    t = txn.Txn.begin(root, "claim", RID, ["locked", "moved", "event"],
                      {"owner_token": lock.owner_token})
    t.mark("locked")
    t.mark("moved")
    # recover: no AUDIT_CLAIMED in chain -> roll back
    healed = txn.recover(root, make_cfg(repo, root, role="codex"))
    assert (t.txn_id, "back") in healed
    assert os.path.exists(storage.safe_request_path(root, "ready", RID))
    assert locking.read_lock(root, RID) is None
    # idempotent: a second recover is a no-op
    assert txn.recover(root, make_cfg(repo, root, role="codex")) == []


def test_recover_rolls_forward_committed_claim(env):
    """If AUDIT_CLAIMED DID land before the crash, recovery rolls forward
    (leaves the claimed state) — never undoing a committed event."""
    root, repo, head, cfg = env
    _publish(root, cfg, repo, head)
    codex_cfg = make_cfg(repo, root, role="codex")
    _event, lock = codex_watch.claim(root, codex_cfg, RID)  # fully claimed
    # a leftover journal marked complete-ish (simulate crash after event)
    t = txn.Txn.begin(root, "claim", RID, ["locked", "moved", "event"],
                      {"owner_token": lock.owner_token})
    t.mark("locked")
    t.mark("moved")
    healed = txn.recover(root, codex_cfg)
    assert (t.txn_id, "forward") in healed
    # still claimed; the committed event is untouched
    assert os.path.exists(storage.safe_request_path(root, "claimed", RID))
    from tools.council import state_machine
    assert state_machine.project(
        events.read_chain(root))[RID]["state"] == "claimed"
