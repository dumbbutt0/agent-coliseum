"""Complete-root and cross-record adversarial proofs for HSC-A."""

from __future__ import annotations

import copy
import hashlib

import pytest

from tools.council.schemas import canonical_json, domain_hash
from tools.section_council import HSCValidationError, RecordStore
from tools.section_council.core import file_id, filesystem_id, locator_sha256
from tools.section_council.records import (
    make_record,
    record_id,
    record_ref,
)
from tools.section_council.store import compute_content_sha


REQUEST = "hsc-a-root-001"
BASE = "0" * 40
EVENT_ID = "001552-1234abcd"
EVENT_HASH = "e" * 64
H0 = "0" * 64
H1 = "1" * 64
H2 = "2" * 64
PROJECT_PREDICTION = {
    "path": "reports/hsc-a-proof.json",
    "kind": "add",
    "rename_source": None,
    "blob_before": None,
    "mode_before": None,
    "required": True,
}
BUDGET = {
    "max_wall_seconds": 30,
    "max_cpu_seconds": 20,
    "max_output_bytes": 4096,
    "max_attempts": 1,
}
INTERFACE = {"interface_id": "report-v1", "version": 1, "digest": H1}


def _ref_key(ref):
    return canonical_json(ref).encode("utf-8")


def _add_prediction(path):
    return {
        "path": path,
        "kind": "add",
        "rename_source": None,
        "blob_before": None,
        "mode_before": None,
        "required": False,
    }


def _observation(index, *, directory=True, mode=None):
    return {
        "profile": "linux-native-id-v1",
        "statx_mount_id": index,
        "device_major": 8,
        "device_minor": 1,
        "statfs_fsid_word0": 2,
        "statfs_fsid_word1": 3,
        "file_handle_type": 1,
        "file_handle_bytes_hex": f"{index:032x}",
        "inode": index,
        "file_type": "directory" if directory else "regular",
        "link_count": 1,
        "native_mode": mode if mode is not None else
        (0o40755 if directory else 0o100644),
    }


def _locator(index, segments=()):
    return {
        "platform": "linux-bwrap-v1",
        "anchor_name": f"root-{index}",
        "anchor_id": f"{index:064x}",
        "segments_hex": list(segments),
        "resolution": "openat2-beneath-no-magiclinks-no-symlinks-v1",
    }


def _root(program_ref, index, kind, *, workspace=None, segments=(),
          view="full-native-tree-v1", delegated_root=None,
          locator_index=None):
    native = _observation(index)
    locator = _locator(index if locator_index is None else locator_index,
                       segments)
    root = {
        "root_id": H0,
        "root_kind": kind,
        "view_kind": view,
        "namespace_id": H0,
        "locator": locator,
        "locator_sha256": locator_sha256(locator),
        "native_identity": native,
        "filesystem_id": filesystem_id(native),
        "file_id": file_id(native),
        "workspace_id": workspace,
        "delegated_control_root_id": (
            delegated_root["root_id"] if delegated_root else None),
        "delegated_control_identity": (
            delegated_root["native_identity"] if delegated_root else None),
    }
    root["namespace_id"] = domain_hash("council:native-namespace:v1", {
        "locator_sha256": root["locator_sha256"],
        "program_ref": program_ref,
        "root_kind": kind,
        "view_kind": view,
        "workspace_id": workspace,
    })
    preimage = dict(root)
    preimage.pop("root_id")
    root["root_id"] = domain_hash("council:native-root:v1", {
        "program_ref": program_ref,
        "root_spec": preimage,
    })
    return root


def _plan(program_ref, roots, *, scope, work_item=None, role=None,
          workspace=None):
    observations = []
    phases = (("pre-assembly", "post-assembly") if scope == "assembly"
              else ("pre-dispatch", "post-worker"))
    for root in roots:
        for phase in phases:
            row = {
                "observation_id": H0,
                "root_id": root["root_id"],
                "phase": phase,
                "scope": scope,
                "work_item_id": work_item,
                "role": role,
                "attempt": None if scope == "assembly" else 0,
                "workspace_id": workspace,
            }
            preimage = dict(row)
            preimage.pop("observation_id")
            preimage["program_ref"] = program_ref
            row["observation_id"] = domain_hash(
                "council:native-observation-requirement:v1", preimage)
            observations.append(row)
    observations.sort(key=lambda row: row["observation_id"])
    roots = sorted(copy.deepcopy(roots), key=lambda row: row["root_id"])
    return make_record("section_native_inventory_plan.v1", {
        "program_ref": program_ref,
        "base_commit": BASE,
        "scope": scope,
        "work_item_id": work_item,
        "role": role,
        "attempt": None if scope == "assembly" else 0,
        "workspace_id": workspace,
        "roots": roots,
        "root_count": len(roots),
        "observations": observations,
        "observation_count": len(observations),
    })


