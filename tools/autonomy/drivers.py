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


DRIVERS = {
    "mock_experiment": _drive_mock,
}
