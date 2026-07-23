"""Owner-gated M8 budget-exhaustion result handoff.

The proposal path is read-only with respect to primary evidence and creates
only its Council event.  The bundle path is unavailable until the distinct
owner approval is present.  Neither path imports a model backend or a
scientific analysis function.
"""
from __future__ import annotations

import importlib
import os
import re
import shutil
import time

from tools.council.schemas import CouncilError, SchemaViolation

ir = importlib.import_module("coliseum.textlab.incomplete_result")


SENDER = "claude"
PROFILE_ID = ir.PROFILE_ID
RESULT_REQUEST_ID = ir.RESULT_REQUEST_ID
SOURCE_REQUEST_ID = ir.SOURCE_REQUEST_ID
SOURCE_REQUEST_PAYLOAD_HASH = (
    "6465368436a36a2c987c18493dfb7c787ef724910a19463d930e5db021c3b840")
SOURCE_PUBLICATION_EVENT_ID = "002358-bb0b2c81"
SOURCE_PUBLICATION_EVENT_HASH = (
    "51cf48f2ebd24feec156295e9d8541914602c87315861e1b0e961a21be080d30")
SOURCE_AUDIT_GO_EVENT_ID = "002360-1f0a8cc7"
SOURCE_AUDIT_GO_EVENT_HASH = (
    "ff2db14b371ef465f34e6d14b731dd6a26f772bbe03667ecc5a5e5947b744f87")
SOURCE_IMPLEMENTATION_COMMIT = (
    "1e4cc64dab1b0f5dec71c80411367738c11ad37b")
SOURCE_OWNER_APPROVAL_EVENT_ID = "002363-31331680"
SOURCE_OWNER_APPROVAL_EVENT_HASH = (
    "72ba09c846394ddd88c0990ddbe2e97844d9f904ec92c6049220a688300bbbf3")
START_EVENT_ID = "002369-f0aac99a"
START_EVENT_HASH = (
    "52b784659bd4d3891ff0b45030577d4a6b440ba2e447bd66789381b351007996")
PAUSE_EVENT_ID = "002370-aa499bcb"
PAUSE_EVENT_HASH = (
    "15e17398bad01474bfffa1b98edc88f3b56122e19dc5d40ce1bc63434c43cc6b")
START_PREDECESSOR_HASH = (
    "8c5953ba24d80be1fbf0e3e393cf6af618f70f7871a46f7542fcb4fb97ab6db4")
START_TIMESTAMP = "2026-07-23T06:49:59.882Z"
PAUSE_TIMESTAMP = "2026-07-23T10:50:01.434Z"
PAUSE_REASON = (
    "wall/compute deadline 14400s exceeded — child process group killed")
SOURCE_SLICE_REQUEST_IDS = (
    "first-gladiator-m8-incomplete-closure-a-001",
    "first-gladiator-m8-incomplete-closure-b-001",
    "first-gladiator-m8-incomplete-closure-c-001",
    "first-gladiator-m8-incomplete-closure-d-001",
    "first-gladiator-m8-incomplete-closure-e-001",
)
AUTHORIZATION_DOMAIN = (
    "council:m8-budget-exhaustion-closure-authorization:v1")
TRANSACTION_DOMAIN = (
    "council:m8-budget-exhaustion-handoff-transaction:v1")
M8_EXPECTED_TEST_COUNT = 2387
VALIDATIONS = [
    "council_chain_verified",
    "closure_owner_approval_verified",
    "repository_clean_at_closure_tool_commit",
    "primary_inventory_verified",
    "terminal_ledgers_verified",
    "partial_attempt_verified_nonterminal",
    "coordinate_census_verified",
    "all_successes_replayed_provider_free",
    "primary_inventory_unchanged_after_replay",
    "derived_bundle_verified",
    "claim_ceiling_verified",
]
REQUEST_SCOPE = [
    "Audit the authenticated M8 budget-exhausted incomplete closure bundle.",
    "Confirm the 105-success, one-partial, 38-unattempted coordinate census.",
    "Confirm that no statistic or scientific M8 finding is emitted.",
]
REQUEST_QUESTIONS = [
    "Do the six derived files bind the unchanged primary evidence?",
    "Does provider-free replay succeed for all 105 successful runs?",
    "Is the only licensed outcome inconclusive and nonclaimable?",
]
REQUEST_ALLOWED_ACTIONS = [
    "Read the frozen primary evidence.",
    "Run provider-free replay and deterministic bundle verification.",
    "Run focused and full repository tests.",
    "Return RESULT_APPROVED or RESULT_BLOCKED.",
]
REQUEST_FORBIDDEN_ACTIONS = [
    "Do not contact a model or provider.",
    "Do not resume, retry, or alter the original M8 execution.",
    "Do not compute an order statistic or make an M8 scientific claim.",
    "Do not modify primary evidence or the derived bundle.",
]

_EVENT_ID = re.compile(r"^\d{6}-[0-9a-f]{8}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_UTC = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")

AUTH_FIELDS = {
    "schema_version", "profile_id", "source_request",
    "execution_authorization", "execution_authorization_hash",
    "terminal_events", "closure_tool", "closure_budget",
    "primary_evidence", "outcome", "derived_output_root",
}
SOURCE_FIELDS = {
    "request_id", "request_payload_hash", "publication_event_id",
    "publication_event_hash", "audit_go_event_id", "audit_go_event_hash",
    "owner_approval_event_id", "owner_approval_event_hash",
}
TERMINAL_FIELDS = {"start", "pause"}
START_FIELDS = {
    "event_id", "event_hash", "previous_event_hash", "timestamp_utc"}
PAUSE_FIELDS = START_FIELDS | {"reason"}
CLOSURE_TOOL_FIELDS = {"target_commit", "integration_events"}
INTEGRATION_FIELDS = {"request_id", "event_id", "event_hash", "target_commit"}
BUDGET_FIELDS = {
    "max_compute_minutes", "max_wall_minutes", "max_storage_mb",
    "max_replay_runs", "max_retries_per_run",
}
PRIMARY_FIELDS = {
    "evidence_root", "manifest", "manifest_sha256", "tombstone_ledger",
    "primary_file_count", "primary_inventory_content_hash",
    "coordinate_census_content_hash", "successful_runs", "partial_runs",
    "unattempted_runs", "tombstoned_runs", "terminal_outcomes", "partial",
}
PARTIAL_FIELDS = {
    "execution_index", "model", "scenario", "scenario_seed", "sampler_seed",
    "directory", "files", "sequence_start", "sequence_end",
    "completed_exposure_ids", "terminal_probe_present",
}