def _entry_hash(domain, payload):
    preimage = dict(payload)
    preimage.pop("scheduler_journal_entry_sha256")
    return domain_hash(domain, preimage)


class RootFixture:
    """Construct one small but complete evidence root in canonical order."""

    def __init__(self):
        self.records = []
        self.paths = {}
        self.blobs = {}
        self.record_slot = 0
        self.content_slot = 0
        self.prefix = f"artifacts/section-council/{REQUEST}/"
        self.event = None
        self.root = None

    def _record_path(self):
        path = f"{self.prefix}records/{self.record_slot:03d}.json"
        self.record_slot += 1
        return path

    def add(self, record, path=None):
        path = path or self._record_path()
        self.records.append(record)
        self.paths[record_id(record)] = path
        return record

    def content(self, program_ref, artifact, data=None, *, producer=None,
                media="application/json"):
        if data is None:
            data = canonical_json({}).encode("utf-8")
        path = f"{self.prefix}content/{self.content_slot:03d}.json"
        self.content_slot += 1
        payload = {
            "program_ref": program_ref,
            "artifact_type": artifact,
            "storage_relpath": path,
            "media_type": media,
            "byte_length": len(data),
            "blob_sha256": hashlib.sha256(data).hexdigest(),
            "producer_assignment_ref": (
                record_ref(producer) if producer is not None else None),
            "parent_content_refs": [],
        }
        record = self.add(make_record("section_content_record.v1", payload))
        self.blobs[path] = data
        return record

    def _dispatch(self, *, program, registry, contract, work_item_id, role,
                  principal, control, credential, workspace, context, profile,
                  first_sequence, predecessor=None):
        pref = record_ref(program)
        common = {
            "program_ref": pref,
            "principal_registry_ref": record_ref(registry),
            "scheduler_authority_id": registry["payload"][
                "scheduler_authority_id"],
            "scheduler_journal_sequence": first_sequence,
            "scheduler_journal_entry_sha256": H0,
            "contract_ref": record_ref(contract),
            "work_item_id": work_item_id,
            "role": role,
            "principal_id": principal,
            "authority_control_id": control,
            "principal_credential_digest": credential,
            "launcher_executable_sha256": "7" * 64,
            "session_nonce": ("b" if role == "builder" else "a") * 64,
            "attempt": 0,
            "context_ref": record_ref(context),
            "sandbox_profile_ref": record_ref(profile),
            "workspace_id": workspace,
            "output_leaf": f"{role}-leaf",
        }
        common["scheduler_journal_entry_sha256"] = _entry_hash(
            "council:section-launch-authorization-entry:v1", common)
        authorization = self.add(make_record(
            "section_launcher_authorization.v1", common))

        assignment_payload = {
            key: value for key, value in common.items()
            if key != "launcher_executable_sha256"
        }
        assignment_payload["scheduler_journal_sequence"] = first_sequence + 1
        assignment_payload["launcher_authorization_ref"] = record_ref(
            authorization)
        assignment_payload["scheduler_journal_entry_sha256"] = _entry_hash(
            "council:section-assignment-entry:v1", assignment_payload)
        assignment = self.add(make_record("section_assignment.v1",
                                          assignment_payload))

        receipt_payload = {
            key: value for key, value in common.items()
            if key not in ("principal_registry_ref", "contract_ref",
                           "work_item_id")
        }
        receipt_payload["authorization_ref"] = record_ref(authorization)
        receipt_payload["assignment_ref"] = record_ref(assignment)
        receipt_payload["scheduler_journal_sequence"] = first_sequence + 2
        receipt_payload["barrier_status"] = "ready"
        receipt_payload["scheduler_journal_entry_sha256"] = _entry_hash(
            "council:section-launch-receipt-entry:v1", receipt_payload)
        receipt = self.add(make_record("section_launcher_receipt.v1",
                                      receipt_payload))

        journal_native = _observation(900, mode=0o40700)
        journal_locator = _locator(900)
        journal_payload = {
            "program_ref": pref,
            "principal_registry_ref": record_ref(registry),
            "scheduler_authority_id": registry["payload"][
                "scheduler_authority_id"],
            "journal_root_id": H0,
            "journal_root_locator": journal_locator,
            "journal_root_locator_sha256": locator_sha256(journal_locator),
            "journal_root_native_identity": journal_native,
            "journal_root_filesystem_id": filesystem_id(journal_native),
            "journal_root_file_id": file_id(journal_native),
            "journal_owner_principal_id": "scheduler-writer",
            "journal_owner_control_id": "d" * 64,
            "journal_mode": "0700",
            "predecessor_journal_manifest_ref": (
                record_ref(predecessor) if predecessor else None),
            "first_sequence": first_sequence,
            "last_sequence": first_sequence + 2,
            "entries": [],
        }
        journal_payload["journal_root_id"] = domain_hash(
            "council:scheduler-journal-root:v1", {
                "journal_mode": "0700",
                "journal_owner_control_id": "d" * 64,
                "journal_owner_principal_id": "scheduler-writer",
                "journal_root_file_id": journal_payload["journal_root_file_id"],
                "journal_root_filesystem_id": journal_payload[
                    "journal_root_filesystem_id"],
                "journal_root_locator_sha256": journal_payload[
                    "journal_root_locator_sha256"],
                "principal_registry_ref": record_ref(registry),
                "program_ref": pref,
            })
        dispatch_records = (authorization, assignment, receipt)
        kinds = ("authorization", "assignment", "receipt")
        writer_roles = ("scheduler", "scheduler", "launcher")
        writer_principals = ("scheduler-writer", "scheduler-writer",
                             "launcher-writer")
        writer_controls = ("d" * 64, "d" * 64, "c" * 64)
        journal_payload["entries"] = [{
            "ordinal": ordinal,
            "sequence": first_sequence + ordinal,
            "entry_kind": kinds[ordinal],
            "record_ref": record_ref(dispatch_records[ordinal]),
            "entry_sha256": dispatch_records[ordinal]["payload"][
                "scheduler_journal_entry_sha256"],
            "writer_role": writer_roles[ordinal],
            "writer_principal_id": writer_principals[ordinal],
            "writer_control_id": writer_controls[ordinal],
        } for ordinal in range(3)]
        journal = self.add(make_record(
            "section_scheduler_journal_manifest.v1", journal_payload))
        return authorization, assignment, receipt, journal

    def build(self):
        bootstrap_data = canonical_json({"schema": "hsc-v1"}).encode("utf-8")
        bootstrap = self.add(make_record("section_bootstrap_content.v1", {
            "planned_request_id": REQUEST,
            "artifact_type": "schema_profile",
            "storage_relpath": f"{self.prefix}bootstrap/schema.json",
            "media_type": "application/json",
            "byte_length": len(bootstrap_data),
            "blob_sha256": hashlib.sha256(bootstrap_data).hexdigest(),
        }))
        self.blobs[bootstrap["payload"]["storage_relpath"]] = bootstrap_data
        read_data = canonical_json({"files": []}).encode("utf-8")
        read_inventory = self.add(make_record(
            "section_bootstrap_content.v1", {
                "planned_request_id": REQUEST,
                "artifact_type": "read_inventory",
                "storage_relpath": f"{self.prefix}bootstrap/read.json",
                "media_type": "application/json",
                "byte_length": len(read_data),
                "blob_sha256": hashlib.sha256(read_data).hexdigest(),
            }))
        self.blobs[read_inventory["payload"]["storage_relpath"]] = read_data

        registry = self.add(make_record("section_principal_registry.v1", {
            "planned_request_id": REQUEST,
            "repository": "/home/dummy/agent-coliseum",
            "base_commit": BASE,
            "enrollment_registry_path": "configs/hsc-principals.json",
            "enrollment_registry_git_blob": "1" * 40,
            "enrollment_registry_version": 1,
            "enrollment_registry_digest": "2" * 64,
            "scheduler_authority_id": "3" * 64,
            "scheduler_writer_principal_id": "scheduler-writer",
            "scheduler_writer_control_id": "d" * 64,
            "launcher_writer_principal_id": "launcher-writer",
            "launcher_writer_control_id": "c" * 64,
            "principals": [{
                "principal_id": "assessor-1",
                "allowed_role": "assessor",
                "authority_control_id": "4" * 64,
                "authority_control_key_digest": "5" * 64,
                "principal_credential_digest": "6" * 64,
                "launcher_profile_id": "assessor-profile",
                "enrollment_evidence_sha256": "7" * 64,
            }, {
                "principal_id": "builder-1",
                "allowed_role": "builder",
                "authority_control_id": "8" * 64,
                "authority_control_key_digest": "9" * 64,
                "principal_credential_digest": "a" * 64,
                "launcher_profile_id": "builder-profile",
                "enrollment_evidence_sha256": "b" * 64,
            }],
        }))

        # The wrapper freezes bounded optional slots before the program exists.
        slots = [f"{self.prefix}records/{index:03d}.json"
                 for index in range(200)]
        slots += [f"{self.prefix}content/{index:03d}.json"
                  for index in range(100)]
        slots += [f"{self.prefix}bootstrap/schema.json",
                  f"{self.prefix}bootstrap/read.json"]
        system_predictions = sorted(
            (_add_prediction(path) for path in slots),
            key=lambda row: (row["path"], row["kind"], ""))
        program = self.add(make_record("section_program.v1", {
            "planned_request_id": REQUEST,
            "repository": "/home/dummy/agent-coliseum",
            "base_commit": BASE,
            "execution_mode": "hierarchical",
            "section_declarations": [{
                "section_id": "section-a",
                "predicted_changes": [PROJECT_PREDICTION],
                "read_inventory_refs": [record_ref(read_inventory)],
                "dependency_section_ids": [],
                "budget": BUDGET,
                "assessment_profile_id": "assessment-v1",
            }],
            "schema_profile_refs": [record_ref(bootstrap)],
            "principal_registry_ref": record_ref(registry),
            "system_artifact_predictions": system_predictions,
            "root_policy_version": 1,
        }))
        pref = record_ref(program)
        self.event = {
            "event_id": EVENT_ID,
            "event_hash": EVENT_HASH,
            "event_type": "BUILD_STARTED",
            "request_id": REQUEST,
            "repository": "/home/dummy/agent-coliseum",
            "target_commit": BASE,
            "payload": {
                "section_program_id": pref["record_id"],
                "section_program_content_sha256": pref["content_sha256"],
                "hsc_base_commit": BASE,
                "hsc_execution_mode": "hierarchical",
            },
        }

        assessment_profile = self.content(pref, "assessment_profile")
        source_snapshot = self.content(pref, "source_snapshot")
        test_result = self.content(pref, "test_result")
        test_manifest = self.content(pref, "test_manifest")
        assembler = self.content(
            pref, "assembler_binary", b"fixture-assembler",
            media="application/octet-stream")
        dependency_snapshot = self.content(pref, "read_inventory")
        dependency_closure = self.content(pref, "read_inventory")
        operation_log = self.content(pref, "operation_log")

        contract = self.add(make_record("section_contract.v1", {
            "program_ref": pref,
            "planned_request_id": REQUEST,
            "parent_build_event_id": EVENT_ID,
            "parent_build_event_hash": EVENT_HASH,
            "base_commit": BASE,
            "section_id": "section-a",
            "contract_version": 1,
            "objective": "Emit one deterministic report.",
            "predicted_changes": [PROJECT_PREDICTION],
            "read_inventory_refs": [record_ref(read_inventory)],
            "forbidden_host_roots": ["council-root"],
            "allowed_operations": ["emit_report"],
            "forbidden_operations": ["council_write", "git_write"],
            "upstream_contract_refs": [],
            "consumed_interfaces": [],
            "exported_interfaces": [INTERFACE],
            "required_invariant_ids": ["invariant-1"],
            "required_check_ids": ["check-1"],
            "required_evidence_ids": ["evidence-1"],
            "threat_ids": ["scope-escape"],
            "assessment_profile_ref": record_ref(assessment_profile),
            "budget": BUDGET,
            "executor_profile_ids": ["fixture-v1"],
            "escalation_rule_ids": ["fail-closed"],
            "completion_condition_ids": ["report-emitted"],
            "integration_precondition_ids": ["council-audit"],
        }))
        item = {
            "work_item_id": H0,
            "section_contract_ref": record_ref(contract),
            "operation": "emit_report",
            "dependency_work_item_ids": [],
            "read_inventory_refs": [record_ref(read_inventory)],
            "predicted_changes": [PROJECT_PREDICTION],
            "shared_interfaces": [INTERFACE],
            "required_audit_levels": ["section", "system"],
            "priority": 0,
            "budget": BUDGET,
        }
        item_preimage = dict(item)
        item_preimage.pop("work_item_id")
        item_preimage["program_ref"] = pref
        item["work_item_id"] = domain_hash(
            "council:section-work-item:v1", item_preimage)
        work_item_id = item["work_item_id"]
        graph = self.add(make_record("section_work_graph.v1", {
            "program_ref": pref,
            "contract_refs": [record_ref(contract)],
            "work_items": [item],
        }))

        candidate_workspace = "f" * 64
        builder_workspace = "b" * 64
        assessor_workspace = "a" * 64
        common = _root(pref, 3, "common-git", locator_index=2,
                       segments=("7265706f", "2e676974"))
        checkout = _root(
            pref, 2, "integration-checkout", segments=("7265706f",),
            view="checkout-excluding-delegated-dotgit-v1",
            delegated_root=common)
        central = [
            _root(pref, 1, "candidate", workspace=candidate_workspace),
            checkout,
            common,
            _root(pref, 4, "council-root"),
            _root(pref, 5, "owner-anchors"),
            _root(pref, 6, "other-worker-leaves"),
            _root(pref, 7, "canonical-evidence"),
            _root(pref, 8, "hidden-suites"),
        ]
        builder_runtime = _root(pref, 9, "runtime-readonly",
                                workspace=builder_workspace)
        builder_output = _root(pref, 10, "builder-output",
                               workspace=builder_workspace)
        assessor_runtime = _root(pref, 11, "runtime-readonly",
                                 workspace=assessor_workspace)
        assessor_output = _root(pref, 12, "assessor-output",
                                workspace=assessor_workspace)
        builder_plan = self.add(_plan(
            pref, central + [builder_runtime, builder_output],
            scope="builder-dispatch", work_item=work_item_id, role="builder",
            workspace=builder_workspace))
        assessor_plan = self.add(_plan(
            pref, central + [assessor_runtime, assessor_output],
            scope="assessor-dispatch", work_item=work_item_id,
            role="assessor", workspace=assessor_workspace))
        assembly_plan = self.add(_plan(
            pref, central + [builder_runtime, builder_output,
                             assessor_runtime, assessor_output],
            scope="assembly"))

        def profile(plan):
            return self.add(make_record("worker_sandbox_profile.v1", {
                "program_ref": pref,
                "platform": "linux-bwrap-v1",
                "launcher_binary_sha256": "7" * 64,
                "argv_template_sha256": "8" * 64,
                "native_inventory_plan_ref": record_ref(plan),
                "source_snapshot_ref": record_ref(source_snapshot),
                "read_only_mount_refs": [record_ref(source_snapshot)],
                "writable_mountpoint": "/out",
                "private_tmpfs_bytes": 4096,
                "unshare_user": True,
                "unshare_pid": True,
                "unshare_net": True,
                "no_new_privileges": True,
                "capability_set": [],
                "seccomp_profile_sha256": "9" * 64,
                "environment_allowlist": [],
                "fd_policy": "close-all-except-stdio-v1",
                "permitted_fds": [
                    {"fd": 0, "role": "stdin", "access": "read",
                     "target_kind": "null"},
                    {"fd": 1, "role": "stdout", "access": "write",
                     "target_kind": "pipe"},
                    {"fd": 2, "role": "stderr", "access": "write",
                     "target_kind": "pipe"},
                ],
            }))

        builder_profile = profile(builder_plan)
        assessor_profile = profile(assessor_plan)
        builder_context = self.add(make_record("section_context_bundle.v1", {
            "program_ref": pref,
            "contract_ref": record_ref(contract),
            "work_item_id": work_item_id,
            "base_commit": BASE,
            "role": "builder",
            "source_files": [],
            "interface_refs": [],
            "policy_files": [],
            "test_files": [],
            "prior_finding_refs": [],
            "proposal_ref": None,
            "deterministic_result_refs": [],
            "omitted_category_ids": [],
        }))
        _, builder_assignment, builder_receipt, builder_journal = \
            self._dispatch(
                program=program, registry=registry, contract=contract,
                work_item_id=work_item_id, role="builder",
                principal="builder-1", control="8" * 64,
                credential="a" * 64, workspace=builder_workspace,
                context=builder_context, profile=builder_profile,
                first_sequence=0)

        proposal = self.content(pref, "proposal", producer=builder_assignment)
        diff_preview = self.content(
            pref, "diff_preview", producer=builder_assignment)
        builder_output_inventory = self.content(
            pref, "read_inventory", producer=builder_assignment)
        assessor_context = self.add(make_record(
            "section_context_bundle.v1", {
                "program_ref": pref,
                "contract_ref": record_ref(contract),
                "work_item_id": work_item_id,
                "base_commit": BASE,
                "role": "assessor",
                "source_files": [],
                "interface_refs": [INTERFACE],
                "policy_files": [],
                "test_files": [],
                "prior_finding_refs": [],
                "proposal_ref": record_ref(proposal),
                "deterministic_result_refs": [record_ref(test_result)],
                "omitted_category_ids": [],
            }))
        _, assessor_assignment, assessor_receipt, assessor_journal = \
            self._dispatch(
                program=program, registry=registry, contract=contract,
                work_item_id=work_item_id, role="assessor",
                principal="assessor-1", control="4" * 64,
                credential="6" * 64, workspace=assessor_workspace,
                context=assessor_context, profile=assessor_profile,
                first_sequence=3, predecessor=builder_journal)
        assessor_output_inventory = self.content(
            pref, "read_inventory", producer=assessor_assignment)

        assignment_for = {
            record_id(builder_plan): builder_assignment,
            record_id(assessor_plan): assessor_assignment,
        }
        inventory_for = {}
        for plan in (builder_plan, assessor_plan, assembly_plan):
            roots = {root["root_id"]: root for root in plan["payload"]["roots"]}
            before = []
            after = []
            for requirement in plan["payload"]["observations"]:
                root_spec = roots[requirement["root_id"]]
                assignment = assignment_for.get(record_id(plan))
                observer_ref = record_ref(assignment) if assignment else None
                payload = {
                    "program_ref": pref,
                    "native_inventory_plan_ref": record_ref(plan),
                    "base_commit": BASE,
                    "observation_id": requirement["observation_id"],
                    "root_id": root_spec["root_id"],
                    "observer_assignment_ref": observer_ref,
                    "observation_workspace_id": requirement["workspace_id"],
                    "phase": requirement["phase"],
                    "observed_root_filesystem_id": root_spec["filesystem_id"],
                    "observed_root_file_id": root_spec["file_id"],
                    "entries": [],
                    "inventory_sha256": H0,
                }
                payload["inventory_sha256"] = domain_hash(
                    "council:section-native-inventory-content:v1", {
                        "native_inventory_plan_ref": record_ref(plan),
                        "root_spec": root_spec,
                        "observation_requirement": requirement,
                        "observer_assignment_ref": observer_ref,
                        "observation_workspace_id": requirement["workspace_id"],
                        "phase": requirement["phase"],
                        "entries": [],
                    })
                inventory = self.add(make_record(
                    "section_native_inventory.v1", payload))
                inventory_for[(record_id(plan), requirement["observation_id"])] = \
                    inventory
                (before if requirement["phase"].startswith("pre-") else after) \
                    .append(record_ref(inventory))
            before.sort(key=_ref_key)
            after.sort(key=_ref_key)
            inventory_for[(record_id(plan), "before")] = before
            inventory_for[(record_id(plan), "after")] = after

        observed_evidence = [self.content(
            pref, "check_evidence", producer=assignment)
            for assignment in (builder_assignment,) * 4 + (assessor_assignment,) * 4]

        def attestation(role, assignment, receipt, journal, profile_record,
                        plan, output_inventory, offset):
            return self.add(make_record("worker_sandbox_attestation.v1", {
                "program_ref": pref,
                "assignment_ref": record_ref(assignment),
                "launcher_receipt_ref": record_ref(receipt),
                "journal_manifest_ref": record_ref(journal),
                "sandbox_profile_ref": record_ref(profile_record),
                "observed_mount_table_ref": record_ref(
                    observed_evidence[offset]),
                "observed_process_status_ref": record_ref(
                    observed_evidence[offset + 1]),
                "observed_environment_ref": record_ref(
                    observed_evidence[offset + 2]),
                "observed_fd_table_ref": record_ref(
                    observed_evidence[offset + 3]),
                "source_snapshot_ref": record_ref(source_snapshot),
                "output_inventory_ref": record_ref(output_inventory),
                "native_inventory_before_refs": inventory_for[
                    (record_id(plan), "before")],
                "native_inventory_after_refs": inventory_for[
                    (record_id(plan), "after")],
                "unexpected_fd_count": 0,
                "writable_filesystem_fd_count": 0,
                "external_write_attempt_count": 1,
                "external_write_success_count": 0,
                "exit_status": 0,
            }))

        builder_attestation = attestation(
            "builder", builder_assignment, builder_receipt, builder_journal,
            builder_profile, builder_plan, builder_output_inventory, 0)
        assessor_attestation = attestation(
            "assessor", assessor_assignment, assessor_receipt,
            assessor_journal, assessor_profile, assessor_plan,
            assessor_output_inventory, 4)

        check_evidence = self.content(
            pref, "check_evidence", producer=assessor_assignment)
        check_data = canonical_json({
            "check_id": "check-1",
            "status": "pass",
            "evidence_output_relpath": check_evidence["payload"][
                "storage_relpath"].rsplit("/", 1)[-1],
        }).encode("utf-8")
        check_declaration = self.content(
            pref, "check_declaration", check_data,
            producer=assessor_assignment)
        assessment_data = canonical_json({
            "schema_version": "section-assessment-declaration.v1",
            "program_ref": pref,
            "contract_ref": record_ref(contract),
            "work_item_id": work_item_id,
            "assessor_assignment_ref": record_ref(assessor_assignment),
            "assessor_context_ref": record_ref(assessor_context),
            "proposal_ref": record_ref(proposal),
            "check_declaration_output_relpaths": [
                check_declaration["payload"]["storage_relpath"].rsplit("/", 1)[-1]],
            "finding_declaration_output_relpaths": [],
            "predecessor_assessment_ref": None,
            "declared_disposition": "pass",
            "error_reason": None,
        }).encode("utf-8")
        assessment_declaration = self.content(
            pref, "assessment_declaration", assessment_data,
            producer=assessor_assignment)
        check_result = {
            "check_id": "check-1",
            "status": "pass",
            "evidence_ref": record_ref(check_evidence),
        }
        invariant_result = {
            "check_id": "invariant-1",
            "status": "pass",
            "evidence_ref": record_ref(check_evidence),
        }
        assessment = self.add(make_record(
            "section_assessment_manifest.v1", {
                "program_ref": pref,
                "contract_ref": record_ref(contract),
                "work_item_id": work_item_id,
                "assessor_assignment_ref": record_ref(assessor_assignment),
                "assessor_context_ref": record_ref(assessor_context),
                "proposal_ref": record_ref(proposal),
                "assessment_declaration_ref": record_ref(
                    assessment_declaration),
                "assessor_output_inventory_ref": record_ref(
                    assessor_output_inventory),
                "check_declaration_refs": [record_ref(check_declaration)],
                "check_results": [check_result],
                "finding_refs": [],
                "finding_inventory_sha256": domain_hash(
                    "council:section-finding-inventory:v1", []),
                "finding_count": 0,
                "open_blocking_count": 0,
                "local_assessment": "pass",
                "error_reason": None,
                "predecessor_assessment_ref": None,
            }))
        bundle = self.add(make_record("section_evidence_bundle.v1", {
            "program_ref": pref,
            "contract_ref": record_ref(contract),
            "work_item_id": work_item_id,
            "base_commit": BASE,
            "builder_assignment_ref": record_ref(builder_assignment),
            "assessor_assignment_ref": record_ref(assessor_assignment),
            "builder_launcher_receipt_ref": record_ref(builder_receipt),
            "assessor_launcher_receipt_ref": record_ref(assessor_receipt),
            "builder_journal_manifest_ref": record_ref(builder_journal),
            "assessor_journal_manifest_ref": record_ref(assessor_journal),
            "builder_context_ref": record_ref(builder_context),
            "assessor_context_ref": record_ref(assessor_context),
            "builder_sandbox_attestation_ref": record_ref(builder_attestation),
            "assessor_sandbox_attestation_ref": record_ref(
                assessor_attestation),
            "proposal_ref": record_ref(proposal),
            "diff_preview_ref": record_ref(diff_preview),
            "assessment_manifest_ref": record_ref(assessment),
            "test_manifest_ref": record_ref(test_manifest),
            "test_result_refs": [record_ref(test_result)],
            "invariant_results": [invariant_result],
            "local_assessment": "pass",
            "error_reason": None,
            "resource_metrics": [{
                "metric_id": "wall-seconds",
                "availability": "unavailable",
                "unit": "seconds",
                "value": None,
                "evidence_ref": None,
            }],
            "dependency_snapshot_ref": record_ref(dependency_snapshot),
            "staleness_input_refs": [record_ref(contract)],
        }))

        anticipated_boundary_path = (
            f"{self.prefix}records/{self.record_slot:03d}.json")
        realized = sorted(
            list(self.paths.values()) + list(self.blobs) +
            [anticipated_boundary_path])
        actual = {
            "path": PROJECT_PREDICTION["path"],
            "kind": "add",
            "rename_source": None,
            "blob_before": None,
            "blob_after": H2,
            "mode_before": None,
            "mode_after": "100644",
        }
        final_scope = self.add(make_record("final_scope_manifest.v1", {
            "program_ref": pref,
            "work_graph_ref": record_ref(graph),
            "base_commit": BASE,
            "predicted_changes": [PROJECT_PREDICTION],
            "actual_changes": [actual],
            "realized_system_artifact_paths": realized,
            "section_bundle_refs": [record_ref(bundle)],
            "assembler_binary_ref": record_ref(assembler),
            "assembled_tree_sha256": H2,
            "envelope_paths": [
                f"{self.prefix}final-scope.json",
                f"{self.prefix}root.json",
            ],
        }), path=f"{self.prefix}final-scope.json")
        boundary = self.add(make_record("boundary_impact_report.v1", {
            "program_ref": pref,
            "work_graph_ref": record_ref(graph),
            "section_bundle_refs": [record_ref(bundle)],
            "final_scope_ref": record_ref(final_scope),
            "changed_section_ids": ["section-a"],
            "changed_interfaces": [INTERFACE],
            "affected_contract_refs": [record_ref(contract)],
            "dependency_closure_ref": record_ref(dependency_closure),
            "activated_check_results": [check_result],
            "conflict_evidence_refs": [],
            "unknown_classification_count": 0,
            "required_system_audit_scope_ids": ["system-scope"],
        }))
        assert self.paths[record_id(boundary)] == anticipated_boundary_path

        inventory = sorted(({
            "schema_version": record["schema_version"],
            "record_id": record_id(record),
            "content_sha256": compute_content_sha(record),
            "repository_relpath": self.paths[record_id(record)],
        } for record in self.records),
            key=lambda row: (row["schema_version"], row["record_id"]))
        self.root = make_record("section_evidence_root.v1", {
            "planned_request_id": REQUEST,
            "program_ref": pref,
            "parent_build_event_id": EVENT_ID,
            "parent_build_event_hash": EVENT_HASH,
            "base_commit": BASE,
            "work_graph_ref": record_ref(graph),
            "final_scope_ref": record_ref(final_scope),
            "record_inventory": inventory,
            "operation_log_ref": record_ref(operation_log),
            "record_count": len(inventory),
        })
        return self


