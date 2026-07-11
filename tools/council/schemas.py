"""Single source of validation truth: event/request/verdict schemas, roles,
canonical JSON, and hashing. All council content is untrusted data — nothing
here ever reaches a shell, and test commands are only COMPARED to an
allowlist, never executed."""
from __future__ import annotations

import hashlib
import json
import os
import re


# ------------------------------------------------------------------ exceptions

class CouncilError(Exception):
    """Base for every protocol violation."""


class SchemaViolation(CouncilError):
    pass


class RoleViolation(CouncilError):
    pass


class ChainError(CouncilError):
    pass


class TransitionError(CouncilError):
    pass


class LockHeld(CouncilError):
    pass


# ----------------------------------------------------------------- event types

EVENT_TYPES = (
    "BUILD_STARTED",
    "BUILD_READY",
    "AUDIT_REQUESTED",
    "AUDIT_CLAIMED",
    "AUDIT_BLOCKED",
    "AUDIT_GO",
    "AUDIT_GO_WITH_CONDITIONS",
    "FIX_STARTED",
    "READY_FOR_REAUDIT",
    "HUMAN_APPROVAL_REQUIRED",
    "EXPERIMENT_APPROVED",
    "EXPERIMENT_STARTED",
    "EXPERIMENT_COMPLETE",
    "REQUEST_CANCELED",
    "WATCHER_ERROR",
    # bounded-autonomy extension (owner amendment): policy-gated automatic
    # approval for explicitly safe sandbox_local experiments
    "POLICY_VALIDATION_REQUIRED",
    "AUTO_APPROVED",
    "RESULT_VALIDATION_REQUIRED",
    "RESULT_AUDIT_REQUESTED",
    "RESULT_APPROVED",
    "RESULT_BLOCKED",
    # launcher extension (owner-ratified 2026-07-11): a GO-audited source
    # candidate is folded into the mainline by fast-forward only; the event
    # records exactly which audited commit master advanced to
    "CHANGE_INTEGRATED",
    "NEXT_MILESTONE_READY",
    "AUTONOMY_PAUSED",
    "AUTONOMY_MILESTONE_REACHED",
)

ROLES = ("claude", "codex", "human")

# Centralized role authority (protocol req 3). claude never submits verdicts
# or opens the gate; codex never records fixes; only human approves/runs.
SENDER_ALLOWED = {
    "BUILD_STARTED": frozenset({"claude"}),
    "BUILD_READY": frozenset({"claude"}),
    "AUDIT_REQUESTED": frozenset({"claude"}),
    "FIX_STARTED": frozenset({"claude"}),
    "READY_FOR_REAUDIT": frozenset({"claude"}),
    "HUMAN_APPROVAL_REQUIRED": frozenset({"claude"}),
    "AUDIT_CLAIMED": frozenset({"codex"}),
    "AUDIT_BLOCKED": frozenset({"codex"}),
    "AUDIT_GO": frozenset({"codex"}),
    "AUDIT_GO_WITH_CONDITIONS": frozenset({"codex"}),
    "EXPERIMENT_APPROVED": frozenset({"human"}),
    # EXPERIMENT_STARTED/COMPLETE: human after the human gate, claude only
    # after AUTO_APPROVED (the state machine enforces which path is live)
    "EXPERIMENT_STARTED": frozenset({"claude", "human"}),
    "EXPERIMENT_COMPLETE": frozenset({"claude", "human"}),
    "REQUEST_CANCELED": frozenset({"claude", "human"}),
    "WATCHER_ERROR": frozenset({"claude", "codex", "human"}),
    "POLICY_VALIDATION_REQUIRED": frozenset({"claude"}),
    "AUTO_APPROVED": frozenset({"claude"}),
    "RESULT_VALIDATION_REQUIRED": frozenset({"claude"}),
    "RESULT_AUDIT_REQUESTED": frozenset({"claude"}),
    "RESULT_APPROVED": frozenset({"codex"}),
    "RESULT_BLOCKED": frozenset({"codex"}),
    "CHANGE_INTEGRATED": frozenset({"claude"}),
    "NEXT_MILESTONE_READY": frozenset({"claude"}),
    "AUTONOMY_PAUSED": frozenset({"claude", "codex", "human"}),
    "AUTONOMY_MILESTONE_REACHED": frozenset({"claude"}),
}

