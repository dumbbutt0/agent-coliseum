# Spatial S2A — Mutable exclusive-location state (design source, rev 2)

**Status:** design source for council review. No production code. Builds on the **immutable, untouched**
integrated identity layers S0 (specs) and S1 (world-lines + instances). Rev 2 closes the three HIGH gaps
from audit 000987: (a) a deterministic fork-materialization algorithm reconciled with S1 world-line-bound
instance identity; (b) explicit authorized-parent-snapshot provenance in a new content-addressed record;
(c) normative canonical location/effect shapes + a single-snapshot state admission validator so transition
identity, legal application, and byte-identical replay are implementation-binding.

## 1. Purpose and boundary
S2A adds the **mutable world state** (*where every entity is*) as an explicit, replayable **event layer**
over the immutable identity records. No scheduler (S2B), no perception/observation (S2C), no
labels/training/weights, no `tools/council` change. Deterministic and content-addressed throughout.
Mutable state is **never** a mutation of a registered identity record; it lives in separate
content-addressed `WorldState` snapshots produced by folding ordered `LocationTransition` events.

## 2. Location — an exclusive tagged union with EXACT key sets
A location value is one canonical tagged dict, exactly one of (no extra/missing keys):
- `{"tag": "in_room", "room_instance_id": <id>}`
- `{"tag": "held_by", "agent_body_id": <id>}`
- `{"tag": "inside", "object_instance_id": <id>}`
- `{"tag": "in_transit", "portal_instance_id": <id>, "origin_room_instance_id": <id>, "destination_room_instance_id": <id>, "start_step": <int≥0>, "arrival_step": <int>}` with `arrival_step > start_step`.

**Entity-kind location legality** (fail closed otherwise):
- `agent_body`: `in_room` or `in_transit` only.
- `object`: `in_room`, `held_by`, or `inside` only.

Every instance id inside a location must be **registered** and in the state's **own `world_line_id`**
(cross-world nested reference fails closed, reusing S1 `assert_same_world_line`).

## 3. Records and identities (self-excluded, domain-separated; reuse `_content_record` + S0 registry)

| record | literal `_domain` | preimage keys (id self-excluded) |
| --- | --- | --- |
| `WorldState` | `spatial.world_state.v1` | `spatial_schema_version`, `world_line_id`, `logical_step`, `placements`, `body_lifecycle` |
| `LocationTransition` | `spatial.location_transition.v1` | `spatial_schema_version`, `world_line_id`, `logical_step`, `prior_state_hash`, `resulting_state_hash`, `actor_body_id`(or `null`), `effect` |
| `ForkInitialization` | `spatial.fork_initialization.v1` | `spatial_schema_version`, `child_world_line_id`, `parent_world_line_id`, `parent_state_hash`, `fork_logical_step`, `source_fork_decision_hash`, `materialized_child_initial_state_hash` |

- `placements`: a list **sorted by `entity_id`** of `{"entity_id": <instance id>, "entity_kind": "agent_body"|"object", "location": <tagged dict §2>}`. `entity_id` values are **unique** across the list.
- `body_lifecycle`: a list **sorted by `agent_body_id`** of `{"agent_body_id": <id>, "status": "active"|"absent"|"removed"}`; `agent_body_id` values unique.
- `logical_step`: non-negative int. An `InitialWorldState` is any admitted `WorldState`; a root world-line's base is at `logical_step = 0`; a fork's base is the `ForkInitialization.materialized_child_initial_state_hash` state (§8).
- `effect`: the canonical per-action delta (§4); its exact shape is enumerated so two conforming
  implementations derive identical `LocationTransition` ids.

## 4. Canonical action / effect matrix (implementation-binding)
`effect` is a tagged dict `{"action": <name>, …}` with the exact keys listed. Each action's **pre**
(guard on the current state) and **post** (the resulting placement/lifecycle) are normative.

