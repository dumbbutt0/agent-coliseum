"""Adversarial HSC-A schema, identity, scope, graph, and conflict tests."""

from __future__ import annotations

import copy
import hashlib

import pytest

from tools.council.schemas import (SchemaViolation, canonical_json,
                                   domain_hash, validate_request_id)
from tools.section_council import (
    HSCValidationError, RecordStore,
    RECORD_TYPES,
    WorkAccess,
    classify_conflict,
    dependency_closure,
    dispatch_order,
    parse_hsc_request_binding,
    stale_work_items,
    validate_actual_change,
    validate_native_rel_path,
    validate_path,
    validate_predicted_change,
    validate_record,
)
from tools.section_council.core import (file_id, filesystem_id,
                                        locator_sha256, require_request_id,
                                        strict_json_bytes,
                                        validate_native_observation)
from tools.section_council.records import make_record, record_ref


H0 = "0" * 64
H1 = "1" * 64
H2 = "2" * 64
G0 = "0" * 40
REF0 = {"record_id": H0, "content_sha256": H1}
PROGRAM_REF = {"record_id": H1, "content_sha256": H2}
BUDGET = {"max_wall_seconds": 10, "max_cpu_seconds": 9,
          "max_output_bytes": 1000, "max_attempts": 1}
ADD = {"path": "src/a.txt", "kind": "add", "rename_source": None,
       "blob_before": None, "mode_before": None, "required": True}
INTERFACE = {"interface_id": "api-v1", "version": 1, "digest": H0}
CHECK = {"check_id": "check-1", "status": "pass", "evidence_ref": REF0}
METRIC = {"metric_id": "runtime", "availability": "unavailable",
          "unit": "seconds", "value": None, "evidence_ref": None}


def observation(index=1, *, directory=False, mode=None):
    return {
        "profile": "linux-native-id-v1", "statx_mount_id": index,
        "device_major": 8, "device_minor": 1,
        "statfs_fsid_word0": 2, "statfs_fsid_word1": 3,
        "file_handle_type": 1,
        "file_handle_bytes_hex": f"{index:032x}", "inode": index,
        "file_type": "directory" if directory else "regular",
        "link_count": 1,
        "native_mode": mode if mode is not None else
        (0o40755 if directory else 0o100644),
    }


def locator(index=1, segments=None):
    return {
        "platform": "linux-bwrap-v1", "anchor_name": f"anchor-{index}",
        "anchor_id": f"{index:064x}", "segments_hex": list(segments or []),
        "resolution": "openat2-beneath-no-magiclinks-no-symlinks-v1",
    }


def root_spec(index, kind, *, workspace=None, view="full-native-tree-v1",
              delegated_id=None, delegated_observation=None, segments=None):
    obs = observation(index, directory=True)
    loc = locator(index, segments)
    value = {
        "root_id": H0, "root_kind": kind, "view_kind": view,
        "namespace_id": H0, "locator": loc,
        "locator_sha256": locator_sha256(loc), "native_identity": obs,
        "filesystem_id": filesystem_id(obs), "file_id": file_id(obs),
        "workspace_id": workspace,
        "delegated_control_root_id": delegated_id,
        "delegated_control_identity": delegated_observation,
    }
    value["namespace_id"] = domain_hash("council:native-namespace:v1", {
        "locator_sha256": value["locator_sha256"], "program_ref": PROGRAM_REF,
        "root_kind": kind, "view_kind": view, "workspace_id": workspace,
    })
    without_id = dict(value)
    without_id.pop("root_id")
    value["root_id"] = domain_hash("council:native-root:v1", {
        "program_ref": PROGRAM_REF, "root_spec": without_id})
    return value


