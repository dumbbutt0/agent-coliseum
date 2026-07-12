"""M7d: the autonomous experiment-loop driver.

After the owner's SC-7 amendment activates ollama_local auto-approval, this
driver removes the human from the ROUTINE loop: it selects the next eligible
REGISTERED experiment from the ratified roadmap, publishes its auto-approve run
request, and advances the in-flight one through the states the launcher does not
(go -> policy-continue, auto_approved -> run-task). The Codex launcher still
audits the request and the result; the immutable policy still decides whether it
may auto-run; every safety gate (M7a authority, M7b eligibility, M7c envelope)
still applies. The driver proposes and executes; it never grants authority.

One `advance()` call performs ONE step and is idempotent/resumable — run it on a
timer (or `experiment-loop --once`). It stops itself on MANUAL/STOP or when the
safety envelope halts (those are checked by policy.evaluate, not re-implemented
here).
"""
from __future__ import annotations

import hashlib
import os
import re

import yaml

from tools.council import events, policy, publish, state_machine, storage
from tools.council.schemas import compute_request_payload_hash
from tools.council.strictjson import loads_strict


def _read_json(path: str):
    with open(path, "rb") as fh:
        return loads_strict(fh.read(), max_bytes=1_048_576)

SENDER = "claude"
_EXPERIMENT_DIR = "configs/experiments"
# request ids the loop owns; the experiment_id is embedded so state is derivable
_PREFIX = "autoloop-"


def _sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _load_configs(repo: str) -> dict:
    """experiment_id -> (config_path, config dict) for every committed run
    config under configs/experiments/."""
    out = {}
    cfg_dir = os.path.join(repo, _EXPERIMENT_DIR)
    if not os.path.isdir(cfg_dir):
        return out
    for name in sorted(os.listdir(cfg_dir)):
        if not name.endswith(".experiment.json"):
            continue
        path = os.path.join(cfg_dir, name)
        try:
            cfg = _read_json(path)
        except (OSError, ValueError):
            continue
        eid = cfg.get("experiment_id") if isinstance(cfg, dict) else None
        if eid:
            out[eid] = (path, cfg)
    return out


