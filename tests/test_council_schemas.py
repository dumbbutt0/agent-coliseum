"""Role matrix, request/verdict schema enforcement, path-traversal and
allowlist defenses."""
import pytest

from tests.council_util import (make_autonomy_block, make_repo, make_request,
                                make_verdict)
from tools.council import schemas
from tools.council.schemas import (ALLOWED_TEST_COMMANDS, EVENT_TYPES,
                                   REQUEST_REQUIRED_FIELDS, ROLES,
                                   SENDER_ALLOWED, RoleViolation,
                                   SchemaViolation, VERDICT_REQUIRED_FIELDS,
                                   compute_request_payload_hash,
                                   compute_verdict_payload_hash,
                                   validate_commit, validate_repository,
                                   validate_request, validate_request_id,
                                   validate_sender, validate_verdict)


def _ready_request(repo, head, **overrides):
    request = make_request(repo, head, **overrides)
    request["request_payload_hash"] = compute_request_payload_hash(request)
    return request


def _ready_verdict(head, **overrides):
    verdict = make_verdict(head, **overrides)
    verdict["verdict_payload_hash"] = compute_verdict_payload_hash(verdict)
    return verdict


# ------------------------------------------------------------- role matrix

@pytest.mark.parametrize("event_type", EVENT_TYPES)
@pytest.mark.parametrize("role", ROLES)
def test_sender_matrix(event_type, role):
    if role in SENDER_ALLOWED[event_type]:
        validate_sender(event_type, role)
    else:
        with pytest.raises(RoleViolation):
            validate_sender(event_type, role)


def test_claude_never_submits_verdicts_or_approves():
    for event_type in ("AUDIT_GO", "AUDIT_GO_WITH_CONDITIONS",
                       "AUDIT_BLOCKED", "EXPERIMENT_APPROVED",
                       "RESULT_APPROVED", "RESULT_BLOCKED"):
        assert "claude" not in SENDER_ALLOWED[event_type]


def test_codex_never_records_fixes_or_opens_gate():
    for event_type in ("FIX_STARTED", "BUILD_READY", "READY_FOR_REAUDIT",
                       "HUMAN_APPROVAL_REQUIRED", "EXPERIMENT_APPROVED"):
        assert "codex" not in SENDER_ALLOWED[event_type]


def test_only_human_approves():
    assert SENDER_ALLOWED["EXPERIMENT_APPROVED"] == frozenset({"human"})


def test_unknown_event_type_and_role():
    with pytest.raises(SchemaViolation):
        validate_sender("NOT_AN_EVENT", "claude")
    with pytest.raises(RoleViolation):
        validate_sender("BUILD_STARTED", "root")


# ---------------------------------------------------------------- request_id

@pytest.mark.parametrize("bad", ["../x", "a/b", "a\\b", "/abs", "..",
                                 "UPPER-case", "sp ace", "", "ab",
                                 "x" * 65, "-lead"])
def test_request_id_traversal_and_format_refused(bad):
    with pytest.raises(SchemaViolation):
        validate_request_id(bad)


def test_request_id_accepts_slug():
    assert validate_request_id("sequential-rerun-audit-004") \
        == "sequential-rerun-audit-004"


# -------------------------------------------------------------------- commits

@pytest.mark.parametrize("bad", ["ed05361", "e" * 39, "e" * 41,
                                 "E" * 40, "xyz", ""])
def test_abbreviated_or_malformed_commit_refused(bad):
    with pytest.raises(SchemaViolation):
        validate_commit(bad)


def test_full_commit_accepted():
    validate_commit("ed0536159a3e69698b38a40adaf340a548d5a7b8")


# --------------------------------------------------------------- repositories

def test_repository_outside_roots_refused(tmp_path):
    repo, _head = make_repo(tmp_path)
    validate_repository(repo, (repo,))
    with pytest.raises(SchemaViolation):
        validate_repository(str(tmp_path / "elsewhere"), (repo,))
    with pytest.raises(SchemaViolation):
        validate_repository("/etc", (repo,))


def test_repository_prefix_trick_refused(tmp_path):
    repo, _head = make_repo(tmp_path)
    with pytest.raises(SchemaViolation):
        validate_repository(repo + "-evil", (repo,))


# ------------------------------------------------------------------- requests

@pytest.mark.parametrize("field", [f for f in REQUEST_REQUIRED_FIELDS
                                   if f != "request_payload_hash"])
