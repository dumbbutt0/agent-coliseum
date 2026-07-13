"""World-specific instance identities (profile §4, Appendix A) — S1.

Immutable **instances** live in exactly one world-line: each is content-addressed from
its spec id, its ``world_line_id``, and a frozen ``deterministic_logical_instance_key``
(a logical index — never wall-clock/PID/UUID/object-identity/mutable-name/run-row).
Sibling world-lines share a spec but every instance id differs, and — the load-bearing
isolation rule — nothing crosses between world-lines: an instance whose
``world_line_id`` differs from a referencing context is refused
(:func:`assert_same_world_line`). Instance mutable STATE and inter-instance references
(location) are later slices; this slice is identity only.
"""
from __future__ import annotations

from coliseum.textlab._content_record import ContentRecord, ContentRecordError
from coliseum.textlab.spatial.world import SPATIAL_SCHEMA_VERSION


def _require_str(name: str, value) -> str:
    if not isinstance(value, str) or not value:
        raise ContentRecordError(f"{name} must be a non-empty string")
    return value


class _Instance(ContentRecord):
    """Shared instance shape: ``{spatial_schema_version, <spec_field>, world_line_id,
    deterministic_logical_instance_key}``. Subclasses set DOMAIN/ID_FIELD/SPEC_FIELD."""
    __slots__ = ()
    SPEC_FIELD: str = ""

    def __init__(self, spec_id: str, world_line_id: str,
                 deterministic_logical_instance_key: str):
        super().__init__({
            "spatial_schema_version": SPATIAL_SCHEMA_VERSION,
            type(self).SPEC_FIELD: _require_str(type(self).SPEC_FIELD, spec_id),
            "world_line_id": _require_str("world_line_id", world_line_id),
            "deterministic_logical_instance_key": _require_str(
                "deterministic_logical_instance_key",
                deterministic_logical_instance_key),
        })

    @property
    def world_line_id(self) -> str:
        return self.content["world_line_id"]


class RoomInstance(_Instance):
    __slots__ = ()
    DOMAIN = "spatial.room_instance.v1"
    ID_FIELD = "room_instance_id"
    SPEC_FIELD = "room_spec_id"


class PortalInstance(_Instance):
    __slots__ = ()
    DOMAIN = "spatial.portal_instance.v1"
    ID_FIELD = "portal_instance_id"
    SPEC_FIELD = "portal_spec_id"


class ObjectInstance(_Instance):
    __slots__ = ()
    DOMAIN = "spatial.object_instance.v1"
    ID_FIELD = "object_instance_id"
    SPEC_FIELD = "object_spec_id"


class AgentBodyInstance(_Instance):
    __slots__ = ()
    DOMAIN = "spatial.agent_body_instance.v1"
    ID_FIELD = "agent_body_id"
    SPEC_FIELD = "agent_body_spec_id"


def assert_same_world_line(expected_world_line_id: str, *instances: "_Instance") -> None:
    """Fail closed unless every instance belongs to ``expected_world_line_id``. The
    cross-world isolation primitive: no state / object / body / observation may cross
    between world-lines, so any referencing context validates membership first."""
    if not isinstance(expected_world_line_id, str) or not expected_world_line_id:
        raise ContentRecordError("expected_world_line_id must be a non-empty string")
    for inst in instances:
        if not isinstance(inst, _Instance):
            raise ContentRecordError("assert_same_world_line takes spatial instances")
        if inst.world_line_id != expected_world_line_id:
            raise ContentRecordError(
                f"cross-world reference refused: instance in world-line "
                f"{inst.world_line_id[:12]!r} referenced from context "
                f"{expected_world_line_id[:12]!r}")
