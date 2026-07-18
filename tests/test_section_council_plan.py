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
             out_ws=WS):
    """The eight central roots plus one runtime + private-output root, as plan
    root-input dicts backed by real no-follow directory handles."""
    def mk(kind, name, view="full-native-tree-v1", ws=None, delegated=None):
        fd = _dir(tmp_path, name)
        fds.append(fd)
        row = {"root_kind": kind, "view_kind": view, "dir_fd": fd,
               "anchor_name": name, "workspace_id": ws}
        if delegated is not None:
            row["delegated_root_kind"] = delegated
        return row

    roots = [
        mk("candidate", "candidate", ws=candidate_ws),
        mk("common-git", "common-git"),
        mk("integration-checkout", "checkout",
           view="checkout-excluding-delegated-dotgit-v1",
           delegated="common-git"),
        mk("council-root", "council"),
        mk("owner-anchors", "anchors"),
        mk("other-worker-leaves", "leaves"),
        mk("canonical-evidence", "evidence"),
        mk("hidden-suites", "hidden"),
        mk("runtime-readonly", "runtime", ws=out_ws),
        mk(out_kind, "output", ws=out_ws),
    ]
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
    # one pre/post requirement per root
    assert p["observation_count"] == 20 == len(p["observations"])
    phases = {o["phase"] for o in p["observations"]}
    assert phases == {"pre-dispatch", "post-worker"}
    # roots + observations are sorted by their reconstructed ids
    assert [r["root_id"] for r in p["roots"]] == \
        sorted(r["root_id"] for r in p["roots"])
    assert [o["observation_id"] for o in p["observations"]] == \
        sorted(o["observation_id"] for o in p["observations"])
    # the checkout binds the common-Git root as its delegated control root
    checkout = next(r for r in p["roots"]
                    if r["root_kind"] == "integration-checkout")
    common = next(r for r in p["roots"] if r["root_kind"] == "common-git")
    assert checkout["delegated_control_root_id"] == common["root_id"]
    assert checkout["delegated_control_identity"] == common["native_identity"]
    assert checkout["workspace_id"] is None


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


def test_assembly_plan_all_null_context(tmp_path):
    fds = []
    try:
        # central roots only (candidate keeps a workspace); assembly needs no
        # private output/runtime root in the validator's minimum.
        roots = [r for r in _central(tmp_path, fds)
                 if r["root_kind"] in plan.CENTRAL_KINDS]
        record = plan.build_native_inventory_plan(
            program_ref=PROGRAM_REF, base_commit=BASE, scope="assembly",
            work_item_id=None, role=None, attempt=None, workspace_id=None,
            roots=roots)
    finally:
        for fd in fds:
            os.close(fd)
    assert validate_record(record) is not None
    p = record["payload"]
    assert {o["phase"] for o in p["observations"]} == \
        {"pre-assembly", "post-assembly"}
    assert all(o["work_item_id"] is None and o["role"] is None
               and o["attempt"] is None and o["workspace_id"] is None
               for o in p["observations"])


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
