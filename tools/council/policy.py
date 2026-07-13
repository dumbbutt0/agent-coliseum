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

# M7c autonomous safety envelope. Code-defined ceilings (agent-immutable; raising
# them is an audited code change the owner integrates, satisfying "increased
# ceilings require the owner"). The window resets on the owner's most recent
# control action (STATUS_CHANGED / POLICY_AMENDED) — re-asserting control clears
# the counters. auto-approval halts to the human gate when either is exceeded.
AUTO_HALT_CONSECUTIVE_FAILURES = 3      # BLOCKED/PAUSED runs since a success
MAX_AGGREGATE_COMPUTE_MINUTES = 720.0   # rolling autonomous compute budget


def autonomous_safety_metrics(chain: list):
    """(consecutive_failures, aggregate_compute_minutes) for the autonomous
    experiment loop, counted since the owner's most recent control action."""
    start = 0
    for i, e in enumerate(chain):
        if e.get("event_type") in ("STATUS_CHANGED", "POLICY_AMENDED"):
            start = i + 1
    window = chain[start:]
    aggregate = 0.0
    for e in window:
        if e.get("event_type") == "EXPERIMENT_COMPLETE":
            try:
                aggregate += float((e.get("payload") or {}).get(
                    "elapsed_minutes", 0) or 0)
            except (TypeError, ValueError):
                pass
    fails = 0
    for e in reversed(window):
        et = e.get("event_type")
        if et in ("RESULT_BLOCKED", "AUTONOMY_PAUSED"):
            fails += 1
        elif et in ("RESULT_APPROVED", "EXPERIMENT_APPROVED",
                    "CHANGE_INTEGRATED"):
            break
    return fails, aggregate

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


# ---------------------------------------------------------------- versioning
# The policy is immutable EXCEPT through an owner-token-gated POLICY_AMENDED
# event. Every reachable policy state is a CODE-DEFINED version here, so an
# agent can neither edit the file (breaks the effective-pin hash) nor inject an
# arbitrary policy (only these audited versions exist). Version 1 is the
# original pinned policy — it carries NO policy_version field, so absent == 1
# and the live pinned hash is preserved. Version 2 (M7/SC-7) adds ollama_local
# + its registered local data source and nothing else.
def _amended_v2() -> dict:
    v2 = json.loads(json.dumps(DEFAULT_POLICY))
    v2["policy_version"] = 2
    v2["amends"] = 1
    v2["auto_approval"]["allowed_experiment_classes"] = \
        ["sandbox_local", "ollama_local"]
    v2["auto_approval"]["allowed_data_sources"] = ["synthetic", "local_model"]
    return v2


# Version 3 (delegated-authority charter, owner-ratified): adds an
# `owner_delegation` block — the SMALLEST bounded delegation, structural `source`
# work only, Codex-only, Class-A conditions only. It changes NOTHING else, so the
# existing experiment auto-approval is unaffected. Delegation is INERT until the
# owner ratifies this version (the effective pin must be v3); under v1/v2 the pin
# check in `evaluate_delegation` fails closed. The forward-additive ladder is:
# v3 = delegation, v4 = governance activation (delegation RETAINED, see _amended_v4),
# v5 = delegation revocation (delegation disabled; governance kept) — each a
# monotonic forward POLICY_AMENDED, never a rollback.
def _owner_delegation() -> dict:
    return {
        "enabled": True,
        "delegation_id": "coliseum-delegation-structural-source-v1",
        "delegation_schema_version": "1",
        "authorized_task_kinds": ["source"],
        "technical_only": True,
        "required_auditors": ["codex"],
        "authorized_condition_classes": ["A"],
        "max_delegated_integrations_per_owner_action": 25,
    }


def _amended_v3() -> dict:
    v3 = _amended_v2()
    v3["policy_version"] = 3
    v3["amends"] = 2
    v3["owner_delegation"] = _owner_delegation()
    return v3


# Version 4 (A/B/C/D governance, owner-ratified): ADDS a `governance` block to v3
# (delegation stays ENABLED) — the additive next capability. The ladder is
# purely forward-additive: v4 keeps delegation and adds governance; delegation
# REVOCATION moves to the forward version 5 (still forward-only, never a rollback —
# the delegation charter's binding intent; only the version number shifts because
# governance was inserted). governance_v1 defines the A/B/C/D classes, the exactly-six
# Class-D reserved list, the frozen Class-C gate set, and the codex-only quorum. It is
# INERT until the owner ratifies v4; the routing/evaluator consult it only when the
# effective policy is >= v4 with governance enabled.
def _governance_v1() -> dict:
    return {
        "enabled": True,
        "governance_id": "coliseum-governance-abcd-v1",
        "governance_schema_version": "1",
        # A: evaluate_delegation (the v3 envelope). B: codex build->audit, integrate
        # only on a clean GO bound to the exact commit (classification != satisfaction).
        # C: autonomous council, frozen Class-C evaluator. D: owner S/KEY token only.
        "classes": ["A", "B", "C", "D"],
        "unclassified_routes_to": "D",   # absent/invalid matter_class fails closed to D
        "class_d_reserved": [
            "external_publication_under_owner_identity",
            "expenditure_beyond_authorized_budget",
            "irreversible_destruction_of_evidence_or_infrastructure",
            "legal_financial_privacy_or_personal_risk_acceptance",
            "alteration_of_fundamental_mission",
            "modification_of_constitutional_safety_controls",
        ],
        "class_c_gates": [
            "preregistration_and_freshness",
            "evidence_adequacy",
            "reproducibility_replay",
            "independent_replication_2plus",
            "metric_validity",
            "independent_auditor_approval",
            "recorded_dissent_consensus",
        ],
        "required_auditors": ["codex"],   # class-C quorum; fable deferred (inactive)
        "class_c_reconciliation_budget": 2,
    }


