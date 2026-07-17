"""Native inventory production (HSC-B component 2).

The trusted host walks each root no-follow and produces the exact
``section_native_inventory.v1`` records the HSC-A validator checks. Every
descendant regular file and directory is observed with the
``linux-native-id-v1`` encoder; the root itself is represented by its root
spec. Regular files carry a byte SHA-256, directories carry null content, and
any symlink / reparse / special file (or a native identity that changes between
the identity-only and readable opens) fails closed.

Names are read as raw bytes via ``getdents64`` so a non-UTF-8 filename is
faithfully hex-encoded into ``NATIVE_REL_PATH.segments_hex`` rather than lost to
a decode.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
from typing import Any

from tools.council.schemas import domain_hash

from .core import (HSCValidationError, file_id, filesystem_id,
                   validate_native_entry)
from .native import (NativeIdentityUnavailable, fail_closed, observe_fd,
                     open_beneath)

_SYS_getdents64 = 217
_DOTGIT = b".git"
_READ_CHUNK = 1 << 20


def _readdir(fd: int) -> list[bytes]:
    """Raw byte names of a directory fd (excluding ``.`` and ``..``), via
    ``getdents64`` so arbitrary filename bytes survive."""
    names: list[bytes] = []
    buf = (ctypes.c_char * 32768)()
    os.lseek(fd, 0, os.SEEK_SET)  # getdents64 advances the offset; rewind
    while True:
        ctypes.set_errno(0)
        n = ctypes.CDLL("libc.so.6", use_errno=True).syscall(
            _SYS_getdents64, fd, ctypes.byref(buf), ctypes.sizeof(buf))
        if n < 0:
            raise NativeIdentityUnavailable(
                f"getdents64 failed (errno {ctypes.get_errno()})")
        if n == 0:
            break
        raw = bytes(buf[:n])
        offset = 0
        while offset < n:
            reclen = int.from_bytes(raw[offset + 16:offset + 18], "little")
            if reclen == 0:
                raise NativeIdentityUnavailable("malformed getdents64 record")
            name = raw[offset + 19:offset + reclen].split(b"\x00", 1)[0]
            if name not in (b".", b".."):
                names.append(name)
            offset += reclen
    return names


def _read_all(fd: int) -> bytes:
    chunks: list[bytes] = []
    while True:
        block = os.read(fd, _READ_CHUNK)
        if not block:
            break
        chunks.append(block)
    return b"".join(chunks)


def _entry(segments: list[bytes], observation: dict[str, Any],
           content_sha256: str | None, kind: str) -> dict[str, Any]:
    entry = {
        "path": {"segments_hex": [seg.hex() for seg in segments]},
        "native_identity": observation,
        "filesystem_id": filesystem_id(observation),
        "file_id": file_id(observation),
        "content_sha256": content_sha256,
        "kind": kind,
    }
    validate_native_entry(entry, "native_entry")
    return entry


def _collect(parent_fd: int, name: bytes, segments: list[bytes],
             entries: list[dict]) -> None:
    # Identity via an O_PATH open first (never blocks on a fifo/device).
    path_fd = open_beneath(parent_fd, name)
    try:
        observation = observe_fd(path_fd)
    finally:
        os.close(path_fd)
    kind = observation["file_type"]
    if kind == "regular":
        read_fd = open_beneath(parent_fd, name, readable=True)
        try:
            if observe_fd(read_fd) != observation:
                fail_closed("native identity changed between opens")
            data = _read_all(read_fd)
        finally:
            os.close(read_fd)
        entries.append(_entry(segments, observation,
                              hashlib.sha256(data).hexdigest(), "regular"))
    else:  # directory
        dir_fd = open_beneath(parent_fd, name, directory=True, readable=True)
        try:
            if observe_fd(dir_fd) != observation:
                fail_closed("native identity changed between opens")
            entries.append(_entry(segments, observation, None, "directory"))
            for child in sorted(_readdir(dir_fd)):
                _collect(dir_fd, child, segments + [child], entries)
        finally:
            os.close(dir_fd)


def walk_root(root_dir_fd: int, *, exclude_dotgit: bool = False,
              expected_dotgit_identity: dict | None = None) \
        -> list[dict[str, Any]]:
    """Every descendant of the root as a sorted, unique ``NATIVE_ENTRY`` list.

    ``exclude_dotgit`` implements the ``checkout-excluding-delegated-dotgit-v1``
    view: the ``.git`` child is excluded only after it is proven to be exactly
    one direct directory whose live native identity equals the delegated
    common-Git root (``expected_dotgit_identity``). A missing, regular-file,
    symlink, or mismatched ``.git`` fails closed."""
    names = sorted(_readdir(root_dir_fd))
    if exclude_dotgit:
        if _DOTGIT not in names:
            fail_closed("checkout view requires a .git directory")
        dotgit_fd = open_beneath(root_dir_fd, _DOTGIT, directory=True)
        try:
            dotgit = observe_fd(dotgit_fd)
        finally:
            os.close(dotgit_fd)
        if dotgit["file_type"] != "directory":
            fail_closed("checkout .git is not a directory")
        if expected_dotgit_identity is not None and \
                dotgit != expected_dotgit_identity:
            fail_closed("checkout .git identity differs from the delegated "
                        "common-Git root")
    entries: list[dict[str, Any]] = []
    for name in names:
        if exclude_dotgit and name == _DOTGIT:
            continue
        _collect(root_dir_fd, name, [name], entries)
    entries.sort(key=lambda e: tuple(
        bytes.fromhex(s) for s in e["path"]["segments_hex"]))
    decoded = [tuple(bytes.fromhex(s) for s in e["path"]["segments_hex"])
               for e in entries]
    if len(decoded) != len(set(decoded)):
        fail_closed("duplicate native path in inventory")
    return entries


def observe_root(root_dir_fd: int) -> dict[str, Any]:
    """The root directory's own observation (represented by the root spec, not
    an entry)."""
    observation = observe_fd(root_dir_fd)
    if observation["file_type"] != "directory":
        fail_closed("inventory root must be a directory")
    return observation


def inventory_content_sha256(*, native_inventory_plan_ref: dict,
                             root_spec: dict, observation_requirement: dict,
                             observer_assignment_ref: dict | None,
                             observation_workspace_id: str | None,
                             phase: str, entries: list[dict]) -> str:
    return domain_hash("council:section-native-inventory-content:v1", {
        "native_inventory_plan_ref": native_inventory_plan_ref,
        "root_spec": root_spec,
        "observation_requirement": observation_requirement,
        "observer_assignment_ref": observer_assignment_ref,
        "observation_workspace_id": observation_workspace_id,
        "phase": phase,
        "entries": entries,
    })


def build_native_inventory(*, program_ref: dict, base_commit: str,
                           native_inventory_plan_ref: dict, root_spec: dict,
                           observation_requirement: dict,
                           observer_assignment_ref: dict | None,
                           observation_workspace_id: str | None,
                           root_dir_fd: int):
    """Observe one root at one phase and return the
    ``section_native_inventory.v1`` payload (not yet a record).

    The observed root identity must equal the plan's ``root_spec`` (a swapped
    or drifted root refuses), and the emitted ``inventory_sha256`` binds the
    plan ref, root spec, observation requirement, dispatch context, phase, and
    the exact entries."""
    from .records import make_record  # local import: avoid a cycle

    exclude = root_spec["view_kind"] == "checkout-excluding-delegated-dotgit-v1"
    root_observation = observe_root(root_dir_fd)
    # The COMPLETE observation must equal the frozen plan, not only the two
    # derived ids: a mode/link-count drift changes native_mode while leaving
    # filesystem_id/file_id equal.
    if root_observation != root_spec["native_identity"]:
        fail_closed("observed root identity differs from its plan root spec")
    observed_fs = filesystem_id(root_observation)
    observed_file = file_id(root_observation)
    if (observed_fs, observed_file) != \
            (root_spec["filesystem_id"], root_spec["file_id"]):
        fail_closed("root spec ids do not reconstruct from its observation")
    entries = walk_root(
        root_dir_fd, exclude_dotgit=exclude,
        expected_dotgit_identity=root_spec["delegated_control_identity"]
        if exclude else None)
    phase = observation_requirement["phase"]
    payload = {
        "program_ref": program_ref,
        "native_inventory_plan_ref": native_inventory_plan_ref,
        "base_commit": base_commit,
        "observation_id": observation_requirement["observation_id"],
        "root_id": root_spec["root_id"],
        "observer_assignment_ref": observer_assignment_ref,
        "observation_workspace_id": observation_workspace_id,
        "phase": phase,
        "observed_root_filesystem_id": observed_fs,
        "observed_root_file_id": observed_file,
        "entries": entries,
        "inventory_sha256": inventory_content_sha256(
            native_inventory_plan_ref=native_inventory_plan_ref,
            root_spec=root_spec,
            observation_requirement=observation_requirement,
            observer_assignment_ref=observer_assignment_ref,
            observation_workspace_id=observation_workspace_id,
            phase=phase, entries=entries),
    }
    return make_record("section_native_inventory.v1", payload)