@pytest.fixture(scope="module")
def complete_fixture():
    return RootFixture().build()


def test_complete_evidence_root_validates_and_orders_every_member(
        complete_fixture):
    fixture = complete_fixture
    report = RecordStore(fixture.records, blobs=fixture.blobs).validate_root(
        fixture.root, build_event=fixture.event)
    assert report.record_count == len(fixture.records)
    assert report.construction_order[-1] == record_id(fixture.root)
    assert sorted(report.construction_ordinals.values()) == list(
        range(len(fixture.records) + 1))


def test_complete_root_refuses_member_omission_and_event_substitution(
        complete_fixture):
    fixture = complete_fixture
    with pytest.raises(HSCValidationError, match="complete record set"):
        RecordStore(fixture.records[:-1], blobs=fixture.blobs).validate_root(
            fixture.root, build_event=fixture.event)
    bad_event = copy.deepcopy(fixture.event)
    bad_event["target_commit"] = "f" * 40
    with pytest.raises(HSCValidationError, match="does not bind"):
        RecordStore(fixture.records, blobs=fixture.blobs).validate_root(
            fixture.root, build_event=bad_event)


def test_complete_root_refuses_dispatch_plan_or_assembly_union_substitution(
        complete_fixture):
    fixture = complete_fixture
    plan_index = next(index for index, record in enumerate(fixture.records)
                      if record["schema_version"] ==
                      "section_native_inventory_plan.v1" and
                      record["payload"]["scope"] == "assembly")
    altered = copy.deepcopy(fixture.records)
    payload = copy.deepcopy(altered[plan_index]["payload"])
    removed = next(root for root in payload["roots"]
                   if root["root_kind"] == "runtime-readonly")
    payload["roots"] = [root for root in payload["roots"]
                        if root["root_id"] != removed["root_id"]]
    payload["root_count"] -= 1
    payload["observations"] = [row for row in payload["observations"]
                               if row["root_id"] in {
                                   root["root_id"] for root in payload["roots"]}]
    payload["observation_count"] = len(payload["observations"])
    altered[plan_index] = make_record(
        "section_native_inventory_plan.v1", payload)
    store = RecordStore(altered, blobs=fixture.blobs)
    program = next(record for record in altered
                   if record["schema_version"] == "section_program.v1")
    with pytest.raises(HSCValidationError, match="exact dispatch-root union"):
        store._validate_native_plans(program)


def test_complete_root_rebuild_is_byte_stable(complete_fixture):
    second = RootFixture().build()
    assert second.records == complete_fixture.records
    assert second.blobs == complete_fixture.blobs
    assert second.root == complete_fixture.root
    first_report = RecordStore(
        complete_fixture.records, blobs=complete_fixture.blobs).validate_root(
            complete_fixture.root, build_event=complete_fixture.event)
    second_report = RecordStore(
        second.records, blobs=second.blobs).validate_root(
            second.root, build_event=second.event)
    assert second_report == first_report
