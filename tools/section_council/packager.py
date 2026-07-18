"""Trusted output packager (HSC-B component 7).

A confined worker writes only closed JSON blobs into its private ``/out`` leaf —
a proposal and diff preview (builder), or an assessment declaration, check
declarations/evidence, and finding declarations/evidence/reproductions
(assessor). It never constructs reference-bearing records. The trusted packager
freezes and no-follow enumerates **every** file in that leaf, wraps all bytes
into ``section_content_record.v1`` records, and then deterministically
constructs each ``section_finding.v1`` and the ``section_assessment_manifest.v1``
by an exact field mapping — not a judgment step (design §6.8).

Packaging refuses whenever the frozen declaration, whole-leaf inventory, and
manifest disagree on any check or finding, or when the derived disposition would
differ from the assessor's declared disposition.
"""

from __future__ import annotations

import hashlib
import os
import stat
from typing import Any

from tools.council.schemas import canonical_json, domain_hash

from .core import (HSCValidationError, require_literal, strict_json_bytes,
                   validate_path)
from .native import observe_fd
from .records import compute_record_content_sha256, make_record, record_ref

_FINDING_INVENTORY = "council:section-finding-inventory:v1"
_SEVERITIES = ("INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL")
_AUDIT_LEVELS = ("section", "boundary", "system")
_FINDING_STATUS = ("open", "resolved", "unreproduced")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def freeze_leaf(leaf_fd: int) -> dict[str, bytes]:
    """No-follow enumerate a worker output leaf and return ``{relpath: bytes}``.

    A symlink, special file, or unreadable entry fails closed rather than being
    silently skipped, so the frozen inventory is exhaustive."""
    out: dict[str, bytes] = {}

    def walk(dir_fd: int, prefix: str) -> None:
        for name in sorted(os.listdir(dir_fd)):
            path = f"{prefix}{name}"
            fd = os.open(name, os.O_PATH | os.O_NOFOLLOW, dir_fd=dir_fd)
            try:
                if stat.S_ISLNK(os.fstat(fd).st_mode):
                    raise HSCValidationError(
                        f"worker leaf entry {path!r} is a symlink")
                obs = observe_fd(fd)
            finally:
                os.close(fd)
            if obs["file_type"] == "directory":
                sub = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                              dir_fd=dir_fd)
                try:
                    walk(sub, f"{path}/")
                finally:
                    os.close(sub)
            elif obs["file_type"] == "regular":
                rfd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dir_fd)
                try:
                    if observe_fd(rfd) != obs:
                        raise HSCValidationError(
                            f"leaf entry {path!r} changed during read")
                    body = b""
                    while True:
                        block = os.read(rfd, 1 << 20)
                        if not block:
                            break
                        body += block
                finally:
                    os.close(rfd)
                out[path] = body
            else:  # pragma: no cover - observe_fd already refuses others
                raise HSCValidationError(f"leaf entry {path!r} is not a file")

    walk(leaf_fd, "")
    return out


class ContentEmitter:
    """Allocates deterministic repository slots for wrapped blobs and records,
    accumulating the ``{repository_relpath: bytes}`` blob map the evidence store
    binds. One emitter is used across a whole request."""

    def __init__(self, request_id: str):
        self.prefix = f"artifacts/section-council/{request_id}/"
        self.blobs: dict[str, bytes] = {}
        self._content_slot = 0

    def wrap(self, program_ref: dict, artifact_type: str, data: bytes, *,
             worker_relpath: str, producer_assignment_ref: dict | None = None,
             media_type: str = "application/json",
             parent_content_refs: list | None = None) -> dict:
        """Wrap raw ``data`` into a ``section_content_record.v1`` and stage its
        bytes under ``content/`` at the worker's exact leaf-relative path.

        The storage path tail is the frozen ``worker_relpath`` (never an
        anonymous slot), so the store's content-tail equality binds the declared
        assessor output path to this exact ref. ``blob_sha256``/``byte_length``
        bind the exact bytes the store re-verifies."""
        rel = validate_path(worker_relpath, "worker_relpath")
        path = f"{self.prefix}content/{rel}"
        if path in self.blobs:
            raise HSCValidationError(
                f"worker leaf relpath {rel!r} wrapped twice")
        self._content_slot += 1
        payload = {
            "program_ref": program_ref,
            "artifact_type": artifact_type,
            "storage_relpath": path,
            "media_type": media_type,
            "byte_length": len(data),
            "blob_sha256": _sha256(data),
            "producer_assignment_ref": producer_assignment_ref,
            "parent_content_refs": parent_content_refs or [],
        }
        record = make_record("section_content_record.v1", payload)
        self.blobs[path] = data
        return record