def _closed(value: object, fields: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        got = set(value) if isinstance(value, dict) else set()
        raise SchemaViolation(
            f"{label} keys differ: missing={sorted(fields-got)}, "
            f"unknown={sorted(got-fields)}")
    return value


def _hash(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise SchemaViolation(f"{label} must be lowercase sha256")
    return value


def _event_id(value: object, label: str) -> str:
    if not isinstance(value, str) or not _EVENT_ID.fullmatch(value):
        raise SchemaViolation(f"{label} must be a Council event id")
    return value


def _nonneg(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SchemaViolation(f"{label} must be a non-negative integer")
    return value


def _safe_relpath(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value.startswith(("/", "\\")) \
            or "\\" in value or "\x00" in value or ".." in value.split("/"):
        raise SchemaViolation(f"{label} must be a safe repository-relative path")
    return value


def closure_authorization_hash(authorization: dict) -> str:
    from tools.council.schemas import domain_hash
    return domain_hash(AUTHORIZATION_DOMAIN, authorization)


def validate_closure_authorization(auth: dict) -> None:
    _closed(auth, AUTH_FIELDS, "closure_authorization")
    if auth["schema_version"] != \
            "m8-budget-exhaustion-closure-authorization.v1" or \
            auth["profile_id"] != PROFILE_ID:
        raise SchemaViolation("closure authorization version/profile differs")

    source = _closed(auth["source_request"], SOURCE_FIELDS, "source_request")
    exact_source = {
        "request_id": SOURCE_REQUEST_ID,
        "request_payload_hash": SOURCE_REQUEST_PAYLOAD_HASH,
        "publication_event_id": SOURCE_PUBLICATION_EVENT_ID,
        "publication_event_hash": SOURCE_PUBLICATION_EVENT_HASH,
        "audit_go_event_id": SOURCE_AUDIT_GO_EVENT_ID,
        "audit_go_event_hash": SOURCE_AUDIT_GO_EVENT_HASH,
    }
    for field, expected in exact_source.items():
        if source[field] != expected:
            raise SchemaViolation(f"source_request.{field} differs")
    if source["owner_approval_event_id"] != SOURCE_OWNER_APPROVAL_EVENT_ID or \
            source["owner_approval_event_hash"] != \
            SOURCE_OWNER_APPROVAL_EVENT_HASH:
        raise SchemaViolation("source owner approval identity differs")

    from tools.council.schemas import (
        compute_execution_authorization_hash,
        validate_execution_authorization)
    validate_execution_authorization(auth["execution_authorization"])
    execution = auth["execution_authorization"]
    exact_execution = {
        "experiment_id": ir.EXPERIMENT_ID,
        "design_hash":
            "431871d3266a96999ef02d0d9eb77caba7e6b317135155d3161b1eecf396d533",
        "implementation_commit": SOURCE_IMPLEMENTATION_COMMIT,
        "experiment_config_hash":
            "4847cadfdac059195986114fed6d61850f3c1d925ca4b97618a06cff59e5c960",
        "planned_runs": 144,
        "budget": {
            "max_units": 144, "max_compute_minutes": 240,
            "max_wall_minutes": 240, "max_storage_mb": 1024,
            "max_retries_per_unit": 0, "max_scenarios": 3},
        "evidence_root": ir.EVIDENCE_ROOT,
        "manifest": ir.MANIFEST,
        "resume_from": None,
    }
    for field, expected in exact_execution.items():
        if execution[field] != expected:
            raise SchemaViolation(f"execution authorization {field} differs")
    if execution["model_digests"] != {
            "huihui_ai/qwen2.5-abliterate:7b-instruct":
            "103482475c9b4d4032999dd5d7383478cad8b966ae6ae984d525daf7352c2219"
            }:
        raise SchemaViolation("execution authorization model identity differs")
    if execution["source_integration_events"] != [
            "002351-a757f517", "002352-60b9033f", "002353-23a8b8e9",
            "002354-a86c0efb", "002355-c7998be4"]:
        raise SchemaViolation(
            "execution authorization source integrations differ")
    if auth["execution_authorization_hash"] != \
            compute_execution_authorization_hash(
                auth["execution_authorization"]):
        raise SchemaViolation("execution_authorization_hash differs")

    terminals = _closed(auth["terminal_events"], TERMINAL_FIELDS,
                        "terminal_events")
    start = _closed(terminals["start"], START_FIELDS, "terminal_events.start")
    pause = _closed(terminals["pause"], PAUSE_FIELDS, "terminal_events.pause")
    if start["event_id"] != START_EVENT_ID or \
            start["event_hash"] != START_EVENT_HASH or \
            pause["event_id"] != PAUSE_EVENT_ID or \
            pause["event_hash"] != PAUSE_EVENT_HASH:
        raise SchemaViolation("terminal event identity differs")
    for label, event in (("start", start), ("pause", pause)):
        _hash(event["previous_event_hash"],
              f"terminal_events.{label}.previous_event_hash")
        if not isinstance(event["timestamp_utc"], str) or \
                not _UTC.fullmatch(event["timestamp_utc"]):
            raise SchemaViolation(f"terminal_events.{label} timestamp malformed")
    if not isinstance(pause["reason"], str) or not pause["reason"]:
        raise SchemaViolation("pause reason must be non-empty")
    if start["previous_event_hash"] != START_PREDECESSOR_HASH or \
            start["timestamp_utc"] != START_TIMESTAMP or \
            pause["previous_event_hash"] != START_EVENT_HASH or \
            pause["timestamp_utc"] != PAUSE_TIMESTAMP or \
            pause["reason"] != PAUSE_REASON:
        raise SchemaViolation("terminal event predecessor/time/reason differs")

    tool = _closed(auth["closure_tool"], CLOSURE_TOOL_FIELDS, "closure_tool")
    if not isinstance(tool["target_commit"], str) or \
            not _COMMIT.fullmatch(tool["target_commit"]):
        raise SchemaViolation("closure_tool.target_commit must be a full commit")
    integrations = tool["integration_events"]
    if not isinstance(integrations, list) or len(integrations) != 5:
        raise SchemaViolation("closure tool requires exactly five integrations")
    if [item.get("request_id") for item in integrations
            if isinstance(item, dict)] != list(SOURCE_SLICE_REQUEST_IDS):
        raise SchemaViolation("closure integrations are not exact A-E order")
    for item in integrations:
        _closed(item, INTEGRATION_FIELDS, "integration_event")
        _event_id(item["event_id"], "integration_event.event_id")
        _hash(item["event_hash"], "integration_event.event_hash")
        if item["target_commit"] != tool["target_commit"]:
            raise SchemaViolation("integration event commit differs")

    budget = _closed(auth["closure_budget"], BUDGET_FIELDS, "closure_budget")
    original = auth["execution_authorization"]["budget"]
    for field in ("max_compute_minutes", "max_wall_minutes", "max_storage_mb"):
        value = budget[field]
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0 \
                or value > original[field]:
            raise SchemaViolation(
                f"closure_budget.{field} must be positive and within original")
    if budget["max_replay_runs"] != 105 or \
            budget["max_retries_per_run"] != 0:
        raise SchemaViolation("closure replay budget must be 105 with zero retries")

    primary = _closed(auth["primary_evidence"], PRIMARY_FIELDS,
                      "primary_evidence")
    exact_primary = {
        "evidence_root": ir.EVIDENCE_ROOT,
        "manifest": ir.MANIFEST,
        "manifest_sha256": ir.MANIFEST_SHA256,
        "tombstone_ledger": {"state": "absent", "sha256": None},
        "primary_file_count": ir.PRIMARY_FILE_COUNT,
        "primary_inventory_content_hash": ir.PRIMARY_INVENTORY_CONTENT_HASH,
        "coordinate_census_content_hash": ir.COORDINATE_CENSUS_CONTENT_HASH,
        "successful_runs": 105, "partial_runs": 1, "unattempted_runs": 38,
        "tombstoned_runs": 0, "terminal_outcomes": 105,
    }
    for field, expected in exact_primary.items():
        if primary[field] != expected:
            raise SchemaViolation(f"primary_evidence.{field} differs")
    partial = _closed(primary["partial"], PARTIAL_FIELDS,
                      "primary_evidence.partial")
    exact_partial_coord = {
        "execution_index": 105,
        "model": "huihui_ai/qwen2.5-abliterate:7b-instruct",
        "scenario": "scramble_dev_m8",
        "scenario_seed": 1,
        "sampler_seed": 2012,
    }
    if any(partial[field] != value
           for field, value in exact_partial_coord.items()) or \
            partial["sequence_start"] != 0 or partial["sequence_end"] != 5 or \
            partial["completed_exposure_ids"] != ["e_trust", "e_betrayal"] or \
            partial["terminal_probe_present"] is not False:
        raise SchemaViolation("partial attempt classification differs")
    _safe_relpath(partial["directory"], "partial.directory")
    files = partial["files"]
    if not isinstance(files, dict) or len(files) != 2:
        raise SchemaViolation("partial.files must contain exactly two paths")
    expected_digests = {ir.PARTIAL_SNAPSHOT_SHA256,
                        ir.PARTIAL_DECISIONS_SHA256}
    if set(files.values()) != expected_digests:
        raise SchemaViolation("partial file hashes differ")
    for path, digest in files.items():
        _safe_relpath(path, "partial.files path")
        _hash(digest, "partial.files digest")
    for field in ("execution_index", "scenario_seed", "sampler_seed"):
        _nonneg(partial[field], f"partial.{field}")
    for field in ("model", "scenario"):
        if not isinstance(partial[field], str) or not partial[field]:
            raise SchemaViolation(f"partial.{field} must be non-empty")

    if auth["outcome"] != ir.OUTCOME or \
            auth["derived_output_root"] != ir.DERIVED_OUTPUT_ROOT:
        raise SchemaViolation("closure outcome or derived root differs")


def validate_proposal_payload(payload: dict) -> None:
    _closed(payload, {
        "schema_version", "closure_authorization",
        "closure_authorization_hash"}, "approval-required payload")
    if payload["schema_version"] != "result-handoff-approval-required.v1":
        raise SchemaViolation("approval-required schema version differs")
    validate_closure_authorization(payload["closure_authorization"])
    if payload["closure_authorization_hash"] != \
            closure_authorization_hash(payload["closure_authorization"]):
        raise SchemaViolation("proposal closure authorization hash differs")


def validate_approval_payload(payload: dict) -> None:
    _closed(payload, {
        "schema_version", "approved_by", "approval_commit",
        "proposal_event_id", "proposal_event_hash", "closure_authorization",
        "closure_authorization_hash", "human_token"}, "approval payload")
    if payload["schema_version"] != "result-handoff-approval.v1" or \
            payload["approved_by"] != "human":
        raise SchemaViolation("result-handoff approval identity differs")
    if payload["approval_commit"] != \
            payload["closure_authorization"].get(
                "closure_tool", {}).get("target_commit"):
        raise SchemaViolation("approval commit differs from closure tool")
    _event_id(payload["proposal_event_id"], "proposal_event_id")
    _hash(payload["proposal_event_hash"], "proposal_event_hash")
    validate_closure_authorization(payload["closure_authorization"])
    if payload["closure_authorization_hash"] != \
            closure_authorization_hash(payload["closure_authorization"]):
        raise SchemaViolation("approval closure authorization hash differs")
    token = payload["human_token"]
    if not isinstance(token, dict):
        raise SchemaViolation("human_token must be an object")


def validate_approval_binding(chain: list[dict], event: dict) -> None:
    proposal = next((item for item in reversed(chain)
                     if item["request_id"] == event["request_id"] and
                     item["event_type"] ==
                     "RESULT_HANDOFF_APPROVAL_REQUIRED"), None)
    if proposal is None:
        raise CouncilError("result-handoff approval has no proposal")
    payload = event["payload"]
    if payload["proposal_event_id"] != proposal["event_id"] or \
            payload["proposal_event_hash"] != proposal["event_hash"] or \
            payload["closure_authorization"] != \
            proposal["payload"]["closure_authorization"] or \
            payload["closure_authorization_hash"] != \
            proposal["payload"]["closure_authorization_hash"]:
        raise CouncilError(
            "result-handoff approval does not exactly copy its proposal")
    if event["target_commit"] != proposal["target_commit"] or \
            payload["approval_commit"] != proposal["target_commit"]:
        raise CouncilError("result-handoff approval commit differs")


def validate_ready_binding(chain: list[dict], event: dict) -> None:
    request = event["payload"]["request"]
    profile = request.get("authorization_profile", {}).get("profile_id")
    if profile != PROFILE_ID:
        return
    approvals = [item for item in chain
                 if item["request_id"] == event["request_id"] and
                 item["event_type"] == "RESULT_HANDOFF_APPROVED"]
    if len(approvals) != 1:
        raise CouncilError("M8 ready event requires exactly one owner approval")
    approval = approvals[0]
    if request.get("closure_authorization") != \
            approval["payload"]["closure_authorization"] or \
            request.get("closure_authorization_hash") != \
            approval["payload"]["closure_authorization_hash"] or \
            request["authorization_profile"].get(
                "closure_owner_approval_event_id") != approval["event_id"] or \
            request["authorization_profile"].get(
                "closure_owner_approval_event_hash") != approval["event_hash"]:
        raise CouncilError("M8 ready request differs from owner approval")


def transaction_id(request_id: str, proposal: dict, approval: dict,
                   authorization_hash: str, commit: str) -> str:
    from tools.council.schemas import domain_hash
    return domain_hash(TRANSACTION_DOMAIN, {
        "request_id": request_id,
        "proposal_event_id": proposal["event_id"],
        "proposal_event_hash": proposal["event_hash"],
        "owner_approval_event_id": approval["event_id"],
        "owner_approval_event_hash": approval["event_hash"],
        "closure_authorization_hash": authorization_hash,
        "closure_tool_commit": commit,
    })


M8_REQUEST_EXTRA_FIELDS = {
    "task_kind", "run_id", "run_dir", "manifest_file",
    "evidence_inventory_hash", "validations", "validation_report_hash",
    "result_config", "experiment_config_hash", "authorization_profile",
    "closure_authorization", "closure_authorization_hash",
    "derived_artifact_hashes", "result_artifacts", "conclusion_scope",
}


def validate_m8_handoff_request(request: dict) -> None:
    from tools.council.schemas import (
        FULL_TEST_COMMAND, REQUEST_REQUIRED_FIELDS, domain_hash,
        validate_result_artifacts)

    expected = set(REQUEST_REQUIRED_FIELDS) | M8_REQUEST_EXTRA_FIELDS
    if set(request) != expected:
        raise SchemaViolation(
            "M8 result request has missing or unknown keys: "
            f"missing={sorted(expected-set(request))}, "
            f"unknown={sorted(set(request)-expected)}")
    auth_profile = _closed(request["authorization_profile"], {
        "profile_id", "closure_authorization_hash",
        "closure_owner_approval_event_id",
        "closure_owner_approval_event_hash"}, "authorization_profile")
    if auth_profile["profile_id"] != PROFILE_ID:
        raise SchemaViolation("M8 authorization profile differs")
    _event_id(auth_profile["closure_owner_approval_event_id"],
              "closure_owner_approval_event_id")
    _hash(auth_profile["closure_owner_approval_event_hash"],
          "closure_owner_approval_event_hash")
    validate_closure_authorization(request["closure_authorization"])
    if request["closure_authorization_hash"] != \
            closure_authorization_hash(request["closure_authorization"]) or \
            auth_profile["closure_authorization_hash"] != \
            request["closure_authorization_hash"]:
        raise SchemaViolation("M8 closure authorization hash differs")
    if request["request_id"] != RESULT_REQUEST_ID or \
            request["target_commit"] != request["closure_authorization"][
                "closure_tool"]["target_commit"] or \
            request["task_kind"] != "result_handoff" or \
            request["run_id"] != ir.RUN_ID or \
            request["run_dir"] != ir.DERIVED_OUTPUT_ROOT or \
            request["manifest_file"] != \
            f"{ir.DERIVED_OUTPUT_ROOT}/primary_inventory.json" or \
            request["conclusion_scope"] != ir.OUTCOME["conclusion_scope"]:
        raise SchemaViolation("M8 result request identity differs")
    if request["expected_test_command"] != FULL_TEST_COMMAND or \
            request["expected_test_count"] != M8_EXPECTED_TEST_COUNT:
        raise SchemaViolation("M8 request full-suite binding differs")
    exact_lists = {
        "scope": REQUEST_SCOPE,
        "questions": REQUEST_QUESTIONS,
        "allowed_actions": REQUEST_ALLOWED_ACTIONS,
        "forbidden_actions": REQUEST_FORBIDDEN_ACTIONS,
        "requested_verdicts": ["RESULT_APPROVED", "RESULT_BLOCKED"],
        "validations": VALIDATIONS,
    }
    for field, expected_value in exact_lists.items():
        if request[field] != expected_value:
            raise SchemaViolation(f"M8 request {field} differs")
    hashes = request["derived_artifact_hashes"]
    if not isinstance(hashes, dict) or set(hashes) != set(ir.DERIVED_FILENAMES):
        raise SchemaViolation("derived_artifact_hashes must name six files")
    for value in hashes.values():
        _hash(value, "derived artifact hash")
    bundle_hash = ir.derived_bundle_hash(hashes)
    if request["evidence_inventory_hash"] != bundle_hash:
        raise SchemaViolation("derived bundle content hash differs")
    config = _closed(request["result_config"], {
        "schema_version", "profile_id", "closure_authorization_hash",
        "derived_bundle_content_hash", "result_artifacts",
        "conclusion_scope"}, "result_config")
    if config["schema_version"] != \
            "m8-budget-exhaustion-result-config.v1" or \
            config["profile_id"] != PROFILE_ID or \
            config["closure_authorization_hash"] != \
            request["closure_authorization_hash"] or \
            config["derived_bundle_content_hash"] != bundle_hash or \
            config["conclusion_scope"] != request["conclusion_scope"]:
        raise SchemaViolation("M8 result_config differs")
    validate_result_artifacts(request["result_artifacts"])
    if config["result_artifacts"] != request["result_artifacts"]:
        raise SchemaViolation("result_config artifact record differs")
    artifacts = request["result_artifacts"]
    source = request["closure_authorization"]["source_request"]
    primary = request["closure_authorization"]["primary_evidence"]
    exact_artifacts = {
        "schema_version": "result-artifacts.v2",
        "profile_id": PROFILE_ID,
        "source_request_id": source["request_id"],
        "source_request_payload_hash": source["request_payload_hash"],
        "source_owner_approval_event_id": source["owner_approval_event_id"],
        "source_owner_approval_event_hash":
            source["owner_approval_event_hash"],
        "start_event_id": request["closure_authorization"][
            "terminal_events"]["start"]["event_id"],
        "start_event_hash": request["closure_authorization"][
            "terminal_events"]["start"]["event_hash"],
        "pause_event_id": request["closure_authorization"][
            "terminal_events"]["pause"]["event_id"],
        "pause_event_hash": request["closure_authorization"][
            "terminal_events"]["pause"]["event_hash"],
        "closure_owner_approval_event_id":
            auth_profile["closure_owner_approval_event_id"],
        "closure_owner_approval_event_hash":
            auth_profile["closure_owner_approval_event_hash"],
        "closure_authorization_hash":
            request["closure_authorization_hash"],
        "closure_tool_commit": request["target_commit"],
        "derived_output_root": ir.DERIVED_OUTPUT_ROOT,
        "analysis_status": "budget_exhausted_incomplete",
        "statistics_computed": False,
        "planned_runs": 144,
        "successful_runs": 105,
        "partial_runs": 1,
        "unattempted_runs": 38,
        "tombstoned_runs": 0,
        "terminal_outcomes": 105,
        "manifest_sha256": primary["manifest_sha256"],
        "tombstone_ledger": primary["tombstone_ledger"],
        "primary_inventory_file_sha256":
            hashes["primary_inventory.json"],
        "primary_inventory_content_hash":
            primary["primary_inventory_content_hash"],
        "replay_attestation_sha256": hashes["replay_attestation.json"],
        "coordinate_census_file_sha256":
            hashes["coordinate_census.json"],
        "coordinate_census_content_hash":
            primary["coordinate_census_content_hash"],
        "incomplete_report_sha256": hashes["incomplete_report.json"],
        "incomplete_result_package_file_sha256":
            hashes["incomplete_result_package.json"],
        # The package content identity is verified from the actual package
        # bytes below. At schema time it is already closed/type checked.
        "incomplete_result_package_content_sha256":
            artifacts["incomplete_result_package_content_sha256"],
        "validation_report_sha256": hashes["validation_report.json"],
        "derived_bundle_content_hash": bundle_hash,
    }
    if artifacts != exact_artifacts:
        raise SchemaViolation(
            "result-artifacts.v2 does not exactly bind closure/request bytes")
    if request["experiment_config_hash"] != domain_hash(
            "council:result-handoff-config:v1", config):
        raise SchemaViolation("experiment_config_hash does not bind config")
    from tools.autonomy.runner import validation_report_hash
    if request["validation_report_hash"] != \
            validation_report_hash(request["validations"]):
        raise SchemaViolation("validation_report_hash does not bind validations")


def _event(chain: list[dict], event_id: str, event_hash: str,
           event_type: str, request_id: str) -> dict:
    found = next((item for item in chain if item["event_id"] == event_id), None)
    if found is None or found["event_hash"] != event_hash or \
            found["event_type"] != event_type or \
            found["request_id"] != request_id:
        raise CouncilError(f"Council binding {event_id} differs")
    return found


def _source_authority(chain: list[dict]) -> tuple[dict, dict, dict, dict]:
    publication = _event(
        chain, SOURCE_PUBLICATION_EVENT_ID, SOURCE_PUBLICATION_EVENT_HASH,
        "AUDIT_REQUESTED", SOURCE_REQUEST_ID)
    audit_go = _event(
        chain, SOURCE_AUDIT_GO_EVENT_ID, SOURCE_AUDIT_GO_EVENT_HASH,
        "AUDIT_GO", SOURCE_REQUEST_ID)
    owner = next((item for item in chain
                  if item["request_id"] == SOURCE_REQUEST_ID and
                  item["event_type"] == "EXPERIMENT_APPROVED"), None)
    if owner is None or owner["event_id"] != SOURCE_OWNER_APPROVAL_EVENT_ID or \
            owner["event_hash"] != SOURCE_OWNER_APPROVAL_EVENT_HASH or \
            owner["payload"].get("request_payload_hash") != \
            SOURCE_REQUEST_PAYLOAD_HASH:
        raise CouncilError("source owner approval differs")
    start = _event(chain, START_EVENT_ID, START_EVENT_HASH,
                   "EXPERIMENT_STARTED", SOURCE_REQUEST_ID)
    pause = _event(chain, PAUSE_EVENT_ID, PAUSE_EVENT_HASH,
                   "AUTONOMY_PAUSED", SOURCE_REQUEST_ID)
    if pause["previous_event_hash"] != start["event_hash"]:
        raise CouncilError("pause is not the immediate successor of start")
    return publication, audit_go, owner, pause


def _closure_integrations(chain: list[dict], commit: str) -> list[dict]:
    result = []
    for request_id in SOURCE_SLICE_REQUEST_IDS:
        matching = [item for item in chain
                    if item["request_id"] == request_id and
                    item["event_type"] == "CHANGE_INTEGRATED"]
        if len(matching) != 1 or matching[0]["target_commit"] != commit:
            raise CouncilError(
                f"{request_id} lacks one same-commit integration")
        go = next((item for item in chain
                   if item["request_id"] == request_id and
                   item["event_type"] == "AUDIT_GO" and
                   item["target_commit"] == commit), None)
        if go is None or go["payload"].get("conditions") != []:
            raise CouncilError(f"{request_id} lacks a fresh plain GO")
        integration = matching[0]
        if integration["payload"].get("audit_go_event") != go["event_id"]:
            raise CouncilError(f"{request_id} integration does not bind its GO")
        result.append({
            "request_id": request_id,
            "event_id": integration["event_id"],
            "event_hash": integration["event_hash"],
            "target_commit": commit,
        })
    return result


def _derive_primary_locked(repo: str, locked_manifest: str,
                           evidence_root: str, planned_design: dict) -> dict:
    sweep = importlib.import_module("coliseum.textlab.sweep")
    successes, tombstones = sweep.terminal_ledgers_load(
        locked_manifest, evidence_root, planned_design=planned_design,
        require_tombstone_regime_anchors=True)
    if tombstones or sweep.tombstone_ledger_identity(locked_manifest) != \
            {"state": "absent", "sha256": None}:
        raise CouncilError("budget-exhausted closure requires no tombstones")
    rows = list(successes.values())
    if len(rows) != 105 or ir.file_sha256(locked_manifest) != \
            ir.MANIFEST_SHA256:
        raise CouncilError("success manifest identity/count differs")
    success_dirs = {row["dir"] for row in rows}
    all_dirs = {
        name for name in os.listdir(evidence_root)
        if os.path.isdir(os.path.join(evidence_root, name)) and
        not os.path.islink(os.path.join(evidence_root, name))}
    partial_dirs = all_dirs - success_dirs
    if len(partial_dirs) != 1:
        raise CouncilError("primary tree must contain one partial directory")
    partial_dir = partial_dirs.pop()
    expected_dirs = {"": {"manifest.jsonl"}}
    for dirname in success_dirs:
        expected_dirs[dirname] = {
            "scenario.snapshot.json", "decisions.jsonl",
            "captures.jsonl", "run.json"}
    expected_dirs[partial_dir] = {
        "scenario.snapshot.json", "decisions.jsonl"}
    inventory = ir.primary_inventory(
        evidence_root, expected_dirs=expected_dirs)
    if inventory["file_count"] != ir.PRIMARY_FILE_COUNT or \
            inventory["content_hash"] != ir.PRIMARY_INVENTORY_CONTENT_HASH:
        raise CouncilError("primary inventory identity differs")
    partial_abs = os.path.join(evidence_root, partial_dir)
    snapshot_path = os.path.join(partial_abs, "scenario.snapshot.json")
    decisions_path = os.path.join(partial_abs, "decisions.jsonl")
    if ir.file_sha256(snapshot_path) != ir.PARTIAL_SNAPSHOT_SHA256 or \
            ir.file_sha256(decisions_path) != ir.PARTIAL_DECISIONS_SHA256:
        raise CouncilError("partial attempt bytes differ")
    ir.validate_partial_decisions(decisions_path)
    coordinate = ir.planned_coordinates(planned_design)[105]
    partial = {
        **coordinate,
        "directory": f"{ir.EVIDENCE_ROOT}/{partial_dir}",
        "files": {
            f"{ir.EVIDENCE_ROOT}/{partial_dir}/decisions.jsonl":
                ir.PARTIAL_DECISIONS_SHA256,
            f"{ir.EVIDENCE_ROOT}/{partial_dir}/scenario.snapshot.json":
                ir.PARTIAL_SNAPSHOT_SHA256,
        },
        "sequence_start": 0,
        "sequence_end": 5,
        "completed_exposure_ids": ["e_trust", "e_betrayal"],
        "terminal_probe_present": False,
    }
    census = ir.build_coordinate_census(planned_design, rows, partial)
    if census["content_hash"] != ir.COORDINATE_CENSUS_CONTENT_HASH:
        raise CouncilError("coordinate census identity differs")
    primary = {
            "evidence_root": ir.EVIDENCE_ROOT,
            "manifest": ir.MANIFEST,
            "manifest_sha256": ir.MANIFEST_SHA256,
            "tombstone_ledger": {"state": "absent", "sha256": None},
            "primary_file_count": ir.PRIMARY_FILE_COUNT,
            "primary_inventory_content_hash":
                ir.PRIMARY_INVENTORY_CONTENT_HASH,
            "coordinate_census_content_hash":
                ir.COORDINATE_CENSUS_CONTENT_HASH,
            "successful_runs": 105,
            "partial_runs": 1,
            "unattempted_runs": 38,
            "tombstoned_runs": 0,
            "terminal_outcomes": 105,
            "partial": partial,
    }
    return {
        "primary": primary,
        "inventory": inventory,
        "census": census,
        "success_rows": rows,
        "expected_dirs": expected_dirs,
    }


def _derive_primary(repo: str) -> dict:
    """Read and authenticate the primary tree while holding its pack lock."""
    sweep = importlib.import_module("coliseum.textlab.sweep")
    registry = importlib.import_module("coliseum.textlab.registry")
    evidence_root = ir.safe_repo_path(repo, ir.EVIDENCE_ROOT)
    manifest_path = ir.safe_repo_path(repo, ir.MANIFEST)
    bundle = registry.load_verified_bundle(
        os.path.join(repo, "configs", "registry", "experiments.yaml"),
        ir.EXPERIMENT_ID)
    with sweep._manifest_advisory_lock(manifest_path) as locked_manifest:
        return _derive_primary_locked(
            repo, locked_manifest, evidence_root,
            bundle.planned_design)["primary"]


def build_closure_authorization(root: str, cfg, commit: str,
                                max_compute_minutes: int,
                                max_wall_minutes: int,
                                max_storage_mb: int,
                                *, primary_deriver=None) -> dict:
    """Build the proposal authorization; no derived output is written."""
    from tools.council import events, git_state, state_machine
    from tools.council.schemas import compute_execution_authorization_hash

    if not _COMMIT.fullmatch(str(commit)):
        raise SchemaViolation("closure commit must be full lowercase hex")
    chain = events.read_chain(root)
    projection = state_machine.project(chain)
    if projection.get(SOURCE_REQUEST_ID, {}).get("state") != \
            state_machine.AUTONOMY_PAUSED:
        raise CouncilError("original M8 request is not autonomy_paused")
    if any(item["request_id"] == RESULT_REQUEST_ID for item in chain):
        raise CouncilError("M8 incomplete result request id is already used")
    publication, audit_go, owner, pause = _source_authority(chain)
    start = _event(chain, START_EVENT_ID, START_EVENT_HASH,
                   "EXPERIMENT_STARTED", SOURCE_REQUEST_ID)
    if sum(item["request_id"] == SOURCE_REQUEST_ID and
           item["event_type"] == "EXPERIMENT_STARTED" for item in chain) != 1:
        raise CouncilError("source execution start count differs")
    forbidden = {"EXPERIMENT_COMPLETE", "RESULT_AUDIT_REQUESTED",
                 "RESULT_APPROVED", "RESULT_BLOCKED"}
    if any(item["request_id"] == SOURCE_REQUEST_ID and
           item["event_type"] in forbidden for item in chain):
        raise CouncilError("source request already carries a result lifecycle")
    repo = publication["repository"]
    if git_state.head_commit(repo, cfg.repo_roots) != commit or \
            not git_state.is_clean(repo, cfg.repo_roots):
        raise CouncilError("closure proposal requires a clean exact HEAD")
    integrations = _closure_integrations(chain, commit)
    output = ir.safe_repo_path(repo, ir.DERIVED_OUTPUT_ROOT,
                               may_be_absent=True)
    if os.path.lexists(output):
        raise CouncilError("derived output root already exists before proposal")
    primary = (primary_deriver or _derive_primary)(repo)
    execution_authorization = owner["payload"]["execution_authorization"]
    authorization = {
        "schema_version":
            "m8-budget-exhaustion-closure-authorization.v1",
        "profile_id": PROFILE_ID,
        "source_request": {
            "request_id": SOURCE_REQUEST_ID,
            "request_payload_hash": SOURCE_REQUEST_PAYLOAD_HASH,
            "publication_event_id": publication["event_id"],
            "publication_event_hash": publication["event_hash"],
            "audit_go_event_id": audit_go["event_id"],
            "audit_go_event_hash": audit_go["event_hash"],
            "owner_approval_event_id": owner["event_id"],
            "owner_approval_event_hash": owner["event_hash"],
        },
        "execution_authorization": execution_authorization,
        "execution_authorization_hash":
            compute_execution_authorization_hash(execution_authorization),
        "terminal_events": {
            "start": {
                "event_id": start["event_id"],
                "event_hash": start["event_hash"],
                "previous_event_hash": start["previous_event_hash"],
                "timestamp_utc": start["timestamp_utc"],
            },
            "pause": {
                "event_id": pause["event_id"],
                "event_hash": pause["event_hash"],
                "previous_event_hash": pause["previous_event_hash"],
                "timestamp_utc": pause["timestamp_utc"],
                "reason": pause["payload"]["reason"],
            },
        },
        "closure_tool": {
            "target_commit": commit,
            "integration_events": integrations,
        },
        "closure_budget": {
            "max_compute_minutes": max_compute_minutes,
            "max_wall_minutes": max_wall_minutes,
            "max_storage_mb": max_storage_mb,
            "max_replay_runs": 105,
            "max_retries_per_run": 0,
        },
        "primary_evidence": primary,
        "outcome": ir.OUTCOME,
        "derived_output_root": ir.DERIVED_OUTPUT_ROOT,
    }
    validate_closure_authorization(authorization)
    return authorization


def validate_proposal_append(root: str, cfg, chain: list[dict],
                             event: dict) -> None:
    """Authoritative append-bound revalidation for an M8 proposal."""
    if event["request_id"] != RESULT_REQUEST_ID:
        raise CouncilError("M8 proposal request id differs")
    if any(item["request_id"] == RESULT_REQUEST_ID for item in chain):
        raise CouncilError("M8 proposal request id already has chain history")
    auth = event["payload"]["closure_authorization"]
    if event["target_commit"] != auth["closure_tool"]["target_commit"]:
        raise CouncilError("M8 proposal event commit differs")
    if event["repository"] not in cfg.repo_roots:
        raise CouncilError("M8 proposal repository differs from configured root")
    budget = auth["closure_budget"]
    expected = build_closure_authorization(
        root, cfg, event["target_commit"],
        budget["max_compute_minutes"], budget["max_wall_minutes"],
        budget["max_storage_mb"])
    if auth != expected or event["payload"]["closure_authorization_hash"] != \
            closure_authorization_hash(expected):
        raise CouncilError(
            "M8 proposal does not equal append-bound authoritative derivation")


def propose(root: str, cfg, request_id: str, commit: str,
            max_compute_minutes: int, max_wall_minutes: int,
            max_storage_mb: int, *, primary_deriver=None) -> dict:
    """Append only RESULT_HANDOFF_APPROVAL_REQUIRED."""
    from tools.council import events, locking
    if request_id != RESULT_REQUEST_ID:
        raise SchemaViolation(f"request id must be exactly {RESULT_REQUEST_ID}")
    lease = locking.acquire(root, "_m8_incomplete_handoff", SENDER,
                            request_id, kind="m8_incomplete_proposal")
    try:
        authorization = build_closure_authorization(
            root, cfg, commit, max_compute_minutes, max_wall_minutes,
            max_storage_mb, primary_deriver=primary_deriver)
        payload = {
            "schema_version": "result-handoff-approval-required.v1",
            "closure_authorization": authorization,
            "closure_authorization_hash":
                closure_authorization_hash(authorization),
        }
        return events.append_event(
            root, cfg, "RESULT_HANDOFF_APPROVAL_REQUIRED", SENDER,
            request_id, cfg.repo_roots[0], commit, payload)
    finally:
        locking.release(lease)


def approval_payload(chain: list[dict], request_id: str,
                     commit: str) -> dict:
    proposals = [item for item in chain
                 if item["request_id"] == request_id and
                 item["event_type"] == "RESULT_HANDOFF_APPROVAL_REQUIRED"]
    if len(proposals) != 1:
        raise CouncilError("result handoff requires exactly one proposal")
    proposal = proposals[0]
    if proposal["target_commit"] != commit:
        raise CouncilError("approval commit differs from proposal")
    return {
        "schema_version": "result-handoff-approval.v1",
        "approved_by": "human",
        "approval_commit": commit,
        "proposal_event_id": proposal["event_id"],
        "proposal_event_hash": proposal["event_hash"],
        "closure_authorization":
            proposal["payload"]["closure_authorization"],
        "closure_authorization_hash":
            proposal["payload"]["closure_authorization_hash"],
    }


def _artifact_objects(snapshot: dict, replay_core: dict, authorization: dict,
                      proposal: dict, approval: dict,
                      transaction: str) -> dict[str, dict]:
    replay = ir.replay_attestation(replay_core)
    report = ir.incomplete_report()
    first = {
        "primary_inventory.json": snapshot["inventory"],
        "replay_attestation.json": replay,
        "coordinate_census.json": snapshot["census"],
        "incomplete_report.json": report,
    }
    first_hashes = {
        name: __import__("hashlib").sha256(ir.json_bytes(value)).hexdigest()
        for name, value in first.items()
    }
    package_content = {
        "schema_version": "m8-budget-exhaustion-incomplete-package.v1",
        "transaction_id": transaction,
        "profile_id": PROFILE_ID,
        "source_request_id": SOURCE_REQUEST_ID,
        "source_implementation_commit": SOURCE_IMPLEMENTATION_COMMIT,
        "closure_tool_commit":
            authorization["closure_tool"]["target_commit"],
        "closure_authorization_hash":
            closure_authorization_hash(authorization),
        "proposal_event_id": proposal["event_id"],
        "proposal_event_hash": proposal["event_hash"],
        "closure_owner_approval_event_id": approval["event_id"],
        "closure_owner_approval_event_hash": approval["event_hash"],
        "primary_inventory_content_hash":
            authorization["primary_evidence"][
                "primary_inventory_content_hash"],
        "partial_files":
            authorization["primary_evidence"]["partial"]["files"],
        "artifact_hashes": first_hashes,
        "outcome": ir.OUTCOME,
    }
    package = dict(
        package_content,
        content_hash=ir.domain_hash(ir.PACKAGE_DOMAIN, package_content))
    validations = ir.validation_report(VALIDATIONS)
    return {
        **first,
        "incomplete_result_package.json": package,
        "validation_report.json": validations,
    }


def _artifact_bytes(objects: dict[str, dict]) -> dict[str, bytes]:
    if set(objects) != set(ir.DERIVED_FILENAMES):
        raise CouncilError("derived artifact object set differs")
    return {name: ir.json_bytes(objects[name])
            for name in ir.DERIVED_FILENAMES}


def _file_hashes(data: dict[str, bytes]) -> dict[str, str]:
    import hashlib
    return {name: hashlib.sha256(value).hexdigest()
            for name, value in data.items()}


def _verify_exact_bundle(path: str, expected: dict[str, bytes]) -> None:
    if not os.path.isdir(path) or os.path.islink(path) or \
            set(os.listdir(path)) != set(expected):
        raise CouncilError("existing derived bundle inventory differs")
    for name, want in expected.items():
        member = os.path.join(path, name)
        info = os.lstat(member)
        if not os.path.isfile(member) or os.path.islink(member) or \
                info.st_nlink != 1:
            raise CouncilError("derived bundle member is not an owned regular file")
        with open(member, "rb") as fh:
            if fh.read() != want:
                raise CouncilError("existing derived bundle bytes differ")


def _preflight_request_namespace(root: str, chain: list[dict]) -> None:
    from tools.council import storage
    allowed = {
        "RESULT_HANDOFF_APPROVAL_REQUIRED", "RESULT_HANDOFF_APPROVED"}
    uses = [item for item in chain if item["request_id"] == RESULT_REQUEST_ID]
    if [item["event_type"] for item in uses] != [
            "RESULT_HANDOFF_APPROVAL_REQUIRED", "RESULT_HANDOFF_APPROVED"] or \
            any(item["event_type"] not in allowed for item in uses):
        raise CouncilError("M8 result request chain prefix differs")
    for bucket in ("ready", "claimed", "complete"):
        path = storage.safe_request_path(root, bucket, RESULT_REQUEST_ID)
        if os.path.lexists(path):
            raise CouncilError(
                f"M8 result request already has a {bucket} lifecycle file")


def _source_rewind_paths(root: str, request_id: str, cycle: int,
                         request_sha256: str, verdict_sha256: str | None,
                         transaction_id: str) -> dict:
    if request_id not in SOURCE_SLICE_REQUEST_IDS:
        raise SchemaViolation("source rewind request id is outside the slice")
    if not isinstance(cycle, int) or isinstance(cycle, bool) or cycle < 1:
        raise SchemaViolation("source rewind cycle must be positive")
    for name, digest in (
            ("request", request_sha256), ("verdict", verdict_sha256),
            ("transaction", transaction_id)):
        if digest is not None and not _SHA256.fullmatch(digest):
            raise SchemaViolation(f"source rewind {name} digest is invalid")
    suffix = (
        f"cycle-{cycle}.{request_sha256[:16]}."
        f"{transaction_id[:16]}.superseded.json")
    return {
        "request_archive": os.path.join(
            root, "requests", "complete", f"{request_id}.{suffix}"),
        "verdict_archive": (
            os.path.join(root, "verdicts", f"{request_id}.{suffix}")
            if verdict_sha256 is not None else None),
        "journal": os.path.join(
            root, "txn",
            f"m8-source-rewind-{request_id}-{transaction_id}.json"),
    }


def _sha256_path(path: str) -> str:
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65_536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _archive_exact(source: str, archive: str, expected_sha256: str) -> None:
    source_exists = os.path.isfile(source)
    archive_exists = os.path.isfile(archive)
    if source_exists == archive_exists:
        raise CouncilError("source rewind archive state is ambiguous")
    current = archive if archive_exists else source
    if _sha256_path(current) != expected_sha256:
        raise CouncilError("source rewind archive bytes differ")
    if source_exists:
        os.rename(source, archive)


def _write_source_rewind_journal(path: str, journal: dict) -> None:
    from tools.council import storage
    os.makedirs(os.path.dirname(path), exist_ok=True)
    storage.atomic_write_json(path, journal)


def _read_source_rewind_journal(path: str) -> dict:
    from tools.council.strictjson import load_strict_file
    try:
        journal = load_strict_file(path, max_bytes=65_536)
    except (OSError, CouncilError, ValueError) as exc:
        raise CouncilError(f"source rewind journal unreadable: {exc}") from exc
    fields = {
        "schema_version", "request_id", "transaction_id", "owner_token",
        "prior_fix_started_count", "prior_state", "cycle",
        "request_sha256", "verdict_sha256", "last_event_id",
        "controlling_event_id", "repository", "target_commit", "completed"}
    if not isinstance(journal, dict) or set(journal) != fields or \
            journal["schema_version"] != "m8-source-rewind.v1" or \
            journal["request_id"] not in SOURCE_SLICE_REQUEST_IDS or \
            journal["prior_state"] not in ("requested", "blocked", "go") or \
            not _SHA256.fullmatch(str(journal["transaction_id"])) or \
            not isinstance(journal["owner_token"], str) or \
            len(journal["owner_token"]) != 32 or \
            not _EVENT_ID.fullmatch(str(journal["last_event_id"])) or \
            not _EVENT_ID.fullmatch(str(journal["controlling_event_id"])) or \
            not isinstance(journal["repository"], str) or \
            not _COMMIT.fullmatch(str(journal["target_commit"])) or \
            not isinstance(journal["prior_fix_started_count"], int) or \
            isinstance(journal["prior_fix_started_count"], bool) or \
            journal["prior_fix_started_count"] < 0 or \
            not isinstance(journal["completed"], list) or \
            any(step not in {
                "locked", "event", "request_archived", "verdict_archived"}
                for step in journal["completed"]):
        raise CouncilError("source rewind journal shape differs")
    paths = _source_rewind_paths(
        os.path.dirname(os.path.dirname(path)), journal["request_id"],
        journal["cycle"], journal["request_sha256"],
        journal["verdict_sha256"], journal["transaction_id"])
    if os.path.normpath(paths["journal"]) != os.path.normpath(path):
        raise CouncilError("source rewind journal path differs")
    return journal


def _source_rewind_journals(root: str, request_id: str) -> list[str]:
    if request_id not in SOURCE_SLICE_REQUEST_IDS:
        raise SchemaViolation("source rewind request id is outside the slice")
    directory = os.path.join(root, "txn")
    if not os.path.isdir(directory):
        return []
    prefix = f"m8-source-rewind-{request_id}-"
    return [
        os.path.join(directory, name)
        for name in sorted(os.listdir(directory))
        if name.startswith(prefix) and name.endswith(".json")]


def _recover_source_rewind(root: str, cfg, path: str,
                           force_owner: bool = False) -> tuple[str, dict | None]:
    """Recover one unique event-first request archive journal."""
    from tools.council import events, locking, storage

    if not os.path.exists(path):
        return "none", None
    journal = _read_source_rewind_journal(path)
    request_id = journal["request_id"]
    paths = _source_rewind_paths(
        root, request_id, journal["cycle"], journal["request_sha256"],
        journal["verdict_sha256"], journal["transaction_id"])
    token = journal["owner_token"]
    holder = locking.read_lock(root, request_id)
    if holder is not None:
        holder_matches = isinstance(holder, dict) and \
            holder.get("owner_token") == token
        if not holder_matches and "locked" in journal["completed"]:
            raise CouncilError("source rewind lock ownership differs")
        if holder_matches and not force_owner:
            expired = locking.lease_is_expired(holder)
            if expired is not True:
                return ("active" if expired is False else "blocked"), None
    chain = events.read_chain(root)
    fixes = [
        event for event in chain
        if event["request_id"] == request_id and
        event["event_type"] == "FIX_STARTED" and
        event.get("payload", {}).get("superseded_audit", {}).get(
            "transaction_id") == journal["transaction_id"]]
    landed = len(fixes) == 1
    source_bucket = (
        "ready" if journal["prior_state"] == "requested" else "complete")
    request_source = storage.safe_request_path(
        root, source_bucket, request_id)
    verdict_source = storage.verdict_path(root, request_id)
    if landed:
        _archive_exact(
            request_source, paths["request_archive"],
            journal["request_sha256"])
        if journal["verdict_sha256"] is not None:
            _archive_exact(
                verdict_source, paths["verdict_archive"],
                journal["verdict_sha256"])
        outcome, event = "forward", fixes[-1]
    else:
        if os.path.exists(paths["request_archive"]) or \
                (paths["verdict_archive"] is not None and
                 os.path.exists(paths["verdict_archive"])):
            raise CouncilError("source rewind archive exists without event")
        outcome, event = "back", None
    try:
        os.unlink(path)
    except OSError:
        pass
    locking.release(locking.Lock(
        path=storage.lock_path(root, request_id), name=request_id,
        role=SENDER, root=root, owner_token=token))
    return outcome, event


def _recover_source_rewinds(root: str, cfg, request_id: str) \
        -> tuple[str, dict | None]:
    forward = None
    for path in _source_rewind_journals(root, request_id):
        outcome, event = _recover_source_rewind(root, cfg, path)
        if outcome in ("active", "blocked"):
            return outcome, None
        if outcome == "forward":
            forward = event
    return ("forward", forward) if forward is not None else ("none", None)


def _source_rewind_expected(root: str, chain: list[dict], journal: dict,
                            request: dict, publication: dict,
                            verdict: dict | None) -> dict:
    paths = _source_rewind_paths(
        root, journal["request_id"], journal["cycle"],
        journal["request_sha256"], journal["verdict_sha256"],
        journal["transaction_id"])
    return {
        "transaction_id": journal["transaction_id"],
        "prior_state": journal["prior_state"],
        "audit_cycle": journal["cycle"],
        "publication_event_id": publication["event_id"],
        "publication_event_hash": publication["event_hash"],
        "request_payload_hash": request["request_payload_hash"],
        "request_file_sha256": journal["request_sha256"],
        "request_archive": os.path.relpath(paths["request_archive"], root),
        "verdict_event_id": verdict["event_id"] if verdict else None,
        "verdict_event_hash": verdict["event_hash"] if verdict else None,
        "verdict_file_sha256": journal["verdict_sha256"],
        "verdict_archive": (
            os.path.relpath(paths["verdict_archive"], root)
            if paths["verdict_archive"] else None),
    }


def validate_source_rewind_append(root: str, cfg, chain: list[dict],
                                  event: dict) -> None:
    """Authoritative boundary for the five exact source rewinds."""
    from tools.council import locking, state_machine, storage
    from tools.council.schemas import validate_request
    from tools.council.strictjson import loads_strict

    request_id = event["request_id"]
    if request_id not in SOURCE_SLICE_REQUEST_IDS:
        return
    projected = state_machine.project(chain).get(request_id)
    if projected is None or projected["state"] not in (
            state_machine.REQUESTED, state_machine.BLOCKED, state_machine.GO):
        return
    nested = event.get("payload", {}).get("superseded_audit")
    transaction_id = nested.get("transaction_id") \
        if isinstance(nested, dict) else None
    if not isinstance(transaction_id, str) or \
            not _SHA256.fullmatch(transaction_id):
        raise CouncilError("source rewind transaction binding is absent")
    # The journal path is derived from event-bound values; no caller path.
    dummy = _source_rewind_paths(
        root, request_id, nested.get("audit_cycle"),
        nested.get("request_file_sha256"),
        nested.get("verdict_file_sha256"), transaction_id)
    journal = _read_source_rewind_journal(dummy["journal"])
    if journal["completed"] != ["locked"] or \
            journal["last_event_id"] != projected["last_event_id"] or \
            journal["prior_state"] != projected["state"] or \
            journal["cycle"] != projected["audit_cycles"] or \
            journal["prior_fix_started_count"] != sum(
                1 for item in chain
                if item["request_id"] == request_id and
                item["event_type"] == "FIX_STARTED") or \
            journal["repository"] != event["repository"] or \
            journal["target_commit"] != event["target_commit"] or \
            journal["controlling_event_id"] != \
            event["payload"].get("controlling_event_id"):
        raise CouncilError("source rewind journal binding differs")
    holder = locking.read_lock(root, request_id)
    if not isinstance(holder, dict) or \
            holder.get("owner_token") != journal["owner_token"] or \
            holder.get("role") != SENDER or \
            holder.get("kind") != "source_audit_supersession":
        raise CouncilError("source rewind request lock differs")
    control = next((
        item for item in chain
        if item["event_id"] == journal["controlling_event_id"]), None)
    if control is None or control["event_type"] != "AUDIT_BLOCKED" or \
            control["target_commit"] != event["target_commit"]:
        raise CouncilError("source rewind controlling verdict differs")
    source_bucket = (
        "ready" if projected["state"] == state_machine.REQUESTED
        else "complete")
    request_path = storage.safe_request_path(
        root, source_bucket, request_id)
    if not os.path.isfile(request_path) or os.path.lexists(
            storage.safe_request_path(root, "claimed", request_id)) or \
            _sha256_path(request_path) != journal["request_sha256"]:
        raise CouncilError("source rewind request bytes differ")
    with open(request_path, "rb") as fh:
        request = loads_strict(fh.read(), max_bytes=262_144)
    validate_request(request, cfg.repo_roots)
    if request["request_id"] != request_id or \
            request["repository"] != event["repository"] or \
            request["target_commit"] != event["target_commit"] or \
            request.get("task_kind") != "source":
        raise CouncilError("source rewind request identity differs")
    publication = next((
        item for item in reversed(chain)
        if item["request_id"] == request_id and
        item["event_type"] in ("AUDIT_REQUESTED", "READY_FOR_REAUDIT")),
        None)
    verdict = next((
        item for item in reversed(chain)
        if item["request_id"] == request_id and
        item["event_type"] in (
            "AUDIT_BLOCKED", "AUDIT_GO", "AUDIT_GO_WITH_CONDITIONS")),
        None)
    if publication is None or (
            projected["state"] != state_machine.REQUESTED and verdict is None):
        raise CouncilError("source rewind lineage differs")
    if journal["verdict_sha256"] is not None:
        verdict_path = storage.verdict_path(root, request_id)
        if not os.path.isfile(verdict_path) or \
                _sha256_path(verdict_path) != journal["verdict_sha256"]:
            raise CouncilError("source rewind verdict bytes differ")
        with open(verdict_path, "rb") as fh:
            verdict_payload = loads_strict(
                fh.read(), max_bytes=1_048_576)
        if verdict is None or verdict_payload != verdict["payload"]:
            raise CouncilError("source rewind verdict artifact differs")
    paths = _source_rewind_paths(
        root, request_id, journal["cycle"], journal["request_sha256"],
        journal["verdict_sha256"], journal["transaction_id"])
    if os.path.lexists(paths["request_archive"]) or \
            (paths["verdict_archive"] is not None and
             os.path.lexists(paths["verdict_archive"])):
        raise CouncilError("source rewind archive already exists")
    expected = _source_rewind_expected(
        root, chain, journal, request, publication, verdict)
    if nested != expected or set(event["payload"]) != {
            "originating_blocked_commit", "blockers_addressed",
            "controlling_event_id", "superseded_audit"} or \
            event["payload"]["originating_blocked_commit"] != \
            event["target_commit"] or \
            not isinstance(event["payload"]["blockers_addressed"], list) or \
            len(event["payload"]["blockers_addressed"]) != 1 or \
            not isinstance(event["payload"]["blockers_addressed"][0], str) or \
            not event["payload"]["blockers_addressed"][0]:
        raise CouncilError("source rewind event payload differs")


def supersede_source_audit(root: str, cfg, request_id: str, repository: str,
                           target_commit: str, reason: str,
                           controlling_event_id: str,
                           _fault=None, _lease_seconds: float = 3600.0) -> dict:
    """Rewind one pending/terminal source audit without racing a claim."""
    import secrets
    from tools.council import events, locking, state_machine, storage
    from tools.council.schemas import validate_request
    from tools.council.strictjson import loads_strict

    if request_id not in SOURCE_SLICE_REQUEST_IDS:
        raise SchemaViolation("source rewind request id is outside the slice")
    recovered, recovered_event = _recover_source_rewinds(
        root, cfg, request_id)
    if recovered == "forward":
        return recovered_event
    if recovered in ("active", "blocked"):
        raise CouncilError("source rewind recovery is not yet available")
    if not isinstance(reason, str) or not reason:
        raise SchemaViolation("source rewind requires a nonempty reason")
    chain = events.read_chain(root)
    control = next((
        event for event in chain
        if event["event_id"] == controlling_event_id), None)
    if control is None or control["event_type"] != "AUDIT_BLOCKED" or \
            control["target_commit"] != target_commit:
        raise SchemaViolation(
            "controlling event must be the same-commit blocked verdict")
    projected = state_machine.project(chain).get(request_id)
    if projected is None or projected["state"] not in (
            state_machine.REQUESTED, state_machine.BLOCKED, state_machine.GO):
        raise CouncilError(
            "source rewind requires requested, blocked, or unintegrated go")
    prior_state = projected["state"]
    if projected["target_commit"] != target_commit:
        raise CouncilError("source rewind target commit differs")
    source_bucket = "ready" if prior_state == state_machine.REQUESTED \
        else "complete"
    source_path = storage.safe_request_path(
        root, source_bucket, request_id)
    claimed_path = storage.safe_request_path(root, "claimed", request_id)
    if not os.path.isfile(source_path) or os.path.lexists(claimed_path):
        raise CouncilError("source rewind request is absent or claimed")
    with open(source_path, "rb") as fh:
        request_bytes = fh.read()
    request = loads_strict(request_bytes, max_bytes=262_144)
    validate_request(request, cfg.repo_roots)
    if request["request_id"] != request_id or \
            request["repository"] != repository or \
            request["target_commit"] != target_commit or \
            request.get("task_kind") != "source":
        raise CouncilError("source rewind request binding differs")
    request_sha256 = __import__("hashlib").sha256(
        request_bytes).hexdigest()
    publication = next((
        event for event in reversed(chain)
        if event["request_id"] == request_id and
        event["event_type"] in ("AUDIT_REQUESTED", "READY_FOR_REAUDIT")),
        None)
    verdict = next((
        event for event in reversed(chain)
        if event["request_id"] == request_id and
        event["event_type"] in (
            "AUDIT_BLOCKED", "AUDIT_GO", "AUDIT_GO_WITH_CONDITIONS")),
        None)
    verdict_path = storage.verdict_path(root, request_id)
    verdict_sha256 = None
    if prior_state != state_machine.REQUESTED:
        if verdict is None or not os.path.isfile(verdict_path):
            raise CouncilError("source rewind verdict artifact is absent")
        with open(verdict_path, "rb") as fh:
            recorded_verdict = loads_strict(fh.read(), max_bytes=1_048_576)
        if recorded_verdict != verdict["payload"]:
            raise CouncilError("source rewind verdict artifact differs")
        verdict_sha256 = _sha256_path(verdict_path)
    cycle = projected["audit_cycles"]
    token = secrets.token_hex(16)
    transaction_id = __import__("hashlib").sha256(
        f"m8-source-rewind:{request_id}:{token}".encode()).hexdigest()
    paths = _source_rewind_paths(
        root, request_id, cycle, request_sha256, verdict_sha256,
        transaction_id)
    if publication is None or any(
            os.path.lexists(path) for name, path in paths.items()
            if name != "journal" and path is not None):
        raise CouncilError("source rewind publication/archive differs")
    journal = {
        "schema_version": "m8-source-rewind.v1",
        "request_id": request_id,
        "transaction_id": transaction_id,
        "owner_token": token,
        "prior_fix_started_count": sum(
            1 for event in chain if event["request_id"] == request_id and
            event["event_type"] == "FIX_STARTED"),
        "prior_state": prior_state,
        "cycle": cycle,
        "request_sha256": request_sha256,
        "verdict_sha256": verdict_sha256,
        "last_event_id": projected["last_event_id"],
        "controlling_event_id": controlling_event_id,
        "repository": repository,
        "target_commit": target_commit,
        "completed": [],
    }
    _write_source_rewind_journal(paths["journal"], journal)
    if _fault is not None:
        _fault("after_journal")
    lock = None
    event = None
    try:
        lock = locking.acquire(
            root, request_id, SENDER, request_id,
            lease_seconds=_lease_seconds,
            kind="source_audit_supersession", owner_token=token)
        journal["completed"].append("locked")
        _write_source_rewind_journal(paths["journal"], journal)
        if _fault is not None:
            _fault("after_lock")
        fresh_chain = events.read_chain(root)
        fresh = state_machine.project(fresh_chain).get(request_id)
        if fresh is None or fresh["state"] != prior_state or \
                fresh["last_event_id"] != projected["last_event_id"]:
            raise CouncilError("source audit changed before rewind")
        nested = _source_rewind_expected(
            root, fresh_chain, journal, request, publication, verdict)
        event = events.append_event(
            root, cfg, "FIX_STARTED", SENDER, request_id, repository,
            target_commit, {
                "originating_blocked_commit": target_commit,
                "blockers_addressed": [reason],
                "controlling_event_id": controlling_event_id,
                "superseded_audit": nested,
            })
        journal["completed"].append("event")
        _write_source_rewind_journal(paths["journal"], journal)
        if _fault is not None:
            _fault("after_event")
        _archive_exact(
            source_path, paths["request_archive"], request_sha256)
        journal["completed"].append("request_archived")
        _write_source_rewind_journal(paths["journal"], journal)
        if _fault is not None:
            _fault("after_request_archive")
        if verdict_sha256 is not None:
            _archive_exact(
                verdict_path, paths["verdict_archive"], verdict_sha256)
        journal["completed"].append("verdict_archived")
        _write_source_rewind_journal(paths["journal"], journal)
        if _fault is not None:
            _fault("after_verdict_archive")
        try:
            os.unlink(paths["journal"])
        except OSError:
            pass
        return event
    except (CouncilError, OSError):
        outcome, recovered_event = _recover_source_rewind(
            root, cfg, paths["journal"], force_owner=True)
        if outcome == "forward" and recovered_event is not None:
            return recovered_event
        raise
    finally:
        if lock is not None:
            locking.release(lock)


def _fsync_directory(path: str) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class _Budget:
    def __init__(self, limits: dict):
        self.limits = limits
        self.wall_start = time.monotonic()
        self.compute_start = time.process_time()

    def check(self, *paths: str) -> None:
        if time.monotonic() - self.wall_start > \
                self.limits["max_wall_minutes"] * 60:
            raise CouncilError("closure wall budget exhausted")
        if time.process_time() - self.compute_start > \
                self.limits["max_compute_minutes"] * 60:
            raise CouncilError("closure compute budget exhausted")
        total = 0
        for root in paths:
            if not root or not os.path.lexists(root):
                continue
            if os.path.isfile(root):
                total += os.path.getsize(root)
                continue
            for dirpath, _dirs, files in os.walk(root):
                total += sum(os.path.getsize(os.path.join(dirpath, name))
                             for name in files)
        if total > self.limits["max_storage_mb"] * 1024 * 1024:
            raise CouncilError("closure storage budget exhausted")


def _write_bundle_transaction(final_path: str, transaction: str,
                              data: dict[str, bytes], budget: _Budget,
                              fault=None) -> None:
    inject = fault or (lambda _stage: None)
    parent = os.path.dirname(final_path)
    temp_path = os.path.join(parent, f".m8-incomplete-{transaction}.tmp")
    os.makedirs(parent, exist_ok=True)
    if os.path.lexists(final_path):
        _verify_exact_bundle(final_path, data)
        _fsync_directory(parent)
        inject("after_adoption_parent_fsync")
        return
    if os.path.lexists(temp_path):
        marker_path = os.path.join(temp_path, ".transaction.json")
        package_path = os.path.join(temp_path,
                                    "incomplete_result_package.json")
        owned = False
        identity_path = marker_path if os.path.isfile(marker_path) \
            and not os.path.islink(marker_path) else package_path
        if os.path.isfile(identity_path) and not os.path.islink(identity_path):
            try:
                from tools.council.strictjson import loads_strict
                with open(identity_path, "rb") as fh:
                    owned = loads_strict(
                        fh.read(), max_bytes=2_000_000).get(
                            "transaction_id") == transaction
            except (OSError, ValueError, AttributeError):
                owned = False
        if not owned:
            raise CouncilError("interrupted bundle is not owned by transaction")
        shutil.rmtree(temp_path)
    os.mkdir(temp_path, 0o700)
    renamed = False
    try:
        marker_path = os.path.join(temp_path, ".transaction.json")
        with open(marker_path, "xb") as fh:
            fh.write(ir.json_bytes({
                "schema_version": "m8-incomplete-transaction-owner.v1",
                "transaction_id": transaction,
            }))
            fh.flush()
            os.fsync(fh.fileno())
        inject("after_owner_marker")
        budget.check(temp_path, final_path)
        for name in ir.DERIVED_FILENAMES:
            inject(f"before_write:{name}")
            path = os.path.join(temp_path, name)
            with open(path, "xb") as fh:
                fh.write(data[name])
                fh.flush()
                os.fsync(fh.fileno())
            inject(f"after_write:{name}")
            budget.check(temp_path, final_path)
        dir_fd = os.open(temp_path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        inject("after_temp_fsync")
        os.unlink(marker_path)
        _fsync_directory(temp_path)
        inject("after_marker_remove")
        os.rename(temp_path, final_path)
        renamed = True
        inject("after_rename")
        _fsync_directory(parent)
        inject("after_parent_fsync")
        _verify_exact_bundle(final_path, data)
    finally:
        if not renamed and os.path.isdir(temp_path):
            shutil.rmtree(temp_path)


def _result_artifacts(authorization: dict, approval: dict,
                      hashes: dict[str, str], bundle_hash: str,
                      objects: dict[str, dict]) -> dict:
    source = authorization["source_request"]
    primary = authorization["primary_evidence"]
    return {
        "schema_version": "result-artifacts.v2",
        "profile_id": PROFILE_ID,
        "source_request_id": source["request_id"],
        "source_request_payload_hash": source["request_payload_hash"],
        "source_owner_approval_event_id": source["owner_approval_event_id"],
        "source_owner_approval_event_hash":
            source["owner_approval_event_hash"],
        "start_event_id": authorization["terminal_events"]["start"]["event_id"],
        "start_event_hash":
            authorization["terminal_events"]["start"]["event_hash"],
        "pause_event_id": authorization["terminal_events"]["pause"]["event_id"],
        "pause_event_hash":
            authorization["terminal_events"]["pause"]["event_hash"],
        "closure_owner_approval_event_id": approval["event_id"],
        "closure_owner_approval_event_hash": approval["event_hash"],
        "closure_authorization_hash":
            closure_authorization_hash(authorization),
        "closure_tool_commit": authorization["closure_tool"]["target_commit"],
        "derived_output_root": ir.DERIVED_OUTPUT_ROOT,
        "analysis_status": "budget_exhausted_incomplete",
        "statistics_computed": False,
        "planned_runs": 144,
        "successful_runs": 105,
        "partial_runs": 1,
        "unattempted_runs": 38,
        "tombstoned_runs": 0,
        "terminal_outcomes": 105,
        "manifest_sha256": primary["manifest_sha256"],
        "tombstone_ledger": primary["tombstone_ledger"],
        "primary_inventory_file_sha256":
            hashes["primary_inventory.json"],
        "primary_inventory_content_hash":
            primary["primary_inventory_content_hash"],
        "replay_attestation_sha256": hashes["replay_attestation.json"],
        "coordinate_census_file_sha256":
            hashes["coordinate_census.json"],
        "coordinate_census_content_hash":
            primary["coordinate_census_content_hash"],
        "incomplete_report_sha256": hashes["incomplete_report.json"],
        "incomplete_result_package_file_sha256":
            hashes["incomplete_result_package.json"],
        "incomplete_result_package_content_sha256":
            objects["incomplete_result_package.json"]["content_hash"],
        "validation_report_sha256": hashes["validation_report.json"],
        "derived_bundle_content_hash": bundle_hash,
    }


def _result_request(repo: str, authorization: dict, approval: dict,
                    objects: dict[str, dict], hashes: dict[str, str]) -> dict:
    from tools.autonomy.runner import validation_report_hash
    from tools.council.schemas import FULL_TEST_COMMAND, domain_hash
    bundle_hash = ir.derived_bundle_hash(hashes)
    artifacts = _result_artifacts(
        authorization, approval, hashes, bundle_hash, objects)
    config = {
        "schema_version": "m8-budget-exhaustion-result-config.v1",
        "profile_id": PROFILE_ID,
        "closure_authorization_hash":
            closure_authorization_hash(authorization),
        "derived_bundle_content_hash": bundle_hash,
        "result_artifacts": artifacts,
        "conclusion_scope": ir.OUTCOME["conclusion_scope"],
    }
    return {
        "request_id": RESULT_REQUEST_ID,
        "protocol_version": "2.0",
        "repository": repo,
        "target_commit": authorization["closure_tool"]["target_commit"],
        "require_clean_tree": True,
        "expected_test_command": FULL_TEST_COMMAND,
        "expected_test_count": M8_EXPECTED_TEST_COUNT,
        "scope": REQUEST_SCOPE,
        "questions": REQUEST_QUESTIONS,
        "allowed_actions": REQUEST_ALLOWED_ACTIONS,
        "forbidden_actions": REQUEST_FORBIDDEN_ACTIONS,
        "requested_verdicts": ["RESULT_APPROVED", "RESULT_BLOCKED"],
        "live_experiment_allowed": False,
        "human_approval_required": True,
        "originating_blocked_commit": SOURCE_IMPLEMENTATION_COMMIT,
        "blockers_addressed": [
            "Close the owner-bounded M8 execution as authenticated, "
            "budget-exhausted, incomplete, and inconclusive."
        ],
        "request_payload_hash": "0" * 64,
        "task_kind": "result_handoff",
        "run_id": ir.RUN_ID,
        "run_dir": ir.DERIVED_OUTPUT_ROOT,
        "manifest_file":
            f"{ir.DERIVED_OUTPUT_ROOT}/primary_inventory.json",
        "evidence_inventory_hash": bundle_hash,
        "validations": VALIDATIONS,
        "validation_report_hash": validation_report_hash(VALIDATIONS),
        "result_config": config,
        "experiment_config_hash": domain_hash(
            "council:result-handoff-config:v1", config),
        "authorization_profile": {
            "profile_id": PROFILE_ID,
            "closure_authorization_hash":
                closure_authorization_hash(authorization),
            "closure_owner_approval_event_id": approval["event_id"],
            "closure_owner_approval_event_hash": approval["event_hash"],
        },
        "closure_authorization": authorization,
        "closure_authorization_hash":
            closure_authorization_hash(authorization),
        "derived_artifact_hashes": hashes,
        "result_artifacts": artifacts,
        "conclusion_scope": ir.OUTCOME["conclusion_scope"],
    }


def verify_bundle_request(repo: str, request: dict, *, chain=None,
                          deep: bool = True, budget: "_Budget | None" = None
                          ) -> None:
    """Verify the immutable six-file bundle against its closed request."""
    validate_m8_handoff_request(request)
    root = ir.safe_repo_path(repo, ir.DERIVED_OUTPUT_ROOT)
    if not os.path.isdir(root) or os.path.islink(root) or \
            set(os.listdir(root)) != set(ir.DERIVED_FILENAMES):
        raise CouncilError("derived bundle inventory differs")
    hashes = {}
    objects = {}
    for name in ir.DERIVED_FILENAMES:
        path = os.path.join(root, name)
        info = os.lstat(path)
        if not os.path.isfile(path) or os.path.islink(path) or \
                info.st_nlink != 1:
            raise CouncilError("derived bundle member is not a single-link file")
        hashes[name] = ir.file_sha256(path)
        from tools.council.strictjson import loads_strict
        with open(path, "rb") as fh:
            objects[name] = loads_strict(
                fh.read(), max_bytes=8_000_000)
    if hashes != request["derived_artifact_hashes"] or \
            ir.derived_bundle_hash(hashes) != \
            request["evidence_inventory_hash"]:
        raise CouncilError("derived bundle hashes differ from request")
    if objects["primary_inventory.json"].get("content_hash") != \
            ir.PRIMARY_INVENTORY_CONTENT_HASH:
        raise CouncilError("primary inventory content identity differs")
    for name, domain in (
            ("primary_inventory.json", ir.PRIMARY_INVENTORY_DOMAIN),
            ("coordinate_census.json", ir.COORDINATE_CENSUS_DOMAIN),
            ("replay_attestation.json", ir.REPLAY_DOMAIN),
            ("validation_report.json", ir.VALIDATION_DOMAIN)):
        content = {key: value for key, value in objects[name].items()
                   if key != "content_hash"}
        if objects[name].get("content_hash") != ir.domain_hash(domain, content):
            raise CouncilError(f"{name} content identity differs")
    if objects["coordinate_census.json"].get("content_hash") != \
            ir.COORDINATE_CENSUS_CONTENT_HASH or \
            objects["incomplete_report.json"] != ir.incomplete_report() or \
            objects["validation_report.json"] != ir.validation_report(
                VALIDATIONS):
        raise CouncilError("derived bundle content identity differs")
    package = objects["incomplete_result_package.json"]
    package_content = {key: value for key, value in package.items()
                       if key != "content_hash"}
    if package.get("content_hash") != ir.domain_hash(
            ir.PACKAGE_DOMAIN, package_content) or \
            package.get("outcome") != ir.OUTCOME:
        raise CouncilError("incomplete result package identity differs")
    first_hashes = {name: hashes[name] for name in (
        "primary_inventory.json", "replay_attestation.json",
        "coordinate_census.json", "incomplete_report.json")}
    authorization = request["closure_authorization"]
    profile = request["authorization_profile"]
    exact_package = {
        "schema_version": "m8-budget-exhaustion-incomplete-package.v1",
        "profile_id": PROFILE_ID,
        "source_request_id": SOURCE_REQUEST_ID,
        "source_implementation_commit": SOURCE_IMPLEMENTATION_COMMIT,
        "closure_tool_commit": request["target_commit"],
        "closure_authorization_hash":
            request["closure_authorization_hash"],
        "closure_owner_approval_event_id":
            profile["closure_owner_approval_event_id"],
        "closure_owner_approval_event_hash":
            profile["closure_owner_approval_event_hash"],
        "primary_inventory_content_hash":
            ir.PRIMARY_INVENTORY_CONTENT_HASH,
        "partial_files": authorization["primary_evidence"]["partial"]["files"],
        "artifact_hashes": first_hashes,
        "outcome": ir.OUTCOME,
    }
    if set(package) != set(exact_package) | {
            "transaction_id", "proposal_event_id",
            "proposal_event_hash", "content_hash"}:
        raise CouncilError("incomplete package field set differs")
    for field, expected in exact_package.items():
        if package.get(field) != expected:
            raise CouncilError(f"incomplete package {field} differs")
    if request["result_artifacts"] != _result_artifacts(
            authorization, {
                "event_id": profile["closure_owner_approval_event_id"],
                "event_hash": profile["closure_owner_approval_event_hash"],
            }, hashes, request["evidence_inventory_hash"], objects):
        raise CouncilError("request artifact record differs from actual bytes")
    if chain is not None:
        proposal = next((item for item in chain
                         if item["request_id"] == request["request_id"] and
                         item["event_type"] ==
                         "RESULT_HANDOFF_APPROVAL_REQUIRED"), None)
        approval = next((item for item in chain
                         if item["request_id"] == request["request_id"] and
                         item["event_type"] == "RESULT_HANDOFF_APPROVED"), None)
        if proposal is None or approval is None:
            raise CouncilError("bundle transaction lacks proposal/approval")
        expected_transaction = transaction_id(
            request["request_id"], proposal, approval,
            request["closure_authorization_hash"], request["target_commit"])
        if package.get("transaction_id") != expected_transaction or \
                package.get("proposal_event_id") != proposal["event_id"] or \
                package.get("proposal_event_hash") != proposal["event_hash"]:
            raise CouncilError("bundle transaction identity differs")
    if not deep:
        return
    sweep = importlib.import_module("coliseum.textlab.sweep")
    registry_module = importlib.import_module("coliseum.textlab.registry")
    evidence_root = ir.safe_repo_path(repo, ir.EVIDENCE_ROOT)
    manifest_path = ir.safe_repo_path(repo, ir.MANIFEST)
    registry = registry_module.load_verified_bundle(
        os.path.join(repo, "configs", "registry", "experiments.yaml"),
        ir.EXPERIMENT_ID)
    if budget is not None and (
            not isinstance(budget, _Budget) or
            budget.limits != authorization["closure_budget"]):
        raise CouncilError(
            "deep verification budget differs from the owner closure budget")
    active_budget = budget or _Budget(authorization["closure_budget"])
    active_budget.check(root)
    with sweep._manifest_advisory_lock(manifest_path) as locked_manifest:
        snapshot = _derive_primary_locked(
            repo, locked_manifest, evidence_root, registry.planned_design)
        if snapshot["primary"] != authorization["primary_evidence"] or \
                objects["primary_inventory.json"] != snapshot["inventory"] or \
                objects["coordinate_census.json"] != snapshot["census"]:
            raise CouncilError(
                "bundle does not equal an independent primary rederivation")
        replay_core = sweep.build_pack_replay_core_locked(
            locked_manifest, evidence_root,
            os.path.join(repo, "configs", "scenarios"),
            registry.planned_design, progress_check=active_budget.check)
        if objects["replay_attestation.json"] != \
                ir.replay_attestation(replay_core):
            raise CouncilError(
                "bundle replay receipt differs from independent replay")
        active_budget.check(root)


def publish_approved(root: str, cfg, request_id: str) -> dict:
    """Build, atomically publish, and journal one owner-approved M8 closure."""
    sweep = importlib.import_module("coliseum.textlab.sweep")
    registry_module = importlib.import_module("coliseum.textlab.registry")
    from tools.council import events, git_state, locking, state_machine
    from tools.council import result_handoff

    if request_id != RESULT_REQUEST_ID:
        raise SchemaViolation(f"request id must be exactly {RESULT_REQUEST_ID}")
    lease = locking.acquire(root, "_m8_incomplete_handoff", SENDER,
                            request_id, kind="m8_incomplete_builder")
    journal_lease = None
    try:
        chain = events.read_chain(root)
        projection = state_machine.project(chain)
        if projection.get(request_id, {}).get("state") != \
                state_machine.RESULT_HANDOFF_OWNER_APPROVED:
            raise CouncilError("M8 result handoff is not owner-approved")
        if projection.get(SOURCE_REQUEST_ID, {}).get("state") != \
                state_machine.AUTONOMY_PAUSED:
            raise CouncilError("original M8 request is no longer paused")
        proposals = [item for item in chain
                     if item["request_id"] == request_id and
                     item["event_type"] ==
                     "RESULT_HANDOFF_APPROVAL_REQUIRED"]
        approvals = [item for item in chain
                     if item["request_id"] == request_id and
                     item["event_type"] == "RESULT_HANDOFF_APPROVED"]
        if len(proposals) != 1 or len(approvals) != 1:
            raise CouncilError("M8 handoff requires one proposal and approval")
        proposal, approval = proposals[0], approvals[0]
        validate_approval_binding(chain, approval)
        authorization = proposal["payload"]["closure_authorization"]
        validate_closure_authorization(authorization)
        commit = authorization["closure_tool"]["target_commit"]
        repo = proposal["repository"]
        if approval["repository"] != repo or \
                git_state.head_commit(repo, cfg.repo_roots) != commit or \
                not git_state.is_clean(repo, cfg.repo_roots):
            raise CouncilError("M8 bundle requires a clean exact closure HEAD")
        _source_authority(chain)
        if _closure_integrations(chain, commit) != \
                authorization["closure_tool"]["integration_events"]:
            raise CouncilError("closure source integration bindings changed")
        _preflight_request_namespace(root, chain)
        journal_lease = locking.acquire(
            root, "_result_handoff", SENDER, request_id,
            kind="result_handoff_transaction")
        # The namespace checked before acquire may become stale while this
        # publisher waits for the transaction lease. Refresh it immediately
        # after acquisition, before registry loading, primary derivation,
        # replay, output, or journal creation.
        _preflight_request_namespace(root, events.read_chain(root))
        transaction = transaction_id(
            request_id, proposal, approval,
            proposal["payload"]["closure_authorization_hash"], commit)
        budget = _Budget(authorization["closure_budget"])
        evidence_root = ir.safe_repo_path(repo, ir.EVIDENCE_ROOT)
        manifest_path = ir.safe_repo_path(repo, ir.MANIFEST)
        final_path = ir.safe_repo_path(
            repo, ir.DERIVED_OUTPUT_ROOT, may_be_absent=True)
        registry = registry_module.load_verified_bundle(
            os.path.join(repo, "configs", "registry", "experiments.yaml"),
            ir.EXPERIMENT_ID)
        with sweep._manifest_advisory_lock(manifest_path) as locked_manifest:
            snapshot = _derive_primary_locked(
                repo, locked_manifest, evidence_root,
                registry.planned_design)
            if snapshot["primary"] != authorization["primary_evidence"]:
                raise CouncilError("primary evidence differs from owner approval")
            budget.check(final_path)
            replay_core = sweep.build_pack_replay_core_locked(
                locked_manifest, evidence_root,
                os.path.join(repo, "configs", "scenarios"),
                registry.planned_design, progress_check=budget.check)
            if len(replay_core["runs"]) > \
                    authorization["closure_budget"]["max_replay_runs"]:
                raise CouncilError("replay count exceeds the owner closure budget")
            objects = _artifact_objects(
                snapshot, replay_core, authorization, proposal, approval,
                transaction)
            data = _artifact_bytes(objects)
            hashes = _file_hashes(data)
            budget.check(final_path)
            # Re-read every primary member and both terminal ledgers before the
            # one atomic publication. The lock makes this a stable snapshot;
            # the second derivation detects direct byte changes by this process.
            final_snapshot = _derive_primary_locked(
                repo, locked_manifest, evidence_root,
                registry.planned_design)
            for field in ("primary", "inventory", "census"):
                if final_snapshot[field] != snapshot[field]:
                    raise CouncilError("primary evidence changed during closure")
            _preflight_request_namespace(root, events.read_chain(root))
            budget.check(final_path)
            _write_bundle_transaction(
                final_path, transaction, data, budget)
        request = _result_request(
            repo, authorization, approval, objects, hashes)
        fresh_chain = events.read_chain(root)
        _preflight_request_namespace(root, fresh_chain)
        budget.check(final_path)
        fresh_chain = events.read_chain(root)
        _preflight_request_namespace(root, fresh_chain)
        if state_machine.project(fresh_chain).get(
                SOURCE_REQUEST_ID, {}).get("state") != \
                state_machine.AUTONOMY_PAUSED:
            raise CouncilError("source pause changed before result publication")
        return result_handoff._publish_handoff_locked(
            root, cfg, request, _m8_budget=budget)
    finally:
        if journal_lease is not None:
            locking.release(journal_lease)
        locking.release(lease)


def source_close_payload(chain: list[dict], result_request_id: str,
                         result_event_id: str) -> dict:
    if result_request_id != RESULT_REQUEST_ID:
        raise SchemaViolation("result request id differs from M8 closure")
    event = next((item for item in chain
                  if item["event_id"] == result_event_id), None)
    if event is None or event["request_id"] != result_request_id or \
            event["event_type"] != "RESULT_APPROVED":
        raise CouncilError("named result event is not the M8 RESULT_APPROVED")
    ready = next((item for item in reversed(chain)
                  if item["request_id"] == result_request_id and
                  item["event_type"] == "RESULT_HANDOFF_READY"), None)
    if ready is None:
        raise CouncilError("M8 result has no ready request")
    closure_hash = ready["payload"]["request"].get(
        "closure_authorization_hash")
    _hash(closure_hash, "closure_authorization_hash")
    return {
        "schema_version": "m8-budget-exhaustion-source-close.v1",
        "reason": "M8 budget-exhausted incomplete outcome approved",
        "result_request_id": result_request_id,
        "result_approved_event_id": event["event_id"],
        "result_approved_event_hash": event["event_hash"],
        "closure_authorization_hash": closure_hash,
    }


def validate_source_close_binding(chain: list[dict], event: dict) -> None:
    payload = event["payload"]
    expected_fields = {
        "schema_version", "reason", "result_request_id",
        "result_approved_event_id", "result_approved_event_hash",
        "closure_authorization_hash", "human_token"}
    _closed(payload, expected_fields, "M8 source-close payload")
    expected = source_close_payload(
        chain, payload["result_request_id"],
        payload["result_approved_event_id"])
    observed = {key: value for key, value in payload.items()
                if key != "human_token"}
    if observed != expected or event["request_id"] != SOURCE_REQUEST_ID or \
            event["sender"] != "human":
        raise CouncilError("M8 source-close event binding differs")
