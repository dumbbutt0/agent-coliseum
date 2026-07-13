"""Fork authorization + deterministic materialization — S2A (§8).

A child world-line inherits ONLY the exact authorized parent snapshot named by a
:class:`ForkDecision` (whose id is the S1 `source_fork_decision_hash`). Materialization
remaps every parent instance id — placements, lifecycle, and nested location refs — into
the child world-line via `(spec_id, deterministic_logical_instance_key)`, registers the
child instances, rewrites the state, inherits the parent's logical clock, admits it, and
binds provenance in a :class:`ForkInitialization`. Nothing crosses between world-lines.
"""
from __future__ import annotations

import copy

from coliseum.textlab._content_record import ContentRecord, ContentRecordError
from coliseum.textlab.spatial.instance import (AgentBodyInstance, ObjectInstance,
                                               PortalInstance, RoomInstance)
from coliseum.textlab.spatial.state import (WorldState, admit_world_state,
                                            _location_ref_ids)
from coliseum.textlab.spatial.world_line import WorldLine

FORK_DECISION_SCHEMA_VERSION = "1"
FORK_INITIALIZATION_SCHEMA_VERSION = "1"

# instance domain -> (class, spec-field) for deterministic re-instantiation.
_INSTANCE_KINDS = {
    "spatial.room_instance.v1": (RoomInstance, "room_spec_id"),
    "spatial.portal_instance.v1": (PortalInstance, "portal_spec_id"),
    "spatial.object_instance.v1": (ObjectInstance, "object_spec_id"),
    "spatial.agent_body_instance.v1": (AgentBodyInstance, "agent_body_spec_id"),
}


def _require_str(name, value):
    if not isinstance(value, str) or not value:
        raise ContentRecordError(f"{name} must be a non-empty string")
    return value


class ForkDecision(ContentRecord):
    """Authorizes exactly one parent snapshot + step for a fork. Its id is the
    `source_fork_decision_hash` the S1 forked WorldLine was built with."""
    __slots__ = ()
    DOMAIN = "spatial.fork_decision.v1"
    ID_FIELD = "fork_decision_id"

    def __init__(self, parent_world_line_id, parent_state_hash, fork_logical_step,
                 changed_dimension, unchanged_comparison_dims, spatial_schema_version=None):
        from coliseum.textlab.spatial.world import SPATIAL_SCHEMA_VERSION
        if not isinstance(fork_logical_step, int) or isinstance(fork_logical_step, bool) \
                or fork_logical_step < 0:
            raise ContentRecordError("fork_logical_step must be a non-negative int")
        if not isinstance(unchanged_comparison_dims, dict):
            raise ContentRecordError("unchanged_comparison_dims must be a dict")
        super().__init__({
            "spatial_schema_version": spatial_schema_version or SPATIAL_SCHEMA_VERSION,
            "parent_world_line_id": _require_str("parent_world_line_id", parent_world_line_id),
            "parent_state_hash": _require_str("parent_state_hash", parent_state_hash),
            "fork_logical_step": fork_logical_step,
            "changed_dimension": _require_str("changed_dimension", changed_dimension),
            "unchanged_comparison_dims": unchanged_comparison_dims,
        })


class ForkInitialization(ContentRecord):
    __slots__ = ()
    DOMAIN = "spatial.fork_initialization.v1"
    ID_FIELD = "fork_initialization_id"

    def __init__(self, child_world_line_id, parent_world_line_id, parent_state_hash,
                 fork_logical_step, source_fork_decision_hash,
                 materialized_child_initial_state_hash, spatial_schema_version=None):
        from coliseum.textlab.spatial.world import SPATIAL_SCHEMA_VERSION
        if not isinstance(fork_logical_step, int) or isinstance(fork_logical_step, bool) \
                or fork_logical_step < 0:
            raise ContentRecordError("fork_logical_step must be a non-negative int")
        super().__init__({
            "spatial_schema_version": spatial_schema_version or SPATIAL_SCHEMA_VERSION,
            "child_world_line_id": _require_str("child_world_line_id", child_world_line_id),
            "parent_world_line_id": _require_str("parent_world_line_id", parent_world_line_id),
            "parent_state_hash": _require_str("parent_state_hash", parent_state_hash),
            "fork_logical_step": fork_logical_step,
            "source_fork_decision_hash": _require_str(
                "source_fork_decision_hash", source_fork_decision_hash),
            "materialized_child_initial_state_hash": _require_str(
                "materialized_child_initial_state_hash", materialized_child_initial_state_hash),
        })


