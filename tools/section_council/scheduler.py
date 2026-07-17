"""Scheduler-minted dispatch journal chain (HSC-B component 5).

The trusted scheduler and launcher write three journaled records per dispatch —
``section_launcher_authorization.v1`` (ordinal 0, scheduler), ``section_assignment.v1``
(ordinal 1, scheduler), and ``section_launcher_receipt.v1`` (ordinal 2, launcher) —
and export the completed triple as one ``section_scheduler_journal_manifest.v1``.
The journal lives in an OS-protected directory (mode ``0700``) that is absent
from every worker namespace; its stable native identity is observed with the
``linux-native-id-v1`` encoder and bound into the manifest id.

This module mints those records with the exact frozen entry-hash domains,
sequences, and writer identities the HSC-A validator checks. Actually launching
a confined worker (and therefore stamping a ``ready``/``refused`` barrier
status from real confinement) is the launcher's job (component 4); here the
receipt's barrier status is supplied by the caller.
"""

from __future__ import annotations

import os
from typing import Any

from tools.council.schemas import domain_hash

from .core import HSCValidationError, file_id, filesystem_id
from .inventory import observe_root
from .native import fail_closed
from .records import make_record, record_ref

_AUTH_ENTRY = "council:section-launch-authorization-entry:v1"
_ASSIGN_ENTRY = "council:section-assignment-entry:v1"
_RECEIPT_ENTRY = "council:section-launch-receipt-entry:v1"
_JOURNAL_ROOT = "council:scheduler-journal-root:v1"
_NATIVE_ANCHOR = "council:native-anchor:v1"
_MODE_0700 = "0700"


def _entry_hash(domain: str, payload: dict[str, Any]) -> str:
    preimage = dict(payload)
    preimage.pop("scheduler_journal_entry_sha256")
    return domain_hash(domain, preimage)


def _verify_journal_anchor(journal_root_fd: int, journal_anchor: dict) -> dict:
    """Observe the open journal directory and require it to BE the enrolled
    anchor before any write occurs. The enrolled ``journal_anchor`` descriptor
    is the trusted root-owned registry row — ``anchor_name`` plus the frozen
    ``NATIVE_ID_OBSERVATION`` and its two derived ids. The observed directory
    must byte-equal that observation, reconstruct the same ids, be a real 0700
    protected directory, and reconstruct the canonical
    ``council:native-anchor:v1`` id. A caller never supplies the anchor id."""
    observation = observe_root(journal_root_fd)  # requires a directory
    if observation["native_mode"] & 0o7777 != 0o700:
        fail_closed("journal root is not a 0700 protected directory")
    if observation != journal_anchor["native_identity"]:
        fail_closed("journal directory differs from its enrolled anchor")
    fs_id = filesystem_id(observation)
    file = file_id(observation)
    if (fs_id, file) != (journal_anchor["filesystem_id"],
                         journal_anchor["file_id"]):
        fail_closed("journal anchor ids do not reconstruct from its observation")
    anchor_id = domain_hash(_NATIVE_ANCHOR, {
        "anchor_name": journal_anchor["anchor_name"],
        "file_id": file,
        "filesystem_id": fs_id,
        "native_identity": observation,
    })
    return {"observation": observation, "filesystem_id": fs_id,
            "file_id": file, "anchor_id": anchor_id,
            "anchor_name": journal_anchor["anchor_name"]}


def _persist_records(journal_root_fd: int, first_sequence: int,
                     records: tuple[dict, dict, dict]) -> None:
    """Write each canonical record's exact bytes create-exclusively (no-follow)
    into the protected journal directory by its sequence, then fsync, reopen
    no-follow, reread, and require the persisted bytes to byte-equal the
    canonical record before returning. A short/partial write, a truncation, or
    an already-present sequence file fails closed, so a minted manifest can only
    describe bytes that are actually present in the journal. The journal
    directory itself is fsynced so the entries survive a crash."""
    from tools.council.schemas import canonical_json  # local: avoid cycle

    for offset, record in enumerate(records):
        name = f"{first_sequence + offset:012d}.json"
        data = canonical_json(record).encode("utf-8")
        try:
            fd = os.open(name,
                         os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=journal_root_fd)
        except FileExistsError:
            fail_closed(f"journal sequence {name} already persisted")
        try:
            written = 0
            while written < len(data):
                n = os.write(fd, data[written:])
                if n <= 0:
                    fail_closed(f"journal sequence {name} write did not advance")
                written += n
            os.fsync(fd)
        finally:
            os.close(fd)
        # Reopen no-follow and require the persisted bytes to equal the record.
        rfd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=journal_root_fd)
        try:
            chunks: list[bytes] = []
            while True:
                block = os.read(rfd, 1 << 20)
                if not block:
                    break
                chunks.append(block)
        finally:
            os.close(rfd)
        if b"".join(chunks) != data:
            fail_closed(f"journal sequence {name} persisted bytes differ")
    os.fsync(journal_root_fd)


