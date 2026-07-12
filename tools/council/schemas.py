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
    # human-only condition sign-off: a conditional source verdict
    # (AUDIT_GO_WITH_CONDITIONS) mechanically refuses CHANGE_INTEGRATED
    # until the owner records this event — printed advice never gates
    "CONDITIONS_SATISFIED",
    "NEXT_MILESTONE_READY",
    "AUTONOMY_PAUSED",
    "AUTONOMY_MILESTONE_REACHED",
    # H1 identity + control events (request_id is a synthetic control slug;
    # they never touch request state)
    "STATUS_CHANGED",
    "POLICY_INITIALIZED",
    "HUMAN_IDENTITY_INITIALIZED",
    "HUMAN_IDENTITY_ROTATED",
    # H4: human-token blessing of a specific legacy/nonconforming event so
    # quarantine-aware projection may treat it as authority again
    "MIGRATION_APPROVED",
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
    "CONDITIONS_SATISFIED": frozenset({"human"}),
    "NEXT_MILESTONE_READY": frozenset({"claude"}),
    "AUTONOMY_PAUSED": frozenset({"claude", "codex", "human"}),
    "AUTONOMY_MILESTONE_REACHED": frozenset({"claude"}),
    "STATUS_CHANGED": frozenset({"human"}),
    "POLICY_INITIALIZED": frozenset({"human"}),
    "HUMAN_IDENTITY_INITIALIZED": frozenset({"human"}),
    "HUMAN_IDENTITY_ROTATED": frozenset({"human"}),
    "MIGRATION_APPROVED": frozenset({"human"}),
}

# H1: events whose authority is a HUMAN one-time token (S/KEY chain,
# tools/council/identity.py) — a caller-supplied --role/sender string is
# never sufficient. REQUEST_CANCELED needs a token only from a human
# sender (claude cancels revoke, never grant). HUMAN_IDENTITY_INITIALIZED
# is self-pinning (it CREATES the chain) and needs no token.
HUMAN_TOKEN_REQUIRED_EVENT_TYPES = frozenset({
    "EXPERIMENT_APPROVED", "CONDITIONS_SATISFIED", "REQUEST_CANCELED",
    "STATUS_CHANGED", "POLICY_INITIALIZED", "HUMAN_IDENTITY_ROTATED",
    "MIGRATION_APPROVED",
})

# H1: bootstrap/control events appendable while the CONTROL record pauses
# the council (a fail-closed fresh root must be bootstrappable, and
# un-pausing requires appending STATUS_CHANGED) — but NEVER while the
# STOP file exists: STOP is the hard emergency stop.
CONTROL_BOOTSTRAP_EVENT_TYPES = frozenset({
    "STATUS_CHANGED", "POLICY_INITIALIZED", "HUMAN_IDENTITY_INITIALIZED",
    "HUMAN_IDENTITY_ROTATED",
})

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

# Test commands an audit request may name (never executed here). SOURCE audits
# use the full suite (they change code). EXPERIMENT run requests bind an
# ALREADY-INTEGRATED commit whose full suite was verified at integration, so
# their no-regression check is the fast experiment-relevant subset (config
# binding, driver, registry, reports, metrics freeze) — ~6s, which completes
# reliably inside the auditor's command window, instead of the ~95s full suite
# that intermittently gets terminated mid-run in the sandbox.
FULL_TEST_COMMAND = "python3 -m pytest tests/ -q"
EXPERIMENT_TEST_COMMAND = (
    "python3 -m pytest tests/test_textlab_experiment_registry.py "
    "tests/test_textlab_reports_claims.py tests/test_autonomy_ollama_driver.py "
    "tests/test_m6_experiment_configs.py tests/test_textlab_prereg.py "
    "tests/test_textlab_metrics_freeze.py -q")
ALLOWED_TEST_COMMANDS = (FULL_TEST_COMMAND, EXPERIMENT_TEST_COMMAND)

