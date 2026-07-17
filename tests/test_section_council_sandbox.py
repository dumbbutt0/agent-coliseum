"""Source export + sandbox-profile proofs (HSC-B component 3)."""

from __future__ import annotations

import hashlib
import os
import subprocess

import pytest

from tools.section_council import sandbox
from tools.section_council.core import HSCValidationError
from tools.section_council.records import validate_record

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "hsc", "GIT_AUTHOR_EMAIL": "hsc@test",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00 +0000",
    "GIT_COMMITTER_NAME": "hsc", "GIT_COMMITTER_EMAIL": "hsc@test",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00 +0000",
}
H = "1" * 64
PROGRAM_REF = {"record_id": "3" * 64, "content_sha256": "4" * 64}
REF = {"record_id": "5" * 64, "content_sha256": "6" * 64}


def _git(repo, args):
    env = dict(os.environ)
    env.update(_GIT_ENV)
    proc = subprocess.run(["git", "-C", repo] + args, capture_output=True,
                          env=env)
    assert proc.returncode == 0, proc.stderr.decode()
    return proc.stdout


def _repo(tmp_path):
    repo = str(tmp_path / "repo")
    os.makedirs(repo)
    _git(repo, ["init", "-q"])
    os.makedirs(os.path.join(repo, "src"))
    with open(os.path.join(repo, "src", "a.py"), "wb") as h:
        h.write(b"print('a')\n")
    with open(os.path.join(repo, "run.sh"), "wb") as h:
        h.write(b"#!/bin/sh\n")
    os.chmod(os.path.join(repo, "run.sh"), 0o755)
    _git(repo, ["-c", "user.name=h", "-c", "user.email=h@t", "add", "-A"])
    _git(repo, ["-c", "user.name=h", "-c", "user.email=h@t", "commit", "-q",
                "-m", "base"])
    return repo, _git(repo, ["rev-parse", "HEAD"]).decode().strip()


def test_export_materializes_tree_without_git(tmp_path):
    repo, commit = _repo(tmp_path)
    dest = str(tmp_path / "snap")
    os.makedirs(dest)
    manifest = sandbox.export_source(repo, commit, dest)
    # exact files present, no .git
    assert not os.path.exists(os.path.join(dest, ".git"))
    with open(os.path.join(dest, "src", "a.py"), "rb") as h:
        assert h.read() == b"print('a')\n"
    assert oct(os.stat(os.path.join(dest, "run.sh")).st_mode & 0o777) == "0o755"
    paths = {row["path"] for row in manifest}
    assert paths == {"src/a.py", "run.sh"}
    a = next(r for r in manifest if r["path"] == "src/a.py")
    assert a["blob_sha256"] == hashlib.sha256(b"print('a')\n").hexdigest()
    assert a["git_mode"] == "100644"
    assert next(r for r in manifest
               if r["path"] == "run.sh")["git_mode"] == "100755"
    # manifest is sorted by path
    assert [r["path"] for r in manifest] == sorted(r["path"] for r in manifest)


def test_export_refuses_non_empty_destination(tmp_path):
    repo, commit = _repo(tmp_path)
    dest = str(tmp_path / "snap")
    os.makedirs(dest)
    open(os.path.join(dest, "stray"), "wb").close()
    with pytest.raises(HSCValidationError, match="not empty"):
        sandbox.export_source(repo, commit, dest)


def test_export_refuses_symlink_in_tree(tmp_path):
    repo, _ = _repo(tmp_path)
    os.symlink("src/a.py", os.path.join(repo, "link"))
    _git(repo, ["-c", "user.name=h", "-c", "user.email=h@t", "add", "-A"])
    _git(repo, ["-c", "user.name=h", "-c", "user.email=h@t", "commit", "-q",
                "-m", "link"])
    commit = _git(repo, ["rev-parse", "HEAD"]).decode().strip()
    dest = str(tmp_path / "snap")
    os.makedirs(dest)
    with pytest.raises(HSCValidationError, match="non-plain-file"):
        sandbox.export_source(repo, commit, dest)


