"""Dispatch journal chain minting proofs (HSC-B component 5)."""

from __future__ import annotations

import os

import pytest

from tools.council.schemas import domain_hash
from tools.section_council import native, scheduler
from tools.section_council.core import file_id, filesystem_id
from tools.section_council.inventory import observe_root
from tools.section_council.native import NativeIdentityUnavailable
from tools.section_council.records import record_ref, validate_record


def _anchor(journal_dir, *, anchor_name="scheduler-journal", identity=None):
    """The enrolled trusted-host anchor descriptor for the journal directory."""
    fd = os.open(str(journal_dir), os.O_RDONLY | os.O_DIRECTORY)
    try:
        obs = observe_root(fd)
    finally:
        os.close(fd)
    if identity is not None:
        obs = identity
    return {"anchor_name": anchor_name, "native_identity": obs,
            "filesystem_id": filesystem_id(obs), "file_id": file_id(obs)}

_AVAILABLE = True
try:
    native.probe_availability()
except NativeIdentityUnavailable:
    _AVAILABLE = False

requires_native = pytest.mark.skipif(
    not _AVAILABLE, reason="linux-native-id-v1 primitives unavailable")

PROGRAM_REF = {"record_id": "3" * 64, "content_sha256": "4" * 64}
REGISTRY_REF = {"record_id": "5" * 64, "content_sha256": "6" * 64}
CONTRACT_REF = {"record_id": "7" * 64, "content_sha256": "8" * 64}
CONTEXT_REF = {"record_id": "9" * 64, "content_sha256": "a" * 64}
PROFILE_REF = {"record_id": "b" * 64, "content_sha256": "c" * 64}


def _mint(journal_dir, role="builder",
          barrier_status="ready", predecessor=None, journal_anchor=None):
    if journal_anchor is None:
        journal_anchor = _anchor(journal_dir)
    fd = os.open(str(journal_dir), os.O_RDONLY | os.O_DIRECTORY)
    try:
        return scheduler.mint_dispatch(
            program_ref=PROGRAM_REF, registry_ref=REGISTRY_REF,
            contract_ref=CONTRACT_REF, context_ref=CONTEXT_REF,
            sandbox_profile_ref=PROFILE_REF,
            scheduler_authority_id="1" * 64,
            scheduler_writer_principal_id="scheduler-writer",
            scheduler_writer_control_id="d" * 64,
            launcher_writer_principal_id="launcher-writer",
            launcher_writer_control_id="e" * 64,
            work_item_id="2" * 64, role=role, principal_id=f"{role}-1",
            authority_control_id="f" * 64,
            principal_credential_digest="0" * 64,
            launcher_executable_sha256="7" * 64,
            session_nonce=("b" if role == "builder" else "a") * 64,
            attempt=0, workspace_id="1" * 64, output_leaf=f"{role}-leaf",
            journal_root_fd=fd, journal_owner_principal_id="scheduler-writer",
            journal_owner_control_id="d" * 64, journal_anchor=journal_anchor,
            predecessor_manifest=predecessor, barrier_status=barrier_status)
    finally:
        os.close(fd)


@requires_native
def test_dispatch_chain_records_validate(tmp_path):
    journal = tmp_path / "journal"
    journal.mkdir(mode=0o700)
    os.chmod(str(journal), 0o700)
    chain = _mint(journal)
    for record in chain.records():
        assert validate_record(record) is not None


@requires_native
def test_manifest_entries_bind_dispatch_records(tmp_path):
    journal = tmp_path / "journal"
    journal.mkdir()
    os.chmod(str(journal), 0o700)
    chain = _mint(journal)
    entries = chain.manifest["payload"]["entries"]
    assert [e["entry_kind"] for e in entries] == [
        "authorization", "assignment", "receipt"]
    assert [e["writer_role"] for e in entries] == [
        "scheduler", "scheduler", "launcher"]
    assert [e["sequence"] for e in entries] == [0, 1, 2]
    assert chain.manifest["payload"]["last_sequence"] == 2
    assert chain.manifest["payload"]["predecessor_journal_manifest_ref"] is None
    # each entry binds its dispatch record's exact ref + entry hash
    for entry, record in zip(entries, (chain.authorization, chain.assignment,
                                       chain.receipt)):
        assert entry["record_ref"] == record_ref(record)
        assert entry["entry_sha256"] == record["payload"][
            "scheduler_journal_entry_sha256"]
    # journal_mode is the exact string 0700 and native mode encodes it
    assert chain.manifest["payload"]["journal_mode"] == "0700"
    obs = chain.manifest["payload"]["journal_root_native_identity"]
    assert obs["native_mode"] & 0o7777 == 0o700


@requires_native
def test_second_manifest_chains_from_predecessor(tmp_path):
    journal = tmp_path / "journal"
    journal.mkdir()
    os.chmod(str(journal), 0o700)
    first = _mint(journal, role="builder")
    second = _mint(journal, role="assessor", predecessor=first.manifest)
    assert second.manifest["payload"]["first_sequence"] == 3
    assert second.manifest["payload"]["last_sequence"] == 5
    assert second.manifest["payload"][
        "predecessor_journal_manifest_ref"] == record_ref(first.manifest)