# H2 item 11 bounds on request AND verdict content (reject unbounded
# strings/arrays). Finding prose (evidence, failure_mode, ...) gets a
# larger cap than short scalar fields but is still bounded.
_MAX_TEST_COUNT = 1_000_000
_MAX_LIST_ITEMS = 200
_MAX_FIELD_STRING = 4_000
_MAX_FINDING_STRING = 20_000


def _validate_safe_relpath(value, field: str) -> None:
    """A request path field must be a safe relative path: no absolute
    root, no `..` traversal, no backslash, no NUL."""
    if not isinstance(value, str) or not value:
        raise SchemaViolation(f"{field} must be a non-empty string")
    if value.startswith("/") or value.startswith("\\") \
            or "\\" in value or "\x00" in value \
            or ".." in value.split("/"):
        raise SchemaViolation(
            f"{field} {value!r} must be a safe relative path "
            "(no leading slash, no '..', no backslash)")

# Continuation kind after AUDIT_GO. "experiment": policy validation ->
# AUTO_APPROVED/human gate -> bounded runner -> result audit. "source":
# state REMAINS `go` — the only legal continuation is a commit-bound
# CHANGE_INTEGRATED recorded by the integration step, never by a watcher.
# Absent field = "experiment": every pre-existing request keeps its exact
# behavior. The field sits inside request_payload_hash, so the kind is
# event-pinned and tamper-evident like every other request field.
TASK_KINDS = ("experiment", "source")

GENESIS_HASH = "0" * 64

_REQUEST_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


# ------------------------------------------------------------- canonical JSON

def canonical_json(obj) -> str:
    """UTF-8, sorted keys, compact separators, NaN refused."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def payload_hash(obj) -> str:
    """LEGACY (protocol 1.0) hash: bare sha256 of canonical JSON, no
    domain tag. Retained for verifying/extending the pre-H2 chain."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def domain_hash(domain: str, obj) -> str:
    """Domain-separated hash (H2 item 12): sha256(domain + NUL + canonical
    JSON). Distinct domains make a request, a verdict, an event, and an
    evidence inventory that happen to canonicalize alike hash DIFFERENTLY,
    so a payload can never be reinterpreted across schemas."""
    return hashlib.sha256(
        domain.encode("ascii") + b"\x00"
        + canonical_json(obj).encode("utf-8")).hexdigest()


# hashing domains (H2). v2 objects are domain-tagged; v1 objects keep the
# bare payload_hash so the existing chain verifies unbroken.
EVENT_DOMAIN_V2 = "council:event:v2"
REQUEST_DOMAIN_V2 = "council:request:v2"
SOURCE_VERDICT_DOMAIN_V2 = "council:source-verdict:v2"
RESULT_VERDICT_DOMAIN_V2 = "council:result-verdict:v2"
EVIDENCE_INVENTORY_DOMAIN = "council:evidence-inventory:v1"
VALIDATION_REPORT_DOMAIN = "council:validation-report:v1"
CONTROL_DOMAIN = "council:control:v1"


_VERSION_ABSENT = object()


def _obj_version(obj: dict, field: str = "protocol_version") -> str:
    """The declared version of an event/object. Cycle-2 blocker: only a
    TRULY ABSENT field defaults to legacy 1.0; a PRESENT value (even
    '', None, False, 0) is returned as-is so the dispatch can reject it —
    `obj.get(field) or '1.0'` silently coerced falsy values to legacy."""
    value = obj.get(field, _VERSION_ABSENT)
    if value is _VERSION_ABSENT:
        return "1.0"
    return value