def native_plan_payload():
    workspace = "a" * 64
    common_obs = observation(3, directory=True)
    common = root_spec(3, "common-git", segments=["7265706f", "2e676974"])
    # Root helper generated the same deterministic observation.
    checkout = root_spec(
        2, "integration-checkout", workspace=None,
        view="checkout-excluding-delegated-dotgit-v1",
        delegated_id=common["root_id"], delegated_observation=common_obs,
        segments=["7265706f"])
    roots = [
        root_spec(1, "candidate", workspace=workspace), checkout, common,
        root_spec(4, "council-root"), root_spec(5, "owner-anchors"),
        root_spec(6, "other-worker-leaves"),
        root_spec(7, "canonical-evidence"), root_spec(8, "hidden-suites"),
        root_spec(9, "runtime-readonly", workspace=workspace),
        root_spec(10, "builder-output", workspace=workspace),
    ]
    roots.sort(key=lambda row: row["root_id"])
    observations = []
    for root in roots:
        for phase in ("pre-dispatch", "post-worker"):
            item = {
                "observation_id": H0, "root_id": root["root_id"],
                "phase": phase, "scope": "builder-dispatch",
                "work_item_id": H1, "role": "builder", "attempt": 0,
                "workspace_id": workspace,
            }
            preimage = dict(item)
            preimage.pop("observation_id")
            preimage["program_ref"] = PROGRAM_REF
            item["observation_id"] = domain_hash(
                "council:native-observation-requirement:v1", preimage)
            observations.append(item)
    observations.sort(key=lambda row: row["observation_id"])
    return {
        "program_ref": PROGRAM_REF, "base_commit": G0,
        "scope": "builder-dispatch", "work_item_id": H1, "role": "builder",
        "attempt": 0, "workspace_id": workspace, "roots": roots,
        "root_count": len(roots), "observations": observations,
        "observation_count": len(observations),
    }


def auth_payload():
    p = {
        "program_ref": PROGRAM_REF, "principal_registry_ref": REF0,
        "scheduler_authority_id": H0, "scheduler_journal_sequence": 0,
        "scheduler_journal_entry_sha256": H0, "contract_ref": REF0,
        "work_item_id": H1, "role": "builder", "principal_id": "builder-1",
        "authority_control_id": H0, "principal_credential_digest": H1,
        "launcher_executable_sha256": H2, "session_nonce": H0, "attempt": 0,
        "context_ref": REF0, "sandbox_profile_ref": REF0,
        "workspace_id": H1, "output_leaf": "builder-out",
    }
    q = dict(p)
    q.pop("scheduler_journal_entry_sha256")
    p["scheduler_journal_entry_sha256"] = domain_hash(
        "council:section-launch-authorization-entry:v1", q)
    return p


def assignment_payload():
    a = auth_payload()
    p = {key: value for key, value in a.items()
         if key != "launcher_executable_sha256"}
    p["launcher_authorization_ref"] = REF0
    p["scheduler_journal_sequence"] = 1
    q = dict(p)
    q.pop("scheduler_journal_entry_sha256")
    p["scheduler_journal_entry_sha256"] = domain_hash(
        "council:section-assignment-entry:v1", q)
    return p


def receipt_payload():
    a = auth_payload()
    p = {key: value for key, value in a.items()
         if key not in ("principal_registry_ref", "contract_ref", "work_item_id")}
    p["authorization_ref"] = REF0
    p["assignment_ref"] = REF0
    p["scheduler_journal_sequence"] = 2
    p["barrier_status"] = "ready"
    q = dict(p)
    q.pop("scheduler_journal_entry_sha256")
    p["scheduler_journal_entry_sha256"] = domain_hash(
        "council:section-launch-receipt-entry:v1", q)
    return p


def journal_payload():
    obs = observation(99, directory=True, mode=0o40700)
    loc = locator(99)
    p = {
        "program_ref": PROGRAM_REF, "principal_registry_ref": REF0,
        "scheduler_authority_id": H0, "journal_root_id": H0,
        "journal_root_locator": loc,
        "journal_root_locator_sha256": locator_sha256(loc),
        "journal_root_native_identity": obs,
        "journal_root_filesystem_id": filesystem_id(obs),
        "journal_root_file_id": file_id(obs),
        "journal_owner_principal_id": "scheduler-writer",
        "journal_owner_control_id": H1, "journal_mode": "0700",
        "predecessor_journal_manifest_ref": None,
        "first_sequence": 0, "last_sequence": 2,
        "entries": [
            {"ordinal": 0, "sequence": 0, "entry_kind": "authorization",
             "record_ref": REF0, "entry_sha256": H0,
             "writer_role": "scheduler", "writer_principal_id":
             "scheduler-writer", "writer_control_id": H1},
            {"ordinal": 1, "sequence": 1, "entry_kind": "assignment",
             "record_ref": REF0, "entry_sha256": H0,
             "writer_role": "scheduler", "writer_principal_id":
             "scheduler-writer", "writer_control_id": H1},
            {"ordinal": 2, "sequence": 2, "entry_kind": "receipt",
             "record_ref": REF0, "entry_sha256": H0,
             "writer_role": "launcher", "writer_principal_id":
             "launcher-writer", "writer_control_id": H2},
        ],
    }
    p["journal_root_id"] = domain_hash(
        "council:scheduler-journal-root:v1", {
            "journal_mode": "0700", "journal_owner_control_id": H1,
            "journal_owner_principal_id": "scheduler-writer",
            "journal_root_file_id": p["journal_root_file_id"],
            "journal_root_filesystem_id": p["journal_root_filesystem_id"],
            "journal_root_locator_sha256": p["journal_root_locator_sha256"],
            "principal_registry_ref": REF0, "program_ref": PROGRAM_REF,
        })
    return p


