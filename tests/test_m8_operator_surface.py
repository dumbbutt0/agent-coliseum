"""M8 Phase-2 operator surface (Builder W4) — replay-pack / order-report /
smoke-pack / result-package, all OFFLINE.

The Director-defined contracts (sweep.verify_pack_replay and the
ORDER_REPORT_VERSION-4 signature of metrics.order_sensitivity_report) are
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
    att = {"attestation_version": "1",
           "verified_utc": "2026-07-19T00:00:00Z",
           "manifest_sha256": _sha256(manifest_path),
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
    return {"report_id": "order_sensitivity", "order_report_version": "4",
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
                "verdict": "no_order_effect_observed",
                "verdict_reason": "offline fake for operator-surface tests"}}}


# ---------------------------------------------------------------- replay-pack

def test_replay_pack_writes_contract_shaped_attestation(tmp_path, monkeypatch,
                                                        capsys):
    manifest, out_root, run_ids = _mk_pack(tmp_path)

    def fake_verify(manifest_path, out_root_arg, config_dir):
        assert manifest_path == manifest and out_root_arg == out_root
        return _write_attestation(manifest_path, out_root_arg, run_ids)[0]

    monkeypatch.setattr(sweep_mod, "verify_pack_replay", fake_verify,
                        raising=False)
    cli.main(["replay-pack", "--manifest", manifest, "--out-root", out_root,
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
        cli.main(["replay-pack", "--manifest", manifest,
                  "--out-root", out_root])
    assert "REPLAY-PACK REFUSED" in str(e.value.code)
    assert not os.path.exists(os.path.join(out_root,
                                           "replay_attestation.json"))


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
                 replay_attestation, terminal_dp_id, surviving_counts):
        captured.update(run_dirs=run_dirs, conditions=conditions,
                        admissibility_policy=admissibility_policy,
                        thresholds=thresholds,
                        replay_attestation=replay_attestation,
                        terminal_dp_id=terminal_dp_id,
                        surviving_counts=surviving_counts)
        # the cli DERIVES the terminal probe from the triplet's unique
        # decision-kind point — for the m8 scenarios that is d_partner
        assert terminal_dp_id == "d_partner"
        return _fake_verdict_report(conditions)

    monkeypatch.setattr(metrics_mod, "order_sensitivity_report", fake_osr)
    cli.main(_order_report_argv(manifest, out_root))
    out = capsys.readouterr().out
    # verdict + reasons printed
    assert "no_order_effect_observed" in out and "VERDICT" in out
    # the report JSON was written
    rp = os.path.join(out_root, "order_report.json")
    assert os.path.isfile(rp)
    report = json.load(open(rp, encoding="utf-8"))
    assert report["order_report_version"] == "4"
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
    captured = {}

    def fake_run_sweep(spec, **kwargs):
        captured["spec"] = spec
        captured["kwargs"] = kwargs
        r = sweep_mod.SweepResult()
        r.rows_written = 6
        return r

    monkeypatch.setattr(sweep_mod, "run_sweep", fake_run_sweep)
    cli.main(["smoke-pack", "--experiment-id", EID, "--scale", "3",
              "--out-root", out_root, "--registry", REGISTRY])
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
    # execution discipline + integrity gates travel with the run
    assert captured["kwargs"]["execution_order"] == "interleaved"
    assert captured["kwargs"]["expected_digests"] == {MODEL: DIGEST}
    assert captured["kwargs"]["max_surviving_delta"] == 2


# ------------------------------------------------------------- result package

def _analyzed_pack(tmp_path, monkeypatch):
    """A pack with attestation + verdict-bearing report on disk."""
    manifest, out_root, run_ids = _mk_pack(tmp_path)
    _write_attestation(manifest, out_root, run_ids)
    report = _fake_verdict_report(EXPECTED_CONDITIONS)
    report_path = os.path.join(out_root, "order_report.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
    return manifest, out_root, report_path


def test_result_package_builds_and_verifies(tmp_path, monkeypatch):
    manifest, out_root, report_path = _analyzed_pack(tmp_path, monkeypatch)
    extra = {"suite_receipt": {"passed": 1766, "skipped": 13,
                               "command": "python3 -m pytest -q"}}
    path = build_result_package(EID, manifest, out_root, REGISTRY,
                                report_path, extra)
    assert path == os.path.join(out_root, "result_package.json")
    pkg = verify_result_package(path)   # raises on any mismatch
    assert pkg["package_version"] == "1"
    assert pkg["experiment_id"] == EID
    # design identity from the registry (not hard-coded: the design may be
    # re-frozen pre-execution by the audit repair loop; the invariant is that
    # the package carries the CURRENT registry entry's reconstructing hash),
    # echoed version from the report
    from coliseum.textlab.registry import _find_entry, design_hash
    entry = _find_entry(REGISTRY, EID)
    assert pkg["design_hash"] == entry["design_hash"]
    assert pkg["design_hash"] == design_hash(entry["planned_design"])
    assert pkg["order_report_version"] == "4"
    assert pkg["verdicts"] == {f"llm:ollama:{MODEL}":
                               "no_order_effect_observed"}
    assert pkg["models"] == [MODEL]
    assert pkg["model_digests"] == {MODEL: DIGEST}
    # every referenced artifact identified by hash
    assert pkg["manifest"]["sha256"] == _sha256(manifest)
    assert pkg["replay_attestation"]["sha256"] == _sha256(
        os.path.join(out_root, "replay_attestation.json"))
    assert pkg["report"]["sha256"] == _sha256(report_path)
    assert len(pkg["runs"]) == 6
    for rec in pkg["runs"].values():
        assert set(rec) == {"run_dir", "replay_ok", "run_json_sha256",
                            "decisions_sha256", "captures_sha256"}
    assert pkg["extra"] == extra
    assert "git_commit" in pkg   # recorded (may be None), never hashed


def test_result_package_refuses_on_tamper(tmp_path, monkeypatch):
    manifest, out_root, report_path = _analyzed_pack(tmp_path, monkeypatch)
    path = build_result_package(EID, manifest, out_root, REGISTRY,
                                report_path, {})
    # 1) tamper the package body itself
    pkg = json.load(open(path, encoding="utf-8"))
    pkg["verdicts"] = {f"llm:ollama:{MODEL}": "order_effect_observed"}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(pkg, fh)
    with pytest.raises(SchemaError, match="content hash mismatch"):
        verify_result_package(path)
    # 2) rebuild clean, then tamper a referenced artifact
    path = build_result_package(EID, manifest, out_root, REGISTRY,
                                report_path, {})
    verify_result_package(path)
    with open(report_path, "a", encoding="utf-8") as fh:
        fh.write("\n")
    with pytest.raises(SchemaError, match="report artifact tampered"):
        verify_result_package(path)


def test_result_package_refuses_verdictless_report_and_missing_attestation(
        tmp_path, monkeypatch):
    manifest, out_root, report_path = _analyzed_pack(tmp_path, monkeypatch)
    # refusal-shaped report (no verdict) is never packaged
    refusal = {"report_id": "order_sensitivity", "order_report_version": "4",
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
