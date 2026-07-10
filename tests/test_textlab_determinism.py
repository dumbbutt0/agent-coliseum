"""The Rung-0 gate for this harness: same seed + scripted agent -> byte-identical logs."""
import json
import os

from coliseum.textlab.runner import run_scenario

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CK = os.path.join(ROOT, "configs", "scenarios", "corrupt_king.yaml")

WALLCLOCK_FIELDS = {"started_at", "finished_at"}  # the only permitted nondeterminism


def _run(tmp_path, sub, seed=42, agent="scripted:obedient"):
    out = tmp_path / sub
    result = run_scenario(CK, agent, seed=seed, out_root=str(out))
    jsonl = open(os.path.join(result.run_dir, "decisions.jsonl"), "rb").read()
    manifest = json.load(open(os.path.join(result.run_dir, "run.json"), encoding="utf-8"))
    return result, jsonl, manifest


def test_same_seed_byte_identical(tmp_path):
    r1, log1, man1 = _run(tmp_path, "a")
    r2, log2, man2 = _run(tmp_path, "b")
    assert r1.run_id == r2.run_id                     # lineage is a pure function of inputs
    assert log1 == log2                               # THE gate: byte-identical source of truth
    strip = lambda m: {k: v for k, v in m.items() if k not in WALLCLOCK_FIELDS}
    assert strip(man1) == strip(man2)


def test_no_wallclock_in_decision_log(tmp_path):
    _, log, _ = _run(tmp_path, "a")
    for line in log.decode("utf-8").splitlines():
        assert json.loads(line)["t"] == 0.0


def test_different_seed_different_run(tmp_path):
    r1, log1, _ = _run(tmp_path, "a", seed=42)
    r2, log2, _ = _run(tmp_path, "b", seed=7)
    assert r1.run_id != r2.run_id
    assert log1 != log2


def test_rerun_in_place_reproduces(tmp_path):
    """Same out_root twice: the run overwrites itself with identical bytes (regenerable-from-seed)."""
    out = str(tmp_path / "runs")
    a = run_scenario(CK, "scripted:merciful", seed=3, out_root=out)
    first = open(os.path.join(a.run_dir, "decisions.jsonl"), "rb").read()
    b = run_scenario(CK, "scripted:merciful", seed=3, out_root=out)
    second = open(os.path.join(b.run_dir, "decisions.jsonl"), "rb").read()
    assert a.run_dir == b.run_dir and first == second
