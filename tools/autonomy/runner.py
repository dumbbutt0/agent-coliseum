"""Execute ONE approved task under hard limits, recording its lifecycle.

Consumes a request in state `auto_approved` (policy path) or `approved`
(human path) and drives, via the council event API only:

    EXPERIMENT_STARTED -> <killable child runs the driver under limits>
    -> EXPERIMENT_COMPLETE -> RESULT_VALIDATION_REQUIRED
    -> RESULT_AUDIT_REQUESTED (+ request file moved back to claimed/ so
       codex_watch --submit --result-audit can find it) -> stop.

Audit blocker 1 (2026-07-11): the frozen-config binding is UNCONDITIONAL.
Every invocation — human-approved included — must carry BOTH a frozen
experiment_config_hash and a canonical experiment_config_file in the
request; the --config path must BE that file and its sha256 must equal the
frozen hash, verified before the config is parsed or a driver is selected.

Audit blocker 2 (2026-07-11): all five declared limits are enforced. The
driver runs in a killable child process (tools/autonomy/child_runner.py)
under a hard min(wall, compute) deadline with live storage monitoring —
the parent kills the child on deadline or storage overrun. Scenario and
retry cardinality are validated BEFORE launch.

The runner NEVER: issues verdicts, approves anything, edits source,
retries past limits, or continues after a failed validation — failures
record AUTONOMY_PAUSED with the exact reasons and stop. Codex must
RESULT_APPROVE the evidence before the task counts as complete.
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time

from tools.autonomy import default_roadmap_path, guard
from tools.autonomy import roadmap as roadmap_mod
from tools.autonomy.drivers import DRIVERS, RunnerRefusal
from tools.council import Config, events, publish, storage

SENDER = "claude"

RUNNABLE_STATES = ("auto_approved", "approved")

# the parent checks the child this often; a storage overrun is therefore
# bounded by (poll interval x write rate) past the cap, then killed
_POLL_SECONDS = 0.25

# the tools/ + coliseum/ packages live here — the child imports from this
# root while operating on the (possibly different) request repository
_PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))


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


def build_evidence_manifest(repo: str, run_dir_rel: str, run_id: str):
    """(manifest, inventory_hash) over the produced run_dir (H3): a sorted
    map of relpath -> sha256 for every evidence file, hashed under the
    council:evidence-inventory:v1 domain. Written OUTSIDE the manifested
    tree (a sibling) so writing it never perturbs the pinned bytes; a
    result verdict binds inventory_hash so the auditor proves it audited
    exactly the bytes the runner produced."""
    from tools.council.schemas import domain_hash, EVIDENCE_INVENTORY_DOMAIN
    abs_dir = os.path.join(repo, run_dir_rel)
    files = {}
    if os.path.isdir(abs_dir):
        for dirpath, _dirs, names in os.walk(abs_dir):
            for name in sorted(names):
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, abs_dir)
                files[rel] = _sha256_file(full)
    # the inventory hash covers CONTENT ONLY (run identity + file digests),
    # never wall-clock — two manifests of the same bytes hash identically
    content = {"schema_version": "evidence-manifest.v1", "run_id": run_id,
               "run_dir": run_dir_rel, "file_count": len(files),
               "files": dict(sorted(files.items()))}
    inventory_hash = domain_hash(EVIDENCE_INVENTORY_DOMAIN, content)
    manifest = dict(content, inventory_hash=inventory_hash,
                    generated_utc=storage.utc_now())
    return manifest, inventory_hash


def validation_report_hash(validations) -> str:
    from tools.council.schemas import domain_hash, VALIDATION_REPORT_DOMAIN
    return domain_hash(VALIDATION_REPORT_DOMAIN, validations)


# ------------------------------------------------------- bounded execution

def _kill_tree(proc) -> None:
    """SIGKILL the child's entire process group (it was started in its own
    session), reap the direct child, and wait briefly until the group has
    no signalable members — descendants must never outlive the bound. On
    non-POSIX platforms (unsupported today) only the direct child dies."""
    if os.name == "posix":
        try:
            pgid = os.getpgid(proc.pid)
        except (ProcessLookupError, PermissionError):
            pgid = None
        if pgid is not None:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        proc.kill()
        proc.wait()
        if pgid is not None:
            for _ in range(100):  # ~5 s upper bound; SIGKILL is prompt
                try:
                    os.killpg(pgid, 0)
                except (ProcessLookupError, PermissionError):
                    return
                time.sleep(0.05)
        return
    proc.kill()
    proc.wait()

def _execute_bounded(argv: list, deadline_seconds: float, storage_root: str,
                     storage_cap_mb: float, size_before_mb: float,
                     cwd: str, stdout=None, stderr=None, env=None) -> None:
    """Run argv as a killable child: hard-kill on the wall/compute deadline
    or when monitored storage growth exceeds the cap (audit blocker 2).
    Raises RunnerRefusal with the exact reason on any kill or nonzero exit.

    stdout/stderr: open file handles for long-lived children whose output
    would otherwise fill the PIPE buffers (default keeps the PIPE capture).
    env: a SANITIZED environment for launcher children (default inherits
    the parent environment, unchanged behavior); PYTHONPATH always gains
    cwd so tools/ imports resolve.

    The child runs in its OWN process group (POSIX start_new_session), and
    every kill path kills the WHOLE group — a bounded audit/experiment that
    spawns pytest or probe subprocesses must not outlive its deadline
    through descendants (launcher audit blocker 2, 2026-07-11)."""
    env = dict(os.environ) if env is None else dict(env)
    env["PYTHONPATH"] = cwd + os.pathsep + env.get("PYTHONPATH", "")
    posix = os.name == "posix"
    try:
        proc = subprocess.Popen(
            argv, cwd=cwd,
            stdout=subprocess.PIPE if stdout is None else stdout,
            stderr=subprocess.PIPE if stderr is None else stderr, env=env,
            start_new_session=posix)
    except OSError as exc:
        # a missing/non-executable binary or unusable cwd is a BOUNDED
        # session failure, never an uncaught crash (launcher cycle-2
        # blocker): callers get the same refusal type as any other kill
        raise RunnerRefusal(
            f"failed to launch child {argv[0]!r}: {exc}") from exc
    started = time.monotonic()
    try:
        while True:
            rc = proc.poll()
            if rc is not None:
                break
            if time.monotonic() - started > deadline_seconds:
                _kill_tree(proc)
                raise RunnerRefusal(
                    f"wall/compute deadline {deadline_seconds:.0f}s "
                    "exceeded — child process group killed")
            if os.path.isdir(storage_root):
                growth = tree_size_mb(storage_root) - size_before_mb
                if growth > storage_cap_mb:
                    _kill_tree(proc)
                    raise RunnerRefusal(
                        f"storage growth {growth:.1f} MB exceeded the cap "
                        f"{storage_cap_mb} MB — child process group killed")
            time.sleep(_POLL_SECONDS)
    finally:
        if proc.poll() is None:
            _kill_tree(proc)
    if rc != 0:
        if stderr is None:
            tail = proc.stderr.read().decode("utf-8", "replace")[-500:]
            raise RunnerRefusal(f"child exited {rc}: {tail.strip()}")
        raise RunnerRefusal(f"child exited {rc} (stderr in the log file)")


def _run_driver_bounded(repo: str, config_path: str, driver_name: str,
                        limits: dict, measure_root: str,
                        size_before_mb: float,
                        execution_context: dict | None = None) -> dict:
    """Spawn the child runner under the full limit set; return its outcome."""
    deadline_seconds = 60 * min(limits["max_wall_minutes"],
                                limits["max_compute_minutes"])
    fd, result_file = tempfile.mkstemp(suffix=".json",
                                       prefix="autonomy-outcome-")
    os.close(fd)
    context_file = None
    try:
        argv = [sys.executable, "-m", "tools.autonomy.child_runner",
                "--repo", repo, "--config", config_path,
                "--driver", driver_name,
                "--deadline-seconds", str(deadline_seconds),
                "--result-file", result_file]
        if execution_context is not None:
            fd, context_file = tempfile.mkstemp(
                suffix=".json", prefix="execution-context-")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(execution_context, fh, sort_keys=True)
            argv += ["--execution-context-file", context_file]
        _execute_bounded(argv, deadline_seconds, measure_root,
                         limits["max_storage_mb"], size_before_mb,
                         cwd=_PACKAGE_ROOT)
        from tools.council.strictjson import loads_strict
        with open(result_file, "rb") as fh:
            result = loads_strict(fh.read(), max_bytes=1_048_576)
    finally:
        try:
            os.unlink(result_file)
        except OSError:
            pass
        if context_file is not None:
            try:
                os.unlink(context_file)
            except OSError:
                pass
    if not result.get("ok"):
        raise RunnerRefusal(f"driver failed: {result.get('error')}")
    return result["outcome"]


# ----------------------------------------------------- request root of trust

def verified_request(cfg: Config, request_id: str) -> tuple:
    """(request, failures, authoritative_repo, authoritative_commit).

    Cycle-2 audit blocker: the mutable request file is trusted only after
    schema + event-pinned hash verification. Cycle-3 moved the shared
    routine to tools/council/publish.verified_request so the automatic
    claude_watch path uses the identical root of trust; this wrapper keeps
    the runner/CLI call sites and their pause semantics unchanged."""
    return publish.verified_request(cfg.council_root, cfg, request_id)


# -------------------------------------------------------------- the runner

def _limits(request: dict, task: dict, policy: dict) -> dict:
    """ALL FIVE effective limits (audit blocker 2): the strictest of the
    roadmap task (wall/storage), the request's autonomy block (all five,
    when present), and the immutable policy caps (always)."""
    caps = policy["auto_approval"]["limits"]
    loops = policy["bounded_loops"]
    block = (request.get("autonomy") or {}).get("limits", {})
    owner_budget = (request.get("execution_authorization") or {}).get(
        "budget", {})

    def eff(*values):
        return min(v for v in values if v is not None)

    return {
        "max_wall_minutes": eff(task["maximum_runtime_minutes"],
                                block.get("max_wall_minutes"),
                                owner_budget.get("max_wall_minutes"),
                                caps["max_wall_minutes"]),
        "max_storage_mb": eff(task["maximum_storage_growth_mb"],
                              block.get("max_storage_mb"),
                              owner_budget.get("max_storage_mb"),
                              caps["max_storage_mb"]),
        "max_compute_minutes": eff(block.get("max_compute_minutes"),
                                   owner_budget.get("max_compute_minutes"),
                                   caps["max_compute_minutes"]),
        "max_retries_per_unit": eff(block.get("max_retries_per_unit"),
                                    owner_budget.get("max_retries_per_unit"),
                                    loops["max_retries_per_unit"]),
        "max_scenarios": eff(block.get("max_scenarios"),
                             owner_budget.get("max_scenarios"),
                             caps["max_scenarios"]),
    }


def _verify_execution_authorization(root: str, request_id: str,
                                    request: dict, config: dict,
                                    config_hash: str, limits: dict) -> tuple:
    """Return (failures, approval_event_id) for an owner-bound run.

    The approval event is independently checked at append time.  Rechecking
    here binds the bytes about to execute and the effective limits to that
    event, so direct runner calls cannot substitute a different design,
    model regime, pack size, budget, or evidence root.
    """
    authorization = request.get("execution_authorization")
    from coliseum.textlab.registry import POLICY_REQUIRED_EXPERIMENTS
    policy_required = config.get("experiment_id") in \
        POLICY_REQUIRED_EXPERIMENTS
    if authorization is None:
        if policy_required:
            return ([
                f"{config.get('experiment_id')}: policy-required experiment "
                "has no owner-bound execution_authorization"
            ], None)
        return ([], None)

    from tools.council.schemas import (compute_execution_authorization_hash,
                                       validate_execution_authorization)
    try:
        validate_execution_authorization(authorization)
    except Exception as exc:
        return ([f"execution_authorization invalid: {exc}"], None)

    failures = []
    checks = (
        ("experiment_id", config.get("experiment_id")),
        ("implementation_commit", request.get("target_commit")),
        ("experiment_config_hash", config_hash),
        ("design_hash", config.get("design_hash")),
        ("model_digests", config.get("model_digests")),
        ("planned_runs", config.get("expected_run_count")),
        ("evidence_root", config.get("out_root")),
        ("manifest", config.get("manifest")),
    )
    for name, observed in checks:
        if authorization.get(name) != observed:
            failures.append(
                f"execution_authorization {name} "
                f"{authorization.get(name)!r} != executable value "
                f"{observed!r}")
    budget = authorization["budget"]
    if budget["max_units"] != authorization["planned_runs"]:
        failures.append(
            "owner-bound max_units differs from planned_runs")
    for name, effective in limits.items():
        if effective > budget[name]:
            failures.append(
                f"effective limit {name}={effective} exceeds the "
                f"owner-bound budget {budget[name]}")

    approval = None
    publication = None
    for event in events.read_chain(root):
        if event["request_id"] == request_id and \
                event["event_type"] == "EXPERIMENT_APPROVED":
            approval = event
        if event["request_id"] == request_id and event["event_type"] in \
                ("AUDIT_REQUESTED", "READY_FOR_REAUDIT"):
            publication = event
    if approval is None:
        failures.append("no EXPERIMENT_APPROVED event exists")
    else:
        payload = approval["payload"]
        if publication is None:
            failures.append("request publication event is absent")
        elif publication["payload"].get(
                "execution_authorization_hash") != \
                compute_execution_authorization_hash(authorization):
            failures.append(
                "request publication event does not bind the audited "
                "execution_authorization")
        expected_core = {
            "approval_schema_version": "experiment-approval.v2",
            "approved_by": "human",
            "approval_commit": request["target_commit"],
            "request_payload_hash": request["request_payload_hash"],
            "request_publication_event_id": (
                publication["event_id"] if publication else None),
            "request_publication_event_hash": (
                publication["event_hash"] if publication else None),
            "execution_authorization": authorization,
        }
        observed_core = {
            k: v for k, v in payload.items() if k != "human_token"
        }
        if observed_core != expected_core:
            failures.append(
                "latest EXPERIMENT_APPROVED event does not exactly bind "
                "the audited execution_authorization")
    evidence_abs = os.path.join(request["repository"],
                                authorization["evidence_root"])
    manifest_abs = os.path.join(request["repository"],
                                authorization["manifest"])
    if authorization["resume_from"] is None:
        if os.path.lexists(evidence_abs) or os.path.lexists(manifest_abs):
            failures.append(
                "owner-bound evidence root or manifest already exists before "
                "the initial EXPERIMENT_STARTED event")
    else:
        if not os.path.isdir(evidence_abs) or not (
                os.path.isfile(manifest_abs) or
                os.path.isfile(manifest_abs + ".tombstones.jsonl")):
            failures.append(
                "owner-bound resume requires the existing evidence root and "
                "terminal ledger")
    return failures, (approval["event_id"] if approval else None)


def run_task(cfg: Config, request_id: str, config_path: str,
             roadmap_path: str | None = None) -> int:
    """Returns a process exit code. Every refusal both prints and records
    AUTONOMY_PAUSED (the incident record) before returning nonzero."""
    root = cfg.council_root
    # cycle-2 blocker: trust the request file ONLY after verifying it
    # against the event-pinned hash; pause coordinates come from the event
    request, integrity_failures, repo, commit = verified_request(
        cfg, request_id)

    def refuse(failures: list) -> int:
        print("runner: REFUSED —")
        for f in failures:
            print(f"  - {f}")
        guard.pause(cfg, request_id, repo, commit, failures)
        print("runner: AUTONOMY_PAUSED recorded; the owner decides next.")
        return 1

    if integrity_failures:
        return refuse(integrity_failures)

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

    # ---- frozen experiment configuration, bit-for-bit, EVERY path
    # (audit blocker 1): binding is verified before the config is parsed
    # or a driver selected, human-approved requests included.
    autonomy = request.get("autonomy")
    frozen_hash = (autonomy or {}).get("experiment_config_hash") \
        or request.get("experiment_config_hash")
    frozen_file = request.get("experiment_config_file")
    if not frozen_hash or not frozen_file:
        return refuse([
            "request carries no frozen experiment config binding — every "
            "run (human-approved included) must bind BOTH "
            "experiment_config_hash and experiment_config_file; refusing "
            "before reading any configuration"])
    audited_path = os.path.realpath(os.path.join(repo, frozen_file))
    if os.path.realpath(config_path) != audited_path:
        return refuse([
            f"--config {config_path!r} is not the audited config file "
            f"{frozen_file!r} — the binding is canonical, not by content"])
    try:
        config_hash = _sha256_file(config_path)
    except OSError as exc:
        return refuse([f"experiment config unreadable: {exc}"])
    if config_hash != str(frozen_hash).replace("sha256:", ""):
        return refuse([
            f"experiment config hash {config_hash[:12]} does not match the "
            f"request's frozen experiment_config_hash "
            f"{str(frozen_hash)[:19]} — refusing to run an unaudited "
            "configuration"])
    from tools.council.strictjson import loads_strict
    with open(config_path, "rb") as fh:
        config = loads_strict(fh.read(), max_bytes=1_048_576)

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
    if driver_name not in DRIVERS:
        return refuse([f"no driver implemented for {driver_name!r} — "
                       "implementing one is a separately audited change"])
    limits = _limits(request, task, report.policy)

    authorization_failures, approval_event_id = \
        _verify_execution_authorization(
            root, request_id, request, config, config_hash, limits)
    if authorization_failures:
        return refuse(authorization_failures)

    # ---- pre-launch cardinality (audit blocker 2): declared scenario and
    # retry counts are part of the frozen config and checked BEFORE launch
    cardinality_failures = []
    for field, cap in (("scenario_count", "max_scenarios"),
                       ("retries_per_unit", "max_retries_per_unit")):
        declared = config.get(field)
        if not isinstance(declared, int) or declared < 0:
            cardinality_failures.append(
                f"frozen config must declare {field} as a non-negative int")
        elif declared > limits[cap]:
            cardinality_failures.append(
                f"declared {field} {declared} exceeds the effective limit "
                f"{cap}={limits[cap]}")
    if cardinality_failures:
        return refuse(cardinality_failures)

    # ---- frozen-design provenance gate (audit blocker): the request-pinned
    # experiment_config_hash proves these exact bytes were AUDITED; it does not
    # prove they FAITHFULLY REALIZE the pre-registered design. A config that
    # carries a design_hash must therefore pass lint_experiment_config on the
    # LIVE path — refusing any weakening of the frozen hypothesis (interaction,
    # scenarios, seeds, sampler seeds, temperature, pinned digests, held-out,
    # run-count) before a single model is called. Configs with no design_hash
    # (e.g. the mock pipeline probe) carry no pre-registration to bind.
    # M7b eligibility: a LIVE experiment (ollama_local) MUST bind a registered
    # pre-registration — an unregistered live experiment can never run, so it
    # can never AUTO-run either (the provenance gate is not optional for it).
    if driver_name == "ollama_local" and not config.get("design_hash"):
        return refuse([
            "ollama_local experiments must bind a registered design "
            "(design_hash) that lint_experiment_config validates — an "
            "unregistered live experiment cannot run"])
    if config.get("design_hash"):
        from coliseum.textlab.registry import lint_experiment_config
        registry_path = os.path.join(
            repo, "configs", "registry", "experiments.yaml")
        design_issues = lint_experiment_config(config_path, registry_path, repo)
        if design_issues:
            return refuse([f"frozen-design provenance gate: {i}"
                           for i in design_issues])

    # ---- lifecycle: start
    started_payload = {
        "task_id": task["task_id"],
        "experiment_class": driver_name,
        "experiment_config_hash": config_hash,
        "experiment_config_file": frozen_file,
        "roadmap_hash": report.roadmap_hash,
        "policy_hash": report.policy_hash,
        "limits": limits,
    }
    if request.get("execution_authorization") is not None:
        started_payload.update({
            "owner_approval_event_id": approval_event_id,
            "request_payload_hash": request["request_payload_hash"],
            "execution_authorization": request["execution_authorization"],
        })
    events.append_event(
        root, cfg, "EXPERIMENT_STARTED", SENDER, request_id, repo, commit,
        started_payload)

    measure_root = os.path.join(repo, config["out_root"])
    size_before = tree_size_mb(measure_root) if os.path.isdir(
        measure_root) else 0.0
    started = time.monotonic()

    try:
        execution_context = None
        if request.get("execution_authorization") is not None:
            execution_context = {
                "owner_approval_event_id": approval_event_id,
                "request_payload_hash": request["request_payload_hash"],
                "execution_authorization": request["execution_authorization"],
            }
        driver_args = (repo, config_path, driver_name, limits, measure_root,
                       size_before)
        outcome = (_run_driver_bounded(
            *driver_args, execution_context=execution_context)
            if execution_context is not None else
            _run_driver_bounded(*driver_args))
    except RunnerRefusal as exc:
        return refuse([str(exc)])
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

    # ---- H3 evidence manifest: pin every produced byte BEFORE completion
    run_dir_rel = outcome.get("run_dir")
    run_id = outcome.get("run_id")
    manifest, inventory_hash = build_evidence_manifest(
        repo, run_dir_rel, run_id)
    manifest_file = run_dir_rel.rstrip("/") + ".manifest.json"
    manifest_abs = os.path.join(repo, manifest_file)
    os.makedirs(os.path.dirname(manifest_abs), exist_ok=True)
    storage.atomic_write_json(manifest_abs, manifest)
    validations = outcome.get("validations", [])
    val_report_hash = validation_report_hash(validations)

    # ---- lifecycle: complete + validation
    events.append_event(
        root, cfg, "EXPERIMENT_COMPLETE", SENDER, request_id, repo, commit,
        {"task_id": task["task_id"], "run_id": run_id,
         "run_dir": run_dir_rel,
         "final_actions": outcome.get("final_actions"),
         "evidence_inventory_hash": inventory_hash,
         "validation_report_hash": val_report_hash,
         "manifest_file": manifest_file,
         "elapsed_minutes": round(elapsed_min, 3),
         "storage_growth_mb": round(growth_mb, 3),
         **({"result_artifacts": outcome.get("result_artifacts")}
            if outcome.get("result_artifacts") is not None else {})})

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
        {"task_id": task["task_id"], "run_id": run_id,
         "run_dir": run_dir_rel, "validations": validations,
         "experiment_config_hash": config_hash,
         "evidence_inventory_hash": inventory_hash,
         "manifest_file": manifest_file,
         "validation_report_hash": val_report_hash,
         **({"result_artifacts": outcome.get("result_artifacts")}
            if outcome.get("result_artifacts") is not None else {}),
         "instructions": ("read-only result audit: verify the evidence dir "
                          "against the pinned manifest, replay determinism, "
                          "limits, and validations. The result verdict must "
                          "bind evidence_inventory_hash, validation_report_"
                          "hash, experiment_config_hash, run_id, run_dir, "
                          "replay_result, counts, conclusion_scope. Submit "
                          "via codex_watch --submit <verdict.json> "
                          "--result-audit")})
    storage.append_log_md(root, "claude", (
        f"**Result audit requested: `{request_id}`** — task "
        f"`{task['task_id']}` ran under AUTO/human approval at `{commit}`.\n\n"
        f"- run_id: `{outcome.get('run_id')}`; evidence: "
        f"`{outcome.get('run_dir')}` (relative to the repo)\n"
        f"- elapsed: {elapsed_min:.2f} min; storage growth: "
        f"{growth_mb:.2f} MB (limits {limits['max_wall_minutes']} min / "
        f"{limits['max_storage_mb']} MB, killable-child enforced)\n"
        f"- validations: " + ", ".join(
            f"{v['name']}={'ok' if v.get('ok') else 'FAILED'}"
            for v in validations) + "\n\n"
        "Codex: audit the evidence READ-ONLY, then submit the result "
        "verdict (APPROVED completes the task; BLOCKED returns it to the "
        "fix loop) via `python3 -m tools.council.codex_watch --submit "
        "<verdict.json> --result-audit`."))

    print(f"runner: task {task['task_id']} complete pending Codex result "
          f"audit (run {outcome.get('run_id')}, {elapsed_min:.2f} min, "
          f"+{growth_mb:.2f} MB)")
    return 0
