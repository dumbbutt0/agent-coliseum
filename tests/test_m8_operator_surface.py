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
    # execution discipline + integrity gates travel with the run
    assert captured["kwargs"]["execution_order"] == "interleaved"
    assert captured["kwargs"]["expected_digests"] == {MODEL: DIGEST}
    assert captured["kwargs"]["max_surviving_delta"] == 2


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
          "thresholds": {"permutation_seed": 20260719},
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
