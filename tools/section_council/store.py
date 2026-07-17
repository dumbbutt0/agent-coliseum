"""Typed reference resolution and complete HSC evidence-root validation."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import subprocess
from typing import Any, Iterable, Mapping

from tools.council import events as council_events
from tools.council.schemas import (CouncilError, canonical_json, domain_hash,
                                   validate_commit, validate_event,
                                   validate_repository)

from .core import (
    HSCValidationError,
    canonical_sort_key,
    change_sort_key,
    exact_keys,
    fail,
    predicted_matches_actual,
    require_bool,
    require_h,
    require_int,
    require_literal,
    require_request_id,
    require_slug,
    require_sorted_unique,
    require_string,
    require_unique_paths,
    strict_json_bytes,
    validate_path,
    validate_ref,
)
from .records import (
    RECORD_TYPES,
    RefRequirement,
    _file_refs,
    id_field_for,
    record_id,
    record_ref,
    validate_record,
)
from .work import dependency_closure


@dataclass(frozen=True)
class ValidationReport:
    program_id: str
    root_id: str
    record_count: int
    construction_order: tuple[str, ...]
    construction_ordinals: Mapping[str, int]


class RecordStore:
    """An immutable validation view over one proposed HSC evidence root.

    ``blobs`` maps the repository storage path declared by bootstrap/content
    records to exact bytes. ``external_roots`` maps a permitted comparison
    root id to its exact content SHA-256. Neither collection grants I/O.
    """

    def __init__(self, records: Iterable[Mapping[str, Any]], *,
                 blobs: Mapping[str, bytes] | None = None,
                 external_roots: Mapping[str, str] | None = None):
        self.records = tuple(copy.deepcopy(record) for record in records)
        self.blobs = dict(blobs or {})
        self.external_roots = dict(external_roots or {})
        self.by_id: dict[str, dict] = {}
        self.refs: dict[str, list[RefRequirement]] = {}
        for record in self.records:
            requirements = validate_record(record)
            rid = record_id(record)
            if rid in self.by_id:
                fail(f"duplicate record id {rid}")
            self.by_id[rid] = record
            self.refs[rid] = list(requirements)
        self._closed_blob_refs: dict[str, list[RefRequirement]] = {}
        self.closed_values: dict[str, Any] = {}

    def get(self, ref: Mapping[str, str], *, versions: Iterable[str] = (),
            artifacts: Iterable[str] = (), external: bool = False) -> dict:
        validate_ref(ref, "reference")
        rid = ref["record_id"]
        if external:
            if rid not in self.external_roots or \
                    self.external_roots[rid] != ref["content_sha256"]:
                fail(f"external root {rid} is not sealed by the supplied authority")
            return {"schema_version": "section_evidence_root.v1",
                    "section_evidence_root_id": rid, "payload": {}}
        try:
            record = self.by_id[rid]
        except KeyError as exc:
            raise HSCValidationError(f"unresolved reference {rid}") from exc
        if compute_content_sha(record) != ref["content_sha256"]:
            fail(f"reference content SHA mismatch for {rid}")
        allowed_versions = tuple(versions)
        if allowed_versions and record["schema_version"] not in allowed_versions:
            fail(f"reference type substitution at {rid}")
        allowed_artifacts = tuple(artifacts)
        if allowed_artifacts:
            if record["schema_version"] == "section_bootstrap_content.v1":
                artifact = record["payload"]["artifact_type"]
            elif record["schema_version"] == "section_content_record.v1":
                artifact = record["payload"]["artifact_type"]
            else:
                fail(f"artifact reference {rid} does not target content")
            if artifact not in allowed_artifacts:
                fail(f"artifact type substitution at {rid}")
        return record

    def validate_all(self) -> None:
        for source_id, requirements in self.refs.items():
            for requirement in requirements:
                self.get(requirement.ref,
                         versions=requirement.expected_versions,
                         artifacts=requirement.artifact_types,
                         external=requirement.external)
        self._validate_blobs()

    def validate_root(self, root: Mapping[str, Any], *,
                      council_root: str, repo: str, repo_roots: Iterable[str],
                      candidate_commit: str) -> ValidationReport:
        """Validate one complete HSC evidence root against AUTHENTICATED
        sources only — never caller-supplied truth:

        - the BUILD_STARTED authority is read from the authenticated Council
          chain at ``council_root`` (verified with the Council's own
          ``verify_chain``) and proven a member there; an inline event or a
          fabricated genesis fork can never stand in for it.
        - the base and candidate project/namespace trees are read directly
          from the Git object store of ``repo`` at ``program.base_commit`` and
          the audited ``candidate_commit`` (both must be real commits); every
          boundary, tree, staleness, invariant, and evidence claim is then
          independently reconstructed and compared exactly.

        Trust boundary: ``council_root``/``repo`` name the authenticated
        Council store and repository the same way every Council tool trusts
        ``COUNCIL_ROOT``/``COUNCIL_REPO_ROOTS`` — the caller must supply the
        genuine ones. The validator authenticates their contents; it does not
        accept their contents from the caller.
        """
        validate_record(root)
        if root["schema_version"] != "section_evidence_root.v1":
            fail("root must be section_evidence_root.v1")
        root_id = record_id(root)
        if root_id in self.by_id:
            fail("evidence root must not inventory itself")
        root_requirements = validate_record(root)
        self.validate_all()
        for requirement in root_requirements:
            self.get(requirement.ref, versions=requirement.expected_versions,
                     artifacts=requirement.artifact_types,
                     external=requirement.external)
        payload = root["payload"]
        self._validate_inventory(payload)
        self._validate_reachability(root_requirements)
        program = self.get(payload["program_ref"], versions=("section_program.v1",))
        program_id = record_id(program)
        build_event = self._read_authenticated_authority(council_root, program,
                                                         root)
        self._validate_program_bindings(program, root, build_event)
        self._validate_program_membership(program)
        self._validate_relations(program, root)
        base_tree = _read_git_tree(repo, repo_roots,
                                   program["payload"]["base_commit"])
        candidate_tree = _read_git_tree(repo, repo_roots, candidate_commit)
        self._validate_candidate_tree(program, root, candidate_tree, base_tree)
        order, ordinals = self._topological_order(root, root_requirements)
        return ValidationReport(program_id, root_id, len(self.records),
                                tuple(order), ordinals)

    def _read_authenticated_authority(self, council_root: str,
                                      program: Mapping[str, Any],
                                      root: Mapping[str, Any]) -> dict:
        """Read the BUILD_STARTED authority from the authenticated Council
        chain and prove membership. The event is obtained from the chain by
        the id the root claims; it is never accepted from the caller, so a
        fabricated genesis-linked fork cannot masquerade as authority."""
        if not isinstance(council_root, str) or not council_root:
            fail("an authenticated Council root path is required for authority")
        try:
            report = council_events.verify_chain(council_root)
        except (CouncilError, OSError, ValueError) as exc:
            raise HSCValidationError(
                f"Council chain at {council_root} could not be verified: "
                f"{exc}") from exc
        if not report.ok or report.suffix_incomplete:
            fail("Council chain at the supplied root is not fully verified")
        chain = council_events.read_chain(council_root)
        rp = root["payload"]
        claimed_id = rp["parent_build_event_id"]
        matches = [event for event in chain
                   if event.get("event_id") == claimed_id]
        if len(matches) != 1:
            fail("root parent_build_event_id is not a unique authenticated "
                 "Council event")
        event = matches[0]
        if event.get("event_hash") != rp["parent_build_event_hash"]:
            fail("authenticated event hash differs from the root binding")
        try:
            validate_event(dict(event))
        except (CouncilError, ValueError, TypeError, KeyError) as exc:
            raise HSCValidationError(
                f"authenticated authority event is not canonical: {exc}") \
                from exc
        if event.get("event_type") != "BUILD_STARTED":
            fail("HSC parent authority must be a BUILD_STARTED event")
        return event

    def _validate_inventory(self, p: Mapping[str, Any]) -> None:
        rows = p["record_inventory"]
        if len(rows) != len(self.records):
            fail("evidence-root inventory is not the complete record set")
        expected_ids = set(self.by_id)
        seen_ids: set[str] = set()
        paths: set[str] = set()
        for row in rows:
            rid = row["record_id"]
            if rid not in expected_ids or rid in seen_ids:
                fail("evidence-root inventory has an omitted, extra, or duplicate id")
            record = self.by_id[rid]
            if row["schema_version"] != record["schema_version"] or \
                    row["content_sha256"] != compute_content_sha(record):
                fail("evidence-root inventory row does not bind exact record bytes")
            if row["repository_relpath"] in paths:
                fail("two records claim the same repository path")
            paths.add(row["repository_relpath"])
            seen_ids.add(rid)
        if seen_ids != expected_ids:
            fail("evidence-root inventory does not enumerate every record")

    def _validate_reachability(self, root_requirements: list[RefRequirement]) \
            -> None:
        """Reject inventory members outside the semantic reference closure.

        Reachability is computed from the root's explicit typed references,
        plus the sanctioned terminal analysis/observation records that
        nothing references by design but whose exact bindings are enforced
        elsewhere: the boundary/comparison reports (bound to the root's
        graph and scope) and the assembly-scope native observation evidence
        (each row must match its plan requirement exactly, so an invented
        observation is refused). The closure runs BEFORE any terminal
        inventory-order edge exists; mere enumeration in the inventory is
        not reachability."""
        seeds = [requirement.ref["record_id"]
                 for requirement in root_requirements
                 if not requirement.external]
        for record in self.records:
            if record["schema_version"] in ("boundary_impact_report.v1",
                                            "section_comparison_report.v1"):
                seeds.append(record_id(record))
            elif record["schema_version"] == "section_native_inventory.v1" \
                    and record["payload"]["phase"] in ("pre-assembly",
                                                       "post-assembly"):
                seeds.append(record_id(record))
        reachable: set[str] = set()
        frontier = [rid for rid in seeds if rid in self.by_id]
        while frontier:
            rid = frontier.pop()
            if rid in reachable:
                continue
            reachable.add(rid)
            for requirement in self.refs.get(rid, []) + \
                    self._closed_blob_refs.get(rid, []):
                if requirement.external:
                    continue
                target = requirement.ref["record_id"]
                if target in self.by_id and target not in reachable:
                    frontier.append(target)
        orphans = set(self.by_id) - reachable
        if orphans:
            fail("evidence-root inventory admits a semantically unreachable "
                 "record")

    def _reference_closure(self, seed_refs: Iterable[Mapping[str, str]]) \
            -> set[str]:
        """Transitive internal reference closure over records and closed
        declaration blobs, starting from explicit seed references."""
        reached: set[str] = set()
        frontier = [ref["record_id"] for ref in seed_refs]
        while frontier:
            rid = frontier.pop()
            if rid in reached:
                continue
            if rid not in self.by_id:
                fail("reference closure reaches an unresolved record")
            reached.add(rid)
            for requirement in self.refs.get(rid, []) + \
                    self._closed_blob_refs.get(rid, []):
                if not requirement.external:
                    frontier.append(requirement.ref["record_id"])
        return reached

    def _validate_blobs(self) -> None:
        declared_paths: set[str] = set()
        for record in self.records:
            if record["schema_version"] not in (
                    "section_bootstrap_content.v1", "section_content_record.v1"):
                continue
            payload = record["payload"]
            path = payload["storage_relpath"]
            if path in declared_paths:
                fail(f"duplicate raw content path {path}")
            declared_paths.add(path)
            if path not in self.blobs:
                fail(f"raw content bytes missing for {path}")
            data = self.blobs[path]
            if not isinstance(data, bytes) or len(data) != payload["byte_length"] or \
                    hashlib.sha256(data).hexdigest() != payload["blob_sha256"]:
                fail(f"raw content size or digest mismatch for {path}")
            refs, value = self._validate_closed_blob(record, data)
            self._closed_blob_refs[record_id(record)] = refs
            if value is not None:
                self.closed_values[record_id(record)] = value
        extras = set(self.blobs) - declared_paths
        if extras:
            fail(f"unreferenced raw content bytes: {sorted(extras)!r}")

    def _validate_closed_blob(self, record: Mapping[str, Any], data: bytes) \
            -> tuple[list[RefRequirement], Any | None]:
        payload = record["payload"]
        artifact = payload["artifact_type"]
        if payload["media_type"] != "application/json":
            return [], None
        value = strict_json_bytes(data, payload["storage_relpath"])
        if artifact == "check_declaration":
            return _closed_check_declaration(value), value
        if artifact == "finding_declaration":
            return _closed_finding_declaration(value), value
        if artifact == "assessment_declaration":
            return _closed_assessment_declaration(value), value
        # Bootstrap schema/read inventories and the remaining JSON content are
        # still closed canonical JSON, but their domain-specific shape belongs
        # to the schema/profile that consumed them.
        return [], value

    def _validate_program_bindings(self, program: Mapping[str, Any],
                                   root: Mapping[str, Any],
                                   event: Mapping[str, Any]) -> None:
        pp = program["payload"]
        rp = root["payload"]
        if rp["planned_request_id"] != pp["planned_request_id"] or \
                rp["base_commit"] != pp["base_commit"]:
            fail("root/program request or base commit mismatch")
        if not isinstance(event, dict):
            fail("canonical BUILD_STARTED event is required")
        if event.get("event_id") != rp["parent_build_event_id"] or \
                event.get("event_hash") != rp["parent_build_event_hash"] or \
                event.get("event_type") != "BUILD_STARTED" or \
                event.get("request_id") != pp["planned_request_id"] or \
                event.get("repository") != pp["repository"] or \
                event.get("target_commit") != pp["base_commit"]:
            fail("BUILD_STARTED event does not bind the HSC program")
        ep = event.get("payload", {})
        pref = record_ref(program)
        if ep.get("section_program_id") != pref["record_id"] or \
                ep.get("section_program_content_sha256") != pref["content_sha256"] or \
                ep.get("hsc_base_commit") != pp["base_commit"] or \
                ep.get("hsc_execution_mode") != pp["execution_mode"]:
            fail("BUILD_STARTED HSC payload binding mismatch")
        for contract in _records(self, "section_contract.v1"):
            cp = contract["payload"]
            if cp["parent_build_event_id"] != event["event_id"] or \
                    cp["parent_build_event_hash"] != event["event_hash"]:
                fail("contract BUILD_STARTED binding mismatch")

    def _validate_program_membership(self, program: Mapping[str, Any]) -> None:
        pref = record_ref(program)
        pp = program["payload"]
        programs = _records(self, "section_program.v1")
        registries = _records(self, "section_principal_registry.v1")
        if len(programs) != 1 or record_id(programs[0]) != record_id(program):
            fail("evidence root must contain exactly its bound Section Program")
        if len(registries) != 1 or \
                record_ref(registries[0]) != pp["principal_registry_ref"]:
            fail("evidence root must contain exactly its bound principal registry")
        prefix = f"artifacts/section-council/{pp['planned_request_id']}/"
        envelopes = {prefix + "root.json", prefix + "final-scope.json"}
        for change in pp["system_artifact_predictions"]:
            if not change["path"].startswith(prefix) or change["path"] in envelopes:
                fail("program system artifact prediction escapes its fixed namespace")
        for record in self.records:
            schema = record["schema_version"]
            payload = record["payload"]
            if schema in ("section_bootstrap_content.v1",
                          "section_principal_registry.v1",
                          "section_program.v1"):
                if "program_ref" in payload:
                    fail(f"{schema} must not contain a program back-reference")
                continue
            if payload.get("program_ref") != pref:
                fail(f"cross-program or missing program_ref in {schema}")
            if schema == "section_content_record.v1" and not \
                    payload["storage_relpath"].startswith(prefix + "content/"):
                fail("content record path does not match program request id")
        for record in _records(self, "section_bootstrap_content.v1"):
            if record["payload"]["planned_request_id"] != \
                    pp["planned_request_id"]:
                fail("bootstrap record request id differs from program")
        declared_bootstrap = set(_ref_ids(pp["schema_profile_refs"]))
        for declaration in pp["section_declarations"]:
            declared_bootstrap.update(_ref_ids(
                declaration["read_inventory_refs"]))
        if declared_bootstrap != {
                record_id(record)
                for record in _records(self, "section_bootstrap_content.v1")}:
            fail("program does not bind every and only bootstrap content record")
        for ref in pp["schema_profile_refs"]:
            target = self.get(ref, versions=("section_bootstrap_content.v1",),
                              artifacts=("schema_profile",))
            if target["payload"]["planned_request_id"] != pp["planned_request_id"]:
                fail("bootstrap schema profile request id mismatch")
        registry = self.get(pp["principal_registry_ref"],
                            versions=("section_principal_registry.v1",))
        rpay = registry["payload"]
        if (rpay["planned_request_id"], rpay["repository"], rpay["base_commit"]) != \
                (pp["planned_request_id"], pp["repository"], pp["base_commit"]):
            fail("principal registry does not bind the program root")

    def _validate_relations(self, program: Mapping[str, Any],
                            root: Mapping[str, Any]) -> None:
        self._validate_contracts_and_graph(program)
        self._validate_dispatches(program)
        self._validate_contexts(program)
        self._validate_native_plans(program)
        self._validate_native_inventories()
        self._validate_attestations()
        self._validate_assessments(root)
        self._validate_bundles()
        self._validate_final_scope(program, root)
        self._validate_boundary_reports(program, root)
        self._validate_rooted_paths(program, root)

    def _topological_order(self, root: Mapping[str, Any],
                           root_requirements: list[RefRequirement]) \
            -> tuple[list[str], dict[str, int]]:
        root_id = record_id(root)
        nodes = dict(self.by_id)
        nodes[root_id] = dict(root)
        requirements = {key: list(value) for key, value in self.refs.items()}
        requirements[root_id] = list(root_requirements)
        for source_id, embedded in self._closed_blob_refs.items():
            requirements.setdefault(source_id, []).extend(embedded)
        outgoing: dict[str, set[str]] = {rid: set() for rid in nodes}
        indegree = {rid: 0 for rid in nodes}
        for source_id, refs in requirements.items():
            for requirement in refs:
                if requirement.external:
                    continue
                target = requirement.ref["record_id"]
                if target == source_id:
                    fail("self reference in HSC root")
                if target not in nodes:
                    fail("unresolved internal reference in HSC root")
                if source_id not in outgoing[target]:
                    outgoing[target].add(source_id)
                    indegree[source_id] += 1
        # Inventory membership is an explicit target-before-terminal edge.
        for member_id in self.by_id:
            if root_id not in outgoing[member_id]:
                outgoing[member_id].add(root_id)
                indegree[root_id] += 1
        def key(rid: str) -> tuple[bytes, str]:
            return (nodes[rid]["schema_version"].encode("utf-8"), rid)
        ready = sorted((rid for rid, degree in indegree.items() if degree == 0),
                       key=key)
        order: list[str] = []
        while ready:
            rid = ready.pop(0)
            order.append(rid)
            for child in sorted(outgoing[rid], key=key):
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
                    ready.sort(key=key)
        if len(order) != len(nodes):
            fail("HSC record graph contains a cycle")
        if order[-1] != root_id:
            fail("evidence root is not the final construction record")
        ordinals = {rid: index for index, rid in enumerate(order)}
        return order, ordinals

    def _validate_contracts_and_graph(self, program: Mapping[str, Any]) -> None:
        pp = program["payload"]
        declarations = {row["section_id"]: row
                        for row in pp["section_declarations"]}
        contracts = [record for record in self.records
                     if record["schema_version"] == "section_contract.v1"]
        by_section: dict[str, dict] = {}
        for contract in contracts:
            cp = contract["payload"]
            sid = cp["section_id"]
            if sid in by_section or sid not in declarations:
                fail("contract section is duplicate or absent from program")
            by_section[sid] = contract
            declaration = declarations[sid]
            if (cp["planned_request_id"], cp["base_commit"]) != \
                    (pp["planned_request_id"], pp["base_commit"]):
                fail("contract request/base differs from its program")
            _require_narrow_changes(declaration["predicted_changes"],
                                    cp["predicted_changes"],
                                    f"contract {sid}")
            if not set(_ref_ids(cp["read_inventory_refs"])) <= \
                    set(_ref_ids(declaration["read_inventory_refs"])):
                fail("contract widens its program read inventory")
            _require_budget_narrow(declaration["budget"], cp["budget"],
                                   f"contract {sid}")
        if set(by_section) != set(declarations):
            fail("program has a section without exactly one contract")
        for sid, contract in by_section.items():
            upstream = {self.get(ref, versions=("section_contract.v1",))
                        ["payload"]["section_id"]
                        for ref in contract["payload"]["upstream_contract_refs"]}
            if upstream != set(declarations[sid]["dependency_section_ids"]):
                fail("contract upstream refs do not equal program dependencies")
        graphs = [record for record in self.records
                  if record["schema_version"] == "section_work_graph.v1"]
        if len(graphs) != 1:
            fail("root must contain exactly one work graph")
        graph = graphs[0]
        gp = graph["payload"]
        if set(_ref_ids(gp["contract_refs"])) != {record_id(c) for c in contracts}:
            fail("work graph contract membership is incomplete")
        items = {item["work_item_id"]: item for item in gp["work_items"]}
        section_for_item: dict[str, str] = {}
        for item in items.values():
            contract = self.get(item["section_contract_ref"],
                                versions=("section_contract.v1",))
            cp = contract["payload"]
            section_for_item[item["work_item_id"]] = cp["section_id"]
            if item["operation"] not in cp["allowed_operations"]:
                fail("work item operation is not contract-authorized")
            _require_narrow_changes(cp["predicted_changes"],
                                    item["predicted_changes"], "work item")
            _require_budget_narrow(cp["budget"], item["budget"], "work item")
            if not set(_ref_ids(item["read_inventory_refs"])) <= \
                    set(_ref_ids(cp["read_inventory_refs"])):
                fail("work item widens its contract read inventory")
            allowed_interfaces = {
                row["interface_id"]: row
                for row in (cp["consumed_interfaces"] +
                            cp["exported_interfaces"])
            }
            for interface in item["shared_interfaces"]:
                if allowed_interfaces.get(interface["interface_id"]) != interface:
                    fail("work item changes an undeclared shared interface")
        for item in items.values():
            sid = section_for_item[item["work_item_id"]]
            allowed_sections = set(declarations[sid]["dependency_section_ids"]) | {sid}
            for dep in item["dependency_work_item_ids"]:
                if section_for_item[dep] not in allowed_sections:
                    fail("work item dependency crosses an undeclared section edge")

    def _validate_dispatches(self, program: Mapping[str, Any]) -> None:
        pp = program["payload"]
        registry = self.get(pp["principal_registry_ref"],
                            versions=("section_principal_registry.v1",))
        rp = registry["payload"]
        principals = {row["principal_id"]: row for row in rp["principals"]}
        auths = _records(self, "section_launcher_authorization.v1")
        assignments = _records(self, "section_assignment.v1")
        receipts = _records(self, "section_launcher_receipt.v1")
        graphs = _records(self, "section_work_graph.v1")
        graph_items = {} if not graphs else {
            item["work_item_id"]: item
            for item in graphs[0]["payload"]["work_items"]
        }
        for auth in auths:
            ap = auth["payload"]
            row = principals.get(ap["principal_id"])
            if row is None or row["allowed_role"] != ap["role"] or \
                    (row["authority_control_id"],
                     row["principal_credential_digest"]) != \
                    (ap["authority_control_id"],
                     ap["principal_credential_digest"]):
                fail("launcher authorization does not resolve to its registry principal")
            if ap["scheduler_authority_id"] != rp["scheduler_authority_id"] or \
                    ap["principal_registry_ref"] != record_ref(registry):
                fail("launcher authorization registry authority mismatch")
            item = graph_items.get(ap["work_item_id"])
            if item is None or item["section_contract_ref"] != ap["contract_ref"]:
                fail("launcher authorization is outside the frozen work graph")
            profile = self.get(ap["sandbox_profile_ref"],
                               versions=("worker_sandbox_profile.v1",))
            if profile["payload"]["launcher_binary_sha256"] != \
                    ap["launcher_executable_sha256"]:
                fail("authorization launcher differs from sandbox profile")
        for assignment in assignments:
            sp = assignment["payload"]
            auth = self.get(sp["launcher_authorization_ref"],
                            versions=("section_launcher_authorization.v1",))
            _require_repeated_dispatch(auth["payload"], sp,
                                       omit={"launcher_executable_sha256",
                                             "contract_ref",
                                             "principal_registry_ref"})
            if sp["contract_ref"] != auth["payload"]["contract_ref"] or \
                    sp["principal_registry_ref"] != \
                    auth["payload"]["principal_registry_ref"]:
                fail("assignment changed authorization contract or registry")
        for receipt in receipts:
            rp_receipt = receipt["payload"]
            auth = self.get(rp_receipt["authorization_ref"],
                            versions=("section_launcher_authorization.v1",))
            assignment = self.get(rp_receipt["assignment_ref"],
                                  versions=("section_assignment.v1",))
            _require_repeated_dispatch(auth["payload"], rp_receipt,
                                       omit={"contract_ref", "work_item_id",
                                             "principal_registry_ref"})
            _require_repeated_dispatch(assignment["payload"], rp_receipt,
                                       omit={"contract_ref", "work_item_id",
                                             "principal_registry_ref",
                                             "launcher_authorization_ref",
                                             "launcher_executable_sha256"})
            if assignment["payload"]["launcher_authorization_ref"] != record_ref(auth):
                fail("receipt assignment does not point at receipt authorization")
        self._validate_journal_chain(registry, auths, assignments, receipts)

    def _validate_contexts(self, program: Mapping[str, Any]) -> None:
        graphs = _records(self, "section_work_graph.v1")
        if len(graphs) != 1:
            return
        items = {item["work_item_id"]: item
                 for item in graphs[0]["payload"]["work_items"]}
        contexts = {record_id(record): record
                    for record in _records(self, "section_context_bundle.v1")}
        used: set[str] = set()
        for assignment in _records(self, "section_assignment.v1"):
            ap = assignment["payload"]
            context = self.get(ap["context_ref"],
                               versions=("section_context_bundle.v1",))
            context_id = record_id(context)
            if context_id not in contexts:
                fail("dispatch context is missing from the evidence root")
            used.add(context_id)
            cp = context["payload"]
            item = items.get(ap["work_item_id"])
            if item is None or item["section_contract_ref"] != ap["contract_ref"]:
                fail("assignment is outside the frozen work graph")
            if (cp["program_ref"], cp["contract_ref"], cp["work_item_id"],
                cp["base_commit"], cp["role"]) != \
                    (record_ref(program), ap["contract_ref"],
                     ap["work_item_id"], program["payload"]["base_commit"],
                     ap["role"]):
                fail("dispatch context does not bind its exact assignment")
        if used != set(contexts):
            fail("unassigned context bundle is present in the evidence root")

    def _validate_journal_chain(self, registry: Mapping[str, Any],
                                auths: list[dict], assignments: list[dict],
                                receipts: list[dict]) -> None:
        manifests = _records(self, "section_scheduler_journal_manifest.v1")
        if not (auths or assignments or receipts or manifests):
            return
        if not manifests:
            fail("dispatch records exist without a typed journal manifest")
        by_id = {record_id(manifest): manifest for manifest in manifests}
        successors: dict[str, list[str]] = {}
        heads = []
        seen_dispatch: set[str] = set()
        registry_payload = registry["payload"]
        journal_identity = None
        for manifest in manifests:
            mp = manifest["payload"]
            predecessor = mp["predecessor_journal_manifest_ref"]
            if predecessor is None:
                heads.append(manifest)
            else:
                predecessor_id = predecessor["record_id"]
                successors.setdefault(predecessor_id, []).append(record_id(manifest))
                pred = self.get(predecessor,
                                versions=("section_scheduler_journal_manifest.v1",))
                if mp["first_sequence"] != pred["payload"]["last_sequence"] + 1:
                    fail("journal predecessor sequence is not contiguous")
            identity = tuple(mp[field] for field in (
                "journal_root_id", "journal_root_locator_sha256",
                "journal_root_filesystem_id", "journal_root_file_id",
                "journal_owner_principal_id", "journal_owner_control_id",
                "journal_mode", "scheduler_authority_id"))
            if journal_identity is None:
                journal_identity = identity
            elif journal_identity != identity:
                fail("journal root identity changes within one chain")
            if mp["scheduler_authority_id"] != \
                    registry_payload["scheduler_authority_id"] or \
                    (mp["journal_owner_principal_id"],
                     mp["journal_owner_control_id"]) != \
                    (registry_payload["scheduler_writer_principal_id"],
                     registry_payload["scheduler_writer_control_id"]):
                fail("journal protected writer identity mismatch")
            for index, entry in enumerate(mp["entries"]):
                target = self.get(entry["record_ref"])
                tp = target["payload"]
                if entry["record_ref"]["record_id"] in seen_dispatch:
                    fail("dispatch record occurs more than once in journal")
                seen_dispatch.add(entry["record_ref"]["record_id"])
                if entry["sequence"] != tp["scheduler_journal_sequence"] or \
                        entry["entry_sha256"] != tp["scheduler_journal_entry_sha256"]:
                    fail("journal entry does not bind dispatch record")
                writer = (registry_payload["scheduler_writer_principal_id"],
                          registry_payload["scheduler_writer_control_id"]) \
                    if index < 2 else \
                    (registry_payload["launcher_writer_principal_id"],
                     registry_payload["launcher_writer_control_id"])
                if (entry["writer_principal_id"], entry["writer_control_id"]) \
                        != writer:
                    fail("journal entry writer substitution")
            auth = self.get(mp["entries"][0]["record_ref"])["payload"]
            assignment = self.get(mp["entries"][1]["record_ref"])["payload"]
            receipt = self.get(mp["entries"][2]["record_ref"])["payload"]
            _require_repeated_dispatch(auth, assignment,
                                       omit={"launcher_executable_sha256",
                                             "contract_ref",
                                             "principal_registry_ref"})
            _require_repeated_dispatch(auth, receipt,
                                       omit={"contract_ref", "work_item_id",
                                             "principal_registry_ref"})
        if len(heads) != 1 or any(len(children) != 1
                                  for children in successors.values()):
            fail("journal manifests do not form one unbroken unforked chain")
        all_dispatch = {record_id(record) for record in auths + assignments + receipts}
        if seen_dispatch != all_dispatch:
            fail("journal membership omits or adds a dispatch record")

    def _validate_native_plans(self, program: Mapping[str, Any]) -> None:
        """Close dispatch-plan membership and the assembly union.

        A locally valid plan proves only its own shape.  The complete root must
        additionally prove that there is one plan for every journaled dispatch,
        no unused plan, one assembly plan, byte-identical central descriptors,
        and an assembly root set equal to the normalized union.
        """
        plans = _records(self, "section_native_inventory_plan.v1")
        profiles = _records(self, "worker_sandbox_profile.v1")
        assignments = _records(self, "section_assignment.v1")
        if not plans:
            fail("complete HSC evidence lacks native inventory plans")
        assembly = [plan for plan in plans
                    if plan["payload"]["scope"] == "assembly"]
        dispatch = [plan for plan in plans
                    if plan["payload"]["scope"] != "assembly"]
        if len(assembly) != 1:
            fail("evidence root requires exactly one native assembly plan")

        pp = program["payload"]
        for plan in plans:
            if plan["payload"]["base_commit"] != pp["base_commit"]:
                fail("native plan base commit differs from its program")

        dispatch_by_key: dict[tuple[str, str, int], dict] = {}
        for plan in dispatch:
            payload = plan["payload"]
            key = (payload["work_item_id"], payload["role"],
                   payload["attempt"])
            if key in dispatch_by_key:
                fail("multiple native plans claim one dispatch attempt")
            dispatch_by_key[key] = plan

        assignment_by_key: dict[tuple[str, str, int], dict] = {}
        for assignment in assignments:
            payload = assignment["payload"]
            key = (payload["work_item_id"], payload["role"],
                   payload["attempt"])
            if key in assignment_by_key:
                fail("multiple assignments claim one dispatch attempt")
            assignment_by_key[key] = assignment
        if set(dispatch_by_key) != set(assignment_by_key):
            fail("native dispatch plans do not exactly match journaled dispatches")

        profile_ids = {record_id(profile) for profile in profiles}
        used_profiles: set[str] = set()
        used_plan_ids: set[str] = set()
        for key, assignment in assignment_by_key.items():
            ap = assignment["payload"]
            profile = self.get(ap["sandbox_profile_ref"],
                               versions=("worker_sandbox_profile.v1",))
            profile_id = record_id(profile)
            if profile_id not in profile_ids or profile_id in used_profiles:
                fail("sandbox profile is missing, extra, or reused by a dispatch")
            used_profiles.add(profile_id)
            plan = self.get(profile["payload"]["native_inventory_plan_ref"],
                            versions=("section_native_inventory_plan.v1",))
            if record_id(plan) != record_id(dispatch_by_key[key]):
                fail("dispatch profile does not reference its unique native plan")
            if plan["payload"]["workspace_id"] != ap["workspace_id"]:
                fail("dispatch plan workspace differs from its assignment")
            used_plan_ids.add(record_id(plan))
        if used_profiles != profile_ids or \
                used_plan_ids != {record_id(plan) for plan in dispatch}:
            fail("unused sandbox profile or native dispatch plan")

        central_kinds = {
            "candidate", "integration-checkout", "common-git", "council-root",
            "owner-anchors", "other-worker-leaves", "canonical-evidence",
            "hidden-suites",
        }
        central: dict[str, dict] = {}
        union_by_id: dict[str, dict] = {}
        for plan in dispatch:
            for root in plan["payload"]["roots"]:
                root_id = root["root_id"]
                prior = union_by_id.get(root_id)
                if prior is not None and prior != root:
                    fail("one native root id has conflicting descriptors")
                union_by_id[root_id] = root
                if root["root_kind"] in central_kinds:
                    previous = central.get(root["root_kind"])
                    if previous is not None and previous != root:
                        fail("central native root descriptor differs across plans")
                    central[root["root_kind"]] = root
        if set(central) != central_kinds:
            fail("dispatch plans do not share the complete central root set")

        output_owners: dict[str, tuple[str, str, int]] = {}
        for key, plan in dispatch_by_key.items():
            payload = plan["payload"]
            expected_kind = f"{payload['role']}-output"
            output = [root for root in payload["roots"]
                      if root["root_kind"] == expected_kind]
            runtime = [root for root in payload["roots"]
                       if root["root_kind"] == "runtime-readonly"]
            if len(output) != 1 or len(runtime) != 1:
                fail("dispatch plan must contain one exact runtime and output")
            workspace = payload["workspace_id"]
            if output[0]["workspace_id"] != workspace or \
                    runtime[0]["workspace_id"] != workspace:
                fail("dispatch runtime/output does not bind its workspace")
            prior = output_owners.get(output[0]["root_id"])
            if prior is not None and prior != key:
                fail("private output root is shared by two dispatches")
            output_owners[output[0]["root_id"]] = key

        assembly_roots = {root["root_id"]: root
                          for root in assembly[0]["payload"]["roots"]}
        if assembly_roots != union_by_id:
            fail("assembly native roots are not the exact dispatch-root union")

    def _validate_native_inventories(self) -> None:
        plans = _records(self, "section_native_inventory_plan.v1")
        inventories = _records(self, "section_native_inventory.v1")
        if not plans and not inventories:
            return
        requirements: dict[tuple[str, str], tuple[dict, dict]] = {}
        observed: dict[tuple[str, str, str], dict] = {}
        for plan in plans:
            pp = plan["payload"]
            roots = {row["root_id"]: row for row in pp["roots"]}
            checkout = next(row for row in pp["roots"]
                            if row["root_kind"] == "integration-checkout")
            common_git = next(row for row in pp["roots"]
                              if row["root_kind"] == "common-git")
            if checkout["view_kind"] != \
                    "checkout-excluding-delegated-dotgit-v1" or \
                    common_git["view_kind"] != "full-native-tree-v1" or \
                    checkout["delegated_control_root_id"] != common_git["root_id"] or \
                    checkout["delegated_control_identity"] != \
                    common_git["native_identity"]:
                fail("checkout/common-Git delegated view relation mismatch")
            expected_locator = dict(checkout["locator"])
            expected_locator["segments_hex"] = (
                list(expected_locator["segments_hex"]) + ["2e676974"])
            if common_git["locator"] != expected_locator:
                fail("common-Git locator is not checkout locator plus .git")
            for requirement in pp["observations"]:
                key = (record_id(plan), requirement["observation_id"])
                requirements[key] = (requirement, roots[requirement["root_id"]])
        seen: set[tuple[str, str]] = set()
        native_objects: dict[tuple[str, str], tuple[str, tuple[bytes, ...]]] = {}
        for inventory in inventories:
            ip = inventory["payload"]
            plan = self.get(ip["native_inventory_plan_ref"],
                            versions=("section_native_inventory_plan.v1",))
            key = (record_id(plan), ip["observation_id"])
            if key in seen or key not in requirements:
                fail("native inventory duplicates or invents an observation")
            seen.add(key)
            requirement, root = requirements[key]
            observed[(record_id(plan), root["root_id"], ip["phase"])] = ip
            if ip["root_id"] != requirement["root_id"] or \
                    ip["phase"] != requirement["phase"] or \
                    ip["base_commit"] != plan["payload"]["base_commit"] or \
                    ip["observation_workspace_id"] != requirement["workspace_id"] or \
                    (ip["observed_root_filesystem_id"],
                     ip["observed_root_file_id"]) != \
                    (root["filesystem_id"], root["file_id"]):
                fail("native inventory does not equal its plan requirement/root")
            if requirement["scope"] == "assembly":
                if ip["observer_assignment_ref"] is not None:
                    fail("assembly inventory must have null observer assignment")
            else:
                assignment = self.get(ip["observer_assignment_ref"],
                                      versions=("section_assignment.v1",))
                ap = assignment["payload"]
                if (ap["work_item_id"], ap["role"], ap["attempt"],
                    ap["workspace_id"]) != \
                        (requirement["work_item_id"], requirement["role"],
                         requirement["attempt"], requirement["workspace_id"]):
                    fail("native inventory observer assignment mismatch")
            expected_hash = domain_hash(
                "council:section-native-inventory-content:v1", {
                    "native_inventory_plan_ref": ip["native_inventory_plan_ref"],
                    "root_spec": root,
                    "observation_requirement": requirement,
                    "observer_assignment_ref": ip["observer_assignment_ref"],
                    "observation_workspace_id": ip["observation_workspace_id"],
                    "phase": ip["phase"],
                    "entries": ip["entries"],
                })
            if ip["inventory_sha256"] != expected_hash:
                fail("native inventory content hash mismatch")
            if root["root_kind"] in ("candidate", "builder-output",
                                     "assessor-output") and any(
                    entry["path"]["segments_hex"] and
                    entry["path"]["segments_hex"][0] == "2e676974"
                    for entry in ip["entries"]):
                fail("full-tree candidate/output inventory contains .git")
            if root["root_kind"] == "integration-checkout" and any(
                    entry["path"]["segments_hex"] and
                    entry["path"]["segments_hex"][0] == "2e676974"
                    for entry in ip["entries"]):
                fail("checkout inventory did not exclude delegated .git")
            root_object = (root["filesystem_id"], root["file_id"])
            _claim_native_object(native_objects, root_object,
                                 root["root_id"], ())
            for entry in ip["entries"]:
                decoded = tuple(bytes.fromhex(item)
                                for item in entry["path"]["segments_hex"])
                _claim_native_object(native_objects,
                                     (entry["filesystem_id"], entry["file_id"]),
                                     root["root_id"], decoded)
        if seen != set(requirements):
            fail("native inventory omits a required observation")
        inventory_root_ids = {
            root["root_id"] for plan in plans for root in plan["payload"]["roots"]
        }
        for manifest in _records(
                self, "section_scheduler_journal_manifest.v1"):
            mp = manifest["payload"]
            if mp["journal_root_id"] in inventory_root_ids:
                fail("scheduler journal anchor aliases an inventory root id")
            _claim_native_object(
                native_objects,
                (mp["journal_root_filesystem_id"], mp["journal_root_file_id"]),
                "journal:" + mp["journal_root_id"], ())
        for plan in plans:
            pp = plan["payload"]
            phases = (("pre-assembly", "post-assembly")
                      if pp["scope"] == "assembly"
                      else ("pre-dispatch", "post-worker"))
            mutable_kind = ("candidate" if pp["scope"] == "assembly"
                            else f"{pp['role']}-output")
            for root in pp["roots"]:
                before = observed[(record_id(plan), root["root_id"], phases[0])]
                after = observed[(record_id(plan), root["root_id"], phases[1])]
                if root["root_kind"] != mutable_kind and \
                        before["entries"] != after["entries"]:
                    fail("protected native root changed across its observation pair")

    def _validate_attestations(self) -> None:
        for attestation in _records(self, "worker_sandbox_attestation.v1"):
            ap = attestation["payload"]
            assignment = self.get(ap["assignment_ref"],
                                  versions=("section_assignment.v1",))
            receipt = self.get(ap["launcher_receipt_ref"],
                               versions=("section_launcher_receipt.v1",))
            manifest = self.get(ap["journal_manifest_ref"], versions=(
                "section_scheduler_journal_manifest.v1",))
            profile = self.get(ap["sandbox_profile_ref"],
                               versions=("worker_sandbox_profile.v1",))
            if receipt["payload"]["barrier_status"] != "ready" or \
                    receipt["payload"]["assignment_ref"] != record_ref(assignment) or \
                    manifest["payload"]["entries"][2]["record_ref"] != \
                    record_ref(receipt) or assignment["payload"]["sandbox_profile_ref"] \
                    != record_ref(profile):
                fail("sandbox attestation lacks an eligible exact dispatch")
            plan = self.get(profile["payload"]["native_inventory_plan_ref"],
                            versions=("section_native_inventory_plan.v1",))
            pp, sp = plan["payload"], assignment["payload"]
            if (pp["work_item_id"], pp["role"], pp["attempt"],
                pp["workspace_id"]) != \
                    (sp["work_item_id"], sp["role"], sp["attempt"],
                     sp["workspace_id"]):
                fail("sandbox profile native plan does not match assignment")
            if ap["source_snapshot_ref"] != profile["payload"]["source_snapshot_ref"]:
                fail("attestation source snapshot differs from sandbox profile")
            expected_before = {row["observation_id"] for row in pp["observations"]
                               if row["phase"] == "pre-dispatch"}
            expected_after = {row["observation_id"] for row in pp["observations"]
                              if row["phase"] == "post-worker"}
            before = {self.get(ref, versions=("section_native_inventory.v1",))
                      ["payload"]["observation_id"]
                      for ref in ap["native_inventory_before_refs"]}
            after = {self.get(ref, versions=("section_native_inventory.v1",))
                     ["payload"]["observation_id"]
                     for ref in ap["native_inventory_after_refs"]}
            if before != expected_before or after != expected_after:
                fail("attestation native inventory membership is incomplete")
            output_inventory = self.get(
                ap["output_inventory_ref"],
                versions=("section_content_record.v1",),
                artifacts=("read_inventory",))
            self._require_exhaustive_output_inventory(
                output_inventory, ap["assignment_ref"])  # bijection only

    def _require_exhaustive_output_inventory(
            self, inventory_record: Mapping[str, Any],
            assignment_ref: Mapping[str, str]) \
            -> tuple[set[str], dict[str, dict]]:
        """An output inventory is never opaque: it is dispatch-owned, closed
        canonical JSON, and an exact no-extra/no-omission bijection with every
        other content record owned by the same assignment.

        The binding uses the FULL content-namespace-relative path (the part
        after ``/content/``), never a basename, so a row relocated to
        ``moved/<name>`` cannot alias ``<name>``. Each row's byte length and
        blob hash must equal exactly one owned sealed content record's."""
        ip = inventory_record["payload"]
        if ip["producer_assignment_ref"] != assignment_ref:
            fail("output inventory is not owned by its dispatch assignment")
        value = self.closed_values.get(record_id(inventory_record))
        if value is None:
            fail("output inventory bytes were not closed JSON")
        rows = _closed_output_inventory(value)
        by_path: dict[str, dict] = {}
        for row in rows:
            if row["output_relpath"] in by_path:
                fail("output inventory repeats an output path")
            by_path[row["output_relpath"]] = row
        owned = [record for record in _records(self, "section_content_record.v1")
                 if record["payload"]["producer_assignment_ref"] ==
                 assignment_ref and
                 record_id(record) != record_id(inventory_record)]
        record_by_path: dict[str, dict] = {}
        for record in owned:
            tail = _content_tail(record["payload"]["storage_relpath"])
            if tail in record_by_path:
                fail("two owned outputs share a content path")
            record_by_path[tail] = record
        if set(by_path) != set(record_by_path):
            fail("output inventory omits, misdescribes, or lists a non-owned "
                 "output")
        for tail, record in record_by_path.items():
            row = by_path[tail]
            payload = record["payload"]
            if (row["byte_length"], row["blob_sha256"]) != \
                    (payload["byte_length"], payload["blob_sha256"]):
                fail("output inventory row bytes differ from the sealed "
                     "content record at that path")
        return set(by_path), record_by_path

    def _validate_assessments(self, root: Mapping[str, Any]) -> None:
        inventory_paths = {row["record_id"]: row["repository_relpath"]
                           for row in root["payload"]["record_inventory"]}
        findings = {record_id(record): record
                    for record in _records(self, "section_finding.v1")}
        for finding in findings.values():
            fp = finding["payload"]
            declaration_record = self.get(
                fp["finding_declaration_ref"],
                versions=("section_content_record.v1",),
                artifacts=("finding_declaration",))
            declaration = self.closed_values.get(record_id(declaration_record))
            if declaration is None:
                fail("finding declaration bytes were not closed JSON")
            mapping = {
                "audit_level": "audit_level", "severity": "severity",
                "invariant_id": "invariant_id", "claim": "claim",
                "affected_path": "affected_path",
                "blocks_local_pass": "blocks_local_pass", "status": "status",
            }
            for output_field, declared_field in mapping.items():
                if fp[output_field] != declaration[declared_field]:
                    fail("packaged finding changes assessor declaration judgment")
            if fp["predecessor_finding_ref"] != \
                    declaration["predecessor_finding_ref"]:
                fail("packaged finding changes predecessor lineage")
        assessments = _records(self, "section_assessment_manifest.v1")
        for assessment in assessments:
            ap = assessment["payload"]
            contract = self.get(ap["contract_ref"],
                                versions=("section_contract.v1",))
            assignment = self.get(ap["assessor_assignment_ref"],
                                  versions=("section_assignment.v1",))
            context = self.get(ap["assessor_context_ref"],
                               versions=("section_context_bundle.v1",))
            proposal = self.get(ap["proposal_ref"],
                                versions=("section_content_record.v1",),
                                artifacts=("proposal",))
            asp, ctp = assignment["payload"], context["payload"]
            if asp["role"] != "assessor" or \
                    (asp["contract_ref"], asp["work_item_id"],
                     asp["context_ref"]) != \
                    (ap["contract_ref"], ap["work_item_id"],
                     ap["assessor_context_ref"]) or \
                    (ctp["role"], ctp["contract_ref"], ctp["work_item_id"],
                     ctp["proposal_ref"]) != \
                    ("assessor", ap["contract_ref"], ap["work_item_id"],
                     ap["proposal_ref"]):
                fail("assessment does not bind its exact assessor dispatch")
            declaration_record = self.get(
                ap["assessment_declaration_ref"],
                versions=("section_content_record.v1",),
                artifacts=("assessment_declaration",))
            if declaration_record["payload"]["producer_assignment_ref"] != \
                    ap["assessor_assignment_ref"]:
                fail("assessment declaration is not assessor-owned")
            declaration = self.closed_values.get(record_id(declaration_record))
            if declaration is None:
                fail("assessment declaration bytes were not closed JSON")
            exact_fields = {
                "program_ref": ap["program_ref"],
                "contract_ref": ap["contract_ref"],
                "work_item_id": ap["work_item_id"],
                "assessor_assignment_ref": ap["assessor_assignment_ref"],
                "assessor_context_ref": ap["assessor_context_ref"],
                "proposal_ref": ap["proposal_ref"],
                "predecessor_assessment_ref": ap["predecessor_assessment_ref"],
                "declared_disposition": ap["local_assessment"],
                "error_reason": ap["error_reason"],
            }
            for field, value in exact_fields.items():
                if declaration[field] != value:
                    fail("assessment manifest changes its sealed declaration")
            inventory_record = self.get(
                ap["assessor_output_inventory_ref"],
                versions=("section_content_record.v1",),
                artifacts=("read_inventory",))
            output_paths, record_by_output_path = \
                self._require_exhaustive_output_inventory(
                    inventory_record, ap["assessor_assignment_ref"])
            check_declarations = []
            for ref in ap["check_declaration_refs"]:
                record = self.get(ref, versions=("section_content_record.v1",),
                                  artifacts=("check_declaration",))
                if record["payload"]["producer_assignment_ref"] != \
                        ap["assessor_assignment_ref"]:
                    fail("check declaration is not assessor-owned")
                check_declarations.append(self.closed_values[record_id(record)])
            declared_check_paths = declaration["check_declaration_output_relpaths"]
            # Each declared path (full leaf-relative) must resolve, through the
            # exhaustive inventory, to exactly the referenced sealed record.
            if {_content_tail(self.get(ref)["payload"]["storage_relpath"])
                for ref in ap["check_declaration_refs"]} != \
                    set(declared_check_paths) or \
                    not set(declared_check_paths) <= output_paths:
                fail("assessment check declarations differ from sealed membership")
            for path in declared_check_paths:
                if record_id(record_by_output_path[path]) not in {
                        record_id(self.get(ref))
                        for ref in ap["check_declaration_refs"]}:
                    fail("declared check path does not map to its sealed record")
            declared_by_id = {row["check_id"]: row for row in check_declarations}
            result_by_id = {row["check_id"]: row for row in ap["check_results"]}
            if set(declared_by_id) != set(result_by_id):
                fail("assessment check result membership mismatch")
            for check_id, result in result_by_id.items():
                if result["status"] != declared_by_id[check_id]["status"]:
                    fail("assessment changes a declared check status")
                evidence = self.get(result["evidence_ref"],
                                    versions=("section_content_record.v1",),
                                    artifacts=("check_evidence",))
                declared_path = declared_by_id[check_id][
                    "evidence_output_relpath"]
                if evidence["payload"]["producer_assignment_ref"] != \
                        ap["assessor_assignment_ref"] or \
                        _content_tail(evidence["payload"]["storage_relpath"]) \
                        != declared_path:
                    fail("check evidence does not map to assessor declaration")
            finding_records = [self.get(ref, versions=("section_finding.v1",))
                               for ref in ap["finding_refs"]]
            declared_finding_paths = declaration[
                "finding_declaration_output_relpaths"]
            actual_finding_paths = [_content_tail(self.get(
                finding["payload"]["finding_declaration_ref"],
                versions=("section_content_record.v1",),
                artifacts=("finding_declaration",))["payload"][
                    "storage_relpath"]) for finding in finding_records]
            if set(actual_finding_paths) != set(declared_finding_paths) or \
                    not set(declared_finding_paths) <= output_paths:
                fail("assessment finding declarations differ from sealed membership")
            for finding in finding_records:
                fp = finding["payload"]
                declaration_content = self.get(
                    fp["finding_declaration_ref"],
                    versions=("section_content_record.v1",),
                    artifacts=("finding_declaration",))
                if (fp["contract_ref"], fp["assessor_assignment_ref"],
                    fp["affected_proposal_ref"]) != \
                        (ap["contract_ref"], ap["assessor_assignment_ref"],
                         ap["proposal_ref"]) or \
                        declaration_content["payload"][
                            "producer_assignment_ref"] != \
                        ap["assessor_assignment_ref"]:
                    fail("finding is not owned by the exact assessment dispatch")
                # The declared evidence/reproduction/resolution output paths in
                # the closed finding declaration must equal the full content
                # tails of the packaged finding's exact typed refs, and each
                # referenced record must be the same assessor-owned sealed
                # record the exhaustive inventory maps that path to. Path and
                # ref cannot disagree.
                closed = self.closed_values.get(record_id(declaration_content))
                if closed is None:
                    fail("finding declaration bytes were not closed JSON")
                declared_to_ref = [
                    (closed["evidence_output_relpath"], fp["evidence_ref"],
                     ("finding_evidence",)),
                    (closed["reproduction_output_relpath"],
                     fp["reproduction_ref"], ("reproduction",)),
                ]
                if closed["resolution_output_relpath"] is not None:
                    declared_to_ref.append(
                        (closed["resolution_output_relpath"],
                         fp["resolution_evidence_ref"], ("resolution",)))
                elif fp["resolution_evidence_ref"] is not None:
                    fail("finding resolution ref present without a declared "
                         "resolution path")
                for declared_path, ref, artifacts in declared_to_ref:
                    referenced = self.get(
                        ref, versions=("section_content_record.v1",),
                        artifacts=artifacts)
                    if referenced["payload"]["producer_assignment_ref"] != \
                            ap["assessor_assignment_ref"] or \
                            _content_tail(referenced["payload"][
                                "storage_relpath"]) != declared_path or \
                            declared_path not in output_paths or \
                            record_id(record_by_output_path[declared_path]) != \
                            record_id(referenced):
                        fail("finding declaration path does not bind its exact "
                             "sealed evidence record")
            tuples = sorted(({
                "record_relpath": inventory_paths[record_id(finding)],
                "record_id": record_id(finding),
                "content_sha256": compute_content_sha(finding),
            } for finding in finding_records),
                key=lambda row: row["record_relpath"])
            expected_inventory = domain_hash(
                "council:section-finding-inventory:v1", tuples)
            if ap["finding_inventory_sha256"] != expected_inventory or \
                    ap["finding_count"] != len(finding_records):
                fail("assessment finding inventory is incomplete")
            open_blockers = sum(
                1 for finding in finding_records
                if finding["payload"]["status"] == "open" and
                finding["payload"]["blocks_local_pass"])
            if ap["open_blocking_count"] != open_blockers:
                fail("assessment open blocking count mismatch")
            required_checks = set(contract["payload"]["required_check_ids"])
            if set(result_by_id) != required_checks:
                fail("assessment is missing or adds contract-required checks")
            declared_output_paths = list(
                declaration["check_declaration_output_relpaths"]) + list(
                declaration["finding_declaration_output_relpaths"]) + [
                row["evidence_output_relpath"] for row in check_declarations]
            for finding in finding_records:
                closed = self.closed_values.get(record_id(self.get(
                    finding["payload"]["finding_declaration_ref"],
                    versions=("section_content_record.v1",),
                    artifacts=("finding_declaration",))))
                if closed is None:
                    fail("finding declaration bytes were not closed JSON")
                declared_output_paths.append(closed["evidence_output_relpath"])
                declared_output_paths.append(
                    closed["reproduction_output_relpath"])
                if closed["resolution_output_relpath"] is not None:
                    declared_output_paths.append(
                        closed["resolution_output_relpath"])
            # Every declared assessor output path (full leaf-relative) must be
            # present in the exhaustive inventory — no basename aliasing.
            for path in declared_output_paths:
                if path not in output_paths:
                    fail("declared assessor output path is absent from the "
                         "exhaustive output inventory")
            statuses = {row["status"] for row in ap["check_results"]}
            if "error" in statuses and ap["error_reason"] is None:
                fail("an errored check requires a sealed error reason")
            expected_disposition = "error" if ap["error_reason"] is not None \
                else "blocked" if "fail" in statuses or open_blockers \
                else "pass"
            if ap["local_assessment"] != expected_disposition:
                fail("assessment disposition is not deterministically derived")
            predecessor = ap["predecessor_assessment_ref"]
            if predecessor is not None:
                prior = self.get(predecessor,
                                 versions=("section_assessment_manifest.v1",))
                prior_findings = set(_ref_ids(prior["payload"]["finding_refs"]))
                carried = set()
                for finding in finding_records:
                    fpred = finding["payload"]["predecessor_finding_ref"]
                    carried.add(fpred["record_id"] if fpred else record_id(finding))
                if not prior_findings <= carried:
                    fail("reassessment drops a predecessor finding")

    def _validate_bundles(self) -> None:
        graphs = _records(self, "section_work_graph.v1")
        graph_items = {} if not graphs else {
            item["work_item_id"]: item
            for item in graphs[0]["payload"]["work_items"]
        }
        bundles = _records(self, "section_evidence_bundle.v1")
        bundle_by_item: dict[str, dict] = {}
        for bundle in bundles:
            bp = bundle["payload"]
            if bp["work_item_id"] in bundle_by_item:
                fail("work item has more than one terminal evidence bundle")
            bundle_by_item[bp["work_item_id"]] = bundle
            item = graph_items.get(bp["work_item_id"])
            if item is None or item["section_contract_ref"] != bp["contract_ref"]:
                fail("evidence bundle is outside the frozen work graph")
            builder = self.get(bp["builder_assignment_ref"],
                               versions=("section_assignment.v1",))
            assessor = self.get(bp["assessor_assignment_ref"],
                                versions=("section_assignment.v1",))
            bpa, apa = builder["payload"], assessor["payload"]
            if bpa["role"] != "builder" or apa["role"] != "assessor" or \
                    bpa["work_item_id"] != bp["work_item_id"] or \
                    apa["work_item_id"] != bp["work_item_id"] or \
                    bpa["contract_ref"] != bp["contract_ref"] or \
                    apa["contract_ref"] != bp["contract_ref"]:
                fail("bundle assignment role/work-item mismatch")
            if bp["base_commit"] != self.get(
                    bp["contract_ref"], versions=("section_contract.v1",))[
                        "payload"]["base_commit"]:
                fail("bundle base commit differs from its contract")
            registry = self.get(bpa["principal_registry_ref"],
                                versions=("section_principal_registry.v1",))
            if apa["principal_registry_ref"] != record_ref(registry):
                fail("builder and assessor use different registries")
            rows = {row["principal_id"]: row
                    for row in registry["payload"]["principals"]}
            br, ar = rows[bpa["principal_id"]], rows[apa["principal_id"]]
            distinct = (
                bpa["principal_id"] != apa["principal_id"],
                bpa["authority_control_id"] != apa["authority_control_id"],
                br["authority_control_key_digest"] !=
                ar["authority_control_key_digest"],
                bpa["principal_credential_digest"] !=
                apa["principal_credential_digest"],
                bpa["session_nonce"] != apa["session_nonce"],
                bpa["workspace_id"] != apa["workspace_id"],
                bpa["output_leaf"] != apa["output_leaf"],
            )
            if not all(distinct):
                fail("builder and assessor are not structurally independent")
            for role in ("builder", "assessor"):
                receipt = self.get(bp[f"{role}_launcher_receipt_ref"],
                                   versions=("section_launcher_receipt.v1",))
                if receipt["payload"]["barrier_status"] != "ready":
                    fail("refused receipt cannot support an evidence bundle")
                if receipt["payload"]["assignment_ref"] != \
                        bp[f"{role}_assignment_ref"]:
                    fail("bundle receipt does not bind exact assignment")
                manifest = self.get(bp[f"{role}_journal_manifest_ref"],
                                    versions=(
                                        "section_scheduler_journal_manifest.v1",))
                if record_ref(receipt) != \
                        manifest["payload"]["entries"][2]["record_ref"]:
                    fail("bundle receipt is not the journal receipt slot")
                assignment_ref = bp[f"{role}_assignment_ref"]
                context_ref = bp[f"{role}_context_ref"]
                attestation = self.get(
                    bp[f"{role}_sandbox_attestation_ref"],
                    versions=("worker_sandbox_attestation.v1",))
                atp = attestation["payload"]
                if atp["assignment_ref"] != assignment_ref or \
                        atp["launcher_receipt_ref"] != \
                        bp[f"{role}_launcher_receipt_ref"] or \
                        atp["journal_manifest_ref"] != \
                        bp[f"{role}_journal_manifest_ref"]:
                    fail("bundle attestation does not bind its dispatch evidence")
                assignment = self.get(assignment_ref,
                                      versions=("section_assignment.v1",))
                if assignment["payload"]["context_ref"] != context_ref:
                    fail("bundle context differs from its assignment")
            assessment = self.get(bp["assessment_manifest_ref"],
                                  versions=("section_assessment_manifest.v1",))
            if (bp["local_assessment"], bp["error_reason"]) != \
                    (assessment["payload"]["local_assessment"],
                     assessment["payload"]["error_reason"]):
                fail("bundle changes assessor disposition")
            asp = assessment["payload"]
            if (asp["contract_ref"], asp["work_item_id"],
                asp["assessor_assignment_ref"], asp["assessor_context_ref"],
                asp["proposal_ref"]) != \
                    (bp["contract_ref"], bp["work_item_id"],
                     bp["assessor_assignment_ref"], bp["assessor_context_ref"],
                     bp["proposal_ref"]):
                fail("bundle assessment does not bind the bundle inputs")
            proposal = self.get(bp["proposal_ref"],
                                versions=("section_content_record.v1",),
                                artifacts=("proposal",))
            if proposal["payload"]["producer_assignment_ref"] != \
                    bp["builder_assignment_ref"]:
                fail("bundle proposal is not owned by its builder")
            contract = self.get(bp["contract_ref"],
                                versions=("section_contract.v1",))
            if {row["check_id"] for row in bp["invariant_results"]} != \
                    set(contract["payload"]["required_invariant_ids"]):
                fail("bundle invariant results do not equal contract requirements")
            invariant_statuses = {row["status"]
                                  for row in bp["invariant_results"]}
            if bp["local_assessment"] == "pass" and \
                    invariant_statuses != {"pass"}:
                fail("failed required invariant cannot coexist with a pass "
                     "bundle")
        if set(bundle_by_item) != set(graph_items):
            fail("complete evidence lacks exactly one bundle per work item")
        # §9 staleness inputs, as far as the HSC-A complete-root validator is
        # responsible: the bundle's stored ``staleness_input_refs`` must equal
        # the acyclic PRE-scope typed input closure (contract/program/
        # dependencies/work-graph/dispatch/assessment). The structural
        # POST-scope memberships are also checked here — boundary and final
        # scope must each reference exactly this bundle set (in their own
        # validators), and the candidate tree must equal base plus the final
        # scope's declared changes (_validate_candidate_tree).
        #
        # SCOPE BOUNDARY (design §15): binding each bundle to the exact final
        # IMPLEMENTATION bytes it assessed — invariant 8's post-assembly
        # recheck that "any byte change after an assessment makes that
        # assessment stale", i.e. reconstructing the assessed proposal and
        # rechecking each section's files against the final commit — is the
        # alias-safe atomic assembler + real-diff enforcement assigned to
        # Slice HSC-B, not HSC-A. HSC-A verifies the root is structurally
        # complete and that the committed tree matches the declared final
        # scope; it does not re-run the assembler. HSC-A therefore makes no
        # claim to detect a bundle reused over two different final section
        # byte-sets; that is caught by HSC-B's real-diff assembler.
        contract_ref_to_bundle = {
            bundle["payload"]["contract_ref"]["record_id"]: bundle
            for bundle in bundles}
        for bundle in bundles:
            bp = bundle["payload"]
            seed = self._bundle_staleness_seed(bp, contract_ref_to_bundle)
            expected_staleness = self._reference_closure(seed)
            expected_refs = sorted(
                ({"content_sha256": compute_content_sha(self.by_id[rid]),
                  "record_id": rid} for rid in expected_staleness),
                key=canonical_sort_key)
            if bp["staleness_input_refs"] != expected_refs:
                fail("bundle staleness inputs do not equal the reconstructed "
                     "acyclic pre-scope input closure (contract, program, "
                     "work graph, dependencies, dispatch, assessment)")

    def _bundle_staleness_seed(self, bundle_payload: Mapping[str, Any],
                               contract_ref_to_bundle: Mapping[str, Any]) \
            -> list[dict]:
        """Acyclic pre-scope staleness seed for one bundle: every reference
        the bundle carries, plus the frozen work graph, plus each upstream
        (dependency) section's contract and terminal evidence bundle. All are
        strictly earlier records, so no cycle is introduced."""
        seed = list(_bundle_seed_refs(bundle_payload))
        graphs = _records(self, "section_work_graph.v1")
        if graphs:
            seed.append(record_ref(graphs[0]))
        contract = self.get(bundle_payload["contract_ref"],
                            versions=("section_contract.v1",))
        for upstream_ref in contract["payload"]["upstream_contract_refs"]:
            seed.append(upstream_ref)
            upstream_bundle = contract_ref_to_bundle.get(
                upstream_ref["record_id"])
            if upstream_bundle is not None:
                seed.append(record_ref(upstream_bundle))
        return seed

    def _validate_final_scope(self, program: Mapping[str, Any],
                              root: Mapping[str, Any]) -> None:
        final_scope = self.get(root["payload"]["final_scope_ref"],
                               versions=("final_scope_manifest.v1",))
        fp = final_scope["payload"]
        pp = program["payload"]
        if fp["base_commit"] != pp["base_commit"] or \
                fp["work_graph_ref"] != root["payload"]["work_graph_ref"]:
            fail("final scope base commit or work graph mismatch")
        program_changes = [change for declaration in pp["section_declarations"]
                           for change in declaration["predicted_changes"]]
        program_changes.sort(key=change_sort_key)
        _require_narrow_changes(program_changes, fp["predicted_changes"],
                                "final scope")
        actual_by_key = {(change["path"], change["kind"],
                          change["rename_source"]): change
                         for change in fp["actual_changes"]}
        predicted_by_key = {(change["path"], change["kind"],
                             change["rename_source"]): change
                            for change in fp["predicted_changes"]}
        if not set(actual_by_key) <= set(predicted_by_key):
            fail("actual scope contains an unpredicted change")
        for key, actual in actual_by_key.items():
            if not predicted_matches_actual(predicted_by_key[key], actual):
                fail("actual change does not match its exact prediction")
        for key, predicted in predicted_by_key.items():
            if predicted["required"] and key not in actual_by_key:
                fail("required predicted change was not realized")
        prefix = f"artifacts/section-council/{pp['planned_request_id']}/"
        expected_envelopes = sorted((prefix + "final-scope.json",
                                     prefix + "root.json"))
        if fp["envelope_paths"] != expected_envelopes:
            fail("final scope envelope paths are not the fixed v1 paths")
        system_predictions = {change["path"]
                              for change in pp["system_artifact_predictions"]}
        realized = set(fp["realized_system_artifact_paths"])
        if not realized <= system_predictions:
            fail("realized system artifact path was not predeclared")
        project_paths = {change["path"] for change in fp["actual_changes"]}
        if realized & (project_paths | set(expected_envelopes)):
            fail("project, system, and envelope path domains overlap")
        bundles = {record_id(record)
                   for record in _records(self, "section_evidence_bundle.v1")}
        if set(_ref_ids(fp["section_bundle_refs"])) != bundles:
            fail("final scope omits or adds a section evidence bundle")

    def _validate_boundary_reports(self, program: Mapping[str, Any],
                                   root: Mapping[str, Any]) -> None:
        """Reconstruct every boundary semantic field deterministically.

        Frozen v1 derivations (each recomputed from the authenticated
        program, contracts, work graph, bundles, and final scope, then
        required to be exactly equal):

        - ``changed_section_ids``: sections owning at least one actual
          change (or rename source) in the final scope, via the program's
          exclusive path->section prediction ownership.
        - ``affected_contract_refs``: contracts of changed sections plus
          every section whose declared dependency closure contains a
          changed section (downstream dependents).
        - ``changed_interfaces``: the exported interfaces of every changed
          section's contract, merged by interface id with conflict refusal.
        - ``activated_check_results``: for every affected contract, the
          exact sealed check results of its section assessment restricted
          to that contract's required check ids, merged with conflict
          refusal and sorted by check id.
        - ``dependency_closure_ref``: closed canonical JSON equal to the
          recomputed work-graph transitive dependency closure.
        - ``required_system_audit_scope_ids``: changed sections plus every
          section owning a work item that requires the system audit level;
          if that union is empty, every section (the system audit always
          has a scope).
        """
        reports = _records(self, "boundary_impact_report.v1")
        if len(reports) != 1:
            fail("complete HSC evidence requires exactly one boundary report")
        report = reports[0]
        bp = report["payload"]
        if bp["work_graph_ref"] != root["payload"]["work_graph_ref"] or \
                bp["final_scope_ref"] != root["payload"]["final_scope_ref"]:
            fail("boundary report does not bind final graph and scope")
        bundles = _records(self, "section_evidence_bundle.v1")
        if set(_ref_ids(bp["section_bundle_refs"])) != \
                {record_id(record) for record in bundles}:
            fail("boundary report omits or adds a section bundle")
        if bp["unknown_classification_count"] != 0 or \
                bp["conflict_evidence_refs"]:
            fail("unknown or conflicting boundary classification blocks publication")

        pp = program["payload"]
        path_to_section: dict[str, str] = {}
        section_dependencies: dict[str, list[str]] = {}
        for declaration in pp["section_declarations"]:
            sid = declaration["section_id"]
            section_dependencies[sid] = list(
                declaration["dependency_section_ids"])
            for change in declaration["predicted_changes"]:
                path_to_section[change["path"]] = sid
                if change["rename_source"] is not None:
                    path_to_section[change["rename_source"]] = sid
        final_scope = self.get(root["payload"]["final_scope_ref"],
                               versions=("final_scope_manifest.v1",))
        changed: set[str] = set()
        for change in final_scope["payload"]["actual_changes"]:
            changed.add(path_to_section[change["path"]])
            if change["rename_source"] is not None:
                changed.add(path_to_section[change["rename_source"]])
        if bp["changed_section_ids"] != sorted(changed):
            fail("boundary changed_section_ids does not reconstruct from the "
                 "final scope")

        def prerequisites(sid: str, seen: set[str]) -> set[str]:
            result: set[str] = set()
            for dependency in section_dependencies[sid]:
                if dependency in seen:
                    continue
                seen.add(dependency)
                result.add(dependency)
                result |= prerequisites(dependency, seen)
            return result

        affected = set(changed)
        for sid in section_dependencies:
            if prerequisites(sid, set()) & changed:
                affected.add(sid)
        contracts_by_section = {
            record["payload"]["section_id"]: record
            for record in _records(self, "section_contract.v1")}
        expected_affected = sorted(
            (record_ref(contracts_by_section[sid]) for sid in affected),
            key=canonical_sort_key)
        if bp["affected_contract_refs"] != expected_affected:
            fail("boundary affected_contract_refs does not reconstruct from "
                 "the dependency graph")

        merged_interfaces: dict[str, dict] = {}
        for sid in sorted(changed):
            for interface in contracts_by_section[sid]["payload"][
                    "exported_interfaces"]:
                prior = merged_interfaces.get(interface["interface_id"])
                if prior is not None and prior != interface:
                    fail("changed sections export one interface id with two "
                         "identities")
                merged_interfaces[interface["interface_id"]] = interface
        expected_interfaces = sorted(
            merged_interfaces.values(),
            key=lambda row: row["interface_id"])
        if bp["changed_interfaces"] != expected_interfaces:
            fail("boundary changed_interfaces does not reconstruct from "
                 "changed section contracts")

        assessments_by_contract: dict[str, dict] = {}
        for bundle in bundles:
            assessment = self.get(
                bundle["payload"]["assessment_manifest_ref"],
                versions=("section_assessment_manifest.v1",))
            assessments_by_contract[
                bundle["payload"]["contract_ref"]["record_id"]] = assessment
        expected_rows: dict[str, dict] = {}
        for sid in sorted(affected):
            contract = contracts_by_section[sid]
            required = set(contract["payload"]["required_check_ids"])
            assessment = assessments_by_contract.get(record_id(contract))
            if assessment is None:
                fail("affected contract lacks a section assessment")
            for row in assessment["payload"]["check_results"]:
                if row["check_id"] not in required:
                    continue
                prior = expected_rows.get(row["check_id"])
                if prior is not None and prior != row:
                    fail("activated boundary check identity conflicts "
                         "across sections")
                expected_rows[row["check_id"]] = row
        expected_activated = sorted(expected_rows.values(),
                                    key=lambda row: row["check_id"])
        if bp["activated_check_results"] != expected_activated:
            fail("boundary activated_check_results does not reconstruct from "
                 "affected contract assessments")
        if any(result["status"] != "pass"
               for result in bp["activated_check_results"]):
            fail("boundary check did not pass")

        graphs = _records(self, "section_work_graph.v1")
        items = graphs[0]["payload"]["work_items"]
        closure = dependency_closure({
            item["work_item_id"]: tuple(item["dependency_work_item_ids"])
            for item in items})
        expected_closure = {
            "schema_version": "section-dependency-closure.v1",
            "closure": {item_id: sorted(members)
                        for item_id, members in closure.items()},
        }
        closure_record = self.get(bp["dependency_closure_ref"],
                                  versions=("section_content_record.v1",),
                                  artifacts=("read_inventory",))
        closure_value = self.closed_values.get(record_id(closure_record))
        if closure_value != expected_closure:
            fail("boundary dependency closure bytes do not reconstruct from "
                 "the frozen work graph")

        section_for_item = {
            item["work_item_id"]: self.get(
                item["section_contract_ref"],
                versions=("section_contract.v1",))["payload"]["section_id"]
            for item in items}
        system_sections = {
            section_for_item[item["work_item_id"]] for item in items
            if "system" in item["required_audit_levels"]}
        expected_scopes = sorted(changed | system_sections) or \
            sorted(section_dependencies)
        if bp["required_system_audit_scope_ids"] != expected_scopes:
            fail("boundary required_system_audit_scope_ids does not "
                 "reconstruct")

        for bundle in bundles:
            if bundle["payload"]["local_assessment"] != "pass":
                fail("non-passing section bundle blocks publication")

    def _validate_rooted_paths(self, program: Mapping[str, Any],
                               root: Mapping[str, Any]) -> None:
        rp = root["payload"]
        pp = program["payload"]
        prefix = f"artifacts/section-council/{pp['planned_request_id']}/"
        final_scope_path = prefix + "final-scope.json"
        final_scope = self.get(rp["final_scope_ref"],
                               versions=("final_scope_manifest.v1",))
        paths = set()
        for row in rp["record_inventory"]:
            if not row["repository_relpath"].startswith(prefix):
                fail("HSC record path escapes its fixed request namespace")
            if row["schema_version"] == "final_scope_manifest.v1":
                if row["record_id"] != record_id(final_scope) or \
                        row["repository_relpath"] != final_scope_path:
                    fail("final-scope record is not at its fixed envelope path")
            else:
                if row["repository_relpath"] in paths:
                    fail("duplicate rooted system path")
                paths.add(row["repository_relpath"])
        for record in self.records:
            if record["schema_version"] in (
                    "section_bootstrap_content.v1", "section_content_record.v1"):
                path = record["payload"]["storage_relpath"]
                if path in paths:
                    fail("record/raw content path alias")
                paths.add(path)
        require_unique_paths(sorted(paths), "rooted system paths")
        if paths != set(final_scope["payload"]["realized_system_artifact_paths"]):
            fail("rooted system paths do not equal final-scope realization")

    def _validate_candidate_tree(self, program: Mapping[str, Any],
                                 root: Mapping[str, Any],
                                 candidate_tree: Iterable[Mapping[str, Any]],
                                 base_tree: Iterable[Mapping[str, Any]]) \
            -> None:
        """Authenticate the complete candidate tree content.

        The supplied base and candidate inventories are complete FILE_REF
        arrays for the base commit tree and the final candidate commit tree.
        The validator independently recomputes, under the frozen exclusion
        rule (``artifacts/section-council/<planned_request_id>/`` excluded):

        1. the project view must equal the base tree with exactly the final
           scope's actual changes applied (per-kind before-state verified);
        2. ``assembled_tree_sha256`` must equal the domain-separated digest
           of that reconstructed project view;
        3. the request-namespace view must contain exactly the realized
           system-artifact paths plus the two fixed envelopes, every entry a
           ``100644`` file whose content hash equals the byte identity bound
           by the root (record bytes, raw blob bytes, and both envelopes).
        """
        candidate = list(candidate_tree) if not isinstance(
            candidate_tree, list) else candidate_tree
        base = list(base_tree) if not isinstance(base_tree, list) else base_tree
        _file_refs(candidate, "candidate_tree")
        _file_refs(base, "base_tree")
        pp = program["payload"]
        rp = root["payload"]
        prefix = f"artifacts/section-council/{pp['planned_request_id']}/"
        base_map = {row["path"]: (row["blob_sha256"], row["git_mode"])
                    for row in base}
        if any(path.startswith(prefix) for path in base_map):
            fail("base tree already contains the fixed request namespace")
        project = {row["path"]: (row["blob_sha256"], row["git_mode"])
                   for row in candidate if not row["path"].startswith(prefix)}
        namespace = {row["path"]: row for row in candidate
                     if row["path"].startswith(prefix)}

        final_scope = self.get(rp["final_scope_ref"],
                               versions=("final_scope_manifest.v1",))
        fp = final_scope["payload"]
        applied = dict(base_map)
        for change in fp["actual_changes"]:
            kind = change["kind"]
            path = change["path"]
            before = (change["blob_before"], change["mode_before"])
            after = (change["blob_after"], change["mode_after"])
            if kind == "add":
                if path in applied:
                    fail("actual add collides with an existing base path")
                applied[path] = after
            elif kind == "delete":
                if applied.get(path) != before:
                    fail("actual delete does not match the base tree")
                del applied[path]
            elif kind in ("modify", "mode"):
                if applied.get(path) != before:
                    fail("actual change does not match the base tree")
                applied[path] = after
            else:
                source = change["rename_source"]
                if applied.get(source) != before or path in applied:
                    fail("actual rename does not match the base tree")
                del applied[source]
                applied[path] = after
        if applied != project:
            fail("candidate project tree does not equal base plus actual "
                 "changes")
        expected_digest = domain_hash(
            "council:section-project-tree:v1",
            [{"path": path, "blob_sha256": blob, "git_mode": mode,
              "kind": "file"}
             for path, (blob, mode) in sorted(project.items())])
        if fp["assembled_tree_sha256"] != expected_digest:
            fail("assembled_tree_sha256 does not reconstruct from the "
                 "candidate project tree")

        envelopes = {prefix + "root.json", prefix + "final-scope.json"}
        realized = set(fp["realized_system_artifact_paths"])
        if set(namespace) != realized | envelopes:
            fail("candidate namespace files do not equal realized system "
                 "artifacts plus the two fixed envelopes")
        for row in namespace.values():
            if row["git_mode"] != "100644":
                fail("candidate namespace entry is not a plain 100644 file")
        for row in rp["record_inventory"]:
            entry = namespace.get(row["repository_relpath"])
            if entry is None or entry["blob_sha256"] != row["content_sha256"]:
                fail("candidate tree does not bind an inventoried record's "
                     "exact bytes")
        for record in self.records:
            if record["schema_version"] in ("section_bootstrap_content.v1",
                                            "section_content_record.v1"):
                payload = record["payload"]
                entry = namespace.get(payload["storage_relpath"])
                if entry is None or \
                        entry["blob_sha256"] != payload["blob_sha256"]:
                    fail("candidate tree does not bind a raw evidence blob's "
                         "exact bytes")
        root_entry = namespace.get(prefix + "root.json")
        if root_entry is None or \
                root_entry["blob_sha256"] != compute_content_sha(root):
            fail("candidate tree does not bind the evidence root's exact "
                 "bytes")