def valid_payload(schema):
    basic_principals = [
        {"principal_id": "assessor-1", "allowed_role": "assessor",
         "authority_control_id": "3" * 64,
         "authority_control_key_digest": "4" * 64,
         "principal_credential_digest": "5" * 64,
         "launcher_profile_id": "assessor-profile",
         "enrollment_evidence_sha256": "6" * 64},
        {"principal_id": "builder-1", "allowed_role": "builder",
         "authority_control_id": "7" * 64,
         "authority_control_key_digest": "8" * 64,
         "principal_credential_digest": "9" * 64,
         "launcher_profile_id": "builder-profile",
         "enrollment_evidence_sha256": "a" * 64},
    ]
    work_item = {
        "work_item_id": H0, "section_contract_ref": REF0,
        "operation": "emit_report", "dependency_work_item_ids": [],
        "read_inventory_refs": [], "predicted_changes": [ADD],
        "shared_interfaces": [INTERFACE],
        "required_audit_levels": ["section", "system"], "priority": 0,
        "budget": BUDGET,
    }
    wi_preimage = dict(work_item)
    wi_preimage.pop("work_item_id")
    wi_preimage["program_ref"] = PROGRAM_REF
    work_item["work_item_id"] = domain_hash("council:section-work-item:v1",
                                             wi_preimage)
    profile = {
        "program_ref": PROGRAM_REF, "platform": "linux-bwrap-v1",
        "launcher_binary_sha256": H0, "argv_template_sha256": H1,
        "native_inventory_plan_ref": REF0, "source_snapshot_ref": REF0,
        "read_only_mount_refs": [REF0], "writable_mountpoint": "/out",
        "private_tmpfs_bytes": 1024, "unshare_user": True,
        "unshare_pid": True, "unshare_net": True,
        "no_new_privileges": True, "capability_set": [],
        "seccomp_profile_sha256": H2, "environment_allowlist": [],
        "fd_policy": "close-all-except-stdio-v1",
        "permitted_fds": [
            {"fd": 0, "role": "stdin", "access": "read",
             "target_kind": "null"},
            {"fd": 1, "role": "stdout", "access": "write",
             "target_kind": "pipe"},
            {"fd": 2, "role": "stderr", "access": "write",
             "target_kind": "pipe"},
        ],
    }
    mapping = {
        "section_bootstrap_content.v1": {
            "planned_request_id": "pilot-001", "artifact_type": "schema_profile",
            "storage_relpath":
            "artifacts/section-council/pilot-001/bootstrap/schema.json",
            "media_type": "application/json", "byte_length": 2,
            "blob_sha256": H0,
        },
        "section_principal_registry.v1": {
            "planned_request_id": "pilot-001", "repository": "/repo",
            "base_commit": G0, "enrollment_registry_path": "configs/hsc.json",
            "enrollment_registry_git_blob": G0,
            "enrollment_registry_version": 1, "enrollment_registry_digest": H0,
            "scheduler_authority_id": H1,
            "scheduler_writer_principal_id": "scheduler-writer",
            "scheduler_writer_control_id": H0,
            "launcher_writer_principal_id": "launcher-writer",
            "launcher_writer_control_id": H1, "principals": basic_principals,
        },
        "section_program.v1": {
            "planned_request_id": "pilot-001", "repository": "/repo",
            "base_commit": G0, "execution_mode": "hierarchical",
            "section_declarations": [{
                "section_id": "section-a", "predicted_changes": [ADD],
                "read_inventory_refs": [], "dependency_section_ids": [],
                "budget": BUDGET, "assessment_profile_id": "assessment-1",
            }], "schema_profile_refs": [REF0],
            "principal_registry_ref": REF0,
            "system_artifact_predictions": [{
                "path": "artifacts/section-council/pilot-001/content/a.json",
                "kind": "add", "rename_source": None, "blob_before": None,
                "mode_before": None, "required": True,
            }], "root_policy_version": 1,
        },
        "section_contract.v1": {
            "program_ref": PROGRAM_REF, "planned_request_id": "pilot-001",
            "parent_build_event_id": "000001-00000000",
            "parent_build_event_hash": H0, "base_commit": G0,
            "section_id": "section-a", "contract_version": 1,
            "objective": "Build the bounded report.", "predicted_changes": [ADD],
            "read_inventory_refs": [], "forbidden_host_roots": ["council"],
            "allowed_operations": ["emit_report"],
            "forbidden_operations": ["council_write"],
            "upstream_contract_refs": [], "consumed_interfaces": [],
            "exported_interfaces": [INTERFACE],
            "required_invariant_ids": ["invariant-1"],
            "required_check_ids": ["check-1"],
            "required_evidence_ids": ["evidence-1"], "threat_ids": ["threat-1"],
            "assessment_profile_ref": REF0, "budget": BUDGET,
            "executor_profile_ids": ["executor-1"],
            "escalation_rule_ids": ["escalate-1"],
            "completion_condition_ids": ["complete-1"],
            "integration_precondition_ids": ["integrate-1"],
        },
        "section_work_graph.v1": {
            "program_ref": PROGRAM_REF, "contract_refs": [REF0],
            "work_items": [work_item],
        },
        "section_context_bundle.v1": {
            "program_ref": PROGRAM_REF, "contract_ref": REF0,
            "work_item_id": H0, "base_commit": G0, "role": "builder",
            "source_files": [], "interface_refs": [], "policy_files": [],
            "test_files": [], "prior_finding_refs": [], "proposal_ref": None,
            "deterministic_result_refs": [], "omitted_category_ids": [],
        },
        "section_content_record.v1": {
            "program_ref": PROGRAM_REF, "artifact_type": "operation_log",
            "storage_relpath":
            "artifacts/section-council/pilot-001/content/log.json",
            "media_type": "application/json", "byte_length": 2,
            "blob_sha256": H0, "producer_assignment_ref": None,
            "parent_content_refs": [],
        },
        "section_launcher_authorization.v1": auth_payload(),
        "section_assignment.v1": assignment_payload(),
        "section_launcher_receipt.v1": receipt_payload(),
        "section_scheduler_journal_manifest.v1": journal_payload(),
        "worker_sandbox_profile.v1": profile,
        "section_native_inventory_plan.v1": native_plan_payload(),
        "section_native_inventory.v1": {
            "program_ref": PROGRAM_REF, "native_inventory_plan_ref": REF0,
            "base_commit": G0, "observation_id": H0, "root_id": H1,
            "observer_assignment_ref": REF0,
            "observation_workspace_id": H2, "phase": "pre-dispatch",
            "observed_root_filesystem_id": H0, "observed_root_file_id": H1,
            "entries": [], "inventory_sha256": H2,
        },
        "worker_sandbox_attestation.v1": {
            "program_ref": PROGRAM_REF, "assignment_ref": REF0,
            "launcher_receipt_ref": REF0, "journal_manifest_ref": REF0,
            "sandbox_profile_ref": REF0, "observed_mount_table_ref": REF0,
            "observed_process_status_ref": REF0,
            "observed_environment_ref": REF0, "observed_fd_table_ref": REF0,
            "source_snapshot_ref": REF0, "output_inventory_ref": REF0,
            "native_inventory_before_refs": [REF0],
            "native_inventory_after_refs": [REF0], "unexpected_fd_count": 0,
            "writable_filesystem_fd_count": 0, "external_write_attempt_count": 1,
            "external_write_success_count": 0, "exit_status": 0,
        },
        "section_finding.v1": {
            "program_ref": PROGRAM_REF, "contract_ref": REF0,
            "assessor_assignment_ref": REF0, "affected_proposal_ref": REF0,
            "finding_declaration_ref": REF0, "audit_level": "section",
            "severity": "LOW", "invariant_id": "invariant-1",
            "claim": "A bounded observation.", "evidence_ref": REF0,
            "reproduction_ref": REF0, "affected_path": None,
            "blocks_local_pass": False, "status": "open",
            "predecessor_finding_ref": None, "resolution_evidence_ref": None,
        },
        "section_assessment_manifest.v1": {
            "program_ref": PROGRAM_REF, "contract_ref": REF0,
            "work_item_id": H0, "assessor_assignment_ref": REF0,
            "assessor_context_ref": REF0, "proposal_ref": REF0,
            "assessment_declaration_ref": REF0,
            "assessor_output_inventory_ref": REF0,
            "check_declaration_refs": [REF0], "check_results": [CHECK],
            "finding_refs": [], "finding_inventory_sha256": H0,
            "finding_count": 0, "open_blocking_count": 0,
            "local_assessment": "pass", "error_reason": None,
            "predecessor_assessment_ref": None,
        },
        "section_evidence_bundle.v1": {
            "program_ref": PROGRAM_REF, "contract_ref": REF0,
            "work_item_id": H0, "base_commit": G0,
            "builder_assignment_ref": REF0, "assessor_assignment_ref": REF0,
            "builder_launcher_receipt_ref": REF0,
            "assessor_launcher_receipt_ref": REF0,
            "builder_journal_manifest_ref": REF0,
            "assessor_journal_manifest_ref": REF0,
            "builder_context_ref": REF0, "assessor_context_ref": REF0,
            "builder_sandbox_attestation_ref": REF0,
            "assessor_sandbox_attestation_ref": REF0, "proposal_ref": REF0,
            "diff_preview_ref": REF0, "assessment_manifest_ref": REF0,
            "test_manifest_ref": REF0, "test_result_refs": [],
            "invariant_results": [CHECK], "local_assessment": "pass",
            "error_reason": None, "resource_metrics": [METRIC],
            "dependency_snapshot_ref": REF0, "staleness_input_refs": [REF0],
        },
        "boundary_impact_report.v1": {
            "program_ref": PROGRAM_REF, "work_graph_ref": REF0,
            "section_bundle_refs": [REF0], "final_scope_ref": REF0,
            "changed_section_ids": ["section-a"],
            "changed_interfaces": [INTERFACE], "affected_contract_refs": [REF0],
            "dependency_closure_ref": REF0,
            "activated_check_results": [CHECK], "conflict_evidence_refs": [],
            "unknown_classification_count": 0,
            "required_system_audit_scope_ids": ["system-1"],
        },
        "section_comparison_report.v1": {
            "program_ref": PROGRAM_REF, "workload_identity_sha256": H0,
            "sequential_root_ref": REF0,
            "hierarchical_root_ref": {"record_id": H1,
                                      "content_sha256": H2},
            "metric_results": [METRIC], "seeded_defect_ids": ["defect-1"],
            "sequential_detected_defect_ids": ["defect-1"],
            "hierarchical_detected_defect_ids": ["defect-1"],
            "escaped_defect_ids": [], "limitations": ["bounded-pilot"],
            "conclusion": "non_inferior",
        },
        "final_scope_manifest.v1": {
            "program_ref": PROGRAM_REF, "work_graph_ref": REF0,
            "base_commit": G0, "predicted_changes": [ADD],
            "actual_changes": [],
            "realized_system_artifact_paths": [
                "artifacts/section-council/pilot-001/content/a.json"],
            "section_bundle_refs": [REF0], "assembler_binary_ref": REF0,
            "assembled_tree_sha256": H0,
            "envelope_paths": [
                "artifacts/section-council/pilot-001/final-scope.json",
                "artifacts/section-council/pilot-001/root.json"],
        },
        "section_evidence_root.v1": {
            "planned_request_id": "pilot-001", "program_ref": PROGRAM_REF,
            "parent_build_event_id": "000001-00000000",
            "parent_build_event_hash": H0, "base_commit": G0,
            "work_graph_ref": REF0, "final_scope_ref": REF0,
            "record_inventory": [{"schema_version": "section_program.v1",
                                  "record_id": H0, "content_sha256": H1,
                                  "repository_relpath": "artifacts/program.json"}],
            "operation_log_ref": REF0, "record_count": 1,
        },
    }
    return copy.deepcopy(mapping[schema])