def output_inventory_bytes(content_records: list[dict]) -> bytes:
    """The closed whole-leaf inventory: canonical JSON of the sorted
    ``(output_relpath, byte_length, blob_sha256)`` tuples for every wrapped leaf
    file (design §6.8). ``output_relpath`` is the worker's exact leaf-relative
    path (the content record's tail after ``/content/``), so it equals the path
    the assessor declared."""
    rows = sorted(({
        "output_relpath": rec["payload"]["storage_relpath"].split(
            "/content/", 1)[1],
        "byte_length": rec["payload"]["byte_length"],
        "blob_sha256": rec["payload"]["blob_sha256"],
    } for rec in content_records), key=lambda row: row["output_relpath"])
    return canonical_json(rows).encode("utf-8")


def validate_finding_declaration(decl: Any) -> dict[str, Any]:
    """Validate a closed ``finding_declaration`` blob (design §6.8) and return
    it. The packager translates only its paths into refs; it never rewrites
    judgment text, severity, status, or lineage."""
    if not isinstance(decl, dict):
        raise HSCValidationError("finding declaration must be an object")
    keys = {"audit_level", "severity", "invariant_id", "claim",
            "evidence_output_relpath", "reproduction_output_relpath",
            "affected_path", "blocks_local_pass", "status",
            "predecessor_finding_ref", "resolution_output_relpath"}
    if set(decl) != keys:
        raise HSCValidationError("finding declaration has unexpected keys")
    require_literal(decl["audit_level"], _AUDIT_LEVELS, "audit_level")
    require_literal(decl["severity"], _SEVERITIES, "severity")
    status = require_literal(decl["status"], _FINDING_STATUS, "status")
    if not isinstance(decl["claim"], str) or not decl["claim"]:
        raise HSCValidationError("finding claim must be a non-empty string")
    if not isinstance(decl["blocks_local_pass"], bool):
        raise HSCValidationError("blocks_local_pass must be a bool")
    if status == "resolved" and decl["resolution_output_relpath"] is None:
        raise HSCValidationError("a resolved finding needs a resolution path")
    if status != "resolved" and decl["resolution_output_relpath"] is not None:
        raise HSCValidationError("only a resolved finding carries a resolution")
    return decl


def build_finding(*, program_ref: dict, contract_ref: dict,
                  assessor_assignment_ref: dict, affected_proposal_ref: dict,
                  finding_declaration_ref: dict, evidence_ref: dict,
                  reproduction_ref: dict, resolution_evidence_ref: dict | None,
                  declaration: dict) -> dict:
    """Construct one ``section_finding.v1`` field-by-field from its frozen
    declaration and the wrapped evidence refs (design §6.8 packaging rule)."""
    decl = validate_finding_declaration(declaration)
    payload = {
        "program_ref": program_ref,
        "contract_ref": contract_ref,
        "assessor_assignment_ref": assessor_assignment_ref,
        "affected_proposal_ref": affected_proposal_ref,
        "finding_declaration_ref": finding_declaration_ref,
        "audit_level": decl["audit_level"],
        "severity": decl["severity"],
        "invariant_id": decl["invariant_id"],
        "claim": decl["claim"],
        "evidence_ref": evidence_ref,
        "reproduction_ref": reproduction_ref,
        "affected_path": decl["affected_path"],
        "blocks_local_pass": decl["blocks_local_pass"],
        "status": decl["status"],
        "predecessor_finding_ref": decl["predecessor_finding_ref"],
        "resolution_evidence_ref": resolution_evidence_ref,
    }
    return make_record("section_finding.v1", payload)


def finding_inventory_sha256(finding_records: list[dict],
                             record_relpaths: dict[str, str]) -> str:
    """The exact finding preimage: canonical JSON array (sorted by
    ``record_relpath``) of ``{record_relpath, record_id, content_sha256}`` for
    every and only packaged ``section_finding.v1`` record (design §6.8).

    ``record_relpaths`` maps each finding record id to its predeclared
    repository slot."""
    array = sorted(({
        "record_relpath": record_relpaths[rec["section_finding_id"]],
        "record_id": rec["section_finding_id"],
        "content_sha256": compute_record_content_sha256(rec),
    } for rec in finding_records), key=lambda row: row["record_relpath"])
    return domain_hash(_FINDING_INVENTORY, array)


