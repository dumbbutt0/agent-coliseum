"""H6 fault matrix (directive item 14).

For each RECOVERABLE council operation, we (1) dry-run it to enumerate every
durable-mutation boundary it crosses (os.rename / os.unlink /
storage.append_line / storage.atomic_write_json), then (2) re-run it once per
boundary, crashing at exactly that boundary, run the operation's recovery
path, and assert the operation's INVARIANT holds — plus that recovery is
idempotent (a second recovery is a no-op) and the event chain stays healthy.

The guiding principle is that the event chain is the single source of truth:
after any crash, the request is in exactly the state the chain's terminal
event implies, never a half-state. Two completeness tests at the bottom
assert every boundary op and every operation is genuinely exercised, so the
matrix can never silently shrink.
"""
import os

import pytest

from tests.council_util import (append, make_cfg, make_repo, make_request,
                                make_root, make_verdict)
from tests.fault_util import (OPS, CrashInjected, FaultInjector,
                              count_boundaries, inject)
from tools.council import (codex_watch, events, locking, publish,
                           state_machine, storage, txn)

RID = "h6-req-001"
# a generous per-operation boundary ceiling; tests skip k beyond the real
# count so adding a boundary never silently drops coverage
MAX_BOUNDARY = 16
# ops observed across every scenario's dry run — the completeness floor
_OBSERVED_OPS: set = set()


# --------------------------------------------------------------- scenarios

def _ready_env(tmp_path):
    """A published request sitting in ready/, plus a codex cfg."""
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    append(root, cfg, "BUILD_READY", "claude", RID, repo, head)
    publish.publish_request(root, cfg, make_request(repo, head, RID))
    return root, repo, head, make_cfg(repo, root, role="codex")


def _claimed_env(tmp_path):
    """A request already claimed (ready for a verdict submission)."""
    root, repo, head, codex_cfg = _ready_env(tmp_path)
    codex_watch.claim(root, codex_cfg, RID)
    return root, repo, head, codex_cfg


# Each scenario: label, setup -> (root, codex_cfg, do_thunk), recover, check.
# `check` receives (root, cfg, crashed) and asserts the invariant.

def _claim_scenario(tmp_path):
    root, repo, head, codex_cfg = _ready_env(tmp_path)
    do = lambda: codex_watch.claim(root, codex_cfg, RID)
    return root, codex_cfg, do


def _check_claim(root, cfg, crashed):
    txn.recover(root, cfg)
    again = txn.recover(root, cfg)          # idempotent
    chain = events.read_chain(root)
    claimed_evt = any(e["event_type"] == "AUDIT_CLAIMED"
                      and e["request_id"] == RID for e in chain)
    ready = os.path.exists(storage.safe_request_path(root, "ready", RID))
    claimed = os.path.exists(storage.safe_request_path(root, "claimed", RID))
    lock = locking.read_lock(root, RID) is not None
    txns = _journal_files(root)
    assert ready ^ claimed, "request must be in exactly one of ready/ claimed"
    assert claimed_evt == claimed, "AUDIT_CLAIMED must match the file location"
    assert lock == claimed, "the claim lock survives iff the claim committed"
    assert txns == [], "no journal residue after recovery"
    assert events.verify_chain(root).healthy
    assert again == [], "second recovery must be a no-op"


def _submit_scenario(tmp_path):
    root, repo, head, codex_cfg = _claimed_env(tmp_path)
    verdict = make_verdict(head, RID, verdict="GO")
    do = lambda: codex_watch.submit_verdict(root, codex_cfg, verdict)
    return root, codex_cfg, do