def test_source_snapshot_record_is_content_addressed(tmp_path):
    repo, commit = _repo(tmp_path)
    dest = str(tmp_path / "snap")
    os.makedirs(dest)
    manifest = sandbox.export_source(repo, commit, dest)
    record, data = sandbox.build_source_snapshot_record(
        PROGRAM_REF, "hsc-b-pilot-001", commit=commit, manifest=manifest)
    assert validate_record(record) is not None
    assert record["payload"]["artifact_type"] == "source_snapshot"
    assert record["payload"]["blob_sha256"] == hashlib.sha256(data).hexdigest()
    assert record["payload"]["byte_length"] == len(data)
    # deterministic: same commit+manifest -> same bytes
    assert sandbox.source_snapshot_bytes(commit, manifest) == data


def test_finding_s4_export_refuses_when_bytes_differ_from_blob(tmp_path,
                                                               monkeypatch):
    # Regression (audit 001649 F2): if the exported bytes do not byte-equal the
    # exact fetched base-commit blob (a short/truncated/redirected write), the
    # reread comparison must fail closed rather than content-address the wrong
    # bytes under the base commit.
    repo, commit = _repo(tmp_path)
    dest = str(tmp_path / "snap")
    os.makedirs(dest)
    original = sandbox._write_no_follow

    def truncating(dest_fd, segments, data, mode):
        original(dest_fd, segments, data[:-1], mode)  # drop the last byte

    monkeypatch.setattr(sandbox, "_write_no_follow", truncating)
    with pytest.raises(HSCValidationError,
                       match="differ from the base-commit blob"):
        sandbox.export_source(repo, commit, dest)


def test_finding3_write_does_not_follow_symlinked_dir_component(tmp_path):
    # Regression (audit 001635 finding 3): materialization must not follow a
    # symlinked path component. A raced symlink standing in for an intermediate
    # directory must fail closed, never redirect the write outside the snapshot.
    dest = tmp_path / "snap"; dest.mkdir()
    outside = tmp_path / "outside"; outside.mkdir()
    os.symlink(str(outside), str(dest / "src"))  # 'src' is a symlink, not a dir
    dest_fd = os.open(str(dest), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        with pytest.raises(OSError):  # ELOOP: O_NOFOLLOW refuses the symlink
            sandbox._write_no_follow(dest_fd, ["src", "a.py"], b"x", "100644")
    finally:
        os.close(dest_fd)
    assert not os.path.exists(os.path.join(str(outside), "a.py"))


def test_finding3_write_refuses_pre_existing_leaf(tmp_path):
    # A leaf that already exists (e.g. a raced symlink at the target name) must
    # fail closed via O_CREAT|O_EXCL rather than write through it.
    dest = tmp_path / "snap"; dest.mkdir()
    outside = tmp_path / "outside.txt"; outside.write_bytes(b"old")
    os.symlink(str(outside), str(dest / "a.py"))
    dest_fd = os.open(str(dest), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        with pytest.raises(OSError):
            sandbox._write_no_follow(dest_fd, ["a.py"], b"new", "100644")
    finally:
        os.close(dest_fd)
    assert outside.read_bytes() == b"old"  # bytes never redirected outside


def test_sandbox_profile_pins_the_frozen_policy():
    record = sandbox.build_sandbox_profile(
        PROGRAM_REF, native_inventory_plan_ref=REF, source_snapshot_ref=REF,
        read_only_mount_refs=[REF], launcher_binary_sha256=H,
        argv_template_sha256=H, seccomp_profile_sha256=H)
    assert validate_record(record) is not None
    p = record["payload"]
    assert p["platform"] == "linux-bwrap-v1"
    assert p["writable_mountpoint"] == "/out"
    assert p["capability_set"] == []
    assert p["unshare_user"] and p["unshare_pid"] and p["unshare_net"]
    assert p["no_new_privileges"] is True
    assert p["fd_policy"] == "close-all-except-stdio-v1"
    assert [r["fd"] for r in p["permitted_fds"]] == [0, 1, 2]
    assert p["permitted_fds"][1] == {
        "fd": 1, "role": "stdout", "access": "write", "target_kind": "pipe"}