def derive_disposition(*, required_check_ids: list[str],
                       check_results: list[dict], findings: list[dict],
                       error_reason: str | None) -> str:
    """Derive the local assessment exactly once (design §6.8 rule 5).

    ``error`` iff ``error_reason`` is non-null (and any ``error``-status check
    requires it). Otherwise ``blocked`` iff a check fails or an open finding
    blocks local pass. Otherwise ``pass`` requires every contract-required check
    exactly once with status ``pass`` and zero open blockers."""
    statuses = [c["status"] for c in check_results]
    if error_reason is not None:
        return "error"
    if "error" in statuses:
        raise HSCValidationError(
            "an error-status check requires a non-null error_reason")
    if "fail" in statuses:
        return "blocked"
    if any(f["status"] == "open" and f["blocks_local_pass"] for f in findings):
        return "blocked"
    # pass: every required check present exactly once with status pass.
    by_id: dict[str, int] = {}
    for c in check_results:
        by_id[c["check_id"]] = by_id.get(c["check_id"], 0) + 1
    for cid in required_check_ids:
        if by_id.get(cid) != 1 or next(
                c["status"] for c in check_results if c["check_id"] == cid) \
                != "pass":
            raise HSCValidationError(
                f"required check {cid!r} is missing, duplicated, or not passing")
    return "pass"


def build_assessment_manifest(*, program_ref: dict, contract_ref: dict,
                              work_item_id: str, assessor_assignment_ref: dict,
                              assessor_context_ref: dict, proposal_ref: dict,
                              assessment_declaration_ref: dict,
                              assessor_output_inventory_ref: dict,
                              check_declaration_refs: list[dict],
                              check_results: list[dict],
                              finding_records: list[dict],
                              finding_record_relpaths: dict[str, str],
                              required_check_ids: list[str],
                              error_reason: str | None,
                              predecessor_assessment_ref: dict | None) -> dict:
    """Assemble the ``section_assessment_manifest.v1`` from purely recomputed
    finding refs/inventory/counts, a recomputed open-blocking count, and the
    disposition derived once inside this constructor.

    The disposition and blocker count are NEVER accepted from the caller (the
    finding 001729 gap): they are derived from the finding records' own frozen
    ``status``/``blocks_local_pass`` and the check results, so a caller cannot
    present ``pass``/zero-blockers over blocking assessor bytes."""
    finding_view = [{"status": rec["payload"]["status"],
                     "blocks_local_pass": rec["payload"]["blocks_local_pass"]}
                    for rec in finding_records]
    open_blocking_count = sum(1 for f in finding_view
                              if f["status"] == "open" and f["blocks_local_pass"])
    local_assessment = derive_disposition(
        required_check_ids=required_check_ids, check_results=check_results,
        findings=finding_view, error_reason=error_reason)
    finding_refs = sorted((record_ref(rec) for rec in finding_records),
                          key=lambda r: r["record_id"])
    payload = {
        "program_ref": program_ref,
        "contract_ref": contract_ref,
        "work_item_id": work_item_id,
        "assessor_assignment_ref": assessor_assignment_ref,
        "assessor_context_ref": assessor_context_ref,
        "proposal_ref": proposal_ref,
        "assessment_declaration_ref": assessment_declaration_ref,
        "assessor_output_inventory_ref": assessor_output_inventory_ref,
        "check_declaration_refs": sorted(
            check_declaration_refs, key=lambda r: r["record_id"]),
        "check_results": sorted(check_results, key=lambda c: c["check_id"]),
        "finding_refs": finding_refs,
        "finding_inventory_sha256": finding_inventory_sha256(
            finding_records, finding_record_relpaths),
        "finding_count": len(finding_records),
        "open_blocking_count": open_blocking_count,
        "local_assessment": local_assessment,
        "error_reason": error_reason,
        "predecessor_assessment_ref": predecessor_assessment_ref,
    }
    return make_record("section_assessment_manifest.v1", payload)


