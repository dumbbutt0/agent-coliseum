"""Evidence-root packaging and §6.10 finalization (HSC-B component 8b).

After the trusted assembler freezes the project changes, the packager builds all
pre-scope records and constructs ``final-scope.json`` over the project changes
plus the path-only list of realized system-artifact slots; then the remaining
post-scope records and ``root.json`` are built, inventorying every earlier and
later record and every raw evidence blob but never the root itself. Finalization
is one-way and uses no cryptographic fixed point (design §6.10).

This module provides the deterministic constructors for that final stage:
``assembled_tree_sha256`` over the candidate Git tree (excluding the request's
own envelope directory), ``build_final_scope`` / ``build_evidence_root``, and the
one exact ``HSC_V1`` ordinary-request binding line the later Council publish
consumes.
"""

from __future__ import annotations

from typing import Any

from tools.council.schemas import domain_hash

from .core import (HSCValidationError, parse_hsc_request_binding, require_h,
                   validate_path)
from .records import compute_record_content_sha256, make_record

_PROJECT_TREE = "council:section-project-tree:v1"


def _prefix(request_id: str) -> str:
    return f"artifacts/section-council/{request_id}/"


def assembled_tree_sha256(file_refs: list[dict], request_id: str) -> str:
    """``domain_hash`` over the sorted ``FILE_REF`` array for the complete
    candidate Git tree after project changes, excluding the request's own
    ``artifacts/section-council/<request_id>/`` envelope (design §6.9).

    Every supplied row — including an excluded envelope row — must be an exact
    ``FILE_REF`` (closed key set, canonical repository path, lowercase-hex
    ``blob_sha256``, permitted Git mode, ``kind=="file"``); a malformed value or
    a duplicate/colliding path fails closed rather than being hashed."""
    prefix = _prefix(request_id)
    validated: list[dict] = []
    for ref in file_refs:
        if not isinstance(ref, dict) or \
                set(ref) != {"path", "blob_sha256", "git_mode", "kind"}:
            raise HSCValidationError("assembled-tree FILE_REF has wrong keys")
        path = validate_path(ref["path"], "assembled-tree FILE_REF path")
        require_h(ref["blob_sha256"], "assembled-tree FILE_REF blob_sha256")
        if ref["kind"] != "file" or ref["git_mode"] not in ("100644", "100755"):
            raise HSCValidationError("assembled-tree FILE_REF kind/mode invalid")
        validated.append({"path": path, "blob_sha256": ref["blob_sha256"],
                          "git_mode": ref["git_mode"], "kind": "file"})
    seen = [ref["path"] for ref in validated]
    if len(seen) != len(set(seen)):
        raise HSCValidationError("assembled-tree FILE_REF paths are not unique")
    kept = [ref for ref in validated if not ref["path"].startswith(prefix)]
    return domain_hash(_PROJECT_TREE,
                       sorted(kept, key=lambda ref: ref["path"]))


def build_final_scope(*, program_ref: dict, work_graph_ref: dict,
                      base_commit: str, request_id: str,
                      predicted_changes: list[dict], actual_changes: list[dict],
                      realized_system_artifact_paths: list[str],
                      section_bundle_refs: list[dict],
                      assembler_binary_ref: dict,
                      assembled_tree_sha256_value: str) -> dict:
    """Construct the ``final_scope_manifest.v1`` written at the fixed
    ``final-scope.json`` envelope path. The two envelope paths are the exact
    fixed pair for this request."""
    prefix = _prefix(request_id)
    payload = {
        "program_ref": program_ref,
        "work_graph_ref": work_graph_ref,
        "base_commit": base_commit,
        "predicted_changes": predicted_changes,
        "actual_changes": actual_changes,
        "realized_system_artifact_paths": sorted(
            set(realized_system_artifact_paths)),
        "section_bundle_refs": section_bundle_refs,
        "assembler_binary_ref": assembler_binary_ref,
        "assembled_tree_sha256": assembled_tree_sha256_value,
        "envelope_paths": [f"{prefix}final-scope.json", f"{prefix}root.json"],
    }
    return make_record("final_scope_manifest.v1", payload)


def build_evidence_root(*, request_id: str, program_ref: dict,
                        parent_build_event_id: str,
                        parent_build_event_hash: str, base_commit: str,
                        work_graph_ref: dict, final_scope_ref: dict,
                        operation_log_ref: dict,
                        records_with_paths: list[tuple[dict, str]]) -> dict:
    """Construct the ``section_evidence_root.v1`` that inventories every member
    record (but never itself).

    ``records_with_paths`` is ``(record, repository_relpath)`` for every record
    the root must reach — bootstrap, program, registry, contracts, contexts,
    content, dispatch chain, native plans/inventories, attestations, findings,
    assessments, bundles, boundary/comparison reports, work graph, and final
    scope. The inventory rows carry each record's bare ``content_sha256`` and its
    unique repository path, sorted by ``(schema_version, record_id)``."""
    inventory = sorted(({
        "schema_version": record["schema_version"],
        "record_id": record[_id_field(record)],
        "content_sha256": compute_record_content_sha256(record),
        "repository_relpath": path,
    } for record, path in records_with_paths),
        key=lambda row: (row["schema_version"], row["record_id"]))
    return make_record("section_evidence_root.v1", {
        "planned_request_id": request_id,
        "program_ref": program_ref,
        "parent_build_event_id": parent_build_event_id,
        "parent_build_event_hash": parent_build_event_hash,
        "base_commit": base_commit,
        "work_graph_ref": work_graph_ref,
        "final_scope_ref": final_scope_ref,
        "record_inventory": inventory,
        "operation_log_ref": operation_log_ref,
        "record_count": len(inventory),
    })


def _id_field(record: dict) -> str:
    return next(key for key in record
               if key not in ("schema_version", "payload"))


def hsc_binding_line(*, target_commit: str, request_id: str, root_record: dict,
                     root_sha256: str, root_git_blob: str, scope_record: dict,
                     scope_sha256: str, scope_git_blob: str) -> str:
    """The one exact ``HSC_V1`` scope-list line the later ordinary Council
    request must carry (design §6.10). Validated through the canonical parser
    before it is returned, so a malformed line never escapes."""
    prefix = _prefix(request_id)
    line = (f"HSC_V1 target_commit={target_commit} "
            f"root_path={prefix}root.json "
            f"root_id={root_record['section_evidence_root_id']} "
            f"root_sha256={root_sha256} root_git_blob={root_git_blob} "
            f"scope_path={prefix}final-scope.json "
            f"scope_id={scope_record['final_scope_manifest_id']} "
            f"scope_sha256={scope_sha256} scope_git_blob={scope_git_blob}")
    parse_hsc_request_binding(line, expected_request_id=request_id)
    return line
