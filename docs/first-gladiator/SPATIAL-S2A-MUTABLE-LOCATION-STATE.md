# Spatial S2A — Mutable exclusive-location state (design source, rev 4)

**Status:** design source for council review. No production code. Builds on the **immutable, untouched**
integrated identity layers S0 (specs) and S1 (world-lines + instances). Rev 4 closes audit 000999:
canonical in-transit fork semantics (the child inherits the parent's logical clock, preserving remaining
travel time) + a general admission invariant relating `logical_step` to transit bounds. (Rev 3 closed
audit 000993: unified entity lifecycle, actor rules, `ForkDecision` authorization, transit step semantics
+ `env_tick`. Rev 2 closed audit 000987: fork materialization, provenance, canonical shapes.)

## 1. Purpose and boundary
S2A adds the **mutable world state** (*where every entity is*) as an explicit, replayable **event layer**
over the immutable identity records. No scheduler (S2B), no perception (S2C), no labels/training/weights,
no `tools/council` change. Deterministic and content-addressed. Mutable state is **never** a mutation of a
registered identity record; it lives in content-addressed `WorldState` snapshots folded from ordered
`LocationTransition` events.

## 2. Location — an exclusive tagged union with EXACT key sets
One canonical tagged dict, exactly one of (no extra/missing keys):
- `{"tag": "in_room", "room_instance_id": <id>}`
- `{"tag": "held_by", "agent_body_id": <id>}`
- `{"tag": "inside", "object_instance_id": <id>}`
- `{"tag": "in_transit", "portal_instance_id": <id>, "origin_room_instance_id": <id>, "destination_room_instance_id": <id>, "start_step": <int≥0>, "arrival_step": <int>}`, `arrival_step > start_step`.

**Entity-kind legality:** `agent_body` → `in_room`|`in_transit`; `object` → `in_room`|`held_by`|`inside`.
Every instance id in a location must be **registered** and in the state's own `world_line_id`.

## 3. Records and identities (self-excluded, domain-separated; reuse `_content_record` + S0 registry)

| record | literal `_domain` | preimage keys (id self-excluded) |
| --- | --- | --- |
| `WorldState` | `spatial.world_state.v1` | `spatial_schema_version`, `world_line_id`, `logical_step`, `placements`, `entity_lifecycle` |
| `LocationTransition` | `spatial.location_transition.v1` | `spatial_schema_version`, `world_line_id`, `logical_step`, `prior_state_hash`, `resulting_state_hash`, `actor_body_id`(or `null`), `effect` |
| `ForkDecision` | `spatial.fork_decision.v1` | `spatial_schema_version`, `parent_world_line_id`, `parent_state_hash`, `fork_logical_step`, `changed_dimension`, `unchanged_comparison_dims` |
| `ForkInitialization` | `spatial.fork_initialization.v1` | `spatial_schema_version`, `child_world_line_id`, `parent_world_line_id`, `parent_state_hash`, `fork_logical_step`, `source_fork_decision_hash`, `materialized_child_initial_state_hash` |

- `placements`: list **sorted by `entity_id`**, entries `{"entity_id": <instance id>, "entity_kind": "agent_body"|"object", "location": <tagged dict §2>}`; `entity_id`s unique.
- `entity_lifecycle`: list **sorted by `entity_id`**, entries `{"entity_id": <instance id>, "entity_kind": "agent_body"|"object", "status": "present"|"absent"|"removed"}`; `entity_id`s unique. **Unified for bodies AND objects.** `present` ⇒ exactly one `placements` row; `absent`/`removed` ⇒ no `placements` row. `removed` is **terminal** for every entity kind.
- `logical_step`: non-negative int. A **root** world-line's base is at `logical_step = 0`; a **fork's**
  base is at `logical_step = fork_logical_step` (the child inherits the parent's logical clock at the fork
  point — §8 — so an inherited in-progress transit keeps its exact remaining travel time).
