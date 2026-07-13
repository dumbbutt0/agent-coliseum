# Spatial World Model — Profile (design source)

Status: **DESIGN PROFILE (implementation-binding). Nothing here is implemented yet.** This document defines
the smallest deterministic **rooms-and-portals** spatial substrate needed for the First Gladiator program to
progress into genuine two-agent experiments (milestone **M11**). It is **not** authorization to build a game
engine, continuous 2D/3D physics, a procedural map generator, combat, an economy, or a full Persistent
Society. It emits the record contracts defined in `TRAINING-READINESS-SUBSTRATE-PROFILE.md`.

## 1. Scope and non-goals

**In scope:** a discrete room-and-portal graph; agent bodies; typed objects; exclusive locations;
deterministic movement; room-scoped local visibility; optional bounded adjacent-room hearing (off by
default); object possession + transfer; portal open/closed(/locked) state; deterministic spatial
transitions; capture + byte-identical replay; matched world-fork isolation; a scripted (non-LLM) two-agent
validation run.

**Explicit non-goals:** continuous coordinates/distance/collision/occlusion/navigation (only introduced if a
later preregistered experiment makes one of them an independent variable), physics, pathfinding beyond
deterministic traversal of explicitly available portals, a game engine, procedural generation, combat, an
economy, weight training, unrestricted live-model experiments, and Persistent-Society Phase-6 activation.
This substrate makes **no** society/persistent-world/embodied claim.

## 2. Core architectural rule — three separated layers
1. **World truth** — the authoritative rooms, portals, locations, objects, bodies, and mutable states.
2. **Perception** — the deterministic subset of world truth available to a particular agent at a particular
   logical step.
3. **Belief / memory** — what an agent thinks/remembers. NOT world truth; it must never overwrite truth.
Agents must **never** receive an implicit global or omniscient view. LLM prompt rendering (when a live model
is later used) consumes the perception **projection**, never the authoritative world state. A hidden
authoritative field must never enter an observation merely because it exists on the state object. This is
the same actor/privileged boundary as the training-readiness profile — the perception renderer *is* the
`project_actor` function for a spatial producer.

## 3. Versioning
A frozen `SPATIAL_SCHEMA_VERSION` (and a `SPATIAL_WORLD_SPEC_VERSION`). Unknown future versions **fail
closed** for new execution; historical replay uses an explicit supported-version dispatcher (mirrors
`DISPATCHABLE_PARSER_VERSIONS`). Renaming/removing/retyping a field bumps the version. The perception regime
carries its own `perception_regime_id` version; a field enters a regime id only when it changes what the
agent can observe (mirrors the interaction-block version-dispatch discipline).

## 4. Identity model
Immutable **specifications** vs world-specific mutable **instances**, all content-addressed via
`schema.canonical_json` + `config_hash`, using the construction-freeze + content-addressed-registry standard
and the **universal self-exclusion + typed-preimage + registry-truth invariant** defined in
`TRAINING-READINESS-SUBSTRATE-PROFILE.md` §3 (each id is `config_hash` of a typed, domain-separated preimage
computed with the output field ABSENT; the protected guarantee is registry truth, not held-object
immutability; `__slots__` alone is not immutability). **The literal `_domain` string and the exhaustive
preimage key set for every id below are bound normatively in Appendix A** — the phrasing here is descriptive;
Appendix A is the binding contract, so two conforming implementations derive identical ids.
- **Spec ids** (definition of a type; self-excluded; exact keys in Appendix A): `spatial_world_spec_id`,
  `room_spec_id`, `portal_spec_id`, `object_spec_id`, `agent_body_spec_id`, `perception_regime_id` (the last
  excludes world-truth-only fields, mirroring `agent_regime_id`).