@pytest.mark.parametrize("schema", sorted(RECORD_TYPES))
def test_every_frozen_record_has_exact_self_identity(schema):
    record = make_record(schema, valid_payload(schema))
    assert validate_record(record) is not None
    bad = copy.deepcopy(record)
    bad[RECORD_TYPES[schema].id_field] = "f" * 64
    with pytest.raises(HSCValidationError, match="self id mismatch"):
        validate_record(bad)


@pytest.mark.parametrize("schema", sorted(RECORD_TYPES))
def test_every_record_rejects_missing_and_extra_top_level_keys(schema):
    record = make_record(schema, valid_payload(schema))
    missing = copy.deepcopy(record)
    missing.pop("payload")
    with pytest.raises(HSCValidationError, match="keys mismatch"):
        validate_record(missing)
    extra = copy.deepcopy(record)
    extra["status"] = "pass"
    with pytest.raises(HSCValidationError, match="keys mismatch"):
        validate_record(extra)


def test_unknown_schema_and_noncanonical_json_refuse():
    with pytest.raises(HSCValidationError, match="unknown schema"):
        validate_record({"schema_version": "section_contract.v2"})
    assert strict_json_bytes(b'{"a":1}') == {"a": 1}
    for bad in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{ "a":1}',
                b'{"a":1}\n', b'{"a":1}garbage'):
        with pytest.raises(HSCValidationError):
            strict_json_bytes(bad)