def test_request_missing_each_required_field(tmp_path, field):
    repo, head = make_repo(tmp_path)
    request = make_request(repo, head)
    del request[field]
    request["request_payload_hash"] = compute_request_payload_hash(request)
    with pytest.raises(SchemaViolation):
        validate_request(request, (repo,))


def test_request_forced_booleans(tmp_path):
    repo, head = make_repo(tmp_path)
    for key, bad in (("require_clean_tree", False),
                     ("live_experiment_allowed", True)):
        request = _ready_request(repo, head, **{key: bad})
        with pytest.raises(SchemaViolation):
            validate_request(request, (repo,))


def test_request_test_command_allowlist(tmp_path):
    repo, head = make_repo(tmp_path)
    request = _ready_request(
        repo, head, expected_test_command="python3 -c 'import os'")
    with pytest.raises(SchemaViolation):
        validate_request(request, (repo,))
    # full suite (source audits) + the fast experiment-relevant subset
    # (experiment run requests bind already-integrated code)
    assert "python3 -m pytest tests/ -q" in ALLOWED_TEST_COMMANDS
    assert len(ALLOWED_TEST_COMMANDS) == 2
    assert any("test_autonomy_ollama_driver" in c for c in ALLOWED_TEST_COMMANDS)


def test_source_task_must_use_full_suite(tmp_path):
    """The fast experiment subset is only for experiment run requests; a SOURCE
    task changes code and must run the full suite (else a code change could
    skip most of the regression)."""
    from tools.council.schemas import (EXPERIMENT_TEST_COMMAND,
                                       FULL_TEST_COMMAND)
    repo, head = make_repo(tmp_path)
    # source + subset -> refused
    bad = _ready_request(repo, head, task_kind="source",
                         expected_test_command=EXPERIMENT_TEST_COMMAND)
    with pytest.raises(SchemaViolation, match="must run the full suite"):
        validate_request(bad, (repo,))
    # source + full suite -> accepted
    good = _ready_request(repo, head, task_kind="source",
                          expected_test_command=FULL_TEST_COMMAND)
    validate_request(good, (repo,))
    # experiment + subset -> accepted (binds already-integrated code)
    exp = _ready_request(repo, head, task_kind="experiment",
                         expected_test_command=EXPERIMENT_TEST_COMMAND)
    validate_request(exp, (repo,))


def test_request_payload_hash_must_match(tmp_path):
    repo, head = make_repo(tmp_path)
    request = _ready_request(repo, head)
    request["scope"] = ["silently widened"]  # hash now stale
    with pytest.raises(SchemaViolation):
        validate_request(request, (repo,))


def test_valid_request_passes(tmp_path):
    repo, head = make_repo(tmp_path)
    validate_request(_ready_request(repo, head), (repo,))


# --------------------------------------------- task_kind (protocol delta)

def test_task_kind_values(tmp_path):
    repo, head = make_repo(tmp_path)
    validate_request(_ready_request(repo, head, task_kind="source"), (repo,))
    validate_request(_ready_request(repo, head, task_kind="experiment"),
                     (repo,))
    with pytest.raises(SchemaViolation):
        validate_request(_ready_request(repo, head, task_kind="wiki"),
                         (repo,))


def test_source_task_kind_refuses_autonomy_gate_bypass(tmp_path):
    """A source task has no policy path — declaring it autonomous
    (human_approval_required false) is a contradiction and is refused."""
    repo, head = make_repo(tmp_path)
    request = _ready_request(repo, head, task_kind="source",
                             human_approval_required=False)
    with pytest.raises(SchemaViolation):
        validate_request(request, (repo,))


def test_task_kind_is_covered_by_payload_hash(tmp_path):
    """Flipping the kind after publish must invalidate the pinned hash —
    the discriminator is tamper-evident like every other field."""
    repo, head = make_repo(tmp_path)
    request = _ready_request(repo, head, task_kind="source")
    request["task_kind"] = "experiment"  # hash now stale
    with pytest.raises(SchemaViolation):
        validate_request(request, (repo,))


# ----------------------------------------------- autonomy block (amendment)

def test_human_gate_false_requires_autonomy_block(tmp_path):
    repo, head = make_repo(tmp_path)
    request = _ready_request(repo, head, human_approval_required=False)
    with pytest.raises(SchemaViolation):
        validate_request(request, (repo,))


