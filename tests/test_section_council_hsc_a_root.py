"""Complete-root and cross-record adversarial proofs for HSC-A."""

from __future__ import annotations

import copy
import hashlib

import pytest

from tools.council.schemas import (GENESIS_HASH, canonical_json,
                                   compute_event_hash, domain_hash,
                                   protocol_version)
from tools.section_council import (HSCValidationError, RecordStore,
                                   compute_bundle_staleness_inputs)
from tools.section_council.core import file_id, filesystem_id, locator_sha256
from tools.section_council.records import (
    make_record,
    record_id,
    record_ref,
)
from tools.section_council.store import compute_content_sha


REQUEST = "hsc-a-root-001"
BASE = "0" * 40
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


def _inventory_bytes(owned_records):
    rows = sorted(({
        "leaf_relpath": record["payload"]["storage_relpath"].rsplit("/", 1)[-1],
        "artifact_type": record["payload"]["artifact_type"],
        "media_type": record["payload"]["media_type"],
        "byte_length": record["payload"]["byte_length"],
        "blob_sha256": record["payload"]["blob_sha256"],
    } for record in owned_records), key=lambda row: row["leaf_relpath"])
    return canonical_json({"schema_version": "section-output-inventory.v1",
                           "outputs": rows}).encode("utf-8")


