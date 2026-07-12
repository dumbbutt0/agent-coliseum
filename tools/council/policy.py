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


POLICY_VERSIONS = {1: DEFAULT_POLICY, 2: _amended_v2()}


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