def compute_event_hash(event: dict) -> str:
    """Version-DISPATCHED (H2): a 2.0 event is hashed under the event
    domain; a 1.0 event keeps the bare formula. An UNSUPPORTED version
    raises (cycle-1 blocker 3: the legacy fallback silently admitted a
    3.0 event) — verify_chain surfaces this as an invalid chain."""
    version = _obj_version(event)
    if version not in SUPPORTED_PROTOCOL_VERSIONS:
        raise ChainError(
            f"event {event.get('event_id')!r}: unsupported "
            f"protocol_version {version!r} — only "
            f"{SUPPORTED_PROTOCOL_VERSIONS} exist")
    body = {k: v for k, v in event.items() if k != "event_hash"}
    if version == "2.0":
        return domain_hash(EVENT_DOMAIN_V2, body)
    return payload_hash(body)


def compute_request_payload_hash(request: dict) -> str:
    body = {k: v for k, v in request.items() if k != "request_payload_hash"}
    version = _obj_version(request)
    if version not in SUPPORTED_PROTOCOL_VERSIONS:
        raise SchemaViolation(
            f"unsupported request protocol_version {version!r}")
    if version == "2.0":
        return domain_hash(REQUEST_DOMAIN_V2, body)
    return payload_hash(body)


VERDICT_SCHEMA_DOMAINS = {
    "source-verdict.v2": SOURCE_VERDICT_DOMAIN_V2,
    "result-verdict.v2": RESULT_VERDICT_DOMAIN_V2,
}

# H3 authority-context bindings. A v2 verdict binds to the exact request,
# publication event, cycle, commit, and auditor; a result verdict also
# binds the frozen config, the evidence inventory, and the auditor's
# replay/counts/conclusion. codex_watch.submit_verdict populates the
# derivable fields; crosscheck_verdict_bindings verifies them against the
# chain at the append boundary.
SOURCE_VERDICT_BINDING_FIELDS = (
    "request_payload_hash", "publication_event_id", "publication_event_hash",
    "audit_cycle", "auditor",
)
RESULT_VERDICT_BINDING_FIELDS = SOURCE_VERDICT_BINDING_FIELDS + (
    "experiment_config_hash", "run_id", "run_dir", "evidence_inventory_hash",
    "validation_report_hash", "replay_result", "counts", "conclusion_scope",
)
REPLAY_RESULTS = ("replayed_ok", "replay_failed", "replay_not_supported")
RESULT_COUNT_FIELDS = ("scenarios_run", "validations_passed",
                       "validations_failed")
_EVENT_ID_RE = re.compile(r"^\d{6}-[0-9a-f]{8}$")


def _validate_verdict_bindings(verdict: dict, result_kind: bool) -> None:
    """Type-check the H3 binding fields present on a v2 verdict (the chain
    cross-check happens in crosscheck_verdict_bindings)."""
    fields = (RESULT_VERDICT_BINDING_FIELDS if result_kind
              else SOURCE_VERDICT_BINDING_FIELDS)
    missing = [f for f in fields if f not in verdict]
    if missing:
        raise SchemaViolation(
            f"v2 verdict missing binding fields: {missing}")
    if not _SHA256_RE.match(str(verdict["request_payload_hash"])):
        raise SchemaViolation("request_payload_hash must be a sha256")
    if not _EVENT_ID_RE.match(str(verdict["publication_event_id"])):
        raise SchemaViolation("publication_event_id malformed")
    if not _SHA256_RE.match(str(verdict["publication_event_hash"])):
        raise SchemaViolation("publication_event_hash must be a sha256")
    if not isinstance(verdict["audit_cycle"], int) \
            or isinstance(verdict["audit_cycle"], bool) \
            or verdict["audit_cycle"] < 1:
        raise SchemaViolation("audit_cycle must be an int >= 1")
    if verdict["auditor"] != "codex":
        raise SchemaViolation("auditor must be 'codex'")
    if not result_kind:
        return
    for name in ("experiment_config_hash", "evidence_inventory_hash",
                 "validation_report_hash"):
        if not _SHA256_RE.match(str(verdict[name])):
            raise SchemaViolation(f"{name} must be a sha256")
    if not isinstance(verdict["run_id"], str) or not verdict["run_id"]:
        raise SchemaViolation("run_id must be a non-empty string")
    _validate_safe_relpath(verdict["run_dir"], "run_dir")
    if verdict["replay_result"] not in REPLAY_RESULTS:
        raise SchemaViolation(
            f"replay_result must be in {REPLAY_RESULTS}")
    counts = verdict["counts"]
    if not isinstance(counts, dict) \
            or set(counts) != set(RESULT_COUNT_FIELDS):
        raise SchemaViolation(
            f"counts must be exactly {RESULT_COUNT_FIELDS}")
    for name in RESULT_COUNT_FIELDS:
        if not isinstance(counts[name], int) \
                or isinstance(counts[name], bool) or counts[name] < 0:
            raise SchemaViolation(f"counts.{name} must be a non-neg int")
    if not isinstance(verdict["conclusion_scope"], str) \
            or not verdict["conclusion_scope"] \
            or len(verdict["conclusion_scope"]) > _MAX_FIELD_STRING:
        raise SchemaViolation(
            f"conclusion_scope must be a non-empty string "
            f"<= {_MAX_FIELD_STRING} chars")


