"""H5: lease locks (owner token, compare-and-delete, renewal, expiry) and
crash-safe transactions (STOP-during-claim compensation, idempotent
recovery)."""
import os
import threading

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


def test_expired_lease_cannot_be_renewed(env):
    """Once recovery may act on expiry, the old owner cannot revive the
    same token and race the rollback decision."""
    root, *_ = env
    lock = locking.acquire(root, "lock-expired", "codex", RID,
                           lease_seconds=-1)
    with pytest.raises(LockHeld, match="expired or invalid"):
        locking.renew(lock, lease_seconds=99999)
    assert locking.lease_is_expired(
        locking.read_lock(root, "lock-expired")) is True
    locking.release(lock)


def test_renew_fails_if_lease_expires_after_initial_read(env, monkeypatch):
    """The post-move check closes the check/use boundary: a lease that was
    live at the first read cannot be revived after it expires mid-renewal."""
    root, *_ = env
    lock = locking.acquire(root, "lock-boundary", "codex", RID,
                           lease_seconds=60)
    real_check = locking.lease_is_expired
    checks = iter((False, True))
    monkeypatch.setattr(locking, "lease_is_expired",
                        lambda holder: next(checks))
    with pytest.raises(LockHeld, match="expired during renewal"):
        locking.renew(lock, lease_seconds=99999)
    monkeypatch.setattr(locking, "lease_is_expired", real_check)
    holder = locking.read_lock(root, "lock-boundary")
    assert holder is not None
    assert holder["owner_token"] == lock.owner_token
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
    lock = locking.acquire(root, RID, "codex", RID, kind="claim",
                           lease_seconds=-1)
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


def test_recovery_expiry_cannot_be_reversed_by_owner_renewal(
        env, monkeypatch):
    """Reproduce the audit boundary: once recovery observes an expired
    claim, the old owner cannot revive that token before rollback."""
    root, repo, head, cfg = env
    _publish(root, cfg, repo, head)
    lock = locking.acquire(root, RID, "codex", RID, kind="claim",
                           lease_seconds=-1)
    os.rename(storage.safe_request_path(root, "ready", RID),
              storage.safe_request_path(root, "claimed", RID))
    t = txn.Txn.begin(root, "claim", RID, ["locked", "moved", "event"],
                      {"owner_token": lock.owner_token,
                       "prior_claimed_count": 0})
    t.mark("locked")
    t.mark("moved")

    real_check = locking.lease_is_expired
    attempted = []

    def observe_expiry_then_attempt_renew(holder):
        if not attempted:
            attempted.append(True)
            with pytest.raises(LockHeld, match="expired or invalid"):
                locking.renew(lock, lease_seconds=99999)
        return real_check(holder)

    monkeypatch.setattr(locking, "lease_is_expired",
                        observe_expiry_then_attempt_renew)
    healed = txn.recover(root, make_cfg(repo, root, role="codex"))

    assert attempted == [True]
    assert (t.txn_id, "back") in healed
    assert os.path.exists(storage.safe_request_path(root, "ready", RID))
    assert not os.path.exists(storage.safe_request_path(
        root, "claimed", RID))
    assert locking.read_lock(root, RID) is None


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


# --------------------------- H5 cycle-2 audit blockers (Codex, BLOCKED) ----

def test_recover_is_cycle_aware(env):
    """Blocker 1: a PRIOR cycle's AUDIT_CLAIMED must not be mistaken for the
    current cycle's terminal event. An interrupted re-audit (a second claim
    with no current-cycle AUDIT_CLAIMED) rolls BACK even though an older
    AUDIT_CLAIMED exists for the request."""
    root, repo, head, cfg = env
    _publish(root, cfg, repo, head)
    codex_cfg = make_cfg(repo, root, role="codex")
    # cycle 1: a full claim -> one AUDIT_CLAIMED in the chain
    _event, lock = codex_watch.claim(root, codex_cfg, RID)
    locking.release(lock)
    # re-audit: the request goes back to ready/ (as a re-publish would)
    os.rename(storage.safe_request_path(root, "claimed", RID),
              storage.safe_request_path(root, "ready", RID))
    # cycle 2: an INTERRUPTED claim — lock + move + journal, but no event.
    # prior_claimed_count records the one existing AUDIT_CLAIMED.
    lock2 = locking.acquire(root, RID, "codex", RID, kind="claim",
                            lease_seconds=-1)
    os.rename(storage.safe_request_path(root, "ready", RID),
              storage.safe_request_path(root, "claimed", RID))
    t = txn.Txn.begin(root, "claim", RID, ["locked", "moved", "event"],
                      {"owner_token": lock2.owner_token,
                       "prior_claimed_count": 1})
    t.mark("locked")
    t.mark("moved")
    healed = txn.recover(root, codex_cfg)
    assert (t.txn_id, "back") in healed          # rolled BACK, not forward
    assert os.path.exists(storage.safe_request_path(root, "ready", RID))
    assert not os.path.exists(storage.safe_request_path(root, "claimed", RID))
    assert locking.read_lock(root, RID) is None
    assert txn.recover(root, codex_cfg) == []    # idempotent


