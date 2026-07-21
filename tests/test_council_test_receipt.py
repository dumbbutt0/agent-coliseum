"""Commit-bound tamper-evident test receipts (audit-throughput slice 1).

A receipt lets ONE full-suite run at a commit stand in for the redundant re-runs
across a source audit round's sections: the others VERIFY the receipt (recompute
its digest + check commit binding + green count) instead of re-running. These
tests pin the guarantees that make that safe — tamper-evidence, commit-binding,
fail-closed verification — plus a fully backward-compatible schema.
"""
import copy

import pytest

from tests.council_util import make_cfg, make_repo, make_root
from tools.council import events
from tools.council.schemas import (
    EXPERIMENT_TEST_COMMAND, FULL_TEST_COMMAND, SchemaViolation,
    compute_request_payload_hash, validate_event, validate_request,
    validate_test_receipt_payload, validate_verdict)
from tools.council.test_receipt import (
    build_receipt_payload, find_test_receipt, record_test_receipt,
    verify_test_receipt)

COMMIT_A = "a" * 40
COMMIT_B = "b" * 40


@pytest.fixture
def env(tmp_path):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    return root, make_cfg(repo, root, role="codex"), repo


def _record(env, *, commit=COMMIT_A, passed=2184, skipped=13,
            command=FULL_TEST_COMMAND):
    root, cfg, repo = env
    return record_test_receipt(
        root, cfg, target_commit=commit, repository=repo,
        tests_passed=passed, tests_skipped=skipped, tree_clean=True,
        env_fingerprint="py3.12-linux", test_command=command)


def _payload(**over):
    kw = dict(target_commit=COMMIT_A, test_command=FULL_TEST_COMMAND,
              tests_passed=2184, tests_skipped=13, tree_clean=True,
              env_fingerprint="x")
    kw.update(over)
    return build_receipt_payload(**kw)


def _validate(payload):
    validate_test_receipt_payload(
        {"event_type": "TEST_RECEIPT_RECORDED", "payload": payload})


# ------------------------------------------------------------- round trip

def test_record_then_verify_round_trip(env):
    _record(env)
    ok, reason = verify_test_receipt(env[0], COMMIT_A, 2184)
    assert ok, reason
    chain = events.read_chain(env[0], verify=False)
    assert verify_test_receipt(chain, COMMIT_A, 2184)[0]


def test_no_receipt_fails_closed(env):
    ok, reason = verify_test_receipt(env[0], COMMIT_A, 2184)
    assert not ok and "no TEST_RECEIPT_RECORDED" in reason


def test_find_test_receipt_supports_idempotent_recording(env):
    assert find_test_receipt(env[0], COMMIT_A) is None
    _record(env)
    assert find_test_receipt(env[0], COMMIT_A)["tests_passed"] == 2184


# --------------------------------------------------------- COMMIT BINDING

def test_receipt_for_one_commit_does_not_verify_for_another(env):
    _record(env, commit=COMMIT_A)
    ok, reason = verify_test_receipt(env[0], COMMIT_B, 2184)
    assert not ok and "no TEST_RECEIPT_RECORDED" in reason


def test_recomputed_digest_still_cannot_move_a_receipt_across_commits():
    # even recomputing the digest after editing cannot help: target_commit is
    # INSIDE the digested content, so a commit-B receipt is self-consistent but
    # simply is not a receipt for commit A.
    forged = _payload(target_commit=COMMIT_B)
    _validate(forged)  # self-consistent for its own commit
    ok, _ = verify_test_receipt(
        [{"event_type": "TEST_RECEIPT_RECORDED", "payload": forged}],
        COMMIT_A, 2184)
    assert not ok


# --------------------------------------------------------- TAMPER EVIDENCE

def test_append_boundary_refuses_a_digest_that_does_not_match_content():
    tampered = dict(_payload())
    tampered["tests_passed"] = 1  # weaken the claim, keep the old digest
    with pytest.raises(SchemaViolation, match="does not match its content"):
        _validate(tampered)


def test_verify_catches_a_tampered_receipt_already_in_a_chain(env):
    _record(env)
    tampered = copy.deepcopy(events.read_chain(env[0], verify=False))
    for e in tampered:
        if e["event_type"] == "TEST_RECEIPT_RECORDED":
            e["payload"]["tests_passed"] = 9999  # digest now stale
    ok, reason = verify_test_receipt(tampered, COMMIT_A, 9999)
    assert not ok and ("digest mismatch" in reason or "re-validation" in reason)


