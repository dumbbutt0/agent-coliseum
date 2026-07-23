"""M8 Phase-2 driver/executor fidelity (audit d-001 finding 0, driver side).

The autonomous ollama_local driver is the ONLY path that turns the frozen M8
config into a live sweep, so it must forward the frozen execution bounds
exactly: `max_surviving_delta` loaded from the registry bundle (run_sweep
skips the balance gate without it), the preregistered interleaved
`execution_order` with the execution index recorded, and the imposed-history
scramble-triplet preflight — all fail-closed, all BEFORE any model call.

Everything here is OFFLINE: `run_sweep` is monkeypatched to a recorder, so
the exact kwargs the driver forwards are asserted with zero network and zero
live compute. Refusal paths are asserted to fire before run_sweep is entered.
"""
import json
import os
import time

import pytest

import coliseum.textlab.registry as registry_mod
import coliseum.textlab.result_package as package_mod
import coliseum.textlab.scenario as scenario_mod
import coliseum.textlab.sweep as sweep_mod
from coliseum.textlab.schema import SchemaError
from tools.autonomy.drivers import RunnerRefusal, _drive_ollama_local

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "configs", "experiments",
                      "m8-phase2-live-order-sensitivity.experiment.json")

EID = "m8-phase2-live-order-sensitivity"
MODEL = "huihui_ai/qwen2.5-abliterate:7b-instruct"
DIGEST = "103482475c9b4d4032999dd5d7383478cad8b966ae6ae984d525daf7352c2219"
M8_SCENARIOS = ["scramble_dev_m8", "scramble_perm_m8", "scramble_sham_m8"]


def _far_deadline():
    return time.monotonic() + 600


def _m8_config(tmp_path, **over):
    """The REAL committed config, with only the evidence roots redirected
    into tmp — the frozen fields under test are the shipped ones."""
    with open(CONFIG, encoding="utf-8") as fh:
        cfg = json.load(fh)
    out_root = str(tmp_path / "runs")
    cfg["out_root"] = out_root
    cfg["manifest"] = os.path.join(out_root, "manifest.jsonl")
    cfg.update(over)
    return cfg


class _StubSweep:
    def __init__(self):
        self.digests = {MODEL: DIGEST}
        self.errors = []
        self.rows_written = 0
        self.skipped_resumed = 0