def _amended_v4() -> dict:
    v4 = _amended_v3()               # delegation ENABLED carried forward
    v4["policy_version"] = 4
    v4["amends"] = 3
    v4["governance"] = _governance_v1()
    return v4


def _amended_v5() -> dict:
    # forward-only delegation REVOCATION target (delegation disabled; governance kept).
    v5 = _amended_v4()
    v5["policy_version"] = 5
    v5["amends"] = 4
    v5["owner_delegation"] = dict(_owner_delegation(), enabled=False)  # revoked
    return v5


POLICY_VERSIONS = {1: DEFAULT_POLICY, 2: _amended_v2(), 3: _amended_v3(),
                   4: _amended_v4(), 5: _amended_v5()}


_VOLATILE = ("created_utc", "amended_utc")


def _content(policy: dict) -> dict:
    """Policy minus volatile timestamps — the audited semantic content."""
    return {k: v for k, v in policy.items() if k not in _VOLATILE}


def content_hash(policy: dict) -> str:
    return payload_hash(_content(policy))


def policy_version_of(policy: dict) -> int:
    """Absent policy_version == 1 (the original pinned policy predates the
    field); otherwise the declared integer version."""
    v = policy.get("policy_version", 1)
    if not isinstance(v, int) or isinstance(v, bool) or v < 1:
        raise SchemaViolation(f"invalid policy_version {v!r}")
    return v


def is_code_defined_version(policy: dict) -> bool:
    """The live policy's SEMANTIC content must equal a code-defined (audited)
    version — so an owner amendment can only move between reviewed policies,
    never install an arbitrary one."""
    v = policy_version_of(policy)
    return v in POLICY_VERSIONS and \
        content_hash(policy) == content_hash(POLICY_VERSIONS[v])


def effective_policy_pin(chain: list):
    """(hash, version) the policy file must currently match, by walking the
    OWNER-AUTHORIZED amendment chain: the first POLICY_INITIALIZED pins v1, then
    each POLICY_AMENDED advances the pin IFF it binds prev_policy_hash == the
    current pin AND new version == current version + 1 (monotonic). Hashes are
    the FULL file hashes (bare payload_hash, incl. timestamps) so this composes
    with the existing pin. POLICY_AMENDED is human-token-only (verified at
    append), so an agent cannot advance the pin — it cannot expand its own
    authority. A malformed/non-monotonic amendment STOPS the walk (fail closed:
    the pin never advances past an invalid link). (None, None) before any pin."""
    # AUTHORITY IS RE-VALIDATED FROM THE CHAIN, NEVER TRUSTED FROM THE PAYLOAD.
    # The events file is agent-writable, so a POLICY_AMENDED could be present
    # with the wrong sender or a forged/absent token. Two independent gates:
    #   (a) identity replay must succeed — every human token in the chain must
    #       burn in sequence, action-bound; ANY inconsistency fails the whole
    #       walk closed (no amendment honored, fall back to the base v1 pin);
    #   (b) an amendment advances the pin ONLY if it is a human-SENDER event
    #       carrying a human_token (append enforces this, but policy replay must
    #       not depend on append having been the only writer).
    from tools.council import checkpoint, identity
    pin = pinned_policy_hash(chain)
    version = 1 if pin is not None else None
    try:
        identity.replay_identity(chain)
    except Exception:
        return pin, version   # identity chain invalid -> honor no amendment

    # ROOT-ANCHOR the identity: an agent that can write events.jsonl could forge
    # a HUMAN_IDENTITY_INITIALIZED root + a matching forged token, which
    # replay_identity alone would trust. A POLICY_AMENDED is therefore honored
    # ONLY when the root-owned chain-head checkpoint (/etc/coliseum/..., outside
    # any agent's write authority) is provisioned, intact, and pins a prefix
    # that COVERS the identity root — so the root cannot have been fabricated.
    try:
        cp = checkpoint.read_checkpoint()
        cp_intact = cp is not None and checkpoint.verify_checkpoint(chain) is None
    except Exception:
        cp, cp_intact = None, False   # unreadable checkpoint -> fail closed
    first_init = next((i for i, e in enumerate(chain)
                       if e.get("event_type") == "HUMAN_IDENTITY_INITIALIZED"),
                      None)
    root_anchored = bool(cp_intact and first_init is not None
                         and cp["length"] > first_init)

    for e in chain:
        if e.get("event_type") != "POLICY_AMENDED":
            continue
        p = e.get("payload", {}) or {}
        if e.get("sender") != "human" or not p.get("human_token"):
            break   # only an owner-token-authenticated amendment counts
        if not root_anchored:
            break   # amendment requires a root-owned checkpoint over the root
        if pin is None or p.get("prev_policy_hash") != pin:
            break
        nv = p.get("policy_version")
        if not isinstance(nv, int) or isinstance(nv, bool) \
                or nv != version + 1 or not p.get("policy_hash"):
            break
        pin, version = p.get("policy_hash"), nv
    return pin, version