# Events that may still be appended while the emergency stop is engaged —
# exactly the ones that RECORD the stop; everything else is refused.
STOP_EXEMPT_EVENT_TYPES = frozenset({"AUTONOMY_PAUSED", "WATCHER_ERROR"})

VERDICT_EVENT_TYPES = frozenset(
    {"AUDIT_BLOCKED", "AUDIT_GO", "AUDIT_GO_WITH_CONDITIONS"})

EVENT_REQUIRED_FIELDS = (
    "protocol_version", "event_id", "event_type", "request_id", "sender",
    "timestamp_utc", "repository", "target_commit", "payload",
    "previous_event_hash", "event_hash",
)

REQUEST_REQUIRED_FIELDS = (
    "request_id", "protocol_version", "repository", "target_commit",
    "require_clean_tree", "expected_test_command", "expected_test_count",
    "scope", "questions", "allowed_actions", "forbidden_actions",
    "requested_verdicts", "live_experiment_allowed",
    "human_approval_required", "originating_blocked_commit",
    "blockers_addressed", "request_payload_hash",
)

VERDICT_REQUIRED_FIELDS = (
    "request_id", "audited_commit", "audit_mode", "working_tree_clean",
    "tests_observed", "verdict", "summary", "blockers", "conditions",
    "findings", "commands_run", "timestamp_utc", "verdict_payload_hash",
)

# The only test command an audit request may name (never executed here).
ALLOWED_TEST_COMMANDS = ("python3 -m pytest tests/ -q",)

GENESIS_HASH = "0" * 64

_REQUEST_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


# ------------------------------------------------------------- canonical JSON