- `ForkDecision.id` is exactly the `source_fork_decision_hash` an S1 `WorldLine.forked(...)` was built with (its `parent_world_line_id`/`changed_dimension`/`unchanged_comparison_dims` equal S1's; it ADDS the `parent_state_hash` + `fork_logical_step` authorization S1 does not carry — S1 unchanged).

## 4. Canonical action / effect matrix + actor rules (implementation-binding)
`effect = {"action": <name>, …}`. **Step convention:** a transition applied to a state at
`logical_step = N` yields `logical_step = N+1`; effect guards read the **prior** state (step N), locations
that record a step use the **resulting** step (N+1).

| action | actor | effect keys (besides `action`) | pre (on prior state N) | post (resulting state N+1) |
| --- | --- | --- | --- | --- |
| `spawn` | system (`null`) | `entity_id`,`entity_kind`,`location` | entity not `present`/`absent`/`removed` OR `absent` (never `removed`); location legal+in-world | entity `present` at `location` |
| `despawn` | system | `entity_id`,`entity_kind` | entity `present` | entity `absent`, no placement |
| `remove` | system | `entity_id`,`entity_kind` | entity `present`/`absent`, not `removed` | entity `removed` (terminal), no placement |
| `env_tick` | system | *(none)* | — | placements/lifecycle unchanged; only `logical_step` advances |
| `move` | actor=`agent_body_id` | `agent_body_id`,`portal_instance_id`,`from_room_instance_id`,`to_room_instance_id` | body `present`,`InRoom(from)`; registered portal connects from→to in-world | `InRoom(to)` if `traversal_duration_steps==0`, else `InTransit(portal,from,to,start=N+1,arrival=N+1+duration)` |
| `complete_transit` | system | `agent_body_id` | body `InTransit(…,arrival)` and `N+1 == arrival_step` | body `InRoom(destination)` |
| `take` | actor=`agent_body_id` | `agent_body_id`,`object_instance_id` | body `InRoom(r)`; object `present`,`InRoom(r)`,`portability`; if `exclusive_possession`, not `held_by` anyone | object `HeldBy(body)` |
| `drop` | actor=`agent_body_id` | `agent_body_id`,`object_instance_id` | object `HeldBy(body)`; body `InRoom(r)` | object `InRoom(r)` |
| `give` | actor=`agent_body_id` | `agent_body_id`,`object_instance_id`,`recipient_agent_body_id` | object `HeldBy(body)`; recipient `present`,`InRoom(r)`=body's room | object `HeldBy(recipient)` |
| `put_inside` | actor=`agent_body_id` | `agent_body_id`,`object_instance_id`,`container_object_instance_id` | object `HeldBy(body)`; container `container_capability`, `InRoom(body's room)`/`HeldBy(body)`; object≠container, container not transitively `Inside` object | object `Inside(container)` |
| `take_out` | actor=`agent_body_id` | `agent_body_id`,`object_instance_id`,`container_object_instance_id` | object `Inside(container)`; container `InRoom(body's room)`/`HeldBy(body)` | object `HeldBy(body)` |

**Actor rules (validated in §6):** a **system** action requires `actor_body_id == null`. An **actor**
action requires `actor_body_id` = a registered, in-world `AgentBodyInstance` with lifecycle `present`, and
`actor_body_id == effect.agent_body_id` (the acting body). Any other combination fails closed.
**Lifecycle matrix (all entities):** `absent↔present` (spawn/despawn); `present|absent → removed`
(remove, **terminal**); `removed → *` refused (**resurrection** — bodies and objects alike; a `remove`d
object cannot be `spawn`ed).
**Capacity:** per room, count of **agent bodies** `InRoom` ≤ `RoomSpec.capacity` (when non-null); objects
don't consume capacity. **Containment:** `Inside` is acyclic (re-checked each take/give/put_inside/take_out).
**Transit:** `start_step < arrival_step`; distinct in-world endpoints the portal connects; a body crosses a
duration-`d` portal via `move` (→`InTransit`, step `N+1`), then `d-1` `env_tick`s, then `complete_transit`
at step `arrival_step` (total `d` steps). `d==0` lands directly `InRoom(dest)`.

## 5. State admission validator (single-snapshot, runs BEFORE any fold)
`admit_world_state(state)` fails closed unless: schema supported; `world_line_id` registered;
`logical_step ≥ 0`; `placements` and `entity_lifecycle` sorted by `entity_id` with unique ids; every
`entity_id` and nested location id **registered, type-correct, in this world-line**; entity-kind location
legality + exact tag key sets; **lifecycle/placement agreement** (`present` ⇒ exactly one placement;
`absent`/`removed` ⇒ none; every placed entity has a `present` lifecycle row); exclusivity (no shared
exclusive slot; `exclusive_possession` `held_by` ≤ 1; room capacity; containment acyclic); transit
validity — distinct in-world endpoints the portal connects, `start_step < arrival_step`, **and the body is
genuinely mid-transit at this state: `start_step ≤ logical_step < arrival_step`** (a state whose
`logical_step` is before an `in_transit` body's `start_step` or at/after its `arrival_step` is malformed
and refused — this holds for every admitted state, fork-materialized or not). Single-snapshot atomic
(reuse S0 discipline): the validated content is exactly the admitted content.

## 6. The pure transition function
`apply_transition(state, transition) -> WorldState` fails closed unless ALL:
1. `transition.world_line_id == state.world_line_id`.
2. `transition.prior_state_hash == state.id` (**stale** rejection).
3. `transition.logical_step == state.logical_step + 1` (monotonic, gap-free).
4. **actor rule (§4)**: a non-null `actor_body_id` is a registered in-world `AgentBodyInstance`, lifecycle
   `present`, and `== effect.agent_body_id`; a system action requires `actor_body_id == null`.
5. every instance id in `effect` is registered + type-correct + in this world-line.
6. the `effect` satisfies its §4 **pre** on `state` (legal application incl. resurrection refusal).
7. the recomputed post-state (apply §4 **post**, re-sort, re-`admit_world_state`) has id `==
   transition.resulting_state_hash` (**transplant** rejection).
Success returns the new `WorldState` (step+1): a verifiable edge
`prior_state_hash --(actor, effect)--> resulting_state_hash`.

## 7. Replay (determinism)
`replay(initial_state, [t0,…])` folds `apply_transition` after `admit_world_state(initial_state)`. Same
admitted initial + same ordered transitions ⇒ **byte-identical** state at every step (sorted canonical
lists ⇒ order/dict/host/thread/filesystem independence).

## 8. Fork — deterministic materialization + authorized-parent provenance
Given a parent `WorldState` S_p in world-line P, a **registered** S1 forked `WorldLine` C
(`parent_world_line_id==P`), and a **registered** `ForkDecision` D with `D.id ==` C's
`source_fork_decision_hash`:

1. **Authorization (distinct from structure):** require `D.parent_world_line_id == P`,
   `D.parent_state_hash == S_p.id`, and `D.fork_logical_step == S_p.logical_step`. The fork DECISION thus
   authorizes exactly one parent snapshot + step; any other admitted historical snapshot of P has a
   different hash/step and fails this bind.
2. **Remap** (total, type-preserving bijection over **every** instance id the state references — as an
   `entity_id` in `placements`, an `entity_id` in `entity_lifecycle`, OR nested inside any location): recover
   `(domain, spec_id, deterministic_logical_instance_key)` and re-derive `e' = instance(spec_id, C, key)`;
   **register** each `e'` under C. Refuse unregistered/foreign/mistyped/non-bijective mappings.
3. **Rewrite** S_p → child initial state S_c: `world_line_id=C`, **`logical_step = S_p.logical_step`**
   (the child inherits the parent's logical clock at the fork point — NOT reset to 0 — so an inherited
   `in_transit` body keeps its absolute `start_step`/`arrival_step` and therefore its exact remaining
   travel time), every `placements` `entity_id`, every `entity_lifecycle` `entity_id`, and every nested
   location id replaced by its `e'`; content otherwise preserved. S_c MUST pass `admit_world_state` (§5)
   with all child-world ids — in particular the transit invariant `start_step ≤ logical_step < arrival_step`,
   which refuses any step-reset/mis-rebased in-transit inheritance. The child's own transitions then continue
   from `logical_step = S_p.logical_step + 1`.
4. **Provenance:** emit `ForkInitialization` binding `child_world_line_id=C`, `parent_world_line_id=P`,
   `parent_state_hash=S_p.id`, `fork_logical_step=S_p.logical_step`, `source_fork_decision_hash=D.id`,
   `materialized_child_initial_state_hash=S_c.id`. **Anti-transplant:** `materialized_child_initial_state_hash`
   must equal the id recomputed by re-running steps 2–3 on the state named by `parent_state_hash`.

**Isolation:** child transitions bind C; a child transition applied to a parent state (or vice-versa)
fails §6.1. Siblings sharing actor-visible content differ in `world_line_id` ⇒ every `WorldState.id` +
instance id differs; nothing crosses. `control_of`/`control_twin_delta` untouched; `world_line_id`/`fork_id`
remain the separate lineage dimension.

## 9. Non-goals / deferred
No scheduler/turn order (S2B). No perception/observation (S2C). No portal/object *internal* attribute
state (open/closed/locked) — documented follow-on. No pathfinding beyond one-portal `move`. No
labels/training/weights/T0-B/M14-SC-8/society. No `tools/council` changes.

## 10. Threat model + required identity vectors
**Identity vectors (byte-pinned):** every location tag; every §4 action/effect shape (incl. `env_tick`);
a `WorldState`; a `LocationTransition`; a `ForkDecision`; a `ForkInitialization`.
**Adversarial (each fails closed):** admission — duplicate `entity_id`/lifecycle rows, nonexistent/wrong-kind
ids, cross-world nested refs, kind-illegal location, capacity overflow, exclusive double-hold, containment
cycle, invalid transit endpoints/timing, lifecycle/placement disagreement; transitions — cross-world,
stale `prior_state_hash`, gapped/non-monotonic step, actor violations (null-when-required,
non-null-when-system, nonexistent/wrong-kind/foreign/inactive actor, actor≠effect body), illegal `effect`
pre, resurrection of a `removed` body OR object, transplanted `resulting_state_hash`; registry TOCTOU
(reuse S0 single-snapshot); fork — raw or partially-remapped snapshot (incl. an un-remapped
`entity_lifecycle` id) refused, fully-remapped child admits, **unauthorized** parent (a different admitted
historical snapshot of P whose hash/step do not match D) refused, foreign/stale/unregistered parent
refused, two siblings distinct with no contamination; transit — byte-pin duration 0/1/>1 move+completion
traces incl. early/late completion refusal, an admitted state with an `in_transit` body whose
`logical_step < start_step` or `≥ arrival_step` refused, and **forking a mid-transit parent** (child
inherits `logical_step = fork_logical_step` with remaining travel preserved and admits; a step-reset
variant refused by the transit invariant); replay — identical bytes, order-independent storage.

## 11. Compatibility
Additive only; new files under `coliseum/textlab/spatial/`. No existing module / primary evidence /
`tools/council` change; `control_of` untouched; frozen `SPATIAL_SCHEMA_VERSION` reused. Historical
evidence + schema dispatch preserved.