def test_human_gate_false_with_valid_autonomy_block(tmp_path):
    repo, head = make_repo(tmp_path)
    request = _ready_request(repo, head, human_approval_required=False,
                             autonomy=make_autonomy_block())
    validate_request(request, (repo,))


@pytest.mark.parametrize("mutate", [
    {"experiment_class": "cloud"},
    {"data_sources": ["production"]},
    {"data_sources": []},
    {"experiment_config_hash": "not-frozen"},
    {"model_digests": {"m": "latest"}},
    {"model_digests": {}},
    {"offline_replay_supported": False},
    {"limits": {"max_compute_minutes": 60}},  # incomplete limits
])
def test_autonomy_block_rejects_unsafe_variants(mutate):
    block = make_autonomy_block(**mutate)
    with pytest.raises(SchemaViolation):
        schemas.validate_autonomy_block(block)


# ------------------------------------------------------------------- verdicts

@pytest.mark.parametrize("field", [f for f in VERDICT_REQUIRED_FIELDS
                                   if f != "verdict_payload_hash"])
def test_verdict_missing_each_required_field(tmp_path, field):
    _repo, head = make_repo(tmp_path)
    verdict = make_verdict(head)
    del verdict[field]
    verdict["verdict_payload_hash"] = compute_verdict_payload_hash(verdict)
    with pytest.raises(SchemaViolation):
        validate_verdict(verdict)


def test_verdict_unknown_kind_refused(tmp_path):
    _repo, head = make_repo(tmp_path)
    verdict = _ready_verdict(head, verdict="MAYBE")
    with pytest.raises(SchemaViolation):
        validate_verdict(verdict)


def test_verdict_valid_passes(tmp_path):
    _repo, head = make_repo(tmp_path)
    validate_verdict(_ready_verdict(head))


# ------------------- strict structured-verdict schema (audit-002 cycle 1)

from tests.council_util import make_finding  # noqa: E402


@pytest.mark.parametrize("field,bad", [
    ("blockers", "not-a-list"),
    ("blockers", ["ok", 7]),
    ("conditions", {"not": "a list"}),
    ("commands_run", "not-a-list"),
    ("findings", "not-a-list"),
    ("summary", 7),
    ("summary", ""),
    ("audit_mode", None),
    ("timestamp_utc", 123),
    ("tests_observed", -1),
    ("tests_observed", True),
    ("working_tree_clean", "yes"),
])
def test_strict_verdict_schema_rejects_wrong_types(field, bad):
    """audit-002 cycle-1 blocker: presence is not a schema — every
    required field is type-checked even when the payload hash is
    recomputed self-consistently over the malformed content."""
    verdict = make_verdict("a" * 40)
    verdict[field] = bad
    verdict["verdict_payload_hash"] = compute_verdict_payload_hash(verdict)
    with pytest.raises(SchemaViolation):
        validate_verdict(verdict)


@pytest.mark.parametrize("bad_findings", [
    ["free text"],                                  # unstructured
    [{"severity": "HIGH"}],                         # missing fields
    [make_finding(severity="NUCLEAR")],             # bad severity
    [make_finding(reproduced="yes")],               # wrong type
    [make_finding(blocks_requested_action=1)],      # wrong type
    [make_finding(claim="")],                       # empty string
    [make_finding(), "free text"],                  # one bad member
])
def test_strict_finding_schema_rejects_malformed_members(bad_findings):
    verdict = make_verdict("a" * 40, findings=bad_findings)
    verdict["verdict_payload_hash"] = compute_verdict_payload_hash(verdict)
    with pytest.raises(SchemaViolation):
        validate_verdict(verdict)


@pytest.mark.parametrize("bad", ["sideways", "", "GO", "narrow ", None, 7])
def test_verdict_audit_mode_enum(bad):
    verdict = make_verdict("a" * 40)
    verdict["audit_mode"] = bad
    verdict["verdict_payload_hash"] = compute_verdict_payload_hash(verdict)
    with pytest.raises(SchemaViolation):
        validate_verdict(verdict)


@pytest.mark.parametrize("bad", ["2026-01-01", "not-a-time",
                                 "2026/01/01T00:00:00Z",
                                 "2026-01-01T00:00:00", ""])