def test_renew_cannot_overwrite_a_replacement_lock(env):
    """Blocker 2: renew is an ownership-preserving compare-and-swap. If the
    holder is released and re-acquired between a stale owner's read and
    write, the stale renew fails closed (LockHeld) and the replacement's
    token + lease survive intact."""
    root, *_ = env
    real = locking.acquire(root, "lock-r", "codex", RID, lease_seconds=10)
    locking.release(real)                          # owner releases
    replacement = locking.acquire(root, "lock-r", "codex", RID,
                                  lease_seconds=10)  # new owner, new token
    assert replacement.owner_token != real.owner_token
    before = locking.read_lock(root, "lock-r")["lease_expires_utc"]
    with pytest.raises(LockHeld):
        locking.renew(real, lease_seconds=99999)   # stale renew refused
    holder = locking.read_lock(root, "lock-r")
    assert holder["owner_token"] == replacement.owner_token
    assert holder["lease_expires_utc"] == before   # lease not corrupted
    locking.release(replacement)


def test_publish_rolls_back_ready_file_on_append_crash(env, monkeypatch):
    """H5 crash-safety (draft->ready->event): if the AUDIT_REQUESTED append
    fails with a low-level OSError (a crash, not just a CouncilError
    refusal), publish_request must not leave an unpinned request orphaned in
    ready/ — the rollback is all-or-nothing, keyed on whether the authority
    event actually landed."""
    root, repo, head, cfg = env
    append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    append(root, cfg, "BUILD_READY", "claude", RID, repo, head)
    real_append = publish.events.append_event

    def boom(root_, cfg_, etype, *a, **k):
        if etype == "AUDIT_REQUESTED":
            raise OSError("simulated crash during append")
        return real_append(root_, cfg_, etype, *a, **k)

    monkeypatch.setattr(publish.events, "append_event", boom)
    with pytest.raises(OSError):
        publish.publish_request(root, cfg, make_request(repo, head, RID))
    monkeypatch.undo()
    assert not os.path.exists(storage.safe_request_path(root, "ready", RID))
    from tools.council import state_machine
    proj = state_machine.project(events.read_chain(root))
    assert RID not in proj or proj[RID]["state"] != "requested"


def test_compensate_is_phase_and_ownership_aware(env):
    """Blocker (cycle 2): a claim that began its journal but never acquired
    the lock or moved the file must NOT, on compensation, disturb a
    concurrent claimant that legitimately holds the lock and moved the
    request. Recovery only undoes the move its OWN journal recorded, and
    releases only a lock its OWN token owns."""
    root, repo, head, cfg = env
    _publish(root, cfg, repo, head)
    # claimant B is mid-claim: holds the lock, moved ready/ -> claimed/, but
    # has not yet appended AUDIT_CLAIMED
    lockB = locking.acquire(root, RID, "codex", RID, kind="claim")
    os.rename(storage.safe_request_path(root, "ready", RID),
              storage.safe_request_path(root, "claimed", RID))
    # claimant A raced: it began a journal (prior_claimed_count 0) but its
    # acquire failed, so it never reached "locked"/"moved"
    tA = txn.Txn.begin(root, "claim", RID, ["locked", "moved", "event"],
                       {"owner_token": "a" * 32, "prior_claimed_count": 0})
    outcome = txn.compensate(root, make_cfg(repo, root, role="codex"), tA)
    assert outcome == "blocked"  # foreign live owner: fail closed, no mutation
    # B is completely untouched: its file stays claimed, its lock survives
    assert os.path.exists(storage.safe_request_path(root, "claimed", RID))
    assert not os.path.exists(storage.safe_request_path(root, "ready", RID))
    holder = locking.read_lock(root, RID)
    assert holder is not None and holder["owner_token"] == lockB.owner_token
    locking.release(lockB)


