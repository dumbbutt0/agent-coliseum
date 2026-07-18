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

from .core import HSCValidationError, require_literal, validate_path
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
