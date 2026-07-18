"""Deterministic native-inventory plan expansion (HSC-B component 6).

The trusted scheduler freezes one ``section_native_inventory_plan.v1`` per exact
dispatch attempt (one for the builder, one for the assessor) and exactly one for
the single assembly operation. A plan is the *closed* required-root set: the
central protected roots (candidate, integration checkout, common Git, Council
root, owner anchors, other worker leaves, canonical evidence, hidden suites)
plus — for a dispatch — that dispatch's runtime and private-output roots, and for
the assembly the union of every runtime and dispatch-output root used by the
program (design §6.7 lines 1109-1165).

The expander opens each root's directory no-follow, resolves it as an enrolled
anchor (``native.enrolled_anchor`` — the one canonical
``council:native-anchor:v1`` derivation), and reconstructs every derived id the
HSC-A validator checks: ``locator_sha256`` from the canonical locator,
``filesystem_id``/``file_id`` from the frozen observation, ``namespace_id`` from
the locator/program/kind/view/workspace, and ``root_id`` from the complete spec.
It then emits one pre/post observation requirement per root for the plan's exact
phase pair. No worker chooses any of these ids; the closed policy expansion — not
a builder-selected phase subset — determines the exhaustive requirement set.
"""

from __future__ import annotations

from typing import Any

from tools.council.schemas import domain_hash

from .core import locator_sha256
from .native import enrolled_anchor
from .records import make_record

_PLATFORM = "linux-bwrap-v1"
_RESOLUTION = "openat2-beneath-no-magiclinks-no-symlinks-v1"
_NAMESPACE = "council:native-namespace:v1"
_ROOT = "council:native-root:v1"
_OBSERVATION = "council:native-observation-requirement:v1"

# The eight central protected roots present in every plan (design §6.7).
CENTRAL_KINDS = ("candidate", "integration-checkout", "common-git",
                 "council-root", "owner-anchors", "other-worker-leaves",
                 "canonical-evidence", "hidden-suites")

_DISPATCH_PHASES = ("pre-dispatch", "post-worker")
_ASSEMBLY_PHASES = ("pre-assembly", "post-assembly")


def _root_spec(program_ref: dict, *, root_kind: str, view_kind: str,
               dir_fd: int, anchor_name: str, workspace_id: str | None,
               delegated: dict | None) -> dict[str, Any]:
    """One ``NATIVE_ROOT_SPEC`` whose every id reconstructs from the live
    no-follow observation of ``dir_fd``.

    ``delegated`` (only for the ``checkout-excluding-delegated-dotgit-v1`` view)
    is the already-built common-Git root spec; its ``root_id`` and
    ``native_identity`` are bound as the delegated control root."""
    enrolled = enrolled_anchor(dir_fd, anchor_name)
    locator = {
        "platform": _PLATFORM,
        "anchor_name": anchor_name,
        "anchor_id": enrolled["anchor_id"],
        "segments_hex": [],
        "resolution": _RESOLUTION,
    }
    loc_sha = locator_sha256(locator)
    namespace_id = domain_hash(_NAMESPACE, {
        "locator_sha256": loc_sha,
        "program_ref": program_ref,
        "root_kind": root_kind,
        "view_kind": view_kind,
        "workspace_id": workspace_id,
    })
    if view_kind == "checkout-excluding-delegated-dotgit-v1":
        if delegated is None:
            raise ValueError("a checkout view requires a delegated common-Git "
                             "root spec")
        delegated_root_id = delegated["root_id"]
        delegated_identity = delegated["native_identity"]
    else:
        if delegated is not None:
            raise ValueError("a full-native-tree root cannot delegate a control "
                             "root")
        delegated_root_id = None
        delegated_identity = None
    without_id = {
        "root_kind": root_kind,
        "view_kind": view_kind,
        "namespace_id": namespace_id,
        "locator": locator,
        "locator_sha256": loc_sha,
        "native_identity": enrolled["native_identity"],
        "filesystem_id": enrolled["filesystem_id"],
        "file_id": enrolled["file_id"],
        "workspace_id": workspace_id,
        "delegated_control_root_id": delegated_root_id,
        "delegated_control_identity": delegated_identity,
    }
    root_id = domain_hash(_ROOT, {"program_ref": program_ref,
                                  "root_spec": without_id})
    return {"root_id": root_id, **without_id}