def compute_verdict_payload_hash(verdict: dict) -> str:
    """A verdict's hash domain is UNAMBIGUOUS (cycle-1 blocker 1): a
    known schema_version drives its v2 domain; ABSENT schema_version is a
    legacy verdict (bare hash). An unknown schema_version raises rather
    than silently falling back — validate_verdict enforces the same, so a
    verdict can never claim a v2 shape while being legacy-hashed."""
    body = {k: v for k, v in verdict.items() if k != "verdict_payload_hash"}
    sv = verdict.get("schema_version")
    if sv is None:
        return payload_hash(body)
    if sv not in VERDICT_SCHEMA_DOMAINS:
        raise SchemaViolation(
            f"unknown verdict schema_version {sv!r} "
            f"(known: {sorted(VERDICT_SCHEMA_DOMAINS)})")
    return domain_hash(VERDICT_SCHEMA_DOMAINS[sv], body)


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


SUPPORTED_PROTOCOL_VERSIONS = ("1.0", "2.0")


def validate_event(event: dict, for_append: bool = False) -> None:
    """Version-dispatched (H2): 1.0 events are valid on READ/replay only;
    only the CURRENT protocol_version may be appended (for_append=True)."""
    missing = [f for f in EVENT_REQUIRED_FIELDS if f not in event]
    if missing:
        raise SchemaViolation(f"event missing required fields: {missing}")
    validate_sender(event["event_type"], event["sender"])
    validate_request_id(event["request_id"])
    validate_commit(event["target_commit"])
    version = event["protocol_version"]
    if version not in SUPPORTED_PROTOCOL_VERSIONS:
        raise SchemaViolation(
            f"protocol_version {version!r} unsupported")
    if for_append and version != protocol_version():
        raise SchemaViolation(
            f"new events must be protocol_version {protocol_version()!r}, "
            f"not {version!r} (1.0 is valid on replay only)")
    if not isinstance(event["payload"], dict):
        raise SchemaViolation("event payload must be an object")
    if event["event_type"] in VERDICT_PAYLOAD_EVENT_TYPES:
        validate_verdict_event_payload(event)
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
    if request["protocol_version"] not in SUPPORTED_PROTOCOL_VERSIONS:
        raise SchemaViolation(
            f"unsupported request protocol_version "
            f"{request['protocol_version']!r}")
    if request["require_clean_tree"] is not True:
        raise SchemaViolation("require_clean_tree must be true")
    if request["live_experiment_allowed"] is not False:
        raise SchemaViolation("live_experiment_allowed must be false")
    task_kind = request.get("task_kind", "experiment")
    if task_kind not in TASK_KINDS:
        raise SchemaViolation(
            f"task_kind {task_kind!r} unknown (allowed: {TASK_KINDS})")
    # human_approval_required may be false ONLY for a policy-eligible
    # sandbox_local experiment carrying a complete autonomy block; the
    # autonomy policy still has final say at POLICY_VALIDATION time.
    if request["human_approval_required"] is not True:
        if request["human_approval_required"] is not False:
            raise SchemaViolation("human_approval_required must be a bool")
        if task_kind == "source":
            raise SchemaViolation(
                "task_kind 'source' has no autonomy/policy path — "
                "human_approval_required must stay true (the flag is never "
                "consumed: source GO ends at commit-bound CHANGE_INTEGRATED)")
        validate_autonomy_block(request.get("autonomy"))
    if request["expected_test_command"] not in ALLOWED_TEST_COMMANDS:
        raise SchemaViolation(
            f"expected_test_command {request['expected_test_command']!r} "
            f"not in allowlist {ALLOWED_TEST_COMMANDS}")
    # SOURCE tasks change code and MUST run the full suite; the fast
    # experiment subset is only for experiment run requests, which bind an
    # already-integrated commit whose full suite was verified at integration.
    if task_kind == "source" and \
            request["expected_test_command"] != FULL_TEST_COMMAND:
        raise SchemaViolation(
            "task_kind 'source' must run the full suite "
            f"({FULL_TEST_COMMAND!r}); the experiment subset is only for "
            "experiment run requests binding already-integrated code")
    # H2 item 11: bool is not an int (isinstance(True, int) is True in
    # Python) and the count is bounded
    if not isinstance(request["expected_test_count"], int) \
            or isinstance(request["expected_test_count"], bool) \
            or not (0 < request["expected_test_count"] <= _MAX_TEST_COUNT):
        raise SchemaViolation(
            f"expected_test_count must be an int in 1..{_MAX_TEST_COUNT}")
    for list_field in ("scope", "questions", "allowed_actions",
                       "forbidden_actions", "requested_verdicts",
                       "blockers_addressed"):
        value = request[list_field]
        if not isinstance(value, list) or not value:
            raise SchemaViolation(f"{list_field} must be a non-empty list")
        # H2 item 11: bounded lists of bounded non-empty strings — no
        # unbounded arrays, no non-string authority-looking entries
        if len(value) > _MAX_LIST_ITEMS:
            raise SchemaViolation(
                f"{list_field} has more than {_MAX_LIST_ITEMS} entries")
        for entry in value:
            if not isinstance(entry, str) or not entry:
                raise SchemaViolation(
                    f"{list_field} entries must be non-empty strings")
            if len(entry) > _MAX_FIELD_STRING:
                raise SchemaViolation(
                    f"{list_field} entry exceeds {_MAX_FIELD_STRING} chars")
    for v in request["requested_verdicts"]:
        if v not in VERDICT_EVENT_TYPES:
            raise SchemaViolation(f"requested verdict {v!r} is not a "
                                  "verdict event type")
    # H2 item 11: v2 requests must carry safe relative path fields (1.0
    # requests keep the legacy permissive behavior on replay)
    if request["protocol_version"] == "2.0":
        for path_field in ("experiment_config_file",):
            if path_field in request:
                _validate_safe_relpath(request[path_field], path_field)
    want = compute_request_payload_hash(request)
    if request["request_payload_hash"] != want:
        raise SchemaViolation("request_payload_hash does not match content")