- **Instance ids** (self-excluded; each preimage is `{_domain, spatial_schema_version, <kind>_spec_id,
  world_line_id, deterministic_logical_instance_key}` per Appendix A): `room_instance_id`,
  `portal_instance_id`, `object_instance_id`, `agent_body_id`. The `deterministic_logical_instance_key` is a
  frozen logical index (never wall-clock/PID/UUID/object-identity/mutable-name/run-row).
- Construction order: `spatial_world_spec_id`/room/portal/object/agent_body **spec** ids first (pure content);
  then `world_line_id` (§4.1); then instance ids referencing the spec + world_line. No id is part of its own
  preimage; no id references a not-yet-built id.
- Forbidden in identity: wall-clock, PID, random UUID (without a frozen derivation), object identity,
  mutable display names, run-row identity as world/scenario identity.
- **Cross-world instance references fail closed** (an instance whose `world_line_id` differs from the
  referencing context is refused).

### 4.1 World-line / fork identity (new, parallel to `control_of`)
`world_line_id`/`fork_id` are a **new** lineage dimension, distinct from the existing `control_of` twin
lineage — which is **not redefined**. Sibling control/intervention forks may share an immutable spatial
spec and a partition group, but differ in `fork_id`/`world_line_id` and in **every** mutable instance id. No
state, object instance, body instance, observation, or memory may cross between siblings. Fork lineage
integrates via an **additive** `lineage_edges` input to the group-aware partition (default empty → existing
callers byte-identical) and a **separate** `counterfactual_delta` metrics join — never by mutating
`control_of` or `control_twin_delta`.

Typed preimages + acyclic construction order (shared with `TRAINING-READINESS-SUBSTRATE-PROFILE.md` §4.7;
exact keys in Appendix A): a **root** world-line is `config_hash({_domain: "spatial.world_line.v1",
spatial_schema_version, spatial_world_spec_id, initial_state_key})` (no parent). A **forked child**
world-line is `config_hash({_domain: "spatial.world_line.v1", spatial_schema_version, parent_world_line_id,
source_fork_decision_hash, changed_dimension, unchanged_comparison_dims})` — computed BEFORE any fork record;
then `fork_id` references that already-built `branch_world_line_id`. Each is self-excluded from its own
preimage, so `world_line_id`, `fork_id`, and the resulting branch identity form a strict order with no cycle.

## 5. Room and portal graph
- **Room spec** (no mutable state): stable semantic name; room type/tags; permitted portal attachment
  points; capacity (only if experimentally relevant); default visibility policy; default audibility policy.
- **Portal spec:** origin + destination room specs; directed/bidirectional; traversal duration in logical
  steps; supported state capabilities; perception behavior when open/closed.
- **Portal instance state:** open/closed; locked/unlocked; traversable/blocked; optional required
  object/capability.
- No pathfinding beyond deterministic traversal of explicitly available portals.

## 6. Typed object model
Objects are typed entities with explicit affordances — never prose embedded in a prompt.
- **Object spec:** object type; allowed state fields (a closed set — no free-form authoritative dict); allowed
  actions; portability; container capability (if applicable); visibility behavior; whether possession is
  exclusive; whether it can satisfy a portal requirement.
- Initial affordances (implement only what the vertical slice needs; document the rest deferred): `take`,
  `drop`, `give`, `hide`, `reveal`, `open`, `close`, `move`.
- A run payload must not invent new authoritative state fields.

## 7. Exclusive-location model
Every locatable entity has exactly **one** authoritative location, an explicit tagged union:
`InRoom(room_instance_id)` | `HeldBy(agent_body_id)` | `Inside(object_instance_id)` |
`InTransit(portal_instance_id, origin, destination, start_step, arrival_step)`. An entity is never in two
rooms, held by two agents, held-and-independently-in-a-room, inside a cross-world container, or
in-transit-and-interactable. Moving a holder moves held objects' effective location without a second
location record. All location transitions are validated centrally.