@pytest.mark.parametrize("path", [
    "/abs", "C:/drive", "../escape", "a/../b", "a/.git/b", "a\\b",
    "CON/file", "a//b", ".hidden", "a/space ",
])
def test_repository_path_refuses_ambient_or_ambiguous_authority(path):
    with pytest.raises(HSCValidationError):
        validate_path(path)


def test_native_byte_paths_round_trip_dotfiles_and_invalid_utf8():
    value = {"segments_hex": ["2e67697469676e6f7265", "2e676974", "ff80"]}
    assert validate_native_rel_path(value) == (b".gitignore", b".git", b"\xff\x80")
    for segment in ("", "0", "FF", "00", "2f", "2e", "2e2e"):
        with pytest.raises(HSCValidationError):
            validate_native_rel_path({"segments_hex": [segment]})


def test_change_truth_table_and_prediction_contract():
    validate_predicted_change(ADD)
    examples = [
        {"path": "a.txt", "kind": "add", "rename_source": None,
         "blob_before": None, "blob_after": H1, "mode_before": None,
         "mode_after": "100644"},
        {"path": "a.txt", "kind": "delete", "rename_source": None,
         "blob_before": H0, "blob_after": None, "mode_before": "100644",
         "mode_after": None},
        {"path": "a.txt", "kind": "modify", "rename_source": None,
         "blob_before": H0, "blob_after": H1, "mode_before": "100644",
         "mode_after": "100644"},
        {"path": "a.txt", "kind": "mode", "rename_source": None,
         "blob_before": H0, "blob_after": H0, "mode_before": "100644",
         "mode_after": "100755"},
        {"path": "b.txt", "kind": "rename", "rename_source": "a.txt",
         "blob_before": H0, "blob_after": H0, "mode_before": "100644",
         "mode_after": "100644"},
    ]
    for example in examples:
        validate_actual_change(example)
    bad = copy.deepcopy(examples[2])
    bad["blob_after"] = H0
    with pytest.raises(HSCValidationError):
        validate_actual_change(bad)
    bad = copy.deepcopy(examples[4])
    bad["mode_after"] = "100755"
    with pytest.raises(HSCValidationError):
        validate_actual_change(bad)