def _check_submit(root, cfg, crashed):
    codex_watch.finalize_incomplete(root, cfg)
    before = events.read_chain(root)
    codex_watch.finalize_incomplete(root, cfg)      # idempotent
    after = events.read_chain(root)
    assert len(before) == len(after), "finalize must never append an event"
    verdict_evt = any(e["event_type"] in codex_watch._TERMINAL_VERDICT_TYPES
                      and e["request_id"] == RID for e in after)
    claimed = os.path.exists(storage.safe_request_path(root, "claimed", RID))
    complete = os.path.exists(storage.safe_request_path(root, "complete", RID))
    verdict_json = os.path.exists(storage.verdict_path(root, RID))
    lock = locking.read_lock(root, RID) is not None
    if verdict_evt:
        # the verdict is authoritative -> artifacts finalized, lock released
        assert complete and not claimed
        assert verdict_json
        assert not lock
    else:
        # no verdict landed -> still claimed, no phantom artifacts
        assert claimed and not complete
        assert not verdict_json
    # a verdict event must never be duplicated by a crash+recover
    n_verdicts = sum(1 for e in after
                     if e["event_type"] in codex_watch._TERMINAL_VERDICT_TYPES
                     and e["request_id"] == RID)
    assert n_verdicts <= 1, "recovery must never duplicate a verdict"
    assert events.verify_chain(root).healthy


def _publish_scenario(tmp_path):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    append(root, cfg, "BUILD_READY", "claude", RID, repo, head)
    req = make_request(repo, head, RID)
    do = lambda: publish.publish_request(root, cfg, req)
    return root, cfg, do


def _check_publish(root, cfg, crashed):
    """publish is all-or-nothing: the append is the authority and the file
    is rolled back if it does not land, so after any crash EITHER the
    AUDIT_REQUESTED event exists AND the request is in ready/, OR neither —
    never a half-published orphan sitting unpinned in ready/."""
    chain = events.read_chain(root)
    published = any(e["event_type"] == "AUDIT_REQUESTED"
                    and e["request_id"] == RID for e in chain)
    ready = os.path.exists(storage.safe_request_path(root, "ready", RID))
    assert published == ready, \
        "publish must be all-or-nothing (event <=> ready file)"
    assert events.verify_chain(root).healthy


SCENARIOS = {
    "claim": (_claim_scenario, _check_claim),
    "submit_verdict": (_submit_scenario, _check_submit),
    "publish": (_publish_scenario, _check_publish),
}


# ----------------------------------------------------------------- helpers

def _journal_files(root):
    d = os.path.join(root, "txn")
    return sorted(os.listdir(d)) if os.path.isdir(d) else []


def _boundary_count(scenario_setup, tmp_path):
    """Dry-run the operation (pure tracer) and return its boundary trace."""
    root, cfg, do = scenario_setup(tmp_path)
    trace = count_boundaries(do)
    for op, _ in trace:
        _OBSERVED_OPS.add(op)
    return trace


# ------------------------------------------------------------------- tests

@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
@pytest.mark.parametrize("k", range(1, MAX_BOUNDARY + 1))
def test_fault_at_each_boundary_recovers(scenario, k, tmp_path):
    setup, check = SCENARIOS[scenario]
    trace = _boundary_count(setup, tmp_path / "count")
    if k > len(trace):
        pytest.skip(f"{scenario} has only {len(trace)} boundaries")
    root, cfg, do = setup(tmp_path / "run")
    crashed = False
    with inject(FaultInjector().fail_global(k)):
        try:
            do()
        except Exception:
            # a fault at a durable boundary crashes the op; a fault at a
            # SWALLOWED cleanup boundary (e.g. atomic_write_json's tmp
            # unlink, wrapped in try/except) is absorbed and the op still
            # succeeds — both must leave a consistent, recoverable state.
            crashed = True
    check(root, cfg, crashed)


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_clean_run_crosses_boundaries(scenario, tmp_path):
    """Every scenario must actually mutate the filesystem (else the
    per-boundary test would be vacuously skipping everything)."""
    setup, _ = SCENARIOS[scenario]
    trace = _boundary_count(setup, tmp_path)
    assert len(trace) >= 1