_ASSESSMENT_DECL_KEYS = {
    "program_ref", "contract_ref", "work_item_id", "assessor_assignment_ref",
    "assessor_context_ref", "proposal_ref", "predecessor_assessment_ref",
    "declared_disposition", "error_reason", "check_declaration_output_relpaths",
    "finding_declaration_output_relpaths"}
_CHECK_DECL_KEYS = {"check_id", "status", "evidence_output_relpath"}


def package_assessment_leaf(leaf_map: dict[str, bytes], *, emitter: ContentEmitter,
                            program_ref: dict, contract_ref: dict,
                            work_item_id: str, assessor_assignment_ref: dict,
                            assessor_context_ref: dict, proposal_ref: dict,
                            required_check_ids: list[str],
                            records_prefix: str,
                            assessment_relpath: str = "assessment.json") -> dict:
    """The ONE trusted packaging transformation (design §6.8, finding 001734-1).

    Given the single frozen ``{leaf-relative path: bytes}`` map of a sealed
    assessor output leaf, this parses and validates the sealed assessment /
    check / finding declarations, wraps **every and only** leaf member exactly
    once with its exact typed path, resolves every declared path through that
    map, recomputes the check results / findings / finding inventory / disposition
    / blocker count, and constructs the manifest — refusing on any omitted leaf
    member, swapped path→ref mapping, mismatched declared disposition, or missing
    contract-required check. Callers cannot omit a file, repoint a declared path,
    or present a pass over blocking bytes: the mapping is exhaustive and derived.

    Returns ``{"manifest", "findings", "contents"}``; the wrapped bytes are staged
    in ``emitter.blobs``. ``records_prefix`` is the repository directory the
    finding records are slotted under for the finding-inventory hash."""
    if assessment_relpath not in leaf_map:
        raise HSCValidationError("assessor leaf has no assessment declaration")
    decl = strict_json_bytes(leaf_map[assessment_relpath], "assessment_declaration")
    if not isinstance(decl, dict) or set(decl) != _ASSESSMENT_DECL_KEYS:
        raise HSCValidationError("assessment declaration has unexpected keys")
    # The sealed static context must equal the dispatch context exactly.
    if decl["program_ref"] != program_ref or \
            decl["contract_ref"] != contract_ref or \
            decl["work_item_id"] != work_item_id or \
            decl["assessor_assignment_ref"] != assessor_assignment_ref or \
            decl["assessor_context_ref"] != assessor_context_ref or \
            decl["proposal_ref"] != proposal_ref:
        raise HSCValidationError("assessment declaration context differs from "
                                 "its dispatch")

    check_paths = decl["check_declaration_output_relpaths"]
    finding_paths = decl["finding_declaration_output_relpaths"]
    for label, paths in (("check", check_paths), ("finding", finding_paths)):
        if not isinstance(paths, list) or len(paths) != len(set(paths)):
            raise HSCValidationError(f"{label} declaration paths are not unique")

    # Parse the check and finding declaration blobs and enumerate the EXACT
    # expected leaf membership (declaration + every path it references).
    expected = {assessment_relpath}
    check_blobs: dict[str, dict] = {}
    for path in check_paths:
        if path not in leaf_map:
            raise HSCValidationError(f"declared check path {path!r} absent from "
                                     "the leaf")
        blob = strict_json_bytes(leaf_map[path], f"check_declaration:{path}")
        if not isinstance(blob, dict) or set(blob) != _CHECK_DECL_KEYS:
            raise HSCValidationError(f"check declaration {path!r} has bad keys")
        require_literal(blob["status"], ("pass", "fail", "error"),
                        f"check {path} status")
        check_blobs[path] = blob
        expected.add(path)
        expected.add(validate_path(blob["evidence_output_relpath"],
                                   "check evidence path"))
    finding_blobs: dict[str, dict] = {}
    for path in finding_paths:
        if path not in leaf_map:
            raise HSCValidationError(f"declared finding path {path!r} absent "
                                     "from the leaf")
        blob = validate_finding_declaration(
            strict_json_bytes(leaf_map[path], f"finding_declaration:{path}"))
        finding_blobs[path] = blob
        expected.add(path)
        expected.add(validate_path(blob["evidence_output_relpath"],
                                   "finding evidence path"))
        expected.add(validate_path(blob["reproduction_output_relpath"],
                                   "finding reproduction path"))
        if blob["resolution_output_relpath"] is not None:
            expected.add(validate_path(blob["resolution_output_relpath"],
                                       "finding resolution path"))
    # Every-and-only: the leaf contains exactly the referenced membership.
    if set(leaf_map) != expected:
        raise HSCValidationError("assessor leaf membership differs from its "
                                 "declared references (omission or extra file)")

    # Wrap every leaf member once with its exact typed artifact + worker path.
    kinds = {assessment_relpath: "assessment_declaration"}
    for path, blob in check_blobs.items():
        kinds[path] = "check_declaration"
        kinds[blob["evidence_output_relpath"]] = "check_evidence"
    for path, blob in finding_blobs.items():
        kinds[path] = "finding_declaration"
        kinds[blob["evidence_output_relpath"]] = "finding_evidence"
        kinds[blob["reproduction_output_relpath"]] = "reproduction"
        if blob["resolution_output_relpath"] is not None:
            kinds[blob["resolution_output_relpath"]] = "resolution"
    contents: dict[str, dict] = {}
    for path in sorted(leaf_map):
        media = "application/json" if kinds[path] in (
            "assessment_declaration", "check_declaration",
            "finding_declaration") else "text/plain"
        contents[path] = emitter.wrap(
            program_ref, kinds[path], leaf_map[path], worker_relpath=path,
            producer_assignment_ref=assessor_assignment_ref, media_type=media)

    # Recompute check results and findings, resolving declared paths to refs.
    check_results = [{
        "check_id": blob["check_id"], "status": blob["status"],
        "evidence_ref": record_ref(contents[blob["evidence_output_relpath"]]),
    } for blob in check_blobs.values()]
    findings = []
    for path in sorted(finding_blobs):
        blob = finding_blobs[path]
        resolution = (record_ref(contents[blob["resolution_output_relpath"]])
                      if blob["resolution_output_relpath"] is not None else None)
        findings.append(build_finding(
            program_ref=program_ref, contract_ref=contract_ref,
            assessor_assignment_ref=assessor_assignment_ref,
            affected_proposal_ref=proposal_ref,
            finding_declaration_ref=record_ref(contents[path]),
            evidence_ref=record_ref(contents[blob["evidence_output_relpath"]]),
            reproduction_ref=record_ref(
                contents[blob["reproduction_output_relpath"]]),
            resolution_evidence_ref=resolution, declaration=blob))
    finding_slots = {rec["section_finding_id"]:
                     f"{records_prefix}finding-{i:04d}.json"
                     for i, rec in enumerate(findings)}

    # The exhaustive output inventory covers every wrapped leaf blob (never
    # itself); wrap it as the assessor read-inventory.
    inv_bytes = output_inventory_bytes(list(contents.values()))
    inventory = emitter.wrap(program_ref, "read_inventory", inv_bytes,
                             worker_relpath="assessor-output-inventory.json",
                             producer_assignment_ref=assessor_assignment_ref)

    # Derive the disposition once and require the sealed declaration to agree.
    finding_view = [{"status": b["status"],
                     "blocks_local_pass": b["blocks_local_pass"]}
                    for b in finding_blobs.values()]
    disposition = derive_disposition(
        required_check_ids=required_check_ids, check_results=check_results,
        findings=finding_view, error_reason=decl["error_reason"])
    if decl["declared_disposition"] != disposition:
        raise HSCValidationError("sealed declared_disposition differs from the "
                                 "derived local assessment")

    manifest = build_assessment_manifest(
        program_ref=program_ref, contract_ref=contract_ref,
        work_item_id=work_item_id,
        assessor_assignment_ref=assessor_assignment_ref,
        assessor_context_ref=assessor_context_ref, proposal_ref=proposal_ref,
        assessment_declaration_ref=record_ref(contents[assessment_relpath]),
        assessor_output_inventory_ref=record_ref(inventory),
        check_declaration_refs=[record_ref(contents[p]) for p in check_blobs],
        check_results=check_results, finding_records=findings,
        finding_record_relpaths=finding_slots,
        required_check_ids=required_check_ids, error_reason=decl["error_reason"],
        predecessor_assessment_ref=decl["predecessor_assessment_ref"])
    return {"manifest": manifest, "findings": findings,
            "contents": list(contents.values()) + [inventory],
            "finding_slots": finding_slots}
