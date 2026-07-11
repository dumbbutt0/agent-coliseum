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
    assert ALLOWED_TEST_COMMANDS == ("python3 -m pytest tests/ -q",)


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