AUDIT_VERDICT_VALUES = ("BLOCKED", "GO", "GO_WITH_CONDITIONS")
RESULT_VERDICT_VALUES = ("APPROVED", "BLOCKED")

# H2 carried follow-ups: audit_mode is a closed vocabulary and
# timestamp_utc matches the council's utc_now() format
AUDIT_MODES = ("narrow", "isolated_archive", "full", "result")
_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$")


def _validate_utc_timestamp(value) -> None:
    """Grammar AND real calendar/clock (cycle-1 blocker 2: the regex alone
    accepted 2026-99-99T99:99:99Z)."""
    if not isinstance(value, str) or not _TIMESTAMP_RE.match(value):
        raise SchemaViolation(
            "timestamp_utc must be ISO-8601 UTC "
            "(YYYY-MM-DDTHH:MM:SS[.ffffff]Z)")
    import datetime
    core = value[:-1]  # drop trailing Z
    fmt = "%Y-%m-%dT%H:%M:%S.%f" if "." in core else "%Y-%m-%dT%H:%M:%S"
    try:
        datetime.datetime.strptime(core, fmt)
    except ValueError as exc:
        raise SchemaViolation(f"timestamp_utc is not a real UTC time: {exc}")

FINDING_REQUIRED_FIELDS = (
    "claim", "evidence", "failure_mode", "file", "line_range",
    "minimum_fix", "minimum_regression", "reproduced", "severity",
    "blocks_requested_action",
)

