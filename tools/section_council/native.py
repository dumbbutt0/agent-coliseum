"""The ``linux-native-id-v1`` native-identity encoder (HSC-B foundation).

This is the trusted-host observation primitive every writable HSC executor
component depends on. Per the frozen design (§6.0), the host opens each target
with ``openat2`` from an enrolled anchor using ``O_PATH|O_NOFOLLOW`` and
exactly ``RESOLVE_BENEATH|RESOLVE_NO_MAGICLINKS|RESOLVE_NO_SYMLINKS``, then
captures a ``statx`` mount id, ``fstat`` device/inode/type/link-count/mode, the
two ``fstatfs`` fsid words, and a persistent ``name_to_handle_at`` file handle,
re-observes, and requires every identity field to be equal. If any required
primitive is unavailable it raises :class:`NativeIdentityUnavailable` — writable
hierarchical execution is then ineligible and the caller must fall back to the
sequential Council (never to an unconfined worker).

The emitted observation is exactly the ``NATIVE_ID_OBSERVATION`` shape the
HSC-A validator (:mod:`tools.section_council.core`) already checks, and its
derived ``filesystem_id``/``file_id`` reconstruct under the same domains.
"""

from __future__ import annotations

import ctypes
import os
from typing import Any

from .core import (HSCValidationError, file_id, filesystem_id,
                   validate_native_observation)


class NativeIdentityUnavailable(HSCValidationError):
    """A required native-identity primitive is unavailable, so the
    ``linux-native-id-v1`` profile is ineligible (fail closed)."""


# ----------------------------------------------------------------- constants

_NATIVE_PROFILE = "linux-native-id-v1"

# openat2(2) resolve flags (uapi/linux/openat2.h).
RESOLVE_NO_MAGICLINKS = 0x02
RESOLVE_NO_SYMLINKS = 0x04
RESOLVE_BENEATH = 0x08
_RESOLVE = RESOLVE_BENEATH | RESOLVE_NO_MAGICLINKS | RESOLVE_NO_SYMLINKS

O_PATH = 0o10000000
O_NOFOLLOW = 0o400000
O_DIRECTORY = 0o200000
O_RDONLY = 0
AT_EMPTY_PATH = 0x1000
AT_SYMLINK_NOFOLLOW = 0x100

# x86_64 syscall numbers.
_SYS_openat2 = 437
_SYS_statx = 332
_SYS_name_to_handle_at = 303
_SYS_fstatfs = 138

STATX_MNT_ID = 0x00001000
STATX_BASIC = 0x000007FF
_STATX_MNT_ID_OFFSET = 144  # byte offset of stx_mnt_id in struct statx
_STATFS_FSID_OFFSET = 56    # byte offset of f_fsid in struct statfs (x86_64)
_MAX_HANDLE_SZ = 128

S_IFMT = 0o170000
S_IFREG = 0o100000
S_IFDIR = 0o040000

_libc = ctypes.CDLL("libc.so.6", use_errno=True)


class _open_how(ctypes.Structure):
    _fields_ = [("flags", ctypes.c_uint64), ("mode", ctypes.c_uint64),
                ("resolve", ctypes.c_uint64)]


class _file_handle(ctypes.Structure):
    _fields_ = [("handle_bytes", ctypes.c_uint32),
                ("handle_type", ctypes.c_int32),
                ("f_handle", ctypes.c_ubyte * _MAX_HANDLE_SZ)]


def _syscall(number: int, *args) -> int:
    ctypes.set_errno(0)
    result = _libc.syscall(number, *args)
    return result


# --------------------------------------------------------------- primitives

def open_beneath(anchor_fd: int, name: bytes, *, directory: bool = False,
                 readable: bool = False) -> int:
    """Open ``name`` relative to ``anchor_fd`` with the frozen no-follow
    resolution. Never follows a symlink, magic link, or an escape above the
    anchor. Returns an ``O_PATH`` descriptor for identity-only use, or an
    ``O_RDONLY`` descriptor (``readable=True``) for content/listing. The
    native-identity fields are the same under either mode."""
    if not isinstance(name, bytes):
        fail_closed("openat2 name must be bytes")
    access = O_RDONLY if readable else O_PATH
    flags = access | O_NOFOLLOW | (O_DIRECTORY if directory else 0)
    how = _open_how(flags, 0, _RESOLVE)
    fd = _syscall(_SYS_openat2, anchor_fd, name, ctypes.byref(how),
                  ctypes.sizeof(how))
    if fd < 0:
        errno = ctypes.get_errno()
        raise NativeIdentityUnavailable(
            f"openat2 refused {name!r} (errno {errno})")
    return fd


def openat2_beneath(anchor_fd: int, name: bytes, *,
                    directory: bool = False) -> int:
    """Back-compat: identity-only ``O_PATH`` open beneath the anchor."""
    return open_beneath(anchor_fd, name, directory=directory)


