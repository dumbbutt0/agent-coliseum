"""Spatial spec-identity records (profile §3-§7, Appendix A) — S0.

The immutable **specification** layer: content-addressed, construction-frozen type
definitions for a rooms-and-portals world. Each record is a
:class:`ContentRecord` whose id is ``config_hash`` of a domain-separated, typed
preimage with the id field ABSENT (self-exclusion) — the exact ``_domain`` literal
and preimage key set are bound by the profile's Appendix A, so two conforming
implementations derive identical ids. List-valued preimage keys are canonicalised
(sorted, de-duplicated) so identity is order-independent.

This slice is INERT: pure identity, no world state, no instances, no simulation.
World-line + instance ids, the scheduler, perception, and the trace are later slices.
"""
from __future__ import annotations

from coliseum.textlab._content_record import ContentRecord, ContentRecordError

#: Frozen spatial schema version. Unknown versions fail closed for new execution;
#: historical replay uses an explicit supported-version dispatch (mirrors the run
#: schema's DISPATCHABLE_PARSER_VERSIONS). Renaming/removing/retyping a preimage
#: field bumps this.
SPATIAL_SCHEMA_VERSION = "0.1"

#: The set of spatial schema versions this build can execute/replay. New execution
#: uses SPATIAL_SCHEMA_VERSION; an unknown version is refused rather than guessed.
SUPPORTED_SPATIAL_SCHEMA_VERSIONS = frozenset({SPATIAL_SCHEMA_VERSION})


def is_supported_version(version: str) -> bool:
    return version in SUPPORTED_SPATIAL_SCHEMA_VERSIONS


def _require_str(name: str, value) -> str:
    if not isinstance(value, str) or not value:
        raise ContentRecordError(f"{name} must be a non-empty string")
    return value


def _sorted_unique_strs(name: str, values) -> list:
    """Canonicalise a preimage list: every entry a non-empty string, sorted and
    de-duplicated so the derived id is order- and duplicate-independent."""
    if not isinstance(values, (list, tuple)):
        raise ContentRecordError(f"{name} must be a list")
    out = []
    for v in values:
        if not isinstance(v, str) or not v:
            raise ContentRecordError(f"{name} entries must be non-empty strings")
        out.append(v)
    return sorted(set(out))


def _require_bool(name: str, value) -> bool:
    if not isinstance(value, bool):
        raise ContentRecordError(f"{name} must be a bool")
    return value


def _require_nonneg_int(name: str, value) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ContentRecordError(f"{name} must be a non-negative int")
    return value


def _optional_nonneg_int(name: str, value):
    if value is None:
        return None
    return _require_nonneg_int(name, value)


class PerceptionRegime(ContentRecord):
    """What an agent can observe — the spatial analogue of ``agent_regime_id``;
    world-truth-only fields are excluded so the regime id changes only when what the
    agent can observe changes."""
    __slots__ = ()
    DOMAIN = "spatial.perception_regime.v1"
    ID_FIELD = "perception_regime_id"

    def __init__(self, renderer_version: str, visibility_policy: str,
                 audibility_policy: str, observation_policy_version: str):
        super().__init__({
            "spatial_schema_version": SPATIAL_SCHEMA_VERSION,
            "renderer_version": _require_str("renderer_version", renderer_version),
            "visibility_policy": _require_str("visibility_policy", visibility_policy),
            "audibility_policy": _require_str("audibility_policy", audibility_policy),
            "observation_policy_version": _require_str(
                "observation_policy_version", observation_policy_version),
        })


class RoomSpec(ContentRecord):
    """A room type — no mutable state."""
    __slots__ = ()
    DOMAIN = "spatial.room_spec.v1"
    ID_FIELD = "room_spec_id"

    def __init__(self, semantic_name: str, room_type_tags, capacity,
                 default_visibility_policy: str, default_audibility_policy: str,
                 permitted_portal_attachment_points=()):
        super().__init__({
            "spatial_schema_version": SPATIAL_SCHEMA_VERSION,
            "semantic_name": _require_str("semantic_name", semantic_name),
            "room_type_tags": _sorted_unique_strs("room_type_tags", room_type_tags),
            "permitted_portal_attachment_points": _sorted_unique_strs(
                "permitted_portal_attachment_points", permitted_portal_attachment_points),
            "capacity": _optional_nonneg_int("capacity", capacity),
            "default_visibility_policy": _require_str(
                "default_visibility_policy", default_visibility_policy),
            "default_audibility_policy": _require_str(
                "default_audibility_policy", default_audibility_policy),
        })