def amend_policy(root: str, target_version: int) -> tuple:
    """Write the code-defined POLICY_VERSIONS[target_version] over the current
    file — the ONLY sanctioned overwrite path, used exclusively by the CLI
    `amend-policy` command alongside recording an owner-token POLICY_AMENDED.
    Verifies the current file's CONTENT is exactly the previous code-defined
    version before writing (fail closed). Returns (prev_hash, new_hash, diff)
    where the hashes are the FULL file hashes (what the event pins)."""
    if target_version not in POLICY_VERSIONS or target_version < 2:
        raise SchemaViolation(f"no amendable policy version {target_version}")
    prev, new = POLICY_VERSIONS[target_version - 1], POLICY_VERSIONS[target_version]
    path = storage.policy_path(root)
    current, prev_hash = load_policy(root)
    if not (policy_version_of(current) == target_version - 1
            and content_hash(current) == content_hash(prev)):
        raise SchemaViolation(
            f"current policy is not code-defined version {target_version - 1} "
            "— refusing to amend from an unknown base")
    written = dict(new, created_utc=current.get("created_utc"),
                   amended_utc=storage.utc_now())
    try:  # the file was made read-only at init; restore write to overwrite
        os.chmod(path, stat.S_IWUSR | stat.S_IRUSR)
    except OSError:
        pass
    storage.atomic_write_json(path, written)
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    except OSError:
        pass
    _new, new_hash = load_policy(root)
    return prev_hash, new_hash, _policy_diff(_content(prev), _content(new))


def restore_policy_version(root: str, version: int) -> None:
    """Roll the policy file back to the code-defined `version`, preserving the
    original created_utc. Used to make `amend-policy` atomic: if recording the
    owner-token POLICY_AMENDED fails (e.g. an invalid token), the file is
    restored so an invalid token leaves BOTH the file and the effective pin at
    the previous version — never a v2 file drifting unpinned."""
    if version not in POLICY_VERSIONS:
        raise SchemaViolation(f"no code-defined policy version {version}")
    path = storage.policy_path(root)
    created = None
    if os.path.exists(path):
        try:
            current, _ = load_policy(root)
            created = current.get("created_utc")
        except SchemaViolation:
            pass
    restored = dict(POLICY_VERSIONS[version])
    if created is not None:
        restored["created_utc"] = created
    try:
        os.chmod(path, stat.S_IWUSR | stat.S_IRUSR)
    except OSError:
        pass
    storage.atomic_write_json(path, restored)
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    except OSError:
        pass


def _policy_diff(old: dict, new: dict) -> dict:
    """Minimal semantic diff of the two auto_approval-bearing policies."""
    diff = {}
    for k in sorted(set(old) | set(new)):
        if old.get(k) != new.get(k):
            diff[k] = {"old": old.get(k), "new": new.get(k)}
    return diff


@dataclass
class PolicyDecision:
    auto_approve: bool
    policy_hash: str | None
    reasons: list = field(default_factory=list)  # every failed condition
    checked: list = field(default_factory=list)  # every condition evaluated


GOVERNANCE_MATTER_CLASSES = ("A", "B", "C", "D")


@dataclass
class GovernanceRoute:
    """The A/B/C/D routing decision for a matter under governance_v1. `matter_class`
    is the EFFECTIVE class after fail-closed guards (deflation is caught: a request
    that touches protected paths or must declare a reserved capability is forced to
    D no matter what the auditor label says). `route` is the handler lane. `active`
    is False when the effective policy has no governance enabled (dormant under
    v1-v3)."""
    active: bool
    matter_class: str                 # effective class A/B/C/D
    declared_class: str | None        # the auditor-emitted matter_class (or None)
    route: str                        # delegation | codex_lifecycle | council | owner
    policy_hash: str | None
    reasons: list = field(default_factory=list)


