"""Evidence-root finalization constructor proofs (HSC-B component 8b)."""

from __future__ import annotations

import hashlib

import pytest

from tools.section_council import evidence_root
from tools.section_council.core import parse_hsc_request_binding
from tools.section_council.records import (compute_record_content_sha256,
                                           make_record, record_ref,
                                           validate_record)

PROGRAM_REF = {"record_id": "a" * 64, "content_sha256": "b" * 64}
REF = {"record_id": "c" * 64, "content_sha256": "d" * 64}
RID = "first-gladiator-hsc-b-pilot-001"
COMMIT = "e" * 40
EVENT = "001609-abcdef12"


def test_assembled_tree_excludes_own_envelope():
    prefix = f"artifacts/section-council/{RID}/"
    refs = [
        {"path": "src/a.py", "blob_sha256": "1" * 64, "git_mode": "100644",
         "kind": "file"},
        {"path": f"{prefix}root.json", "blob_sha256": "2" * 64,
         "git_mode": "100644", "kind": "file"},
    ]
    got = evidence_root.assembled_tree_sha256(refs, RID)
    # equals the hash of the same array with the envelope entry removed
    only_project = [refs[0]]
    assert got == evidence_root.assembled_tree_sha256(only_project, RID)


def _prediction():
    return {"path": "src/new.py", "kind": "add", "rename_source": None,
            "blob_before": None, "mode_before": None, "required": True}


def _actual():
    return {"path": "src/new.py", "kind": "add", "rename_source": None,
            "blob_before": None, "blob_after": "9" * 64, "mode_before": None,
            "mode_after": "100644"}


def test_build_final_scope_validates():
    scope = evidence_root.build_final_scope(
        program_ref=PROGRAM_REF, work_graph_ref=REF, base_commit=COMMIT,
        request_id=RID, predicted_changes=[_prediction()],
        actual_changes=[_actual()],
        realized_system_artifact_paths=[
            f"artifacts/section-council/{RID}/records/000.json"],
        section_bundle_refs=[REF], assembler_binary_ref=REF,
        assembled_tree_sha256_value="7" * 64)
    assert validate_record(scope) is not None
    p = scope["payload"]
    assert p["envelope_paths"] == [
        f"artifacts/section-council/{RID}/final-scope.json",
        f"artifacts/section-council/{RID}/root.json"]


def test_build_evidence_root_inventory_reconstructs():
    # two arbitrary member records at distinct repo paths
    content = make_record("section_content_record.v1", {
        "program_ref": PROGRAM_REF, "artifact_type": "operation_log",
        "storage_relpath": f"artifacts/section-council/{RID}/content/op",
        "media_type": "application/json", "byte_length": 2,
        "blob_sha256": hashlib.sha256(b"{}").hexdigest(),
        "producer_assignment_ref": None, "parent_content_refs": []})
    members = [
        (content, f"artifacts/section-council/{RID}/records/000.json"),
    ]
    root = evidence_root.build_evidence_root(
        request_id=RID, program_ref=PROGRAM_REF, parent_build_event_id=EVENT,
        parent_build_event_hash="f" * 64, base_commit=COMMIT,
        work_graph_ref=REF, final_scope_ref=REF, operation_log_ref=REF,
        records_with_paths=members)
    assert validate_record(root) is not None
    p = root["payload"]
    assert p["record_count"] == 1 == len(p["record_inventory"])
    row = p["record_inventory"][0]
    assert row["content_sha256"] == compute_record_content_sha256(content)
    assert row["schema_version"] == "section_content_record.v1"
    # the root does not inventory itself
    assert all(r["record_id"] != root["section_evidence_root_id"]
               for r in p["record_inventory"])


def test_hsc_binding_line_round_trips():
    scope = evidence_root.build_final_scope(
        program_ref=PROGRAM_REF, work_graph_ref=REF, base_commit=COMMIT,
        request_id=RID, predicted_changes=[_prediction()],
        actual_changes=[_actual()],
        realized_system_artifact_paths=[
            f"artifacts/section-council/{RID}/records/000.json"],
        section_bundle_refs=[REF], assembler_binary_ref=REF,
        assembled_tree_sha256_value="7" * 64)
    root = evidence_root.build_evidence_root(
        request_id=RID, program_ref=PROGRAM_REF, parent_build_event_id=EVENT,
        parent_build_event_hash="f" * 64, base_commit=COMMIT,
        work_graph_ref=REF, final_scope_ref=record_ref(scope),
        operation_log_ref=REF, records_with_paths=[(scope,
            f"artifacts/section-council/{RID}/final-scope.json")])
    line = evidence_root.hsc_binding_line(
        target_commit=COMMIT, request_id=RID, root_record=root,
        root_sha256="a" * 64, root_git_blob="b" * 40, scope_record=scope,
        scope_sha256="c" * 64, scope_git_blob="d" * 40)
    binding = parse_hsc_request_binding(line, expected_request_id=RID)
    assert binding.target_commit == COMMIT
    assert binding.root_id == root["section_evidence_root_id"]
    assert binding.scope_id == scope["final_scope_manifest_id"]


def test_hsc_binding_line_rejects_malformed_target_commit():
    scope = evidence_root.build_final_scope(
        program_ref=PROGRAM_REF, work_graph_ref=REF, base_commit=COMMIT,
        request_id=RID, predicted_changes=[_prediction()],
        actual_changes=[_actual()],
        realized_system_artifact_paths=[
            f"artifacts/section-council/{RID}/records/000.json"],
        section_bundle_refs=[REF], assembler_binary_ref=REF,
        assembled_tree_sha256_value="7" * 64)
    root = evidence_root.build_evidence_root(
        request_id=RID, program_ref=PROGRAM_REF, parent_build_event_id=EVENT,
        parent_build_event_hash="f" * 64, base_commit=COMMIT,
        work_graph_ref=REF, final_scope_ref=record_ref(scope),
        operation_log_ref=REF, records_with_paths=[(scope,
            f"artifacts/section-council/{RID}/final-scope.json")])
    # a target_commit that is not a 40-hex git id must fail the canonical parse
    # rather than escape as a valid binding line
    with pytest.raises(Exception):
        evidence_root.hsc_binding_line(
            target_commit="not-a-commit", request_id=RID,
            root_record=root, root_sha256="a" * 64, root_git_blob="b" * 40,
            scope_record=scope, scope_sha256="c" * 64, scope_git_blob="d" * 40)