class PortalSpec(ContentRecord):
    """A directed or bidirectional connection between two room specs."""
    __slots__ = ()
    DOMAIN = "spatial.portal_spec.v1"
    ID_FIELD = "portal_spec_id"
    _DIRECTIONALITY = ("directed", "bidirectional")

    def __init__(self, origin_room_spec_id: str, destination_room_spec_id: str,
                 directionality: str, traversal_duration_steps: int,
                 perception_behavior: str, supported_state_capabilities=()):
        if directionality not in self._DIRECTIONALITY:
            raise ContentRecordError(
                f"directionality must be one of {self._DIRECTIONALITY}")
        super().__init__({
            "spatial_schema_version": SPATIAL_SCHEMA_VERSION,
            "origin_room_spec_id": _require_str("origin_room_spec_id", origin_room_spec_id),
            "destination_room_spec_id": _require_str(
                "destination_room_spec_id", destination_room_spec_id),
            "directionality": directionality,
            "traversal_duration_steps": _require_nonneg_int(
                "traversal_duration_steps", traversal_duration_steps),
            "supported_state_capabilities": _sorted_unique_strs(
                "supported_state_capabilities", supported_state_capabilities),
            "perception_behavior": _require_str("perception_behavior", perception_behavior),
        })


class ObjectSpec(ContentRecord):
    """A typed object with explicit affordances — a closed set of authoritative state
    fields and allowed actions (never free-form prose)."""
    __slots__ = ()
    DOMAIN = "spatial.object_spec.v1"
    ID_FIELD = "object_spec_id"

    def __init__(self, object_type: str, portability: bool,
                 container_capability: bool, visibility_behavior: str,
                 exclusive_possession: bool, satisfies_portal_requirement: bool,
                 allowed_state_fields=(), allowed_actions=()):
        super().__init__({
            "spatial_schema_version": SPATIAL_SCHEMA_VERSION,
            "object_type": _require_str("object_type", object_type),
            "allowed_state_fields": _sorted_unique_strs(
                "allowed_state_fields", allowed_state_fields),
            "allowed_actions": _sorted_unique_strs("allowed_actions", allowed_actions),
            "portability": _require_bool("portability", portability),
            "container_capability": _require_bool("container_capability", container_capability),
            "visibility_behavior": _require_str("visibility_behavior", visibility_behavior),
            "exclusive_possession": _require_bool("exclusive_possession", exclusive_possession),
            "satisfies_portal_requirement": _require_bool(
                "satisfies_portal_requirement", satisfies_portal_requirement),
        })


class AgentBodySpec(ContentRecord):
    """The embodied agent type — its default perception regime and inventory limit."""
    __slots__ = ()
    DOMAIN = "spatial.agent_body_spec.v1"
    ID_FIELD = "agent_body_spec_id"

    def __init__(self, agent_body_type: str, default_perception_regime_id: str,
                 inventory_limit=None):
        super().__init__({
            "spatial_schema_version": SPATIAL_SCHEMA_VERSION,
            "agent_body_type": _require_str("agent_body_type", agent_body_type),
            "default_perception_regime_id": _require_str(
                "default_perception_regime_id", default_perception_regime_id),
            "inventory_limit": _optional_nonneg_int("inventory_limit", inventory_limit),
        })


class SpatialWorldSpec(ContentRecord):
    """The immutable definition of a world: the sets of room/portal/object/agent-body
    specs it is built from, its perception regime, and its initial layout. References
    only pre-existing spec ids (construction order §4)."""
    __slots__ = ()
    DOMAIN = "spatial.world_spec.v1"
    ID_FIELD = "spatial_world_spec_id"

    def __init__(self, room_spec_ids, portal_spec_ids, object_spec_ids,
                 agent_body_spec_ids, perception_regime_id: str, initial_layout: dict):
        if not isinstance(initial_layout, dict):
            raise ContentRecordError("initial_layout must be a dict")
        super().__init__({
            "spatial_schema_version": SPATIAL_SCHEMA_VERSION,
            "room_spec_ids": _sorted_unique_strs("room_spec_ids", room_spec_ids),
            "portal_spec_ids": _sorted_unique_strs("portal_spec_ids", portal_spec_ids),
            "object_spec_ids": _sorted_unique_strs("object_spec_ids", object_spec_ids),
            "agent_body_spec_ids": _sorted_unique_strs(
                "agent_body_spec_ids", agent_body_spec_ids),
            "perception_regime_id": _require_str("perception_regime_id", perception_regime_id),
            "initial_layout": initial_layout,
        })
