"""Trusted deterministic atomic assembler (HSC-B component 8b).

The assembler is the only HSC component permitted to write the integration
checkout (design §7.4). It runs only after a complete assessor pass, parses a
proposal without shell evaluation, refuses binary/symlink/submodule/special-file
targets, validates every old blob/mode against the frozen base, and applies the
exact changes in sorted ``work_item_id`` order using handle-relative no-follow
operations.

Before any write it opens every affected ancestor and target no-follow and
reconstructs the exact §6 native observation and filesystem/file ids, requires
regular targets to have ``link_count==1``, and rejects a target id that appears
at another candidate path. ``add`` installs a create-exclusive no-follow temp
file with no-replace semantics; ``modify``/``mode`` never write or chmod the old
inode — they build a replacement inode and atomically replace it after
re-checking the unchanged old identity/blob/mode; ``delete`` and pure ``rename``
re-check a unique source identity immediately before unlink/rename. A failure
before the atomic operation leaves the old path intact; a later failure aborts
the whole disposable candidate.

After assembly the resulting candidate tree is re-read and compared to the frozen
base through the canonical ``diff.real_diff`` extractor (no Git similarity), so
the actual change set feeds final-scope and real-diff enforcement.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import stat
from typing import Any

from .core import HSCValidationError, validate_path
from .diff import real_diff
from .native import fail_closed, observe_fd

_MODES = {"100644": 0o644, "100755": 0o755}
_MODE_BITS = {0o644: "100644", 0o755: "100755"}
_KINDS = ("add", "delete", "modify", "mode", "rename")

_SYS_renameat2 = 316  # x86_64
_RENAME_NOREPLACE = 1
_AT_FDCWD = -100


def _renameat2(old_dir_fd: int, old_name: str, new_dir_fd: int, new_name: str,
               flags: int) -> None:
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    ctypes.set_errno(0)
    rc = libc.syscall(_SYS_renameat2, old_dir_fd, old_name.encode(),
                      new_dir_fd, new_name.encode(), flags)
    if rc != 0:
        err = ctypes.get_errno()
        raise HSCValidationError(
            f"renameat2({old_name!r}->{new_name!r}) failed (errno {err})")


def _git_mode(observation: dict[str, Any]) -> str:
    if observation["file_type"] != "regular":
        fail_closed("assembler target is not a regular file")
    if observation["link_count"] != 1:
        fail_closed("assembler regular target has link_count != 1")
    bits = observation["native_mode"] & 0o777
    if bits not in _MODE_BITS:
        fail_closed(f"assembler target mode {bits:04o} is not a permitted blob "
                    "mode")
    return _MODE_BITS[bits]


def _open_dir(parent_fd: int, name: str) -> int:
    return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                   dir_fd=parent_fd)


def _resolve_parent(root_fd: int, segments: list[str]) -> tuple[int, list[int]]:
    """Open every ancestor directory of a path no-follow beneath the root and
    return the immediate parent fd plus the chain of opened fds (for closing)."""
    opened: list[int] = []
    cur = root_fd
    for seg in segments[:-1]:
        nxt = _open_dir(cur, seg)
        opened.append(nxt)
        cur = nxt
    return cur, opened


def _observe_child(parent_fd: int, name: str) -> dict[str, Any] | None:
    """Observe a child no-follow, or ``None`` if it is absent. A symlink or
    special file at the name fails closed rather than being silently skipped."""
    try:
        fd = os.open(name, os.O_PATH | os.O_NOFOLLOW, dir_fd=parent_fd)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise HSCValidationError(
            f"assembler target {name!r} is unopenable") from exc
    try:
        # O_PATH|O_NOFOLLOW opens a symlink itself rather than failing; a
        # symlink/special file at a target name fails closed (never followed).
        if stat.S_ISLNK(os.fstat(fd).st_mode):
            raise HSCValidationError(
                f"assembler target {name!r} is a symlink or unopenable")
        return observe_fd(fd)
    finally:
        os.close(fd)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_regular(parent_fd: int, name: str, expect: dict[str, Any]) \
        -> tuple[str, str]:
    """Re-open the existing regular target no-follow, confirm its identity is
    unchanged, and return its ``(blob_sha256, git_mode)``."""
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
    try:
        if observe_fd(fd) != expect:
            fail_closed(f"assembler target {name!r} changed under re-check")
        mode = _git_mode(expect)
        chunks = []
        while True:
            block = os.read(fd, 1 << 20)
            if not block:
                break
            chunks.append(block)
    finally:
        os.close(fd)
    return _sha256(b"".join(chunks)), mode


def _write_temp(parent_fd: int, name: str, data: bytes, mode: str) -> None:
    """Create a create-exclusive no-follow temp regular file, verify its native
    identity/link count, write/fsync/chmod it. Caller installs it by rename."""
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=parent_fd)
    try:
        observation = observe_fd(fd)
        if observation["file_type"] != "regular" or \
                observation["link_count"] != 1:
            fail_closed("assembler temp file is not a fresh regular inode")
        written = 0
        while written < len(data):
            n = os.write(fd, data[written:])
            if n <= 0:
                fail_closed("assembler temp write did not advance")
            written += n
        os.fchmod(fd, _MODES[mode])
        os.fsync(fd)
    finally:
        os.close(fd)


def _temp_name(work_item_id: str, target: str) -> str:
    # A same-directory temp name unique to this work item and target leaf.
    leaf = target.rsplit("/", 1)[-1]
    return f".hsc-assemble.{work_item_id[:16]}.{leaf}"


def _apply_change(root_fd: int, base: dict[str, tuple[str, str]],
                  change: dict[str, Any]) -> None:
    kind = change["kind"]
    path = change["path"]
    segments = path.split("/")
    parent_fd, opened = _resolve_parent(root_fd, segments)
    leaf = segments[-1]
    try:
        existing = _observe_child(parent_fd, leaf)
        if kind == "add":
            if existing is not None:
                fail_closed(f"assembler add target {path!r} already exists")
            if path in base:
                fail_closed(f"assembler add target {path!r} exists in base")
            temp = _temp_name(change["work_item_id"], path)
            _write_temp(parent_fd, temp, change["content_after"],
                        change["mode_after"])
            try:
                _renameat2(parent_fd, temp, parent_fd, leaf, _RENAME_NOREPLACE)
            except HSCValidationError:
                os.unlink(temp, dir_fd=parent_fd)
                raise
        elif kind in ("modify", "mode"):
            if existing is None:
                fail_closed(f"assembler {kind} target {path!r} is absent")
            blob_before, mode_before = _read_regular(parent_fd, leaf, existing)
            if (blob_before, mode_before) != \
                    (change["blob_before"], change["mode_before"]):
                fail_closed(f"assembler {kind} base blob/mode mismatch for "
                            f"{path!r}")
            if base.get(path) != (blob_before, mode_before):
                fail_closed(f"assembler {kind} target diverges from the frozen "
                            f"base tree at {path!r}")
            data = change["content_after"] if kind == "modify" else \
                change["_current_bytes"]
            temp = _temp_name(change["work_item_id"], path)
            _write_temp(parent_fd, temp, data, change["mode_after"])
            # Re-check the old inode is still the exact frozen identity right
            # before the atomic replace; we never wrote or chmod'd it.
            if _observe_child(parent_fd, leaf) != existing:
                os.unlink(temp, dir_fd=parent_fd)
                fail_closed(f"assembler {kind} old inode drifted before replace")
            os.rename(temp, leaf, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        elif kind == "delete":
            if existing is None:
                fail_closed(f"assembler delete target {path!r} is absent")
            blob_before, mode_before = _read_regular(parent_fd, leaf, existing)
            if base.get(path) != (blob_before, mode_before):
                fail_closed(f"assembler delete target diverges from base at "
                            f"{path!r}")
            if _observe_child(parent_fd, leaf) != existing:
                fail_closed(f"assembler delete inode drifted before unlink")
            os.unlink(leaf, dir_fd=parent_fd)
        elif kind == "rename":
            source = change["rename_source"]
            src_segments = source.split("/")
            src_parent, src_opened = _resolve_parent(root_fd, src_segments)
            try:
                src_leaf = src_segments[-1]
                src_obs = _observe_child(src_parent, src_leaf)
                if src_obs is None:
                    fail_closed(f"assembler rename source {source!r} is absent")
                blob_before, mode_before = _read_regular(
                    src_parent, src_leaf, src_obs)
                if base.get(source) != (blob_before, mode_before):
                    fail_closed("assembler rename source diverges from base")
                if existing is not None or path in base:
                    fail_closed(f"assembler rename dest {path!r} already exists")
                if _observe_child(src_parent, src_leaf) != src_obs:
                    fail_closed("assembler rename source drifted before rename")
                _renameat2(src_parent, src_leaf, parent_fd, leaf,
                           _RENAME_NOREPLACE)
            finally:
                for fd in reversed(src_opened):
                    os.close(fd)
        else:  # pragma: no cover - guarded by validation
            fail_closed(f"assembler cannot apply kind {kind!r}")
        os.fsync(parent_fd)
    finally:
        for fd in reversed(opened):
            os.close(fd)


def _validate_proposal_change(change: Any, seen_items: set) -> dict[str, Any]:
    if not isinstance(change, dict):
        raise HSCValidationError("proposal change must be an object")
    keys = {"work_item_id", "kind", "path", "rename_source", "content_after_hex",
            "mode_after", "blob_before", "mode_before"}
    if set(change) != keys:
        raise HSCValidationError("proposal change has unexpected keys")
    kind = change["kind"]
    if kind not in _KINDS:
        raise HSCValidationError(f"proposal change kind {kind!r} is invalid")
    wid = change["work_item_id"]
    if not isinstance(wid, str) or len(wid) != 64:
        raise HSCValidationError("proposal work_item_id must be a 64-hex id")
    if wid in seen_items:
        raise HSCValidationError("proposal reuses a work_item_id")
    seen_items.add(wid)
    validate_path(change["path"], "proposal change path")
    normalized: dict[str, Any] = {
        "work_item_id": wid, "kind": kind, "path": change["path"],
        "rename_source": change["rename_source"],
        "blob_before": change["blob_before"],
        "mode_before": change["mode_before"],
        "mode_after": change["mode_after"],
    }
    if kind in ("add", "modify"):
        hex_body = change["content_after_hex"]
        if not isinstance(hex_body, str):
            raise HSCValidationError(f"{kind} requires content_after_hex")
        try:
            normalized["content_after"] = bytes.fromhex(hex_body)
        except ValueError as exc:
            raise HSCValidationError("content_after_hex is not hex") from exc
        if change["mode_after"] not in _MODES:
            raise HSCValidationError(f"{kind} requires a valid mode_after")
    if kind == "rename":
        if not isinstance(change["rename_source"], str):
            raise HSCValidationError("rename requires rename_source")
        validate_path(change["rename_source"], "proposal rename_source")
    return normalized


def apply_proposal(root_fd: int, base_tree: dict[str, tuple[str, str]],
                   proposal: dict[str, Any], *,
                   predicted_renames: list | None = None) -> list[dict]:
    """Apply the parsed ``proposal`` to the integration checkout open at
    ``root_fd`` and return the resulting sorted ``ACTUAL_CHANGE`` list.

    ``base_tree`` maps every base project path to ``(blob_sha256, git_mode)``
    (from the frozen source snapshot). Changes apply in sorted ``work_item_id``
    order; each is validated against the base before its atomic operation."""
    if not isinstance(proposal, dict) or set(proposal) != {"changes"}:
        raise HSCValidationError("proposal must be {'changes': [...]}")
    raw = proposal["changes"]
    if not isinstance(raw, list) or not raw:
        raise HSCValidationError("proposal changes must be a non-empty list")
    seen: set = set()
    changes = [_validate_proposal_change(c, seen) for c in raw]
    changes.sort(key=lambda c: c["work_item_id"])
    for change in changes:
        if change["kind"] == "mode":
            # 'mode' keeps content: capture the exact current bytes to rewrite
            # into the replacement inode (never touching the old one).
            path = change["path"]
            segments = path.split("/")
            parent_fd, opened = _resolve_parent(root_fd, segments)
            try:
                obs = _observe_child(parent_fd, segments[-1])
                if obs is None:
                    fail_closed(f"assembler mode target {path!r} is absent")
                fd = os.open(segments[-1], os.O_RDONLY | os.O_NOFOLLOW,
                             dir_fd=parent_fd)
                try:
                    body = b""
                    while True:
                        block = os.read(fd, 1 << 20)
                        if not block:
                            break
                        body += block
                finally:
                    os.close(fd)
            finally:
                for fd in reversed(opened):
                    os.close(fd)
            change["_current_bytes"] = body
        _apply_change(root_fd, base_tree, change)
    os.fsync(root_fd)
    candidate_tree = read_tree(root_fd)
    return real_diff(base_tree, candidate_tree,
                     predicted_renames=predicted_renames)


def read_tree(root_fd: int) -> dict[str, tuple[str, str]]:
    """Read a checkout as ``{path: (blob_sha256, git_mode)}`` via no-follow
    enumeration. Any symlink/special file or non-permitted mode fails closed."""
    tree: dict[str, tuple[str, str]] = {}

    def walk(dir_fd: int, prefix: str) -> None:
        for name in sorted(os.listdir(dir_fd)):
            if prefix == "" and name == ".git":
                continue  # a delegated control tree is not project content
            child_path = f"{prefix}{name}"
            fd = os.open(name, os.O_PATH | os.O_NOFOLLOW, dir_fd=dir_fd)
            try:
                obs = observe_fd(fd)
            finally:
                os.close(fd)
            if obs["file_type"] == "directory":
                sub = _open_dir(dir_fd, name)
                try:
                    walk(sub, f"{child_path}/")
                finally:
                    os.close(sub)
            else:
                rfd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dir_fd)
                try:
                    if observe_fd(rfd) != obs:
                        fail_closed("tree file identity changed during read")
                    mode = _git_mode(obs)
                    body = b""
                    while True:
                        block = os.read(rfd, 1 << 20)
                        if not block:
                            break
                        body += block
                finally:
                    os.close(rfd)
                tree[child_path] = (_sha256(body), mode)

    walk(root_fd, "")
    return tree
