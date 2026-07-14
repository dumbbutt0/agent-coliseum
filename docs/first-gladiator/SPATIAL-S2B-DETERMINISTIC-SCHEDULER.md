# Spatial S2B — Deterministic scheduler (design source, rev 4)

**Status:** design source for council review. No production code. Builds on integrated S0/S1/S2A. Rev 4
closes audit 001053: the scheduler **genesis** is now bound to exactly one authenticated `SchedulerRun` per
world-line (an authorized run-start state — a root world-line's `logical_step==0` initial state, or a forked
world-line's `ForkInitialization.materialized_child_initial_state_hash`). `scheduler_run_id` is part of every
`SchedulerState`/`Activation` identity, an `initial` cursor is valid ONLY at that bound genesis, and every
cursor's provenance chain must terminate at that unique genesis — so a caller cannot "reset" the scheduler at
a later admitted state to duplicate/skip owed turns. Rev 3 closes audit 001047: (a) every non-initial cursor carries an **authenticated provenance link**
(`prev_scheduler_state_hash` + `last_outcome` + `last_applied_transition_hash`) and is canonical ONLY as the
exact one-step `consume()` successor of a registered predecessor — a content-addressed record with an
in-range `within_round_index` is no longer trusted, so a forged cursor cannot skip mandatory turns or jump
rounds; (b) **QUIESCENT** is the first, disjoint dispatch rule; (c) the `RandomDraw` authoritative value is a
frozen **integer draw word** (exact JSON), with the uniform in `[0,1)` derived by consumers. (Rev 2 added the
round-start queue anchor + `PASS`; rev 1 the base engine.)

## 1. Purpose and boundary
S2B is the **deterministic turn engine**: a pure function of the authoritative `WorldState` + a
content-addressed **scheduler cursor** that yields the ordered sequence of **activations** (which body is
invited to act), **passes** (an eligible body with no legal action), and **`advance_step` ticks**. Logical
positions — never wall-clock — are execution identity. It decides *whose turn it is*, never the action
CONTENT (agent/experiment choice). No perception (S2C), no labels/training/weights, no `tools/council`
change. Same spec + admitted initial state + `world_line_id` + `scheduler_version` (+ same scripted action
choices) ⇒ **byte-identical** sequence + authoritative state, independent of host/thread/filesystem/dict order.

## 2. Records and identities (self-excluded, domain-separated; reuse `_content_record` + S1 registry)

| record | literal `_domain` | preimage keys (id self-excluded) |
| --- | --- | --- |
| `SchedulerRun` | `spatial.scheduler_run.v1` | `spatial_schema_version`, `scheduler_version`, `world_line_id`, `initial_world_state_hash` |
| `SchedulerState` | `spatial.scheduler_state.v1` | `spatial_schema_version`, `scheduler_version`, `scheduler_run_id`, `world_line_id`, `current_world_state_hash`, `round_start_state_hash`, `round_index`, `within_round_index`, `prev_scheduler_state_hash`(or `null`), `last_outcome`, `last_applied_transition_hash`(or `null`) |
| `Activation` | `spatial.activation.v1` | `spatial_schema_version`, `scheduler_version`, `scheduler_run_id`, `world_line_id`, `current_world_state_hash`, `round_start_state_hash`, `logical_step`, `round_index`, `within_round_index`, `agent_body_id`, `outcome_kind`, `legal_action_kinds` |
| `RandomStream` | `spatial.random_stream.v1` | `spatial_schema_version`, `scheduler_version`, `world_line_id`, `logical_step`, `purpose` |
| `RandomDraw` | `spatial.random_draw.v1` | `spatial_schema_version`, `random_stream_id`, `draw_position`, `value` |

- `scheduler_version` = frozen `SCHEDULER_VERSION` (unknown fails closed; any ordering/eligibility/tie-break/
  randomness rule change bumps it).
- `SchedulerRun` is the authenticated **genesis** of a run: it binds `initial_world_state_hash`, which MUST
  be a registered admitted `WorldState` in `world_line_id` that is an **authorized run-start** — for a ROOT
  world-line, its `logical_step == 0`; for a FORKED world-line, it equals a registered
  `ForkInitialization.materialized_child_initial_state_hash` for that world-line (S2A). Any other
  `initial_world_state_hash` (e.g. a mid-run state at `logical_step > 0`) is refused. `scheduler_run_id` is
  bound into every `SchedulerState`/`Activation` identity, so cursors of different runs never interoperate.
- `last_outcome ∈ {initial, activate, pass, advance_arrival, advance_endround}` names the one-step
  transition that produced THIS cursor from `prev_scheduler_state_hash`; `last_applied_transition_hash` is the
  S2A `LocationTransition` id for `activate`/`advance_*` (an S2A edge was applied) and `null` for
  `initial`/`pass` (no state change). A cursor is canonical only if it is the exact `consume()` successor of
  its (registered) predecessor (§5); `initial` cursors have `prev=null` and are derivable from the initial
  admitted state.
- `outcome_kind ∈ {activate, pass}`. `legal_action_kinds` = sorted legal S2A actor-action kinds for the body
  at `current_world_state_hash` (§4); empty ⇒ `outcome_kind = pass`.
- **No stored `remaining_body_queue`**: the queue is DERIVED canonically as
  `sorted_eligible(round_start_state)[within_round_index:]` (§3), so a cursor is fully verifiable from its
  own fields — the consumed history is exactly the first `within_round_index` of the round's frozen,
  sorted eligible list.

## 3. The deterministic turn model (queue anchored to the round-start state)
**Eligibility:** a body is eligible iff lifecycle `present` **and** location `InRoom` (an `in_transit`,
`absent`, or `removed` body is never activated). `sorted_eligible(state)` = eligible bodies sorted by
`agent_body_id` (content-addressed id — a stable, host/dict-independent total order; the frozen tie-break).

A **round** is anchored to a `round_start_state` and consumes its frozen queue `Q =
sorted_eligible(round_start_state)` head-first. A queued body stays `present`+`InRoom` until its own turn (no
S2A actor action moves or removes another body; `advance_step` only lands `in_transit` bodies, which are not
in `Q`), so the head is always valid when reached. `initial_scheduler_state(scheduler_run, world_state)` requires
`world_state.id == scheduler_run.initial_world_state_hash` (the authorized genesis — §2) and binds
`scheduler_run_id = scheduler_run.id`, `current = round_start = world_state.id`, `round_index = 0`,
`within_round_index = 0`, `prev = null`, `last_outcome = "initial"`. A genesis at any non-run-start state is
refused, so the scheduler cannot be reset mid-run.

`next(scheduler_state, world_state, registry)` — pure/deterministic, fail-closed on an incoherent cursor
(§5) — dispatches in this **exact, mutually-exclusive order** (QUIESCENT first, so it is never shadowed):
0. **Quiescence (first):** if `world_state` has **no** `present`+`InRoom` body **and no** `in_transit`
   body, return `QUIESCENT` — no step; a run may end. A turn is never fabricated. (All later rules assume at
   least one eligible or in-transit body, so end-of-round ADVANCE and QUIESCENT are disjoint.)
1. **Arrivals-first ADVANCE:** else if any `present` body is `in_transit` with `arrival_step ==
   world_state.logical_step + 1`, return `ADVANCE`. Consuming it applies S2A `advance_step` (H→H1); the next
   cursor keeps the **same round** (`round_start_state_hash`, `round_index`, `within_round_index` unchanged;
   `current_world_state_hash = H1`) — the interrupted head still owes its turn, and the just-arrived body
   joins the NEXT round, never this frozen `Q`.
2. **Head of round:** else let `Q = sorted_eligible(round_start_state)`. If `within_round_index < len(Q)`,
   let `body = Q[within_round_index]` and `L = legal_action_kinds(body, world_state, registry)`. Return an
   `Activation` binding this position, `body`, `outcome_kind = pass if L empty else activate`, and `L`.
   - **activate** (L non-empty): the caller obtains `body`'s chosen legal action and applies it via S2A
     `apply_transition` (H→H1); the next cursor is `current = H1`, `within+1`, same round.
   - **pass** (L empty): NO S2A action; the next cursor is `current = H` (unchanged), `within+1`, same round.
     Pass gives an actionless body deterministic progress without an unsupported S2A no-op.
3. **End-of-round ADVANCE:** else (`within_round_index == len(Q)`, and — by rule 0 — some in-transit body
   or a non-empty round exists) return `ADVANCE`; consuming it applies `advance_step` (H→H1) and the next
   cursor starts a NEW round: `current = round_start = H1`, `round_index+1`, `within = 0`.

**Liveness (total):** every non-quiescent admitted state has a well-defined next step — `ADVANCE` (arrivals
due, end of round, or only in-transit bodies remain), an `activate` (head has a legal action), or a `pass`
(head has none). No reachable non-quiescent state lacks a legal successor, and no eligible body can wedge
the fold.

## 4. Legal-action context
`legal_action_kinds(body, world_state, registry)` = the sorted subset of S2A actor kinds (`move`, `take`,
`drop`, `give`, `put_inside`, `take_out`) whose S2A precondition is satisfiable for `body` at the **current**
`world_state` (e.g. `move` iff an available in-world portal leaves the body's room with destination capacity
headroom; `take` iff a co-located portable object exists with inventory headroom). DERIVED (never
authoritative), bound into the `Activation` id so a forged context yields a different id.

## 5. Authenticated provenance + fail-closed forgery resistance
A cursor's validity is NOT established by content-address + in-range fields alone (that would let a forged
record jump within/across rounds). It is established by **authenticated one-step provenance**: a
`SchedulerState` `S` is canonical iff EITHER
- **initial** (`prev_scheduler_state_hash == null`, `last_outcome == "initial"`,
  `last_applied_transition_hash == null`): `scheduler_run_id` names a **registered** `SchedulerRun` `R` (a
  valid authorized genesis, §2), and `current == round_start == R.initial_world_state_hash`, `world_line_id
  == R.world_line_id`, `round_index == 0`, `within_round_index == 0` — i.e. `S ==
  initial_scheduler_state(R, that genesis state)`. A registered admitted state that is NOT `R`'s bound
  genesis cannot anchor an initial cursor, so a mid-run reset is refused; OR
