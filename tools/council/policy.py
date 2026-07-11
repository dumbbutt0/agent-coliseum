"""The immutable autonomy policy and its evaluation engine.

The policy file (council/autonomy_policy.json) is created once by a human
via `cli init-policy`, made read-only best-effort, and hash-pinned into the
event chain the first time it is used. Agents may READ it; there is no API
that modifies it, and any hash drift during autonomous operation pauses
autonomy. Policy evaluation — not the human-readable log — is authoritative
for whether an experiment may run without the human gate.

Automatic execution requires ALL conditions to hold (owner amendment):
GO verdict on the exact full commit, clean tree, frozen experiment config
hash, sandbox_local class, synthetic data only, no destructive tools, no
cloud APIs, no website automation, no weight training, pinned model digests,
limits within policy, offline replay supported, verified event chain.
"""
from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass, field

from tools.council import Config, state_machine, storage
from tools.council import events as events_mod
from tools.council import git_state
from tools.council.schemas import (SchemaViolation, payload_hash,
                                   validate_autonomy_block)

POLICY_ID = "coliseum-autonomy-policy-v1"

# capability strings a request's forbidden_actions must explicitly carry
FORBIDDEN_CAPABILITIES = ("destructive_tools", "cloud_apis",
                          "website_automation", "weight_training")

SOCIETY_MILESTONE_CRITERIA = (
    "sequential_history_validated",
    "five_multi_act_scenarios",
    "three_controlled_scenario_families",
    "private_per_agent_observations",
    "deterministic_scheduling",
    "communication_and_reputation",
    "delayed_consequences",
    "replayable_society_run_5_10_agents",
    "final_substrate_audit_go",
)

DEFAULT_POLICY = {
    "policy_id": POLICY_ID,
    "protocol_version": "1.0",
    "created_by": "human",
    "auto_approval": {
        "allowed_experiment_classes": ["sandbox_local"],
        "allowed_data_sources": ["synthetic"],
        "require_go_verdict": True,
        "require_clean_tree": True,
        "forbidden_capabilities": list(FORBIDDEN_CAPABILITIES),
        "limits": {
            "max_compute_minutes": 240,
            "max_wall_minutes": 360,
            "max_storage_mb": 2048,
            "max_retries_per_unit": 2,
            "max_scenarios": 60,
        },
    },
    "bounded_loops": {
        "max_audit_cycles_per_request": 5,
        "max_retries_per_unit": 2,
        "max_consecutive_watcher_errors": 3,
        "allow_scope_expansion": False,
    },
    "protected_paths": ["tools/council/", "autonomy_policy.json",
                        "PROTOCOL.md"],
    "society_milestone": {
        "criteria": list(SOCIETY_MILESTONE_CRITERIA),
        "note": ("On completion: append AUTONOMY_MILESTONE_REACHED, stop "
                 "both watchers, generate an owner briefing. No weight-level "
                 "interventions, public release, cloud testing, or society "
                 "expansion — those require the owner."),
    },
}


@dataclass
class PolicyDecision:
    auto_approve: bool
    policy_hash: str | None
    reasons: list = field(default_factory=list)  # every failed condition
    checked: list = field(default_factory=list)  # every condition evaluated