## 8. Actions and transitions
Typed actions with explicit preconditions. Minimum vertical-slice actions: move through a portal; take;
drop; give (to a co-located agent); open/close a portal (if supported). Optional only if required:
lock/unlock; hide/reveal; place-in-container. Every action result distinguishes: applied / refused-invalid /
precondition-failed / unavailable-because-unobserved-or-unreachable / excluded-schema-or-world-mismatch.
**Invalid actions are data** — never silently coerced into valid ones (they become FailureRecords in the
training-readiness layer). The four-layer split (high-level intent / symbolic action / spatial-controller
action / execution result) is preserved so movement failure is not mislabeled as moral/social/planning
failure.

## 9. Deterministic logical time
Logical steps / decision indices, not wall-clock, order everything. Frozen: actor ordering; simultaneous-
action resolution; movement start/arrival; portal-state checks; transfer ordering; tie-breaking; invalid-
action treatment; observation emission point. Same spec + initial state + `world_line_id` + action sequence
+ perception regime + scheduler version ⇒ **byte-identical** authoritative state + trace. Latency is
non-identity metadata.

## 10. Perception renderer
A deterministic function of (authoritative state, observing agent body, perception regime, logical step,
schema + renderer versions). Default visibility for the first slice: an agent sees visible agents + visible
objects in its current room; sees portals attached to its room and only the portal state it may observe;
does not see entities in unrelated rooms; a held object is visible per object + holder rules; hidden objects
are excluded unless a deterministic reveal condition holds; adjacent-room hearing is off by default (or
narrowly versioned). Each observation carries: observer identity; `world_line_id`; logical step; perception
regime; visible room identity; visible entity identities; and the observable state projection. Its
`observation_hash = config_hash({_domain: "trs.observation." + view_kind + ".v1", schema_version,
view_kind, observer_identity, world_line_id, logical_step, perception_regime, visible_room_identity,
visible_entity_identities, observable_state_projection})` (literal domains + exact keys in Appendix A) —
self-excluded from its own preimage (§3/§4), with `view_kind` in the domain so the actor and privileged
artifacts of the same emission can never alias.
Authoritative hidden fields are never included in the actor preimage. The renderer emits the **actor**
`ObservationArtifact` (this projection); a separate **privileged** `ObservationArtifact` carries world truth
under `view_kind = privileged`.

## 11. Belief / memory boundary
This slice does **not** implement persistent beliefs or relationships — it provides a clean interface
boundary so M12 can later record remembered observations, believed locations, confidence/uncertainty,
relationship history, and stale/contradicted beliefs. For now: world truth is authoritative; observations
are immutable evidence; agent-generated beliefs may be logged as agent outputs but never modify truth; no
memory component obtains hidden world fields absent from the agent's observations.

## 12. Spatial trace and replay
Spatial transitions are **experimental evidence**, written to the run-dir stream (`decisions.jsonl`-style,
`t=0.0`) — **never** to the constitutional council event vocabulary (`tools/council/schemas.py`
`EVENT_TYPES`; `tools/council/` is in M11 `forbidden_files`). A minimal versioned spatial trace vocabulary
(adapt to textlab conventions): `SPATIAL_WORLD_INITIALIZED`, `ENTITY_INSTANTIATED`, `ACTION_PROPOSED`,
`ACTION_APPLIED`, `ACTION_REFUSED`, `LOCATION_CHANGED`, `PORTAL_STATE_CHANGED`, `OBJECT_STATE_CHANGED`,
`OBSERVATION_EMITTED`, `SPATIAL_WORLD_COMPLETED`. Each record binds: trace + spatial schema versions;
`world_line_id`; scenario + experiment identity; logical step; actor (if applicable); pre-state hash; action
hash; post-state hash; observation hash (if applicable); and a deterministic ordering key. Replay verifies
manifest identity, schema versions, initial-state hash, world-line, ordered action sequence, every
pre/post-state hash, observation hashes, final-state hash, and byte-identical canonical trace output; it
refuses missing/reordered/unknown-version/cross-world/hash-drift/mutable-overwrite/duplicate-id-different-
bytes. Preserves the project's immutable-evidence + collision-refusal rules.