@pytest.mark.parametrize("op", OPS)
def test_completeness_every_op_exercised(op, tmp_path):
    """Force the dry runs, then assert every durable-mutation primitive is
    crossed by at least one scenario — the matrix cannot silently stop
    covering a boundary kind."""
    for setup, _ in SCENARIOS.values():
        _boundary_count(setup, tmp_path / f"c-{id(setup)}")
    assert op in _OBSERVED_OPS, f"no scenario exercises {op!r}"


def test_completeness_every_scenario_present():
    """Guard against a scenario being dropped from the table."""
    assert set(SCENARIOS) == {"claim", "submit_verdict", "publish"}


def test_recover_is_idempotent_with_no_journal(tmp_path):
    """recover() on a clean root heals nothing and returns []."""
    root, repo, head, codex_cfg = _ready_env(tmp_path)
    assert txn.recover(root, codex_cfg) == []
    assert codex_watch.finalize_incomplete(root, codex_cfg) == []


def test_injector_fires_precisely(tmp_path):
    """The fault injector must raise at exactly the Nth matching op (and no
    earlier), and record the full boundary trace — otherwise a per-boundary
    test could pass vacuously by never actually interrupting anything."""
    p = str(tmp_path / "f.json")
    with inject(FaultInjector().fail_op("atomic_write_json", 2)) as fi:
        storage.atomic_write_json(p, {"n": 1})            # 1st: proceeds
        assert os.path.exists(p)
        with pytest.raises(CrashInjected):
            storage.atomic_write_json(p, {"n": 2})        # 2nd: fires first
    assert fi.count("atomic_write_json") == 2
    # the injected op never ran, so the on-disk value is still the 1st write
    import json
    assert json.load(open(p))["n"] == 1


def test_acquire_cleans_up_partial_lock_on_write_failure(tmp_path, monkeypatch):
    """H6 cycle-1 finding: locking.acquire must not strand a TOKENLESS lock
    if the body write fails after the O_EXCL create — compare-and-delete
    needs the token, so a half-written lock could never be removed. The
    O_EXCL create guarantees the cleanup only ever unlinks a lock we just
    made, never another holder's."""
    root = make_root(tmp_path)
    real_write = os.write

    def boom(fd, data):
        raise OSError("simulated crash writing the lock body")

    monkeypatch.setattr(os, "write", boom)
    with pytest.raises(OSError):
        locking.acquire(root, "lk-partial", "codex", "lk-partial-rid",
                        kind="claim")
    monkeypatch.setattr(os, "write", real_write)
    assert locking.read_lock(root, "lk-partial") is None   # no stranded lock


def test_acquire_cleans_up_on_short_write(tmp_path, monkeypatch):
    """os.write may return fewer bytes than requested WITHOUT raising. A
    short write that then stalls must not strand a truncated, tokenless lock:
    acquire writes the whole body or unlinks the partial (H6 cycle-3)."""
    root = make_root(tmp_path)
    real_write = os.write
    calls = {"n": 0}

    def short(fd, data):
        calls["n"] += 1
        if calls["n"] == 1:
            return real_write(fd, bytes(data)[:5])   # partial: 5 bytes land
        return 0                                       # then no progress

    monkeypatch.setattr(os, "write", short)
    with pytest.raises(OSError):
        locking.acquire(root, "lk-short", "codex", "lk-short-rid",
                        kind="claim")
    monkeypatch.setattr(os, "write", real_write)
    assert locking.read_lock(root, "lk-short") is None     # truncated -> gone