_ROUTE_OF = {"A": "delegation", "B": "codex_lifecycle", "C": "council", "D": "owner"}


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
        # the file must match the effective pin — the latest OWNER-authorized
        # policy state after walking the POLICY_INITIALIZED + POLICY_AMENDED
        # chain (agents can't record either) — AND be a code-defined version
        eff_hash, eff_version = effective_policy_pin(chain)
        cond("policy_unchanged", eff_hash is None or eff_hash == policy_hash,
             "autonomy policy file changed since it was pinned in the chain")
        try:
            known = is_code_defined_version(policy)
        except SchemaViolation:
            known = False
        cond("policy_is_code_defined_version",
             known and (eff_version is None
                        or policy_version_of(policy) == eff_version),
             "running policy is not the owner-authorized code-defined version")

    # emergency stop precedes everything
    stop = storage.emergency_stop_reason(root)
    cond("emergency_stop_clear", stop is None, stop or "")

    # M7c safety envelope: return-to-manual + runaway/compute auto-halt. These
    # only gate AUTO-approval — the human gate (manual approval) still works.
    cond("auto_approval_enabled", not storage.manual_mode_present(root),
         "council is in manual mode (MANUAL marker present) — auto-approval "
         "disabled; experiments require the human gate")
    fails, aggregate = autonomous_safety_metrics(chain)
    cond("consecutive_failures_within_bound",
         fails < AUTO_HALT_CONSECUTIVE_FAILURES,
         f"{fails} consecutive autonomous failures since the last owner "
         "control action — the loop halts to the human gate pending review")
    cond("aggregate_compute_within_bound",
         aggregate <= MAX_AGGREGATE_COMPUTE_MINUTES,
         f"{aggregate:.0f} min autonomous compute since the last owner control "
         f"action exceeds the {MAX_AGGREGATE_COMPUTE_MINUTES:.0f} min ceiling")

    # event chain must verify end to end
    report = events_mod.verify_chain(root)
    cond("event_chain_verifies", report.healthy,
         report.error or ("torn suffix" if report.suffix_incomplete else ""))

    # the human-authority (S/KEY) chain must replay cleanly — every human token
    # burns in sequence, action-bound. A forged/misbound token anywhere (e.g. a
    # fabricated POLICY_AMENDED) fails this closed, so no auto-approval proceeds.
    from tools.council import identity
    try:
        identity.replay_identity(chain)
        cond("identity_chain_valid", True)
    except Exception as exc:
        cond("identity_chain_valid", False, str(exc))

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


def delegated_integration_count(chain: list) -> int:
    """CONDITIONS_AUTO_SATISFIED events since the owner's most recent control
    action — the delegation budget window (reset by STATUS_CHANGED/POLICY_AMENDED,
    exactly like the compute/failure envelopes)."""
    start = 0
    for i, e in enumerate(chain):
        if e.get("event_type") in ("STATUS_CHANGED", "POLICY_AMENDED"):
            start = i + 1
    return sum(1 for e in chain[start:]
               if e.get("event_type") == "CONDITIONS_AUTO_SATISFIED")