| action | effect keys (besides `action`) | pre | post |
| --- | --- | --- | --- |
| `spawn` | `entity_id`, `entity_kind`, `location` | entity not in `placements`; if body, lifecycle ∈ {absent, ∅} (never `removed`) | entity in `placements` at `location`; if body, lifecycle→`active` (system/env transition: `actor_body_id=null`) |
| `despawn` | `entity_id`, `entity_kind` | entity active/present, in `placements` | entity removed from `placements`; if body, lifecycle→`absent` |
| `remove` | `entity_id`, `entity_kind` | entity present or absent; if body not already `removed` | entity absent from `placements`; if body, lifecycle→`removed` (terminal) |
| `move` | `agent_body_id`, `portal_instance_id`, `from_room_instance_id`, `to_room_instance_id` | body `active`, `InRoom(from)`; a registered portal instance connects from→to in-world & traversable | body → `InRoom(to)` if portal `traversal_duration_steps==0`, else `InTransit(portal, from, to, start=step, arrival=step+duration)` |
| `complete_transit` | `agent_body_id` | body `InTransit(…, arrival)`; next state step `== arrival_step` | body → `InRoom(destination)` |
| `take` | `agent_body_id`, `object_instance_id` | body `InRoom(r)`; object `InRoom(r)`; object `portability==true`; if `exclusive_possession`, object not currently `held_by` anyone | object → `HeldBy(body)` |
| `drop` | `agent_body_id`, `object_instance_id` | object `HeldBy(body)`; body `InRoom(r)` | object → `InRoom(r)` |
| `give` | `agent_body_id`, `object_instance_id`, `recipient_agent_body_id` | object `HeldBy(body)`; recipient `active`, `InRoom(r)` = body's room | object → `HeldBy(recipient)` |
| `put_inside` | `agent_body_id`, `object_instance_id`, `container_object_instance_id` | object `HeldBy(body)`; container `container_capability==true`, `InRoom(body's room)` or `HeldBy(body)`; object≠container and container not transitively `Inside` object (**acyclic**) | object → `Inside(container)` |
| `take_out` | `agent_body_id`, `object_instance_id`, `container_object_instance_id` | object `Inside(container)`; container `InRoom(body's room)` or `HeldBy(body)` | object → `HeldBy(body)` |

**Lifecycle matrix (bodies):** `absent↔active` (spawn/despawn); `active|absent → removed` (remove,
**terminal**); `removed → *` refused (**resurrection**). Objects are *present* iff in `placements`; a
`remove`d object cannot be re-spawned.
**Capacity:** for each room, the count of **agent bodies** with `InRoom(that room)` ≤ its `RoomSpec.capacity`
(when non-null); objects do not consume room capacity.
**Containment:** the `Inside` relation is a forest (acyclic); every `take/give/put_inside/take_out`
re-checks acyclicity.
**Transit:** `start_step < arrival_step`; origin/destination are distinct in-world rooms the portal connects.

## 5. State admission validator (single-snapshot, runs BEFORE any fold)
`admit_world_state(state)` fails closed unless ALL hold — so malformed/duplicate/cross-world content can
never enter the base state and escape transition-time checks:
1. `spatial_schema_version` supported; `world_line_id` registered; `logical_step ≥ 0`.
2. `placements` sorted by `entity_id`, `entity_id`s unique; `body_lifecycle` sorted, `agent_body_id`s unique.
3. every `entity_id` and every nested location instance id is **registered, type-correct** (kind matches
   domain), and in **this** `world_line_id`.
4. entity-kind location legality (§2); tagged-dict key sets exact.
5. lifecycle/placement agreement: `active` body ⇒ exactly one location in `placements`; `absent`/`removed`
   body ⇒ **not** in `placements`; every placed body has an `active` lifecycle row.
6. exclusivity: no two placements share an exclusive slot; `exclusive_possession` object `held_by` ≤ 1;
   room capacity respected; containment acyclic; transit endpoints/timing valid.
Admission is single-snapshot atomic (reuse S0 discipline): the validated content is exactly the content
whose id is admitted — no re-read of a polymorphic caller.

## 6. The pure transition function
`apply_transition(state, transition) -> WorldState` is pure/deterministic and fails closed unless ALL:
1. `transition.world_line_id == state.world_line_id` (no cross-world contamination).
2. `transition.prior_state_hash == state.id` (**stale-transition** rejection).
3. `transition.logical_step == state.logical_step + 1` (monotonic, gap-free).
4. every instance id in `effect` is registered + type-correct + in this world-line.
5. the `effect` satisfies its §4 **pre** on `state` (legal application: right location, availability,
   portability, exclusivity, capacity headroom, acyclicity, transit timing, lifecycle legality — incl.
   **resurrection** refusal).
6. the recomputed post-state (apply §4 **post**, re-sort, re-admit via §5) has id `==
   transition.resulting_state_hash` (**transplant/forgery** rejection).
Success returns the new `WorldState` (step+1). A transition is thus a verifiable edge
`prior_state_hash --(actor, effect)--> resulting_state_hash`.