class RootFixture:
    """Construct one small but complete evidence root in canonical order.

    ``tweaks`` maps a hook name to a mutator applied while building, so a
    regression can inject exactly one adversarial change and every dependent
    identity, reference, inventory, and root regenerates consistently:

    - ``contract``: fn(contract_payload)
    - ``bundle``: fn(bundle_payload)  (after staleness inputs are computed)
    - ``staleness``: fn(list_of_refs) -> list_of_refs
    - ``final_scope``: fn(final_scope_payload)
    - ``boundary``: fn(boundary_payload)
    - ``assessor_inventory_data``: fn(bytes) -> bytes
    - ``extra_content``: fn(fixture, program_ref)  (may call fixture.content)
    """

    def __init__(self):
        self.records = []
        self.paths = {}
        self.blobs = {}
        self.record_slot = 0
        self.content_slot = 0
        self.prefix = f"artifacts/section-council/{REQUEST}/"
        self.event = None
        self.chain = None
        self.root = None
        self.candidate_tree = None
        self.base_tree = None

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

    def validate(self, *, records=None, root=None, event=None, chain=None,
                 candidate_tree=None, base_tree=None, blobs=None):
        return RecordStore(
            self.records if records is None else records,
            blobs=self.blobs if blobs is None else blobs).validate_root(
                self.root if root is None else root,
                build_event=self.event if event is None else event,
                chain=self.chain if chain is None else chain,
                candidate_tree=(self.candidate_tree if candidate_tree is None
                                else candidate_tree),
                base_tree=self.base_tree if base_tree is None else base_tree)

    def build(self, tweaks=None):
        tweaks = tweaks or {}
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

        # A canonical, hash-valid, genesis-linked BUILD_STARTED authority.
        self.event = {
            "protocol_version": protocol_version(),
            "event_id": "000001-0000000a",
            "event_type": "BUILD_STARTED",
            "request_id": REQUEST,
            "sender": "claude",
            "timestamp_utc": "2026-07-16T00:00:00Z",
            "repository": "/home/dummy/agent-coliseum",
            "target_commit": BASE,
            "payload": {
                "section_program_id": pref["record_id"],
                "section_program_content_sha256": pref["content_sha256"],
                "hsc_base_commit": BASE,
                "hsc_execution_mode": "hierarchical",
            },
            "previous_event_hash": GENESIS_HASH,
        }
        self.event["event_hash"] = compute_event_hash(self.event)
        self.chain = [self.event]
        event_id = self.event["event_id"]
        event_hash = self.event["event_hash"]

        assessment_profile = self.content(pref, "assessment_profile")
        source_snapshot = self.content(pref, "source_snapshot")
        test_result = self.content(pref, "test_result")
        test_manifest = self.content(pref, "test_manifest")
        assembler = self.content(
            pref, "assembler_binary", b"fixture-assembler",
            media="application/octet-stream")
        dependency_snapshot = self.content(pref, "read_inventory")
        operation_log = self.content(pref, "operation_log")

        contract_payload = {
            "program_ref": pref,
            "planned_request_id": REQUEST,
            "parent_build_event_id": event_id,
            "parent_build_event_hash": event_hash,
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
            "required_evidence_ids": ["check-1", "invariant-1"],
            "threat_ids": ["scope-escape"],
            "assessment_profile_ref": record_ref(assessment_profile),
            "budget": BUDGET,
            "executor_profile_ids": ["fixture-v1"],
            "escalation_rule_ids": ["fail-closed"],
            "completion_condition_ids": ["report-emitted"],
            "integration_precondition_ids": ["council-audit"],
        }
        if "contract" in tweaks:
            tweaks["contract"](contract_payload)
        contract = self.add(make_record("section_contract.v1",
                                        contract_payload))
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
        closure_data = canonical_json({
            "schema_version": "section-dependency-closure.v1",
            "closure": {work_item_id: []},
        }).encode("utf-8")
        if "closure_data" in tweaks:
            closure_data = tweaks["closure_data"](closure_data)
        dependency_closure_record = self.content(
            pref, "read_inventory", closure_data)

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
        builder_observed = [self.content(
            pref, "check_evidence", producer=builder_assignment)
            for _ in range(4)]
        builder_output_inventory = self.content(
            pref, "read_inventory",
            _inventory_bytes([proposal, diff_preview] + builder_observed),
            producer=builder_assignment)

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

        assessor_observed = [self.content(
            pref, "check_evidence", producer=assessor_assignment)
            for _ in range(4)]
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
        assessor_inventory_data = _inventory_bytes(
            assessor_observed + [check_evidence, check_declaration,
                                 assessment_declaration])
        if "assessor_inventory_data" in tweaks:
            assessor_inventory_data = tweaks["assessor_inventory_data"](
                assessor_inventory_data)
        assessor_output_inventory = self.content(
            pref, "read_inventory", assessor_inventory_data,
            producer=assessor_assignment)

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

        def attestation(assignment, receipt, journal, profile_record,
                        plan, output_inventory, observed):
            return self.add(make_record("worker_sandbox_attestation.v1", {
                "program_ref": pref,
                "assignment_ref": record_ref(assignment),
                "launcher_receipt_ref": record_ref(receipt),
                "journal_manifest_ref": record_ref(journal),
                "sandbox_profile_ref": record_ref(profile_record),
                "observed_mount_table_ref": record_ref(observed[0]),
                "observed_process_status_ref": record_ref(observed[1]),
                "observed_environment_ref": record_ref(observed[2]),
                "observed_fd_table_ref": record_ref(observed[3]),
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
            builder_assignment, builder_receipt, builder_journal,
            builder_profile, builder_plan, builder_output_inventory,
            builder_observed)
        assessor_attestation = attestation(
            assessor_assignment, assessor_receipt, assessor_journal,
            assessor_profile, assessor_plan, assessor_output_inventory,
            assessor_observed)

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
        bundle_payload = {
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
        }
        staleness = compute_bundle_staleness_inputs(
            self.records, self.blobs, bundle_payload)
        if "staleness" in tweaks:
            staleness = tweaks["staleness"](staleness)
        bundle_payload["staleness_input_refs"] = staleness
        if "bundle" in tweaks:
            tweaks["bundle"](bundle_payload)
        bundle = self.add(make_record("section_evidence_bundle.v1",
                                      bundle_payload))

        if "extra_content" in tweaks:
            tweaks["extra_content"](self, pref)

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
        assembled_tree_sha256 = domain_hash(
            "council:section-project-tree:v1",
            [{"path": PROJECT_PREDICTION["path"], "blob_sha256": H2,
              "git_mode": "100644", "kind": "file"}])
        final_scope_payload = {
            "program_ref": pref,
            "work_graph_ref": record_ref(graph),
            "base_commit": BASE,
            "predicted_changes": [PROJECT_PREDICTION],
            "actual_changes": [actual],
            "realized_system_artifact_paths": realized,
            "section_bundle_refs": [record_ref(bundle)],
            "assembler_binary_ref": record_ref(assembler),
            "assembled_tree_sha256": assembled_tree_sha256,
            "envelope_paths": [
                f"{self.prefix}final-scope.json",
                f"{self.prefix}root.json",
            ],
        }
        if "final_scope" in tweaks:
            tweaks["final_scope"](final_scope_payload)
        final_scope = self.add(
            make_record("final_scope_manifest.v1", final_scope_payload),
            path=f"{self.prefix}final-scope.json")
        boundary_payload = {
            "program_ref": pref,
            "work_graph_ref": record_ref(graph),
            "section_bundle_refs": [record_ref(bundle)],
            "final_scope_ref": record_ref(final_scope),
            "changed_section_ids": ["section-a"],
            "changed_interfaces": [INTERFACE],
            "affected_contract_refs": [record_ref(contract)],
            "dependency_closure_ref": record_ref(dependency_closure_record),
            "activated_check_results": [check_result],
            "conflict_evidence_refs": [],
            "unknown_classification_count": 0,
            "required_system_audit_scope_ids": ["section-a"],
        }
        if "boundary" in tweaks:
            tweaks["boundary"](boundary_payload)
        boundary = self.add(make_record("boundary_impact_report.v1",
                                        boundary_payload))
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
            "parent_build_event_id": event_id,
            "parent_build_event_hash": event_hash,
            "base_commit": BASE,
            "work_graph_ref": record_ref(graph),
            "final_scope_ref": record_ref(final_scope),
            "record_inventory": inventory,
            "operation_log_ref": record_ref(operation_log),
            "record_count": len(inventory),
        })

        self.base_tree = []
        tree = [{"path": PROJECT_PREDICTION["path"], "blob_sha256": H2,
                 "git_mode": "100644", "kind": "file"}]
        for row in inventory:
            tree.append({"path": row["repository_relpath"],
                         "blob_sha256": row["content_sha256"],
                         "git_mode": "100644", "kind": "file"})
        for path, data in self.blobs.items():
            tree.append({"path": path,
                         "blob_sha256": hashlib.sha256(data).hexdigest(),
                         "git_mode": "100644", "kind": "file"})
        tree.append({"path": f"{self.prefix}root.json",
                     "blob_sha256": compute_content_sha(self.root),
                     "git_mode": "100644", "kind": "file"})
        tree.sort(key=lambda row: row["path"])
        self.candidate_tree = tree
        return self


