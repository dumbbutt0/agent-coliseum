"""Atomic assembler proofs (HSC-B component 8b)."""

from __future__ import annotations

import hashlib
import os

import pytest

from tools.section_council import assembler
from tools.section_council.core import HSCValidationError

WID_A = "a" * 64
WID_B = "b" * 64
WID_C = "c" * 64


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _checkout(tmp_path, files):
    """Materialize a base checkout; return (root, root_fd, base_tree)."""
    root = tmp_path / "checkout"
    root.mkdir()
    base = {}
    for path, (data, mode) in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        os.chmod(target, 0o755 if mode == "100755" else 0o644)
        base[path] = (_sha(data), mode)
    fd = os.open(str(root), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    return root, fd, base


def _pred(change, *, required=True):
    """Derive the authorized prediction that matches a proposal change."""
    return {"path": change["path"], "kind": change["kind"],
            "rename_source": change["rename_source"],
            "blob_before": change["blob_before"],
            "mode_before": change["mode_before"], "required": required}


def _scope(proposal):
    """The per-work-item authorized scope: each change owned by its own wid."""
    return {c["work_item_id"]: [_pred(c)] for c in proposal["changes"]}


def test_add_modify_mode_delete_rename(tmp_path):
    root, fd, base = _checkout(tmp_path, {
        "keep.txt": (b"keep\n", "100644"),
        "edit.txt": (b"old\n", "100644"),
        "flip.sh": (b"#!/bin/sh\n", "100644"),
        "drop.txt": (b"bye\n", "100644"),
        "src/from.txt": (b"moved\n", "100644"),
    })
    proposal = {"changes": [
        {"work_item_id": WID_A, "kind": "add", "path": "new.txt",
         "rename_source": None, "content_after_hex": b"hi\n".hex(),
         "mode_after": "100644", "blob_before": None, "mode_before": None},
        {"work_item_id": WID_B, "kind": "modify", "path": "edit.txt",
         "rename_source": None, "content_after_hex": b"new\n".hex(),
         "mode_after": "100644", "blob_before": _sha(b"old\n"),
         "mode_before": "100644"},
        {"work_item_id": WID_C, "kind": "mode", "path": "flip.sh",
         "rename_source": None, "content_after_hex": None,
         "mode_after": "100755", "blob_before": _sha(b"#!/bin/sh\n"),
         "mode_before": "100644"},
        {"work_item_id": "d" * 64, "kind": "delete", "path": "drop.txt",
         "rename_source": None, "content_after_hex": None, "mode_after": None,
         "blob_before": _sha(b"bye\n"), "mode_before": "100644"},
        {"work_item_id": "e" * 64, "kind": "rename", "path": "dst/to.txt",
         "rename_source": "src/from.txt", "content_after_hex": None,
         "mode_after": None, "blob_before": _sha(b"moved\n"),
         "mode_before": "100644"},
    ]}
    (root / "dst").mkdir()
    try:
        changes = assembler.apply_proposal(
            fd, base, proposal, work_item_scope=_scope(proposal),
            predicted_renames=[{"path": "dst/to.txt",
                                "rename_source": "src/from.txt"}])
    finally:
        os.close(fd)
    assert (root / "new.txt").read_bytes() == b"hi\n"
    assert (root / "edit.txt").read_bytes() == b"new\n"
    assert oct(os.stat(root / "flip.sh").st_mode & 0o777) == "0o755"
    assert (root / "flip.sh").read_bytes() == b"#!/bin/sh\n"
    assert not (root / "drop.txt").exists()
    assert not (root / "src/from.txt").exists()
    assert (root / "dst/to.txt").read_bytes() == b"moved\n"
    kinds = {(c["path"], c["kind"]) for c in changes}
    assert kinds == {("new.txt", "add"), ("edit.txt", "modify"),
                     ("flip.sh", "mode"), ("drop.txt", "delete"),
                     ("dst/to.txt", "rename")}


def test_add_over_existing_refuses(tmp_path):
    root, fd, base = _checkout(tmp_path, {"a.txt": (b"x\n", "100644")})
    proposal = {"changes": [
        {"work_item_id": WID_A, "kind": "add", "path": "a.txt",
         "rename_source": None, "content_after_hex": b"y\n".hex(),
         "mode_after": "100644", "blob_before": None, "mode_before": None}]}
    try:
        with pytest.raises(HSCValidationError, match="already exists"):
            assembler.apply_proposal(fd, base, proposal,
                                     work_item_scope=_scope(proposal))
        assert (root / "a.txt").read_bytes() == b"x\n"
    finally:
        os.close(fd)


def test_modify_base_mismatch_refuses(tmp_path):
    root, fd, base = _checkout(tmp_path, {"a.txt": (b"real\n", "100644")})
    proposal = {"changes": [
        {"work_item_id": WID_A, "kind": "modify", "path": "a.txt",
         "rename_source": None, "content_after_hex": b"z\n".hex(),
         "mode_after": "100644", "blob_before": _sha(b"WRONG\n"),
         "mode_before": "100644"}]}
    try:
        # the prediction agrees with the (wrong) declared base, so the scope gate
        # passes and the on-disk base check is what fires
        with pytest.raises(HSCValidationError, match="base blob/mode mismatch"):
            assembler.apply_proposal(fd, base, proposal,
                                     work_item_scope=_scope(proposal))
        assert (root / "a.txt").read_bytes() == b"real\n"
    finally:
        os.close(fd)


def test_symlink_target_refuses(tmp_path):
    root, fd, base = _checkout(tmp_path, {"a.txt": (b"x\n", "100644")})
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"secret\n")
    os.symlink(str(outside), str(root / "link"))
    proposal = {"changes": [
        {"work_item_id": WID_A, "kind": "modify", "path": "link",
         "rename_source": None, "content_after_hex": b"pwn\n".hex(),
         "mode_after": "100644", "blob_before": _sha(b"whatever"),
         "mode_before": "100644"}]}
    try:
        with pytest.raises(HSCValidationError, match="symlink or unopenable"):
            assembler.apply_proposal(fd, base, proposal,
                                     work_item_scope=_scope(proposal))
        assert outside.read_bytes() == b"secret\n"
    finally:
        os.close(fd)


