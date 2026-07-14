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
from coliseum.textlab.spatial.state import (WorldState, admit_world_state,
                                            validate_location)
from coliseum.textlab.spatial.transition import (LocationTransition,
                                                 apply_transition, replay)
from coliseum.textlab.spatial.fork import (ForkDecision, ForkInitialization,
                                           materialize_fork)
from coliseum.textlab.spatial.scheduler import (SCHEDULER_VERSION, Activation,
                                                RandomDraw, RandomStream,
                                                SchedulerManifest, SchedulerRun,
                                                SchedulerState, WorldLineGenesis,
                                                action_script_commitment,
                                                legal_action_kinds,
                                                materialize_fork_closure,
                                                materialize_root, schedule,
                                                validate_world_line_genesis,
                                                verify_manifest)
from coliseum.textlab.spatial.perception import (RENDERER_VERSION,
                                                 assert_actor_content_schema,
                                                 closure_visible_state_commitment,
                                                 render_observation_pair)
from coliseum.textlab.spatial.scenario import SCENARIOS, build_scenario
from coliseum.textlab.spatial.run import (execute_spatial_run,
                                          inspect_spatial_run,
                                          replay_spatial_run)

__all__ = [
    "SPATIAL_SCHEMA_VERSION", "is_supported_version",
    "PerceptionRegime", "RoomSpec", "PortalSpec", "ObjectSpec", "AgentBodySpec",
    "SpatialWorldSpec",
    "WorldLine",
    "RoomInstance", "PortalInstance", "ObjectInstance", "AgentBodyInstance",
    "assert_same_world_line",
    # S2A mutable state
    "WorldState", "admit_world_state", "validate_location",
    "LocationTransition", "apply_transition", "replay",
    "ForkDecision", "ForkInitialization", "materialize_fork",
    # S2C perception
    "RENDERER_VERSION", "assert_actor_content_schema",
    "closure_visible_state_commitment", "render_observation_pair",
    # S2D scripted runner
    "SCENARIOS", "build_scenario", "execute_spatial_run",
    "inspect_spatial_run", "replay_spatial_run",
]