FINDING_SEVERITIES = ("HIGH", "MEDIUM", "LOW", "INFO")


def _validate_finding(finding) -> None:
    """Every finding is a structured object with the ten protocol fields,
    correctly typed. Extra keys are permitted (auditors attach evidence
    detail); the required shape is not negotiable."""
    if not isinstance(finding, dict):
        raise SchemaViolation(
            "each finding must be a structured object, not "
            f"{type(finding).__name__}")
    missing = [f for f in FINDING_REQUIRED_FIELDS if f not in finding]
    if missing:
        raise SchemaViolation(f"finding missing required fields: {missing}")
    if finding["severity"] not in FINDING_SEVERITIES:
        raise SchemaViolation(
            f"finding severity {finding['severity']!r} not in "
            f"{FINDING_SEVERITIES}")
    for name in ("reproduced", "blocks_requested_action"):
        if not isinstance(finding[name], bool):
            raise SchemaViolation(f"finding {name} must be a bool")
    for name in ("claim", "evidence", "failure_mode", "file", "line_range",
                 "minimum_fix", "minimum_regression"):
        if not isinstance(finding[name], str) or not finding[name]:
            raise SchemaViolation(
                f"finding {name} must be a non-empty string")
        if len(finding[name]) > _MAX_FINDING_STRING:
            raise SchemaViolation(
                f"finding {name} exceeds {_MAX_FINDING_STRING} chars")