def evaluate_delegation(root: str, cfg: Config, request: dict,
                        verdict_event: dict, chain: list) -> PolicyDecision:
    """May a codex AUDIT_GO_WITH_CONDITIONS on a structural SOURCE task have its
    conditions auto-satisfied under the owner-ratified delegation charter (v3)?
    Fail-closed: every unmet condition lands in `reasons`; any non-empty `reasons`
    means the human CONDITIONS_SATISFIED token is the only unlock. Mirrors
    `evaluate`, reusing its guards; the CLASS-A signal is the CODEX-emitted
    `condition_classes` in the verdict (hash-bound, codex-authored — the builder
    cannot forge it). Delegation is INERT unless the effective policy is the
    owner-ratified v3 with `owner_delegation.enabled`."""
    reasons: list = []
    checked: list = []

    def cond(name: str, ok: bool, why: str = "") -> None:
        checked.append(name)
        if not ok:
            reasons.append(f"{name}: {why}" if why else name)

    policy = policy_hash = None
    try:
        policy, policy_hash = load_policy(root)
    except SchemaViolation as exc:
        cond("policy_installed", False, str(exc))
    deleg = None
    if policy is not None:
        eff_hash, eff_version = effective_policy_pin(chain)
        cond("policy_unchanged", eff_hash is None or eff_hash == policy_hash,
             "autonomy policy file changed since it was pinned in the chain")
        try:
            known = is_code_defined_version(policy)
        except SchemaViolation:
            known = False
        cond("policy_is_code_defined_version",
             known and (eff_version is None
                        or policy_version_of(policy) == eff_version),
             "running policy is not the owner-authorized code-defined version")
        deleg = policy.get("owner_delegation") or {}
        # delegation is INERT until the owner ratifies v3 (>=3, enabled). Under
        # v1/v2 there is no owner_delegation block and this fails closed.
        cond("delegation_active",
             bool(deleg.get("enabled")) and eff_version is not None
             and eff_version >= 3,
             "owner delegation is not active (requires an owner-ratified "
             "delegation-enabled policy version)")

    # emergency stop / manual suspension / runaway envelope (reused; fail-closed)
    stop = storage.emergency_stop_reason(root)
    cond("emergency_stop_clear", stop is None, stop or "")
    cond("delegation_suspension_clear", not storage.manual_mode_present(root),
         "MANUAL marker present — delegated satisfaction is suspended; use the "
         "human CONDITIONS_SATISFIED gate")
    fails, aggregate = autonomous_safety_metrics(chain)
    cond("consecutive_failures_within_bound",
         fails < AUTO_HALT_CONSECUTIVE_FAILURES,
         f"{fails} consecutive autonomous failures since the last owner action")
    cond("aggregate_compute_within_bound",
         aggregate <= MAX_AGGREGATE_COMPUTE_MINUTES,
         f"{aggregate:.0f} min autonomous compute exceeds the ceiling")

    report = events_mod.verify_chain(root)
    cond("event_chain_verifies", report.healthy,
         report.error or ("torn suffix" if report.suffix_incomplete else ""))
    from tools.council import identity
    try:
        identity.replay_identity(chain)
        cond("identity_chain_valid", True)
    except Exception as exc:
        cond("identity_chain_valid", False, str(exc))
    requests = state_machine.project(chain)
    flags = state_machine.global_flags(requests)
    cond("milestone_not_reached", not flags["milestone_reached"],
         "society milestone reached — autonomous continuation is forbidden")

    # the verdict must be a CODEX conditional GO for the exact request commit
    cond("verdict_is_codex_conditional",
         verdict_event.get("event_type") == "AUDIT_GO_WITH_CONDITIONS"
         and verdict_event.get("sender") == "codex",
         f"got {verdict_event.get('event_type')} from "
         f"{verdict_event.get('sender')}")
    verdict = verdict_event.get("payload", {}) or {}
    cond("verdict_commit_exact",
         verdict.get("audited_commit") == request.get("target_commit")
         and verdict_event.get("target_commit") == request.get("target_commit"),
         "audited commit differs from the request's target commit")

    # AUDITOR-EMITTED CLASS-A CLASSIFICATION (the security core): every condition
    # must be codex-classified Class A. condition_classes is part of the codex
    # verdict payload (verdict_payload_hash-bound); the builder cannot forge it.
    classes = verdict.get("condition_classes")
    conditions = verdict.get("conditions", []) or []
    cond("condition_classes_present",
         isinstance(classes, list) and len(conditions) > 0
         and len(classes) == len(conditions),
         "verdict lacks a per-condition auditor classification")
    cond("all_conditions_class_a",
         isinstance(classes, list) and bool(classes)
         and all(c == "A" for c in classes),
         f"not all conditions are auditor-classified Class A: {classes!r}")

    if policy is not None and deleg is not None:
        cond("task_kind_delegated",
             request.get("task_kind") == "source"
             and "source" in (deleg.get("authorized_task_kinds") or []),
             f"task_kind {request.get('task_kind')!r} is not delegated")
        cond("technical_only_delegation", bool(deleg.get("technical_only")),
             "delegation is technical-only")
        cond("required_auditors_met",
             (deleg.get("required_auditors") or []) == ["codex"],
             "this charter is codex-only (Fable quorum deferred)")
        cond("classes_within_charter",
             isinstance(classes, list)
             and set(classes) <= set(deleg.get("authorized_condition_classes")
                                     or []),
             "a condition class is outside the charter's authorized set")
        protected = tuple(policy["protected_paths"])
        # AUTHORITATIVE guard (slice-1 audit HIGH finding 000621): the charter
        # invariant "the delegation cannot be modified from inside the delegated
        # program" must be enforced against the EXACT audited commit's real diff,
        # NOT the builder's free-form scope prose (a benign scope can hide a
        # tools/council change). git_state.changed_paths fails closed on any git
        # error or ambiguous (merge) ancestry, so a raise here => refuse.
        try:
            changed = git_state.changed_paths(
                request["repository"], request["target_commit"], cfg.repo_roots)
            commit_touched = [p for p in changed
                              if any(prot in p for prot in protected)]
            cond("no_protocol_self_modification", not commit_touched,
                 f"audited commit changes protected paths: {commit_touched}")
        except Exception as exc:
            cond("no_protocol_self_modification", False,
                 f"cannot derive the audited commit's changed paths "
                 f"(fail-closed): {exc}")
        # defense in depth: the DECLARED scope must also not name a protected
        # path — a secondary, non-authoritative signal (never the boundary).
        scope_touched = [s for s in request.get("scope", [])
                         if any(p in str(s) for p in protected)]
        cond("scope_declares_no_protected_path", not scope_touched,
             f"scope names protected paths: {scope_touched}")
        forbidden = set(request.get("forbidden_actions", []))
        missing = [c for c in policy["auto_approval"]["forbidden_capabilities"]
                   if c not in forbidden]
        cond("forbidden_capabilities_declared", not missing,
             f"request must forbid {missing}")
        used = delegated_integration_count(chain)
        cap = deleg.get("max_delegated_integrations_per_owner_action", 0)
        cond("delegation_budget_within_bound", used < cap,
             f"{used}/{cap} delegated satisfactions since the last owner action")
        cycles = requests.get(request["request_id"],
                              {"audit_cycles": 0})["audit_cycles"]
        cond("audit_cycles_within_bound",
             cycles <= policy["bounded_loops"]["max_audit_cycles_per_request"],
             f"{cycles} build-audit cycles")

    try:
        repo = request["repository"]
        cond("working_tree_clean", git_state.is_clean(repo, cfg.repo_roots),
             "working tree is dirty")
        cond("head_is_target",
             git_state.head_commit(repo, cfg.repo_roots)
             == request.get("target_commit"),
             "HEAD moved away from the audited commit")
    except Exception as exc:
        cond("git_state_readable", False, str(exc))

    return PolicyDecision(auto_approve=not reasons, policy_hash=policy_hash,
                          reasons=reasons, checked=checked)


