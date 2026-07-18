"""Trusted output packager proofs (HSC-B component 7)."""

from __future__ import annotations

import hashlib
import os

import pytest

from tools.council.schemas import canonical_json
from tools.section_council import packager
from tools.section_council.core import HSCValidationError
from tools.section_council.records import (compute_record_content_sha256,
                                           record_ref, validate_record)

PROGRAM_REF = {"record_id": "a" * 64, "content_sha256": "b" * 64}
REF = {"record_id": "c" * 64, "content_sha256": "d" * 64}
RID = "first-gladiator-hsc-b-pilot-001"


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _decl(**over):
    base = {
        "audit_level": "section", "severity": "HIGH", "invariant_id": "inv-1",
        "claim": "the proposal violates inv-1", "evidence_output_relpath":
        "finding_evidence/0.txt", "reproduction_output_relpath":
        "reproduction/0.txt", "affected_path": "src/a.py",
        "blocks_local_pass": True, "status": "open",
        "predecessor_finding_ref": None, "resolution_output_relpath": None,
    }
    base.update(over)
    return base


def test_freeze_leaf_reads_every_file_and_refuses_symlink(tmp_path):
    leaf = tmp_path / "out"
    leaf.mkdir()
    (leaf / "a.json").write_bytes(b'{"x":1}')
    (leaf / "sub").mkdir()
    (leaf / "sub" / "b.txt").write_bytes(b"hello")
    fd = os.open(str(leaf), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        frozen = packager.freeze_leaf(fd)
    finally:
        os.close(fd)
    assert frozen == {"a.json": b'{"x":1}', "sub/b.txt": b"hello"}
    # a symlink in the leaf fails closed
    os.symlink(str(tmp_path), str(leaf / "escape"))
    fd = os.open(str(leaf), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        with pytest.raises(HSCValidationError, match="symlink"):
            packager.freeze_leaf(fd)
    finally:
        os.close(fd)


def test_content_emitter_binds_exact_bytes():
    em = packager.ContentEmitter(RID)
    data = b'{"proposal":true}'
    rec = em.wrap(PROGRAM_REF, "proposal", data, media_type="application/json")
    assert validate_record(rec) is not None
    p = rec["payload"]
    assert p["artifact_type"] == "proposal"
    assert p["blob_sha256"] == _sha(data) and p["byte_length"] == len(data)
    assert p["storage_relpath"].startswith(
        f"artifacts/section-council/{RID}/content/")
    assert em.blobs[p["storage_relpath"]] == data
    # fresh slot each wrap
    rec2 = em.wrap(PROGRAM_REF, "diff_preview", b"x", media_type="text/plain")
    assert rec2["payload"]["storage_relpath"] != p["storage_relpath"]


def test_output_inventory_bytes_sorted_tuples():
    em = packager.ContentEmitter(RID)
    a = em.wrap(PROGRAM_REF, "finding_declaration", b'{"k":2}')
    b = em.wrap(PROGRAM_REF, "finding_evidence", b"zzz")
    data = packager.output_inventory_bytes([b, a])
    rows = __import__("json").loads(data)
    assert [r["output_relpath"] for r in rows] == \
        sorted(r["output_relpath"] for r in rows)
    assert {r["blob_sha256"] for r in rows} == {_sha(b'{"k":2}'), _sha(b"zzz")}


def test_build_finding_field_by_field():
    finding = packager.build_finding(
        program_ref=PROGRAM_REF, contract_ref=REF, assessor_assignment_ref=REF,
        affected_proposal_ref=REF, finding_declaration_ref=REF, evidence_ref=REF,
        reproduction_ref=REF, resolution_evidence_ref=None,
        declaration=_decl())
    assert validate_record(finding) is not None
    p = finding["payload"]
    assert p["severity"] == "HIGH" and p["invariant_id"] == "inv-1"
    assert p["blocks_local_pass"] is True and p["status"] == "open"
    assert p["resolution_evidence_ref"] is None


def test_build_finding_rejects_unexpected_keys():
    with pytest.raises(HSCValidationError, match="unexpected keys"):
        packager.build_finding(
            program_ref=PROGRAM_REF, contract_ref=REF,
            assessor_assignment_ref=REF, affected_proposal_ref=REF,
            finding_declaration_ref=REF, evidence_ref=REF, reproduction_ref=REF,
            resolution_evidence_ref=None,
            declaration={**_decl(), "extra": 1})


def test_derive_disposition_pass_blocked_error():
    ok_checks = [{"check_id": "c1", "status": "pass", "evidence_ref": REF}]
    assert packager.derive_disposition(
        required_check_ids=["c1"], check_results=ok_checks, findings=[],
        error_reason=None) == "pass"
    # an open blocking finding -> blocked
    assert packager.derive_disposition(
        required_check_ids=["c1"], check_results=ok_checks,
        findings=[{"status": "open", "blocks_local_pass": True}],
        error_reason=None) == "blocked"
    # a failing check -> blocked
    assert packager.derive_disposition(
        required_check_ids=["c1"],
        check_results=[{"check_id": "c1", "status": "fail",
                        "evidence_ref": REF}],
        findings=[], error_reason=None) == "blocked"
    # error_reason -> error
    assert packager.derive_disposition(
        required_check_ids=["c1"], check_results=ok_checks, findings=[],
        error_reason="the check harness crashed") == "error"


def test_derive_disposition_missing_required_check_refuses():
    with pytest.raises(HSCValidationError, match="missing, duplicated"):
        packager.derive_disposition(
            required_check_ids=["c1", "c2"],
            check_results=[{"check_id": "c1", "status": "pass",
                            "evidence_ref": REF}],
            findings=[], error_reason=None)


def test_build_assessment_manifest_recomputes_inventory():
    finding = packager.build_finding(
        program_ref=PROGRAM_REF, contract_ref=REF, assessor_assignment_ref=REF,
        affected_proposal_ref=REF, finding_declaration_ref=REF, evidence_ref=REF,
        reproduction_ref=REF, resolution_evidence_ref=None,
        declaration=_decl(blocks_local_pass=False))
    slot = {finding["section_finding_id"]:
            f"artifacts/section-council/{RID}/records/finding-0.json"}
    checks = [{"check_id": "c1", "status": "pass", "evidence_ref": REF}]
    manifest = packager.build_assessment_manifest(
        program_ref=PROGRAM_REF, contract_ref=REF, work_item_id="1" * 64,
        assessor_assignment_ref=REF, assessor_context_ref=REF, proposal_ref=REF,
        assessment_declaration_ref=REF, assessor_output_inventory_ref=REF,
        check_declaration_refs=[REF], check_results=checks,
        finding_records=[finding], finding_record_relpaths=slot,
        open_blocking_count=0, local_assessment="pass", error_reason=None,
        predecessor_assessment_ref=None)
    assert validate_record(manifest) is not None
    p = manifest["payload"]
    assert p["finding_count"] == 1
    assert p["finding_refs"] == [record_ref(finding)]
    assert p["finding_inventory_sha256"] == packager.finding_inventory_sha256(
        [finding], slot)
    assert p["local_assessment"] == "pass"
