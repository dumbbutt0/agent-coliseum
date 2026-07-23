"""Experiment drivers, importable by the killable child process
(tools/autonomy/child_runner.py). A driver executes exactly one task's
work inside the child and returns an outcome dict:

    {"run_id", "run_dir" (repo-relative), "final_actions",
     "validations": [{"name", "ok", ...}, ...]}

Drivers never touch the council — lifecycle events belong to the parent
runner. New drivers are separately audited changes.
"""
from __future__ import annotations

import filecmp
import hashlib
import json
import os
import tempfile
import time


class RunnerRefusal(Exception):
    """A precondition or limit failed — recorded, never worked around."""


def _drive_mock(repo: str, config: dict, deadline: float,
                *, execution_context: dict | None = None) -> dict:
    """mock_experiment: fixture-backed LLM run + offline byte-identical
    replay. Deterministic, zero network, synthetic by construction."""
    from coliseum.textlab.runner import run_scenario

    scenario_path = os.path.join(repo, config["scenario"])
    out_root = os.path.join(repo, config["out_root"])
    result = run_scenario(scenario_path, config["agent"],
                          config["scenario_seed"], out_root=out_root)
    if time.monotonic() > deadline:
        raise RunnerRefusal("wall-clock limit exceeded during the run")

    # offline replay gate (same comparison as `cli replay`): re-run from the
    # stored captures into a temp dir, byte-compare decisions.jsonl
    with tempfile.TemporaryDirectory() as tmp:
        replay = run_scenario(scenario_path, result.run.agent_id,
                              result.run.seed, out_root=tmp,
                              replay_from=result.run_dir)
        replay_ok = (replay.run_id == result.run_id and filecmp.cmp(
            os.path.join(result.run_dir, "decisions.jsonl"),
            os.path.join(replay.run_dir, "decisions.jsonl"), shallow=False))

    expected = config.get("expected_final_actions")
    path_ok = expected is None or list(result.final_actions) == list(expected)
    return {
        "run_id": result.run_id,
        "run_dir": os.path.relpath(result.run_dir, repo),
        "final_actions": list(result.final_actions),
        "validations": [
            {"name": "offline_replay_byte_identical", "ok": replay_ok},
            {"name": "expected_final_actions", "ok": path_ok,
             "expected": expected, "got": list(result.final_actions)},
        ],
    }


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: str, body: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(body, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def _drive_ollama_local(repo: str, config: dict, deadline: float,
                        *, execution_context: dict | None = None) -> dict:
    """ollama_local: a live pinned-digest sweep (coliseum.textlab.sweep.run_sweep
    — the SAME code path as the human `scripts/sweep_models.py`) followed by an
    offline byte-identical replay of EVERY produced run. The frozen config pins
    each model's digest; a served digest that differs is a NEW regime and aborts
    before any compute. The only network egress is the LAN ollama endpoint; the
    killable child caps wall-clock and storage on top of the in-driver deadline.

    Evidence: all runs + the sweep manifest land under one dedicated out_root,
    which the parent runner hashes into the evidence inventory and hands to the
    Codex result audit."""
    from coliseum.textlab.sweep import (SweepAborted, SweepUnbalanced,
                                        manifest_load,
                                        norm_digest, run_sweep,
                                        terminal_ledgers_load,
                                        tombstone_ledger_identity,
                                        verify_pack_replay,
                                        verify_run_replay)

    out_root = os.path.join(repo, config["out_root"])
    manifest_path = os.path.join(repo, config["manifest"])
    config_dir = os.path.join(repo, config.get("config_dir",
                                               "configs/scenarios"))
    expected_digests = config.get("model_digests")  # {model: pinned digest}

    # ---- M8 Phase-2 executor fidelity (audit d-001 finding 1, driver side).
    # For a policy-required experiment the frozen registry bundle is the ONLY
    # source of the analysis-critical execution bounds: the driver must load
    # it, must forward max_surviving_delta so run_sweep's balance gate cannot
    # be silently skipped, must honor the preregistered interleaved execution
    # order (recording the realized index), and must preflight the scramble
    # triplet under the imposed-history contract. All of it fails closed —
    # a config or registry that cannot supply a bound refuses before any run.
    sweep_extra = {}
    experiment_id = config.get("experiment_id")
    from coliseum.textlab.registry import POLICY_REQUIRED_EXPERIMENTS
    if experiment_id in POLICY_REQUIRED_EXPERIMENTS:
        from coliseum.textlab.registry import load_verified_bundle
        from coliseum.textlab.sweep import ExecutionPolicy
        from coliseum.textlab.scenario import (lint_scramble_triplet,
                                               load_scenario)
        from coliseum.textlab.schema import SchemaError

        if not config.get("execution_order"):
            raise RunnerRefusal(
                f"{experiment_id}: config declares no execution_order — the "
                "preregistration requires interleaved execution and a driver "
                "default would silently run the historical blocked order")
        registry_path = os.path.join(repo, "configs", "registry",
                                     "experiments.yaml")
        # d-003 finding 0: load a VERIFIED bundle, not a raw design_hash-only
        # load. load_verified_bundle re-checks every value against the audited
        # M8_FROZEN_PROFILE, so a caller-selected --registry that self-rehashes
        # a weakened design refuses here instead of running with lax bounds.
        try:
            bundle = load_verified_bundle(registry_path, experiment_id)
        except (SchemaError, OSError) as exc:
            raise RunnerRefusal(
                f"{experiment_id}: verified frozen bundle unavailable ({exc}) "
                "— the driver never invents execution bounds nor accepts an "
                "unverified (self-rehashed or profile-mismatched) design")

        # scramble-triplet preflight under the imposed-history contract: the
        # three conditions must be matched-except-order BEFORE any model call.
        scenarios = list(config["scenarios"])
        if len(scenarios) != 3:
            raise RunnerRefusal(
                f"{experiment_id}: expected the A/B/C scramble triplet, got "
                f"{scenarios!r}")
        try:
            a, b, c = (load_scenario(
                os.path.join(config_dir, f"{sid}.yaml")) for sid in scenarios)
            preflight = lint_scramble_triplet(
                a, b, c,
                os.path.join(repo, "configs", "registry", "scenarios.yaml"),
                imposed_history=True)
        except (SchemaError, OSError) as exc:
            raise RunnerRefusal(
                f"{experiment_id}: scramble-triplet preflight failed to run "
                f"({exc})")
        if preflight:
            raise RunnerRefusal(
                f"{experiment_id}: scramble-triplet preflight refused: "
                + "; ".join(preflight))
        # b-003 / c-003: build the STRUCTURAL execution policy from the verified
        # bundle. retries_per_unit=0 (durable tombstones, no re-roll) and
        # max_surviving_delta come from the profile-checked frozen design; a
        # missing/nonzero value refuses here, before any provider contact.
        try:
            policy = ExecutionPolicy.from_verified_bundle(
                bundle, execution_order=config["execution_order"],
                record_execution_index=True)
        except SweepAborted as exc:
            raise RunnerRefusal(str(exc))
        sweep_extra = {"execution_policy": policy}

    spec = {"models": config["models"], "scenarios": config["scenarios"],
            "seeds": config["seeds"],
            "sampler_seeds": config.get("sampler_seeds"),
            "temperature": config.get("temperature", 0.0),
            "arbitration": config.get("arbitration", "planner_priority"),
            "interaction": config.get("interaction", "independent_vignettes"),
            "config_dir": config_dir, "out_root": out_root,
            "manifest": manifest_path,
            # experiment_id lets run_sweep detect a policy-required sweep and
            # fail closed if no ExecutionPolicy was supplied.
            "experiment_id": experiment_id}
    try:
        sweep = run_sweep(spec, deadline=deadline,
                          expected_digests=expected_digests, **sweep_extra)
    except SweepUnbalanced as exc:
        if experiment_id not in POLICY_REQUIRED_EXPERIMENTS or \
                exc.completed_result is None:
            raise RunnerRefusal(str(exc))
        # The balance gate is evaluated after all no-reroll failures have been
        # durably tombstoned. Continue only far enough to validate the exact
        # terminal census and emit the canonical inconclusive package below.
        sweep = exc.completed_result
    except SweepAborted as exc:
        raise RunnerRefusal(str(exc))

    # every row in the final manifest is the full evidence set handed to the
    # auditor — replay-verify all of it, not only this call's fresh runs
    done = manifest_load(manifest_path, out_root)
    run_dirs = sorted({os.path.join(out_root, rec["dir"])
                       for rec in done.values()})
    replay_failures = []
    replay_attestation = None
    result_artifacts = None
    if experiment_id in POLICY_REQUIRED_EXPERIMENTS:
        if execution_context is None:
            raise RunnerRefusal(
                f"{experiment_id}: owner-bound execution context is absent")
        if time.monotonic() > deadline:
            raise RunnerRefusal(
                "wall-clock limit exceeded before pack replay")
        try:
            replay_attestation = verify_pack_replay(
                manifest_path, out_root, config_dir,
                registry_path=os.path.join(repo, "configs", "registry",
                                           "experiments.yaml"),
                experiment_id=experiment_id)
        except Exception as exc:
            raise RunnerRefusal(
                f"{experiment_id}: provider-free pack replay refused: {exc}")

        # Close the pack before the parent inventories evidence.  A complete
        # all-success grid receives the frozen order analysis; a complete
        # terminal grid containing durable failures receives a canonical
        # no-statistics inconclusive report.  Any incomplete terminal census
        # refuses rather than pretending the planned pack completed.
        from coliseum.textlab.registry import load_verified_bundle
        from coliseum.textlab.result_package import (
            _recompute_order_report, build_result_package,
            terminal_failure_report, verify_result_package)
        registry_path = os.path.join(repo, "configs", "registry",
                                     "experiments.yaml")
        vb = load_verified_bundle(registry_path, experiment_id)
        rows, tombstones = terminal_ledgers_load(
            manifest_path, out_root, planned_design=vb.planned_design,
            require_tombstone_regime_anchors=True)
        expected = config.get("expected_run_count")
        terminal_count = len(rows) + len(tombstones)
        if terminal_count != expected:
            raise RunnerRefusal(
                f"{experiment_id}: terminal census {terminal_count} != "
                f"frozen planned count {expected}")
        if tombstones:
            report = terminal_failure_report(
                experiment_id, vb.planned_design, rows, tombstones)
        else:
            try:
                report = _recompute_order_report(
                    experiment_id, registry_path, manifest_path, out_root,
                    config_dir, replay_attestation,
                    terminal_snapshot=(rows, tombstones))
            except Exception as exc:
                raise RunnerRefusal(
                    f"{experiment_id}: frozen order report refused: {exc}")
        report_path = os.path.join(out_root, "order_report.json")
        _write_json_atomic(report_path, report)
        extra = {
            "owner_approval_event_id": execution_context.get(
                "owner_approval_event_id"),
            "request_payload_hash": execution_context.get(
                "request_payload_hash"),
            "execution_authorization": execution_context.get(
                "execution_authorization"),
        }
        try:
            package_path = build_result_package(
                experiment_id, manifest_path, out_root, registry_path,
                report_path, extra, config_dir=config_dir)
            package = verify_result_package(package_path)
        except Exception as exc:
            raise RunnerRefusal(
                f"{experiment_id}: result package refused: {exc}")
        result_artifacts = {
            "owner_approval_event_id": extra["owner_approval_event_id"],
            "request_payload_hash": extra["request_payload_hash"],
            "manifest_sha256": _sha256_file(manifest_path),
            "tombstone_ledger": tombstone_ledger_identity(manifest_path),
            "replay_attestation_sha256": _sha256_file(os.path.join(
                out_root, "replay_attestation.json")),
            "order_report_sha256": _sha256_file(report_path),
            "result_package_file_sha256": _sha256_file(package_path),
            "result_package_content_sha256": package["package_sha256"],
            "successful_runs": len(rows),
            "tombstoned_runs": len(tombstones),
            "terminal_outcomes": terminal_count,
            "analysis_status": package["analysis_status"],
        }
    else:
        for d in run_dirs:
            if time.monotonic() > deadline:
                raise RunnerRefusal(
                    "wall-clock limit exceeded during replay verification")
            ok, detail = verify_run_replay(d, config_dir)
            if not ok:
                replay_failures.append(f"{os.path.basename(d)}: {detail}")

    expected_runs = config.get("expected_run_count")
    if experiment_id in POLICY_REQUIRED_EXPERIMENTS:
        count_ok = bool(result_artifacts and
                        result_artifacts["terminal_outcomes"] == expected_runs)
    else:
        count_ok = expected_runs is None or len(done) == expected_runs

    # honestly recompute (never hardcode) whether every served digest matches
    # its frozen pin — run_sweep's preflight already aborts on a mismatch, so
    # this is True whenever we reach here, but it is COMPUTED evidence
    digest_ok = expected_digests is None or all(
        (not expected_digests.get(m)) or
        norm_digest(dg) == norm_digest(expected_digests[m])
        for m, dg in sweep.digests.items())

    validations = [
        {"name": "fleet_digests_match_pinned", "ok": digest_ok,
         "served_digests": dict(sweep.digests),
         "note": "computed vs frozen pins (norm_digest); run_sweep also "
                 "aborts before any run on a mismatch"},
        {"name": ("terminal_outcomes_complete" if experiment_id in
                  POLICY_REQUIRED_EXPERIMENTS else "sweep_completed_without_errors"),
         "ok": (count_ok if experiment_id in POLICY_REQUIRED_EXPERIMENTS
                else not sweep.errors),
         "errors": sweep.errors},
        {"name": "manifest_run_count", "ok": count_ok,
         "expected": expected_runs,
         "got": (result_artifacts["terminal_outcomes"] if result_artifacts
                 else len(done)),
         "written_this_call": sweep.rows_written,
         "resumed": sweep.skipped_resumed},
        {"name": "offline_replay_byte_identical",
         "ok": (replay_attestation is not None if experiment_id in
                POLICY_REQUIRED_EXPERIMENTS else not replay_failures),
         "failures": replay_failures,
         "runs_checked": len(run_dirs)},
    ]
    if result_artifacts is not None:
        validations.append({
            "name": "m8_result_package_verified", "ok": True,
            "analysis_status": result_artifacts["analysis_status"],
            "terminal_outcomes": result_artifacts["terminal_outcomes"],
        })
    return {
        "run_id": config.get("run_id") or config["task_id"],
        "run_dir": os.path.relpath(out_root, repo),
        "final_actions": [],   # a sweep has no single decision path
        "validations": validations,
        "result_artifacts": result_artifacts,
    }


DRIVERS = {
    "mock_experiment": _drive_mock,
    "ollama_local": _drive_ollama_local,
}
