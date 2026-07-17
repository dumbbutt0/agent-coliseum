"""Read-only source export + sandbox-profile minting (HSC-B component 3).

The trusted host exports the exact base commit into a content-inventoried
source snapshot with **no** ``.git`` directory (design §7.4 step 1), which is
later mounted read-only into every worker namespace. It also mints the frozen
``worker_sandbox_profile.v1`` record that pins the ``linux-bwrap-v1`` namespace,
capability, fd, and seccomp policy the launcher must apply.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from typing import Any

from tools.council.schemas import canonical_json, validate_commit
from tools.section_council.core import HSCValidationError
from tools.section_council.records import make_record

_SNAPSHOT_SCHEMA = "section-source-snapshot.v1"
_WRITABLE_MOUNTPOINT = "/out"
_FD_POLICY = "close-all-except-stdio-v1"
_PERMITTED_FDS = [
    {"fd": 0, "role": "stdin", "access": "read", "target_kind": "null"},
    {"fd": 1, "role": "stdout", "access": "write", "target_kind": "pipe"},
    {"fd": 2, "role": "stderr", "access": "write", "target_kind": "pipe"},
]


def _git(repo: str, args: list[str]) -> bytes:
    proc = subprocess.run(["git", "-C", repo] + args, capture_output=True,
                          timeout=120)
    if proc.returncode != 0:
        raise HSCValidationError(
            f"git {' '.join(args)} failed: "
            f"{proc.stderr.decode('utf-8', 'replace').strip()}")
    return proc.stdout


def export_source(repo: str, commit: str, dest: str) -> list[dict[str, Any]]:
    """Materialize the exact ``commit`` tree under ``dest`` with no ``.git``
    and no worker-writable metadata, and return the sorted content manifest.

    Only ``100644``/``100755`` blobs are exported; a symlink, gitlink, or any
    other mode refuses (the source must be a plain read-only tree). ``dest``
    must be an empty directory."""
    validate_commit(commit)
    if os.listdir(dest):
        raise HSCValidationError("source export destination is not empty")
    listing = _git(repo, ["ls-tree", "-r", "-z", commit])
    entries: list[tuple[str, str, str]] = []
    wanted: list[str] = []
    for record in listing.split(b"\x00"):
        if not record:
            continue
        meta, _, raw_path = record.partition(b"\t")
        parts = meta.split(b" ")
        if len(parts) != 3:
            raise HSCValidationError("malformed git ls-tree record")
        mode, obj_type, obj_id = (p.decode("ascii") for p in parts)
        if obj_type != "blob" or mode not in ("100644", "100755"):
            raise HSCValidationError(
                "source tree contains a non-plain-file entry")
        path = raw_path.decode("utf-8")
        if path.split("/")[0] == ".git":
            raise HSCValidationError("source tree unexpectedly contains .git")
        entries.append((path, mode, obj_id))
        wanted.append(obj_id)
    contents = _cat_blobs(repo, wanted)
    manifest: list[dict[str, Any]] = []
    for path, mode, obj_id in entries:
        data = contents[obj_id]
        full = os.path.join(dest, path)
        os.makedirs(os.path.dirname(full) or dest, exist_ok=True)
        with open(full, "wb") as handle:
            handle.write(data)
        os.chmod(full, 0o755 if mode == "100755" else 0o644)
        manifest.append({"path": path, "git_mode": mode,
                         "blob_sha256": hashlib.sha256(data).hexdigest(),
                         "byte_length": len(data)})
    manifest.sort(key=lambda row: row["path"])
    if os.path.exists(os.path.join(dest, ".git")):
        raise HSCValidationError("exported source snapshot contains .git")
    return manifest


def _cat_blobs(repo: str, blob_ids: list[str]) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    unique = sorted(set(blob_ids))
    if not unique:
        return result
    proc = subprocess.run(["git", "-C", repo, "cat-file", "--batch"],
                          input=("\n".join(unique) + "\n").encode("ascii"),
                          capture_output=True, timeout=120)
    if proc.returncode != 0:
        raise HSCValidationError("git cat-file failed")
    out = proc.stdout
    offset = 0
    for blob_id in unique:
        newline = out.index(b"\n", offset)
        header = out[offset:newline].decode("ascii").split(" ")
        if len(header) != 3 or header[0] != blob_id or header[1] != "blob":
            raise HSCValidationError("git cat-file returned an unexpected blob")
        size = int(header[2])
        start = newline + 1
        result[blob_id] = out[start:start + size]
        offset = start + size + 1
    return result


def source_snapshot_bytes(commit: str, manifest: list[dict[str, Any]]) -> bytes:
    """The canonical ``source_snapshot`` content-record bytes: the exact
    exported base commit and its per-file digests, so the snapshot's identity
    is content-addressed."""
    return canonical_json({
        "schema_version": _SNAPSHOT_SCHEMA,
        "base_commit": commit,
        "files": manifest,
    }).encode("utf-8")


def build_source_snapshot_record(program_ref: dict, request_id: str, *,
                                 commit: str, manifest: list[dict[str, Any]]):
    """Wrap the source-snapshot bytes as a ``section_content_record.v1`` of
    artifact type ``source_snapshot``."""
    data = source_snapshot_bytes(commit, manifest)
    prefix = f"artifacts/section-council/{request_id}/content/"
    payload = {
        "program_ref": program_ref,
        "artifact_type": "source_snapshot",
        "storage_relpath": prefix + "source-snapshot.json",
        "media_type": "application/json",
        "byte_length": len(data),
        "blob_sha256": hashlib.sha256(data).hexdigest(),
        "producer_assignment_ref": None,
        "parent_content_refs": [],
    }
    return make_record("section_content_record.v1", payload), data


def build_sandbox_profile(program_ref: dict, *, native_inventory_plan_ref: dict,
                          source_snapshot_ref: dict,
                          read_only_mount_refs: list[dict],
                          launcher_binary_sha256: str,
                          argv_template_sha256: str,
                          seccomp_profile_sha256: str,
                          private_tmpfs_bytes: int = 64 * 1024 * 1024,
                          environment_allowlist: list[str] | None = None):
    """Mint the frozen ``worker_sandbox_profile.v1`` record. The namespace,
    capability, and fd policy are fixed by the design: user/pid/net unshared,
    no_new_privileges, empty capability set, the exact stdio-only fd table, and
    the single ``/out`` writable mountpoint."""
    payload = {
        "program_ref": program_ref,
        "platform": "linux-bwrap-v1",
        "launcher_binary_sha256": launcher_binary_sha256,
        "argv_template_sha256": argv_template_sha256,
        "native_inventory_plan_ref": native_inventory_plan_ref,
        "source_snapshot_ref": source_snapshot_ref,
        "read_only_mount_refs": sorted(
            read_only_mount_refs,
            key=lambda ref: canonical_json(ref)),
        "writable_mountpoint": _WRITABLE_MOUNTPOINT,
        "private_tmpfs_bytes": private_tmpfs_bytes,
        "unshare_user": True,
        "unshare_pid": True,
        "unshare_net": True,
        "no_new_privileges": True,
        "capability_set": [],
        "seccomp_profile_sha256": seccomp_profile_sha256,
        "environment_allowlist": sorted(environment_allowlist or []),
        "fd_policy": _FD_POLICY,
        "permitted_fds": [dict(rule) for rule in _PERMITTED_FDS],
    }
    return make_record("worker_sandbox_profile.v1", payload)
