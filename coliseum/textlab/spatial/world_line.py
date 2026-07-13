"""World-line (fork) identity (profile §4.1, Appendix A) — S1.

``world_line_id`` is a NEW lineage dimension, parallel to and never redefining the
existing ``control_of`` twin lineage. A **root** world-line is content-addressed from
its world spec + initial state; a **forked child** is content-addressed from its
parent + the exact fork decision + the changed/unchanged comparison dimensions —
computed BEFORE any fork record, self-excluded, so parent → child form a strict
acyclic order. Sibling forks share an immutable spec but differ in
``world_line_id`` and in every mutable instance id; nothing crosses between them.
"""
from __future__ import annotations

from coliseum.textlab._content_record import ContentRecord, ContentRecordError
from coliseum.textlab.spatial.world import SPATIAL_SCHEMA_VERSION

_ROOT_KEYS = frozenset({
    "spatial_schema_version", "spatial_world_spec_id", "initial_state_key",
})
_FORKED_KEYS = frozenset({
    "spatial_schema_version", "parent_world_line_id", "source_fork_decision_hash",
    "changed_dimension", "unchanged_comparison_dims",
})


def _require_str(name: str, value) -> str:
    if not isinstance(value, str) or not value:
        raise ContentRecordError(f"{name} must be a non-empty string")
    return value


class WorldLine(ContentRecord):
    """A world-line identity — build via :meth:`root` or :meth:`forked`; direct
    construction accepts only an exact root/forked preimage."""
    __slots__ = ()
    DOMAIN = "spatial.world_line.v1"
    ID_FIELD = "world_line_id"

    def __init__(self, preimage: dict):
        if not isinstance(preimage, dict):
            raise ContentRecordError("preimage must be a dict")
        keys = set(preimage)
        if keys != _ROOT_KEYS and keys != _FORKED_KEYS:
            raise ContentRecordError(
                "world_line preimage must be exactly a root "
                f"{sorted(_ROOT_KEYS)} or forked {sorted(_FORKED_KEYS)} key set")
        if preimage["spatial_schema_version"] != SPATIAL_SCHEMA_VERSION:
            raise ContentRecordError(
                f"spatial_schema_version must be {SPATIAL_SCHEMA_VERSION!r}")
        super().__init__(preimage)

    @property
    def is_root(self) -> bool:
        return "spatial_world_spec_id" in self.content

    @classmethod
    def root(cls, spatial_world_spec_id: str, initial_state_key: str) -> "WorldLine":
        return cls({
            "spatial_schema_version": SPATIAL_SCHEMA_VERSION,
            "spatial_world_spec_id": _require_str(
                "spatial_world_spec_id", spatial_world_spec_id),
            "initial_state_key": _require_str("initial_state_key", initial_state_key),
        })

    @classmethod
    def forked(cls, parent_world_line_id: str, source_fork_decision_hash: str,
               changed_dimension: str, unchanged_comparison_dims: dict) -> "WorldLine":
        if not isinstance(unchanged_comparison_dims, dict):
            raise ContentRecordError("unchanged_comparison_dims must be a dict")
        return cls({
            "spatial_schema_version": SPATIAL_SCHEMA_VERSION,
            "parent_world_line_id": _require_str(
                "parent_world_line_id", parent_world_line_id),
            "source_fork_decision_hash": _require_str(
                "source_fork_decision_hash", source_fork_decision_hash),
            "changed_dimension": _require_str("changed_dimension", changed_dimension),
            "unchanged_comparison_dims": unchanged_comparison_dims,
        })