def test_acquire_fsync_is_best_effort(tmp_path, monkeypatch):
    """Narrowed contract (H6 cycle-2): the body write is what makes a lock
    complete; the fsync is BEST-EFFORT (the council root is drvfs, where
    fsync can legitimately fail). An fsync error after a successful write
    leaves a COMPLETE, token-bearing, releasable lock — it is NOT unlinked,
    because dropping a fully-written lock a caller believes it holds would be
    wrong. Only a WRITE failure (tested above) triggers cleanup."""
    root = make_root(tmp_path)
    real_fsync = os.fsync

    def boom(fd):
        raise OSError("simulated fsync failure")

    monkeypatch.setattr(os, "fsync", boom)
    lock = locking.acquire(root, "lk-fsync", "codex", "lk-fsync-rid",
                           kind="claim")
    monkeypatch.setattr(os, "fsync", real_fsync)
    holder = locking.read_lock(root, "lk-fsync")
    assert holder is not None
    assert holder["owner_token"] == lock.owner_token       # complete + usable
    locking.release(lock)
    assert locking.read_lock(root, "lk-fsync") is None      # and releasable


def test_renew_restores_original_lock_even_if_all_writes_fail(tmp_path,
                                                             monkeypatch):
    """H6 cycle-4/5: the restore is a WRITE-FREE rename of the intact aside
    file, so even if EVERY os.write short-stalls (the renewed-body write AND
    any restore attempt), the original lock is put back at the normal path —
    readable and releasable by release(lock), never stranded in
    .renew.<token>."""
    root = make_root(tmp_path)
    lock = locking.acquire(root, "lk-renew", "codex", "lk-renew-rid",
                           kind="claim", lease_seconds=10)
    real_write = os.write

    def always_stall(fd, data):
        return 0                                       # never makes progress

    monkeypatch.setattr(os, "write", always_stall)
    with pytest.raises(locking.LockHeld):
        locking.renew(lock, lease_seconds=99999)
    monkeypatch.setattr(os, "write", real_write)       # restore for teardown
    holder = locking.read_lock(root, "lk-renew")
    assert holder is not None
    assert holder["owner_token"] == lock.owner_token   # original restored
    assert not os.path.exists(f"{lock.path}.renew.{lock.owner_token}")
    locking.release(lock)                              # still releasable
    assert locking.read_lock(root, "lk-renew") is None


def test_release_clears_aside_after_doubly_failed_renew(tmp_path,
                                                        monkeypatch):
    """H6 (-002 cycle 1): the deepest failure tail — the renewed-body write
    fails AND the write-free restore rename fails, so the intact original
    survives only in .renew.<token>. The lock must STILL be releasable by
    release(lock): the aside name is derived from the owner token the Lock
    carries, so release sweeps it (and only ours) too."""
    root = make_root(tmp_path)
    lock = locking.acquire(root, "lk-dbl", "codex", "lk-dbl-rid",
                           kind="claim", lease_seconds=10)
    aside = f"{lock.path}.renew.{lock.owner_token}"
    real_write, real_rename = os.write, os.rename

    def stall(fd, data):
        return 0                                   # every write fails

    def flaky_rename(src, dst):
        if src == aside and dst == lock.path:
            raise OSError("simulated restore rename failure")
        return real_rename(src, dst)

    monkeypatch.setattr(os, "write", stall)
    monkeypatch.setattr(os, "rename", flaky_rename)
    with pytest.raises(locking.LockHeld):
        locking.renew(lock, lease_seconds=99999)
    monkeypatch.setattr(os, "write", real_write)
    monkeypatch.setattr(os, "rename", real_rename)
    # the strand: nothing at the normal path, the original only in aside
    assert locking.read_lock(root, "lk-dbl") is None
    assert os.path.exists(aside)
    # ...but release(lock) clears it — the lock is never unreleasable
    locking.release(lock)
    assert not os.path.exists(aside)
    assert locking.read_lock(root, "lk-dbl") is None


def test_injector_global_index(tmp_path):
    """fail_global(k) fires at the kth boundary across ALL ops, and the
    trace is a faithful ordered record used to drive the matrix."""
    p = str(tmp_path / "g.json")
    with inject(FaultInjector().fail_global(1)) as fi:
        with pytest.raises(CrashInjected):
            storage.append_line(p, "x")                   # 1st boundary fires
    assert fi.total() == 1 and fi.calls[0][0] == "append_line"
    assert not os.path.exists(p)                          # op never ran