class DispatchChain:
    """The four minted records of one dispatch, in construction order."""

    def __init__(self, authorization, assignment, receipt, manifest):
        self.authorization = authorization
        self.assignment = assignment
        self.receipt = receipt
        self.manifest = manifest

    def records(self) -> list[dict]:
        return [self.authorization, self.assignment, self.receipt,
                self.manifest]


def mint_dispatch(*, program_ref: dict, registry_ref: dict,
                  contract_ref: dict, context_ref: dict,
                  sandbox_profile_ref: dict, scheduler_authority_id: str,
                  scheduler_writer_principal_id: str,
                  scheduler_writer_control_id: str,
                  launcher_writer_principal_id: str,
                  launcher_writer_control_id: str, work_item_id: str,
                  role: str, principal_id: str, authority_control_id: str,
                  principal_credential_digest: str,
                  launcher_executable_sha256: str, session_nonce: str,
                  attempt: int, workspace_id: str, output_leaf: str,
                  journal_root_fd: int, journal_owner_principal_id: str,
                  journal_owner_control_id: str, journal_anchor: dict,
                  predecessor_manifest=None, barrier_status: str = "ready") \
        -> DispatchChain:
    """Mint the authorization/assignment/receipt/manifest chain for one
    dispatch and PERSIST each record create-exclusively in the protected
    journal directory. ``journal_root_fd`` is an open descriptor for that
    directory, which must be a real ``0700`` directory (its stable native
    identity is bound into the manifest id). The sequence range is DERIVED
    from the predecessor manifest — an arbitrary gap cannot be supplied."""
    if role not in ("builder", "assessor"):
        fail_closed("dispatch role must be builder or assessor")
    if barrier_status not in ("ready", "refused"):
        fail_closed("barrier status must be ready or refused")
    # Verify the enrolled protected 0700 journal anchor BEFORE any write, so an
    # ineligible directory (wrong identity, or not 0700) is refused with the
    # journal left untouched.
    verified_anchor = _verify_journal_anchor(journal_root_fd, journal_anchor)
    # Contiguous continuity is derived, never accepted from the caller.
    if predecessor_manifest is None:
        first_sequence = 0
    else:
        first_sequence = predecessor_manifest["payload"]["last_sequence"] + 1

    common = {
        "program_ref": program_ref,
        "principal_registry_ref": registry_ref,
        "scheduler_authority_id": scheduler_authority_id,
        "scheduler_journal_sequence": first_sequence,
        "scheduler_journal_entry_sha256": "0" * 64,
        "contract_ref": contract_ref,
        "work_item_id": work_item_id,
        "role": role,
        "principal_id": principal_id,
        "authority_control_id": authority_control_id,
        "principal_credential_digest": principal_credential_digest,
        "launcher_executable_sha256": launcher_executable_sha256,
        "session_nonce": session_nonce,
        "attempt": attempt,
        "context_ref": context_ref,
        "sandbox_profile_ref": sandbox_profile_ref,
        "workspace_id": workspace_id,
        "output_leaf": output_leaf,
    }
    common["scheduler_journal_entry_sha256"] = _entry_hash(_AUTH_ENTRY, common)
    authorization = make_record("section_launcher_authorization.v1", common)

    assignment_payload = {key: value for key, value in common.items()
                          if key != "launcher_executable_sha256"}
    assignment_payload["scheduler_journal_sequence"] = first_sequence + 1
    assignment_payload["launcher_authorization_ref"] = record_ref(authorization)
    assignment_payload["scheduler_journal_entry_sha256"] = _entry_hash(
        _ASSIGN_ENTRY, assignment_payload)
    assignment = make_record("section_assignment.v1", assignment_payload)

    receipt_payload = {key: value for key, value in common.items()
                       if key not in ("principal_registry_ref", "contract_ref",
                                      "work_item_id")}
    receipt_payload["authorization_ref"] = record_ref(authorization)
    receipt_payload["assignment_ref"] = record_ref(assignment)
    receipt_payload["scheduler_journal_sequence"] = first_sequence + 2
    receipt_payload["barrier_status"] = barrier_status
    receipt_payload["scheduler_journal_entry_sha256"] = _entry_hash(
        _RECEIPT_ENTRY, receipt_payload)
    receipt = make_record("section_launcher_receipt.v1", receipt_payload)

    # Persist each canonical record create-exclusively in the protected
    # journal directory by its sequence, and fsync, before the manifest is
    # minted over those persisted bytes.
    _persist_records(journal_root_fd, first_sequence,
                     (authorization, assignment, receipt))

    manifest = _mint_manifest(
        program_ref=program_ref, registry_ref=registry_ref,
        scheduler_authority_id=scheduler_authority_id,
        verified_anchor=verified_anchor,
        journal_owner_principal_id=journal_owner_principal_id,
        journal_owner_control_id=journal_owner_control_id,
        first_sequence=first_sequence,
        predecessor_manifest=predecessor_manifest,
        scheduler_writer_principal_id=scheduler_writer_principal_id,
        scheduler_writer_control_id=scheduler_writer_control_id,
        launcher_writer_principal_id=launcher_writer_principal_id,
        launcher_writer_control_id=launcher_writer_control_id,
        dispatch=(authorization, assignment, receipt))
    return DispatchChain(authorization, assignment, receipt, manifest)