def _referenced_instance_ids(state: "WorldState"):
    ids = set()
    for p in state.content["placements"]:
        ids.add(p["entity_id"])
        for _field, ref in _location_ref_ids(p["location"]):
            ids.add(ref)
    for e in state.content["entity_lifecycle"]:
        ids.add(e["entity_id"])
    return ids


def _remap(parent_ids, child_world_line_id, registry):
    """Total, type-preserving bijection parent id -> child id, re-deriving + registering
    each child instance under the child world-line."""
    mapping = {}
    for pid in sorted(parent_ids):
        try:
            inst = registry.get(pid)
        except ContentRecordError:
            raise ContentRecordError(f"fork references unregistered instance {pid[:12]!r}")
        kind = _INSTANCE_KINDS.get(inst.domain)
        if kind is None:
            raise ContentRecordError(f"fork instance {pid[:12]!r} has non-instance domain")
        cls, spec_field = kind
        c = inst.content
        child = cls(c[spec_field], child_world_line_id, c["deterministic_logical_instance_key"])
        registry.register(child)
        mapping[pid] = child.id
    if len(set(mapping.values())) != len(mapping):
        raise ContentRecordError("fork remap is not injective")
    return mapping


def _rewrite_location(loc, mapping):
    out = dict(loc)
    from coliseum.textlab.spatial.state import _LOCATION_REF_DOMAINS
    for k in out:
        if k in _LOCATION_REF_DOMAINS:
            out[k] = mapping[out[k]]
    return out


def materialize_fork(parent_state, child_world_line, fork_decision, registry):
    """Materialize the authorized child initial state + its ForkInitialization (§8).

    Fails closed on unauthorized/foreign/stale parent, unregistered child world-line,
    decision/world-line mismatch, or a non-admissible materialized child. Returns
    (child_initial_state, fork_initialization)."""
    if not isinstance(parent_state, WorldState):
        raise ContentRecordError("parent_state must be a WorldState")
    if not isinstance(child_world_line, WorldLine) or child_world_line.is_root:
        raise ContentRecordError("child_world_line must be a forked WorldLine")
    if not isinstance(fork_decision, ForkDecision):
        raise ContentRecordError("fork_decision must be a ForkDecision")
    # the fork_decision must be REGISTERED (admitted authorization), of the exact
    # domain, with content identical to the supplied decision (content-addressed).
    try:
        stored = registry.get(fork_decision.id)
    except ContentRecordError:
        raise ContentRecordError("fork_decision is not registered")
    if stored.domain != "spatial.fork_decision.v1" or stored.content != fork_decision.content:
        raise ContentRecordError("fork_decision is not a registered spatial.fork_decision.v1")
    # the parent snapshot must itself be admissible.
    admit_world_state(parent_state, registry)
    cwl = child_world_line.content
    D = fork_decision.content
    # authorization: the decision binds the EXACT parent snapshot + step, and the child
    # world-line was built from this decision + parent line.
    if D["parent_world_line_id"] != parent_state.world_line_id:
        raise ContentRecordError("fork_decision parent_world_line_id != parent state world-line")
    if D["parent_state_hash"] != parent_state.id:
        raise ContentRecordError("fork_decision does not authorize this parent snapshot")
    if D["fork_logical_step"] != parent_state.logical_step:
        raise ContentRecordError("fork_decision fork_logical_step != parent state step")
    if cwl["source_fork_decision_hash"] != fork_decision.id:
        raise ContentRecordError("child world-line was not built from this fork_decision")
    if cwl["parent_world_line_id"] != parent_state.world_line_id:
        raise ContentRecordError("child world-line parent != parent state world-line")

    mapping = _remap(_referenced_instance_ids(parent_state), child_world_line.id, registry)
    placements = []
    for p in parent_state.content["placements"]:
        placements.append({
            "entity_id": mapping[p["entity_id"]],
            "entity_kind": p["entity_kind"],
            "location": _rewrite_location(p["location"], mapping),
        })
    lifecycle = [{
        "entity_id": mapping[e["entity_id"]],
        "entity_kind": e["entity_kind"],
        "status": e["status"],
    } for e in parent_state.content["entity_lifecycle"]]

    # inherit the parent's logical clock so in-transit remaining travel is preserved.
    child_state = WorldState(child_world_line.id, parent_state.logical_step,
                             placements, lifecycle)
    admit_world_state(child_state, registry)

    fork_init = ForkInitialization(
        child_world_line_id=child_world_line.id,
        parent_world_line_id=parent_state.world_line_id,
        parent_state_hash=parent_state.id,
        fork_logical_step=parent_state.logical_step,
        source_fork_decision_hash=fork_decision.id,
        materialized_child_initial_state_hash=child_state.id)
    return child_state, fork_init
