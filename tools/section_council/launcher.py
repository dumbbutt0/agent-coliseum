"""Pinned ``linux-bwrap-v1`` launcher + trusted-parent observation (HSC-B #4).

The launcher runs one confined section worker under the frozen sandbox profile
(design §7.4): new user/pid/net namespaces, ``no_new_privileges``, empty
capabilities, the pinned seccomp filter, the read-only source snapshot plus a
read-only runtime image, a single writable ``/out`` leaf, and a bounded private
``/tmp`` tmpfs. Before releasing the worker it holds it at a pre-exec barrier
while a trusted parent enumerates the child's descriptor table and mount table
from ``/proc`` — the worker table must reduce to exactly fd 0/1/2 (stdin=null,
stdout/stderr=pipe) once the launcher's own control channels are excluded, and
no writable filesystem descriptor may be inherited. If any required primitive
is unavailable the launch is ineligible (fail closed), never an unconfined
worker.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass, field

from .core import HSCValidationError
from .seccomp import SeccompUnavailable, build_seccomp_bpf

_BWRAP = "bwrap"
_DEFAULT_RUNTIME = ("/usr", "/bin", "/lib", "/lib64", "/sbin", "/etc/alternatives")
_SRC_MOUNT = "/src"
_OUT_MOUNT = "/out"


class SandboxUnavailable(HSCValidationError):
    """A required sandbox primitive is unavailable, so writable hierarchical
    execution is ineligible (fail closed)."""


# The pinned trusted first stage. It runs as the confined command after bwrap
# closes its own setup descriptors, enumerates its descriptor table (target +
# access mode) and the child mount count into a dedicated writable attest mount
# (never the worker's /out), then execs the real worker with an untouched
# table. It is Python (from the read-only runtime) rather than shell so the
# enumeration itself introduces no phantom descriptors: it reads /proc/self/fd
# before opening the attest file.
_FIRST_STAGE = (
    "import os,sys,json,fcntl\n"
    "fds={}\n"
    "for n in os.listdir('/proc/self/fd'):\n"
    "    fd=int(n)\n"
    "    try:\n"
    "        t=os.readlink('/proc/self/fd/'+n)\n"
    "        a=fcntl.fcntl(fd,fcntl.F_GETFL)&os.O_ACCMODE\n"
    "    except OSError:\n"
    "        continue\n"
    "    fds[fd]={'target':t,'accmode':a}\n"
    "open('/attest/fdtable','w').write(json.dumps(fds))\n"
    "open('/attest/mounts','w').write("
    "str(sum(1 for _ in open('/proc/self/mountinfo'))))\n"
    "os.execv(sys.argv[1],sys.argv[1:])\n"
)
_PYTHON = "/usr/bin/python3"
_ATTEST_MOUNT = "/attest"


@dataclass
class WorkerFd:
    fd: int
    target: str
    writable: bool
    readable: bool

    @property
    def is_filesystem(self) -> bool:
        return self.target.startswith("/") and self.target != "/dev/null"

    @property
    def is_monitor_pipe(self) -> bool:
        # bwrap 0.9.0 leaves two write-only sync pipes to its own monitor; they
        # are not filesystem descriptors and cannot carry data into the worker.
        return self.target.startswith("pipe:[") and not self.readable

    @property
    def is_stdio(self) -> bool:
        return self.fd in (0, 1, 2)


@dataclass
class ConfinedResult:
    exit_status: int
    worker_fds: list[WorkerFd]
    child_mount_count: int
    stdout: bytes
    stderr: bytes
    notes: list[str] = field(default_factory=list)

    @property
    def writable_filesystem_fd_count(self) -> int:
        return sum(1 for e in self.worker_fds
                   if e.is_filesystem and e.writable)

    @property
    def foreign_fd_count(self) -> int:
        """Non-stdio descriptors that are not the launcher's own benign
        write-only monitor pipes — an inherited host/foreign/writable fd."""
        return sum(1 for e in self.worker_fds
                   if not e.is_stdio and not e.is_monitor_pipe)

    @property
    def stdio_present(self) -> bool:
        return {0, 1, 2} <= {e.fd for e in self.worker_fds}

    @property
    def confinement_is_clean(self) -> bool:
        return (self.stdio_present and self.foreign_fd_count == 0 and
                self.writable_filesystem_fd_count == 0)


def preflight() -> None:
    """Fail closed unless bwrap, the seccomp profile, and user/pid/net
    namespaces are all available."""
    if subprocess.run([_BWRAP, "--version"], capture_output=True).returncode:
        raise SandboxUnavailable("bwrap is unavailable")
    try:
        build_seccomp_bpf()
    except SeccompUnavailable as exc:
        raise SandboxUnavailable(str(exc)) from exc
    probe = subprocess.run(
        [_BWRAP, "--unshare-user", "--unshare-pid", "--unshare-net",
         "--clearenv", "--die-with-parent", "--ro-bind", "/usr", "/usr",
         "--ro-bind", "/bin", "/bin", "--ro-bind", "/lib", "/lib",
         "--ro-bind-try", "/lib64", "/lib64", "--proc", "/proc", "--dev",
         "/dev", "--tmpfs", "/tmp", "--chdir", "/", "/bin/true"],
        capture_output=True)
    if probe.returncode != 0:
        raise SandboxUnavailable(
            f"bwrap namespace setup failed: {probe.stderr.decode()[:200]}")


def run_confined(*, source_dir: str, out_leaf: str, worker_argv: list[str],
                 runtime_ro: tuple[str, ...] = _DEFAULT_RUNTIME,
                 tmpfs_bytes: int = 64 * 1024 * 1024,
                 timeout: float = 120.0) -> ConfinedResult:
    """Run ``worker_argv`` confined and capture the pinned first stage's
    post-exec descriptor and mount observation. ``source_dir`` is mounted
    read-only at ``/src`` and ``out_leaf`` read-write at ``/out``; both must be
    real directories."""
    if not os.path.isdir(source_dir):
        raise SandboxUnavailable("source directory is missing")
    if not os.path.isdir(out_leaf):
        raise SandboxUnavailable("output leaf is missing")
    bpf = build_seccomp_bpf()
    seccomp_handle, seccomp_path = tempfile.mkstemp(prefix="hsc-seccomp-")
    os.write(seccomp_handle, bpf)
    os.lseek(seccomp_handle, 0, os.SEEK_SET)
    os.set_inheritable(seccomp_handle, True)
    attest_dir = tempfile.mkdtemp(prefix="hsc-attest-")

    argv = [_BWRAP, "--unshare-user", "--unshare-pid", "--unshare-net",
            "--clearenv", "--die-with-parent", "--new-session"]
    for path in runtime_ro:
        argv += ["--ro-bind-try", path, path]
    argv += ["--ro-bind", source_dir, _SRC_MOUNT,
             "--bind", out_leaf, _OUT_MOUNT,
             "--bind", attest_dir, _ATTEST_MOUNT,
             "--size", str(tmpfs_bytes), "--tmpfs", "/tmp",
             "--proc", "/proc", "--dev", "/dev", "--chdir", "/",
             "--seccomp", str(seccomp_handle), "--",
             _PYTHON, "-c", _FIRST_STAGE] + worker_argv

    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            pass_fds=(seccomp_handle,))
    os.close(seccomp_handle)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise SandboxUnavailable("confined worker exceeded its deadline")
    finally:
        try:
            os.unlink(seccomp_path)
        except OSError:
            pass

    worker_fds = _read_fd_table(os.path.join(attest_dir, "fdtable"))
    mount_count = _read_int(os.path.join(attest_dir, "mounts"))
    for name in ("fdtable", "mounts"):
        try:
            os.unlink(os.path.join(attest_dir, name))
        except OSError:
            pass
    try:
        os.rmdir(attest_dir)
    except OSError:
        pass
    return ConfinedResult(
        exit_status=proc.returncode, worker_fds=worker_fds,
        child_mount_count=mount_count, stdout=stdout, stderr=stderr)


def _read_fd_table(path: str) -> list[WorkerFd]:
    """Parse the first stage's JSON descriptor table into typed entries. Each
    value carries the readlink target and the ``O_ACCMODE`` bits (0=ro, 1=wo,
    2=rw)."""
    import json
    try:
        with open(path, "r") as handle:
            raw = json.loads(handle.read() or "{}")
    except (OSError, ValueError) as exc:
        raise SandboxUnavailable(
            f"first stage did not record its descriptor table: {exc}") from exc
    entries: list[WorkerFd] = []
    for key, value in raw.items():
        fd = int(key)
        target = value["target"]
        if target.startswith(_ATTEST_MOUNT + "/"):
            continue  # the observation's own attest descriptor, not a worker fd
        accmode = int(value["accmode"])
        entries.append(WorkerFd(
            fd=fd, target=target,
            readable=accmode in (os.O_RDONLY, os.O_RDWR),
            writable=accmode in (os.O_WRONLY, os.O_RDWR)))
    if not entries:
        raise SandboxUnavailable("first stage recorded an empty fd table")
    return entries


def _read_int(path: str) -> int:
    try:
        with open(path, "r") as handle:
            return int(handle.read().strip() or "0")
    except (OSError, ValueError):
        return 0
