# Spatial S2B — Deterministic scheduler (design source)

**Status:** design source for council review. No production code. Builds on the integrated S0 (specs),
S1 (world-lines + instances), and S2A (mutable location state: `WorldState`, `admit_world_state`,
`apply_transition`, `advance_step`, `replay`). Slice 2 of the owner-directed perception track. Turn *policy*
was explicitly deferred from S2A to S2B; **action CONTENT** (what a body does) is the agent/experiment's
choice and is NOT decided here — S2B decides only *whose turn it is*, deterministically.

## 1. Purpose and boundary
S2B is the **deterministic turn engine**: a pure function of the authoritative `WorldState` + an explicit
content-addressed scheduler cursor that produces the ordered sequence of **activations** (which body is
invited to act) and **`advance_step` ticks** (clock/arrival resolution), with frozen ordering + explicit
tie-breaking. Logical positions — never wall-clock — are execution identity. No perception (S2C), no labels/
training/weights, no `tools/council` change. Same spec + initial state + `world_line_id` + scheduler version
⇒ **byte-identical** activation sequence, independent of host/thread/filesystem/dict-iteration order.

## 2. Records and identities (self-excluded, domain-separated; reuse `_content_record` + S1 registry discipline)

| record | literal `_domain` | preimage keys (id self-excluded) |
| --- | --- | --- |
| `SchedulerState` | `spatial.scheduler_state.v1` | `spatial_schema_version`, `scheduler_version`, `world_line_id`, `world_state_hash`, `round_index`, `remaining_body_queue` |
| `Activation` | `spatial.activation.v1` | `spatial_schema_version`, `scheduler_version`, `world_line_id`, `world_state_hash`, `logical_step`, `round_index`, `within_round_index`, `agent_body_id`, `legal_action_kinds` |
| `RandomStream` | `spatial.random_stream.v1` | `spatial_schema_version`, `scheduler_version`, `world_line_id`, `logical_step`, `purpose` |
| `RandomDraw` | `spatial.random_draw.v1` | `spatial_schema_version`, `random_stream_id`, `draw_position`, `value` |

- `scheduler_version` is a frozen `SCHEDULER_VERSION` (unknown versions fail closed; a change to any ordering/
  tie-break/eligibility rule bumps it — mirrors the S2A/S1 version dispatch).
- `remaining_body_queue`: the ordered `agent_body_id`s still to act **this round** (see §3). `round_index`,
  `within_round_index`, `logical_step` are non-negative ints.
- `legal_action_kinds`: the sorted set of action kinds legal for the activated body at `world_state_hash`
  (§4) — descriptive context bound into the activation's identity; the body's chosen action is validated by
  S2A `apply_transition`, not here.

## 3. The deterministic turn model (pure over `WorldState` + `SchedulerState`)
A **round** activates every currently-**eligible** body exactly once, in a frozen order, then the clock
advances. Eligibility is deterministic: a body is eligible iff its lifecycle is `present` **and** it is
`InRoom` (an `in_transit`, `absent`, or `removed` body is not activated). The round's queue is the eligible
bodies **sorted by `agent_body_id`** (content-addressed id — a stable, host-independent total order; the
frozen tie-break).

`initial_scheduler_state(world_state)` = `SchedulerState(round_index=0, remaining_body_queue = eligible
bodies of world_state sorted, world_state_hash = world_state.id, …)`.

`next(scheduler_state, world_state, registry)` — pure/deterministic — returns `(step, next_scheduler_state)`
where `step` is either an `Activation` or the sentinel `ADVANCE`, fail-closed unless the cursor is coherent
(§5):
1. **Arrivals first:** if any `present` body is `in_transit` with `arrival_step == world_state.logical_step
   + 1`, the step is **`ADVANCE`** (S2A `advance_step` must resolve the due set); the next cursor is a fresh
   round on the resulting state (queue recomputed). An activation is never scheduled onto a due-arrival step
   (consistent with the S2A due-arrival guard).
2. **Within a round:** else if `remaining_body_queue` is non-empty, the step is an `Activation` for
   `remaining_body_queue[0]` (the head) binding the current `logical_step`, `round_index`, the
   `within_round_index` (= bodies already acted this round), and that body's `legal_action_kinds`; the next
   cursor pops the head. (The caller obtains the body's chosen legal action elsewhere and applies it via S2A
   `apply_transition`, advancing to the next `WorldState`; the next `next()` call re-binds to that state.)
3. **End of round:** else (`remaining_body_queue` empty, no arrival due) the step is **`ADVANCE`** (a clock
   tick / round boundary); the next cursor starts a new round (`round_index+1`, queue recomputed on the
   resulting state).
4. **Quiescence:** if there are no eligible bodies **and** no `in_transit` bodies, the world is QUIESCENT —
   `next()` returns a `QUIESCENT` sentinel and no step (a run may end); it never fabricates a turn.