## 13. Matched world forks
For control/intervention siblings the immutable spatial spec may be identical and the partition group is
shared where required, but `fork_id`/`world_line_id` and every mutable instance id differ; nothing crosses
between siblings; matched-environment validation identifies exactly which preregistered mechanism differs;
alternate renderings and retries never route across dataset partitions. An **independent leakage lint**
re-derives these relationships rather than trusting run-declared grouping fields.

## 14. Minimal scripted two-agent vertical slice
After the substrate and its records exist and the roadmap gate permits: 2 rooms (Antechamber, Arena); one
door (closed, openable); Agent A in the Antechamber, Agent B in the Arena; one portable token/key + one
private-information object (e.g. a sealed instruction). Trajectory: separated → A observes an object B
cannot → A takes/leaves it → an agent opens the portal → an agent changes rooms → co-located → an object is
transferred/dropped/hidden/discovered → observations differ correctly before meeting and update correctly
after → the complete trajectory reconstructs byte-identically. This measures **substrate correctness only**.
**Scripted (non-LLM) agents first** — a scripted run needs no owner token. No live-model (Ollama) pilot
until: the scripted slice is integrated; replay is byte-identical; perception-leakage tests pass; the
scenario + experiment are registered; the roadmap permits a live run; and the required audit verdict is
integrated.

## 15. Scientific and claim boundaries
This slice may establish only: deterministic spatial execution; correct room separation; typed-object
interaction; per-agent observation isolation; world-fork isolation; replayable two-agent trajectories. It
may **not** establish emergent social behavior, persistent relationships, moral agency, deception detection,
loyalty, long-term memory, society validity, human-like spatial reasoning, or training effectiveness — each
needs later preregistered experiments + the active Class-C scientific acceptance procedure. The dashboard
and roadmap must report the actual milestone state and must never claim the Living Coliseum is complete.

## 16. Milestone & authorization boundaries
- M8 stays focused on reflex/time-pressure measurement validation; M9 defines how personas interact with
  perception/spatial context; M10 tests generalization across room arrangements; **M11** introduces the
  minimal room graph + the first two-agent execution; M12 adds persistent locations/possessions/memories/
  relationships.
- **Authorization:** inert design/schema/code proceeds now inside `coliseum/textlab/` (M11 `allowed_files`;
  `tools/council/` forbidden). A **scripted** two-agent run needs no owner token. A **live persistent /
  embodied society** run requires the owner **SC-LC** gate **and** prior `G-SOCIETY-PROFILE` design-source
  routing, and must make no society claim without it. Roadmap YAML / M11-completion marking is Class-D
  (owner). Weight training is M14/SC-8.

## 17. Protected boundaries
Do not modify for spatial convenience: council identity / cryptographic role binding; the constitutional
event vocabulary; policy pin / amendment semantics; owner authentication; chain-head anchors; audit-verdict
authority; hidden-evaluation controls; frozen METRICS-v1; weight-training restrictions; or existing
world-line/fork/`control_of` identity semantics (without an independently audited migration). A genuine
defect found in one of these is preserved as a fixture, classified under v4, and routed through the proper
governance path — never smuggled into a spatial source slice.

## 18. Deferred / gated capabilities (explicitly labeled)
- **Deferred (designed, not built):** continuous coordinates/physics/navigation; containers; lock/unlock,
  hide/reveal beyond the vertical slice; adjacent-room hearing; persistent belief/memory (M12);
  `LabelRecord` normative labels (T0-B).
- **Gated:** a live-model spatial run and any persistent/embodied society dynamics (owner SC-LC +
  G-SOCIETY-PROFILE); weight-level behavioral training (M14/SC-8).
- **Built + verified:** nothing yet — this is a design profile.

