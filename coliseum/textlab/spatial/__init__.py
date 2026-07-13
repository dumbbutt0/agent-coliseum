"""Minimal deterministic rooms-and-portals spatial substrate (SPATIAL-WORLD-MODEL
profile). NOT a game engine: no coordinates, no physics, no pathfinding beyond
deterministic traversal of explicitly-available portals. This package is the inert
identity + (later) truth/perception/belief layer whose trace emits the integrated
training-readiness records.

S0 (this slice): the immutable spec-identity layer only — content-addressed,
construction-frozen spec records + a collision-refusing registry + fail-closed
version dispatch. World-line, instances, scheduler, perception, and the trace are
later slices.
"""
from coliseum.textlab.spatial.instance import (AgentBodyInstance, ObjectInstance,
                                               PortalInstance, RoomInstance,
                                               assert_same_world_line)
from coliseum.textlab.spatial.world import (SPATIAL_SCHEMA_VERSION,
                                            AgentBodySpec, ObjectSpec,
                                            PerceptionRegime, PortalSpec, RoomSpec,
                                            SpatialWorldSpec, is_supported_version)
from coliseum.textlab.spatial.world_line import WorldLine

__all__ = [
    "SPATIAL_SCHEMA_VERSION", "is_supported_version",
    "PerceptionRegime", "RoomSpec", "PortalSpec", "ObjectSpec", "AgentBodySpec",
    "SpatialWorldSpec",
    "WorldLine",
    "RoomInstance", "PortalInstance", "ObjectInstance", "AgentBodyInstance",
    "assert_same_world_line",
]