def test_journal_mode_has_one_encoding_and_native_relation():
    record = make_record("section_scheduler_journal_manifest.v1",
                         journal_payload())
    validate_record(record)
    for bad_mode in (448, "448", "0o700", "00700"):
        payload = journal_payload()
        payload["journal_mode"] = bad_mode
        with pytest.raises(HSCValidationError):
            make_record("section_scheduler_journal_manifest.v1", payload)
    payload = journal_payload()
    payload["journal_root_native_identity"]["native_mode"] = 0o40755
    with pytest.raises(HSCValidationError):
        make_record("section_scheduler_journal_manifest.v1", payload)


def test_request_binding_is_exact_and_fixed_path_paired():
    line = (f"HSC_V1 target_commit={G0} "
            "root_path=artifacts/section-council/pilot-001/root.json "
            f"root_id={H0} root_sha256={H1} root_git_blob={G0} "
            "scope_path=artifacts/section-council/pilot-001/final-scope.json "
            f"scope_id={H1} scope_sha256={H2} scope_git_blob={G0}")
    assert parse_hsc_request_binding(line).root_id == H0
    assert parse_hsc_request_binding(
        line, expected_request_id="pilot-001").root_id == H0
    for bad in (line + " ", line.replace("HSC_V1", "HSC_V2"),
                line.replace("root.json", "other.json"),
                line.replace(" target_commit", "  target_commit")):
        with pytest.raises(HSCValidationError):
            parse_hsc_request_binding(bad)