# ----------------------------------------------------- A/B/C/D governance routing

_SOURCE_VERDICT_EVENTS = ("AUDIT_GO", "AUDIT_GO_WITH_CONDITIONS", "AUDIT_BLOCKED")


def _authoritative_matter_class(chain: list, rid: str, target: str):
    """The routing matter_class from the VERIFIED chain (read from root by the
    caller): the LAST codex source verdict for this request that is schema +
    payload-hash valid and target-commit bound. Returns (matter_class|None,
    reason|None) — None means fail-closed to D."""
    from tools.council.schemas import (compute_verdict_payload_hash,
                                       validate_verdict, CouncilError)
    verdict_event = None
    for e in chain:
        if e.get("request_id") == rid \
                and e.get("event_type") in _SOURCE_VERDICT_EVENTS \
                and e.get("sender") == "codex":
            verdict_event = e   # last wins
    if verdict_event is None:
        return None, "no codex source verdict for this request in the chain"
    if verdict_event.get("target_commit") != target:
        return None, "verdict target_commit does not bind the request target_commit"
    verdict = verdict_event.get("payload") or {}
    try:
        validate_verdict(verdict, result_audit=False)
    except CouncilError as exc:
        return None, f"chain verdict fails schema validation: {exc}"
    if verdict.get("verdict_payload_hash") != compute_verdict_payload_hash(verdict):
        return None, "chain verdict payload hash mismatch"
    if verdict.get("audited_commit") != target:
        return None, "verdict audited_commit does not bind the request target_commit"
    mc = verdict.get("matter_class")
    if mc not in GOVERNANCE_MATTER_CLASSES:
        return None, f"absent/invalid matter_class ({mc!r})"
    return mc, None


def governance_route(root: str, cfg: Config, request_id: str) -> GovernanceRoute:
    """Route a matter A/B/C/D under governance_v1 (owner-ratified v4+). SELF-
    AUTHENTICATING — it trusts NO caller argument (audit 000708): it re-reads and
    hash-verifies the chain from root, and obtains the request through
    publish.verified_request (which binds the file to the publication event's pinned
    request_payload_hash, so a post-publication mutation fails). The authoritative
    matter_class is the last codex source verdict in the verified chain for the exact
    request/commit. Fail-closed: an unverifiable chain/request, an absent/invalid
    class, a protected-path real-diff, or any implicated/undeclared Class-D predicate
    (all six governance predicates + the legacy capabilities) forces D. Active ONLY
    when the installed policy equals the effective owner-ratified governance-enabled
    pin >= v4 (hash AND version); otherwise dormant (active=False, route=owner).
    A pure, re-runnable function of (root, request_id)."""
    policy = policy_hash = None
    try:
        policy, policy_hash = load_policy(root)
    except SchemaViolation as exc:
        return GovernanceRoute(False, "D", None, "owner", None,
                               [f"policy_installed: {exc}"])
    # F1 (000708): establish chain provenance from root — never a caller argument.
    # Every read/parse/verification failure (incl. a malformed complete record that
    # raises StrictJSONError) fails closed to an owner/D decision (audit 000714 C1),
    # never an uncaught exception.
    try:
        report = events_mod.verify_chain(root)
        if not report.healthy:
            return GovernanceRoute(False, "D", None, "owner", policy_hash,
                                   [f"chain not healthy -> D: "
                                    f"{report.error or 'torn/incomplete suffix'}"])
        chain = events_mod.read_chain(root, verify=True)
    except Exception as exc:
        return GovernanceRoute(False, "D", None, "owner", policy_hash,
                               [f"chain unreadable/unverifiable -> D: {exc}"])
    eff_hash, eff_version = effective_policy_pin(chain)
    try:
        code_defined = is_code_defined_version(policy)
    except SchemaViolation:
        code_defined = False
    gov = policy.get("governance") or {}
    # F3: bind the INSTALLED policy to the effective owner-ratified pin (hash AND
    # version), mirroring evaluate/evaluate_delegation.
    active = (eff_version is not None and eff_version >= 4
              and (eff_hash is None or eff_hash == policy_hash)
              and code_defined and policy_version_of(policy) == eff_version
              and bool(gov.get("enabled")))
    if not active:
        return GovernanceRoute(False, "D", None, "owner", policy_hash,
                               ["governance not active (requires the installed policy "
                                "to equal the owner-ratified governance-enabled pin "
                                ">= v4)"])
    # F2 (000708): the AUTHORITATIVE, hash-verified request — repository, commit,
    # forbidden_actions, allowed_actions all bound to the publication event; a
    # post-publication mutation (stale or recomputed hash) fails here -> D.
    from tools.council import publish
    try:
        request, failures, repo, commit = publish.verified_request(
            root, cfg, request_id)
    except Exception as exc:   # missing/unreadable request file -> fail closed
        return GovernanceRoute(True, "D", None, "owner", policy_hash,
                               [f"request not verifiable -> D: {exc}"])
    if failures:
        return GovernanceRoute(True, "D", None, "owner", policy_hash,
                               ["request not verifiable -> D: " + "; ".join(failures)])

    reasons: list = []
    declared, why = _authoritative_matter_class(chain, request_id, commit)
    effective = declared if declared is not None \
        else (gov.get("unclassified_routes_to") or "D")
    if declared is None:
        reasons.append(f"matter_class not authenticated from chain -> {effective}: {why}")

    # anti-deflation guard 1: a D-touching change can never be A/B/C — verified from
    # the pinned commit's real diff, fail-closed on any verification failure.
    protected = tuple(policy["protected_paths"])
    try:
        changed = git_state.changed_paths(repo, commit, cfg.repo_roots)
        touched = [p for p in changed if any(pr in p for pr in protected)]
        if touched:
            effective = "D"
            reasons.append(f"audited commit changes protected paths -> D: {touched}")
    except Exception as exc:
        effective = "D"
        reasons.append(f"cannot verify the audited commit's changed paths "
                       f"(fail-closed -> D): {exc}")
    # anti-deflation guard 2: the verified request must forbid EVERY one of the six
    # governance Class-D predicates and implicate none in its allowed_actions — plus
    # the legacy experiment capabilities.
    forbidden = set(request.get("forbidden_actions", []))
    allowed = set(request.get("allowed_actions", []))
    reserved_d = list(gov.get("class_d_reserved") or [])
    undeclared_d = [p for p in reserved_d if p not in forbidden]
    implicated_d = [p for p in reserved_d if p in allowed]
    if undeclared_d or implicated_d:
        effective = "D"
        reasons.append(f"Class-D predicate implicated/undeclared -> D "
                       f"(undeclared={undeclared_d}, implicated={implicated_d})")
    missing_legacy = [c for c in policy["auto_approval"]["forbidden_capabilities"]
                      if c not in forbidden]
    if missing_legacy:
        effective = "D"
        reasons.append(f"undeclared legacy reserved capabilities -> D: {missing_legacy}")

    return GovernanceRoute(True, effective, declared, _ROUTE_OF[effective],
                           policy_hash, reasons)