def test_verdict_timestamp_format(bad):
    verdict = make_verdict("a" * 40)
    verdict["timestamp_utc"] = bad
    verdict["verdict_payload_hash"] = compute_verdict_payload_hash(verdict)
    with pytest.raises(SchemaViolation):
        validate_verdict(verdict)


def test_verdict_good_timestamp_and_mode_pass():
    verdict = make_verdict("a" * 40)
    verdict["audit_mode"] = "isolated_archive"
    verdict["timestamp_utc"] = "2026-07-11T03:14:15.926Z"
    verdict["verdict_payload_hash"] = compute_verdict_payload_hash(verdict)
    validate_verdict(verdict)


# --------------------------------------- request hardening (H2 item 11)

def test_request_bool_test_count_refused(tmp_path):
    repo, head = make_repo(tmp_path)
    request = _ready_request(repo, head, expected_test_count=True)
    with pytest.raises(SchemaViolation):
        validate_request(request, (repo,))


def test_request_non_string_scope_entries_refused(tmp_path):
    repo, head = make_repo(tmp_path)
    for bad in ([1, 2], ["ok", 7], [""], [None]):
        request = _ready_request(repo, head, scope=bad)
        with pytest.raises(SchemaViolation):
            validate_request(request, (repo,))


def test_request_unbounded_list_refused(tmp_path):
    repo, head = make_repo(tmp_path)
    request = _ready_request(repo, head, scope=["x"] * 500)
    with pytest.raises(SchemaViolation):
        validate_request(request, (repo,))


def test_request_unbounded_string_refused(tmp_path):
    repo, head = make_repo(tmp_path)
    request = _ready_request(repo, head, scope=["x" * 5000])
    with pytest.raises(SchemaViolation):
        validate_request(request, (repo,))


def test_v2_request_unsafe_path_refused(tmp_path):
    repo, head = make_repo(tmp_path)
    for bad in ("/etc/passwd", "../escape.json", "a\\b.json"):
        request = _ready_request(repo, head, protocol_version="2.0",
                                 experiment_config_file=bad)
        with pytest.raises(SchemaViolation):
            validate_request(request, (repo,))
    # a safe relative path passes
    ok = _ready_request(repo, head, protocol_version="2.0",
                        experiment_config_file="reports/x.json")
    validate_request(ok, (repo,))


def test_verdict_lists_and_strings_are_bounded():
    """H2 cycle-3 blocker: verdict content is bounded symmetrically with
    requests — 201 blockers, a 4001+ char summary, and 201 findings are
    all refused even with a self-consistent payload hash."""
    from tools.council.schemas import (_MAX_LIST_ITEMS, _MAX_FIELD_STRING,
                                       _MAX_FINDING_STRING)
    base = make_verdict("a" * 40, verdict="BLOCKED")
    cases = [
        dict(base, blockers=["b"] * (_MAX_LIST_ITEMS + 1)),
        dict(base, conditions=["c"] * (_MAX_LIST_ITEMS + 1)),
        dict(base, commands_run=["x"] * (_MAX_LIST_ITEMS + 1)),
        dict(base, summary="s" * (_MAX_FIELD_STRING + 1)),  # 4000 cap
        dict(base, blockers=["b" * (_MAX_FINDING_STRING + 1)]),
        dict(base, findings=[make_finding()] * (_MAX_LIST_ITEMS + 1)),
        dict(base, findings=[make_finding(
            evidence="e" * (_MAX_FINDING_STRING + 1))]),
    ]
    for verdict in cases:
        verdict["verdict_payload_hash"] = \
            compute_verdict_payload_hash(verdict)
        with pytest.raises(SchemaViolation):
            validate_verdict(verdict)


def test_valid_structured_verdicts_pass_both_vocabularies():
    """Compatibility fixtures: fully structured source and result verdicts
    (including evidence extras, which the open top level admits) validate."""
    source = make_verdict("a" * 40, findings=[
        make_finding(), make_finding(severity="HIGH", reproduced=True,
                                     blocks_requested_action=True)])
    source["verdict_payload_hash"] = compute_verdict_payload_hash(source)
    validate_verdict(source)
    result = make_verdict("a" * 40, verdict="APPROVED",
                          evidence_hashes={"run.json": "0" * 64},
                          limits_observed={"elapsed_minutes": 0.1})
    result["verdict_payload_hash"] = compute_verdict_payload_hash(result)
    validate_verdict(result, result_audit=True)