@requires_native
def test_non_0700_journal_root_refuses(tmp_path):
    journal = tmp_path / "journal"
    journal.mkdir()
    os.chmod(str(journal), 0o755)
    with pytest.raises(NativeIdentityUnavailable, match="0700 protected"):
        _mint(journal)


@requires_native
def test_refused_barrier_receipt_is_recorded(tmp_path):
    journal = tmp_path / "journal"
    journal.mkdir()
    os.chmod(str(journal), 0o700)
    chain = _mint(journal, barrier_status="refused")
    assert chain.receipt["payload"]["barrier_status"] == "refused"
    assert validate_record(chain.receipt) is not None


@requires_native
def test_finding4_records_persisted_create_exclusively(tmp_path):
    # Regression (audit 001635 finding 4): mint must PERSIST each dispatch
    # record create-exclusively in the protected journal by its sequence.
    from tools.council.schemas import canonical_json
    journal = tmp_path / "journal"
    journal.mkdir()
    os.chmod(str(journal), 0o700)
    chain = _mint(journal)
    names = sorted(p.name for p in journal.iterdir())
    assert names == ["000000000000.json", "000000000001.json",
                     "000000000002.json"]
    persisted = (journal / "000000000000.json").read_bytes()
    assert persisted == canonical_json(chain.authorization).encode("utf-8")


@requires_native
def test_finding4_duplicate_sequence_fails_closed(tmp_path):
    # A replayed dispatch at an already-committed sequence must fail closed
    # rather than overwrite the persisted journal entry.
    journal = tmp_path / "journal"
    journal.mkdir()
    os.chmod(str(journal), 0o700)
    _mint(journal)  # persists sequences 0,1,2
    with pytest.raises(NativeIdentityUnavailable, match="already persisted"):
        _mint(journal)  # predecessor=None -> derives 0 again -> collision


@requires_native
def test_finding4_locator_anchor_is_canonical_native_anchor(tmp_path):
    # The manifest locator anchor id must be the canonical council:native-
    # anchor:v1 reconstruction over the enrolled anchor, never a caller-
    # supplied control id and never a bare file id.
    journal = tmp_path / "journal"
    journal.mkdir()
    os.chmod(str(journal), 0o700)
    anchor = _anchor(journal)
    chain = _mint(journal, journal_anchor=anchor)
    payload = chain.manifest["payload"]
    anchor_id = payload["journal_root_locator"]["anchor_id"]
    expected = domain_hash("council:native-anchor:v1", {
        "anchor_name": anchor["anchor_name"],
        "file_id": anchor["file_id"],
        "filesystem_id": anchor["filesystem_id"],
        "native_identity": anchor["native_identity"]})
    assert anchor_id == expected
    assert anchor_id != payload["journal_root_file_id"]
    assert anchor_id != "d" * 64  # the caller journal_owner_control_id


@requires_native
def test_finding_s3a_wrong_enrolled_anchor_refuses(tmp_path):
    # Regression (audit 001649 F1): a journal_anchor whose enrolled identity
    # differs from the observed directory must refuse.
    journal = tmp_path / "journal"
    journal.mkdir()
    os.chmod(str(journal), 0o700)
    other = tmp_path / "other"
    other.mkdir()
    os.chmod(str(other), 0o700)
    wrong = _anchor(other)  # a different directory's enrolled identity
    with pytest.raises(NativeIdentityUnavailable,
                       match="differs from its enrolled anchor"):
        _mint(journal, journal_anchor=wrong)


@requires_native
def test_finding_s3b_0755_journal_leaves_no_records(tmp_path):
    # A non-0700 journal must refuse BEFORE any record is persisted.
    journal = tmp_path / "journal"
    journal.mkdir()
    os.chmod(str(journal), 0o755)
    with pytest.raises(NativeIdentityUnavailable, match="0700 protected"):
        _mint(journal)
    assert list(journal.iterdir()) == []  # nothing written on refusal


@requires_native
def test_finding_s3c_stalled_write_fails_closed(tmp_path, monkeypatch):
    # A write that does not advance (returns 0) must fail closed rather than
    # mint a manifest over absent bytes.
    journal = tmp_path / "journal"
    journal.mkdir()
    os.chmod(str(journal), 0o700)
    monkeypatch.setattr(scheduler.os, "write", lambda fd, data: 0)
    with pytest.raises(NativeIdentityUnavailable, match="did not advance"):
        _mint(journal)


@requires_native
def test_finding_s3d_persisted_bytes_mismatch_fails_closed(tmp_path,
                                                           monkeypatch):
    # If the persisted bytes differ from the canonical record (a write that
    # claims full length but stores less), mint must fail closed.
    journal = tmp_path / "journal"
    journal.mkdir()
    os.chmod(str(journal), 0o700)
    real_write = os.write

    def truncating_write(fd, data):
        real_write(fd, data[: len(data) // 2])
        return len(data)  # lie about the count so the loop "completes"

    monkeypatch.setattr(scheduler.os, "write", truncating_write)
    with pytest.raises(NativeIdentityUnavailable,
                       match="persisted bytes differ"):
        _mint(journal)