def _mint_manifest(*, program_ref, registry_ref, scheduler_authority_id,
                   verified_anchor, journal_owner_principal_id,
                   journal_owner_control_id, first_sequence,
                   predecessor_manifest, scheduler_writer_principal_id,
                   scheduler_writer_control_id, launcher_writer_principal_id,
                   launcher_writer_control_id, dispatch):
    from .core import locator_sha256  # local: avoid cycle at import

    # The verified enrolled anchor (observed + required 0700 before persistence)
    # supplies the identity; the locator anchor id is the canonical
    # council:native-anchor:v1 reconstruction, never a caller-supplied id.
    observation = verified_anchor["observation"]
    fs_id = verified_anchor["filesystem_id"]
    file = verified_anchor["file_id"]
    locator = {
        "platform": "linux-bwrap-v1",
        "anchor_name": verified_anchor["anchor_name"],
        "anchor_id": verified_anchor["anchor_id"],
        "segments_hex": [],
        "resolution": "openat2-beneath-no-magiclinks-no-symlinks-v1",
    }
    journal_root_id = domain_hash(_JOURNAL_ROOT, {
        "journal_mode": _MODE_0700,
        "journal_owner_control_id": journal_owner_control_id,
        "journal_owner_principal_id": journal_owner_principal_id,
        "journal_root_file_id": file,
        "journal_root_filesystem_id": fs_id,
        "journal_root_locator_sha256": locator_sha256(locator),
        "principal_registry_ref": registry_ref,
        "program_ref": program_ref,
    })
    kinds = ("authorization", "assignment", "receipt")
    writer_roles = ("scheduler", "scheduler", "launcher")
    writer_principals = (scheduler_writer_principal_id,
                         scheduler_writer_principal_id,
                         launcher_writer_principal_id)
    writer_controls = (scheduler_writer_control_id, scheduler_writer_control_id,
                       launcher_writer_control_id)
    entries = [{
        "ordinal": ordinal,
        "sequence": first_sequence + ordinal,
        "entry_kind": kinds[ordinal],
        "record_ref": record_ref(dispatch[ordinal]),
        "entry_sha256": dispatch[ordinal]["payload"][
            "scheduler_journal_entry_sha256"],
        "writer_role": writer_roles[ordinal],
        "writer_principal_id": writer_principals[ordinal],
        "writer_control_id": writer_controls[ordinal],
    } for ordinal in range(3)]
    payload = {
        "program_ref": program_ref,
        "principal_registry_ref": registry_ref,
        "scheduler_authority_id": scheduler_authority_id,
        "journal_root_id": journal_root_id,
        "journal_root_locator": locator,
        "journal_root_locator_sha256": locator_sha256(locator),
        "journal_root_native_identity": observation,
        "journal_root_filesystem_id": fs_id,
        "journal_root_file_id": file,
        "journal_owner_principal_id": journal_owner_principal_id,
        "journal_owner_control_id": journal_owner_control_id,
        "journal_mode": _MODE_0700,
        "predecessor_journal_manifest_ref": (
            record_ref(predecessor_manifest) if predecessor_manifest else None),
        "first_sequence": first_sequence,
        "last_sequence": first_sequence + 2,
        "entries": entries,
    }
    return make_record("section_scheduler_journal_manifest.v1", payload)