def _observation(program_ref: dict, *, root_id: str, phase: str, scope: str,
                 work_item_id: str | None, role: str | None,
                 attempt: int | None, workspace_id: str | None) \
        -> dict[str, Any]:
    """One ``NATIVE_OBSERVATION_REQUIREMENT`` whose ``observation_id``
    reconstructs from its exact context plus the program ref."""
    without_id = {
        "root_id": root_id,
        "phase": phase,
        "scope": scope,
        "work_item_id": work_item_id,
        "role": role,
        "attempt": attempt,
        "workspace_id": workspace_id,
    }
    preimage = dict(without_id)
    preimage["program_ref"] = program_ref
    observation_id = domain_hash(_OBSERVATION, preimage)
    return {"observation_id": observation_id, **without_id}


def build_native_inventory_plan(*, program_ref: dict, base_commit: str,
                                scope: str, work_item_id: str | None,
                                role: str | None, attempt: int | None,
                                workspace_id: str | None,
                                roots: list[dict]) -> dict:
    """Freeze one ``section_native_inventory_plan.v1`` from live no-follow root
    handles.

    ``roots`` is the caller-assembled closed required-root set: one dict per
    root with ``root_kind``, ``view_kind``, ``dir_fd`` (an open no-follow
    directory descriptor), ``anchor_name``, ``workspace_id``, and — for the
    integration checkout only — ``delegated_root_kind`` naming the common-Git
    root whose identity is delegated. The completeness/uniqueness/phase-coverage
    invariants are enforced by the HSC-A validator via ``make_record`` (a missing
    or duplicated central root, an unbalanced phase set, a colliding native
    object, or an id that fails to reconstruct all refuse the record)."""
    phases = _ASSEMBLY_PHASES if scope == "assembly" else _DISPATCH_PHASES

    # Two passes so a checkout root can bind an already-built common-Git spec:
    # every full-native-tree root first, then the delegated-.git checkout roots.
    specs_by_kind: dict[str, dict] = {}
    deferred: list[dict] = []
    for spec_input in roots:
        if spec_input["view_kind"] == "checkout-excluding-delegated-dotgit-v1":
            deferred.append(spec_input)
            continue
        spec = _root_spec(
            program_ref, root_kind=spec_input["root_kind"],
            view_kind=spec_input["view_kind"], dir_fd=spec_input["dir_fd"],
            anchor_name=spec_input["anchor_name"],
            workspace_id=spec_input["workspace_id"], delegated=None)
        specs_by_kind[spec_input["root_kind"]] = spec
    for spec_input in deferred:
        delegated_kind = spec_input["delegated_root_kind"]
        delegated = specs_by_kind.get(delegated_kind)
        if delegated is None:
            raise ValueError(f"checkout delegates to absent root "
                             f"{delegated_kind!r}")
        spec = _root_spec(
            program_ref, root_kind=spec_input["root_kind"],
            view_kind=spec_input["view_kind"], dir_fd=spec_input["dir_fd"],
            anchor_name=spec_input["anchor_name"],
            workspace_id=spec_input["workspace_id"], delegated=delegated)
        specs_by_kind[spec_input["root_kind"]] = spec

    specs = sorted(specs_by_kind.values(), key=lambda s: s["root_id"])
    observations = []
    for spec in specs:
        for phase in phases:
            observations.append(_observation(
                program_ref, root_id=spec["root_id"], phase=phase, scope=scope,
                work_item_id=work_item_id, role=role, attempt=attempt,
                workspace_id=workspace_id))
    observations.sort(key=lambda o: o["observation_id"])

    payload = {
        "program_ref": program_ref,
        "base_commit": base_commit,
        "scope": scope,
        "work_item_id": work_item_id,
        "role": role,
        "attempt": attempt,
        "workspace_id": workspace_id,
        "roots": specs,
        "root_count": len(specs),
        "observations": observations,
        "observation_count": len(observations),
    }
    return make_record("section_native_inventory_plan.v1", payload)
