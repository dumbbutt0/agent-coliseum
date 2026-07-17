"""Native inventory producer proofs (HSC-B component 2)."""

from __future__ import annotations

import hashlib
import os

import pytest

from tools.council.schemas import domain_hash
from tools.section_council import inventory, native
from tools.section_council.core import (file_id, filesystem_id,
                                        locator_sha256)
from tools.section_council.native import NativeIdentityUnavailable
from tools.section_council.records import validate_record

_AVAILABLE = True
try:
    native.probe_availability()
except NativeIdentityUnavailable:
    _AVAILABLE = False

requires_native = pytest.mark.skipif(
    not _AVAILABLE, reason="linux-native-id-v1 primitives unavailable")

H1 = "1" * 64
H2 = "2" * 64
REF = {"record_id": H1, "content_sha256": H2}
PROGRAM_REF = {"record_id": "3" * 64, "content_sha256": "4" * 64}


def _locator():
    return {
        "platform": "linux-bwrap-v1", "anchor_name": "candidate",
        "anchor_id": "5" * 64, "segments_hex": [],
        "resolution": "openat2-beneath-no-magiclinks-no-symlinks-v1",
    }


def _root_spec(root_observation):
    loc = _locator()
    spec = {
        "root_id": "0" * 64, "root_kind": "candidate",
        "view_kind": "full-native-tree-v1", "namespace_id": "0" * 64,
        "locator": loc, "locator_sha256": locator_sha256(loc),
        "native_identity": root_observation,
        "filesystem_id": filesystem_id(root_observation),
        "file_id": file_id(root_observation),
        "workspace_id": "6" * 64,
        "delegated_control_root_id": None, "delegated_control_identity": None,
    }
    spec["namespace_id"] = domain_hash("council:native-namespace:v1", {
        "locator_sha256": spec["locator_sha256"], "program_ref": PROGRAM_REF,
        "root_kind": "candidate", "view_kind": "full-native-tree-v1",
        "workspace_id": spec["workspace_id"]})
    without = dict(spec)
    without.pop("root_id")
    spec["root_id"] = domain_hash("council:native-root:v1", {
        "program_ref": PROGRAM_REF, "root_spec": without})
    return spec


def _assembly_requirement(root_id, phase="pre-assembly"):
    row = {"root_id": root_id, "phase": phase, "scope": "assembly",
           "work_item_id": None, "role": None, "attempt": None,
           "workspace_id": None}
    preimage = dict(row)
    preimage["program_ref"] = PROGRAM_REF
    row = {"observation_id": domain_hash(
        "council:native-observation-requirement:v1", preimage), **row}
    return row


def _build(root_dir):
    root_fd = os.open(str(root_dir), os.O_RDONLY | os.O_DIRECTORY)
    try:
        root_obs = inventory.observe_root(root_fd)
        spec = _root_spec(root_obs)
        req = _assembly_requirement(spec["root_id"])
        record = inventory.build_native_inventory(
            program_ref=PROGRAM_REF, base_commit="0" * 40,
            native_inventory_plan_ref=REF, root_spec=spec,
            observation_requirement=req, observer_assignment_ref=None,
            observation_workspace_id=None, root_dir_fd=root_fd)
    finally:
        os.close(root_fd)
    return record, spec, req


@requires_native
def test_inventory_record_validates_and_binds_content(tmp_path):
    root = tmp_path / "root"; root.mkdir()
    (root / "a.txt").write_bytes(b"alpha")
    sub = root / "d"
    sub.mkdir()
    (sub / "b.txt").write_bytes(b"beta")
    record, spec, req = _build(root)
    assert validate_record(record) is not None
    entries = record["payload"]["entries"]
    by_path = {tuple(bytes.fromhex(s) for s in e["path"]["segments_hex"]): e
               for e in entries}
    # every descendant present; root itself is not an entry
    assert set(by_path) == {(b"a.txt",), (b"d",), (b"d", b"b.txt")}
    assert by_path[(b"a.txt",)]["content_sha256"] == \
        hashlib.sha256(b"alpha").hexdigest()
    assert by_path[(b"d",)]["content_sha256"] is None  # directory
    assert by_path[(b"d", b"b.txt")]["content_sha256"] == \
        hashlib.sha256(b"beta").hexdigest()
    # entries are sorted by decoded native path
    decoded = [tuple(bytes.fromhex(s) for s in e["path"]["segments_hex"])
               for e in entries]
    assert decoded == sorted(decoded)


@requires_native
def test_inventory_sha256_recomputes(tmp_path):
    root = tmp_path / "root"; root.mkdir()
    (root / "x").write_bytes(b"x")
    record, spec, req = _build(root)
    recomputed = inventory.inventory_content_sha256(
        native_inventory_plan_ref=REF, root_spec=spec,
        observation_requirement=req, observer_assignment_ref=None,
        observation_workspace_id=None, phase="pre-assembly",
        entries=record["payload"]["entries"])
    assert record["payload"]["inventory_sha256"] == recomputed
    # observed root identity is bound
    assert record["payload"]["observed_root_filesystem_id"] == \
        spec["filesystem_id"]
    assert record["payload"]["observed_root_file_id"] == spec["file_id"]


@requires_native
def test_dotgit_excluded_only_in_checkout_view(tmp_path):
    root = tmp_path / "root"; root.mkdir()
    gitdir = root / ".git"
    gitdir.mkdir()
    (gitdir / "HEAD").write_bytes(b"ref: refs/heads/main\n")
    (root / "keep").write_bytes(b"k")
    root_fd = os.open(str(root), os.O_RDONLY | os.O_DIRECTORY)
    try:
        full = inventory.walk_root(root_fd, exclude_dotgit=False)
        checkout = inventory.walk_root(root_fd, exclude_dotgit=True)
    finally:
        os.close(root_fd)
    full_paths = {tuple(bytes.fromhex(s) for s in e["path"]["segments_hex"])
                  for e in full}
    checkout_paths = {tuple(bytes.fromhex(s) for s in e["path"]["segments_hex"])
                      for e in checkout}
    assert (b".git",) in full_paths and (b".git", b"HEAD") in full_paths
    assert not any(p and p[0] == b".git" for p in checkout_paths)
    assert (b"keep",) in checkout_paths


@requires_native
def test_symlink_descendant_fails_closed(tmp_path):
    root = tmp_path / "root"; root.mkdir()
    (root / "real").write_bytes(b"r")
    os.symlink("real", str(root / "link"))
    root_fd = os.open(str(root), os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(NativeIdentityUnavailable):
            inventory.walk_root(root_fd)
    finally:
        os.close(root_fd)


@requires_native
def test_swapped_root_spec_refuses(tmp_path):
    root = tmp_path / "root"; root.mkdir()
    (root / "f").write_bytes(b"f")
    other = tmp_path / "other"
    other.mkdir()
    root_fd = os.open(str(root), os.O_RDONLY | os.O_DIRECTORY)
    other_fd = os.open(str(other), os.O_RDONLY | os.O_DIRECTORY)
    try:
        spec = _root_spec(inventory.observe_root(other_fd))  # wrong root
        req = _assembly_requirement(spec["root_id"])
        with pytest.raises(NativeIdentityUnavailable, match="differs from its plan"):
            inventory.build_native_inventory(
                program_ref=PROGRAM_REF, base_commit="0" * 40,
                native_inventory_plan_ref=REF, root_spec=spec,
                observation_requirement=req, observer_assignment_ref=None,
                observation_workspace_id=None, root_dir_fd=root_fd)
    finally:
        os.close(root_fd)
        os.close(other_fd)
