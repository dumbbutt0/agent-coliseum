"""Exact HSC v1 record schemas and self-identity validation.

Reference resolution and whole-root relations live in :mod:`store`; this
module refuses malformed records before any relationship is trusted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from tools.council.schemas import canonical_json, domain_hash

from .core import (
    HSCValidationError,
    canonical_sort_key,
    change_sort_key,
    compute_record_content_sha256,
    exact_keys,
    fail,
    file_id,
    filesystem_id,
    locator_sha256,
    require_bool,
    require_event,
    require_g,
    require_h,
    require_int,
    require_literal,
    require_ordered,
    require_request_id,
    require_slug,
    require_sorted_unique,
    require_string,
    require_unique_paths,
    validate_change_set,
    validate_native_entry,
    validate_native_locator,
    validate_native_observation,
    validate_native_rel_path,
    validate_path,
    validate_ref,
)


@dataclass(frozen=True)
class RefRequirement:
    ref: Mapping[str, str]
    where: str
    expected_versions: tuple[str, ...] = ()
    artifact_types: tuple[str, ...] = ()
    external: bool = False


@dataclass(frozen=True)
class RecordType:
    id_field: str
    domain: str
    validator: Callable[[Mapping[str, Any]], list[RefRequirement]]


def _ref(value: Any, where: str, versions: Iterable[str] = (),
         artifacts: Iterable[str] = (), *, nullable: bool = False,
         external: bool = False) -> RefRequirement | None:
    parsed = validate_ref(value, where, nullable=nullable)
    if parsed is None:
        return None
    return RefRequirement(parsed, where, tuple(versions), tuple(artifacts),
                          external)


def _refs(values: Any, where: str, versions: Iterable[str] = (),
          artifacts: Iterable[str] = (), *, nonempty: bool = False,
          external: bool = False) -> list[RefRequirement]:
    require_sorted_unique(values, where, nonempty=nonempty)
    result = []
    for index, value in enumerate(values):
        result.append(_ref(value, f"{where}[{index}]", versions, artifacts,
                           external=external))
    return result


def _strings(values: Any, where: str, *, slug: bool = False,
             nonempty: bool = False) -> None:
    require_sorted_unique(values, where, nonempty=nonempty)
    for index, value in enumerate(values):
        (require_slug if slug else require_string)(value, f"{where}[{index}]")


def _budget(value: Any, where: str) -> None:
    exact_keys(value, {"max_wall_seconds", "max_cpu_seconds",
                       "max_output_bytes", "max_attempts"}, where)
    for key in value:
        require_int(value[key], f"{where}.{key}")
    if value["max_attempts"] < 1:
        fail(f"{where}.max_attempts must be positive")


def _interface(value: Any, where: str) -> None:
    exact_keys(value, {"interface_id", "version", "digest"}, where)
    require_slug(value["interface_id"], f"{where}.interface_id")
    require_int(value["version"], f"{where}.version", minimum=1)
    require_h(value["digest"], f"{where}.digest")


def _interfaces(values: Any, where: str) -> None:
    require_sorted_unique(values, where,
                          key=lambda item: item.get("interface_id", ""))
    for index, value in enumerate(values):
        _interface(value, f"{where}[{index}]")


def _file_ref(value: Any, where: str) -> None:
    exact_keys(value, {"path", "blob_sha256", "git_mode", "kind"}, where)
    validate_path(value["path"], f"{where}.path")
    require_h(value["blob_sha256"], f"{where}.blob_sha256")
    require_literal(value["git_mode"], ("100644", "100755"),
                    f"{where}.git_mode")
    require_literal(value["kind"], ("file",), f"{where}.kind")


def _file_refs(values: Any, where: str) -> None:
    require_sorted_unique(values, where, key=lambda item: item.get("path", ""))
    for index, value in enumerate(values):
        _file_ref(value, f"{where}[{index}]")
    require_unique_paths([item["path"] for item in values], where)


def _check_result(value: Any, where: str) -> RefRequirement:
    exact_keys(value, {"check_id", "status", "evidence_ref"}, where)
    require_slug(value["check_id"], f"{where}.check_id")
    require_literal(value["status"], ("pass", "fail", "error"),
                    f"{where}.status")
    return _ref(value["evidence_ref"], f"{where}.evidence_ref",
                ("section_content_record.v1",), ("check_evidence",))


def _check_results(values: Any, where: str, *, nonempty: bool = False) \
        -> list[RefRequirement]:
    require_sorted_unique(values, where, key=lambda item: item.get("check_id", ""),
                          nonempty=nonempty)
    return [_check_result(value, f"{where}[{index}]")
            for index, value in enumerate(values)]


def _metric(value: Any, where: str) -> RefRequirement | None:
    exact_keys(value, {"metric_id", "availability", "unit", "value",
                       "evidence_ref"}, where)
    require_slug(value["metric_id"], f"{where}.metric_id")
    availability = require_literal(value["availability"],
                                   ("measured", "estimated", "unavailable"),
                                   f"{where}.availability")
    require_slug(value["unit"], f"{where}.unit")
    if availability == "unavailable":
        if value["value"] is not None or value["evidence_ref"] is not None:
            fail(f"{where} unavailable metric must use null value/evidence")
        return None
    require_int(value["value"], f"{where}.value")
    return _ref(value["evidence_ref"], f"{where}.evidence_ref",
                ("section_content_record.v1",))


def _metrics(values: Any, where: str) -> list[RefRequirement]:
    require_sorted_unique(values, where, key=lambda item: item.get("metric_id", ""))
    return [ref for index, value in enumerate(values)
            if (ref := _metric(value, f"{where}[{index}]")) is not None]


def _program_ref(payload: Mapping[str, Any]) -> RefRequirement:
    return _ref(payload["program_ref"], "payload.program_ref",
                ("section_program.v1",))


ROOT_KINDS = (
    "candidate", "integration-checkout", "common-git", "council-root",
    "owner-anchors", "other-worker-leaves", "canonical-evidence",
    "hidden-suites", "runtime-readonly", "builder-output", "assessor-output",
)


def _native_root_spec(value: Any, where: str, program_ref: Mapping[str, str]) \
        -> None:
    keys = {"root_id", "root_kind", "view_kind", "namespace_id", "locator",
            "locator_sha256", "native_identity", "filesystem_id", "file_id",
            "workspace_id", "delegated_control_root_id",
            "delegated_control_identity"}
    exact_keys(value, keys, where)
    require_h(value["root_id"], f"{where}.root_id")
    kind = require_literal(value["root_kind"], ROOT_KINDS, f"{where}.root_kind")
    view = require_literal(value["view_kind"],
                           ("full-native-tree-v1",
                            "checkout-excluding-delegated-dotgit-v1"),
                           f"{where}.view_kind")
    require_h(value["namespace_id"], f"{where}.namespace_id")
    validate_native_locator(value["locator"], f"{where}.locator")
    require_h(value["locator_sha256"], f"{where}.locator_sha256")
    validate_native_observation(value["native_identity"],
                                f"{where}.native_identity")
    if value["native_identity"]["file_type"] != "directory":
        fail(f"{where} native root must be a directory")
    require_h(value["filesystem_id"], f"{where}.filesystem_id")
    require_h(value["file_id"], f"{where}.file_id")
    if value["workspace_id"] is not None:
        require_h(value["workspace_id"], f"{where}.workspace_id")
    if view == "full-native-tree-v1":
        if value["delegated_control_root_id"] is not None or \
                value["delegated_control_identity"] is not None:
            fail(f"{where} full tree cannot delegate a control root")
    else:
        if kind != "integration-checkout":
            fail(f"{where} delegated .git view is checkout-only")
        require_h(value["delegated_control_root_id"],
                  f"{where}.delegated_control_root_id")
        validate_native_observation(value["delegated_control_identity"],
                                    f"{where}.delegated_control_identity")
    want_locator = locator_sha256(value["locator"])
    want_fs = filesystem_id(value["native_identity"])
    want_file = file_id(value["native_identity"])
    if (value["locator_sha256"], value["filesystem_id"], value["file_id"]) != \
            (want_locator, want_fs, want_file):
        fail(f"{where} locator/native ids do not reconstruct")
    want_namespace = domain_hash("council:native-namespace:v1", {
        "locator_sha256": want_locator,
        "program_ref": program_ref,
        "root_kind": kind,
        "view_kind": view,
        "workspace_id": value["workspace_id"],
    })
    if value["namespace_id"] != want_namespace:
        fail(f"{where}.namespace_id does not reconstruct")
    without_id = dict(value)
    without_id.pop("root_id")
    want_root = domain_hash("council:native-root:v1", {
        "program_ref": program_ref, "root_spec": without_id})
    if value["root_id"] != want_root:
        fail(f"{where}.root_id does not reconstruct")


def _observation_requirement(value: Any, where: str,
                             program_ref: Mapping[str, str]) -> None:
    keys = {"observation_id", "root_id", "phase", "scope", "work_item_id",
            "role", "attempt", "workspace_id"}
    exact_keys(value, keys, where)
    require_h(value["observation_id"], f"{where}.observation_id")
    require_h(value["root_id"], f"{where}.root_id")
    require_literal(value["phase"], ("pre-dispatch", "post-worker",
                                     "pre-assembly", "post-assembly"),
                    f"{where}.phase")
    scope = require_literal(value["scope"], ("builder-dispatch",
                                              "assessor-dispatch", "assembly"),
                            f"{where}.scope")
    if scope == "assembly":
        if any(value[field] is not None for field in
               ("work_item_id", "role", "attempt", "workspace_id")):
            fail(f"{where} assembly context fields must be null")
        if value["phase"] not in ("pre-assembly", "post-assembly"):
            fail(f"{where} assembly phase mismatch")
    else:
        require_h(value["work_item_id"], f"{where}.work_item_id")
        expected_role = scope.removesuffix("-dispatch")
        if value["role"] != expected_role:
            fail(f"{where} dispatch role mismatch")
        require_int(value["attempt"], f"{where}.attempt")
        require_h(value["workspace_id"], f"{where}.workspace_id")
        if value["phase"] not in ("pre-dispatch", "post-worker"):
            fail(f"{where} dispatch phase mismatch")
    preimage = dict(value)
    preimage.pop("observation_id")
    preimage["program_ref"] = program_ref
    if value["observation_id"] != domain_hash(
            "council:native-observation-requirement:v1", preimage):
        fail(f"{where}.observation_id does not reconstruct")


def _validate_self_record(record: Mapping[str, Any], schema: str,
                          spec: RecordType) -> None:
    exact_keys(record, {"schema_version", spec.id_field, "payload"}, "record")
    if record["schema_version"] != schema:
        fail("record schema_version changed during dispatch")
    require_h(record[spec.id_field], f"record.{spec.id_field}")
    if not isinstance(record["payload"], dict):
        fail("record.payload must be an object")
    expected = domain_hash(spec.domain, {"schema_version": schema,
                                         "payload": record["payload"]})
    if record[spec.id_field] != expected:
        fail(f"{schema} self id mismatch")


def validate_record(record: Any) -> list[RefRequirement]:
    if not isinstance(record, dict):
        fail("record must be an object")
    schema = record.get("schema_version")
    if not isinstance(schema, str) or schema not in RECORD_TYPES:
        fail(f"unknown schema_version {schema!r}")
    spec = RECORD_TYPES[schema]
    _validate_self_record(record, schema, spec)
    return spec.validator(record["payload"])


def make_record(schema_version: str, payload: Mapping[str, Any]) -> dict:
    if schema_version not in RECORD_TYPES:
        fail(f"unknown schema_version {schema_version!r}")
    spec = RECORD_TYPES[schema_version]
    record = {"schema_version": schema_version, "payload": dict(payload)}
    record[spec.id_field] = domain_hash(
        spec.domain, {"schema_version": schema_version,
                      "payload": record["payload"]})
    # Exact top-level key order is canonicalized by canonical_json; insertion
    # order is not an identity input.
    validate_record(record)
    return record


def _bootstrap_content(p: Mapping[str, Any]) -> list[RefRequirement]:
    exact_keys(p, {"planned_request_id", "artifact_type", "storage_relpath",
                   "media_type", "byte_length", "blob_sha256"}, "payload")
    rid = require_request_id(p["planned_request_id"],
                             "payload.planned_request_id")
    require_literal(p["artifact_type"], ("schema_profile", "read_inventory"),
                    "payload.artifact_type")
    path = validate_path(p["storage_relpath"], "payload.storage_relpath")
    if not path.startswith(f"artifacts/section-council/{rid}/bootstrap/"):
        fail("bootstrap storage path is outside its fixed request directory")
    require_literal(p["media_type"], ("application/json",),
                    "payload.media_type")
    require_int(p["byte_length"], "payload.byte_length")
    require_h(p["blob_sha256"], "payload.blob_sha256")
    return []


def _principal_registry(p: Mapping[str, Any]) -> list[RefRequirement]:
    keys = {"planned_request_id", "repository", "base_commit",
            "enrollment_registry_path", "enrollment_registry_git_blob",
            "enrollment_registry_version", "enrollment_registry_digest",
            "scheduler_authority_id", "scheduler_writer_principal_id",
            "scheduler_writer_control_id", "launcher_writer_principal_id",
            "launcher_writer_control_id", "principals"}
    exact_keys(p, keys, "payload")
    require_request_id(p["planned_request_id"], "payload.planned_request_id")
    require_string(p["repository"], "payload.repository")
    require_g(p["base_commit"], "payload.base_commit")
    validate_path(p["enrollment_registry_path"],
                  "payload.enrollment_registry_path")
    require_g(p["enrollment_registry_git_blob"],
              "payload.enrollment_registry_git_blob")
    require_int(p["enrollment_registry_version"],
                "payload.enrollment_registry_version", minimum=1)
    for field in ("enrollment_registry_digest", "scheduler_authority_id",
                  "scheduler_writer_control_id", "launcher_writer_control_id"):
        require_h(p[field], f"payload.{field}")
    require_slug(p["scheduler_writer_principal_id"],
                 "payload.scheduler_writer_principal_id")
    require_slug(p["launcher_writer_principal_id"],
                 "payload.launcher_writer_principal_id")
    if p["scheduler_writer_principal_id"] == p["launcher_writer_principal_id"] \
            or p["scheduler_writer_control_id"] == p["launcher_writer_control_id"]:
        fail("scheduler and launcher writer authorities must be distinct")
    principals = p["principals"]
    require_sorted_unique(principals, "payload.principals",
                          key=lambda row: row.get("principal_id", ""),
                          nonempty=True)
    unique_fields = {name: set() for name in (
        "principal_id", "authority_control_id", "authority_control_key_digest",
        "principal_credential_digest")}
    for index, row in enumerate(principals):
        where = f"payload.principals[{index}]"
        exact_keys(row, {"principal_id", "allowed_role", "authority_control_id",
                         "authority_control_key_digest",
                         "principal_credential_digest", "launcher_profile_id",
                         "enrollment_evidence_sha256"}, where)
        require_slug(row["principal_id"], f"{where}.principal_id")
        require_literal(row["allowed_role"], ("builder", "assessor"),
                        f"{where}.allowed_role")
        for field in ("authority_control_id", "authority_control_key_digest",
                      "principal_credential_digest", "enrollment_evidence_sha256"):
            require_h(row[field], f"{where}.{field}")
        require_slug(row["launcher_profile_id"], f"{where}.launcher_profile_id")
        for field, seen in unique_fields.items():
            if row[field] in seen:
                fail(f"payload.principals duplicates {field}")
            seen.add(row[field])
    worker_principals = unique_fields["principal_id"]
    worker_controls = unique_fields["authority_control_id"]
    if {p["scheduler_writer_principal_id"], p["launcher_writer_principal_id"]} \
            & worker_principals or \
            {p["scheduler_writer_control_id"], p["launcher_writer_control_id"]} \
            & worker_controls:
        fail("protected writers must be distinct from worker principals")
    return []


def _program(p: Mapping[str, Any]) -> list[RefRequirement]:
    keys = {"planned_request_id", "repository", "base_commit", "execution_mode",
            "section_declarations", "schema_profile_refs",
            "principal_registry_ref", "system_artifact_predictions",
            "root_policy_version"}
    exact_keys(p, keys, "payload")
    require_request_id(p["planned_request_id"], "payload.planned_request_id")
    require_string(p["repository"], "payload.repository")
    require_g(p["base_commit"], "payload.base_commit")
    require_literal(p["execution_mode"], ("sequential", "hierarchical"),
                    "payload.execution_mode")
    declarations = p["section_declarations"]
    require_sorted_unique(declarations, "payload.section_declarations",
                          key=lambda row: row.get("section_id", ""), nonempty=True)
    refs: list[RefRequirement] = []
    all_paths: list[str] = []
    section_ids: list[str] = []
    dependency_map: dict[str, list[str]] = {}
    for index, row in enumerate(declarations):
        where = f"payload.section_declarations[{index}]"
        exact_keys(row, {"section_id", "predicted_changes",
                         "read_inventory_refs", "dependency_section_ids",
                         "budget", "assessment_profile_id"}, where)
        sid = require_slug(row["section_id"], f"{where}.section_id")
        section_ids.append(sid)
        validate_change_set(row["predicted_changes"],
                            f"{where}.predicted_changes", predicted=True,
                            nonempty=True)
        all_paths.extend(change["path"] for change in row["predicted_changes"])
        all_paths.extend(change["rename_source"] for change in row["predicted_changes"]
                         if change["rename_source"] is not None)
        refs.extend(_refs(row["read_inventory_refs"],
                          f"{where}.read_inventory_refs",
                          ("section_bootstrap_content.v1",), ("read_inventory",)))
        _strings(row["dependency_section_ids"],
                 f"{where}.dependency_section_ids", slug=True)
        dependency_map[sid] = row["dependency_section_ids"]
        _budget(row["budget"], f"{where}.budget")
        require_slug(row["assessment_profile_id"],
                     f"{where}.assessment_profile_id")
    require_unique_paths(all_paths, "payload.section_declarations")
    known = set(section_ids)
    for sid, deps in dependency_map.items():
        if sid in deps or not set(deps) <= known:
            fail("section dependency references self or unknown section")
    _reject_cycles(dependency_map, "section dependency graph")
    refs.extend(_refs(p["schema_profile_refs"], "payload.schema_profile_refs",
                      ("section_bootstrap_content.v1",), ("schema_profile",),
                      nonempty=True))
    refs.append(_ref(p["principal_registry_ref"],
                     "payload.principal_registry_ref",
                     ("section_principal_registry.v1",)))
    validate_change_set(p["system_artifact_predictions"],
                        "payload.system_artifact_predictions", predicted=True,
                        nonempty=True)
    if any(change["kind"] != "add" for change in
           p["system_artifact_predictions"]):
        fail("system artifact predictions must be exact adds")
    require_int(p["root_policy_version"], "payload.root_policy_version",
                minimum=1)
    return refs


def _reject_cycles(graph: Mapping[str, Iterable[str]], where: str) -> None:
    state: dict[str, int] = {}
    def visit(node: str) -> None:
        if state.get(node) == 1:
            fail(f"{where} contains a cycle")
        if state.get(node) == 2:
            return
        state[node] = 1
        for dep in graph.get(node, ()):
            visit(dep)
        state[node] = 2
    for node in graph:
        visit(node)


def _contract(p: Mapping[str, Any]) -> list[RefRequirement]:
    keys = {"program_ref", "planned_request_id", "parent_build_event_id",
            "parent_build_event_hash", "base_commit", "section_id",
            "contract_version", "objective", "predicted_changes",
            "read_inventory_refs", "forbidden_host_roots", "allowed_operations",
            "forbidden_operations", "upstream_contract_refs",
            "consumed_interfaces", "exported_interfaces",
            "required_invariant_ids", "required_check_ids",
            "required_evidence_ids", "threat_ids", "assessment_profile_ref",
            "budget", "executor_profile_ids", "escalation_rule_ids",
            "completion_condition_ids", "integration_precondition_ids"}
    exact_keys(p, keys, "payload")
    refs = [_program_ref(p)]
    require_request_id(p["planned_request_id"], "payload.planned_request_id")
    require_event(p["parent_build_event_id"], "payload.parent_build_event_id")
    require_h(p["parent_build_event_hash"], "payload.parent_build_event_hash")
    require_g(p["base_commit"], "payload.base_commit")
    require_slug(p["section_id"], "payload.section_id")
    require_int(p["contract_version"], "payload.contract_version", minimum=1)
    require_string(p["objective"], "payload.objective")
    validate_change_set(p["predicted_changes"], "payload.predicted_changes",
                        predicted=True, nonempty=True)
    refs.extend(_refs(p["read_inventory_refs"], "payload.read_inventory_refs",
                      ("section_bootstrap_content.v1",), ("read_inventory",)))
    _strings(p["forbidden_host_roots"], "payload.forbidden_host_roots",
             nonempty=True)
    _enum_subset(p["allowed_operations"], "payload.allowed_operations",
                 ("analyze", "emit_patch", "emit_report", "run_allowlisted_check"),
                 nonempty=True)
    _enum_subset(p["forbidden_operations"], "payload.forbidden_operations",
                 ("council_write", "git_write", "integration_write", "network",
                  "process_escape", "unregistered_output"), nonempty=True)
    refs.extend(_refs(p["upstream_contract_refs"],
                      "payload.upstream_contract_refs", ("section_contract.v1",)))
    _interfaces(p["consumed_interfaces"], "payload.consumed_interfaces")
    _interfaces(p["exported_interfaces"], "payload.exported_interfaces")
    for field in ("required_invariant_ids", "required_check_ids",
                  "required_evidence_ids", "threat_ids", "executor_profile_ids",
                  "escalation_rule_ids", "completion_condition_ids",
                  "integration_precondition_ids"):
        _strings(p[field], f"payload.{field}", slug=True, nonempty=True)
    refs.append(_ref(p["assessment_profile_ref"],
                     "payload.assessment_profile_ref",
                     ("section_content_record.v1",), ("assessment_profile",)))
    _budget(p["budget"], "payload.budget")
    return refs


def _enum_subset(values: Any, where: str, allowed: Iterable[str], *,
                 nonempty: bool = False) -> None:
    require_sorted_unique(values, where, nonempty=nonempty)
    for index, value in enumerate(values):
        require_literal(value, allowed, f"{where}[{index}]")


def _work_graph(p: Mapping[str, Any]) -> list[RefRequirement]:
    exact_keys(p, {"program_ref", "contract_refs", "work_items"}, "payload")
    refs = [_program_ref(p)]
    refs.extend(_refs(p["contract_refs"], "payload.contract_refs",
                      ("section_contract.v1",), nonempty=True))
    items = p["work_items"]
    require_sorted_unique(items, "payload.work_items",
                          key=lambda row: row.get("work_item_id", ""),
                          nonempty=True)
    ids: list[str] = []
    dependency_map: dict[str, list[str]] = {}
    for index, item in enumerate(items):
        where = f"payload.work_items[{index}]"
        exact_keys(item, {"work_item_id", "section_contract_ref", "operation",
                          "dependency_work_item_ids", "read_inventory_refs",
                          "predicted_changes", "shared_interfaces",
                          "required_audit_levels", "priority", "budget"}, where)
        require_h(item["work_item_id"], f"{where}.work_item_id")
        refs.append(_ref(item["section_contract_ref"],
                         f"{where}.section_contract_ref",
                         ("section_contract.v1",)))
        require_literal(item["operation"],
                        ("analyze", "emit_patch", "emit_report",
                         "run_allowlisted_check"), f"{where}.operation")
        _strings(item["dependency_work_item_ids"],
                 f"{where}.dependency_work_item_ids")
        for dep in item["dependency_work_item_ids"]:
            require_h(dep, f"{where}.dependency_work_item_ids")
        refs.extend(_refs(item["read_inventory_refs"],
                          f"{where}.read_inventory_refs",
                          ("section_bootstrap_content.v1",
                           "section_content_record.v1"), ("read_inventory",)))
        validate_change_set(item["predicted_changes"],
                            f"{where}.predicted_changes", predicted=True)
        _interfaces(item["shared_interfaces"], f"{where}.shared_interfaces")
        _enum_subset(item["required_audit_levels"],
                     f"{where}.required_audit_levels",
                     ("section", "boundary", "system"), nonempty=True)
        require_int(item["priority"], f"{where}.priority")
        _budget(item["budget"], f"{where}.budget")
        without_id = dict(item)
        without_id.pop("work_item_id")
        without_id["program_ref"] = p["program_ref"]
        expected = domain_hash("council:section-work-item:v1", without_id)
        if item["work_item_id"] != expected:
            fail(f"{where}.work_item_id does not reconstruct")
        ids.append(item["work_item_id"])
        dependency_map[item["work_item_id"]] = item["dependency_work_item_ids"]
    known = set(ids)
    for item_id, deps in dependency_map.items():
        if item_id in deps or not set(deps) <= known:
            fail("work graph dependency references self or unknown item")
    _reject_cycles(dependency_map, "work graph")
    return refs


def _context_bundle(p: Mapping[str, Any]) -> list[RefRequirement]:
    keys = {"program_ref", "contract_ref", "work_item_id", "base_commit",
            "role", "source_files", "interface_refs", "policy_files",
            "test_files", "prior_finding_refs", "proposal_ref",
            "deterministic_result_refs", "omitted_category_ids"}
    exact_keys(p, keys, "payload")
    refs = [_program_ref(p), _ref(p["contract_ref"], "payload.contract_ref",
                                  ("section_contract.v1",))]
    require_h(p["work_item_id"], "payload.work_item_id")
    require_g(p["base_commit"], "payload.base_commit")
    role = require_literal(p["role"], ("builder", "assessor"), "payload.role")
    for field in ("source_files", "policy_files", "test_files"):
        _file_refs(p[field], f"payload.{field}")
    _interfaces(p["interface_refs"], "payload.interface_refs")
    refs.extend(_refs(p["prior_finding_refs"], "payload.prior_finding_refs",
                      ("section_finding.v1",)))
    proposal = _ref(p["proposal_ref"], "payload.proposal_ref",
                    ("section_content_record.v1",), ("proposal",), nullable=True)
    if proposal:
        refs.append(proposal)
    if role == "assessor" and proposal is None:
        fail("assessor context requires a proposal")
    if role == "builder" and proposal is not None:
        fail("builder context cannot include a proposal")
    refs.extend(_refs(p["deterministic_result_refs"],
                      "payload.deterministic_result_refs",
                      ("section_content_record.v1",),
                      ("test_result", "check_evidence")))
    _strings(p["omitted_category_ids"], "payload.omitted_category_ids", slug=True)
    return refs


CONTENT_ARTIFACTS = (
    "read_inventory", "assessment_profile", "assessment_declaration",
    "check_declaration", "finding_declaration", "source_snapshot", "proposal",
    "diff_preview", "test_manifest", "test_result", "check_evidence",
    "finding_evidence", "reproduction", "resolution", "operation_log",
    "conflict_evidence", "assembler_binary", "scheduler_failure_evidence",
)


def _content_record(p: Mapping[str, Any]) -> list[RefRequirement]:
    exact_keys(p, {"program_ref", "artifact_type", "storage_relpath",
                   "media_type", "byte_length", "blob_sha256",
                   "producer_assignment_ref", "parent_content_refs"}, "payload")
    refs = [_program_ref(p)]
    require_literal(p["artifact_type"], CONTENT_ARTIFACTS,
                    "payload.artifact_type")
    path = validate_path(p["storage_relpath"], "payload.storage_relpath")
    if not path.startswith("artifacts/section-council/") or "/content/" not in path:
        fail("content storage path is outside the fixed content namespace")
    require_literal(p["media_type"],
                    ("application/json", "text/plain", "text/x-diff",
                     "application/octet-stream"), "payload.media_type")
    require_int(p["byte_length"], "payload.byte_length")
    require_h(p["blob_sha256"], "payload.blob_sha256")
    producer = _ref(p["producer_assignment_ref"],
                    "payload.producer_assignment_ref",
                    ("section_assignment.v1",), nullable=True)
    if producer:
        refs.append(producer)
    refs.extend(_refs(p["parent_content_refs"], "payload.parent_content_refs",
                      ("section_content_record.v1",)))
    return refs


def _authorization(p: Mapping[str, Any]) -> list[RefRequirement]:
    keys = {"program_ref", "principal_registry_ref", "scheduler_authority_id",
            "scheduler_journal_sequence", "scheduler_journal_entry_sha256",
            "contract_ref", "work_item_id", "role", "principal_id",
            "authority_control_id", "principal_credential_digest",
            "launcher_executable_sha256", "session_nonce", "attempt",
            "context_ref", "sandbox_profile_ref", "workspace_id", "output_leaf"}
    exact_keys(p, keys, "payload")
    refs = [_program_ref(p),
            _ref(p["principal_registry_ref"], "payload.principal_registry_ref",
                 ("section_principal_registry.v1",)),
            _ref(p["contract_ref"], "payload.contract_ref",
                 ("section_contract.v1",)),
            _ref(p["context_ref"], "payload.context_ref",
                 ("section_context_bundle.v1",)),
            _ref(p["sandbox_profile_ref"], "payload.sandbox_profile_ref",
                 ("worker_sandbox_profile.v1",))]
    _dispatch_common(p)
    expected = _entry_hash("council:section-launch-authorization-entry:v1", p)
    if p["scheduler_journal_entry_sha256"] != expected:
        fail("authorization journal entry hash mismatch")
    return refs


def _assignment(p: Mapping[str, Any]) -> list[RefRequirement]:
    keys = {"program_ref", "contract_ref", "work_item_id", "role",
            "principal_registry_ref", "principal_id", "authority_control_id",
            "principal_credential_digest", "scheduler_authority_id",
            "scheduler_journal_sequence", "scheduler_journal_entry_sha256",
            "launcher_authorization_ref", "session_nonce", "attempt",
            "context_ref", "sandbox_profile_ref", "workspace_id", "output_leaf"}
    exact_keys(p, keys, "payload")
    refs = [_program_ref(p),
            _ref(p["contract_ref"], "payload.contract_ref",
                 ("section_contract.v1",)),
            _ref(p["principal_registry_ref"], "payload.principal_registry_ref",
                 ("section_principal_registry.v1",)),
            _ref(p["launcher_authorization_ref"],
                 "payload.launcher_authorization_ref",
                 ("section_launcher_authorization.v1",)),
            _ref(p["context_ref"], "payload.context_ref",
                 ("section_context_bundle.v1",)),
            _ref(p["sandbox_profile_ref"], "payload.sandbox_profile_ref",
                 ("worker_sandbox_profile.v1",))]
    _dispatch_common(p, launcher=False)
    expected = _entry_hash("council:section-assignment-entry:v1", p)
    if p["scheduler_journal_entry_sha256"] != expected:
        fail("assignment journal entry hash mismatch")
    return refs


def _receipt(p: Mapping[str, Any]) -> list[RefRequirement]:
    keys = {"program_ref", "authorization_ref", "assignment_ref",
            "scheduler_authority_id", "scheduler_journal_sequence",
            "scheduler_journal_entry_sha256", "role", "principal_id",
            "authority_control_id", "principal_credential_digest",
            "launcher_executable_sha256", "session_nonce", "attempt",
            "context_ref", "sandbox_profile_ref", "workspace_id", "output_leaf",
            "barrier_status"}
    exact_keys(p, keys, "payload")
    refs = [_program_ref(p),
            _ref(p["authorization_ref"], "payload.authorization_ref",
                 ("section_launcher_authorization.v1",)),
            _ref(p["assignment_ref"], "payload.assignment_ref",
                 ("section_assignment.v1",)),
            _ref(p["context_ref"], "payload.context_ref",
                 ("section_context_bundle.v1",)),
            _ref(p["sandbox_profile_ref"], "payload.sandbox_profile_ref",
                 ("worker_sandbox_profile.v1",))]
    _dispatch_common(p, contract=False, registry=False)
    require_literal(p["barrier_status"], ("ready", "refused"),
                    "payload.barrier_status")
    expected = _entry_hash("council:section-launch-receipt-entry:v1", p)
    if p["scheduler_journal_entry_sha256"] != expected:
        fail("receipt journal entry hash mismatch")
    return refs


def _dispatch_common(p: Mapping[str, Any], *, launcher: bool = True,
                     contract: bool = True, registry: bool = True) -> None:
    for field in ("scheduler_authority_id", "authority_control_id",
                  "principal_credential_digest", "session_nonce", "workspace_id"):
        require_h(p[field], f"payload.{field}")
    if launcher:
        require_h(p["launcher_executable_sha256"],
                  "payload.launcher_executable_sha256")
    require_int(p["scheduler_journal_sequence"],
                "payload.scheduler_journal_sequence")
    require_h(p["scheduler_journal_entry_sha256"],
              "payload.scheduler_journal_entry_sha256")
    if contract:
        require_h(p["work_item_id"], "payload.work_item_id")
    require_literal(p["role"], ("builder", "assessor"), "payload.role")
    require_slug(p["principal_id"], "payload.principal_id")
    require_int(p["attempt"], "payload.attempt")
    require_slug(p["output_leaf"], "payload.output_leaf")
    del registry


def _entry_hash(domain: str, p: Mapping[str, Any]) -> str:
    preimage = dict(p)
    preimage.pop("scheduler_journal_entry_sha256")
    return domain_hash(domain, preimage)


def _journal_manifest(p: Mapping[str, Any]) -> list[RefRequirement]:
    keys = {"program_ref", "principal_registry_ref", "scheduler_authority_id",
            "journal_root_id", "journal_root_locator",
            "journal_root_locator_sha256", "journal_root_native_identity",
            "journal_root_filesystem_id", "journal_root_file_id",
            "journal_owner_principal_id", "journal_owner_control_id",
            "journal_mode", "predecessor_journal_manifest_ref",
            "first_sequence", "last_sequence", "entries"}
    exact_keys(p, keys, "payload")
    refs = [_program_ref(p),
            _ref(p["principal_registry_ref"], "payload.principal_registry_ref",
                 ("section_principal_registry.v1",))]
    for field in ("scheduler_authority_id", "journal_root_id",
                  "journal_root_locator_sha256", "journal_root_filesystem_id",
                  "journal_root_file_id", "journal_owner_control_id"):
        require_h(p[field], f"payload.{field}")
    validate_native_locator(p["journal_root_locator"],
                            "payload.journal_root_locator")
    validate_native_observation(p["journal_root_native_identity"],
                                "payload.journal_root_native_identity")
    require_slug(p["journal_owner_principal_id"],
                 "payload.journal_owner_principal_id")
    require_literal(p["journal_mode"], ("0700",), "payload.journal_mode")
    observation = p["journal_root_native_identity"]
    if observation["file_type"] != "directory" or \
            observation["native_mode"] & 4095 != 448:
        fail("journal native observation does not encode a 0700 directory")
    expected_locator = locator_sha256(p["journal_root_locator"])
    expected_fs = filesystem_id(observation)
    expected_file = file_id(observation)
    if (p["journal_root_locator_sha256"], p["journal_root_filesystem_id"],
        p["journal_root_file_id"]) != (expected_locator, expected_fs,
                                       expected_file):
        fail("journal root native identities do not reconstruct")
    expected_root = domain_hash("council:scheduler-journal-root:v1", {
        "journal_mode": "0700",
        "journal_owner_control_id": p["journal_owner_control_id"],
        "journal_owner_principal_id": p["journal_owner_principal_id"],
        "journal_root_file_id": p["journal_root_file_id"],
        "journal_root_filesystem_id": p["journal_root_filesystem_id"],
        "journal_root_locator_sha256": p["journal_root_locator_sha256"],
        "principal_registry_ref": p["principal_registry_ref"],
        "program_ref": p["program_ref"],
    })
    if p["journal_root_id"] != expected_root:
        fail("journal_root_id does not reconstruct")
    predecessor = _ref(p["predecessor_journal_manifest_ref"],
                       "payload.predecessor_journal_manifest_ref",
                       ("section_scheduler_journal_manifest.v1",), nullable=True)
    if predecessor:
        refs.append(predecessor)
    first = require_int(p["first_sequence"], "payload.first_sequence")
    last = require_int(p["last_sequence"], "payload.last_sequence")
    if last != first + 2 or predecessor is None and first != 0:
        fail("journal sequence range is not a contiguous triple")
    entries = require_ordered(p["entries"], "payload.entries", nonempty=True)
    if len(entries) != 3:
        fail("journal manifest requires exactly three entries")
    expected_kinds = (("authorization", "scheduler"),
                      ("assignment", "scheduler"),
                      ("receipt", "launcher"))
    expected_versions = ("section_launcher_authorization.v1",
                         "section_assignment.v1",
                         "section_launcher_receipt.v1")
    for index, entry in enumerate(entries):
        where = f"payload.entries[{index}]"
        exact_keys(entry, {"ordinal", "sequence", "entry_kind", "record_ref",
                           "entry_sha256", "writer_role", "writer_principal_id",
                           "writer_control_id"}, where)
        require_int(entry["ordinal"], f"{where}.ordinal")
        if entry["ordinal"] != index:
            fail(f"{where}.ordinal does not equal its canonical slot")
        if entry["sequence"] != first + index:
            fail(f"{where}.sequence is not contiguous")
        require_literal(entry["entry_kind"], (expected_kinds[index][0],),
                        f"{where}.entry_kind")
        require_literal(entry["writer_role"], (expected_kinds[index][1],),
                        f"{where}.writer_role")
        refs.append(_ref(entry["record_ref"], f"{where}.record_ref",
                         (expected_versions[index],)))
        require_h(entry["entry_sha256"], f"{where}.entry_sha256")
        require_slug(entry["writer_principal_id"],
                     f"{where}.writer_principal_id")
        require_h(entry["writer_control_id"], f"{where}.writer_control_id")
    return refs


def _fd_rule(value: Any, where: str) -> None:
    exact_keys(value, {"fd", "role", "access", "target_kind"}, where)
    require_int(value["fd"], f"{where}.fd")
    require_literal(value["role"], ("stdin", "stdout", "stderr"),
                    f"{where}.role")
    require_literal(value["access"], ("read", "write"), f"{where}.access")
    require_literal(value["target_kind"], ("null", "pipe"),
                    f"{where}.target_kind")


def _sandbox_profile(p: Mapping[str, Any]) -> list[RefRequirement]:
    keys = {"program_ref", "platform", "launcher_binary_sha256",
            "argv_template_sha256", "native_inventory_plan_ref",
            "source_snapshot_ref", "read_only_mount_refs", "writable_mountpoint",
            "private_tmpfs_bytes", "unshare_user", "unshare_pid", "unshare_net",
            "no_new_privileges", "capability_set", "seccomp_profile_sha256",
            "environment_allowlist", "fd_policy", "permitted_fds"}
    exact_keys(p, keys, "payload")
    refs = [_program_ref(p),
            _ref(p["native_inventory_plan_ref"],
                 "payload.native_inventory_plan_ref",
                 ("section_native_inventory_plan.v1",)),
            _ref(p["source_snapshot_ref"], "payload.source_snapshot_ref",
                 ("section_content_record.v1",), ("source_snapshot",))]
    require_literal(p["platform"], ("linux-bwrap-v1",), "payload.platform")
    require_h(p["launcher_binary_sha256"], "payload.launcher_binary_sha256")
    require_h(p["argv_template_sha256"], "payload.argv_template_sha256")
    refs.extend(_refs(p["read_only_mount_refs"], "payload.read_only_mount_refs",
                      ("section_content_record.v1",), nonempty=True))
    require_literal(p["writable_mountpoint"], ("/out",),
                    "payload.writable_mountpoint")
    require_int(p["private_tmpfs_bytes"], "payload.private_tmpfs_bytes",
                minimum=1)
    for field in ("unshare_user", "unshare_pid", "unshare_net",
                  "no_new_privileges"):
        if p[field] is not True:
            fail(f"payload.{field} must be true")
    if p["capability_set"] != []:
        fail("payload.capability_set must be empty")
    require_h(p["seccomp_profile_sha256"], "payload.seccomp_profile_sha256")
    _strings(p["environment_allowlist"], "payload.environment_allowlist",
             slug=True)
    require_literal(p["fd_policy"], ("close-all-except-stdio-v1",),
                    "payload.fd_policy")
    expected = [
        {"fd": 0, "role": "stdin", "access": "read", "target_kind": "null"},
        {"fd": 1, "role": "stdout", "access": "write", "target_kind": "pipe"},
        {"fd": 2, "role": "stderr", "access": "write", "target_kind": "pipe"},
    ]
    if p["permitted_fds"] != expected:
        fail("payload.permitted_fds must be the exact stdio table")
    for index, rule in enumerate(p["permitted_fds"]):
        _fd_rule(rule, f"payload.permitted_fds[{index}]")
    return refs


def _native_inventory_plan(p: Mapping[str, Any]) -> list[RefRequirement]:
    keys = {"program_ref", "base_commit", "scope", "work_item_id", "role",
            "attempt", "workspace_id", "roots", "root_count", "observations",
            "observation_count"}
    exact_keys(p, keys, "payload")
    refs = [_program_ref(p)]
    require_g(p["base_commit"], "payload.base_commit")
    scope = require_literal(p["scope"], ("builder-dispatch",
                                         "assessor-dispatch", "assembly"),
                            "payload.scope")
    if scope == "assembly":
        if any(p[field] is not None for field in
               ("work_item_id", "role", "attempt", "workspace_id")):
            fail("assembly plan context fields must be null")
    else:
        require_h(p["work_item_id"], "payload.work_item_id")
        if p["role"] != scope.removesuffix("-dispatch"):
            fail("dispatch plan role mismatch")
        require_int(p["attempt"], "payload.attempt")
        require_h(p["workspace_id"], "payload.workspace_id")
    roots = p["roots"]
    require_sorted_unique(roots, "payload.roots",
                          key=lambda row: row.get("root_id", ""), nonempty=True)
    for index, root in enumerate(roots):
        _native_root_spec(root, f"payload.roots[{index}]", p["program_ref"])
    require_int(p["root_count"], "payload.root_count")
    if p["root_count"] != len(roots):
        fail("payload.root_count mismatch")
    root_ids = [root["root_id"] for root in roots]
    root_kinds = [root["root_kind"] for root in roots]
    central_kinds = {"candidate", "integration-checkout", "common-git",
                     "council-root", "owner-anchors", "other-worker-leaves",
                     "canonical-evidence", "hidden-suites"}
    if not central_kinds <= set(root_kinds) or \
            any(root_kinds.count(kind) != 1 for kind in central_kinds):
        fail("native plan omits or duplicates a required central root")
    if scope != "assembly":
        required_output = "builder-output" if p["role"] == "builder" \
            else "assessor-output"
        if root_kinds.count(required_output) != 1 or \
                "runtime-readonly" not in root_kinds:
            fail("dispatch plan lacks its runtime or private output root")
    central_null = central_kinds - {"candidate"}
    for root in roots:
        if root["root_kind"] in central_null and root["workspace_id"] is not None:
            fail("central protected root must have null workspace_id")
        if root["root_kind"] == "candidate" and root["workspace_id"] is None:
            fail("candidate root must bind its preallocated workspace")
        if scope != "assembly" and root["root_kind"] in {
                "runtime-readonly", "builder-output",
                "assessor-output"} and root["workspace_id"] != p["workspace_id"]:
            fail("dispatch runtime/output root workspace mismatch")
    namespaces = [root["namespace_id"] for root in roots]
    objects = [(root["filesystem_id"], root["file_id"]) for root in roots]
    if len(root_ids) != len(set(root_ids)) or \
            len(namespaces) != len(set(namespaces)) or \
            len(objects) != len(set(objects)):
        fail("native plan root ids, namespaces, and native objects must be unique")
    observations = p["observations"]
    require_sorted_unique(observations, "payload.observations",
                          key=lambda row: row.get("observation_id", ""),
                          nonempty=True)
    for index, observation in enumerate(observations):
        _observation_requirement(observation,
                                 f"payload.observations[{index}]",
                                 p["program_ref"])
        if observation["scope"] != scope or \
                observation["work_item_id"] != p["work_item_id"] or \
                observation["role"] != p["role"] or \
                observation["attempt"] != p["attempt"] or \
                observation["workspace_id"] != p["workspace_id"]:
            fail("native observation context does not equal its plan")
        if observation["root_id"] not in root_ids:
            fail("native observation references an unknown root")
    require_int(p["observation_count"], "payload.observation_count")
    if p["observation_count"] != len(observations):
        fail("payload.observation_count mismatch")
    expected_phases = ({"pre-assembly", "post-assembly"} if scope == "assembly"
                       else {"pre-dispatch", "post-worker"})
    observed_pairs: dict[str, set[str]] = {root_id: set() for root_id in root_ids}
    for observation in observations:
        phases = observed_pairs[observation["root_id"]]
        if observation["phase"] in phases:
            fail("native plan duplicates a root/phase observation")
        phases.add(observation["phase"])
    if any(phases != expected_phases for phases in observed_pairs.values()):
        fail("native plan does not require every root before and after")
    return refs


def _native_inventory(p: Mapping[str, Any]) -> list[RefRequirement]:
    keys = {"program_ref", "native_inventory_plan_ref", "base_commit",
            "observation_id", "root_id", "observer_assignment_ref",
            "observation_workspace_id", "phase", "observed_root_filesystem_id",
            "observed_root_file_id", "entries", "inventory_sha256"}
    exact_keys(p, keys, "payload")
    refs = [_program_ref(p),
            _ref(p["native_inventory_plan_ref"],
                 "payload.native_inventory_plan_ref",
                 ("section_native_inventory_plan.v1",))]
    require_g(p["base_commit"], "payload.base_commit")
    require_h(p["observation_id"], "payload.observation_id")
    require_h(p["root_id"], "payload.root_id")
    observer = _ref(p["observer_assignment_ref"],
                    "payload.observer_assignment_ref",
                    ("section_assignment.v1",), nullable=True)
    if observer:
        refs.append(observer)
    if p["observation_workspace_id"] is not None:
        require_h(p["observation_workspace_id"],
                  "payload.observation_workspace_id")
    require_literal(p["phase"], ("pre-dispatch", "post-worker",
                                  "pre-assembly", "post-assembly"),
                    "payload.phase")
    require_h(p["observed_root_filesystem_id"],
              "payload.observed_root_filesystem_id")
    require_h(p["observed_root_file_id"], "payload.observed_root_file_id")
    entries = p["entries"]
    if not isinstance(entries, list):
        fail("payload.entries must be an array")
    decoded = []
    for index, entry in enumerate(entries):
        validate_native_entry(entry, f"payload.entries[{index}]")
        decoded.append(validate_native_rel_path(entry["path"]))
    if decoded != sorted(decoded) or len(decoded) != len(set(decoded)):
        fail("payload.entries must be sorted by decoded native path and unique")
    require_h(p["inventory_sha256"], "payload.inventory_sha256")
    return refs


def _sandbox_attestation(p: Mapping[str, Any]) -> list[RefRequirement]:
    keys = {"program_ref", "assignment_ref", "launcher_receipt_ref",
            "journal_manifest_ref", "sandbox_profile_ref",
            "observed_mount_table_ref", "observed_process_status_ref",
            "observed_environment_ref", "observed_fd_table_ref",
            "source_snapshot_ref", "output_inventory_ref",
            "native_inventory_before_refs", "native_inventory_after_refs",
            "unexpected_fd_count", "writable_filesystem_fd_count",
            "external_write_attempt_count", "external_write_success_count",
            "exit_status"}
    exact_keys(p, keys, "payload")
    refs = [_program_ref(p),
            _ref(p["assignment_ref"], "payload.assignment_ref",
                 ("section_assignment.v1",)),
            _ref(p["launcher_receipt_ref"], "payload.launcher_receipt_ref",
                 ("section_launcher_receipt.v1",)),
            _ref(p["journal_manifest_ref"], "payload.journal_manifest_ref",
                 ("section_scheduler_journal_manifest.v1",)),
            _ref(p["sandbox_profile_ref"], "payload.sandbox_profile_ref",
                 ("worker_sandbox_profile.v1",))]
    for field in ("observed_mount_table_ref", "observed_process_status_ref",
                  "observed_environment_ref", "observed_fd_table_ref"):
        refs.append(_ref(p[field], f"payload.{field}",
                         ("section_content_record.v1",), ("check_evidence",)))
    refs.append(_ref(p["source_snapshot_ref"], "payload.source_snapshot_ref",
                     ("section_content_record.v1",), ("source_snapshot",)))
    refs.append(_ref(p["output_inventory_ref"], "payload.output_inventory_ref",
                     ("section_content_record.v1",), ("read_inventory",)))
    refs.extend(_refs(p["native_inventory_before_refs"],
                      "payload.native_inventory_before_refs",
                      ("section_native_inventory.v1",), nonempty=True))
    refs.extend(_refs(p["native_inventory_after_refs"],
                      "payload.native_inventory_after_refs",
                      ("section_native_inventory.v1",), nonempty=True))
    for field in ("unexpected_fd_count", "writable_filesystem_fd_count",
                  "external_write_attempt_count", "external_write_success_count",
                  "exit_status"):
        require_int(p[field], f"payload.{field}")
    if p["unexpected_fd_count"] or p["writable_filesystem_fd_count"] or \
            p["external_write_success_count"]:
        fail("sandbox attestation records forbidden authority or write success")
    return refs


def _finding(p: Mapping[str, Any]) -> list[RefRequirement]:
    keys = {"program_ref", "contract_ref", "assessor_assignment_ref",
            "affected_proposal_ref", "finding_declaration_ref", "audit_level",
            "severity", "invariant_id", "claim", "evidence_ref",
            "reproduction_ref", "affected_path", "blocks_local_pass", "status",
            "predecessor_finding_ref", "resolution_evidence_ref"}
    exact_keys(p, keys, "payload")
    refs = [_program_ref(p),
            _ref(p["contract_ref"], "payload.contract_ref",
                 ("section_contract.v1",)),
            _ref(p["assessor_assignment_ref"],
                 "payload.assessor_assignment_ref", ("section_assignment.v1",)),
            _ref(p["affected_proposal_ref"], "payload.affected_proposal_ref",
                 ("section_content_record.v1",), ("proposal",)),
            _ref(p["finding_declaration_ref"],
                 "payload.finding_declaration_ref",
                 ("section_content_record.v1",), ("finding_declaration",)),
            _ref(p["evidence_ref"], "payload.evidence_ref",
                 ("section_content_record.v1",), ("finding_evidence",)),
            _ref(p["reproduction_ref"], "payload.reproduction_ref",
                 ("section_content_record.v1",), ("reproduction",))]
    require_literal(p["audit_level"], ("section", "boundary", "system"),
                    "payload.audit_level")
    require_literal(p["severity"],
                    ("INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"),
                    "payload.severity")
    require_slug(p["invariant_id"], "payload.invariant_id")
    require_string(p["claim"], "payload.claim")
    if p["affected_path"] is not None:
        validate_path(p["affected_path"], "payload.affected_path")
    require_bool(p["blocks_local_pass"], "payload.blocks_local_pass")
    status = require_literal(p["status"], ("open", "resolved", "unreproduced"),
                             "payload.status")
    predecessor = _ref(p["predecessor_finding_ref"],
                       "payload.predecessor_finding_ref",
                       ("section_finding.v1",), nullable=True)
    resolution = _ref(p["resolution_evidence_ref"],
                      "payload.resolution_evidence_ref",
                      ("section_content_record.v1",), ("resolution",),
                      nullable=True)
    if predecessor:
        refs.append(predecessor)
    if resolution:
        refs.append(resolution)
    if status == "resolved" and (predecessor is None or resolution is None):
        fail("resolved finding requires predecessor and resolution evidence")
    if status != "resolved" and resolution is not None:
        fail("only a resolved finding may carry resolution evidence")
    return refs


def _assessment_manifest(p: Mapping[str, Any]) -> list[RefRequirement]:
    keys = {"program_ref", "contract_ref", "work_item_id",
            "assessor_assignment_ref", "assessor_context_ref", "proposal_ref",
            "assessment_declaration_ref", "assessor_output_inventory_ref",
            "check_declaration_refs", "check_results", "finding_refs",
            "finding_inventory_sha256", "finding_count", "open_blocking_count",
            "local_assessment", "error_reason", "predecessor_assessment_ref"}
    exact_keys(p, keys, "payload")
    refs = [_program_ref(p),
            _ref(p["contract_ref"], "payload.contract_ref",
                 ("section_contract.v1",)),
            _ref(p["assessor_assignment_ref"],
                 "payload.assessor_assignment_ref", ("section_assignment.v1",)),
            _ref(p["assessor_context_ref"], "payload.assessor_context_ref",
                 ("section_context_bundle.v1",)),
            _ref(p["proposal_ref"], "payload.proposal_ref",
                 ("section_content_record.v1",), ("proposal",)),
            _ref(p["assessment_declaration_ref"],
                 "payload.assessment_declaration_ref",
                 ("section_content_record.v1",), ("assessment_declaration",)),
            _ref(p["assessor_output_inventory_ref"],
                 "payload.assessor_output_inventory_ref",
                 ("section_content_record.v1",), ("read_inventory",))]
    require_h(p["work_item_id"], "payload.work_item_id")
    refs.extend(_refs(p["check_declaration_refs"],
                      "payload.check_declaration_refs",
                      ("section_content_record.v1",), ("check_declaration",),
                      nonempty=True))
    refs.extend(_check_results(p["check_results"], "payload.check_results",
                               nonempty=True))
    refs.extend(_refs(p["finding_refs"], "payload.finding_refs",
                      ("section_finding.v1",)))
    require_h(p["finding_inventory_sha256"],
              "payload.finding_inventory_sha256")
    require_int(p["finding_count"], "payload.finding_count")
    require_int(p["open_blocking_count"], "payload.open_blocking_count")
    if p["finding_count"] != len(p["finding_refs"]):
        fail("payload.finding_count mismatch")
    disposition = require_literal(p["local_assessment"],
                                  ("pass", "blocked", "error"),
                                  "payload.local_assessment")
    if disposition == "error":
        require_string(p["error_reason"], "payload.error_reason")
    elif p["error_reason"] is not None:
        fail("only error assessment may carry error_reason")
    predecessor = _ref(p["predecessor_assessment_ref"],
                       "payload.predecessor_assessment_ref",
                       ("section_assessment_manifest.v1",), nullable=True)
    if predecessor:
        refs.append(predecessor)
    return refs


def _evidence_bundle(p: Mapping[str, Any]) -> list[RefRequirement]:
    keys = {"program_ref", "contract_ref", "work_item_id", "base_commit",
            "builder_assignment_ref", "assessor_assignment_ref",
            "builder_launcher_receipt_ref", "assessor_launcher_receipt_ref",
            "builder_journal_manifest_ref", "assessor_journal_manifest_ref",
            "builder_context_ref", "assessor_context_ref",
            "builder_sandbox_attestation_ref", "assessor_sandbox_attestation_ref",
            "proposal_ref", "diff_preview_ref", "assessment_manifest_ref",
            "test_manifest_ref", "test_result_refs", "invariant_results",
            "local_assessment", "error_reason", "resource_metrics",
            "dependency_snapshot_ref", "staleness_input_refs"}
    exact_keys(p, keys, "payload")
    refs = [_program_ref(p),
            _ref(p["contract_ref"], "payload.contract_ref",
                 ("section_contract.v1",)),
            _ref(p["builder_assignment_ref"], "payload.builder_assignment_ref",
                 ("section_assignment.v1",)),
            _ref(p["assessor_assignment_ref"], "payload.assessor_assignment_ref",
                 ("section_assignment.v1",)),
            _ref(p["builder_launcher_receipt_ref"],
                 "payload.builder_launcher_receipt_ref",
                 ("section_launcher_receipt.v1",)),
            _ref(p["assessor_launcher_receipt_ref"],
                 "payload.assessor_launcher_receipt_ref",
                 ("section_launcher_receipt.v1",)),
            _ref(p["builder_journal_manifest_ref"],
                 "payload.builder_journal_manifest_ref",
                 ("section_scheduler_journal_manifest.v1",)),
            _ref(p["assessor_journal_manifest_ref"],
                 "payload.assessor_journal_manifest_ref",
                 ("section_scheduler_journal_manifest.v1",)),
            _ref(p["builder_context_ref"], "payload.builder_context_ref",
                 ("section_context_bundle.v1",)),
            _ref(p["assessor_context_ref"], "payload.assessor_context_ref",
                 ("section_context_bundle.v1",)),
            _ref(p["builder_sandbox_attestation_ref"],
                 "payload.builder_sandbox_attestation_ref",
                 ("worker_sandbox_attestation.v1",)),
            _ref(p["assessor_sandbox_attestation_ref"],
                 "payload.assessor_sandbox_attestation_ref",
                 ("worker_sandbox_attestation.v1",)),
            _ref(p["proposal_ref"], "payload.proposal_ref",
                 ("section_content_record.v1",), ("proposal",)),
            _ref(p["diff_preview_ref"], "payload.diff_preview_ref",
                 ("section_content_record.v1",), ("diff_preview",)),
            _ref(p["assessment_manifest_ref"], "payload.assessment_manifest_ref",
                 ("section_assessment_manifest.v1",)),
            _ref(p["test_manifest_ref"], "payload.test_manifest_ref",
                 ("section_content_record.v1",), ("test_manifest",)),
            _ref(p["dependency_snapshot_ref"], "payload.dependency_snapshot_ref",
                 ("section_content_record.v1",), ("read_inventory",))]
    require_h(p["work_item_id"], "payload.work_item_id")
    require_g(p["base_commit"], "payload.base_commit")
    refs.extend(_refs(p["test_result_refs"], "payload.test_result_refs",
                      ("section_content_record.v1",), ("test_result",)))
    refs.extend(_check_results(p["invariant_results"],
                               "payload.invariant_results", nonempty=True))
    disposition = require_literal(p["local_assessment"],
                                  ("pass", "blocked", "error"),
                                  "payload.local_assessment")
    if disposition == "error":
        require_string(p["error_reason"], "payload.error_reason")
    elif p["error_reason"] is not None:
        fail("only error bundle may carry error_reason")
    refs.extend(_metrics(p["resource_metrics"], "payload.resource_metrics"))
    refs.extend(_refs(p["staleness_input_refs"], "payload.staleness_input_refs",
                      nonempty=True))
    return refs


def _boundary_report(p: Mapping[str, Any]) -> list[RefRequirement]:
    keys = {"program_ref", "work_graph_ref", "section_bundle_refs",
            "final_scope_ref", "changed_section_ids", "changed_interfaces",
            "affected_contract_refs", "dependency_closure_ref",
            "activated_check_results", "conflict_evidence_refs",
            "unknown_classification_count", "required_system_audit_scope_ids"}
    exact_keys(p, keys, "payload")
    refs = [_program_ref(p),
            _ref(p["work_graph_ref"], "payload.work_graph_ref",
                 ("section_work_graph.v1",)),
            _ref(p["final_scope_ref"], "payload.final_scope_ref",
                 ("final_scope_manifest.v1",)),
            _ref(p["dependency_closure_ref"], "payload.dependency_closure_ref",
                 ("section_content_record.v1",), ("read_inventory",))]
    refs.extend(_refs(p["section_bundle_refs"], "payload.section_bundle_refs",
                      ("section_evidence_bundle.v1",), nonempty=True))
    _strings(p["changed_section_ids"], "payload.changed_section_ids", slug=True)
    _interfaces(p["changed_interfaces"], "payload.changed_interfaces")
    refs.extend(_refs(p["affected_contract_refs"],
                      "payload.affected_contract_refs",
                      ("section_contract.v1",)))
    refs.extend(_check_results(p["activated_check_results"],
                               "payload.activated_check_results", nonempty=True))
    refs.extend(_refs(p["conflict_evidence_refs"],
                      "payload.conflict_evidence_refs",
                      ("section_content_record.v1",), ("conflict_evidence",)))
    require_int(p["unknown_classification_count"],
                "payload.unknown_classification_count")
    _strings(p["required_system_audit_scope_ids"],
             "payload.required_system_audit_scope_ids", slug=True, nonempty=True)
    return refs


def _comparison_report(p: Mapping[str, Any]) -> list[RefRequirement]:
    keys = {"program_ref", "workload_identity_sha256", "sequential_root_ref",
            "hierarchical_root_ref", "metric_results", "seeded_defect_ids",
            "sequential_detected_defect_ids", "hierarchical_detected_defect_ids",
            "escaped_defect_ids", "limitations", "conclusion"}
    exact_keys(p, keys, "payload")
    refs = [_program_ref(p),
            _ref(p["sequential_root_ref"], "payload.sequential_root_ref",
                 ("section_evidence_root.v1",), external=True),
            _ref(p["hierarchical_root_ref"], "payload.hierarchical_root_ref",
                 ("section_evidence_root.v1",), external=True)]
    if p["sequential_root_ref"] == p["hierarchical_root_ref"]:
        fail("comparison roots must be distinct")
    require_h(p["workload_identity_sha256"],
              "payload.workload_identity_sha256")
    if not p["metric_results"]:
        fail("payload.metric_results must be nonempty")
    refs.extend(_metrics(p["metric_results"], "payload.metric_results"))
    for field in ("seeded_defect_ids", "sequential_detected_defect_ids",
                  "hierarchical_detected_defect_ids", "escaped_defect_ids"):
        _strings(p[field], f"payload.{field}", slug=True,
                 nonempty=field == "seeded_defect_ids")
    _strings(p["limitations"], "payload.limitations", nonempty=True)
    require_literal(p["conclusion"],
                    ("improved", "non_inferior", "inconclusive", "worse"),
                    "payload.conclusion")
    return refs


def _final_scope(p: Mapping[str, Any]) -> list[RefRequirement]:
    keys = {"program_ref", "work_graph_ref", "base_commit",
            "predicted_changes", "actual_changes",
            "realized_system_artifact_paths", "section_bundle_refs",
            "assembler_binary_ref", "assembled_tree_sha256", "envelope_paths"}
    exact_keys(p, keys, "payload")
    refs = [_program_ref(p),
            _ref(p["work_graph_ref"], "payload.work_graph_ref",
                 ("section_work_graph.v1",)),
            _ref(p["assembler_binary_ref"], "payload.assembler_binary_ref",
                 ("section_content_record.v1",), ("assembler_binary",))]
    require_g(p["base_commit"], "payload.base_commit")
    validate_change_set(p["predicted_changes"], "payload.predicted_changes",
                        predicted=True, nonempty=True)
    validate_change_set(p["actual_changes"], "payload.actual_changes",
                        predicted=False)
    paths = p["realized_system_artifact_paths"]
    require_sorted_unique(paths, "payload.realized_system_artifact_paths",
                          nonempty=True)
    for index, path in enumerate(paths):
        validate_path(path, f"payload.realized_system_artifact_paths[{index}]")
    require_unique_paths(paths, "payload.realized_system_artifact_paths")
    refs.extend(_refs(p["section_bundle_refs"], "payload.section_bundle_refs",
                      ("section_evidence_bundle.v1",), nonempty=True))
    require_h(p["assembled_tree_sha256"], "payload.assembled_tree_sha256")
    envelopes = p["envelope_paths"]
    require_sorted_unique(envelopes, "payload.envelope_paths", nonempty=True)
    if len(envelopes) != 2:
        fail("payload.envelope_paths must contain exactly two paths")
    for index, path in enumerate(envelopes):
        validate_path(path, f"payload.envelope_paths[{index}]")
    return refs


def _evidence_root(p: Mapping[str, Any]) -> list[RefRequirement]:
    keys = {"planned_request_id", "program_ref", "parent_build_event_id",
            "parent_build_event_hash", "base_commit", "work_graph_ref",
            "final_scope_ref", "record_inventory", "operation_log_ref",
            "record_count"}
    exact_keys(p, keys, "payload")
    refs = [_program_ref(p),
            _ref(p["work_graph_ref"], "payload.work_graph_ref",
                 ("section_work_graph.v1",)),
            _ref(p["final_scope_ref"], "payload.final_scope_ref",
                 ("final_scope_manifest.v1",)),
            _ref(p["operation_log_ref"], "payload.operation_log_ref",
                 ("section_content_record.v1",), ("operation_log",))]
    require_request_id(p["planned_request_id"], "payload.planned_request_id")
    require_event(p["parent_build_event_id"], "payload.parent_build_event_id")
    require_h(p["parent_build_event_hash"], "payload.parent_build_event_hash")
    require_g(p["base_commit"], "payload.base_commit")
    inventory = p["record_inventory"]
    require_sorted_unique(inventory, "payload.record_inventory",
                          key=lambda row: (row.get("schema_version", ""),
                                           row.get("record_id", "")),
                          nonempty=True)
    allowed = set(RECORD_TYPES) - {"section_evidence_root.v1"}
    for index, row in enumerate(inventory):
        where = f"payload.record_inventory[{index}]"
        exact_keys(row, {"schema_version", "record_id", "content_sha256",
                         "repository_relpath"}, where)
        require_literal(row["schema_version"], allowed,
                        f"{where}.schema_version")
        require_h(row["record_id"], f"{where}.record_id")
        require_h(row["content_sha256"], f"{where}.content_sha256")
        validate_path(row["repository_relpath"], f"{where}.repository_relpath")
    require_int(p["record_count"], "payload.record_count")
    if p["record_count"] != len(inventory):
        fail("payload.record_count mismatch")
    require_unique_paths([row["repository_relpath"] for row in inventory],
                         "payload.record_inventory")
    return refs


RECORD_TYPES: dict[str, RecordType] = {
    "section_program.v1": RecordType("section_program_id",
                                     "council:section-program:v1", _program),
    "section_bootstrap_content.v1": RecordType(
        "section_bootstrap_content_id", "council:section-bootstrap-content:v1",
        _bootstrap_content),
    "section_principal_registry.v1": RecordType(
        "section_principal_registry_id", "council:section-principal-registry:v1",
        _principal_registry),
    "section_contract.v1": RecordType("section_contract_id",
                                      "council:section-contract:v1", _contract),
    "section_work_graph.v1": RecordType("section_work_graph_id",
                                        "council:section-work-graph:v1",
                                        _work_graph),
    "section_context_bundle.v1": RecordType(
        "section_context_bundle_id", "council:section-context-bundle:v1",
        _context_bundle),
    "section_content_record.v1": RecordType(
        "section_content_record_id", "council:section-content-record:v1",
        _content_record),
    "section_assignment.v1": RecordType(
        "section_assignment_id", "council:section-assignment:v1", _assignment),
    "section_launcher_authorization.v1": RecordType(
        "section_launcher_authorization_id",
        "council:section-launcher-authorization:v1", _authorization),
    "section_launcher_receipt.v1": RecordType(
        "section_launcher_receipt_id", "council:section-launcher-receipt:v1",
        _receipt),
    "section_scheduler_journal_manifest.v1": RecordType(
        "section_scheduler_journal_manifest_id",
        "council:section-scheduler-journal-manifest:v1", _journal_manifest),
    "worker_sandbox_profile.v1": RecordType(
        "worker_sandbox_profile_id", "council:worker-sandbox-profile:v1",
        _sandbox_profile),
    "worker_sandbox_attestation.v1": RecordType(
        "worker_sandbox_attestation_id",
        "council:worker-sandbox-attestation:v1", _sandbox_attestation),
    "section_native_inventory_plan.v1": RecordType(
        "section_native_inventory_plan_id",
        "council:section-native-inventory-plan:v1", _native_inventory_plan),
    "section_native_inventory.v1": RecordType(
        "section_native_inventory_id", "council:section-native-inventory:v1",
        _native_inventory),
    "section_finding.v1": RecordType("section_finding_id",
                                     "council:section-finding:v1", _finding),
    "section_assessment_manifest.v1": RecordType(
        "section_assessment_manifest_id",
        "council:section-assessment-manifest:v1", _assessment_manifest),
    "section_evidence_bundle.v1": RecordType(
        "section_evidence_bundle_id", "council:section-evidence-bundle:v1",
        _evidence_bundle),
    "boundary_impact_report.v1": RecordType(
        "boundary_impact_report_id", "council:boundary-impact-report:v1",
        _boundary_report),
    "section_comparison_report.v1": RecordType(
        "section_comparison_report_id", "council:section-comparison-report:v1",
        _comparison_report),
    "final_scope_manifest.v1": RecordType(
        "final_scope_manifest_id", "council:final-scope-manifest:v1",
        _final_scope),
    "section_evidence_root.v1": RecordType(
        "section_evidence_root_id", "council:section-evidence-root:v1",
        _evidence_root),
}


def id_field_for(record: Mapping[str, Any]) -> str:
    return RECORD_TYPES[record["schema_version"]].id_field


def record_id(record: Mapping[str, Any]) -> str:
    return record[id_field_for(record)]


def record_ref(record: Mapping[str, Any]) -> dict[str, str]:
    validate_record(record)
    return {"record_id": record_id(record),
            "content_sha256": compute_record_content_sha256(record)}