@pytest.fixture(scope="module")
def complete_fixture():
    return RootFixture().build()


def test_complete_evidence_root_validates_and_orders_every_member(
        complete_fixture):
    fixture = complete_fixture
    report = fixture.validate()
    assert report.record_count == len(fixture.records)
    assert report.construction_order[-1] == record_id(fixture.root)
    assert sorted(report.construction_ordinals.values()) == list(
        range(len(fixture.records) + 1))


def test_complete_root_refuses_member_omission_and_event_substitution(
        complete_fixture):
    fixture = complete_fixture
    with pytest.raises(HSCValidationError, match="complete record set"):
        fixture.validate(records=fixture.records[:-1])
    bad_event = copy.deepcopy(fixture.event)
    bad_event["target_commit"] = "f" * 40
    with pytest.raises(HSCValidationError, match="canonical Council event"):
        fixture.validate(event=bad_event)


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
    assert second.event == complete_fixture.event
    assert second.candidate_tree == complete_fixture.candidate_tree
    assert second.validate() == complete_fixture.validate()


# --- audit 001569 finding 1: boundary fields must reconstruct ---------------

@pytest.mark.parametrize("mutator", [
    lambda p: p.update(changed_section_ids=[]),
    lambda p: p.update(changed_interfaces=[]),
    lambda p: p.update(affected_contract_refs=[]),
    lambda p: p.update(required_system_audit_scope_ids=["other-scope"]),
    lambda p: p.update(activated_check_results=[{
        "check_id": "unrelated-check", "status": "pass",
        "evidence_ref": p["activated_check_results"][0]["evidence_ref"]}]),
], ids=["sections", "interfaces", "contracts", "scopes", "checks"])
def test_boundary_semantic_fields_must_reconstruct(mutator):
    fixture = RootFixture().build(tweaks={"boundary": mutator})
    with pytest.raises(HSCValidationError, match="does not reconstruct"):
        fixture.validate()


def test_boundary_dependency_closure_bytes_must_reconstruct():
    wrong_bytes = canonical_json({
        "schema_version": "section-dependency-closure.v1",
        "closure": {},
    }).encode("utf-8")
    fixture = RootFixture().build(tweaks={
        "closure_data": lambda data: wrong_bytes})
    with pytest.raises(HSCValidationError,
                       match="closure bytes do not reconstruct"):
        fixture.validate()


# --- finding 2: assembled tree and candidate content must reconstruct -------