def _install_recorder(monkeypatch, calls):
    """Swap run_sweep for a kwarg recorder and manifest_load for an empty
    view, so the driver's post-sweep bookkeeping is inert."""
    def fake_run_sweep(spec, *, deadline=None, expected_digests=None,
                       progress=None, execution_order="blocked",
                       record_execution_index=None,
                       max_surviving_delta=None, retries_per_unit=None,
                       execution_policy=None):
        calls.append({"spec": spec, "deadline": deadline,
                      "expected_digests": expected_digests,
                      "execution_order": execution_order,
                      "record_execution_index": record_execution_index,
                      "max_surviving_delta": max_surviving_delta,
                      "retries_per_unit": retries_per_unit,
                      "execution_policy": execution_policy})
        os.makedirs(spec["out_root"], exist_ok=True)
        open(spec["manifest"], "w", encoding="utf-8").close()
        return _StubSweep()

    monkeypatch.setattr(sweep_mod, "run_sweep", fake_run_sweep)
    monkeypatch.setattr(sweep_mod, "manifest_load", lambda p, o: {})
    rows = {i: {"dir": f"run-{i}"} for i in range(144)}
    monkeypatch.setattr(sweep_mod, "terminal_ledgers_load",
                        lambda *_a, **_k: (rows, {}))

    def fake_replay(_manifest, out_root, *_a, **_k):
        att = {"manifest_sha256": "1" * 64, "runs": {},
               "tombstone_ledger": {"state": "absent", "sha256": None}}
        with open(os.path.join(out_root, "replay_attestation.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(att, fh)
        return att

    monkeypatch.setattr(sweep_mod, "verify_pack_replay", fake_replay)
    monkeypatch.setattr(package_mod, "_recompute_order_report",
                        lambda *_a, **_k: {
                            "order_report_version": "6",
                            "per_agent": {"a": {"verdict": "inconclusive"}}})

    def fake_package(_eid, _manifest, out_root, *_a, **_k):
        path = os.path.join(out_root, "result_package.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"package_sha256": "2" * 64,
                       "analysis_status": "analyzed"}, fh)
        return path

    monkeypatch.setattr(package_mod, "build_result_package", fake_package)
    monkeypatch.setattr(package_mod, "verify_result_package",
                        lambda path: json.load(open(path, encoding="utf-8")))


def _execution_context(cfg):
    return {
        "owner_approval_event_id": "000001-deadbeef",
        "request_payload_hash": "3" * 64,
        "execution_authorization": {
            "schema_version": "execution-authorization.v1",
            "experiment_id": cfg["experiment_id"],
            "design_hash": cfg["design_hash"],
            "implementation_commit": "a" * 40,
            "experiment_config_hash": "4" * 64,
            "model_digests": cfg["model_digests"],
            "planned_runs": cfg["expected_run_count"],
            "budget": {"max_units": 144, "max_compute_minutes": 1,
                       "max_wall_minutes": 1, "max_storage_mb": 1,
                       "max_retries_per_unit": 0, "max_scenarios": 3},
            "evidence_root": "logs/runs/m8-phase2-live-order-sensitivity",
            "manifest": ("logs/runs/m8-phase2-live-order-sensitivity/"
                         "manifest.jsonl"),
            "m7_prerequisite_events": [
                "001714-6f7a48e0", "001719-21604e97",
                "001724-8cebf880"],
            "source_integration_events": [
                "000001-11111111", "000002-22222222",
                "000003-33333333", "000004-44444444",
                "000005-55555555"],
            "resume_from": None,
        },
    }


# --------------------------------------------- exact kwargs are forwarded

def test_driver_forwards_the_frozen_bounds_to_run_sweep(tmp_path,
                                                        monkeypatch):
    """d-001 finding 0 (driver side): the frozen registry bundle's
    max_surviving_delta reaches run_sweep, execution is interleaved with the
    index recorded, and the pinned digests flow through — asserted on the
    EXACT kwargs, not on prose."""
    calls = []
    _install_recorder(monkeypatch, calls)
    loaded = []
    real_load = registry_mod.load_verified_bundle

    def spy(path, eid):
        loaded.append((path, eid))
        return real_load(path, eid)

    # the driver now loads a VERIFIED bundle (profile-checked), not a raw
    # design_hash-only threshold load
    monkeypatch.setattr(registry_mod, "load_verified_bundle", spy)

    cfg = _m8_config(tmp_path)
    outcome = _drive_ollama_local(
        ROOT, cfg, _far_deadline(), execution_context=_execution_context(cfg))

    expected_load = (os.path.join(ROOT, "configs", "registry",
                                  "experiments.yaml"), EID)
    # Once for preflight/execution policy and once for terminal closure.
    assert loaded == [expected_load, expected_load]
    assert len(calls) == 1
    call = calls[0]
    # b-003 / c-003: the frozen contract flows through a typed ExecutionPolicy,
    # NOT as loose kwargs the driver could forget
    ep = call["execution_policy"]
    assert ep is not None
    assert ep.retries_per_unit == 0            # zero-retry tombstone contract
    assert ep.max_surviving_delta == 2
    assert isinstance(ep.max_surviving_delta, int)
    assert ep.execution_order == "interleaved"
    assert ep.record_execution_index is True
    assert call["expected_digests"] == {MODEL: DIGEST}
    spec = call["spec"]
    assert spec["experiment_id"] == EID       # lets run_sweep detect policy-req
    assert spec["arbitration"] == "planner_priority"
    assert spec["temperature"] == 0.7
    assert spec["scenarios"] == M8_SCENARIOS
    assert spec["seeds"] == [42, 1]
    assert spec["sampler_seeds"] == list(range(2001, 2025))
    assert outcome["run_id"] == EID


# ------------------------------------------------ the triplet preflight

def test_preflight_lints_the_triplet_under_imposed_history(tmp_path,
                                                           monkeypatch):
    """The three m8 scenarios are linted as an A/B/C triplet with
    imposed_history=True against the INDEPENDENT scenario registry, before
    any sweep."""
    calls = []
    _install_recorder(monkeypatch, calls)
    seen = []

    def fake_lint(a, b, c, registry_path, imposed_history=False):
        seen.append({"ids": [a.scenario_id, b.scenario_id, c.scenario_id],
                     "registry_path": registry_path,
                     "imposed_history": imposed_history})
        return []

    monkeypatch.setattr(scenario_mod, "lint_scramble_triplet", fake_lint)
    cfg = _m8_config(tmp_path)
    _drive_ollama_local(
        ROOT, cfg, _far_deadline(), execution_context=_execution_context(cfg))

    assert len(seen) == 1
    assert seen[0]["ids"] == M8_SCENARIOS
    assert seen[0]["imposed_history"] is True
    assert seen[0]["registry_path"] == os.path.join(
        ROOT, "configs", "registry", "scenarios.yaml")
    assert len(calls) == 1     # preflight passed, sweep proceeded


def test_real_committed_triplet_passes_the_preflight(tmp_path, monkeypatch):
    """No seam on the lint: the shipped scramble_*_m8 scenarios really do
    satisfy the imposed-history contract the driver enforces."""
    calls = []
    _install_recorder(monkeypatch, calls)
    cfg = _m8_config(tmp_path)
    _drive_ollama_local(
        ROOT, cfg, _far_deadline(), execution_context=_execution_context(cfg))
    assert len(calls) == 1


def test_preflight_issue_refuses_before_any_sweep(tmp_path, monkeypatch):
    calls = []
    _install_recorder(monkeypatch, calls)
    monkeypatch.setattr(
        scenario_mod, "lint_scramble_triplet",
        lambda a, b, c, registry_path, imposed_history=False:
        ["B: not a permutation of A"])
    with pytest.raises(RunnerRefusal) as exc:
        _drive_ollama_local(ROOT, _m8_config(tmp_path), _far_deadline())
    assert "preflight refused" in str(exc.value)
    assert "not a permutation" in str(exc.value)
    assert calls == []         # refusal fired BEFORE run_sweep


def test_wrong_scenario_count_refuses(tmp_path, monkeypatch):
    calls = []
    _install_recorder(monkeypatch, calls)
    cfg = _m8_config(tmp_path, scenarios=M8_SCENARIOS[:2])
    with pytest.raises(RunnerRefusal) as exc:
        _drive_ollama_local(ROOT, cfg, _far_deadline())
    assert "triplet" in str(exc.value)
    assert calls == []


# ------------------------------------------------------ fail-closed bounds

def test_config_without_execution_order_refuses(tmp_path, monkeypatch):
    """A missing execution_order must refuse — a silent driver default would
    run the historical blocked order the prereg forbids."""
    calls = []
    _install_recorder(monkeypatch, calls)
    cfg = _m8_config(tmp_path)
    del cfg["execution_order"]
    with pytest.raises(RunnerRefusal) as exc:
        _drive_ollama_local(ROOT, cfg, _far_deadline())
    assert "execution_order" in str(exc.value)
    assert calls == []


def _genuine_bundle_without_dropout_bound():
    """A GENUINE registry.VerifiedBundle whose frozen design carries no dropout
    bound. Must be a real VerifiedBundle (not a duck-typed stand-in) so the
    refusal fires on the MISSING max_surviving_delta (a-006 c-003), not on the
    isinstance guard (a-006 B-1) that rejects forged/duck-typed bundles first."""
    from coliseum.textlab.registry import VerifiedBundle
    return VerifiedBundle(
        experiment_id=EID, design_hash="0" * 64,
        planned_design={"retries_per_unit": 0},   # NO max_surviving_delta
        thresholds={}, admissibility_policy={})


def test_registry_bundle_without_dropout_bound_refuses(tmp_path,
                                                       monkeypatch):
    """A verified bundle that cannot supply max_surviving_delta must refuse:
    run_sweep skips the balance gate without the bound, so running would
    silently unbound differential dropout. The refusal now fires when the
    ExecutionPolicy is built from the bundle."""
    calls = []
    _install_recorder(monkeypatch, calls)

    monkeypatch.setattr(registry_mod, "load_verified_bundle",
                        lambda path, eid: _genuine_bundle_without_dropout_bound())
    with pytest.raises(RunnerRefusal) as exc:
        _drive_ollama_local(ROOT, _m8_config(tmp_path), _far_deadline())
    assert "max_surviving_delta" in str(exc.value)
    assert calls == []


def test_tampered_registry_refuses(tmp_path, monkeypatch):
    """load_verified_bundle refusing (design_hash no longer reconstructs OR the
    frozen profile disagrees) must surface as a driver refusal, never as
    invented defaults or a silently weaker (self-rehashed) design."""
    calls = []
    _install_recorder(monkeypatch, calls)

    def raising(path, eid):
        raise SchemaError(f"{eid}: the frozen design was mutated")

    monkeypatch.setattr(registry_mod, "load_verified_bundle", raising)
    with pytest.raises(RunnerRefusal) as exc:
        _drive_ollama_local(ROOT, _m8_config(tmp_path), _far_deadline())
    assert "verified frozen bundle unavailable" in str(exc.value)
    assert calls == []


# ----------------------------------------- non-M8 configs are unaffected

def test_non_policy_config_keeps_the_historical_path(tmp_path, monkeypatch):
    """An m6-style config (no policy-required experiment_id) executes exactly
    as before: blocked order, no forced index, no dropout bound, and NO
    triplet preflight — Phase-1/M6 evidence regenerates unchanged."""
    calls = []
    _install_recorder(monkeypatch, calls)
    linted = []
    monkeypatch.setattr(
        scenario_mod, "lint_scramble_triplet",
        lambda *a, **k: linted.append(a) or [])

    out_root = str(tmp_path / "runs")
    cfg = {"task_id": "m6-style", "models": [MODEL],
           "scenarios": ["corrupt_king"], "seeds": [42],
           "sampler_seeds": None, "temperature": 0.0,
           "arbitration": "planner_priority",
           "interaction": "independent_vignettes",
           "config_dir": "configs/scenarios", "out_root": out_root,
           "manifest": os.path.join(out_root, "manifest.jsonl"),
           "model_digests": {MODEL: DIGEST}, "expected_run_count": 1}
    _drive_ollama_local(ROOT, cfg, _far_deadline())

    assert linted == []        # no preflight outside the policy-required set
    assert len(calls) == 1
    call = calls[0]
    assert call["execution_policy"] is None     # no mandatory policy off-path
    assert call["execution_order"] == "blocked"
    assert call["record_execution_index"] is None
    assert call["max_surviving_delta"] is None