## 7. Replay (determinism)
`replay(initial_state, [t0,…]) -> WorldState` folds `apply_transition` after `admit_world_state(initial_state)`.
**Guarantee:** same admitted initial state + same ordered transition list ⇒ **byte-identical** state bytes
at every step (identical `WorldState.id`). Placements/lifecycle are **sorted canonical lists**, so identity
is independent of insertion order / dict iteration / host/thread/filesystem order.

## 8. Fork — deterministic materialization + authorized-parent provenance
Reconciles inheritance with S1 (instance id = `config_hash(spec_id, world_line_id, logical_key)`; a
foreign-world instance id fails closed). Given a parent `WorldState` S_p in world-line P (the exact fork
step) and a **registered** S1 forked `WorldLine` C whose `parent_world_line_id == P`:

1. **Remap** (total, type-preserving bijection): for every instance id `e` referenced by S_p (as an
   `entity_id` OR nested inside any location), recover its `(domain, spec_id, deterministic_logical_instance_key)`
   and re-derive the child id `e' = instance(spec_id, C, logical_key)`; **register** each `e'` under C
   (deterministic re-instantiation). Refuse if any `e` is unregistered/foreign, if the re-derived spec is
   missing, if kinds mismatch, or if the mapping is not bijective (two parents → one child).
2. **Rewrite** S_p → child initial state S_c: `world_line_id=C`, `logical_step=0`, every `entity_id` and
   every nested location instance id replaced by its remapped `e'`; placements/lifecycle content otherwise
   preserved. S_c MUST pass `admit_world_state` (§5) — all child-world ids, exclusivity, capacity,
   acyclicity, transit validity.
3. **Provenance:** emit `ForkInitialization` binding `child_world_line_id=C`, `parent_world_line_id=P`,
   `parent_state_hash = S_p.id`, `fork_logical_step = S_p.logical_step`, `source_fork_decision_hash`
   (matching C's S1 preimage), `materialized_child_initial_state_hash = S_c.id`.
4. **Authorization / anti-transplant:** `materialized_child_initial_state_hash` MUST equal the id
   recomputed by re-running steps 1–2 on the state named by `parent_state_hash`. A child initial state that
   is not the deterministic remap of the stated authorized parent snapshot is refused; a foreign, stale
   (wrong `fork_logical_step`), unregistered, or unauthorized parent is refused.

**Isolation:** child transitions bind C; applying a child transition to a parent state (or vice-versa)
fails §6.1. Siblings sharing actor-visible content still differ in `world_line_id` and therefore in every
`WorldState.id` and instance id — **nothing crosses** between parent/sibling world-lines. `control_of` /
`control_twin_delta` are untouched; `world_line_id`/`fork_id` remain the separate lineage dimension.

## 9. Non-goals / deferred (explicit)
No scheduler/turn order (S2B). No perception/observation/visibility (S2C). No portal/object *internal*
attribute state (open/closed/locked) — documented follow-on. No pathfinding beyond one-portal `move`. No
labels/training/weights/T0-B/M14-SC-8/society surfaces. No `tools/council` changes.

## 10. Threat model + required identity vectors
**Identity vectors (byte-pinned in tests):** every location tag and every §4 action/effect shape; a
`WorldState`; a `LocationTransition`; a `ForkInitialization`.
**Adversarial (each fails closed):** initial-state admission — duplicate `entity_id`/lifecycle rows,
nonexistent or wrong-kind ids, cross-world nested references, entity-kind-illegal location, capacity
overflow, double-hold of an exclusive object, containment cycle, invalid transit endpoints/timing,
lifecycle/placement disagreement; transitions — cross-world (`world_line` mismatch), stale
(`prior_state_hash`), non-monotonic/gapped `logical_step`, illegal `effect` pre (wrong location, missing
portal, non-portable take, over-capacity, acyclicity break), illegal resurrection of a `removed` body,
transplanted `resulting_state_hash`; registry TOCTOU on the new records (reuse S0 single-snapshot);
fork — raw parent-id snapshot refused, fully-remapped child admits with all child-world nested ids,
unauthorized/foreign/stale/transplanted parent refused, two siblings distinct with no parent/sibling
contamination; replay — same initial+ordered transitions ⇒ identical bytes, order-independent internal
storage.

## 11. Compatibility
Additive only; new files under `coliseum/textlab/spatial/`. No existing module / primary evidence /
`tools/council` change; `control_of` untouched; frozen `SPATIAL_SCHEMA_VERSION` reused. Historical
evidence + schema dispatch preserved.