def write_initial_policy(root: str) -> str:
    """Human-run, once. Refuses to overwrite: the policy is immutable during
    autonomous operation and there is deliberately no update API."""
    path = storage.policy_path(root)
    if os.path.exists(path):
        raise SchemaViolation(
            f"{path} already exists — the autonomy policy is immutable; "
            "pausing autonomy and editing by hand is an owner-only act")
    policy = dict(DEFAULT_POLICY)
    policy["created_utc"] = storage.utc_now()
    storage.atomic_write_json(path, policy)
    try:  # best-effort read-only bit (drvfs may ignore it)
        os.chmod(path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    except OSError:
        pass
    return path


def load_policy(root: str) -> tuple:
    """(policy, policy_hash). Raises SchemaViolation when absent/invalid."""
    path = storage.policy_path(root)
    if not os.path.exists(path):
        raise SchemaViolation(
            "no autonomy policy installed (council/autonomy_policy.json) — "
            "run `cli init-policy` as the owner; until then every "
            "experiment requires the human gate")
    from tools.council.strictjson import loads_strict
    with open(path, "rb") as fh:
        policy = loads_strict(fh.read(), max_bytes=262_144)
    for section in ("auto_approval", "bounded_loops", "protected_paths",
                    "society_milestone"):
        if section not in policy:
            raise SchemaViolation(f"autonomy policy missing {section!r}")
    return policy, payload_hash(policy)


def pinned_policy_hash(chain: list):
    """The hash pinned by the FIRST policy-referencing event in the chain.
    Any later drift means the file changed mid-flight -> pause autonomy."""
    for event in chain:
        h = event.get("payload", {}).get("policy_hash")
        if h:
            return h
    return None


def evaluate(root: str, cfg: Config, request: dict, verdict_event: dict,
             chain: list) -> PolicyDecision:
    """May this GO verdict proceed to AUTO_APPROVED? Fail-closed: every
    exception path and every unmet condition lands in `reasons`, and any
    non-empty `reasons` means the human gate."""
    reasons: list = []
    checked: list = []

    def cond(name: str, ok: bool, why: str = "") -> None:
        checked.append(name)
        if not ok:
            reasons.append(f"{name}: {why}" if why else name)

    # policy file present, valid, and unchanged since first pinned
    policy = policy_hash = None
    try:
        policy, policy_hash = load_policy(root)
    except SchemaViolation as exc:
        cond("policy_installed", False, str(exc))
    if policy is not None:
        pinned = pinned_policy_hash(chain)
        cond("policy_unchanged", pinned is None or pinned == policy_hash,
             "autonomy policy file changed since it was pinned in the chain")

    # emergency stop precedes everything
    stop = storage.emergency_stop_reason(root)
    cond("emergency_stop_clear", stop is None, stop or "")

    # event chain must verify end to end
    report = events_mod.verify_chain(root)
    cond("event_chain_verifies", report.ok, report.error or "")

    # no autonomous continuation after the society milestone
    requests = state_machine.project(chain)
    flags = state_machine.global_flags(requests)
    cond("milestone_not_reached", not flags["milestone_reached"],
         "society milestone reached — autonomous continuation is forbidden")

    # the request itself must declare autonomy (human gate otherwise)
    cond("request_declares_autonomy",
         request.get("human_approval_required") is False,
         "request requires the human gate")
    autonomy = request.get("autonomy")
    try:
        validate_autonomy_block(autonomy)
        cond("autonomy_block_valid", True)
    except SchemaViolation as exc:
        cond("autonomy_block_valid", False, str(exc))
        autonomy = None

    # verdict must be GO (not GO_WITH_CONDITIONS) for the exact full commit
    cond("verdict_is_go", verdict_event.get("event_type") == "AUDIT_GO",
         f"got {verdict_event.get('event_type')}")
    verdict = verdict_event.get("payload", {})
    cond("verdict_commit_exact",
         verdict.get("audited_commit") == request.get("target_commit")
         and verdict_event.get("target_commit") == request.get("target_commit"),
         "audited commit differs from the request's target commit")

    # tree must still be clean at the bound commit
    try:
        repo = request["repository"]
        cond("working_tree_clean", git_state.is_clean(repo, cfg.repo_roots),
             "working tree is dirty")
        cond("head_is_target",
             git_state.head_commit(repo, cfg.repo_roots)
             == request.get("target_commit"),
             "HEAD moved away from the audited commit")
    except Exception as exc:  # fail closed on any git/validation error
        cond("git_state_readable", False, str(exc))

    if policy is not None and autonomy is not None:
        approval = policy["auto_approval"]
        cond("experiment_class_allowed",
             autonomy["experiment_class"]
             in approval["allowed_experiment_classes"],
             autonomy["experiment_class"])
        cond("synthetic_data_only",
             all(s in approval["allowed_data_sources"]
                 for s in autonomy["data_sources"]),
             str(autonomy["data_sources"]))
        forbidden = set(request.get("forbidden_actions", []))
        missing_caps = [c for c in approval["forbidden_capabilities"]
                        if c not in forbidden]
        cond("forbidden_capabilities_declared", not missing_caps,
             f"request must forbid {missing_caps}")
        over = [name for name, cap in approval["limits"].items()
                if autonomy["limits"].get(name, float("inf")) > cap]
        cond("limits_within_policy", not over, f"over policy caps: {over}")
        cond("retries_within_policy",
             autonomy["limits"]["max_retries_per_unit"]
             <= policy["bounded_loops"]["max_retries_per_unit"],
             "max two retries per experimental unit")
        cycles = requests.get(request["request_id"],
                              {"audit_cycles": 0})["audit_cycles"]
        cond("audit_cycles_within_bound",
             cycles <= policy["bounded_loops"]
             ["max_audit_cycles_per_request"],
             f"{cycles} build-audit cycles")
        protected = tuple(policy["protected_paths"])
        touched = [s for s in request.get("scope", [])
                   if any(p in str(s) for p in protected)]
        cond("no_protocol_self_modification", not touched,
             f"scope touches protected paths: {touched} — council protocol "
             "changes require a separate audit and the owner")

    return PolicyDecision(auto_approve=not reasons, policy_hash=policy_hash,
                          reasons=reasons, checked=checked)


# ------------------------------------------------------------ society milestone

def milestone_status(chain: list, policy: dict) -> tuple:
    """(reached, satisfied, missing). Criteria are satisfied by codex-signed
    RESULT_APPROVED / AUDIT_GO events whose payload lists them under
    `milestones_completed` — agents cannot self-certify."""
    criteria = list(policy["society_milestone"]["criteria"])
    satisfied: set = set()
    for event in chain:
        if event["event_type"] in ("RESULT_APPROVED", "AUDIT_GO"):
            for item in event.get("payload", {}).get(
                    "milestones_completed", []):
                if item in criteria:
                    satisfied.add(item)
    missing = set(criteria) - satisfied
    return (not missing, satisfied, missing)
