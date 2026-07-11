"""Execute ONE approved task under hard limits, recording its lifecycle.

Consumes a request in state `auto_approved` (policy path) or `approved`
(human path) and drives, via the council event API only:

    EXPERIMENT_STARTED -> <driver runs under wall-clock + storage limits>
    -> EXPERIMENT_COMPLETE -> RESULT_VALIDATION_REQUIRED
    -> RESULT_AUDIT_REQUESTED (+ request file moved back to claimed/ so
       codex_watch --submit --result-audit can find it) -> stop.

The runner NEVER: issues verdicts, approves anything, edits source, retries
past limits, or continues after a failed validation — failures record
AUTONOMY_PAUSED with the exact reasons and stop. Codex must RESULT_APPROVE
the evidence before the task counts as complete.

The experiment configuration is FROZEN: the runner recomputes the sha256 of
the config file and refuses to start unless it equals the request's
autonomy.experiment_config_hash. Bit-for-bit, or it does not run.
"""
from __future__ import annotations

import filecmp
import hashlib
import json
import os
import tempfile
import time

from tools.autonomy import default_roadmap_path, guard
from tools.autonomy import roadmap as roadmap_mod
from tools.council import Config, events, publish, state_machine, storage

SENDER = "claude"

RUNNABLE_STATES = ("auto_approved", "approved")


class RunnerRefusal(Exception):
    """A precondition failed — recorded, never worked around."""


# ------------------------------------------------------------- measurement

def tree_size_mb(path: str) -> float:
    total = 0
    for dirpath, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                pass
    return total / (1024 * 1024)


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


# ----------------------------------------------------------------- drivers

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


# -------------------------------------------------------------- the runner

def _limits(request: dict, task: dict) -> dict:
    """Effective limits: the stricter of the request's autonomy block and
    the roadmap task (a roadmap limit may be stricter than policy, never
    larger — validated at roadmap load)."""
    block = (request.get("autonomy") or {}).get("limits", {})
    wall = min(task["maximum_runtime_minutes"],
               block.get("max_wall_minutes", float("inf")))
    store = min(task["maximum_storage_growth_mb"],
                block.get("max_storage_mb", float("inf")))
    return {"max_wall_minutes": wall, "max_storage_mb": store}