def statx_mnt_id(fd: int) -> int:
    buf = (ctypes.c_ubyte * 256)()
    rc = _syscall(_SYS_statx, fd, b"", AT_EMPTY_PATH,
                  STATX_MNT_ID | STATX_BASIC, ctypes.byref(buf))
    if rc != 0:
        raise NativeIdentityUnavailable(
            f"statx failed (errno {ctypes.get_errno()})")
    mask = int.from_bytes(bytes(buf[0:4]), "little")
    if not mask & STATX_MNT_ID:
        raise NativeIdentityUnavailable("statx did not return a mount id")
    return int.from_bytes(
        bytes(buf[_STATX_MNT_ID_OFFSET:_STATX_MNT_ID_OFFSET + 8]), "little")


def fstatfs_fsid(fd: int) -> tuple[int, int]:
    buf = (ctypes.c_ubyte * 120)()
    rc = _syscall(_SYS_fstatfs, fd, ctypes.byref(buf))
    if rc != 0:
        raise NativeIdentityUnavailable(
            f"fstatfs failed (errno {ctypes.get_errno()})")
    word0 = int.from_bytes(
        bytes(buf[_STATFS_FSID_OFFSET:_STATFS_FSID_OFFSET + 4]), "little")
    word1 = int.from_bytes(
        bytes(buf[_STATFS_FSID_OFFSET + 4:_STATFS_FSID_OFFSET + 8]), "little")
    return word0, word1


def file_handle(fd: int) -> tuple[int, str]:
    handle = _file_handle()
    handle.handle_bytes = _MAX_HANDLE_SZ
    mount_id = ctypes.c_int(0)
    rc = _syscall(_SYS_name_to_handle_at, fd, b"", ctypes.byref(handle),
                  ctypes.byref(mount_id), AT_EMPTY_PATH)
    if rc != 0:
        raise NativeIdentityUnavailable(
            f"name_to_handle_at failed (errno {ctypes.get_errno()})")
    length = handle.handle_bytes
    if not 1 <= length <= 256:
        raise NativeIdentityUnavailable("file handle length is out of range")
    raw = bytes(handle.f_handle[:length])
    return handle.handle_type, raw.hex()


def fail_closed(message: str) -> None:
    raise NativeIdentityUnavailable(message)


# ---------------------------------------------------------------- encoder

def _observe_once(fd: int) -> dict[str, Any]:
    st = os.fstat(fd)
    raw_type = st.st_mode & S_IFMT
    if raw_type == S_IFREG:
        file_type = "regular"
    elif raw_type == S_IFDIR:
        file_type = "directory"
    else:
        fail_closed("native target is neither a regular file nor a directory")
    mount_id = statx_mnt_id(fd)
    word0, word1 = fstatfs_fsid(fd)
    handle_type, handle_hex = file_handle(fd)
    return {
        "profile": _NATIVE_PROFILE,
        "statx_mount_id": mount_id,
        "device_major": os.major(st.st_dev),
        "device_minor": os.minor(st.st_dev),
        "statfs_fsid_word0": word0,
        "statfs_fsid_word1": word1,
        "file_handle_type": handle_type,
        "file_handle_bytes_hex": handle_hex,
        "inode": st.st_ino,
        "file_type": file_type,
        "link_count": st.st_nlink,
        "native_mode": st.st_mode & 0xFFFFFFFF,
    }


def observe_fd(fd: int) -> dict[str, Any]:
    """Return the validated ``NATIVE_ID_OBSERVATION`` for an already-open
    no-follow descriptor, observing twice and requiring equality."""
    first = _observe_once(fd)
    second = _observe_once(fd)
    if first != second:
        fail_closed("native identity changed under stable re-observation")
    try:
        validate_native_observation(first)
    except HSCValidationError as exc:
        raise NativeIdentityUnavailable(
            f"observed identity is not a valid linux-native-id-v1 record: "
            f"{exc}") from exc
    return first


def observe(anchor_fd: int, name: bytes, *,
            directory: bool = False) -> dict[str, Any]:
    """Return the ``NATIVE_ID_OBSERVATION`` for ``name`` under ``anchor_fd``.

    The target is opened no-follow beneath the anchor, observed twice, and every
    identity field must be equal across the two observations (a mutation between
    them fails closed). The result validates under the HSC-A schema and its
    derived ids reconstruct."""
    fd = openat2_beneath(anchor_fd, name, directory=directory)
    try:
        return observe_fd(fd)
    finally:
        os.close(fd)


def observe_ids(anchor_fd: int, name: bytes, *,
                directory: bool = False) -> tuple[dict[str, Any], str, str]:
    """``(observation, filesystem_id, file_id)`` for one native target."""
    observation = observe(anchor_fd, name, directory=directory)
    return observation, filesystem_id(observation), file_id(observation)


def probe_availability() -> None:
    """Fail closed if the ``linux-native-id-v1`` primitives are unavailable in
    this environment. Callers use this to decide eligibility before any
    writable dispatch (design §7.4 / test #78)."""
    anchor = os.open(".", O_RDONLY | O_DIRECTORY)
    try:
        observe(anchor, b".", directory=True)
    finally:
        os.close(anchor)
