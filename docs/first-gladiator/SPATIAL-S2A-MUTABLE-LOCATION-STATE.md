# Spatial S2A — Mutable exclusive-location state (design source)

**Status:** design source for council review. No production code in this document. Builds on the
integrated spatial identity layers S0 (specs) and S1 (world-lines + instances), which remain
**immutable and untouched**. Slice of the owner-directed three-part perception track
(S2A location state → S2B deterministic scheduler → S2C perception non-interference).

## 1. Purpose and boundary
S2A adds the **mutable world state** — *where every entity is* — as an explicit, replayable
**event layer** over the immutable identity records. It introduces no simulation loop, no scheduler
(S2B), no perception/observation (S2C), no labels/training/weights. It is deterministic and
content-addressed throughout.

**Inviolable:** mutable state is **never** represented by mutating a registered identity record
(spec or instance). Identity records stay frozen; state lives in separate content-addressed
`WorldState` snapshots produced by folding ordered `LocationTransition` events.

## 2. Location — an exclusive tagged union (profile §7)
An entity's location is **exactly one** of:
- `InRoom(room_instance_id)`
- `HeldBy(agent_body_id)`
- `Inside(object_instance_id)`
- `InTransit(portal_instance_id, origin_room_instance_id, destination_room_instance_id, start_step, arrival_step)`

Every referenced instance id must be **registered** and belong to the **same `world_line_id`** as the
state (cross-world reference fails closed, reusing S1 `assert_same_world_line`). An entity is never in
two locations; the location value is canonical (a tagged dict with a fixed key set per tag).

## 3. Records and identities (Appendix-A style; self-excluded, domain-separated)
All ids are `config_hash` of a typed preimage with the id field ABSENT, reusing the integrated
`_content_record` standard and the S0 single-snapshot registry discipline.

| record | literal `_domain` | preimage keys (id self-excluded) |
| --- | --- | --- |
| `WorldState` | `spatial.world_state.v1` | `spatial_schema_version`, `world_line_id`, `logical_step`, `placements` (sorted list of `{entity_id, entity_kind, location}`), `body_lifecycle` (sorted list of `{agent_body_id, status}`) |
| `LocationTransition` | `spatial.location_transition.v1` | `spatial_schema_version`, `world_line_id`, `logical_step`, `prior_state_hash`, `resulting_state_hash`, `actor_body_id` (or `null` for an environment/system transition), `canonical_action`, `effect` (the canonical placement/lifecycle delta) |
| `InitialWorldState` | (a `WorldState` at `logical_step = 0`) | — the fold's base; a fork's base is the authorized parent snapshot (§6) |

- `entity_kind ∈ {agent_body, object}`. `status ∈ {active, absent, removed}` — a **removed** body holds
  no location; an **absent** body (temporarily out of play) holds no location; an **active** body holds
  exactly one location.
- `canonical_action` is drawn from a closed S2A action set: `move` (through a portal),
  `take`/`drop`/`give` (change `HeldBy`/`Inside`/`InRoom`), `enter`/`exit` (container),
  `advance_transit` (progress/complete an `InTransit`), plus `spawn`/`despawn` lifecycle actions. Portal
  and object *internal* mutable attributes (open/closed, locked) are a **documented follow-on** (S2A′ or
  folded into S2C world-truth), NOT in S2A — S2A is placement + lifecycle only.

## 4. The pure transition function
`apply_transition(state: WorldState, transition: LocationTransition) -> WorldState` is pure and
deterministic. It **fails closed** unless ALL hold:
1. `transition.world_line_id == state.world_line_id` (no cross-world contamination).
2. `transition.prior_state_hash == state.id` (**stale-transition** rejection — a transition computed
   against a different/older state is refused).
3. `transition.logical_step == state.logical_step + 1` (monotonic, gap-free).
4. every instance id referenced by the effect is registered and in this world-line (nonexistent-room /
   cross-world rejection).
5. the effect is **legal** for the actor + current location + canonical_action (e.g. `move` requires an
   available portal from the body's current room; `take` requires the object co-located and, if
   `exclusive_possession`, not already held; `give` requires giver holding it and recipient co-located).
6. **exclusivity**: applying the effect leaves every `active` body in exactly one location, respects
   room `capacity`, and never assigns two holders to an `exclusive_possession` object
   (**duplicate-occupancy** rejection).
7. **no illegal resurrection**: a `removed` body may not be re-placed or re-activated.
8. the recomputed post-state's id `== transition.resulting_state_hash` (**transplant/forgery**
   rejection — the caller cannot claim a resulting state that does not follow from prior+effect).

On success it returns the new `WorldState` (step + 1). The transition record is thus a verifiable edge:
`prior_state_hash --(actor, action, effect)--> resulting_state_hash`.

## 5. Replay (determinism)
`replay(initial_state, [t0, t1, …]) -> WorldState` folds `apply_transition`. **Guarantee:** the same
`initial_state` + the same ordered transition list reconstruct **byte-identical** state bytes (identical
`WorldState.id` at every step and at the end). No wall-clock/PID/UUID/object-identity/dict-iteration
influence: placements and lifecycle are stored as **sorted** canonical lists, so state identity is
independent of insertion order.

## 6. Fork semantics (parallel to control_of; never redefined)
A forked `world_line_id` (S1) begins from an **authorized parent snapshot**: the fork's
`InitialWorldState` is the parent `WorldState` at the exact fork step, **re-domained to the child
`world_line_id`** (every placement/lifecycle entry keeps its logical content but the state binds the
child world-line). Thereafter:
- the child's transitions bind the child `world_line_id`; applying a child transition to a parent state
  (or vice-versa) fails at check §4.1 — **no parent/sibling contamination**.
- sibling forks that share actor-visible content still differ in `world_line_id` and therefore in every
  `WorldState.id` and instance id; nothing crosses.
- a fork may only inherit a parent state the caller is authorized to branch from (the fork records the
  parent `world_line_id` + parent state hash it descends from; an unregistered/foreign parent state is
  refused).

## 7. Non-goals / deferred (explicit)
No scheduler or turn order (S2B). No perception/observation/visibility (S2C). No portal/object internal
attribute state (open/closed/locked) — documented follow-on. No pathfinding beyond one-portal `move`.
No labels/training/weights/T0-B/M14-SC-8/society surfaces. No `tools/council` changes (the spatial state
lives in `coliseum/textlab/spatial/`, never as council `EVENT_TYPES`).

## 8. Threat model (the S2A adversarial test set)
cross-world transition (world_line mismatch) refused; nonexistent room/portal/object refused; stale
transition (wrong `prior_state_hash`) refused; non-monotonic/gapped `logical_step` refused; duplicate
occupancy / capacity overflow / double-hold of an exclusive object refused; illegal resurrection of a
`removed` body refused; **transplanted** `resulting_state_hash` (claiming a state that does not follow)
refused; registry TOCTOU on the new records refused (reuse S0 single-snapshot admission); fork isolation
(child transition cannot mutate parent/sibling state; sibling `WorldState.id`s differ); replay
determinism (same initial + ordered transitions → identical bytes, order-independent internal storage);
lifecycle exclusivity (an `active` body has exactly one location, a `removed`/`absent` body none).

## 9. Compatibility
Additive only. New files under `coliseum/textlab/spatial/`. No existing module, primary evidence, or
`tools/council` change; `control_of`/`control_twin_delta` untouched; frozen `SPATIAL_SCHEMA_VERSION`
reused (a new record schema version bumps only if a preimage field changes). Historical evidence and
schema dispatch preserved.