def validate_verdict(verdict: dict, result_audit: bool = False) -> None:
    """The STRICT structured-verdict schema (launcher audit-002 cycle-1
    blocker: presence alone is not a schema). Source audits verdict in
    AUDIT_VERDICT_VALUES; result audits in RESULT_VERDICT_VALUES; both
    share the required fields, types, and payload hash. The top level
    deliberately admits EXTRA fields — result verdicts carry evidence
    extras (evidence_hashes, limits_observed, run_dir, ...) and every
    extra is covered by the payload hash — but every required field is
    fully type-checked and findings must be structured objects."""
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
    if not isinstance(verdict["tests_observed"], int) \
            or isinstance(verdict["tests_observed"], bool) \
            or verdict["tests_observed"] < 0:
        raise SchemaViolation(
            "tests_observed must be a non-negative int")
    for name in ("summary", "audit_mode", "timestamp_utc"):
        if not isinstance(verdict[name], str) or not verdict[name]:
            raise SchemaViolation(f"{name} must be a non-empty string")
    # H2 item 11 (cycle-3/4 blockers): summary is a short scalar field,
    # capped at _MAX_FIELD_STRING (4000) — the larger _MAX_FINDING_STRING
    # applies only to finding prose (evidence, failure_mode, ...)
    if len(verdict["summary"]) > _MAX_FIELD_STRING:
        raise SchemaViolation(
            f"summary exceeds {_MAX_FIELD_STRING} chars")
    # H2 (carried from codex-auto-launcher-audit-002 GO_WITH_CONDITIONS):
    # audit_mode is an enum and timestamp_utc is a REAL UTC timestamp
    if verdict["audit_mode"] not in AUDIT_MODES:
        raise SchemaViolation(
            f"audit_mode {verdict['audit_mode']!r} not in {AUDIT_MODES}")
    _validate_utc_timestamp(verdict["timestamp_utc"])
    # cycle-1 blocker 1: schema_version, if present, must be known and
    # match the audit kind — no verdict claims a v2 shape while legacy
    sv = verdict.get("schema_version")
    if sv is not None:
        expected_sv = ("result-verdict.v2" if result_audit
                       else "source-verdict.v2")
        if sv != expected_sv:
            raise SchemaViolation(
                f"verdict schema_version {sv!r} does not match this audit "
                f"kind (expected {expected_sv!r})")
        # H3: a v2 verdict carries its authority-context bindings
        _validate_verdict_bindings(verdict, result_audit)
    for name in ("blockers", "conditions", "commands_run"):
        value = verdict[name]
        if not isinstance(value, list) or \
                any(not isinstance(x, str) or not x for x in value):
            raise SchemaViolation(
                f"{name} must be a list of non-empty strings")
        # H2 item 11 (cycle-3 blocker): bound the list and each string
        if len(value) > _MAX_LIST_ITEMS:
            raise SchemaViolation(
                f"{name} has more than {_MAX_LIST_ITEMS} entries")
        if any(len(x) > _MAX_FINDING_STRING for x in value):
            raise SchemaViolation(
                f"{name} entry exceeds {_MAX_FINDING_STRING} chars")
    if not isinstance(verdict["findings"], list):
        raise SchemaViolation("findings must be a list")
    if len(verdict["findings"]) > _MAX_LIST_ITEMS:
        raise SchemaViolation(
            f"findings has more than {_MAX_LIST_ITEMS} entries")
    for finding in verdict["findings"]:
        _validate_finding(finding)
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

RESULT_VERDICT_EVENT_TYPES = frozenset(RESULT_VERDICT_TO_EVENT.values())
VERDICT_PAYLOAD_EVENT_TYPES = \
    frozenset(VERDICT_TO_EVENT.values()) | RESULT_VERDICT_EVENT_TYPES


def validate_verdict_event_payload(event: dict) -> None:
    """A verdict EVENT must carry a fully schema-valid nested verdict bound
    to the same request and commit, whose verdict value maps to the event
    type (launcher audit cycle-5 blocker). Enforced at the append boundary
    for every new AUDIT_*/RESULT_* verdict event, and re-checked before
    artifact recovery ever treats a chained payload as authority — a
    hash-chained but malformed verdict is never promoted into one."""
    etype = event["event_type"]
    result_kind = etype in RESULT_VERDICT_EVENT_TYPES
    verdict = event["payload"]
    validate_verdict(verdict, result_audit=result_kind)
    # H2 completion: a 2.0 verdict event MUST carry the matching v2
    # schema_version so its payload is domain-separated (1.0 verdict
    # events replay under the legacy bare hash). validate_verdict already
    # rejects a mismatched schema_version; here we require its PRESENCE
    # for new (2.0) verdict events.
    if _obj_version(event) == "2.0":
        expected_sv = ("result-verdict.v2" if result_kind
                       else "source-verdict.v2")
        if verdict.get("schema_version") != expected_sv:
            raise SchemaViolation(
                f"a 2.0 {etype} event requires a domain-separated verdict "
                f"(schema_version {expected_sv!r}); absent/legacy bare hash "
                "is refused for new verdicts")
    if verdict["request_id"] != event["request_id"]:
        raise SchemaViolation(
            "nested verdict request_id differs from the event's request_id")
    if verdict["audited_commit"] != event["target_commit"]:
        raise SchemaViolation(
            f"nested verdict audited_commit "
            f"{verdict['audited_commit'][:12]} differs from the event's "
            f"target_commit {event['target_commit'][:12]}")
    table = RESULT_VERDICT_TO_EVENT if result_kind else VERDICT_TO_EVENT
    if table[verdict["verdict"]] != etype:
        raise SchemaViolation(
            f"verdict value {verdict['verdict']!r} does not map to event "
            f"type {etype!r}")