## Appendix A — Normative spatial identity-derivation table (binding)
Same rule as `TRAINING-READINESS-SUBSTRATE-PROFILE.md` Appendix A: `id = config_hash(canonical_json({_domain:
<literal>, <exact keys>}))` with the output id field **absent** (self-exclusion), the literal `_domain`
mandatory, referenced ids pre-existing (construction order §4). A conforming implementation MUST derive the
same id from the same content. `spatial_schema_version` is the frozen `SPATIAL_SCHEMA_VERSION`.

| id | literal `_domain` | preimage keys (besides `_domain`; id self-excluded) |
| --- | --- | --- |
| `spatial_world_spec_id` | `spatial.world_spec.v1` | `spatial_schema_version`, `room_spec_ids` (sorted), `portal_spec_ids` (sorted), `object_spec_ids` (sorted), `agent_body_spec_ids` (sorted), `perception_regime_id`, `initial_layout` |
| `room_spec_id` | `spatial.room_spec.v1` | `spatial_schema_version`, `semantic_name`, `room_type_tags` (sorted), `permitted_portal_attachment_points` (sorted), `capacity` (or `null`), `default_visibility_policy`, `default_audibility_policy` |
| `portal_spec_id` | `spatial.portal_spec.v1` | `spatial_schema_version`, `origin_room_spec_id`, `destination_room_spec_id`, `directionality`, `traversal_duration_steps`, `supported_state_capabilities` (sorted), `perception_behavior` |
| `object_spec_id` | `spatial.object_spec.v1` | `spatial_schema_version`, `object_type`, `allowed_state_fields` (sorted), `allowed_actions` (sorted), `portability`, `container_capability`, `visibility_behavior`, `exclusive_possession`, `satisfies_portal_requirement` |
| `agent_body_spec_id` | `spatial.agent_body_spec.v1` | `spatial_schema_version`, `agent_body_type`, `default_perception_regime_id`, `inventory_limit` (or `null`) |
| `perception_regime_id` | `spatial.perception_regime.v1` | `spatial_schema_version`, `renderer_version`, `visibility_policy`, `audibility_policy`, `observation_policy_version` (world-truth-only fields are excluded) |
| `room_instance_id` | `spatial.room_instance.v1` | `spatial_schema_version`, `room_spec_id`, `world_line_id`, `deterministic_logical_instance_key` |
| `portal_instance_id` | `spatial.portal_instance.v1` | `spatial_schema_version`, `portal_spec_id`, `world_line_id`, `deterministic_logical_instance_key` |
| `object_instance_id` | `spatial.object_instance.v1` | `spatial_schema_version`, `object_spec_id`, `world_line_id`, `deterministic_logical_instance_key` |
| `agent_body_id` | `spatial.agent_body_instance.v1` | `spatial_schema_version`, `agent_body_spec_id`, `world_line_id`, `deterministic_logical_instance_key` |
| `world_line_id` (root) | `spatial.world_line.v1` | `spatial_schema_version`, `spatial_world_spec_id`, `initial_state_key` |
| `world_line_id` (forked) | `spatial.world_line.v1` | `spatial_schema_version`, `parent_world_line_id`, `source_fork_decision_hash`, `changed_dimension`, `unchanged_comparison_dims` |
| `observation_hash` (per view) | `trs.observation.actor.v1` / `trs.observation.privileged.v1` | `schema_version`, `view_kind`, `observer_identity`, `world_line_id`, `logical_step`, `perception_regime`, `visible_room_identity`, `visible_entity_identities`, `observable_state_projection` |

The spatial trace record ids (`SPATIAL_WORLD_INITIALIZED` … `SPATIAL_WORLD_COMPLETED`, §12) bind the fields
listed in §12 under the literal `_domain` `spatial.trace.<event_name>.v1`, self-excluded, with pre/post-state
and action/observation hashes referenced (not recomputed).
