"""M8 Phase-2 operator surface (Builder W4) — replay-pack / order-report /
smoke-pack / result-package, all OFFLINE.

The Director-defined contracts (sweep.verify_pack_replay and the
ORDER_REPORT_VERSION-6 signature of metrics.order_sensitivity_report) are
implemented by concurrent builders; here they are monkeypatched with
contract-shaped fakes so these tests exercise the OPERATOR surface — argument
plumbing, refusal ordering, marker discipline, and package integrity — without
depending on the concurrent work or on any live model.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from coliseum.textlab import cli
from coliseum.textlab import metrics as metrics_mod
from coliseum.textlab import result_package as result_package_mod
from coliseum.textlab import sweep as sweep_mod
from coliseum.textlab.result_package import (build_result_package,
                                             verify_result_package)
from coliseum.textlab.schema import SchemaError

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(REPO, "configs", "registry", "experiments.yaml")
EID = "m8-phase2-live-order-sensitivity"
MODEL = "huihui_ai/qwen2.5-abliterate:7b-instruct"
DIGEST = "103482475c9b4d4032999dd5d7383478cad8b966ae6ae984d525daf7352c2219"
SCENARIOS = ("scramble_dev_m8", "scramble_perm_m8", "scramble_sham_m8")
# Director contract: the frozen m8 condition mapping
EXPECTED_CONDITIONS = {"A": "scramble_dev_m8", "B": "scramble_perm_m8",
                       "C": "scramble_sham_m8"}


def _sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _execution_extra(manifest, out_root):
    """Contract-shaped owner binding for provider-free package fixtures."""
    from coliseum.textlab.registry import _find_entry
    entry = _find_entry(REGISTRY, EID)
    pd = entry["planned_design"]
    return {
        "owner_approval_event_id": "000001-deadbeef",
        "request_payload_hash": "f" * 64,
        "execution_authorization": {
            "schema_version": "execution-authorization.v1",
            "experiment_id": EID,
            "design_hash": entry["design_hash"],
            "implementation_commit": result_package_mod._git_commit(),
            "experiment_config_hash": _sha256(os.path.join(
                REPO, "configs", "experiments",
                "m8-phase2-live-order-sensitivity.experiment.json")),
            "model_digests": dict(pd["model_digests"]),
            "planned_runs": pd["expected_run_count"],
            "budget": {"max_units": pd["expected_run_count"],
                       "max_compute_minutes": 240,
                       "max_wall_minutes": 240,
                       "max_storage_mb": 1024,
                       "max_retries_per_unit": 0,
                       "max_scenarios": 3},
            "evidence_root": out_root,
            "manifest": manifest,
            "m7_prerequisite_events": ["000001-aaaaaaaa"],
            "source_integration_events": ["000002-bbbbbbbb"],
            "resume_from": None,
        },
    }


def _mk_pack(tmp_path, sampler_seeds=(2001, 2002)):
    """A tiny offline mock pack that passes the REAL sweep.manifest_load
    validation: run dirs with run.json/decisions.jsonl/captures.jsonl plus a
    full-schema manifest. Returns (manifest_path, out_root, run_ids)."""
    out_root = str(tmp_path / "pack")
    os.makedirs(out_root)
    manifest_path = os.path.join(out_root, "manifest.jsonl")
    run_ids = []
    with open(manifest_path, "w", encoding="utf-8") as mf:
        for scenario in SCENARIOS:
            for ss in sampler_seeds:
                rid = f"run_{scenario}_s42_k{ss}"
                run_ids.append(rid)
                rd = os.path.join(out_root, rid)
                os.makedirs(rd)
                run = {"run_id": rid, "attempt": 0,
                       "comparison_regime_id": f"regime_{scenario}",
                       "agent_id": f"llm:ollama:{MODEL}",
                       "agent_regime_id": "a" * 64,
                       "agent_config": {"model": MODEL, "model_digest": DIGEST},
                       "scenario_id": scenario, "scenario_hash": "h" * 64,
                       "seed": 42, "scenario_seed": 42, "sampler_seed": ss,
                       "variant_id": "v0_caravan",
                       "sampling": {"mode": "stochastic", "temperature": 0.7},
                       "arbitration": "planner_priority",
                       "reportable": True, "stochastic_reportable": True,
                       "interaction_mode": "sequential_history"}
                json.dump(run, open(os.path.join(rd, "run.json"), "w",
                                    encoding="utf-8"))
                with open(os.path.join(rd, "decisions.jsonl"), "w",
                          encoding="utf-8") as fh:
                    fh.write(json.dumps(
                        {"kind": "decision_node",
                         "data": {"final_action": "share_resource"}}) + "\n")
                with open(os.path.join(rd, "captures.jsonl"), "w",
                          encoding="utf-8") as fh:
                    fh.write(json.dumps({"raw_text": "captured"}) + "\n")
                row = {"regime_id": f"regime_{scenario}", "model": MODEL,
                       "scenario": scenario, "scenario_seed": 42,
                       "sampler_seed": ss, "variant_id": "v0_caravan",
                       "temperature": 0.7, "sampling_mode": "stochastic",
                       "digest": DIGEST, "scenario_hash": "h" * 64,
                       "arbitration": "planner_priority", "run_id": rid,
                       "dir": rid, "reportable": True,
                       "stochastic_reportable": True,
                       "interaction_mode": "sequential_history",
                       "path": ["share_resource"]}
                mf.write(json.dumps(row) + "\n")
    return manifest_path, out_root, run_ids


def _write_attestation(manifest_path, out_root, run_ids):
    """Contract-shaped attestation, hashes built inline with hashlib."""
    tombstone_path = manifest_path + ".tombstones.jsonl"
    tombstone_identity = (
        {"state": "present", "sha256": _sha256(tombstone_path)}
        if os.path.isfile(tombstone_path)
        else {"state": "absent", "sha256": None})
    att = {"attestation_version": "1",
           "verified_utc": "2026-07-19T00:00:00Z",
           "manifest_sha256": _sha256(manifest_path),
           "tombstone_ledger": tombstone_identity,
           "runs": {}}
    for rid in run_ids:
        rd = os.path.join(out_root, rid)
        att["runs"][rid] = {
            "run_dir": rd, "replay_ok": True,
            "run_json_sha256": _sha256(os.path.join(rd, "run.json")),
            "decisions_sha256": _sha256(os.path.join(rd, "decisions.jsonl")),
            "captures_sha256": _sha256(os.path.join(rd, "captures.jsonl"))}
    path = os.path.join(out_root, "replay_attestation.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(att, fh, indent=2, sort_keys=True)
    return path, att


def _fake_verdict_report(conditions):
    cells = {label: {"distribution": {"share_resource": 1.0},
                     "counts": {"share_resource": 2},
                     "admissible_effective_n": 2, "admissible_draw_n": 2,
                     "non_decision_n": 0, "non_decision_rate": 0.0,
                     "non_decision_reasons": {}}
             for label in ("A", "B", "C", "A|S1", "A|S2")}
    return {"report_id": "order_sensitivity", "order_report_version": "6",
            "conditions": dict(conditions), "excluded": [],
            "per_agent": {f"llm:ollama:{MODEL}": {
                "agent_regime_id": "a" * 64,
                "cells": cells,
                "tv_distances": {"A|B": 0.0, "A|C": 0.0, "null": 0.0},
                "decision_inputs": {"tv_ab": 0.0, "tv_ac": 0.0,
                                    "q_ab": 0.2, "q_ac": 0.2,
                                    "min_detectable_effect": 0.25,
                                    "alpha": 0.05, "confidence": 0.95},
                "diagnostics": {"tv_null": 0.0},
                "verdict": "no_distributional_order_effect_observed",
                "verdict_reason": "offline fake for operator-surface tests"}}}


# ---------------------------------------------------------------- replay-pack

def test_replay_pack_writes_contract_shaped_attestation(tmp_path, monkeypatch,
                                                        capsys):
    manifest, out_root, run_ids = _mk_pack(tmp_path)

    def fake_verify(manifest_path, out_root_arg, config_dir, **_kwargs):
        assert manifest_path == manifest and out_root_arg == out_root
        return _write_attestation(manifest_path, out_root_arg, run_ids)[0]

    monkeypatch.setattr(sweep_mod, "verify_pack_replay", fake_verify,
                        raising=False)
    cli.main(["replay-pack", "--experiment-id", EID,
              "--manifest", manifest, "--out-root", out_root,
              "--registry", REGISTRY,
              "--config-dir", "configs/scenarios"])
    out = capsys.readouterr().out
    att_path = os.path.join(out_root, "replay_attestation.json")
    assert att_path in out and "6 replay-verified" in out
    att = json.load(open(att_path, encoding="utf-8"))
    assert att["attestation_version"] == "1"
    assert att["manifest_sha256"] == _sha256(manifest)
    assert set(att["runs"]) == set(run_ids)
    for rec in att["runs"].values():
        assert set(rec) == {"run_dir", "replay_ok", "run_json_sha256",
                            "decisions_sha256", "captures_sha256"}
        assert rec["replay_ok"] is True


def test_replay_pack_refuses_on_failure_and_writes_nothing(tmp_path,
                                                           monkeypatch):
    manifest, out_root, _ = _mk_pack(tmp_path)

    def fake_verify(*_a, **_k):
        raise SchemaError("run X: decisions.jsonl differs on replay")

    monkeypatch.setattr(sweep_mod, "verify_pack_replay", fake_verify,
                        raising=False)
    with pytest.raises(SystemExit) as e:
        cli.main(["replay-pack", "--experiment-id", EID,
                  "--manifest", manifest, "--out-root", out_root,
                  "--registry", REGISTRY])
    assert "REPLAY-PACK REFUSED" in str(e.value.code)
    assert not os.path.exists(os.path.join(out_root,
                                           "replay_attestation.json"))


def test_replay_pack_invalid_registry_removes_stale_receipt(tmp_path):
    manifest, out_root, _run_ids = _mk_pack(tmp_path)
    attestation_path = os.path.join(out_root, "replay_attestation.json")
    with open(attestation_path, "w", encoding="utf-8") as fh:
        json.dump({"stale": True}, fh)
    with pytest.raises(SystemExit, match="REPLAY-PACK REFUSED"):
        cli.main(["replay-pack", "--experiment-id", EID,
                  "--manifest", manifest, "--out-root", out_root,
                  "--registry", str(tmp_path / "missing-registry.yaml")])
    assert not os.path.exists(attestation_path)


def test_replay_core_is_deterministic_and_performs_no_write(
        tmp_path, monkeypatch):
    manifest, out_root, run_ids = _mk_pack(tmp_path)
    monkeypatch.setattr(
        sweep_mod, "verify_run_replay",
        lambda _run_dir, _config_dir: (True, "byte-identical"))
    planned = {
        "models": [MODEL],
        "scenarios": list(SCENARIOS),
        "scenario_seeds": [42],
        "sampler_seeds": [2001, 2002],
    }
    boundaries = []
    with sweep_mod._manifest_advisory_lock(manifest) as locked:
        first = sweep_mod.build_pack_replay_core_locked(
            locked, out_root, "configs/scenarios", planned,
            progress_check=lambda: boundaries.append("checked"))
        second = sweep_mod.build_pack_replay_core_locked(
            locked, out_root, "configs/scenarios", planned)
    assert first == second
    assert set(first) == {"manifest_sha256", "tombstone_ledger", "runs"}
    assert set(first["runs"]) == set(run_ids)
    assert len(boundaries) == 2 * len(run_ids)
    assert not os.path.exists(os.path.join(
        out_root, "replay_attestation.json"))


# --------------------------------------------------------------- order-report

def _order_report_argv(manifest, out_root):
    return ["order-report", "--experiment-id", EID, "--manifest", manifest,
            "--out-root", out_root, "--registry", REGISTRY]


def test_order_report_refuses_without_attestation(tmp_path, monkeypatch):
    manifest, out_root, _ = _mk_pack(tmp_path)

    def never(*_a, **_k):
        raise AssertionError("analysis must not run without an attestation")

    monkeypatch.setattr(metrics_mod, "order_sensitivity_report", never)
    with pytest.raises(SystemExit) as e:
        cli.main(_order_report_argv(manifest, out_root))
    msg = str(e.value.code)
    assert "MANDATORY" in msg and "replay" in msg.lower()
    assert not os.path.exists(os.path.join(out_root, "order_report.json"))


def test_order_report_end_to_end_reaches_verdict_json(tmp_path, monkeypatch,
                                                      capsys):
    manifest, out_root, run_ids = _mk_pack(tmp_path)
    _, att = _write_attestation(manifest, out_root, run_ids)
    captured = {}

    def fake_osr(run_dirs, conditions, *, admissibility_policy, thresholds,
                 replay_attestation, terminal_dp_id, surviving_counts,
                 retries_per_unit=None, frozen_grid=None):
        captured.update(run_dirs=run_dirs, conditions=conditions,
                        admissibility_policy=admissibility_policy,
                        thresholds=thresholds,
                        replay_attestation=replay_attestation,
                        terminal_dp_id=terminal_dp_id,
                        surviving_counts=surviving_counts,
                        retries_per_unit=retries_per_unit,
                        frozen_grid=frozen_grid)
        # the cli DERIVES the terminal probe from the triplet's unique
        # decision-kind point — for the m8 scenarios that is d_partner
        assert terminal_dp_id == "d_partner"
        # d-003 f1: the policy-required entrypoint sources retries_per_unit=0
        # from the frozen verified design — omission is impossible
        assert retries_per_unit == 0
        return _fake_verdict_report(conditions)

    monkeypatch.setattr(metrics_mod, "order_sensitivity_report", fake_osr)
    cli.main(_order_report_argv(manifest, out_root))
    out = capsys.readouterr().out
    # verdict + reasons printed
    assert "no_distributional_order_effect_observed" in out and "VERDICT" in out
    # the report JSON was written
    rp = os.path.join(out_root, "order_report.json")
    assert os.path.isfile(rp)
    report = json.load(open(rp, encoding="utf-8"))
    assert report["order_report_version"] == "6"
    # ALL contract kwargs were supplied, from the right sources
    assert captured["conditions"] == EXPECTED_CONDITIONS
    assert captured["surviving_counts"] == {s: 2 for s in SCENARIOS}
    assert captured["replay_attestation"] == att
    assert len(captured["run_dirs"]) == 6
    assert captured["run_dirs"] == sorted(captured["run_dirs"])
    # frozen bundles came from the registry loaders
    assert captured["admissibility_policy"]["max_non_decision_rate"] == 0.2
    assert captured["thresholds"]["max_surviving_delta"] == 2
    assert captured["thresholds"]["permutation_seed"] == 20260719
    # d-006: the policy-required entrypoint threads the FROZEN matched-unit grid
    # (pinned count + group axis) from the verified design — omission is impossible
    assert captured["frozen_grid"] == {"scenario_seeds": [42, 1],
                                       "matched_units_per_condition": 48}


def test_order_report_typed_refusal_writes_no_distances_file(tmp_path,
                                                             monkeypatch):
    manifest, out_root, run_ids = _mk_pack(tmp_path)
    _write_attestation(manifest, out_root, run_ids)
    before = set(os.listdir(out_root))

    def refusing(*_a, **_k):
        exc = SchemaError("order-sensitivity aggregator REFUSES under "
                          "admissibility policy '1': A: non_decision_rate "
                          "0.5 > 0.2")
        exc.report = {"report_id": "order_sensitivity", "per_agent": {}}
        raise exc

    monkeypatch.setattr(metrics_mod, "order_sensitivity_report", refusing)
    with pytest.raises(SystemExit) as e:
        cli.main(_order_report_argv(manifest, out_root))
    msg = str(e.value.code)
    assert "REFUSED (typed)" in msg and "REFUSES" in msg
    # nothing new on disk — in particular no distances-bearing file
    assert set(os.listdir(out_root)) == before
    assert not os.path.exists(os.path.join(out_root, "order_report.json"))


def test_order_report_refuses_smoke_marked_pack(tmp_path, monkeypatch):
    manifest, out_root, run_ids = _mk_pack(tmp_path)
    _write_attestation(manifest, out_root, run_ids)
    with open(os.path.join(out_root, "SMOKE_MARKER.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"claim_bearing": False,
                   "purpose": "operational validation"}, fh)

    def never(*_a, **_k):
        raise AssertionError("a smoke pack must never reach analysis")

    monkeypatch.setattr(metrics_mod, "order_sensitivity_report", never)
    with pytest.raises(SystemExit) as e:
        cli.main(_order_report_argv(manifest, out_root))
    msg = str(e.value.code)
    assert "SMOKE" in msg and "never be analyzed" in msg
    assert not os.path.exists(os.path.join(out_root, "order_report.json"))


# ----------------------------------------------------------------- smoke-pack

FAKE_HEAD = "f" * 40   # the candidate commit, injected via cli._git_head


def _owner_authorization(tmp_path, experiment_id, design_hash_hex, digests,
                         scale, run_count, name="owner-auth.json",
                         overrides=None):
    """Write a canonical smoke-authorization.v1 manifest; overrides let each
    regression case corrupt exactly one binding."""
    auth = {"authorization_version": "1",
            "authorization_kind": "owner_experiment_execution",
            "experiment_id": experiment_id,
            "design_hash": design_hash_hex,
            "candidate_commit": FAKE_HEAD,
            "model_digests": dict(digests),
            "run_count": run_count,
            "scale": scale,
            "budget": {"max_units": run_count}}
    auth.update(overrides or {})
    path = str(tmp_path / name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(auth, fh, indent=2, sort_keys=True)
    return path


def test_smoke_pack_refuses_without_ollama_host(tmp_path, monkeypatch):
    out_root = str(tmp_path / "m8-smoke")
    monkeypatch.delenv("OLLAMA_HOST", raising=False)

    def never(*_a, **_k):
        raise AssertionError("run_sweep must not be reached without a host")

    monkeypatch.setattr(sweep_mod, "run_sweep", never)
    with pytest.raises(SystemExit) as e:
        cli.main(["smoke-pack", "--experiment-id", EID, "--scale", "2",
                  "--out-root", out_root, "--registry", REGISTRY])
    assert "OLLAMA_HOST" in str(e.value.code)
    assert not os.path.exists(os.path.join(out_root, "SMOKE_MARKER.json"))


def test_smoke_pack_refuses_unlabeled_out_root(tmp_path, monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://smoke-host:11434")
    with pytest.raises(SystemExit) as e:
        cli.main(["smoke-pack", "--experiment-id", EID, "--scale", "2",
                  "--out-root", str(tmp_path / "claims"),
                  "--registry", REGISTRY])
    assert "smoke" in str(e.value.code)


def test_smoke_pack_builds_scaled_spec_and_marker(tmp_path, monkeypatch,
                                                  capsys):
    out_root = str(tmp_path / "m8-smoke")
    monkeypatch.setenv("OLLAMA_HOST", "http://smoke-host:11434")
    monkeypatch.setattr(cli, "_git_head", lambda: FAKE_HEAD)
    captured = {}

    def fake_run_sweep(spec, **kwargs):
        captured["spec"] = spec
        captured["kwargs"] = kwargs
        r = sweep_mod.SweepResult()
        r.rows_written = 6
        return r

    monkeypatch.setattr(sweep_mod, "run_sweep", fake_run_sweep)
    # the exact canonical owner authorization for THIS invocation, built
    # from the live registry entry the command itself will verify against
    from coliseum.textlab.registry import _find_entry
    entry = _find_entry(REGISTRY, EID)
    pd = entry["planned_design"]
    run_count = (len(pd["models"]) * len(pd["scenarios"])
                 * len(pd["scenario_seeds"])
                 * len(list(pd["sampler_seeds"])[:3]))
    auth = _owner_authorization(tmp_path, EID, entry["design_hash"],
                                pd["model_digests"], 3, run_count)
    cli.main(["smoke-pack", "--experiment-id", EID, "--scale", "3",
              "--out-root", out_root, "--registry", REGISTRY,
              "--authorization", auth])
    out = capsys.readouterr().out
    # digest-pinned models announced BEFORE any contact
    assert out.index(DIGEST) < out.index("rows written")
    assert MODEL in out and "claim_bearing: false" in out
    # the marker exists and is claim-refusing
    marker = json.load(open(os.path.join(out_root, "SMOKE_MARKER.json"),
                            encoding="utf-8"))
    assert marker["claim_bearing"] is False
    assert marker["purpose"] == "operational validation"
    # the spec is the frozen design scaled to the FIRST N sampler seeds
    spec = captured["spec"]
    assert spec["sampler_seeds"] == [2001, 2002, 2003]
    assert spec["scenarios"] == list(SCENARIOS)
    assert spec["seeds"] == [42, 1]
    assert spec["temperature"] == 0.7
    assert spec["arbitration"] == "planner_priority"
    assert spec["interaction"] == "sequential_history"
    assert "smoke" in os.path.basename(spec["manifest"])
    assert spec["out_root"] == out_root
    # execution discipline + integrity gates travel with the run as ONE typed
    # ExecutionPolicy (b-003/c-003), not loose kwargs a caller could omit
    policy = captured["kwargs"]["execution_policy"]
    assert policy.execution_order == "interleaved"
    assert policy.retries_per_unit == 0
    assert policy.max_surviving_delta == 2
    assert policy.record_execution_index is True
    assert captured["kwargs"]["expected_digests"] == {MODEL: DIGEST}


# ------------------------------------- smoke-pack authorization gate (B-002)
#
# Verdict first-gladiator-m8-phase2-b-002: smoke-pack may not initiate ANY
# live provider contact (or filesystem mutation preparing one) without a
# canonical owner experiment authorization binding design hash, candidate
# commit, model digests, run count and budget. These tests use an INLINE
# fixture registry (concurrent builders own the live one) and a trapped
# run_sweep: of {absent, design-audit-only, stale, exact} only the exact
# authorization may reach the sweep.

FIX_EID = "m8-fixture-smoke-authz"
FIX_MODEL = "fixture/model:tag"
FIX_DIGEST = "d" * 64


def _fixture_registry(tmp_path):
    """A minimal self-consistent experiments registry written inline (YAML is
    a JSON superset). Returns (registry_path, planned_design, design_hash)."""
    from coliseum.textlab.registry import design_hash
    pd = {"models": [FIX_MODEL],
          "model_digests": {FIX_MODEL: FIX_DIGEST},
          "scenarios": ["fix_dev", "fix_perm", "fix_sham"],
          "scenario_seeds": [42, 1],
          "sampler_seeds": [2001, 2002, 2003, 2004],
          "temperature": 0.7,
          "arbitration": "planner_priority",
          "interaction_mode": "sequential_history",
          # the smoke-pack routes through load_verified_bundle (B-0/C-0), which
          # requires the frozen admissibility bounds to be present; a stochastic
          # live design must freeze its bounds. Fixture values, on_violation=refuse.
          "admissibility_policy": {"policy_version": "1",
                                   "admissibility_version": "1",
                                   "max_non_decision_rate": 0.2,
                                   "max_non_decision_rate_delta": 0.1,
                                   "min_admissible_effective_n": 1,
                                   "on_violation": "refuse"},
          "thresholds": {"permutation_seed": 20260719},
          # c-003 frozen contract: no re-rolls; the balance gate needs the delta.
          "retries_per_unit": 0,
          "max_surviving_delta": 2}
    dh = design_hash(pd)
    reg = {"registry_version": "1",
           "experiments": [{"experiment_id": FIX_EID,
                            "planned_design": pd, "design_hash": dh}]}
    path = str(tmp_path / "fixture-experiments.yaml")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(reg, fh, indent=2, sort_keys=True)
    return path, pd, dh


def _authz_env(tmp_path, monkeypatch):
    """Common harness: fixture registry, pinned HEAD, trapped run_sweep.
    Returns (registry, pd, design_hash, out_root, sweep_calls, argv_base)."""
    registry, pd, dh = _fixture_registry(tmp_path)
    out_root = str(tmp_path / "m8-smoke")
    monkeypatch.setenv("OLLAMA_HOST", "http://smoke-host:11434")
    monkeypatch.setattr(cli, "_git_head", lambda: FAKE_HEAD)
    calls = []

    def trap(spec, **kwargs):
        calls.append(spec)
        r = sweep_mod.SweepResult()
        r.rows_written = 0
        return r

    monkeypatch.setattr(sweep_mod, "run_sweep", trap)
    argv = ["smoke-pack", "--experiment-id", FIX_EID, "--scale", "2",
            "--out-root", out_root, "--registry", registry]
    return registry, pd, dh, out_root, calls, argv


def _fixture_run_count(pd, scale):
    return (len(pd["models"]) * len(pd["scenarios"])
            * len(pd["scenario_seeds"])
            * len(list(pd["sampler_seeds"])[:scale]))


def _assert_refused_before_contact(excinfo, out_root, calls):
    """A refused invocation exits nonzero, reaches no sweep, writes NOTHING —
    not the marker, not the out_root itself."""
    assert excinfo.value.code            # nonzero exit
    assert "SMOKE-PACK REFUSED" in str(excinfo.value.code)
    assert calls == []                   # run_sweep never reached
    assert not os.path.exists(out_root)  # no filesystem mutation at all


def test_smoke_pack_refuses_without_authorization(tmp_path, monkeypatch):
    _, _, _, out_root, calls, argv = _authz_env(tmp_path, monkeypatch)
    with pytest.raises(SystemExit) as e:
        cli.main(argv)                   # no --authorization at all
    _assert_refused_before_contact(e, out_root, calls)
    msg = str(e.value.code)
    assert "authorization" in msg
    # the smoke marker's status is explicitly NOT contact authority
    assert "never grants contact authority" in msg


def test_smoke_pack_refuses_design_audit_only_artifact(tmp_path, monkeypatch):
    _, pd, dh, out_root, calls, argv = _authz_env(tmp_path, monkeypatch)
    # every binding correct EXCEPT the kind: a design-audit approval carrying
    # the right design hash and commit still is not execution authority
    auth = _owner_authorization(
        tmp_path, FIX_EID, dh, pd["model_digests"], 2,
        _fixture_run_count(pd, 2),
        overrides={"authorization_kind": "design_audit"})
    with pytest.raises(SystemExit) as e:
        cli.main(argv + ["--authorization", auth])
    _assert_refused_before_contact(e, out_root, calls)
    assert "NOT authority to contact the provider" in str(e.value.code)
    # and a partial artifact missing the execution bindings also refuses
    partial = str(tmp_path / "design-audit-note.json")
    with open(partial, "w", encoding="utf-8") as fh:
        json.dump({"authorization_kind": "design_audit",
                   "experiment_id": FIX_EID, "design_hash": dh}, fh)
    with pytest.raises(SystemExit) as e:
        cli.main(argv + ["--authorization", partial])
    _assert_refused_before_contact(e, out_root, calls)
    assert "missing required bindings" in str(e.value.code)


def test_smoke_pack_refuses_stale_or_mismatched_authorization(tmp_path,
                                                              monkeypatch):
    _, pd, dh, out_root, calls, argv = _authz_env(tmp_path, monkeypatch)
    run_count = _fixture_run_count(pd, 2)
    stale_cases = {
        "wrong-commit": dict(candidate_commit="0" * 40),
        "wrong-design-hash": dict(design_hash="0" * 64),
        "wrong-digests": dict(model_digests={FIX_MODEL: "0" * 64}),
        "wrong-run-count": dict(run_count=run_count + 1),
        "wrong-scale": dict(scale=3),
        "budget-exceeded": dict(budget={"max_units": run_count - 1}),
    }
    for name, override in stale_cases.items():
        auth = _owner_authorization(tmp_path, FIX_EID, dh,
                                    pd["model_digests"], 2, run_count,
                                    name=f"auth-{name}.json",
                                    overrides=override)
        with pytest.raises(SystemExit) as e:
            cli.main(argv + ["--authorization", auth])
        _assert_refused_before_contact(e, out_root, calls)
        assert "does not bind this invocation" in str(e.value.code), name
    # a HEAD that cannot be resolved fails CLOSED, never open
    monkeypatch.setattr(cli, "_git_head", lambda: None)
    auth = _owner_authorization(tmp_path, FIX_EID, dh, pd["model_digests"],
                                2, run_count, name="auth-no-head.json")
    with pytest.raises(SystemExit) as e:
        cli.main(argv + ["--authorization", auth])
    _assert_refused_before_contact(e, out_root, calls)
    assert "fails closed" in str(e.value.code)


def test_smoke_pack_exact_authorization_reaches_sweep(tmp_path, monkeypatch,
                                                      capsys):
    _, pd, dh, out_root, calls, argv = _authz_env(tmp_path, monkeypatch)
    auth = _owner_authorization(tmp_path, FIX_EID, dh, pd["model_digests"],
                                2, _fixture_run_count(pd, 2))
    cli.main(argv + ["--authorization", auth])
    out = capsys.readouterr().out
    # exactly one sweep, with the frozen fixture design scaled to 2 seeds
    assert len(calls) == 1
    spec = calls[0]
    assert spec["sampler_seeds"] == [2001, 2002]
    assert spec["scenarios"] == ["fix_dev", "fix_perm", "fix_sham"]
    # digest printing survives the repair, before any contact
    assert out.index(FIX_DIGEST) < out.index("rows written")
    assert "claim_bearing: false" in out
    marker = json.load(open(os.path.join(out_root, "SMOKE_MARKER.json"),
                            encoding="utf-8"))
    assert marker["claim_bearing"] is False


# ------------------------------------------------------------- result package

def _analyzed_pack(tmp_path, monkeypatch):
    """A pack with attestation + verdict-bearing report on disk. Used ONLY by
    the refusal tests whose gate fires BEFORE the d-003 f2 recompute (verdictless
    report, missing attestation, attestation-bound-to-other-manifest), so the
    fast synthetic `_mk_pack` — which the recompute would reject — is sufficient
    and honest: those refusals never reach the recomputation at all."""
    manifest, out_root, run_ids = _mk_pack(tmp_path)
    _write_attestation(manifest, out_root, run_ids)
    report = _fake_verdict_report(EXPECTED_CONDITIONS)
    report_path = os.path.join(out_root, "order_report.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
    return manifest, out_root, report_path


# ---- a REAL, recomputable pack (d-003 f2) --------------------------------
#
# build_result_package RE-DERIVES the order report for the policy-required m8
# experiment from the bound evidence (sweep.manifest_load ->
# metrics.order_sensitivity_report with the frozen VerifiedBundle and
# retries_per_unit=0) and demands canonical equality with the supplied report.
# To exercise that path HONESTLY the tests below hand it a pack the recompute
# genuinely accepts and a report that is genuinely the recomputed one.
#
# The pack reuses the operating-characteristics builder `oc._write_unit`, which
# writes a decision node carrying the terminal probe `d_partner` — exactly what
# `metrics.order_sensitivity_report` consumes. The A/B/C conditions get the SAME
# action per matched unit (a clean sharp-null-true pack), so the recompute yields
# the deterministic verdict `no_distributional_order_effect_observed`.

from scripts import m8_operating_characteristics as oc  # noqa: E402
from coliseum.textlab.result_package import (  # noqa: E402
    _recompute_order_report)

# the real pack's per-agent id is oc._write_unit's fixed agent (`live`), not the
# synthetic `llm:ollama:...` of `_mk_pack`
REAL_AGENT = "live"
# 3 conditions x 2 variants x 24 sampler seeds = 144 real run dirs
REAL_RUN_COUNT = 3 * len(oc.VARIANTS) * len(oc.SAMPLER_SEEDS)


def _recomputable_pack(tmp_path, subdir="pack", law=0):
    """Write a REAL pack the d-003 f2 recompute accepts, plus a genuinely
    recomputed order report on disk. Returns (manifest, out_root, report_path).

    `law` selects a deterministic per-unit action assignment; A, B and C all
    receive the SAME action for a matched unit (sharp-null true, so the
    marginals are identical and the recompute verdict is
    `no_distributional_order_effect_observed`). Two different `law` values yield
    two valid packs whose recomputed reports differ — used to prove a report
    bound to a DIFFERENT pack is refused by the recompute."""
    out_root = str(tmp_path / subdir)
    os.makedirs(out_root)
    run_ids = []
    rows = []
    for cond in ("A", "B", "C"):
        for variant, scen_seed in oc.VARIANTS:
            for s_index, samp in enumerate(oc.SAMPLER_SEEDS):
                # action depends ONLY on the unit (and the pack's law), never on
                # the condition -> A_i == B_i == C_i at every matched unit. The
                # two laws use DIFFERENT marginal supports (4-action cycle vs
                # 2-action alternation) so their recomputed reports genuinely
                # differ, while both stay sharp-null-true.
                if law == 0:
                    action = oc.MENU[(s_index
                                      + (0 if variant == "v0_caravan" else 2))
                                     % len(oc.MENU)]
                else:
                    action = oc.MENU[s_index % 2]
                d = oc._write_unit(out_root, cond, variant, scen_seed, samp,
                                   action)
                rid = os.path.basename(d)
                run_ids.append(rid)
                # oc._write_unit omits comparison_regime_id; sweep.manifest_load
                # keys resume identity on (comparison_regime_id, scenario_seed,
                # sampler_seed), so a per-CONDITION regime id keeps all 144 keys
                # unique across the shared unit grid.
                rj = os.path.join(d, "run.json")
                with open(rj, encoding="utf-8") as fh:
                    run = json.load(fh)
                run["comparison_regime_id"] = f"regime_{cond}"
                run.setdefault("agent_config", {})["model"] = MODEL
                run["agent_config"]["model_digest"] = DIGEST
                with open(rj, "w", encoding="utf-8") as fh:
                    json.dump(run, fh)
                rows.append({"regime_id": f"regime_{cond}", "model": MODEL,
                             "scenario": oc.CONDITIONS[cond],
                             "scenario_seed": scen_seed, "sampler_seed": samp,
                             "variant_id": variant, "temperature": 0.7,
                             "sampling_mode": "stochastic", "digest": DIGEST,
                             "scenario_hash": "",
                             "arbitration": "planner_priority", "run_id": rid,
                             "dir": rid, "reportable": True,
                             "stochastic_reportable": True,
                             "interaction_mode": "sequential_history",
                             "path": ["expose", action]})
    manifest = os.path.join(out_root, "manifest.jsonl")
    with open(manifest, "w", encoding="utf-8") as mf:
        for row in rows:
            mf.write(json.dumps(row) + "\n")

    # attestation MUST bind manifest_sha256 to THIS manifest and carry a per-run
    # record (with run_dir) for every run — written AFTER run.json was patched,
    # so its hashes cover the final bytes.
    _write_attestation(manifest, out_root, run_ids)

    # the report handed to build_result_package IS the genuine recomputation
    # (same VerifiedBundle / conditions / terminal probe / surviving counts /
    # retries_per_unit=0 the recompute derives), so canonical equality holds.
    att = json.load(open(os.path.join(out_root, "replay_attestation.json"),
                         encoding="utf-8"))
    report = _recompute_order_report(EID, REGISTRY, manifest, out_root,
                                     "configs/scenarios", att)
    from coliseum.textlab.schema import canonical_json
    report_path = os.path.join(out_root, "order_report.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(canonical_json(report) + "\n")
    return manifest, out_root, report_path


def _write_terminal_tombstone(manifest, *, same_coordinate=True,
                              regime=None):
    """Write one fully shaped adjacent tombstone from a real manifest row."""
    with open(manifest, encoding="utf-8") as fh:
        row = json.loads(fh.readline())
    tombstone = {
        "regime_id": regime or row["regime_id"],
        "model": row["model"],
        "scenario": row["scenario"],
        "scenario_seed": (row["scenario_seed"] if same_coordinate else 1),
        "sampler_seed": row["sampler_seed"],
        "failure_kind": "timeout",
        "error": "offline terminal-ledger fixture",
        "recorded_utc": "2026-07-22T00:00:00Z",
    }
    path = manifest + ".tombstones.jsonl"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(tombstone, sort_keys=True) + "\n")
    return path


def test_all_derived_surfaces_refuse_same_coordinate_terminal_conflict(
        tmp_path):
    """D-012: replay, analysis, and packaging share the sweep refusal."""
    from coliseum.textlab.registry import load_verified_bundle

    manifest, out_root, report_path = _recomputable_pack(tmp_path)
    with open(report_path, "rb") as fh:
        report_bytes = fh.read()
    os.remove(report_path)
    _write_terminal_tombstone(manifest)

    with pytest.raises(SystemExit, match="terminal outcomes disagree"):
        cli.main(_order_report_argv(manifest, out_root))
    assert not os.path.exists(report_path)

    with open(report_path, "wb") as fh:
        fh.write(report_bytes)
    with pytest.raises(SchemaError, match="terminal outcomes disagree"):
        build_result_package(EID, manifest, out_root, REGISTRY, report_path,
                             {}, config_dir="configs/scenarios")
    assert not os.path.exists(os.path.join(out_root, "result_package.json"))

    bundle = load_verified_bundle(REGISTRY, EID)
    with pytest.raises(sweep_mod.TerminalLedgerError,
                       match="terminal outcomes disagree"):
        sweep_mod.verify_pack_replay(
            manifest, out_root, "configs/scenarios",
            planned_design=bundle.planned_design)
    assert not os.path.exists(os.path.join(out_root,
                                           "replay_attestation.json"))


def test_authenticated_tombstone_absence_rejects_post_replay_creation(
        tmp_path):
    """An adjacent ledger created after replay invalidates later derivation."""
    manifest, out_root, report_path = _recomputable_pack(tmp_path)
    with open(report_path, "rb") as fh:
        report_bytes = fh.read()
    os.remove(report_path)
    open(manifest + ".tombstones.jsonl", "w", encoding="utf-8").close()

    with pytest.raises(SystemExit, match="authenticated absence"):
        cli.main(_order_report_argv(manifest, out_root))
    assert not os.path.exists(report_path)

    with open(report_path, "wb") as fh:
        fh.write(report_bytes)
    with pytest.raises(SchemaError, match="authenticated absence"):
        build_result_package(EID, manifest, out_root, REGISTRY, report_path,
                             {}, config_dir="configs/scenarios")
    assert not os.path.exists(os.path.join(out_root, "result_package.json"))


def test_result_package_builds_and_verifies(tmp_path):
    manifest, out_root, report_path = _recomputable_pack(tmp_path)
    extra = _execution_extra(manifest, out_root)
    # config_dir points at the m8 scenarios so the recompute can derive the
    # terminal probe d_partner
    path = build_result_package(EID, manifest, out_root, REGISTRY,
                                report_path, extra,
                                config_dir="configs/scenarios")
    assert path == os.path.join(out_root, "result_package.json")
    pkg = verify_result_package(path)   # raises on any mismatch
    assert pkg["package_version"] == "3"
    assert pkg["experiment_id"] == EID
    # design identity from the registry (not hard-coded: the design may be
    # re-frozen pre-execution by the audit repair loop; the invariant is that
    # the package carries the CURRENT registry entry's reconstructing hash),
    # echoed version from the report
    from coliseum.textlab.registry import _find_entry, design_hash
    entry = _find_entry(REGISTRY, EID)
    assert pkg["design_hash"] == entry["design_hash"]
    assert pkg["design_hash"] == design_hash(entry["planned_design"])
    assert pkg["order_report_version"] == "6"
    # the verdict is the DERIVED one, keyed by the real pack's agent id
    assert pkg["verdicts"] == {REAL_AGENT:
                               "no_distributional_order_effect_observed"}
    # models/digests still come from the frozen registry design, not the pack
    assert pkg["models"] == [MODEL]
    assert pkg["model_digests"] == {MODEL: DIGEST}
    # every referenced artifact identified by hash
    assert pkg["manifest"]["sha256"] == _sha256(manifest)
    assert pkg["tombstone_ledger"] == {
        "path": manifest + ".tombstones.jsonl",
        "state": "absent", "sha256": None}
    assert pkg["replay_attestation"]["tombstone_ledger"] == {
        "state": "absent", "sha256": None}
    assert pkg["replay_attestation"]["sha256"] == _sha256(
        os.path.join(out_root, "replay_attestation.json"))
    assert pkg["report"]["sha256"] == _sha256(report_path)
    assert len(pkg["runs"]) == REAL_RUN_COUNT
    for rec in pkg["runs"].values():
        assert set(rec) == {"run_dir", "replay_ok", "run_json_sha256",
                            "decisions_sha256", "captures_sha256"}
    assert pkg["extra"] == extra
    assert "git_commit" in pkg   # recorded (may be None), never hashed


def test_terminal_tombstone_pack_closes_as_inconclusive_without_statistics(
        tmp_path):
    """A fully terminal 143-success/1-failure pack is completed evidence,
    while the missing matched-success unit prevents confirmatory statistics."""
    from coliseum.textlab.registry import load_verified_bundle
    from coliseum.textlab.result_package import terminal_failure_report

    manifest, out_root, report_path = _recomputable_pack(tmp_path)
    with open(manifest, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh]
    failed_row = rows.pop(0)
    with open(manifest, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    tombstone = {
        "regime_id": failed_row["regime_id"], "model": failed_row["model"],
        "scenario": failed_row["scenario"],
        "scenario_seed": failed_row["scenario_seed"],
        "sampler_seed": failed_row["sampler_seed"],
        "failure_kind": "timeout", "error": "frozen terminal fixture",
        "recorded_utc": "2026-07-22T00:00:00Z",
    }
    with open(manifest + ".tombstones.jsonl", "w", encoding="utf-8") as fh:
        fh.write(json.dumps(tombstone) + "\n")
    _write_attestation(manifest, out_root, [row["run_id"] for row in rows])

    bundle = load_verified_bundle(REGISTRY, EID)
    terminal = sweep_mod.terminal_ledgers_load(
        manifest, out_root, planned_design=bundle.planned_design,
        require_tombstone_regime_anchors=True)
    report = terminal_failure_report(
        EID, bundle.planned_design, terminal[0], terminal[1])
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, sort_keys=True)
    assert report["statistics_computed"] is False
    assert "tv_distances" not in report

    path = build_result_package(
        EID, manifest, out_root, REGISTRY, report_path,
        _execution_extra(manifest, out_root), config_dir="configs/scenarios")
    pkg = verify_result_package(path)
    assert pkg["analysis_status"] == "terminal_failure_inconclusive"
    assert pkg["verdicts"] == {"pack": "inconclusive"}


def test_result_package_verification_rejects_later_tombstone_creation(
        tmp_path):
    """Package v3 authenticates that the adjacent ledger stayed absent."""
    manifest, out_root, report_path = _recomputable_pack(tmp_path)
    path = build_result_package(EID, manifest, out_root, REGISTRY,
                                report_path, _execution_extra(manifest, out_root),
                                config_dir="configs/scenarios")
    verify_result_package(path)
    open(manifest + ".tombstones.jsonl", "w", encoding="utf-8").close()
    with pytest.raises(SchemaError, match="created, removed, or modified"):
        verify_result_package(path)


def test_result_package_locked_verifier_rejects_manifest_reference_switch(
        tmp_path):
    """The package cannot select another ledger after lock acquisition."""
    package_path = tmp_path / "result_package.json"
    package_path.write_text(
        json.dumps({"manifest": {"path": str(tmp_path / "second.jsonl")}}),
        encoding="utf-8")
    with pytest.raises(SchemaError, match="reference changed"):
        result_package_mod._verify_result_package_locked(
            str(package_path),
            expected_manifest_path=str(tmp_path / "first.jsonl"))


def test_result_package_refuses_on_tamper(tmp_path):
    manifest, out_root, report_path = _recomputable_pack(tmp_path)
    path = build_result_package(EID, manifest, out_root, REGISTRY,
                                report_path, _execution_extra(manifest, out_root),
                                config_dir="configs/scenarios")
    # 1) tamper the package body itself
    pkg = json.load(open(path, encoding="utf-8"))
    pkg["verdicts"] = {f"llm:ollama:{MODEL}": "distributional_order_effect_observed"}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(pkg, fh)
    with pytest.raises(SchemaError, match="content hash mismatch"):
        verify_result_package(path)
    # 2) rebuild clean, then tamper a referenced artifact
    path = build_result_package(EID, manifest, out_root, REGISTRY,
                                report_path, _execution_extra(manifest, out_root),
                                config_dir="configs/scenarios")
    verify_result_package(path)
    with open(report_path, "a", encoding="utf-8") as fh:
        fh.write("\n")
    with pytest.raises(SchemaError, match="report artifact tampered"):
        verify_result_package(path)


def test_result_package_refuses_a_forged_verdict(tmp_path):
    """The heart of d-003 finding 2: build_result_package RE-DERIVES the verdict
    from the bound evidence and refuses any report whose verdict the evidence
    does not produce — a caller-authored verdict is never packaged. Two attacks:
    (1) a FLIPPED verdict on the real pack's own report, and (2) a genuinely
    recomputed report from a DIFFERENT (but individually valid) pack. Both are
    blocked BY THE RECOMPUTE, not by an earlier gate — the real pack passes the
    verdict, versioning, attestation-binding and design-hash checks, so the only
    thing left to catch the mismatch is the independent recomputation."""
    from coliseum.textlab.schema import canonical_json

    manifest, out_root, report_path = _recomputable_pack(tmp_path)

    # sanity: the untouched real pack packages cleanly (so any refusal below is
    # attributable to the tamper, not a latent pack defect)
    ok = build_result_package(EID, manifest, out_root, REGISTRY, report_path,
                              _execution_extra(manifest, out_root),
                              config_dir="configs/scenarios")
    verify_result_package(ok)
    os.remove(ok)

    # (1) FORGE the verdict: flip the derived non-rejection to a rejection. The
    # report still carries a verdict and the right version, the attestation
    # still binds THIS manifest, the design still reconstructs — only the
    # recompute can tell the verdict is not what the evidence produces.
    with open(report_path, encoding="utf-8") as fh:
        report = json.load(fh)
    (agent_id,) = tuple(report["per_agent"])
    assert report["per_agent"][agent_id]["verdict"] == \
        "no_distributional_order_effect_observed"
    report["per_agent"][agent_id]["verdict"] = \
        "distributional_order_effect_observed"
    forged_path = os.path.join(out_root, "forged_order_report.json")
    with open(forged_path, "w", encoding="utf-8") as fh:
        fh.write(canonical_json(report) + "\n")
    with pytest.raises(SchemaError, match="independent recomputation"):
        build_result_package(EID, manifest, out_root, REGISTRY, forged_path,
                             {}, config_dir="configs/scenarios")

    # (2) MIS-BIND: a report genuinely recomputed from a DIFFERENT valid pack
    # (different per-unit action law) is handed against THIS pack's evidence.
    # Every non-recompute gate passes; the recompute derives THIS pack's report
    # and finds it unequal, so the mis-bound report is refused.
    _, other_root, other_report = _recomputable_pack(tmp_path, subdir="other",
                                                     law=1)
    assert (canonical_json(json.load(open(other_report, encoding="utf-8")))
            != canonical_json(json.load(open(report_path, encoding="utf-8"))))
    with pytest.raises(SchemaError, match="independent recomputation"):
        build_result_package(EID, manifest, out_root, REGISTRY, other_report,
                             {}, config_dir="configs/scenarios")


def _unfrozen_three_group_pack(tmp_path, subdir="probe3"):
    """The d-006 probe as a REAL buildable pack: the frozen two groups PLUS an
    unfrozen ('v2_probe', 7) group across A/B/C (3 conditions x 3 groups x 24
    sampler seeds = 216 run dirs). Returns (manifest, out_root) with a
    contract-shaped attestation on disk. No recomputed report is written — the
    recompute now REFUSES this shape, which is the point of the test."""
    out_root = str(tmp_path / subdir)
    os.makedirs(out_root)
    run_ids = []
    rows = []
    groups = list(oc.VARIANTS) + [("v2_probe", 7)]   # ('v2_probe', 7) is UNFROZEN
    for cond in ("A", "B", "C"):
        for variant, scen_seed in groups:
            for samp in oc.SAMPLER_SEEDS:
                d = oc._write_unit(out_root, cond, variant, scen_seed, samp,
                                   "share_resource")
                rid = os.path.basename(d)
                run_ids.append(rid)
                rj = os.path.join(d, "run.json")
                with open(rj, encoding="utf-8") as fh:
                    run = json.load(fh)
                run["comparison_regime_id"] = f"regime_{cond}"
                with open(rj, "w", encoding="utf-8") as fh:
                    json.dump(run, fh)
                rows.append({"regime_id": f"regime_{cond}", "model": "",
                             "scenario": oc.CONDITIONS[cond],
                             "scenario_seed": scen_seed, "sampler_seed": samp,
                             "variant_id": variant, "temperature": 0.7,
                             "sampling_mode": "stochastic", "digest": "",
                             "scenario_hash": "",
                             "arbitration": "planner_priority", "run_id": rid,
                             "dir": rid, "reportable": True,
                             "stochastic_reportable": True,
                             "interaction_mode": "sequential_history",
                             "path": ["expose", "share_resource"]})
    manifest = os.path.join(out_root, "manifest.jsonl")
    with open(manifest, "w", encoding="utf-8") as mf:
        for row in rows:
            mf.write(json.dumps(row) + "\n")
    _write_attestation(manifest, out_root, run_ids)
    return manifest, out_root


def test_result_package_refuses_an_unfrozen_group_pack(tmp_path):
    """d-006 (Section D), production seal: a pack carrying an EXTRA unfrozen
    (variant, scenario_seed) group cannot be packaged. build_result_package
    RE-DERIVES the order report with the frozen grid threaded from the verified
    design (frozen_grid_from_design), so the recompute REFUSES the unfrozen group
    — the required matched-unit count is pinned to the pre-registered 48 and is
    never scaled to the 72 the 3-group evidence carries — and the package fails
    closed. The direct recompute refuses identically."""
    from coliseum.textlab.schema import canonical_json
    from coliseum.textlab.result_package import _recompute_order_report

    manifest, out_root = _unfrozen_three_group_pack(tmp_path)
    # a verdict-bearing report on disk; only the recompute can catch the pack
    report_path = os.path.join(out_root, "order_report.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(canonical_json(
            _fake_verdict_report(EXPECTED_CONDITIONS)) + "\n")

    with pytest.raises(SchemaError) as exc:
        build_result_package(EID, manifest, out_root, REGISTRY, report_path,
                             {}, config_dir="configs/scenarios")
    msg = str(exc.value)
    assert "independent recomputation" in msg
    assert "inadmissible" in msg

    att = json.load(open(os.path.join(out_root, "replay_attestation.json"),
                         encoding="utf-8"))
    with pytest.raises(SchemaError) as exc2:
        _recompute_order_report(EID, REGISTRY, manifest, out_root,
                                "configs/scenarios", att)
    assert "inadmissible" in str(exc2.value)
    # nothing was sealed
    assert not os.path.exists(os.path.join(out_root, "result_package.json"))


def test_result_package_refuses_verdictless_report_and_missing_attestation(
        tmp_path, monkeypatch):
    manifest, out_root, report_path = _analyzed_pack(tmp_path, monkeypatch)
    # refusal-shaped report (no verdict) is never packaged
    refusal = {"report_id": "order_sensitivity", "order_report_version": "6",
               "per_agent": {f"llm:ollama:{MODEL}": {
                   "agent_regime_id": "a" * 64, "cells": {}}}}
    bad_report = os.path.join(out_root, "refusal_report.json")
    with open(bad_report, "w", encoding="utf-8") as fh:
        json.dump(refusal, fh)
    with pytest.raises(SchemaError, match="no verdict"):
        build_result_package(EID, manifest, out_root, REGISTRY, bad_report, {})
    # missing attestation refuses
    os.remove(os.path.join(out_root, "replay_attestation.json"))
    with pytest.raises(SchemaError, match="attestation missing"):
        build_result_package(EID, manifest, out_root, REGISTRY,
                             report_path, {})


def test_result_package_refuses_attestation_bound_to_other_manifest(
        tmp_path, monkeypatch):
    manifest, out_root, report_path = _analyzed_pack(tmp_path, monkeypatch)
    att_path = os.path.join(out_root, "replay_attestation.json")
    att = json.load(open(att_path, encoding="utf-8"))
    att["manifest_sha256"] = "0" * 64
    with open(att_path, "w", encoding="utf-8") as fh:
        json.dump(att, fh)
    with pytest.raises(SchemaError, match="does not attest THIS manifest"):
        build_result_package(EID, manifest, out_root, REGISTRY,
                             report_path, {})
