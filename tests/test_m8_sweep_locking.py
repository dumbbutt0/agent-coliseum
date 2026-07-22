"""Round 4 manifest-lifecycle ownership regressions.

These tests use independently started processes but replace the under-lock
sweep body with a bounded fixture.  That isolates the ownership boundary: a
non-holder must not enter setup, call execution, or mutate either terminal
ledger.
"""
import multiprocessing as mp
import json
import os
import queue
import tempfile
from argparse import Namespace

import pytest

import coliseum.textlab.sweep as sweep_mod
from coliseum.textlab import cli as cli_mod
from coliseum.textlab import result_package as package_mod
from coliseum.textlab.schema import SchemaError
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
    if spec.get("_temp_root"):
        temp_root = spec["_temp_root"]
        for name in ("TMPDIR", "TMP", "TEMP"):
            os.environ[name] = temp_root
        tempfile.tempdir = temp_root
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


def test_distinct_process_temp_roots_cannot_split_one_manifest_lock(tmp_path):
    """B-010 reproduction: process-local temp roots must not select inodes."""
    ctx = mp.get_context("spawn")
    manifest = str(tmp_path / "shared-across-env" / "manifest.jsonl")
    temp_roots = [str(tmp_path / name) for name in ("tmp-a", "tmp-b")]
    for path in temp_roots:
        os.makedirs(path)
    entered = ctx.Queue()
    release = ctx.Event()
    queues = [ctx.Queue(), ctx.Queue()]
    specs = [
        {"manifest": manifest, "_entered": entered, "_release": release,
         "_return": "holder-complete", "_temp_root": temp_root}
        for temp_root in temp_roots]

    holder = ctx.Process(target=_call_sweep, args=(specs[0], queues[0]))
    holder.start()
    assert entered.get(timeout=10) == holder.pid

    contender = ctx.Process(target=_call_sweep, args=(specs[1], queues[1]))
    contender.start()
    _join(contender)
    status, kind, detail = queues[1].get(timeout=2)
    assert status == "error" and kind == "SweepAborted"
    assert "already owned by another sweep" in detail
    with pytest.raises(queue.Empty):
        entered.get(timeout=0.2)
    assert not os.path.exists(manifest)
    assert not os.path.exists(manifest + ".tombstones.jsonl")

    canonical, lock_path = sweep_mod._manifest_lock_identity(manifest)
    assert canonical == os.path.realpath(manifest)
    assert os.path.dirname(lock_path) == os.path.join(
        os.path.realpath("/tmp"), "agent-coliseum-manifest-locks-v1")
    assert all(not lock_path.startswith(root + os.sep) for root in temp_roots)

    release.set()
    _join(holder)
    assert queues[0].get(timeout=2) == ("ok", "holder-complete")
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


def test_locked_body_consumes_the_captured_canonical_manifest(tmp_path,
                                                               monkeypatch):
    """A mutable/non-stable input cannot switch ledger targets after locking."""
    first = str(tmp_path / "first" / "manifest.jsonl")
    second = str(tmp_path / "second" / "manifest.jsonl")

    class FlippingSpec(dict):
        reads = 0

        def __getitem__(self, key):
            if key == "manifest":
                self.reads += 1
                return first if self.reads == 1 else second
            return super().__getitem__(key)

    original = FlippingSpec(manifest=second)
    observed = []

    def _capture(bound_spec, **_kwargs):
        observed.append((bound_spec is original, bound_spec["manifest"]))
        return bound_spec["manifest"]

    monkeypatch.setattr(sweep_mod, "_run_sweep_locked", _capture)
    assert sweep_mod.run_sweep(original) == os.path.realpath(first)
    assert observed == [(False, os.path.realpath(first))]
    assert original["manifest"] == second

    _, first_lock = sweep_mod._manifest_lock_identity(first)
    _, second_lock = sweep_mod._manifest_lock_identity(second)
    assert os.path.exists(first_lock)
    assert not os.path.exists(second_lock)


def test_derived_consumers_refuse_while_manifest_is_owned(
        tmp_path, monkeypatch):
    """Replay, analysis, package build, and verification share ownership."""
    ctx = mp.get_context("spawn")
    manifest = str(tmp_path / "pack" / "manifest.jsonl")
    ready, release = ctx.Event(), ctx.Event()
    holder = ctx.Process(target=_hold_lock, args=(manifest, ready, release))
    holder.start()
    assert ready.wait(10)
    entered = []
    monkeypatch.setattr(
        sweep_mod, "_verify_pack_replay_locked",
        lambda *_a, **_k: entered.append("replay"))
    monkeypatch.setattr(
        cli_mod, "_cmd_order_report_locked",
        lambda *_a, **_k: entered.append("report"))
    monkeypatch.setattr(
        package_mod, "_build_result_package_locked",
        lambda *_a, **_k: entered.append("package"))
    monkeypatch.setattr(
        package_mod, "_verify_result_package_locked",
        lambda *_a, **_k: entered.append("verify"))
    package_path = str(tmp_path / "result_package.json")
    with open(package_path, "w", encoding="utf-8") as fh:
        json.dump({"manifest": {"path": manifest}}, fh)
    try:
        with pytest.raises(SweepAborted, match="already owned"):
            sweep_mod.verify_pack_replay(
                manifest, str(tmp_path), "configs/scenarios",
                planned_design={"models": ["m"], "scenarios": ["s"],
                                "scenario_seeds": [1],
                                "sampler_seeds": [None]})
        with pytest.raises(SystemExit, match="terminal lock"):
            cli_mod.cmd_order_report(Namespace(manifest=manifest))
        with pytest.raises(SchemaError, match="terminal lock"):
            package_mod.build_result_package(
                "e", manifest, str(tmp_path), "registry", "report", {})
        with pytest.raises(SchemaError, match="verification lock"):
            package_mod.verify_result_package(package_path)
        assert entered == []
    finally:
        release.set()
        _join(holder)