- **a `consume()` successor**: its `prev_scheduler_state_hash` names a **registered canonical**
  `SchedulerState` `P` with the SAME `scheduler_run_id` (a cursor never changes runs), and `S` is EXACTLY the
  cursor the §3 rule dispatched from `P` produces for
  `last_outcome`:
  - `activate`: `P`'s head `= sorted_eligible(P.round_start)[P.within]` is the actor of the registered S2A
    edge `last_applied_transition_hash` (`P.current → S.current`, a valid `apply_transition`), `round_start`/
    `round_index` unchanged, `within = P.within+1`; the head's `legal_action_kinds` at `P.current` were non-empty.
  - `pass`: the head's `legal_action_kinds` at `P.current` were empty; `S.current == P.current`,
    `last_applied_transition_hash == null`, `round_start`/`round_index` unchanged, `within = P.within+1`.
  - `advance_arrival`: an arrival was due at `P.current.logical_step+1`; `last_applied_transition_hash` is a
    valid `advance_step` edge `P.current → S.current`; `round_start`/`round_index`/`within` unchanged.
  - `advance_endround`: `P.within == len(sorted_eligible(P.round_start))` and no arrival was due;
    `last_applied_transition_hash` is a valid `advance_step` edge `P.current → S.current`;
    `round_start == S.current`, `round_index = P.round_index+1`, `within = 0`.