def crosscheck_verdict_bindings(event: dict, chain: list,
                                projection: dict) -> None:
    """H3: verify a v2 verdict's authority-context bindings against the
    CHAIN at the append boundary — the publication event exists with the
    pinned hash and type, the request payload hash and audit cycle match,
    tests_observed equals the request's expected count (the semantic check
    deferred from H2), and for result verdicts the evidence bindings equal
    the values the runner pinned in RESULT_AUDIT_REQUESTED. Legacy (1.0)
    verdicts carry no bindings and are skipped."""
    if _obj_version(event) != "2.0":
        return
    etype = event["event_type"]
    result_kind = etype in RESULT_VERDICT_EVENT_TYPES
    verdict = event["payload"]
    rid = event["request_id"]

    # the pinned publication event (source: latest AUDIT_REQUESTED/
    # READY_FOR_REAUDIT; result: the RESULT_AUDIT_REQUESTED)
    pub_types = (("RESULT_AUDIT_REQUESTED",) if result_kind
                 else ("AUDIT_REQUESTED", "READY_FOR_REAUDIT"))
    pub = None
    for e in chain:
        if e["request_id"] == rid and e["event_type"] in pub_types:
            pub = e
    if pub is None:
        raise SchemaViolation(
            f"no {pub_types} publication event for {rid} — cannot bind")
    if verdict["publication_event_id"] != pub["event_id"] \
            or verdict["publication_event_hash"] != pub["event_hash"]:
        raise SchemaViolation(
            "verdict publication_event binding does not match the chain's "
            f"pinned {pub['event_type']} event")
    req_state = projection.get(rid, {})
    if verdict["audit_cycle"] != req_state.get("audit_cycles"):
        raise SchemaViolation(
            f"verdict audit_cycle {verdict['audit_cycle']} != the request's "
            f"cycle count {req_state.get('audit_cycles')}")
    # request_payload_hash: source binds the payload hash pinned by the
    # publication event; result binds the request's payload hash too
    pinned_req_hash = None
    for e in chain:
        if e["request_id"] == rid and e["event_type"] in (
                "AUDIT_REQUESTED", "READY_FOR_REAUDIT"):
            pinned_req_hash = e["payload"].get("request_payload_hash")
    # verify only what the publication event actually pins (the real
    # publish/runner path always pins these; a synthetic/legacy event
    # that pins nothing has nothing to cross-check against)
    if pinned_req_hash is not None \
            and verdict["request_payload_hash"] != pinned_req_hash:
        raise SchemaViolation(
            "verdict request_payload_hash does not match the pinned request")
    # deferred from H2/-002: tests_observed must equal the request's
    # event-pinned expected_test_count (source audits declare it)
    pinned_expected = None
    for e in chain:
        if e["request_id"] == rid and e["event_type"] in (
                "AUDIT_REQUESTED", "READY_FOR_REAUDIT"):
            pinned_expected = e["payload"].get("expected_test_count")
    if pinned_expected is not None \
            and verdict["tests_observed"] != pinned_expected:
        raise SchemaViolation(
            f"verdict tests_observed {verdict['tests_observed']} != the "
            f"request's expected_test_count {pinned_expected}")
    if result_kind:
        for field in ("experiment_config_hash", "evidence_inventory_hash",
                      "validation_report_hash", "run_id", "run_dir"):
            pinned = pub["payload"].get(field)
            if pinned is not None and verdict[field] != pinned:
                raise SchemaViolation(
                    f"verdict {field} does not match the runner-pinned "
                    "RESULT_AUDIT_REQUESTED value")


def protocol_version() -> str:
    from tools.council import PROTOCOL_VERSION
    return PROTOCOL_VERSION