def test_assembled_tree_digest_must_reconstruct_from_candidate_tree():
    fixture = RootFixture().build(tweaks={
        "final_scope": lambda p: p.update(assembled_tree_sha256="9" * 64)})
    with pytest.raises(HSCValidationError,
                       match="assembled_tree_sha256 does not reconstruct"):
        fixture.validate()


def test_candidate_tree_content_substitution_or_omission_refuses(
        complete_fixture):
    fixture = complete_fixture
    project_path = PROJECT_PREDICTION["path"]
    mutated = copy.deepcopy(fixture.candidate_tree)
    for row in mutated:
        if row["path"] == project_path:
            row["blob_sha256"] = "f" * 64
    with pytest.raises(HSCValidationError,
                       match="base plus actual changes"):
        fixture.validate(candidate_tree=mutated)
    omitted = [row for row in fixture.candidate_tree
               if not row["path"].endswith("/records/000.json")]
    with pytest.raises(HSCValidationError):
        fixture.validate(candidate_tree=omitted)
    record_swap = copy.deepcopy(fixture.candidate_tree)
    for row in record_swap:
        if row["path"].endswith("/records/000.json"):
            row["blob_sha256"] = "e" * 64
    with pytest.raises(HSCValidationError, match="exact bytes"):
        fixture.validate(candidate_tree=record_swap)
    root_swap = copy.deepcopy(fixture.candidate_tree)
    for row in root_swap:
        if row["path"].endswith("/root.json"):
            row["blob_sha256"] = "d" * 64
    with pytest.raises(HSCValidationError, match="evidence root's exact"):
        fixture.validate(candidate_tree=root_swap)
    poisoned_base = [{"path": f"{fixture.prefix}stale.json",
                      "blob_sha256": "a" * 64, "git_mode": "100644",
                      "kind": "file"}]
    with pytest.raises(HSCValidationError, match="base tree already"):
        fixture.validate(base_tree=poisoned_base)


# --- finding 3: semantically unreachable inventory members ------------------

def test_orphan_inventory_member_is_unreachable():
    def add_orphan(fixture_obj, pref):
        fixture_obj.content(pref, "operation_log",
                            canonical_json({"orphan": True}).encode("utf-8"))
    fixture = RootFixture().build(tweaks={"extra_content": add_orphan})
    with pytest.raises(HSCValidationError,
                       match="semantically unreachable"):
        fixture.validate()


# --- finding 4: staleness inputs must equal the reconstructed closure -------

@pytest.mark.parametrize("mutator", [
    lambda refs: refs[1:],
    lambda refs: refs[:1],
    lambda refs: list(reversed(refs)),
    lambda refs: refs + [{"record_id": "9" * 64, "content_sha256": "9" * 64}],
], ids=["omit", "truncate", "reorder", "add"])
def test_bundle_staleness_inputs_must_reconstruct(mutator):
    # A mutation may already violate the record-level sorted-unique refs
    # contract (reorder/add) or survive to the closure reconstruction
    # (omit/truncate); either way the root path must refuse.
    with pytest.raises(HSCValidationError):
        RootFixture().build(tweaks={"staleness": mutator}).validate()


def test_staleness_closure_covers_every_typed_bundle_input(complete_fixture):
    bundle = next(record for record in complete_fixture.records
                  if record["schema_version"] == "section_evidence_bundle.v1")
    closure_ids = {ref["record_id"]
                   for ref in bundle["payload"]["staleness_input_refs"]}
    for schema in ("section_program.v1", "section_contract.v1",
                   "section_principal_registry.v1", "section_assignment.v1",
                   "section_launcher_receipt.v1",
                   "section_scheduler_journal_manifest.v1",
                   "worker_sandbox_attestation.v1",
                   "section_assessment_manifest.v1"):
        members = [record_id(record) for record in complete_fixture.records
                   if record["schema_version"] == schema]
        assert members and set(members) <= closure_ids, schema


# --- finding 5: a failed required invariant forces refusal ------------------

@pytest.mark.parametrize("status", ["fail", "error"])
def test_failed_required_invariant_blocks_pass_publication(status):
    def fail_invariant(payload):
        payload["invariant_results"] = [
            dict(payload["invariant_results"][0], status=status)]
    fixture = RootFixture().build(tweaks={"bundle": fail_invariant})
    with pytest.raises(HSCValidationError,
                       match="invariant cannot coexist|evidence identity"):
        fixture.validate()