def run_task(cfg: Config, request_id: str, config_path: str,
             roadmap_path: str | None = None) -> int:
    """Returns a process exit code. Every refusal both prints and records
    AUTONOMY_PAUSED (the incident record) before returning nonzero."""
    root = cfg.council_root
    request = publish.read_request(root, request_id)
    repo = request["repository"]
    commit = request["target_commit"]

    def refuse(failures: list) -> int:
        print("runner: REFUSED —")
        for f in failures:
            print(f"  - {f}")
        guard.pause(cfg, request_id, repo, commit, failures)
        print("runner: AUTONOMY_PAUSED recorded; the owner decides next.")
        return 1

    # ---- preflight: emergency stop, chain, policy, roadmap, exact commit
    rm_path = roadmap_path or default_roadmap_path(root)
    pinned_rm = request.get("roadmap_hash")
    report = guard.preflight(cfg, repo=repo, expect_head=commit,
                             roadmap_path=rm_path,
                             pinned_roadmap_hash=pinned_rm)
    if not report.ok:
        return refuse(report.failures)

    state = report.requests.get(request_id, {}).get("state")
    if state not in RUNNABLE_STATES:
        return refuse([f"request {request_id!r} is in state {state!r} — "
                       f"runnable states are {RUNNABLE_STATES}"])

    # ---- frozen experiment configuration, bit-for-bit
    autonomy = request.get("autonomy")
    try:
        config_hash = _sha256_file(config_path)
    except OSError as exc:
        return refuse([f"experiment config unreadable: {exc}"])
    if autonomy is not None and \
            config_hash != str(autonomy["experiment_config_hash"]).replace(
                "sha256:", ""):
        return refuse([
            f"experiment config hash {config_hash[:12]} does not match the "
            "request's frozen experiment_config_hash "
            f"{str(autonomy['experiment_config_hash'])[:19]} — refusing to "
            "run an unaudited configuration"])
    with open(config_path, encoding="utf-8") as fh:
        config = json.load(fh)

    # ---- the task, from the hash-pinned roadmap
    try:
        task = roadmap_mod.task_by_id(report.roadmap, config["task_id"])
    except roadmap_mod.RoadmapError as exc:
        return refuse([str(exc)])
    if task["requires_human"]:
        return refuse([f"task {task['task_id']!r} declares requires_human — "
                       "it never runs autonomously"])
    if task["status"] not in ("ready", "active"):
        return refuse([f"task {task['task_id']!r} status is "
                       f"{task['status']!r} — not runnable"])
    driver_name = task["experiment_class"]
    if config.get("driver") != driver_name:
        return refuse([f"config driver {config.get('driver')!r} != task "
                       f"experiment_class {driver_name!r}"])
    driver = DRIVERS.get(driver_name)
    if driver is None:
        return refuse([f"no driver implemented for {driver_name!r} — "
                       "implementing one is a separately audited change"])
    limits = _limits(request, task)

    # ---- lifecycle: start
    events.append_event(
        root, cfg, "EXPERIMENT_STARTED", SENDER, request_id, repo, commit,
        {"task_id": task["task_id"],
         "experiment_class": driver_name,
         "experiment_config_hash": config_hash,
         "experiment_config_file": os.path.relpath(config_path, repo),
         "roadmap_hash": report.roadmap_hash,
         "policy_hash": report.policy_hash,
         "limits": limits})

    measure_root = os.path.join(repo, config["out_root"])
    size_before = tree_size_mb(measure_root) if os.path.isdir(
        measure_root) else 0.0
    started = time.monotonic()
    deadline = started + limits["max_wall_minutes"] * 60

    try:
        outcome = driver(repo, config, deadline)
    except Exception as exc:
        return refuse([f"driver failed: {exc.__class__.__name__}: {exc}"])

    elapsed_min = (time.monotonic() - started) / 60
    growth_mb = max(0.0, (tree_size_mb(measure_root) if os.path.isdir(
        measure_root) else 0.0) - size_before)
    limit_failures = []
    if elapsed_min > limits["max_wall_minutes"]:
        limit_failures.append(
            f"wall-clock {elapsed_min:.1f} min exceeded the limit "
            f"{limits['max_wall_minutes']} min")
    if growth_mb > limits["max_storage_mb"]:
        limit_failures.append(
            f"storage growth {growth_mb:.1f} MB exceeded the limit "
            f"{limits['max_storage_mb']} MB")
    if limit_failures:
        return refuse(limit_failures)

    # ---- lifecycle: complete + validation
    events.append_event(
        root, cfg, "EXPERIMENT_COMPLETE", SENDER, request_id, repo, commit,
        {"task_id": task["task_id"], "run_id": outcome.get("run_id"),
         "run_dir": outcome.get("run_dir"),
         "final_actions": outcome.get("final_actions"),
         "elapsed_minutes": round(elapsed_min, 3),
         "storage_growth_mb": round(growth_mb, 3)})

    validations = outcome.get("validations", [])
    events.append_event(
        root, cfg, "RESULT_VALIDATION_REQUIRED", SENDER, request_id, repo,
        commit, {"task_id": task["task_id"], "validations": validations})
    failed = [v for v in validations if not v.get("ok")]
    if failed:
        return refuse([f"validation failed: {v['name']}" for v in failed])

    # ---- hand the evidence to Codex for the result audit. submit_verdict
    # requires the request file in claimed/; the initial audit moved it to
    # complete/, so move it back — a protocol file operation, not an edit.
    complete_path = storage.safe_request_path(root, "complete", request_id)
    claimed_path = storage.safe_request_path(root, "claimed", request_id)
    if os.path.exists(complete_path) and not os.path.exists(claimed_path):
        os.rename(complete_path, claimed_path)

    events.append_event(
        root, cfg, "RESULT_AUDIT_REQUESTED", SENDER, request_id, repo, commit,
        {"task_id": task["task_id"], "run_id": outcome.get("run_id"),
         "run_dir": outcome.get("run_dir"), "validations": validations,
         "instructions": ("read-only result audit: verify the evidence dir, "
                          "replay determinism, limits, and validations. "
                          "APPROVED: record RESULT_APPROVED via "
                          "tools.council.cli record (codex role) with the "
                          "verdict as payload; BLOCKED: codex_watch "
                          "--submit <verdict.json> --result-audit")})
    storage.append_log_md(root, "claude", (
        f"**Result audit requested: `{request_id}`** — task "
        f"`{task['task_id']}` ran under AUTO/human approval at `{commit}`.\n\n"
        f"- run_id: `{outcome.get('run_id')}`; evidence: "
        f"`{outcome.get('run_dir')}` (relative to the repo)\n"
        f"- elapsed: {elapsed_min:.2f} min; storage growth: "
        f"{growth_mb:.2f} MB (limits {limits['max_wall_minutes']} min / "
        f"{limits['max_storage_mb']} MB)\n"
        f"- validations: " + ", ".join(
            f"{v['name']}={'ok' if v.get('ok') else 'FAILED'}"
            for v in validations) + "\n\n"
        "Codex: audit the evidence READ-ONLY. APPROVED completes the task — "
        "record it via `python3 -m tools.council.cli --role codex record "
        f"--type RESULT_APPROVED --request-id {request_id} --repository "
        f"{repo} --commit {commit} --payload-json '<verdict JSON>'` "
        "(codex_watch --result-audit cannot submit APPROVED — known council "
        "defect, see docs/AUTONOMY.md). BLOCKED returns the task to the fix "
        "loop via `codex_watch --submit <verdict.json> --result-audit`."))

    print(f"runner: task {task['task_id']} complete pending Codex result "
          f"audit (run {outcome.get('run_id')}, {elapsed_min:.2f} min, "
          f"+{growth_mb:.2f} MB)")
    return 0