def test_rename_dest_exists_refuses(tmp_path):
    root, fd, base = _checkout(tmp_path, {
        "from.txt": (b"m\n", "100644"), "to.txt": (b"here\n", "100644")})
    proposal = {"changes": [
        {"work_item_id": WID_A, "kind": "rename", "path": "to.txt",
         "rename_source": "from.txt", "content_after_hex": None,
         "mode_after": None, "blob_before": _sha(b"m\n"),
         "mode_before": "100644"}]}
    try:
        with pytest.raises(HSCValidationError, match="dest .* already exists"):
            assembler.apply_proposal(fd, base, proposal,
                                     work_item_scope=_scope(proposal))
        assert (root / "from.txt").read_bytes() == b"m\n"
    finally:
        os.close(fd)


def test_duplicate_work_item_refuses(tmp_path):
    root, fd, base = _checkout(tmp_path, {"a.txt": (b"x\n", "100644")})
    proposal = {"changes": [
        {"work_item_id": WID_A, "kind": "add", "path": "b.txt",
         "rename_source": None, "content_after_hex": b"1\n".hex(),
         "mode_after": "100644", "blob_before": None, "mode_before": None},
        {"work_item_id": WID_A, "kind": "add", "path": "c.txt",
         "rename_source": None, "content_after_hex": b"2\n".hex(),
         "mode_after": "100644", "blob_before": None, "mode_before": None}]}
    try:
        with pytest.raises(HSCValidationError, match="reuses a work_item_id"):
            assembler.apply_proposal(fd, base, proposal,
                                     work_item_scope=_scope(proposal))
    finally:
        os.close(fd)


def test_non_hex_work_item_refuses(tmp_path):
    # finding 001729-3: a 64-char non-hex identity must fail the canonical
    # SHA-256 grammar, never merely len==64.
    root, fd, base = _checkout(tmp_path, {"a.txt": (b"x\n", "100644")})
    proposal = {"changes": [
        {"work_item_id": "z" * 64, "kind": "add", "path": "b.txt",
         "rename_source": None, "content_after_hex": b"1\n".hex(),
         "mode_after": "100644", "blob_before": None, "mode_before": None}]}
    try:
        with pytest.raises(HSCValidationError, match="work_item_id"):
            assembler.apply_proposal(fd, base, proposal,
                                     work_item_scope=_scope(proposal))
    finally:
        os.close(fd)


def test_unpredicted_change_refuses(tmp_path):
    # finding 001729-3: an operation outside the frozen authorized scope must be
    # refused BEFORE any write, not applied and left to later real-diff.
    root, fd, base = _checkout(tmp_path, {"a.txt": (b"x\n", "100644")})
    proposal = {"changes": [
        {"work_item_id": WID_A, "kind": "add", "path": "sneaky.txt",
         "rename_source": None, "content_after_hex": b"1\n".hex(),
         "mode_after": "100644", "blob_before": None, "mode_before": None}]}
    scope = {WID_A: [{"path": "authorized.txt", "kind": "add",
                      "rename_source": None, "blob_before": None,
                      "mode_before": None, "required": False}]}
    try:
        with pytest.raises(HSCValidationError, match="not owned by work item"):
            assembler.apply_proposal(fd, base, proposal, work_item_scope=scope)
        assert not (root / "sneaky.txt").exists()  # nothing written
    finally:
        os.close(fd)


def test_relabeled_op_refuses(tmp_path):
    # finding 001734-2: an operation authorized for work item B cannot be
    # relabeled to work item A and slip through a program-wide union — ownership
    # is keyed by (work_item_id, change).
    root, fd, base = _checkout(tmp_path, {"a.txt": (b"x\n", "100644")})
    proposal = {"changes": [
        {"work_item_id": WID_A, "kind": "add", "path": "owned-by-b.txt",
         "rename_source": None, "content_after_hex": b"1\n".hex(),
         "mode_after": "100644", "blob_before": None, "mode_before": None}]}
    # the operation exists in the scope, but owned by WID_B, not WID_A
    scope = {WID_B: [{"path": "owned-by-b.txt", "kind": "add",
                      "rename_source": None, "blob_before": None,
                      "mode_before": None, "required": False}]}
    try:
        with pytest.raises(HSCValidationError, match="not owned by work item"):
            assembler.apply_proposal(fd, base, proposal, work_item_scope=scope)
        assert not (root / "owned-by-b.txt").exists()
    finally:
        os.close(fd)


def test_missing_required_prediction_refuses(tmp_path):
    root, fd, base = _checkout(tmp_path, {"a.txt": (b"x\n", "100644")})
    proposal = {"changes": [
        {"work_item_id": WID_A, "kind": "add", "path": "b.txt",
         "rename_source": None, "content_after_hex": b"1\n".hex(),
         "mode_after": "100644", "blob_before": None, "mode_before": None}]}
    scope = _scope(proposal)
    scope[WID_A].append(
        {"path": "must-have.txt", "kind": "add", "rename_source": None,
         "blob_before": None, "mode_before": None, "required": True})
    try:
        with pytest.raises(HSCValidationError,
                           match="required predicted change .* is missing"):
            assembler.apply_proposal(fd, base, proposal, work_item_scope=scope)
    finally:
        os.close(fd)
