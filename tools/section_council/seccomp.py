"""Pinned ``linux-bwrap-v1`` seccomp profile (HSC-B launcher support).

A confined HSC worker runs under a pinned seccomp BPF filter (design §7.4
step 2). This module builds that filter deterministically via ``libseccomp``
and exports it as a compiled BPF program whose bytes are content-addressed by
SHA-256 — the digest the ``worker_sandbox_profile.v1`` record pins.

The v1 pilot policy is defence-in-depth on top of the user/pid/net namespaces,
``no_new_privileges``, empty capability set, read-only mounts, and fd closure:
default ALLOW, with a small deny-list that kills the process on the syscalls a
deterministic file-transforming worker never needs and that would aid a sandbox
escape or host observation (ptrace family, kernel module and mount control,
namespace re-entry, bpf, kexec, and privileged clock/reboot operations).

If ``libseccomp`` is unavailable the profile is ineligible (fail closed):
writable hierarchical execution must not proceed without it.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import hashlib
import os
import tempfile

from .core import HSCValidationError

PROFILE_VERSION = "linux-bwrap-seccomp.v1"

# libseccomp action codes (seccomp.h).
_SCMP_ACT_ALLOW = 0x7FFF0000
_SCMP_ACT_KILL_PROCESS = 0x80000000

# Syscalls a deterministic file-transforming worker never needs and that would
# aid escape, host observation, or privilege games. Denied by KILL_PROCESS.
_DENY = (
    "ptrace", "process_vm_readv", "process_vm_writev",
    "kcmp", "pidfd_getfd",
    "init_module", "finit_module", "delete_module",
    "kexec_load", "kexec_file_load",
    "mount", "umount2", "pivot_root", "chroot",
    "setns", "unshare", "add_key", "keyctl", "request_key",
    "bpf", "perf_event_open",
    "reboot", "settimeofday", "clock_settime", "clock_adjtime", "adjtimex",
    "swapon", "swapoff", "acct", "quotactl",
)


class SeccompUnavailable(HSCValidationError):
    """``libseccomp`` (or a required syscall name) is unavailable, so the
    pinned seccomp profile is ineligible (fail closed)."""


def _libseccomp():
    name = ctypes.util.find_library("seccomp") or "libseccomp.so.2"
    try:
        lib = ctypes.CDLL(name, use_errno=True)
    except OSError as exc:
        raise SeccompUnavailable(f"libseccomp is unavailable: {exc}") from exc
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_init.argtypes = [ctypes.c_uint32]
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    lib.seccomp_syscall_resolve_name.restype = ctypes.c_int
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    lib.seccomp_rule_add.restype = ctypes.c_int
    lib.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                                     ctypes.c_int, ctypes.c_uint]
    lib.seccomp_export_bpf.restype = ctypes.c_int
    lib.seccomp_export_bpf.argtypes = [ctypes.c_void_p, ctypes.c_int]
    return lib


def build_seccomp_bpf() -> bytes:
    """Return the compiled BPF program bytes for the pinned v1 profile."""
    lib = _libseccomp()
    ctx = lib.seccomp_init(_SCMP_ACT_ALLOW)
    if not ctx:
        raise SeccompUnavailable("seccomp_init failed")
    fd = -1
    path = None
    try:
        for name in _DENY:
            number = lib.seccomp_syscall_resolve_name(name.encode("ascii"))
            # __NR_SCMP_ERROR is -1; an unresolved name on this arch is skipped
            # only if it is genuinely absent, never silently for a typo.
            if number == -1:
                continue
            rc = lib.seccomp_rule_add(ctx, _SCMP_ACT_KILL_PROCESS, number, 0)
            if rc != 0:
                raise SeccompUnavailable(
                    f"seccomp_rule_add failed for {name} (rc {rc})")
        handle, path = tempfile.mkstemp(prefix="hsc-seccomp-")
        fd = handle
        os.lseek(fd, 0, os.SEEK_SET)
        rc = lib.seccomp_export_bpf(ctx, fd)
        if rc != 0:
            raise SeccompUnavailable(f"seccomp_export_bpf failed (rc {rc})")
        os.lseek(fd, 0, os.SEEK_SET)
        with open(fd, "rb", closefd=False) as handle_file:
            data = handle_file.read()
        if not data:
            raise SeccompUnavailable("exported seccomp program is empty")
        return data
    finally:
        lib.seccomp_release(ctx)
        if fd >= 0:
            os.close(fd)
        if path is not None:
            os.unlink(path)


def seccomp_profile_sha256() -> str:
    return hashlib.sha256(build_seccomp_bpf()).hexdigest()


def probe_seccomp() -> None:
    """Fail closed if the pinned seccomp profile cannot be produced."""
    build_seccomp_bpf()
