"""Round 4 manifest-lifecycle ownership regressions.

These tests use independently started processes but replace the under-lock
sweep body with a bounded fixture.  That isolates the ownership boundary: a
non-holder must not enter setup, call execution, or mutate either terminal
ledger.
"""
import multiprocessing as mp
import os
import queue

import pytest

import coliseum.textlab.sweep as sweep_mod
from coliseum.textlab.sweep import SweepAborted


pytestmark = pytest.mark.skipif(
    os.name != "posix" or "spawn" not in mp.get_all_start_methods(),
    reason="POSIX process-lock regressions require spawned processes")


def _bounded_body(spec, **_kwargs):
    spec["_entered"].put(os.getpid())
    assert spec["_release"].wait(15)
    return spec["_return"]


def _call_sweep(spec, result_queue):
    # Install the bounded body inside each independently started interpreter;
    # no inherited monkeypatch or parent Python state is needed.
    sweep_mod._run_sweep_locked = _bounded_body
    try:
        result = sweep_mod.run_sweep(spec)
    except BaseException as exc:  # return the exact child outcome to the parent
        result_queue.put(("error", type(exc).__name__, str(exc)))
    else:
        result_queue.put(("ok", result))


def _hold_lock(manifest, ready, release):
    with sweep_mod._manifest_advisory_lock(manifest):
        ready.set()
        release.wait(15)


def _join(process):
    process.join(15)
    assert not process.is_alive(), f"child {process.pid} did not finish"
    assert process.exitcode == 0


def test_two_sweep_processes_same_manifest_refuse_nonholder_before_body(
        tmp_path):
    ctx = mp.get_context("spawn")
    manifest = str(tmp_path / "shared" / "manifest.jsonl")
    entered = ctx.Queue()
    release = ctx.Event()
    spec = {"manifest": manifest, "_entered": entered,
            "_release": release, "_return": "holder-complete"}
    q1, q2 = ctx.Queue(), ctx.Queue()
    p1 = ctx.Process(target=_call_sweep, args=(spec, q1))
    p1.start()
    holder_pid = entered.get(timeout=10)
    assert holder_pid == p1.pid

    p2 = ctx.Process(target=_call_sweep, args=(spec, q2))
    p2.start()
    _join(p2)
    status, kind, detail = q2.get(timeout=2)
    assert status == "error" and kind == "SweepAborted"
    assert "already owned by another sweep" in detail
    with pytest.raises(queue.Empty):
        entered.get(timeout=0.2)
    assert not os.path.exists(manifest)
    assert not os.path.exists(manifest + ".tombstones.jsonl")

    _, lock_path = sweep_mod._manifest_lock_identity(manifest)
    assert os.path.exists(lock_path), "persistent lock identity was removed"
    release.set()
    _join(p1)
    assert q1.get(timeout=2) == ("ok", "holder-complete")
    assert os.path.exists(lock_path)


def test_distinct_manifests_have_independent_process_locks(tmp_path):
    ctx = mp.get_context("spawn")
    manifests = [str(tmp_path / name / "manifest.jsonl")
                 for name in ("left", "right")]
    entered = ctx.Queue()
    release = ctx.Event()

    queues = [ctx.Queue(), ctx.Queue()]
    specs = [{"manifest": manifest, "_entered": entered,
              "_release": release, "_return": manifest}
             for manifest in manifests]
    processes = [ctx.Process(target=_call_sweep, args=(spec, queue))
                 for spec, queue in zip(specs, queues)]
    for process in processes:
        process.start()
    entered_pids = {entered.get(timeout=10), entered.get(timeout=10)}
    assert entered_pids == {process.pid for process in processes}
    release.set()
    for process in processes:
        _join(process)
    assert {queue.get(timeout=2) for queue in queues} == {
        ("ok", manifests[0]), ("ok", manifests[1])}


def test_symlink_alias_resolves_to_the_same_manifest_lock(tmp_path,
                                                           monkeypatch):
    ctx = mp.get_context("spawn")
    target = tmp_path / "target" / "manifest.jsonl"
    target.parent.mkdir()
    alias = tmp_path / "alias.jsonl"
    alias.symlink_to(target)
    target_identity, target_lock = sweep_mod._manifest_lock_identity(str(target))
    alias_identity, alias_lock = sweep_mod._manifest_lock_identity(str(alias))
    assert (alias_identity, alias_lock) == (target_identity, target_lock)

    ready, release = ctx.Event(), ctx.Event()
    holder = ctx.Process(target=_hold_lock,
                         args=(str(target), ready, release))
    holder.start()
    assert ready.wait(10)
    entered = []
    monkeypatch.setattr(
        sweep_mod, "_run_sweep_locked",
        lambda *_args, **_kwargs: entered.append(True))
    try:
        with pytest.raises(SweepAborted, match="already owned"):
            sweep_mod.run_sweep({"manifest": str(alias)})
        assert entered == []
    finally:
        release.set()
        _join(holder)
    assert os.path.exists(target_lock)


def test_unavailable_posix_locking_refuses_before_sweep_body(tmp_path,
                                                             monkeypatch):
    entered = []

    def _unavailable():
        raise SweepAborted("POSIX advisory locking unavailable")

    monkeypatch.setattr(sweep_mod, "_posix_lock_module", _unavailable)
    monkeypatch.setattr(
        sweep_mod, "_run_sweep_locked",
        lambda *_args, **_kwargs: entered.append(True))
    manifest = str(tmp_path / "manifest.jsonl")
    with pytest.raises(SweepAborted, match="locking unavailable"):
        sweep_mod.run_sweep({"manifest": manifest})
    assert entered == []
    assert not os.path.exists(manifest)


def test_holder_exception_releases_only_kernel_lock_and_keeps_identity_file(
        tmp_path, monkeypatch):
    manifest = str(tmp_path / "manifest.jsonl")

    def _raise(*_args, **_kwargs):
        raise RuntimeError("bounded fixture failure")

    monkeypatch.setattr(sweep_mod, "_run_sweep_locked", _raise)
    with pytest.raises(RuntimeError, match="bounded fixture failure"):
        sweep_mod.run_sweep({"manifest": manifest})
    _, lock_path = sweep_mod._manifest_lock_identity(manifest)
    first = os.stat(lock_path)

    monkeypatch.setattr(sweep_mod, "_run_sweep_locked",
                        lambda *_args, **_kwargs: "resumed")
    assert sweep_mod.run_sweep({"manifest": manifest}) == "resumed"
    second = os.stat(lock_path)
    assert second.st_ino == first.st_ino
    assert os.path.exists(lock_path), "lock identity file was auto-removed"