An `Activation` is canonical iff its `SchedulerState` is canonical, `current_world_state_hash ==
world_state.id`, `logical_step == world_state.logical_step`, `agent_body_id ==
sorted_eligible(round_start_state)[within_round_index]`, and `outcome_kind`/`legal_action_kinds` match the §3
derivation on the current state. `consume(scheduler_state, world_state, applied_transition_or_None,
registry)` is the ONLY constructor of non-initial cursors: it re-verifies `scheduler_state` is registered
canonical, dispatches §3, checks the supplied `applied_transition` is the required S2A edge (or `None` for
`pass`), registers and returns the successor (propagating `scheduler_run_id` unchanged). Because every
accepted cursor must exhibit a registered canonical predecessor with the same `scheduler_run_id` and the
exact dispatched delta, and every provenance chain terminates at the run's **unique authenticated genesis**
(the `SchedulerRun`-bound run-start state — not any admitted snapshot), a caller-fabricated cursor that
**skips a mandatory turn** (jumps `within`), **duplicates** a turn, **selects a different round anchor**,
**resets the run at a later state** (a non-genesis initial cursor), or is **stale/cross-world** has no valid
provenance and is refused; unsupported `scheduler_version` fails closed.

## 6. Deterministic randomness (frozen; the base scheduler consumes none)
The base engine is fully deterministic (sorted round-robin + pass), so the first slice draws no randomness.
When a policy needs it, it MUST use a **domain-separated deterministic stream** (never a global RNG):
`RandomStream` id `= config_hash({_domain:"spatial.random_stream.v1", scheduler_version, world_line_id,
logical_step, purpose})`. A draw's **authoritative value is a frozen integer draw word** — `digest =
config_hash({_domain:"spatial.random_draw.v1", random_stream_id, draw_position})` (a 64-hex string) and
`value = int(digest[:16], 16)` — an exact non-negative integer `0 ≤ value < 2**64`, stored as a JSON integer
(no float rounding, no representation ambiguity). A consumer derives a uniform in `[0,1)` as `value / 2**64`
(always `< 1`) or an exact float64 as `(value >> 11) / 2**53`; those are DERIVED, never stored. A `RandomDraw`
whose stored `value != int(digest[:16], 16)` is refused. No wall-clock/PID/host entropy enters identity or
value. There is no `seed`
parameter: stream identity IS the seed commitment. Byte-pinned stream/draw vectors accompany the slice.

## 7. Replay (determinism)
`schedule(initial_world_state)` folds `next()`/`consume()` (advancing S2A via the caller-supplied chosen
actions in a scripted run) to produce the ordered `[Activation | ADVANCE]` sequence + final state.
**Guarantee:** same spec + admitted initial state + `world_line_id` + `scheduler_version` (+ same scripted
action choices) ⇒ **byte-identical** sequence and authoritative state, independent of host/thread/filesystem/
dict-iteration order (queues are sorted canonical lists; all records content-addressed; no wall-clock).
Latency is non-identity metadata and never enters a preimage.

## 8. Non-goals / deferred
No perception/observation (S2C). No action CONTENT / agent policy. No portal/object internal state (S2A
deferral). No labels/training/weights/T0-B/M14-SC-8/society. No `tools/council` changes. No wall-clock/PID/
UUID/object-identity/dict-iteration order in any identity or ordering decision.

## 9. Threat model + identity vectors
**Identity vectors (byte-pinned):** a `SchedulerRun`; an `initial` / post-activation / post-pass /
post-arrival / new-round `SchedulerState` (each with its `scheduler_run_id`/`prev`/`last_outcome`/
`last_applied_transition_hash`); an `activate` and a `pass` `Activation`; a `RandomStream`; a `RandomDraw`
(incl. its frozen integer draw word).
**Adversarial (each fails closed):** a **genesis reset** (an `initial` cursor whose `current` is an admitted
mid-run state, not the `SchedulerRun`-bound run-start — so an acted body cannot be re-activated by resetting;
a `SchedulerRun` whose `initial_world_state_hash` is not an authorized run-start (root `logical_step!=0`, or
a forked world-line state that is not a registered `ForkInitialization` materialized child) is itself
refused); a cursor whose `scheduler_run_id` differs from its predecessor's (cross-run splice); an
**unprovenanced cursor** (a content-addressed `SchedulerState` whose `prev_scheduler_state_hash` is
null-but-not-initial, unregistered, or not the exact §5 one-step predecessor — e.g. a fabricated cursor with
`within == len(Q)` that skips every mandatory head); stale/cross-world cursor
(`current_world_state_hash`/`world_line` mismatch); forged cursor (wrong `within_round_index`/
`round_start_state_hash`/`round_index`/`last_outcome`); duplicate turn
(body not the derived head); skipped mandatory turn (non-head activation); activation onto a due-arrival
step; ineligible-body activation (`in_transit`/`absent`/`removed`/cross-world); a `pass` claimed when the
head has a legal action, or an `activate` claimed when it has none; a `RandomDraw` whose stored integer
`value != int(digest[:16],16)`; unsupported `scheduler_version`. **Determinism:** identical inputs → identical sequence
across two independent runs and across shuffled registry/dict orderings. **Liveness:** every non-quiescent
admitted state yields a step (activate/pass/advance), incl. an all-actionless-eligible round (all pass, then
advance); a fully quiescent state yields `QUIESCENT`, never a fabricated turn.

## 10. Compatibility
Additive only; new files under `coliseum/textlab/spatial/`. No existing module / primary evidence /
`tools/council` change; S0/S1/S2A records + `control_of` untouched; frozen `SPATIAL_SCHEMA_VERSION` reused +
a new frozen `SCHEDULER_VERSION`. Historical evidence + schema dispatch preserved.