def test_pinned_expected_digest_must_match(env):
    _record(env)
    ok, reason = verify_test_receipt(env[0], COMMIT_A, 2184,
                                     expected_digest="0" * 64)
    assert not ok and "expected_digest" in reason


# ----------------------------------------------------- GREEN / COUNT / CMD

def test_count_mismatch_fails(env):
    _record(env, passed=2184)
    ok, reason = verify_test_receipt(env[0], COMMIT_A, 2200)
    assert not ok and "not the expected" in reason


def test_red_or_empty_run_is_never_a_receipt():
    with pytest.raises(SchemaViolation, match="tests_passed must be > 0"):
        _validate(_payload(tests_passed=0))


def test_unclean_tree_is_refused():
    with pytest.raises(SchemaViolation, match="tree_clean must be exactly True"):
        _validate(_payload(tree_clean=False))


def test_wrong_test_command_does_not_satisfy_a_full_suite_verifier(env):
    _record(env, command=EXPERIMENT_TEST_COMMAND, passed=9)
    ok, reason = verify_test_receipt(env[0], COMMIT_A, 9,
                                     test_command=FULL_TEST_COMMAND)
    assert not ok and "matches test_command" in reason
    assert verify_test_receipt(env[0], COMMIT_A, 9,
                               test_command=EXPERIMENT_TEST_COMMAND)[0]


def test_real_append_records_a_valid_receipt(env):
    evt = _record(env)
    assert evt["event_type"] == "TEST_RECEIPT_RECORDED"
    validate_event(evt)


# --------------------------------------------------------- request-side
# a source audit may run the focused subset ONLY if it opts into a receipt;
# the DEFAULT still forces the full suite (backward-compat).

def _src_request(tmp_path, **over):
    from tests.council_util import make_request
    repo, head = make_repo(tmp_path)
    req = make_request(repo, head, task_kind="source", **over)
    req["request_payload_hash"] = compute_request_payload_hash(req)
    return req, (repo,)


def test_source_default_still_requires_full_suite(tmp_path):
    req, roots = _src_request(tmp_path,
                              expected_test_command=EXPERIMENT_TEST_COMMAND)
    with pytest.raises(SchemaViolation, match="must run the full suite"):
        validate_request(req, roots)


def test_source_full_suite_request_unchanged(tmp_path):
    req, roots = _src_request(tmp_path, expected_test_command=FULL_TEST_COMMAND,
                              expected_test_count=2184)
    validate_request(req, roots)


def test_receipt_backed_source_may_run_the_focused_subset(tmp_path):
    req, roots = _src_request(
        tmp_path, expected_test_command=EXPERIMENT_TEST_COMMAND,
        expected_test_count=9, suite_receipt_required=True,
        suite_receipt_expected_count=2184)
    validate_request(req, roots)


def test_receipt_required_without_expected_count_refused(tmp_path):
    req, roots = _src_request(
        tmp_path, expected_test_command=EXPERIMENT_TEST_COMMAND,
        expected_test_count=9, suite_receipt_required=True)
    with pytest.raises(SchemaViolation, match="suite_receipt_expected_count"):
        validate_request(req, roots)


def test_receipt_required_on_non_source_refused(tmp_path):
    from tests.council_util import make_request
    repo, head = make_repo(tmp_path)
    req = make_request(repo, head, suite_receipt_required=True,
                       suite_receipt_expected_count=2184)
    req["request_payload_hash"] = compute_request_payload_hash(req)
    with pytest.raises(SchemaViolation, match="only meaningful for a source"):
        validate_request(req, (repo,))


# --------------------------------------------------------- verdict-side

def _verdict_with_ref(ref):
    from tests.council_util import make_verdict
    v = make_verdict(COMMIT_A, verdict="GO")
    v.setdefault("verdict_payload_hash", "0" * 64)  # past the required-field gate
    v["suite_receipt_ref"] = ref                    # the ref check fires first
    return v


def test_malformed_suite_receipt_ref_is_refused():
    with pytest.raises(SchemaViolation, match="suite_receipt_ref must be"):
        validate_verdict(_verdict_with_ref({"target_commit": COMMIT_A}))
    with pytest.raises(SchemaViolation, match="target_commit must be a git"):
        validate_verdict(_verdict_with_ref(
            {"target_commit": "nothex", "receipt_digest": "0" * 64}))
    with pytest.raises(SchemaViolation, match="receipt_digest must be a sha256"):
        validate_verdict(_verdict_with_ref(
            {"target_commit": COMMIT_A, "receipt_digest": "short"}))