def test_request_binding_fixes_exactly_one_canonical_request_segment():
    def binding(directory):
        return (f"HSC_V1 target_commit={G0} "
                f"root_path=artifacts/section-council/{directory}/root.json "
                f"root_id={H0} root_sha256={H1} root_git_blob={G0} "
                f"scope_path=artifacts/section-council/{directory}/"
                "final-scope.json "
                f"scope_id={H1} scope_sha256={H2} scope_git_blob={G0}")
    # Extra nested segment, prefix escape, and non-canonical request segments
    # are refused; the exact four-segment canonical pair is retained.
    with pytest.raises(HSCValidationError, match="four-segment"):
        parse_hsc_request_binding(binding("extra/pilot"))
    with pytest.raises(HSCValidationError, match="canonical"):
        parse_hsc_request_binding(binding("Pilot-001"))
    with pytest.raises(HSCValidationError, match="canonical"):
        parse_hsc_request_binding(binding("pilot_001"))
    with pytest.raises(HSCValidationError, match="differs from the expected"):
        parse_hsc_request_binding(binding("pilot-001"),
                                  expected_request_id="pilot-002")
    assert parse_hsc_request_binding(binding("pilot-001")).root_path == \
        "artifacts/section-council/pilot-001/root.json"


def test_request_id_grammar_equals_canonical_council_grammar():
    candidates = ["pilot-001", "abc", "ab", "a", "A_b", "a.b", "a/b",
                  "-abc", "a" * 64, "a" * 65, "hsc-a-root-001", "UPPER",
                  "trailing-", "0k9"]
    for value in candidates:
        canonical_ok = True
        try:
            validate_request_id(value)
        except SchemaViolation:
            canonical_ok = False
        hsc_ok = True
        try:
            require_request_id(value, "probe")
        except HSCValidationError:
            hsc_ok = False
        assert hsc_ok == canonical_ok, value


@pytest.mark.parametrize("file_type,mode,valid", [
    ("regular", 0o100644, True),
    ("directory", 0o40755, True),
    ("regular", 0o40755, False),
    ("directory", 0o100644, False),
    ("regular", 0o120777, False),
    ("directory", 0o120755, False),
    ("regular", 0o10644, False),
])
def test_native_mode_type_bits_must_agree_with_file_type(file_type, mode,
                                                         valid):
    value = observation(1, directory=file_type == "directory", mode=mode)
    if valid:
        validate_native_observation(value)
    else:
        with pytest.raises(HSCValidationError, match="type bits disagree"):
            validate_native_observation(value)


SHARED_BASE = "5" * 64


def access(name, section, *, writes=(), reads=(), immutable=(), deps=(),
           priority=0, interfaces=(), stale=False, blocked=False, unknown=False):
    return WorkAccess(name * 64, section, priority, tuple(deps), tuple(writes),
                      tuple(reads), tuple(immutable), tuple(interfaces), stale,
                      blocked, unknown)


def test_conflict_classifier_allows_only_pinned_disjoint_work():
    base = {"fixtures/shared.json": SHARED_BASE}
    a = access("a", "section-a", writes=("out/a.json",),
               reads=("fixtures/shared.json",),
               immutable=(("fixtures/shared.json", SHARED_BASE),))
    b = access("b", "section-b", writes=("out/b.json",),
               reads=("fixtures/shared.json",),
               immutable=(("fixtures/shared.json", SHARED_BASE),))
    assert classify_conflict(a, b, base_content=base).conflict is False
    overlap = access("c", "section-c", writes=("out/a.json",))
    assert "write/write overlap" in \
        classify_conflict(a, overlap, base_content=base).reasons
    mutable = access("d", "section-d", reads=("out/a.json",))
    assert classify_conflict(a, mutable, base_content=base).conflict
    uncertain = access("e", "section-e", unknown=True)
    result = classify_conflict(a, uncertain, base_content=base)
    assert result.conflict and result.uncertain
    left = access("f", "section-f",
                  interfaces=(("shared-v1", 1, H0),))
    right = access("9", "section-g",
                   interfaces=(("shared-v1", 2, H0),))
    assert "shared interface version/digest mismatch" in \
        classify_conflict(left, right, base_content=base).reasons