def _registry(repo: str) -> dict:
    with open(os.path.join(repo, "configs", "registry",
                           "experiments.yaml"), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _terminal_states() -> set:
    """States from which a loop request cannot progress further. An experiment
    with only terminal attempts is NOT in flight."""
    return state_machine.TERMINAL_STATES | {"integrated", "result_approved",
                                            "next_milestone_ready"}


def _attempt_rids(proj: dict, eid: str) -> dict:
    """Every loop request id for this experiment: the base id plus any
    numeric-suffixed re-attempts (autoloop-<eid>, autoloop-<eid>-002, ...).
    The numeric-only suffix keeps 'm6-x' from matching 'm6-x-extra'."""
    base = _PREFIX + eid
    pat = re.compile("^" + re.escape(base) + r"(-\d{3,})?$")
    return {rid: r for rid, r in proj.items() if pat.match(rid)}


def _experiment_in_flight(proj: dict, eid: str, terminal: set) -> bool:
    """True iff any of this experiment's loop attempts is still non-terminal —
    it must be finished before a fresh attempt starts."""
    for _rid, r in _attempt_rids(proj, eid).items():
        state = r.get("state")
        if state is not None and state not in terminal:
            return True
    return False


def next_request_id(proj: dict, eid: str) -> str:
    """The request id for this experiment's NEXT attempt. The base id for a
    first attempt; the lowest free numeric suffix if prior attempts exist
    (they are terminal — _experiment_in_flight already gated on that). The
    append-only chain makes a canceled attempt's id immutable, so a re-attempt
    MUST use a fresh id rather than reopen the terminal one."""
    base = _PREFIX + eid
    existing = _attempt_rids(proj, eid)
    if base not in existing:
        return base
    n = 2
    while f"{base}-{n:03d}" in existing:
        n += 1
    return f"{base}-{n:03d}"


# --- retry safety: a re-attempt must be BOUNDED and REASON-AWARE ------------
# Only a PRE-EXECUTION cancel by the loop may be auto-retried. Owner
# cancellation, rejected results, standing halts, design/audit failures, and an
# exhausted budget must never mint a fresh request id automatically. The
# classification is DERIVED from immutable chain facts (never a self-asserted
# field) so an agent cannot expand its own retry authority.
MAX_ATTEMPTS_PER_EXPERIMENT = 3

# event types that prove an attempt actually EXECUTED (ran live / had a result)
_EXECUTION_EVENTS = frozenset({
    "EXPERIMENT_STARTED", "EXPERIMENT_COMPLETE", "RESULT_VALIDATION_REQUIRED",
    "RESULT_AUDIT_REQUESTED", "RESULT_APPROVED", "RESULT_BLOCKED"})

# reason classes that permit an automatic fresh attempt
_RETRYABLE = frozenset({"initial", "pre_execution_retryable"})


def _ordinal_of(rid: str, eid: str) -> int:
    """1 for the base id, N for autoloop-<eid>-00N."""
    base = _PREFIX + eid
    if rid == base:
        return 1
    m = re.match("^" + re.escape(base) + r"-(\d{3,})$", rid)
    return int(m.group(1)) if m else 1


def _events_for(chain: list, rid: str) -> list:
    return [e for e in chain if e.get("request_id") == rid]


def classify_prior_attempt(chain: list, rid: str, active_halt: bool) -> str:
    """Fail-closed retry classification of a terminal attempt, derived only from
    chain facts. Retryable ONLY when the loop canceled it BEFORE any live
    execution with no active standing halt. Any ambiguity => non-retryable."""
    evs = _events_for(chain, rid)
    if not evs:
        return "other"
    types = [e["event_type"] for e in evs]
    if any(t in _EXECUTION_EVENTS for t in types):
        return "result_stage"                 # it ran or produced a result
    if types[-1] == "AUDIT_BLOCKED":
        return "audit_blocked"                # design/audit failure
    cancels = [e for e in evs if e["event_type"] == "REQUEST_CANCELED"]
    if not cancels:
        return "other"
    if cancels[-1].get("sender") == "human":
        return "owner_directed"               # owner cancellation
    if active_halt:
        return "standing_halt"                # a halt is engaged right now
    return "pre_execution_retryable"          # loop-canceled, pre-execution


def _active_halt(root: str, proj: dict) -> bool:
    flags = state_machine.global_flags(proj)
    return bool(storage.stop_file_present(root)
                or storage.manual_mode_present(root)
                or flags.get("autonomy_paused")
                or flags.get("milestone_reached"))


def plan_reattempt(root: str, repo: str, eid: str):
    """Decide whether experiment `eid` may take a fresh autonomous attempt.
    Returns (request_id, lineage) when permitted, else (None, refusal). The
    lineage records every property the owner requires: prior request id, the
    cancellation/failure event, the reason classification, the attempt ordinal,
    the (unchanged) experiment + design hashes, and the applicable ceiling."""
    configs = _load_configs(repo)
    if eid not in configs:
        return None, {"reason_class": "other", "detail": "no committed config"}
    config_path, config = configs[eid]
    reg = {e["experiment_id"]: e for e in _registry(repo)["experiments"]}
    design_hash = config.get("design_hash")
    registry_design = reg.get(eid, {}).get("design_hash")
    cfg_hash = _sha256_file(config_path)
    ceiling = MAX_ATTEMPTS_PER_EXPERIMENT
    # unchanged experiment + design: the frozen config's design must equal the
    # registry's pre-registered design (the provenance gate also enforces this).
    if registry_design is not None and design_hash != registry_design:
        return None, {"reason_class": "design_changed", "experiment_id": eid,
                      "detail": "config design_hash != registry design_hash"}

    chain = events.read_chain(root)
    proj = state_machine.project(chain)
    attempts = _attempt_rids(proj, eid)
    active_halt = _active_halt(root, proj)

    if not attempts:                          # first attempt ever
        return _PREFIX + eid, {
            "prior_request_id": None, "prior_terminal_event_id": None,
            "reason_class": "initial", "attempt_ordinal": 1,
            "experiment_id": eid, "design_hash": design_hash,
            "prior_design_hash": design_hash, "experiment_config_hash": cfg_hash,
            "retry_ceiling": ceiling}

    prior_rid = max(attempts, key=lambda r: _ordinal_of(r, eid))
    next_ord = _ordinal_of(prior_rid, eid) + 1
    reason = classify_prior_attempt(chain, prior_rid, active_halt)
    prior_evs = _events_for(chain, prior_rid)
    prior_terminal = prior_evs[-1]["event_id"] if prior_evs else None
    base_refusal = {"reason_class": reason, "prior_request_id": prior_rid,
                    "prior_terminal_event_id": prior_terminal,
                    "attempt_ordinal": next_ord, "experiment_id": eid,
                    "retry_ceiling": ceiling}
    if reason not in _RETRYABLE:
        return None, base_refusal
    if next_ord > ceiling:                    # budget exhausted -> escalate
        return None, {**base_refusal, "reason_class": "retry_budget_exhausted"}
    return next_request_id(proj, eid), {
        "prior_request_id": prior_rid, "prior_terminal_event_id": prior_terminal,
        "reason_class": reason, "attempt_ordinal": next_ord,
        "experiment_id": eid, "design_hash": design_hash,
        "prior_design_hash": design_hash, "experiment_config_hash": cfg_hash,
        "retry_ceiling": ceiling}


def select_next_experiment(root: str, repo: str):
    """The next PRE-REGISTERED experiment with a committed config, no IN-FLIGHT
    attempt, and a PERMITTED (bounded, reason-aware) next attempt. Returns
    (experiment_id, config_path) or None. Deterministic (registry order).

    A prior terminal attempt no longer orphans an experiment, but only a
    loop-canceled PRE-EXECUTION attempt within budget is auto-retried
    (plan_reattempt decides). Owner cancellation, rejected results, standing
    halts, design/audit failures, and an exhausted budget are NOT re-selected —
    they need the owner. Eligibility is thus tightened, never loosened."""
    reg = _registry(repo)
    configs = _load_configs(repo)
    proj = state_machine.project(events.read_chain(root))
    terminal = _terminal_states()
    # 1. finish any in-flight experiment before proposing another
    for e in reg["experiments"]:
        eid = e["experiment_id"]
        if e.get("status") != "pre-registered" or eid not in configs:
            continue
        if _experiment_in_flight(proj, eid, terminal):
            return None
    # 2. the first registered experiment whose next attempt is PERMITTED
    for e in reg["experiments"]:
        eid = e["experiment_id"]
        if e.get("status") != "pre-registered" or eid not in configs:
            continue
        rid, _plan = plan_reattempt(root, repo, eid)
        if rid is not None:
            return eid, configs[eid][0]
    return None


def build_autonomy_block(config: dict, config_path: str, roadmap_task: dict) -> dict:
    """A complete, policy-checkable autonomy block for an ollama_local config.
    Limits come from the roadmap task (which validate_roadmap already caps at or
    below the policy) so limits_within_policy holds."""
    return {
        "experiment_class": config["driver"],
        "experiment_config_hash": _sha256_file(config_path),
        "data_sources": ["local_model"],
        "model_digests": dict(config["model_digests"]),
        "limits": {
            "max_compute_minutes": roadmap_task["maximum_runtime_minutes"],
            "max_wall_minutes": roadmap_task["maximum_runtime_minutes"],
            "max_storage_mb": roadmap_task["maximum_storage_growth_mb"],
            "max_retries_per_unit": config.get("retries_per_unit", 0) or 1,
            "max_scenarios": max(config.get("scenario_count", 1), 1),
        },
        "offline_replay_supported": True,
    }


def build_run_request(repo: str, head: str, roadmap_hash: str, eid: str,
                      config_path: str, config: dict,
                      roadmap_task: dict, request_id: str | None = None) -> dict:
    """The auto-approve (human_approval_required: false) run request for a
    registered experiment. The immutable policy re-checks EVERY field before
    AUTO_APPROVED; this is a proposal, not an approval. `request_id` defaults to
    the base id; a re-attempt passes a disambiguated one (next_request_id)."""
    rid = request_id or (_PREFIX + eid)
    rel_config = os.path.relpath(config_path, repo)
    return {
        "request_id": rid, "task_kind": "experiment", "repository": repo,
        "target_commit": head, "originating_blocked_commit": head,
        "protocol_version": "1.0", "require_clean_tree": True,
        "live_experiment_allowed": False, "human_approval_required": False,
        "roadmap_hash": roadmap_hash,
        "experiment_config_file": rel_config,
        "experiment_config_hash": _sha256_file(config_path),
        "autonomy": build_autonomy_block(config, config_path, roadmap_task),
        "expected_test_command": (
            "python3 -m pytest tests/test_textlab_experiment_registry.py "
            "tests/test_textlab_reports_claims.py "
            "tests/test_autonomy_ollama_driver.py "
            "tests/test_m6_experiment_configs.py tests/test_textlab_prereg.py "
            "tests/test_textlab_metrics_freeze.py "
            "tests/test_autonomy_runner.py::test_provenance_gate_blocks_weakened_design_config "
            "tests/test_autonomy_runner.py::test_provenance_gate_skipped_without_design_hash "
            "tests/test_autonomy_runner.py::test_human_approved_without_binding_refused_before_driver "
            "-q"),
        "expected_test_count": 71,
        "requested_verdicts": ["AUDIT_BLOCKED", "AUDIT_GO",
                               "AUDIT_GO_WITH_CONDITIONS"],
        "blockers_addressed": [
            f"Autonomous loop (M7d): registered experiment {eid} "
            f"(design {config.get('design_hash', '')[:12]}) proposed for "
            "auto-approval — binds the frozen config; the immutable policy and "
            "every M7 gate re-check it before any run."],
        "scope": [
            f"Bind + run the frozen config {rel_config} for pre-registered "
            f"experiment {eid}; read-only audit of the binding.",
            "AUTHORIZATION: the run is gated by the immutable policy "
            "(auto-approve iff every condition holds) + run_task; the audit is "
            "read-only."],
        "allowed_actions": [
            "read-only inspection of source, tests, registries, config, chain",
            "run the allowlisted test command (redirect; wait for exit)",
            "run the registry + config lints (read-only) under /tmp",
            "append the structured verdict + log.md mirror via tools/council"],
        "forbidden_actions": [
            "destructive_tools", "cloud_apis", "website_automation",
            "weight_training", "modifying source files or committed evidence",
            "live model GENERATION calls during the audit",
            "running scripts/sweep_models.py or the driver during the audit",
            "touching the live council identity/control records"],
        "questions": [
            f"Does lint_experiment_config report {eid}'s config clean against "
            "its pre-registered design, and does the config hash match?",
            "Is the autonomy block complete and within policy (class, data "
            "source, pinned digests, limits, offline replay)?",
            "Do the allowlisted experiment-subset tests pass at this commit?"],
    }


def publish_next(root, cfg, repo: str, head: str, roadmap, roadmap_hash: str):
    """Select + publish the next eligible experiment's auto-approve request.
    Returns the request_id, or None if nothing is eligible."""
    from tools.autonomy import roadmap as roadmap_mod
    picked = select_next_experiment(root, repo)
    if picked is None:
        return None
    eid, config_path = picked
    config = _read_json(config_path)
    task = roadmap_mod.task_by_id(roadmap, config["task_id"])
    rid, lineage = plan_reattempt(root, repo, eid)
    if rid is None:                 # defense in depth: select already agreed
        return None
    request = build_run_request(repo, head, roadmap_hash, eid, config_path,
                                config, task, request_id=rid)
    # the reattempt lineage is recorded ON-CHAIN (append-only, hash-chained):
    # prior request id, the cancellation/failure event, reason class, ordinal,
    # unchanged experiment + design hashes, and the applicable retry ceiling.
    events.append_event(root, cfg, "BUILD_STARTED", SENDER, rid, repo, head,
                        {"purpose": f"autonomous loop: {eid}",
                         "reattempt": lineage})
    events.append_event(root, cfg, "BUILD_READY", SENDER, rid, repo, head,
                        {"tests": request["expected_test_count"]})
    request["request_payload_hash"] = compute_request_payload_hash(request)
    publish.publish_request(root, cfg, request, autonomous=True)
    return rid


def advance(cfg, roadmap_path=None) -> str:
    """ONE idempotent step of the autonomous loop. Returns a short status.
    Stops itself on STOP/MANUAL; the policy (not this driver) decides whether a
    proposed experiment may auto-run."""
    from tools.autonomy import default_roadmap_path
    from tools.autonomy import cli as autonomy_cli
    from tools.autonomy import roadmap as roadmap_mod
    from tools.autonomy import runner
    import argparse
    root = cfg.council_root
    repo = cfg.repo_roots[0]
    if storage.stop_file_present(root):
        return "stopped: STOP file present"
    if storage.manual_mode_present(root):
        return "manual: MANUAL marker present — auto-approval disabled"
    rm_path = roadmap_path or default_roadmap_path(root)
    roadmap, rm_hash = roadmap_mod.load_roadmap(
        rm_path, policy.load_policy(root)[0])
    import subprocess
    head = subprocess.check_output(["git", "-C", repo, "rev-parse",
                                    "HEAD"]).decode().strip()
    proj = state_machine.project(events.read_chain(root))
    # advance any in-flight loop request first
    for rid, r in proj.items():
        if not rid.startswith(_PREFIX):
            continue
        state = r.get("state")
        if state == "go":
            autonomy_cli.cmd_policy_continue(
                cfg, argparse.Namespace(request_id=rid))
            return f"policy-continue: {rid}"
        if state == "auto_approved":
            cfg_rel = None
            # the runner reads the config path from the request binding
            reqf = publish.read_request(root, rid)
            cfg_path = os.path.join(repo, reqf["experiment_config_file"])
            runner.run_task(cfg, rid, cfg_path, roadmap_path=rm_path)
            return f"run-task: {rid}"
        if state in ("requested", "claimed", "result_audit",
                     "policy_validation", "building", "fixing", "ready",
                     "awaiting_human", "experiment_running"):
            return f"waiting: {rid} at {state}"
        if state == "blocked":
            return f"halted: {rid} BLOCKED — human review"
    # nothing in flight -> propose the next registered experiment
    rid = publish_next(root, cfg, repo, head, roadmap, rm_hash)
    return f"published: {rid}" if rid else "idle: no eligible experiment"