def compute_content_sha(record: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()


def _content_tail(storage_relpath: str) -> str:
    """The full content-namespace-relative path of a sealed content record —
    everything after the fixed ``/content/`` segment. Used as the exact,
    non-basename identity that binds an output-inventory row and a declared
    assessor output path to their sealed content record."""
    marker = "/content/"
    index = storage_relpath.find(marker)
    if index < 0:
        fail("content record path lacks the fixed /content/ segment")
    tail = storage_relpath[index + len(marker):]
    if not tail:
        fail("content record path has an empty content tail")
    return tail


def _git(repo: str, args: list, repo_roots) -> subprocess.CompletedProcess:
    validate_repository(repo, list(repo_roots))
    return subprocess.run(["git", "-C", repo] + args, capture_output=True,
                          timeout=120)


def _read_git_tree(repo: str, repo_roots: Iterable[str],
                   commit: str) -> list[dict]:
    """The complete recursive tree of an EXACT real Git commit as a sorted
    FILE_REF array ``{path, blob_sha256, git_mode, kind:"file"}``.

    ``blob_sha256`` is the SHA-256 of the file's exact bytes (not the Git
    object id). The commit must be a real object; a nonexistent or malformed
    commit, a submodule/symlink/gitlink entry, or any non-``100644``/
    ``100755`` mode refuses. This binds every downstream tree claim to real
    Git identity so a synthetic all-zero commit cannot masquerade as truth."""
    validate_commit(commit)
    roots = list(repo_roots)
    exists = _git(repo, ["cat-file", "-e", commit + "^{commit}"], roots)
    if exists.returncode != 0:
        fail(f"commit {commit[:12]} is not a real object in the repository")
    listing = _git(repo, ["ls-tree", "-r", "-z", commit], roots)
    if listing.returncode != 0:
        raise HSCValidationError(
            f"git ls-tree failed for {commit[:12]}: "
            f"{listing.stderr.decode('utf-8', 'replace').strip()}")
    entries: list[tuple[str, str, str]] = []  # (path, git_mode, blob_sha1)
    wanted: set[str] = set()
    for record in listing.stdout.split(b"\x00"):
        if not record:
            continue
        meta, _, raw_path = record.partition(b"\t")
        parts = meta.split(b" ")
        if len(parts) != 3:
            fail("malformed git ls-tree record")
        mode, obj_type, obj_id = (p.decode("ascii", "strict") for p in parts)
        if obj_type != "blob" or mode not in ("100644", "100755"):
            fail("candidate/base tree contains a non-file entry "
                 "(symlink, gitlink, or unexpected mode)")
        try:
            path = raw_path.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise HSCValidationError("git path is not valid UTF-8") from exc
        validate_path(path)
        entries.append((path, mode, obj_id))
        wanted.add(obj_id)
    sha256_by_blob = _git_blob_sha256(repo, roots, commit, sorted(wanted))
    tree = [{"path": path, "blob_sha256": sha256_by_blob[obj_id],
             "git_mode": mode, "kind": "file"}
            for path, mode, obj_id in entries]
    tree.sort(key=lambda row: row["path"])
    return tree


def _git_blob_sha256(repo: str, repo_roots: Iterable[str], commit: str,
                     blob_ids: list[str]) -> dict[str, str]:
    """SHA-256 of each requested blob's exact bytes, read from the object
    store via a single ``git cat-file --batch``."""
    result: dict[str, str] = {}
    if not blob_ids:
        return result
    proc = subprocess.run(
        ["git", "-C", repo, "cat-file", "--batch"],
        input=("\n".join(blob_ids) + "\n").encode("ascii"),
        capture_output=True, timeout=120)
    if proc.returncode != 0:
        raise HSCValidationError(
            f"git cat-file failed: "
            f"{proc.stderr.decode('utf-8', 'replace').strip()}")
    out = proc.stdout
    offset = 0
    for blob_id in blob_ids:
        newline = out.index(b"\n", offset)
        header = out[offset:newline].decode("ascii", "strict")
        fields = header.split(" ")
        if len(fields) != 3 or fields[0] != blob_id or fields[1] != "blob":
            fail("git cat-file did not return the requested blob")
        size = int(fields[2])
        start = newline + 1
        data = out[start:start + size]
        result[blob_id] = hashlib.sha256(data).hexdigest()
        offset = start + size + 1  # trailing newline after the payload
    return result


_BUNDLE_SEED_REF_FIELDS = (
    "program_ref", "contract_ref", "builder_assignment_ref",
    "assessor_assignment_ref", "builder_launcher_receipt_ref",
    "assessor_launcher_receipt_ref", "builder_journal_manifest_ref",
    "assessor_journal_manifest_ref", "builder_context_ref",
    "assessor_context_ref", "builder_sandbox_attestation_ref",
    "assessor_sandbox_attestation_ref", "proposal_ref", "diff_preview_ref",
    "assessment_manifest_ref", "test_manifest_ref", "dependency_snapshot_ref",
)


def _bundle_seed_refs(bundle_payload: Mapping[str, Any]) -> list[dict]:
    """The typed staleness seed set of one bundle: every reference the
    bundle itself carries except ``staleness_input_refs``."""
    refs = [bundle_payload[field] for field in _BUNDLE_SEED_REF_FIELDS]
    refs.extend(bundle_payload["test_result_refs"])
    refs.extend(row["evidence_ref"]
                for row in bundle_payload["invariant_results"])
    refs.extend(row["evidence_ref"]
                for row in bundle_payload["resource_metrics"]
                if row["evidence_ref"] is not None)
    return refs


def compute_bundle_staleness_inputs(records: Iterable[Mapping[str, Any]],
                                    blobs: Mapping[str, bytes],
                                    bundle_payload: Mapping[str, Any]) \
        -> list[dict]:
    """Producer-side helper: the exact acyclic pre-scope
    ``staleness_input_refs`` value the complete-root validator will
    independently reconstruct for a bundle (transitive typed closure of the
    bundle's own references plus the work graph and each upstream section's
    contract and bundle). Post-scope §9 triggers are enforced at root time,
    never stored in the bundle."""
    store = RecordStore(records, blobs=blobs)
    store._validate_blobs()
    contract_ref_to_bundle = {
        record["payload"]["contract_ref"]["record_id"]: record
        for record in _records(store, "section_evidence_bundle.v1")}
    seed = store._bundle_staleness_seed(bundle_payload, contract_ref_to_bundle)
    reached = store._reference_closure(seed)
    return sorted(
        ({"content_sha256": compute_content_sha(store.by_id[rid]),
          "record_id": rid} for rid in reached),
        key=canonical_sort_key)


def _closed_output_inventory(value: Any) -> list[dict]:
    """The frozen output-inventory byte shape (design §6.9, lines 1324-1326):
    one closed canonical JSON array of the sorted tuples
    ``(output_relpath, byte_length, blob_sha256)`` for every leaf file. No
    additional fields are frozen, so none are invented here."""
    if not isinstance(value, list):
        fail("output inventory must be a canonical array of output tuples")
    require_sorted_unique(
        value, "output_inventory",
        key=lambda row: row.get("output_relpath", "")
        if isinstance(row, dict) else "")
    for index, row in enumerate(value):
        where = f"output_inventory[{index}]"
        exact_keys(row, {"output_relpath", "byte_length", "blob_sha256"},
                   where)
        validate_path(row["output_relpath"], f"{where}.output_relpath")
        require_int(row["byte_length"], f"{where}.byte_length")
        require_h(row["blob_sha256"], f"{where}.blob_sha256")
    return value


def _records(store: RecordStore, schema_version: str) -> list[dict]:
    return [record for record in store.records
            if record["schema_version"] == schema_version]


def _ref_ids(refs: Iterable[Mapping[str, str]]) -> list[str]:
    return [ref["record_id"] for ref in refs]


def _change_key(change: Mapping[str, Any]) -> tuple:
    return (change["path"], change["kind"], change["rename_source"],
            change["blob_before"], change["mode_before"])


def _require_narrow_changes(parent: Iterable[Mapping[str, Any]],
                            child: Iterable[Mapping[str, Any]],
                            where: str) -> None:
    parent_map = {_change_key(change): change for change in parent}
    child_map = {_change_key(change): change for change in child}
    if not set(child_map) <= set(parent_map):
        fail(f"{where} widens its predicted change set")
    for key, change in parent_map.items():
        if change["required"] and key not in child_map:
            fail(f"{where} drops a required predicted change")
    for key, change in child_map.items():
        if change["required"] != parent_map[key]["required"]:
            fail(f"{where} changes a prediction's required flag")


def _require_budget_narrow(parent: Mapping[str, int], child: Mapping[str, int],
                           where: str) -> None:
    if any(child[field] > parent[field] for field in parent):
        fail(f"{where} widens its budget")


def _require_repeated_dispatch(left: Mapping[str, Any],
                               right: Mapping[str, Any], *,
                               omit: set[str] | None = None) -> None:
    excluded = set(omit or ()) | {"scheduler_journal_sequence",
                                  "scheduler_journal_entry_sha256",
                                  "authorization_ref", "assignment_ref",
                                  "barrier_status"}
    repeated = {
        "program_ref", "contract_ref", "work_item_id", "role",
        "principal_registry_ref", "principal_id", "authority_control_id",
        "principal_credential_digest", "scheduler_authority_id",
        "launcher_executable_sha256", "session_nonce", "attempt", "context_ref",
        "sandbox_profile_ref", "workspace_id", "output_leaf",
    }
    for field in sorted(repeated - excluded):
        if field in left and field in right and left[field] != right[field]:
            fail(f"dispatch repeated field {field} changed")


def _claim_native_object(seen: dict[tuple[str, str],
                                    tuple[str, tuple[bytes, ...]]],
                         native_id: tuple[str, str], root_id: str,
                         path: tuple[bytes, ...]) -> None:
    location = (root_id, path)
    prior = seen.get(native_id)
    if prior is not None and prior != location:
        fail("native file identity aliases two namespaces or paths")
    seen[native_id] = location


def _closed_check_declaration(value: Any) -> list[RefRequirement]:
    if not isinstance(value, dict):
        fail("check declaration must be an object")
    if set(value) != {"check_id", "status", "evidence_output_relpath"}:
        fail("check declaration exact keys mismatch")
    require_slug(value["check_id"], "check_declaration.check_id")
    require_literal(value["status"], ("pass", "fail", "error"),
                    "check_declaration.status")
    validate_path(value["evidence_output_relpath"],
                  "check_declaration.evidence_output_relpath")
    return []


def _closed_finding_declaration(value: Any) -> list[RefRequirement]:
    keys = {"audit_level", "severity", "invariant_id", "claim",
            "evidence_output_relpath", "reproduction_output_relpath",
            "affected_path", "blocks_local_pass", "status",
            "predecessor_finding_ref", "resolution_output_relpath"}
    if not isinstance(value, dict) or set(value) != keys:
        fail("finding declaration exact keys mismatch")
    require_literal(value["audit_level"], ("section", "boundary", "system"),
                    "finding_declaration.audit_level")
    require_literal(value["severity"],
                    ("INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"),
                    "finding_declaration.severity")
    require_slug(value["invariant_id"], "finding_declaration.invariant_id")
    require_string(value["claim"], "finding_declaration.claim")
    validate_path(value["evidence_output_relpath"],
                  "finding_declaration.evidence_output_relpath")
    validate_path(value["reproduction_output_relpath"],
                  "finding_declaration.reproduction_output_relpath")
    if value["affected_path"] is not None:
        validate_path(value["affected_path"], "finding_declaration.affected_path")
    require_bool(value["blocks_local_pass"],
                 "finding_declaration.blocks_local_pass")
    status = require_literal(value["status"],
                             ("open", "resolved", "unreproduced"),
                             "finding_declaration.status")
    predecessor = validate_ref(value["predecessor_finding_ref"],
                               "finding_declaration.predecessor_finding_ref",
                               nullable=True)
    if value["resolution_output_relpath"] is not None:
        validate_path(value["resolution_output_relpath"],
                      "finding_declaration.resolution_output_relpath")
    if status == "resolved" and (predecessor is None or
                                  value["resolution_output_relpath"] is None):
        fail("resolved finding declaration lacks lineage or resolution")
    if status != "resolved" and value["resolution_output_relpath"] is not None:
        fail("non-resolved finding declaration carries resolution")
    return ([] if predecessor is None else [RefRequirement(
        predecessor, "finding_declaration.predecessor_finding_ref",
        ("section_finding.v1",))])


def _closed_assessment_declaration(value: Any) -> list[RefRequirement]:
    keys = {"schema_version", "program_ref", "contract_ref", "work_item_id",
            "assessor_assignment_ref", "assessor_context_ref", "proposal_ref",
            "check_declaration_output_relpaths",
            "finding_declaration_output_relpaths", "predecessor_assessment_ref",
            "declared_disposition", "error_reason"}
    if not isinstance(value, dict) or set(value) != keys:
        fail("assessment declaration exact keys mismatch")
    require_literal(value["schema_version"],
                    ("section-assessment-declaration.v1",),
                    "assessment_declaration.schema_version")
    refs = []
    typed = (
        ("program_ref", "section_program.v1"),
        ("contract_ref", "section_contract.v1"),
        ("assessor_assignment_ref", "section_assignment.v1"),
        ("assessor_context_ref", "section_context_bundle.v1"),
        ("proposal_ref", "section_content_record.v1"),
    )
    for field, version in typed:
        ref = validate_ref(value[field], f"assessment_declaration.{field}")
        artifacts = ("proposal",) if field == "proposal_ref" else ()
        refs.append(RefRequirement(ref, f"assessment_declaration.{field}",
                                   (version,), artifacts))
    require_h(value["work_item_id"], "assessment_declaration.work_item_id")
    all_paths = []
    for field in ("check_declaration_output_relpaths",
                  "finding_declaration_output_relpaths"):
        require_sorted_unique(value[field], f"assessment_declaration.{field}",
                              nonempty=field.startswith("check"))
        for index, path in enumerate(value[field]):
            validate_path(path, f"assessment_declaration.{field}[{index}]")
            all_paths.append(path)
    if len(all_paths) != len(set(all_paths)):
        fail("assessment declaration output paths overlap")
    predecessor = validate_ref(value["predecessor_assessment_ref"],
                               "assessment_declaration.predecessor_assessment_ref",
                               nullable=True)
    if predecessor:
        refs.append(RefRequirement(
            predecessor, "assessment_declaration.predecessor_assessment_ref",
            ("section_assessment_manifest.v1",)))
    disposition = require_literal(value["declared_disposition"],
                                  ("pass", "blocked", "error"),
                                  "assessment_declaration.declared_disposition")
    if disposition == "error":
        require_string(value["error_reason"],
                       "assessment_declaration.error_reason")
    elif value["error_reason"] is not None:
        fail("only error declaration carries error_reason")
    return refs