def test_recover_never_rolls_back_a_live_claim_transaction(env, monkeypatch):
    """Events 001513-001516 regression: a concurrent watcher may invoke
    global recovery while the first claimant has moved the request but has
    not appended AUDIT_CLAIMED yet.  The matching live lease makes that
    journal untouchable; the duplicate claim is refused and the first claim
    commits with one file, one lock, one event, and no journal residue."""
    root, repo, head, cfg = env
    _publish(root, cfg, repo, head)
    codex_cfg = make_cfg(repo, root, role="codex")
    entered = threading.Event()
    proceed = threading.Event()
    real_append = codex_watch.events.append_event

    def pause_before_claim_event(root_, cfg_, event_type, *args, **kwargs):
        if event_type == "AUDIT_CLAIMED" and \
                threading.current_thread().name == "first-claimant":
            entered.set()
            assert proceed.wait(5), "test did not release first claimant"
        return real_append(root_, cfg_, event_type, *args, **kwargs)

    monkeypatch.setattr(codex_watch.events, "append_event",
                        pause_before_claim_event)
    result = {}

    def first_claim():
        try:
            result["value"] = codex_watch.claim(root, codex_cfg, RID)
        except BaseException as exc:  # surfaced in the main test thread
            result["error"] = exc

    worker = threading.Thread(target=first_claim, name="first-claimant")
    worker.start()
    assert entered.wait(5)
    assert os.path.exists(storage.safe_request_path(root, "claimed", RID))
    holder = locking.read_lock(root, RID)
    assert holder is not None

    # Recovery observes the in-flight owner and makes no mutation.  A second
    # claim invocation also refuses instead of restoring ready/.
    assert txn.recover(root, codex_cfg) == []
    assert os.listdir(os.path.join(root, "txn"))
    with pytest.raises(CouncilError):
        codex_watch.claim(root, codex_cfg, RID)
    assert os.path.exists(storage.safe_request_path(root, "claimed", RID))
    assert not os.path.exists(storage.safe_request_path(root, "ready", RID))
    assert locking.read_lock(root, RID)["owner_token"] == \
        holder["owner_token"]

    proceed.set()
    worker.join(5)
    assert not worker.is_alive()
    assert "error" not in result
    assert sum(e["event_type"] == "AUDIT_CLAIMED" and
               e["request_id"] == RID for e in events.read_chain(root)) == 1
    assert os.path.exists(storage.safe_request_path(root, "claimed", RID))
    assert not os.path.exists(storage.safe_request_path(root, "ready", RID))
    assert locking.read_lock(root, RID) is not None
    assert os.listdir(os.path.join(root, "txn")) == []


def test_recover_rolls_forward_event_committed_claim_artifacts(env):
    """If AUDIT_CLAIMED lands before a crash, the journal repairs artifacts
    toward claimed; it never silently restores the request to ready."""
    root, repo, head, cfg = env
    _publish(root, cfg, repo, head)
    codex_cfg = make_cfg(repo, root, role="codex")
    token = "a" * 32
    lock = locking.acquire(root, RID, "codex", RID, kind="claim",
                           owner_token=token)
    t = txn.Txn.begin(root, "claim", RID, ["locked", "moved", "event"],
                      {"owner_token": token, "prior_claimed_count": 0})
    t.mark("locked")
    t.mark("moved")
    os.rename(storage.safe_request_path(root, "ready", RID),
              storage.safe_request_path(root, "claimed", RID))
    request = make_request(repo, head, RID)
    events.append_event(
        root, codex_cfg, "AUDIT_CLAIMED", "codex", RID, repo, head,
        {"claimed_by": "codex", "lock_file": f"locks/{RID}.lock",
         "lock_holder": locking.read_lock(root, RID)})
    # Reproduce the bad artifact tail while retaining the transaction journal.
    os.rename(storage.safe_request_path(root, "claimed", RID),
              storage.safe_request_path(root, "ready", RID))
    locking.release(lock)

    assert (t.txn_id, "forward") in txn.recover(root, codex_cfg)
    assert os.path.exists(storage.safe_request_path(root, "claimed", RID))
    assert not os.path.exists(storage.safe_request_path(root, "ready", RID))
    assert locking.read_lock(root, RID)["owner_token"] == token
    assert txn.recover(root, codex_cfg) == []


def test_launcher_recovers_orphan_claim_before_work(env, monkeypatch):
    """Blocker 3: codex_launcher._run calls txn.recover at the loop top, so
    an orphaned interrupted claim is healed BEFORE work is derived — not
    left waiting for a later codex_watch invocation."""
    from tools.autonomy import codex_launcher
    root, repo, head, cfg = env
    monkeypatch.setenv("COUNCIL_ROOT", root)
    monkeypatch.setenv("COUNCIL_REPO_ROOTS", repo)
    _publish(root, cfg, repo, head)
    # stage an orphan interrupted claim: lock + move + journal, no event
    lock = locking.acquire(root, RID, "codex", RID, kind="claim",
                           lease_seconds=-1)
    os.rename(storage.safe_request_path(root, "ready", RID),
              storage.safe_request_path(root, "claimed", RID))
    t = txn.Txn.begin(root, "claim", RID, ["locked", "moved", "event"],
                      {"owner_token": lock.owner_token,
                       "prior_claimed_count": 0})
    t.mark("locked")
    t.mark("moved")
    # never launch a real session: the loop should still recover first
    monkeypatch.setattr(codex_launcher, "process_one",
                        lambda *a, **k: "waiting")
    assert codex_launcher.main(["--once"]) == 0
    # recovered: request back in ready/, lock released, journal gone
    assert os.path.exists(storage.safe_request_path(root, "ready", RID))
    assert not os.path.exists(storage.safe_request_path(root, "claimed", RID))
    assert locking.read_lock(root, RID) is None
    assert os.listdir(os.path.join(root, "txn")) == []
