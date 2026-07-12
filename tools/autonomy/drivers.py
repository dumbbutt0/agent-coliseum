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
import os
import tempfile
import time


class RunnerRefusal(Exception):
    """A precondition or limit failed — recorded, never worked around."""


def _drive_mock(repo: str, config: dict, deadline: float) -> dict:
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


def _drive_ollama_local(repo: str, config: dict, deadline: float) -> dict:
    """ollama_local: a live pinned-digest sweep (coliseum.textlab.sweep.run_sweep
    — the SAME code path as the human `scripts/sweep_models.py`) followed by an
    offline byte-identical replay of EVERY produced run. The frozen config pins
    each model's digest; a served digest that differs is a NEW regime and aborts
    before any compute. The only network egress is the LAN ollama endpoint; the
    killable child caps wall-clock and storage on top of the in-driver deadline.

    Evidence: all runs + the sweep manifest land under one dedicated out_root,
    which the parent runner hashes into the evidence inventory and hands to the
    Codex result audit."""
    from coliseum.textlab.sweep import (SweepAborted, manifest_load,
                                        norm_digest, run_sweep,
                                        verify_run_replay)

    out_root = os.path.join(repo, config["out_root"])
    manifest_path = os.path.join(repo, config["manifest"])
    config_dir = os.path.join(repo, config.get("config_dir",
                                               "configs/scenarios"))
    expected_digests = config.get("model_digests")  # {model: pinned digest}
    spec = {"models": config["models"], "scenarios": config["scenarios"],
            "seeds": config["seeds"],
            "sampler_seeds": config.get("sampler_seeds"),
            "temperature": config.get("temperature", 0.0),
            "arbitration": config.get("arbitration", "planner_priority"),
            "interaction": config.get("interaction", "independent_vignettes"),
            "config_dir": config_dir, "out_root": out_root,
            "manifest": manifest_path}
    try:
        sweep = run_sweep(spec, deadline=deadline,
                          expected_digests=expected_digests)
    except SweepAborted as exc:
        raise RunnerRefusal(str(exc))

    # every row in the final manifest is the full evidence set handed to the
    # auditor — replay-verify all of it, not only this call's fresh runs
    done = manifest_load(manifest_path, out_root)
    run_dirs = sorted({os.path.join(out_root, rec["dir"])
                       for rec in done.values()})
    replay_failures = []
    for d in run_dirs:
        if time.monotonic() > deadline:
            raise RunnerRefusal(
                "wall-clock limit exceeded during replay verification")
        ok, detail = verify_run_replay(d, config_dir)
        if not ok:
            replay_failures.append(f"{os.path.basename(d)}: {detail}")

    expected_runs = config.get("expected_run_count")
    count_ok = expected_runs is None or len(done) == expected_runs

    # honestly recompute (never hardcode) whether every served digest matches
    # its frozen pin — run_sweep's preflight already aborts on a mismatch, so
    # this is True whenever we reach here, but it is COMPUTED evidence
    digest_ok = expected_digests is None or all(
        (not expected_digests.get(m)) or
        norm_digest(dg) == norm_digest(expected_digests[m])
        for m, dg in sweep.digests.items())

    return {
        "run_id": config.get("run_id") or config["task_id"],
        "run_dir": os.path.relpath(out_root, repo),
        "final_actions": [],   # a sweep has no single decision path
        "validations": [
            {"name": "fleet_digests_match_pinned", "ok": digest_ok,
             "served_digests": dict(sweep.digests),
             "note": "computed vs frozen pins (norm_digest); run_sweep also "
                     "aborts before any run on a mismatch"},
            {"name": "sweep_completed_without_errors",
             "ok": not sweep.errors, "errors": sweep.errors},
            {"name": "manifest_run_count", "ok": count_ok,
             "expected": expected_runs, "got": len(done),
             "written_this_call": sweep.rows_written,
             "resumed": sweep.skipped_resumed},
            {"name": "offline_replay_byte_identical",
             "ok": not replay_failures, "failures": replay_failures,
             "runs_checked": len(run_dirs)},
        ],
    }


DRIVERS = {
    "mock_experiment": _drive_mock,
    "ollama_local": _drive_ollama_local,
}