def canonical_json(obj) -> str:
    """UTF-8, sorted keys, compact separators, NaN refused."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def payload_hash(obj) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def compute_event_hash(event: dict) -> str:
    """sha256 over the canonical event WITHOUT its event_hash field."""
    body = {k: v for k, v in event.items() if k != "event_hash"}
    return payload_hash(body)


def compute_request_payload_hash(request: dict) -> str:
    body = {k: v for k, v in request.items() if k != "request_payload_hash"}
    return payload_hash(body)


def compute_verdict_payload_hash(verdict: dict) -> str:
    body = {k: v for k, v in verdict.items() if k != "verdict_payload_hash"}
    return payload_hash(body)


# ------------------------------------------------------------------ validators

def validate_request_id(request_id) -> str:
    """Lowercase slug only: kills path traversal, separators, and Windows
    case-insensitivity collisions in one rule."""
    if not isinstance(request_id, str) or not _REQUEST_ID_RE.match(request_id):
        raise SchemaViolation(
            f"invalid request_id {request_id!r} — must match "
            "^[a-z0-9][a-z0-9-]{2,63}$")
    return request_id


def validate_commit(commit) -> str:
    """Full 40-hex only; abbreviated hashes are refused."""
    if not isinstance(commit, str) or not _COMMIT_RE.match(commit):
        raise SchemaViolation(
            f"invalid commit {commit!r} — full 40-hex sha required "
            "(abbreviations refused)")
    return commit


def validate_repository(repository, repo_roots) -> str:
    """The repository must resolve inside a configured root."""
    if not isinstance(repository, str) or not repository:
        raise SchemaViolation("repository must be a non-empty string")
    real = os.path.realpath(repository)
    for root in repo_roots:
        root_real = os.path.realpath(root)
        if real == root_real or real.startswith(root_real + os.sep):
            return repository
    raise SchemaViolation(
        f"repository {repository!r} is outside the configured roots")


def validate_sender(event_type: str, sender: str) -> None:
    if event_type not in SENDER_ALLOWED:
        raise SchemaViolation(f"unknown event_type {event_type!r}")
    if sender not in ROLES:
        raise RoleViolation(f"unknown sender role {sender!r}")
    if sender not in SENDER_ALLOWED[event_type]:
        raise RoleViolation(
            f"role {sender!r} may not emit {event_type} "
            f"(allowed: {sorted(SENDER_ALLOWED[event_type])})")


def validate_event(event: dict) -> None:
    missing = [f for f in EVENT_REQUIRED_FIELDS if f not in event]
    if missing:
        raise SchemaViolation(f"event missing required fields: {missing}")
    validate_sender(event["event_type"], event["sender"])
    validate_request_id(event["request_id"])
    validate_commit(event["target_commit"])
    if event["protocol_version"] != protocol_version():
        raise SchemaViolation(
            f"protocol_version {event['protocol_version']!r} unsupported")
    if not isinstance(event["payload"], dict):
        raise SchemaViolation("event payload must be an object")
    if compute_event_hash(event) != event["event_hash"]:
        raise ChainError(
            f"event {event.get('event_id')!r}: event_hash does not match "
            "canonical content")


def validate_request(request: dict, repo_roots) -> None:
    if not isinstance(request, dict):
        raise SchemaViolation("request must be an object")
    missing = [f for f in REQUEST_REQUIRED_FIELDS if f not in request]
    if missing:
        raise SchemaViolation(f"request missing required fields: {missing}")
    validate_request_id(request["request_id"])
    validate_commit(request["target_commit"])
    validate_commit(request["originating_blocked_commit"])
    validate_repository(request["repository"], repo_roots)
    if request["protocol_version"] != protocol_version():
        raise SchemaViolation("unsupported request protocol_version")
    if request["require_clean_tree"] is not True:
        raise SchemaViolation("require_clean_tree must be true")
    if request["live_experiment_allowed"] is not False:
        raise SchemaViolation("live_experiment_allowed must be false")
    # human_approval_required may be false ONLY for a policy-eligible
    # sandbox_local experiment carrying a complete autonomy block; the
    # autonomy policy still has final say at POLICY_VALIDATION time.
    if request["human_approval_required"] is not True:
        if request["human_approval_required"] is not False:
            raise SchemaViolation("human_approval_required must be a bool")
        validate_autonomy_block(request.get("autonomy"))
    if request["expected_test_command"] not in ALLOWED_TEST_COMMANDS:
        raise SchemaViolation(
            f"expected_test_command {request['expected_test_command']!r} "
            f"not in allowlist {ALLOWED_TEST_COMMANDS}")
    if not isinstance(request["expected_test_count"], int) \
            or request["expected_test_count"] <= 0:
        raise SchemaViolation("expected_test_count must be a positive int")
    for list_field in ("scope", "questions", "allowed_actions",
                       "forbidden_actions", "requested_verdicts",
                       "blockers_addressed"):
        if not isinstance(request[list_field], list) or not request[list_field]:
            raise SchemaViolation(f"{list_field} must be a non-empty list")
    for v in request["requested_verdicts"]:
        if v not in VERDICT_EVENT_TYPES:
            raise SchemaViolation(f"requested verdict {v!r} is not a "
                                  "verdict event type")
    want = compute_request_payload_hash(request)
    if request["request_payload_hash"] != want:
        raise SchemaViolation("request_payload_hash does not match content")


AUDIT_VERDICT_VALUES = ("BLOCKED", "GO", "GO_WITH_CONDITIONS")
RESULT_VERDICT_VALUES = ("APPROVED", "BLOCKED")


def validate_verdict(verdict: dict, result_audit: bool = False) -> None:
    """Source audits verdict in AUDIT_VERDICT_VALUES; result audits in
    RESULT_VERDICT_VALUES. Both share the same required fields and hash."""
    if not isinstance(verdict, dict):
        raise SchemaViolation("verdict must be an object")
    missing = [f for f in VERDICT_REQUIRED_FIELDS if f not in verdict]
    if missing:
        raise SchemaViolation(f"verdict missing required fields: {missing}")
    validate_request_id(verdict["request_id"])
    validate_commit(verdict["audited_commit"])
    allowed = RESULT_VERDICT_VALUES if result_audit else AUDIT_VERDICT_VALUES
    if verdict["verdict"] not in allowed:
        kind = "result" if result_audit else "audit"
        raise SchemaViolation(
            f"unknown {kind} verdict {verdict['verdict']!r} "
            f"(allowed: {allowed})")
    if not isinstance(verdict["working_tree_clean"], bool):
        raise SchemaViolation("working_tree_clean must be a bool")
    if not isinstance(verdict["tests_observed"], int):
        raise SchemaViolation("tests_observed must be an int")
    want = compute_verdict_payload_hash(verdict)
    if verdict["verdict_payload_hash"] != want:
        raise SchemaViolation("verdict_payload_hash does not match content")


AUTONOMY_BLOCK_REQUIRED_FIELDS = (
    "experiment_class", "experiment_config_hash", "data_sources",
    "model_digests", "limits", "offline_replay_supported",
)

AUTONOMY_LIMIT_FIELDS = (
    "max_compute_minutes", "max_wall_minutes", "max_storage_mb",
    "max_retries_per_unit", "max_scenarios",
)

_SHA256_RE = re.compile(r"^(sha256:)?[0-9a-f]{64}$")


def validate_autonomy_block(autonomy) -> None:
    """A request may only skip the human gate with a complete, pinned,
    sandbox_local autonomy declaration. The policy engine re-checks all of
    this (and more) against the immutable policy file before AUTO_APPROVED."""
    if not isinstance(autonomy, dict):
        raise SchemaViolation(
            "human_approval_required: false requires an autonomy block")
    missing = [f for f in AUTONOMY_BLOCK_REQUIRED_FIELDS if f not in autonomy]
    if missing:
        raise SchemaViolation(f"autonomy block missing fields: {missing}")
    if autonomy["experiment_class"] != "sandbox_local":
        raise SchemaViolation(
            "autonomy is only defined for experiment_class 'sandbox_local'")
    if not _SHA256_RE.match(str(autonomy["experiment_config_hash"])):
        raise SchemaViolation(
            "experiment_config_hash must be a frozen sha256 hex digest")
    sources = autonomy["data_sources"]
    if not isinstance(sources, list) or not sources or \
            any(s != "synthetic" for s in sources):
        raise SchemaViolation("autonomy data_sources must be ['synthetic']")
    digests = autonomy["model_digests"]
    if not isinstance(digests, dict) or not digests or \
            any(not _SHA256_RE.match(str(d)) for d in digests.values()):
        raise SchemaViolation(
            "model_digests must pin every model to a sha256 digest")
    limits = autonomy["limits"]
    if not isinstance(limits, dict):
        raise SchemaViolation("autonomy limits must be an object")
    lim_missing = [f for f in AUTONOMY_LIMIT_FIELDS if f not in limits]
    if lim_missing:
        raise SchemaViolation(f"autonomy limits missing: {lim_missing}")
    for name in AUTONOMY_LIMIT_FIELDS:
        value = limits[name]
        if not isinstance(value, (int, float)) or isinstance(value, bool) \
                or value <= 0:
            raise SchemaViolation(f"autonomy limit {name} must be > 0")
    if autonomy["offline_replay_supported"] is not True:
        raise SchemaViolation("offline_replay_supported must be true for "
                              "autonomous execution")


VERDICT_TO_EVENT = {
    "BLOCKED": "AUDIT_BLOCKED",
    "GO": "AUDIT_GO",
    "GO_WITH_CONDITIONS": "AUDIT_GO_WITH_CONDITIONS",
}

RESULT_VERDICT_TO_EVENT = {
    "APPROVED": "RESULT_APPROVED",
    "BLOCKED": "RESULT_BLOCKED",
}


def protocol_version() -> str:
    from tools.council import PROTOCOL_VERSION
    return PROTOCOL_VERSION
