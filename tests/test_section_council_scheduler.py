"""Dispatch journal chain minting proofs (HSC-B component 5)."""

from __future__ import annotations

import os

import pytest

from tools.council.schemas import domain_hash
from tools.section_council import native, scheduler
from tools.section_council.native import NativeIdentityUnavailable
from tools.section_council.records import record_ref, validate_record

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
          barrier_status="ready", predecessor=None):
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
            journal_owner_control_id="d" * 64,
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
    with pytest.raises(NativeIdentityUnavailable, match="0700 directory"):
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
def test_finding4_locator_anchor_reconstructed_not_caller_supplied(tmp_path):
    # The manifest locator anchor id must be the observed journal directory's
    # own file id, never the caller-supplied journal_owner_control_id.
    journal = tmp_path / "journal"
    journal.mkdir()
    os.chmod(str(journal), 0o700)
    chain = _mint(journal)
    payload = chain.manifest["payload"]
    anchor_id = payload["journal_root_locator"]["anchor_id"]
    assert anchor_id == payload["journal_root_file_id"]
    assert anchor_id != "d" * 64  # the caller journal_owner_control_id