# -------------------------------------------- A/B/C/D governance Class-C evaluator

def council_resolution_exists(chain: list, matter_id: str) -> bool:
    """A matter is already resolved iff the chain carries a COUNCIL_RESOLVED for it."""
    return any(e.get("event_type") == "COUNCIL_RESOLVED"
               and e.get("request_id") == matter_id for e in chain)


def evaluate_class_c(root: str, cfg: Config, resolution_event: dict,
                     chain: list) -> PolicyDecision:
    """May a Class-C matter be resolved (COUNCIL_RESOLVED) under governance_v1's
    FROZEN seven-gate protocol? Self-authenticating and fail-closed: every gate is
    re-derived from the VERIFIED chain (the preregistration, the codex-approved
    evidence, and any dissent are chain events — the builder's resolution payload is
    a set of CLAIMS re-checked here, never trusted). Any unmet gate lands in
    `reasons`; a non-empty `reasons` means the matter stays UNRESOLVED. Insufficient
    auditor quorum leaves the matter unresolved — it NEVER escalates to the owner.
    INERT unless the installed policy equals the effective owner-ratified
    governance-enabled pin (v4+)."""
    from tools.council.schemas import (compute_preregistration_hash,
                                       compute_resolution_hash)
    reasons: list = []
    checked: list = []

    def cond(name: str, ok: bool, why: str = "") -> None:
        checked.append(name)
        if not ok:
            reasons.append(f"{name}: {why}" if why else name)

    policy = policy_hash = None
    try:
        policy, policy_hash = load_policy(root)
    except SchemaViolation as exc:
        cond("policy_installed", False, str(exc))
        return PolicyDecision(False, None, reasons, checked)

    # governance must be ACTIVE on the exact owner-ratified pin (INERT under v3)
    eff_hash, eff_version = effective_policy_pin(chain)
    try:
        code_defined = is_code_defined_version(policy)
    except SchemaViolation:
        code_defined = False
    gov = policy.get("governance") or {}
    cond("governance_active",
         bool(gov.get("enabled")) and eff_version is not None
         and eff_version >= 4 and code_defined
         and (eff_hash is None or eff_hash == policy_hash)
         and policy_version_of(policy) == eff_version,
         "governance is not active on the owner-ratified pin")

    report = events_mod.verify_chain(root)
    cond("event_chain_verifies", report.healthy,
         report.error or ("torn suffix" if report.suffix_incomplete else ""))

    payload = resolution_event.get("payload") or {}
    matter_id = resolution_event.get("request_id")
    cond("resolution_payload_bound",
         payload.get("matter_id") == matter_id
         and payload.get("resolution_hash") == compute_resolution_hash(payload),
         "resolution payload is not self-consistent / matter-bound")
    cond("matter_not_already_resolved",
         not council_resolution_exists(chain, matter_id),
         "matter already has a COUNCIL_RESOLVED")

    # --- gate 1a: the preregistration exists, is claude-authored + hash-valid ---
    prereg_id = payload.get("preregistration_event_id")
    prereg = None
    prereg_index = None
    for i, e in enumerate(chain):
        if e.get("event_id") == prereg_id \
                and e.get("event_type") == "PREREGISTRATION" \
                and e.get("request_id") == matter_id:
            prereg, prereg_index = e, i
    if prereg is None:
        cond("preregistration_present", False,
             "no matching PREREGISTRATION for this matter in the chain")
    else:
        pp = prereg.get("payload") or {}
        cond("preregistration_present",
             prereg.get("sender") == "claude"
             and pp.get("preregistration_hash") == compute_preregistration_hash(pp),
             "preregistration is not a valid claude-authored hash-bound record")

    # --- resolve the cited evidence to codex RESULT_APPROVED chain events ---
    by_id = {e.get("event_id"): (i, e) for i, e in enumerate(chain)}
    cited = payload.get("evidence_approval_event_ids") or []
    evidence = []          # [(index, event, verdict_payload)]
    all_codex_approved = bool(cited)
    for eid in cited:
        pair = by_id.get(eid)
        if pair is None or pair[1].get("event_type") != "RESULT_APPROVED" \
                or pair[1].get("sender") != "codex":
            all_codex_approved = False
            continue
        evidence.append((pair[0], pair[1], pair[1].get("payload") or {}))
    # gate 6: independent auditor approval (codex; no self-audit — the resolver is
    # claude, the approvals are codex). Insufficient quorum -> unresolved, not owner.
    required = gov.get("class_c_required_auditors") or gov.get("required_auditors") \
        or ["codex"]
    cond("independent_auditor_approval",
         all_codex_approved and len(evidence) >= 1 and required == ["codex"],
         "every cited evidence must be an independent codex RESULT_APPROVED "
         "(insufficient quorum leaves the matter UNRESOLVED, never owner)")

    # gate 3: reproducibility replay (integrity) — every deterministic evidence
    # byte-replayed. SEPARATE from replication.
    cond("reproducibility_replay",
         bool(evidence) and all(v.get("replay_result") == "replayed_ok"
                                for _i, _e, v in evidence),
         "every cited evidence must have replay_result == replayed_ok")

    # gate 4: independent replication >= 2 DISTINCT citable experiments.
    distinct_experiments = {v.get("experiment_config_hash")
                            for _i, _e, v in evidence
                            if v.get("experiment_config_hash")}
    cond("independent_replication_2plus", len(distinct_experiments) >= 2,
         f"needs >=2 distinct citable experiments (got "
         f"{len(distinct_experiments)}); replay is not replication")

    # gate 1b: preregistration precedes the evidence + evidence freshness. No
    # evidence may predate the preregistration (backfilling); a sealed inventory
    # must have been committed at preregistration.
    if prereg is not None and evidence:
        pp = prereg.get("payload") or {}
        fresh_ok, fresh_why = True, ""
        for i, _e, v in evidence:
            if i <= prereg_index:
                fresh_ok, fresh_why = False, "evidence predates preregistration"
                break
            if pp.get("freshness_mode") == "sealed_inventory":
                if v.get("evidence_inventory_hash") not in \
                        set(pp.get("sealed_inventory_hashes") or []):
                    fresh_ok = False
                    fresh_why = "evidence inventory not in the sealed precommitment"
                    break
        cond("preregistration_and_freshness", fresh_ok, fresh_why)
    else:
        cond("preregistration_and_freshness", False,
             "cannot establish preregistration+evidence ordering")

    # gate 2: evidence adequacy — summed scenarios_run meets the precommitted size.
    if prereg is not None:
        min_n = (prereg.get("payload") or {}).get("min_sample_size", 0)
        total_n = sum((v.get("counts") or {}).get("scenarios_run", 0)
                      for _i, _e, v in evidence)
        cond("evidence_adequacy", total_n >= min_n and min_n > 0,
             f"sample size {total_n} < precommitted min {min_n}")

    # gate 5: metric validity — the resolution metric equals the PRECOMMITTED metric
    # (no post-hoc metric selection).
    if prereg is not None:
        cond("metric_validity",
             payload.get("metric") == (prereg.get("payload") or {})
             .get("precommitted_metric"),
             "resolution metric differs from the preregistered metric "
             "(post-hoc metric selection)")

    # gate 7: recorded-dissent consensus — an unreconciled codex COUNCIL_DISSENT
    # for the matter BLOCKS (dissent is never averaged or builder-resolved).
    open_dissent = [e for e in chain
                    if e.get("event_type") == "COUNCIL_DISSENT"
                    and e.get("request_id") == matter_id
                    and not (e.get("payload") or {}).get("reconciled", False)]
    cond("recorded_dissent_consensus", not open_dissent,
         f"{len(open_dissent)} unreconciled council dissent(s) block resolution")

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
        # H4 defense in depth: require the codex signature explicitly
        # (RESULT_APPROVED/AUDIT_GO are codex-only in SENDER_ALLOWED, but
        # never rely on that transitively for a milestone claim)
        if event["event_type"] in ("RESULT_APPROVED", "AUDIT_GO") \
                and event.get("sender") == "codex":
            for item in event.get("payload", {}).get(
                    "milestones_completed", []):
                if item in criteria:
                    satisfied.add(item)
    missing = set(criteria) - satisfied
    return (not missing, satisfied, missing)
