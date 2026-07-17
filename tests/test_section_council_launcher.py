"""Confined launcher proofs (HSC-B component 4). Runs real bwrap."""

from __future__ import annotations

import os

import pytest

from tools.section_council import launcher
from tools.section_council.launcher import SandboxUnavailable

_AVAILABLE = True
try:
    launcher.preflight()
except SandboxUnavailable:
    _AVAILABLE = False

requires_sandbox = pytest.mark.skipif(
    not _AVAILABLE, reason="linux-bwrap-v1 sandbox unavailable")


def _dirs(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "input.txt").write_bytes(b"payload")
    out = tmp_path / "out"
    out.mkdir()
    return str(src), str(out)


@requires_sandbox
def test_worker_reads_source_and_writes_out(tmp_path):
    src, out = _dirs(tmp_path)
    script = tmp_path / "w.sh"
    script.write_text("#!/bin/sh\ncat /src/input.txt > /out/result\n")
    result = launcher.run_confined(
        source_dir=src, out_leaf=out,
        worker_argv=["/bin/sh", str(_bind_script(tmp_path, script))])
    assert result.exit_status == 0, result.stderr
    with open(os.path.join(out, "result"), "rb") as h:
        assert h.read() == b"payload"


@requires_sandbox
def test_worker_descriptor_table_is_confinement_clean(tmp_path):
    src, out = _dirs(tmp_path)
    result = launcher.run_confined(
        source_dir=src, out_leaf=out, worker_argv=["/bin/true"])
    assert result.exit_status == 0
    # stdio present; no writable filesystem descriptor and no foreign/host fd
    # inherited (bwrap's own write-only monitor pipes are benign and excluded)
    assert result.stdio_present
    assert result.writable_filesystem_fd_count == 0
    assert result.foreign_fd_count == 0
    assert result.confinement_is_clean
    # every non-stdio descriptor is a write-only monitor pipe, never a file
    for entry in result.worker_fds:
        if not entry.is_stdio:
            assert entry.is_monitor_pipe, (entry.fd, entry.target)
    assert result.child_mount_count >= 1


@requires_sandbox
def test_source_mount_is_read_only(tmp_path):
    src, out = _dirs(tmp_path)
    script = tmp_path / "w.sh"
    script.write_text("#!/bin/sh\nif echo x > /src/evil 2>/dev/null; then "
                      "echo WROTE; else echo READONLY; fi\n")
    result = launcher.run_confined(
        source_dir=src, out_leaf=out,
        worker_argv=["/bin/sh", str(_bind_script(tmp_path, script))])
    assert b"READONLY" in result.stdout
    assert not os.path.exists(os.path.join(src, "evil"))


@requires_sandbox
def test_network_is_unshared(tmp_path):
    src, out = _dirs(tmp_path)
    script = tmp_path / "w.sh"
    # With --unshare-net only loopback exists and it is down; a route to a
    # public address is unavailable. Prove no external interface is present.
    script.write_text("#!/bin/sh\nls /sys/class/net 2>/dev/null | tr '\\n' ' '\n")
    result = launcher.run_confined(
        source_dir=src, out_leaf=out,
        worker_argv=["/bin/sh", str(_bind_script(tmp_path, script))])
    ifaces = result.stdout.decode().split()
    assert ifaces in ([], ["lo"]), ifaces


@requires_sandbox
def test_protected_host_paths_are_absent_from_the_namespace(tmp_path):
    src, out = _dirs(tmp_path)
    script = tmp_path / "w.sh"
    # bwrap mounts exactly the argv paths, so protected host trees (home, the
    # live council root, the Windows mount) are simply not present. Prove it
    # by behavior, which is kernel-enforced rather than parsed from mountinfo.
    script.write_text(
        "#!/bin/sh\n"
        "for p in /home /root /mnt/c /home/dummy/agent-coliseum "
        "/home/dummy/.claude; do\n"
        "  if [ -e \"$p\" ]; then echo \"PRESENT $p\"; fi\n"
        "done\n"
        "echo DONE\n")
    result = launcher.run_confined(
        source_dir=src, out_leaf=out,
        worker_argv=["/bin/sh", str(_bind_script(tmp_path, script))])
    assert result.exit_status == 0, result.stderr
    assert b"PRESENT" not in result.stdout, result.stdout
    assert b"DONE" in result.stdout


@requires_sandbox
def test_nonzero_worker_exit_is_reported(tmp_path):
    src, out = _dirs(tmp_path)
    result = launcher.run_confined(
        source_dir=src, out_leaf=out, worker_argv=["/bin/false"])
    assert result.exit_status != 0


def _bind_script(tmp_path, script):
    """Copy a worker script into the source tree so it is reachable read-only
    inside the sandbox at /src/<name> (workers run from the read-only source)."""
    os.chmod(str(script), 0o755)
    dest = tmp_path / "src" / script.name
    with open(str(script), "rb") as s, open(str(dest), "wb") as d:
        d.write(s.read())
    os.chmod(str(dest), 0o755)
    return f"/src/{script.name}"