def test_immutable_read_exemption_requires_exact_base_identity():
    base = {"fixtures/shared.json": SHARED_BASE}
    writer = access("a", "section-a", writes=("fixtures/shared.json",),
                    reads=("fixtures/shared.json",))
    pinned = access("b", "section-b", reads=("fixtures/shared.json",),
                    immutable=(("fixtures/shared.json", SHARED_BASE),))
    divergent = access("c", "section-c", reads=("fixtures/shared.json",),
                       immutable=(("fixtures/shared.json", "a" * 64),))
    unpinned = access("d", "section-d", reads=("fixtures/shared.json",))
    # Only the pin that reconstructs against the frozen base is exempt.
    assert classify_conflict(writer, pinned, base_content=base).conflict \
        is False
    # A divergent pinned identity is never exempt (64 a's vs 64 5's bytes).
    divergent_result = classify_conflict(writer, divergent, base_content=base)
    assert divergent_result.conflict
    assert "immutable pin diverges from frozen base" in \
        divergent_result.reasons
    # A path-only (unpinned) read of a written path is a conflict.
    assert classify_conflict(writer, unpinned, base_content=base).conflict
    # Without a verifiable frozen base the exemption fails closed.
    assert classify_conflict(writer, pinned).conflict
    assert classify_conflict(writer, pinned,
                             base_content={}).conflict
    # Two readers pinning one path to two identities cannot both be right.
    other = access("e", "section-e", reads=("fixtures/shared.json",),
                   immutable=(("fixtures/shared.json", "a" * 64),))
    mismatch = classify_conflict(pinned, other, base_content=base)
    assert "immutable base identity mismatch" in mismatch.reasons


def test_dependency_dispatch_and_targeted_staleness_are_deterministic():
    a, b, c = "a" * 64, "b" * 64, "c" * 64
    graph = {a: (), b: (a,), c: ()}
    closure = dependency_closure(graph)
    assert closure[b] == frozenset({a})
    items = [access("b", "section-b", deps=(a,), priority=0),
             access("c", "section-c", priority=1),
             access("a", "section-a", priority=1)]
    assert dispatch_order(items) == (a, c, b)
    assert stale_work_items(graph, {a: ("x",), b: ("y",), c: ("z",)},
                            ("x",)) == frozenset({a, b})
    with pytest.raises(HSCValidationError, match="cycle"):
        dependency_closure({a: (b,), b: (a,)})


def test_dispatch_uses_longest_dependency_depth_not_ancestor_count():
    a, b, c, d, e, f = (character * 64 for character in "abcdef")
    # d has three direct ancestors but depth one; c has a two-edge chain.
    items = [
        access("a", "section-a"),
        access("b", "section-b", deps=(a,)),
        access("c", "section-c", deps=(b,), priority=9),
        access("d", "section-d", deps=(a, e, f), priority=0),
        access("e", "section-e"),
        access("f", "section-f"),
    ]
    order = dispatch_order(items)
    assert order.index(d) < order.index(c)


def bootstrap_store():
    schema_bytes = b'{}'
    schema_payload = valid_payload("section_bootstrap_content.v1")
    schema_payload["blob_sha256"] = hashlib.sha256(schema_bytes).hexdigest()
    schema = make_record("section_bootstrap_content.v1", schema_payload)
    registry = make_record("section_principal_registry.v1",
                           valid_payload("section_principal_registry.v1"))
    program_payload = valid_payload("section_program.v1")
    program_payload["schema_profile_refs"] = [record_ref(schema)]
    program_payload["principal_registry_ref"] = record_ref(registry)
    program = make_record("section_program.v1", program_payload)
    return (RecordStore(
        [schema, registry, program],
        blobs={schema_payload["storage_relpath"]: schema_bytes}),
        schema, registry, program)


def test_typed_reference_and_blob_validation_is_exact():
    store, schema, registry, program = bootstrap_store()
    store.validate_all()
    bad_bytes = RecordStore(
        [schema, registry, program],
        blobs={schema["payload"]["storage_relpath"]: b'[]'})
    with pytest.raises(HSCValidationError, match="size or digest"):
        bad_bytes.validate_all()
    payload = copy.deepcopy(program["payload"])
    payload["schema_profile_refs"] = [record_ref(registry)]
    wrong_type = make_record("section_program.v1", payload)
    with pytest.raises(HSCValidationError, match="type substitution"):
        RecordStore([schema, registry, wrong_type], blobs={
            schema["payload"]["storage_relpath"]: b'{}'}).validate_all()
    payload = copy.deepcopy(program["payload"])
    payload["schema_profile_refs"][0]["content_sha256"] = H0
    stale = make_record("section_program.v1", payload)
    with pytest.raises(HSCValidationError, match="content SHA mismatch"):
        RecordStore([schema, registry, stale], blobs={
            schema["payload"]["storage_relpath"]: b'{}'}).validate_all()