# --- finding 9: assessor output inventory must be exhaustive ----------------

def test_assessor_output_inventory_must_be_exhaustive():
    fixture = RootFixture().build(tweaks={
        "assessor_inventory_data":
        lambda data: canonical_json({}).encode("utf-8")})
    with pytest.raises(HSCValidationError, match="output inventory"):
        fixture.validate()

    def drop_row(data):
        import json
        value = json.loads(data)
        value["outputs"] = value["outputs"][1:]
        return canonical_json(value).encode("utf-8")
    fixture = RootFixture().build(tweaks={"assessor_inventory_data": drop_row})
    with pytest.raises(HSCValidationError,
                       match="omits or misdescribes"):
        fixture.validate()

    def wrong_hash(data):
        import json
        value = json.loads(data)
        value["outputs"][0]["blob_sha256"] = "9" * 64
        return canonical_json(value).encode("utf-8")
    fixture = RootFixture().build(tweaks={"assessor_inventory_data": wrong_hash})
    with pytest.raises(HSCValidationError,
                       match="omits or misdescribes"):
        fixture.validate()

    def extra_row(data):
        import json
        value = json.loads(data)
        value["outputs"] = sorted(
            value["outputs"] + [{
                "leaf_relpath": "zzz-fabricated.json",
                "artifact_type": "check_evidence",
                "media_type": "application/json",
                "byte_length": 2,
                "blob_sha256": "8" * 64,
            }], key=lambda row: row["leaf_relpath"])
        return canonical_json(value).encode("utf-8")
    fixture = RootFixture().build(tweaks={"assessor_inventory_data": extra_row})
    with pytest.raises(HSCValidationError,
                       match="does not own"):
        fixture.validate()


# --- finding 11: required evidence ids must be satisfied exactly once -------

def test_contract_required_evidence_ids_must_be_satisfied():
    fixture = RootFixture().build(tweaks={
        "contract": lambda p: p.update(required_evidence_ids=["ghost-1"])})
    with pytest.raises(HSCValidationError,
                       match="evidence identity is not satisfied"):
        fixture.validate()

    def duplicate_coverage(payload):
        payload["required_invariant_ids"] = ["check-1"]
        payload["required_evidence_ids"] = ["check-1"]

    def rename_invariant(payload):
        payload["invariant_results"] = [
            dict(payload["invariant_results"][0], check_id="check-1")]
    fixture = RootFixture().build(tweaks={"contract": duplicate_coverage,
                                          "bundle": rename_invariant})
    with pytest.raises(HSCValidationError,
                       match="evidence identity is not satisfied"):
        fixture.validate()


# --- finding 12: only a chain-verified canonical BUILD_STARTED is authority --

def test_fabricated_build_started_mappings_are_refused(complete_fixture):
    fixture = complete_fixture
    legacy_shape = {key: fixture.event[key] for key in (
        "event_id", "event_type", "request_id", "repository",
        "target_commit", "payload")}
    legacy_shape["event_hash"] = "e" * 64
    with pytest.raises(HSCValidationError, match="canonical Council event"):
        fixture.validate(event=legacy_shape)

    arbitrary_hash = copy.deepcopy(fixture.event)
    arbitrary_hash["event_hash"] = "e" * 64
    with pytest.raises(HSCValidationError, match="canonical Council event"):
        fixture.validate(event=arbitrary_hash)

    wrong_sender = copy.deepcopy(fixture.event)
    wrong_sender["sender"] = "codex"
    wrong_sender["event_hash"] = compute_event_hash(wrong_sender)
    with pytest.raises(HSCValidationError, match="canonical Council event"):
        fixture.validate(event=wrong_sender)

    unchained = copy.deepcopy(fixture.event)
    unchained["timestamp_utc"] = "2026-07-16T00:00:01Z"
    unchained["event_hash"] = compute_event_hash(unchained)
    with pytest.raises(HSCValidationError, match="not a member"):
        fixture.validate(event=unchained)

    broken_link = copy.deepcopy(fixture.event)
    broken_link["previous_event_hash"] = "a" * 64
    broken_link["event_hash"] = compute_event_hash(broken_link)
    with pytest.raises(HSCValidationError, match="link from genesis"):
        fixture.validate(event=broken_link, chain=[broken_link])

    with pytest.raises(HSCValidationError, match="chain is required"):
        fixture.validate(chain=[])
