"""Native-inventory plan expander proofs (HSC-B component 6)."""

from __future__ import annotations

import os

import pytest

from tools.section_council import plan
from tools.section_council.core import HSCValidationError
from tools.section_council.records import validate_record

PROGRAM_REF = {"record_id": "a" * 64, "content_sha256": "b" * 64}
BASE = "c" * 40
WS = "d" * 64          # plan workspace
CAND_WS = "e" * 64     # candidate workspace


def _dir(tmp_path, name):
    path = tmp_path / name
    path.mkdir()
    return os.open(str(path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)


def _central(tmp_path, fds, *, candidate_ws=CAND_WS, out_kind="builder-output",
             out_ws=WS, extra=()):
    """The eight central roots plus one runtime + private-output root (plus any
    ``extra`` inputs), backed by real no-follow directory handles.

    ``common-git`` carries no anchor_name: its locator is derived as the checkout
    anchor plus the ``.git`` segment and its ``dir_fd`` is a distinct directory
    standing in for the live ``.git``."""
    def mk(kind, name, view="full-native-tree-v1", ws=None, anchor=True):
        fd = _dir(tmp_path, name)
        fds.append(fd)
        row = {"root_kind": kind, "view_kind": view, "dir_fd": fd,
               "workspace_id": ws}
        if anchor:
            row["anchor_name"] = name
        return row

    roots = [
        mk("candidate", "candidate", ws=candidate_ws),
        mk("common-git", "common-git", anchor=False),   # derived from checkout
        mk("integration-checkout", "checkout",
           view="checkout-excluding-delegated-dotgit-v1"),
        mk("council-root", "council"),
        mk("owner-anchors", "anchors"),
        mk("other-worker-leaves", "leaves"),
        mk("canonical-evidence", "evidence"),
        mk("hidden-suites", "hidden"),
        mk("runtime-readonly", "runtime", ws=out_ws),
        mk(out_kind, "output", ws=out_ws),
    ]
    roots.extend(extra)
    return roots


def test_builder_dispatch_plan_validates(tmp_path):
    fds = []
    try:
        roots = _central(tmp_path, fds)
        record = plan.build_native_inventory_plan(
            program_ref=PROGRAM_REF, base_commit=BASE, scope="builder-dispatch",
            work_item_id="1" * 64, role="builder", attempt=0, workspace_id=WS,
            roots=roots)
    finally:
        for fd in fds:
            os.close(fd)
    assert validate_record(record) is not None
    p = record["payload"]
    assert p["root_count"] == 10 == len(p["roots"])
    assert p["observation_count"] == 20 == len(p["observations"])
    assert {o["phase"] for o in p["observations"]} == {"pre-dispatch",
                                                       "post-worker"}
    assert [r["root_id"] for r in p["roots"]] == \
        sorted(r["root_id"] for r in p["roots"])
    checkout = next(r for r in p["roots"]
                    if r["root_kind"] == "integration-checkout")
    common = next(r for r in p["roots"] if r["root_kind"] == "common-git")
    # finding 001729-0: the checkout delegates to common-Git, and the common-Git
    # locator is EXACTLY the checkout locator plus the .git segment (the relation
    # the integrated store validator requires).
    assert checkout["delegated_control_root_id"] == common["root_id"]
    assert checkout["delegated_control_identity"] == common["native_identity"]
    assert checkout["workspace_id"] is None
    assert common["locator"]["anchor_id"] == checkout["locator"]["anchor_id"]
    assert common["locator"]["segments_hex"] == \
        checkout["locator"]["segments_hex"] + ["2e676974"]


def test_assessor_dispatch_plan_validates(tmp_path):
    fds = []
    try:
        roots = _central(tmp_path, fds, out_kind="assessor-output")
        record = plan.build_native_inventory_plan(
            program_ref=PROGRAM_REF, base_commit=BASE, scope="assessor-dispatch",
            work_item_id="1" * 64, role="assessor", attempt=1, workspace_id=WS,
            roots=roots)
    finally:
        for fd in fds:
            os.close(fd)
    assert validate_record(record) is not None
    assert record["payload"]["role"] == "assessor"


def test_assembly_plan_keeps_multiple_output_roots(tmp_path):
    # finding 001729-0 (second half): the assembly union may carry several
    # runtime/output roots; a per-kind collapse would silently narrow it. Two
    # builder-output roots (distinct dirs, distinct workspaces) must both survive.
    fds = []
    try:
        extra_fd = _dir(tmp_path, "output2")
        fds.append(extra_fd)
        extra = [{"root_kind": "builder-output",
                  "view_kind": "full-native-tree-v1", "dir_fd": extra_fd,
                  "anchor_name": "output2", "workspace_id": "f" * 64}]
        roots = _central(tmp_path, fds, extra=extra)
        record = plan.build_native_inventory_plan(
            program_ref=PROGRAM_REF, base_commit=BASE, scope="assembly",
            work_item_id=None, role=None, attempt=None, workspace_id=None,
            roots=roots)
    finally:
        for fd in fds:
            os.close(fd)
    assert validate_record(record) is not None
    p = record["payload"]
    outputs = [r for r in p["roots"] if r["root_kind"] == "builder-output"]
    assert len(outputs) == 2  # neither collapsed away
    assert {o["phase"] for o in p["observations"]} == {"pre-assembly",
                                                       "post-assembly"}


def test_missing_central_root_refuses(tmp_path):
    fds = []
    try:
        roots = [r for r in _central(tmp_path, fds)
                 if r["root_kind"] != "hidden-suites"]
        with pytest.raises(HSCValidationError,
                           match="omits or duplicates a required central root"):
            plan.build_native_inventory_plan(
                program_ref=PROGRAM_REF, base_commit=BASE,
                scope="builder-dispatch", work_item_id="1" * 64, role="builder",
                attempt=0, workspace_id=WS, roots=roots)
    finally:
        for fd in fds:
            os.close(fd)


def test_dispatch_plan_without_output_root_refuses(tmp_path):
    fds = []
    try:
        roots = [r for r in _central(tmp_path, fds)
                 if r["root_kind"] != "builder-output"]
        with pytest.raises(HSCValidationError,
                           match="lacks its runtime or private output root"):
            plan.build_native_inventory_plan(
                program_ref=PROGRAM_REF, base_commit=BASE,
                scope="builder-dispatch", work_item_id="1" * 64, role="builder",
                attempt=0, workspace_id=WS, roots=roots)
    finally:
        for fd in fds:
            os.close(fd)