**Liveness (guaranteed):** every non-quiescent admitted state has a well-defined next step — `ADVANCE` when
arrivals are due, when the round is empty, or when only `in_transit` bodies remain; otherwise the head
activation. There is no reachable admitted non-quiescent state without a legal successor.

## 4. Legal-action context
`legal_action_kinds(body, world_state, registry)` is the sorted subset of the S2A actor action kinds
(`move`, `take`, `drop`, `give`, `put_inside`, `take_out`) whose S2A precondition is satisfiable for `body`
at `world_state` (e.g. `move` iff an available in-world portal leaves the body's room with destination
capacity headroom; `take` iff a co-located portable object exists). It is DERIVED (never authoritative) and
bound into the `Activation` id so a forged legal context yields a different activation id.

## 5. Fail-closed cursor + forgery resistance
`next()` and any consumer of a `SchedulerState`/`Activation` fail closed unless:
- `scheduler_state.world_line_id == world_state.world_line_id` and `scheduler_state.world_state_hash ==
  world_state.id` (**stale / cross-world** cursor refused — a cursor bound to a different or older state).
- `scheduler_state` equals the **canonical** cursor derived by the scheduler for that state (its
  `remaining_body_queue`, `round_index` recomputed and compared) — a **forged ordering / position** cursor
  (e.g. a reordered or truncated queue) is refused.
- an `Activation` presented for application matches the canonical next step exactly: same `world_state_hash`,
  `agent_body_id == remaining_body_queue[0]`, `within_round_index`, `round_index`, `logical_step`, and
  `legal_action_kinds` — this rejects a **duplicate turn** (a body not at the queue head / already acted), a
  **skipped mandatory turn** (activating a non-head body while the head is still due), and a **stale-state
  action** (activation bound to a superseded state).
- `scheduler_version` supported (unknown fails closed).

## 6. Deterministic randomness (specified; the base scheduler needs none)
The base turn engine is fully deterministic (sorted round-robin), so the first slice draws no randomness.
When a policy needs randomness it MUST use a **domain-separated deterministic stream**, never a global RNG:
`RandomStream` id = `config_hash({_domain:"spatial.random_stream.v1", scheduler_version, world_line_id,
logical_step, purpose})`; a `RandomDraw` records `(random_stream_id, draw_position, value)` so every draw is
reproducible and position-addressed. No wall-clock/PID/host entropy enters identity or values. (The first
slice ships the stream/draw primitives + their identity vectors; no scheduler rule consumes them yet.)

## 7. Replay (determinism)
`schedule(initial_world_state, seed=None)` folds `next()` (advancing the S2A state via the caller-supplied
chosen actions in a scripted run) to produce the ordered `[Activation | ADVANCE]` sequence. **Guarantee:**
same spec + admitted initial state + `world_line_id` + `scheduler_version` (+ same scripted action choices)
⇒ **byte-identical** activation sequence and authoritative state, independent of host/thread/filesystem/dict
iteration order (all queues are sorted canonical lists; `SchedulerState`/`Activation` are content-addressed).
Latency/timing is non-identity metadata and never enters any preimage.

## 8. Non-goals / deferred
No perception/observation/visibility (S2C). No action CONTENT / agent policy (the scheduler picks the turn,
not the move). No portal/object internal state (S2A deferral). No labels/training/weights/T0-B/M14-SC-8/
society. No `tools/council` changes. No wall-clock, PID, UUID, object identity, or dict-iteration order in
any identity or ordering decision.

## 9. Threat model + identity vectors
**Identity vectors (byte-pinned):** a `SchedulerState`, an `Activation`, a `RandomStream`, a `RandomDraw`.
**Adversarial (each fails closed):** a cursor whose `world_state_hash`/`world_line_id` mismatches the state
(stale / cross-world); a forged cursor (reordered/truncated/injected `remaining_body_queue`, wrong
`round_index`); a duplicate turn (activating a body not at the queue head / already popped); a skipped
mandatory turn (activating a non-head eligible body); an activation onto a due-arrival step (must be
`ADVANCE`); an activation of an ineligible body (`in_transit`/`absent`/`removed`/cross-world); an unsupported
`scheduler_version`. **Determinism:** identical inputs → identical activation sequence across two independent
runs and across shuffled input orderings; the eligible-queue order is independent of registry/dict iteration.
**Liveness:** every non-quiescent admitted state yields a next step; a fully quiescent state yields
`QUIESCENT`, never a fabricated turn. **Randomness:** two draws at the same `(stream, draw_position)` are
identical; different `purpose`/`logical_step`/`world_line_id` give independent streams.

## 10. Compatibility
Additive only; new files under `coliseum/textlab/spatial/`. No existing module / primary evidence /
`tools/council` change; S0/S1/S2A records + `control_of` untouched; frozen `SPATIAL_SCHEMA_VERSION` reused +
a new frozen `SCHEDULER_VERSION`. Historical evidence + schema dispatch preserved.
