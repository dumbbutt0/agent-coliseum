# Spatial S2B — Deterministic scheduler (design source, rev 2)

**Status:** design source for council review. No production code. Builds on integrated S0/S1/S2A. Rev 2
closes audit 001041: (a) the cursor now anchors its round queue to a `round_start_state_hash` +
`within_round_index` so it crosses S2A actor transitions canonically (no chain-walking, no re-derivation
from the post-action state); (b) a deterministic `PASS` gives progress to an eligible body with no
satisfiable action, making liveness total; (c) the `RandomDraw` value is a frozen canonical derivation.

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
| `SchedulerState` | `spatial.scheduler_state.v1` | `spatial_schema_version`, `scheduler_version`, `world_line_id`, `current_world_state_hash`, `round_start_state_hash`, `round_index`, `within_round_index` |
| `Activation` | `spatial.activation.v1` | `spatial_schema_version`, `scheduler_version`, `world_line_id`, `current_world_state_hash`, `round_start_state_hash`, `logical_step`, `round_index`, `within_round_index`, `agent_body_id`, `outcome_kind`, `legal_action_kinds` |
| `RandomStream` | `spatial.random_stream.v1` | `spatial_schema_version`, `scheduler_version`, `world_line_id`, `logical_step`, `purpose` |
| `RandomDraw` | `spatial.random_draw.v1` | `spatial_schema_version`, `random_stream_id`, `draw_position`, `value` |

- `scheduler_version` = frozen `SCHEDULER_VERSION` (unknown fails closed; any ordering/eligibility/tie-break/
  randomness rule change bumps it).
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
in `Q`), so the head is always valid when reached. `initial_scheduler_state(world_state)` binds
`current = round_start = world_state.id`, `round_index = 0`, `within_round_index = 0`.

`next(scheduler_state, world_state, registry)` — pure/deterministic, fail-closed on an incoherent cursor
(§5) — returns one of:
1. **Arrivals-first ADVANCE:** if any `present` body is `in_transit` with `arrival_step ==
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
3. **End-of-round ADVANCE:** else (`within_round_index == len(Q)`) return `ADVANCE`; consuming it applies
   `advance_step` (H→H1) and the next cursor starts a NEW round: `current = round_start = H1`,
   `round_index+1`, `within = 0`.
4. **Quiescence:** if there are no eligible bodies **and** no `in_transit` bodies, return `QUIESCENT` — no
   step; a run may end. A turn is never fabricated.

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

## 5. Fail-closed cursor + forgery resistance
A `SchedulerState`/`Activation` is **canonical** (else refused) iff: `scheduler_version` supported;
`world_line_id == world_state.world_line_id`; `current_world_state_hash == world_state.id` (**stale /
cross-world** cursor refused); the `round_start_state` is registered/admitted and in this world-line;
`0 <= within_round_index <= len(sorted_eligible(round_start_state))`; and (for an `Activation`)
`agent_body_id == sorted_eligible(round_start_state)[within_round_index]`, `logical_step ==
world_state.logical_step`, `outcome_kind`/`legal_action_kinds` match the canonical derivation. This rejects a
**forged position** (wrong `within_round_index`/`round_start`), a **duplicate turn** (a body not at the
derived head / already consumed), a **skipped mandatory turn** (activating a non-head eligible body), a
**stale-state action** (cursor bound to a superseded state), an **ineligible body** (`in_transit`/`absent`/
`removed`/cross-world), and an activation onto a **due-arrival** step (canonical next is `ADVANCE`).
Consumption is one atomic API: `consume(scheduler_state, world_state, applied_transition_or_None, registry)`
verifies the cursor + (for `activate`) that `applied_transition` is a valid S2A edge `H→H1` whose actor is
the head body, and returns the next canonical cursor; a caller cannot advance the cursor except through it.

## 6. Deterministic randomness (frozen; the base scheduler consumes none)
The base engine is fully deterministic (sorted round-robin + pass), so the first slice draws no randomness.
When a policy needs it, it MUST use a **domain-separated deterministic stream** (never a global RNG):
`RandomStream` id `= config_hash({_domain:"spatial.random_stream.v1", scheduler_version, world_line_id,
logical_step, purpose})`. A draw's **value is a frozen derivation** — `digest =
config_hash({_domain:"spatial.random_draw.v1", random_stream_id, draw_position})` (a 64-hex string), and the
canonical uniform in `[0,1)` is `uniform01(digest) = int(digest[:16], 16) / 2**64` (frozen decode; other
ranges via a stated canonical transform). A `RandomDraw` record stores `(random_stream_id, draw_position,
value)` with `value == uniform01(...)` — a `RandomDraw` whose stored value disagrees with the frozen
derivation is refused. No wall-clock/PID/host entropy enters identity or value. There is no `seed`
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
**Identity vectors (byte-pinned):** a round-start / mid-round / post-arrival `SchedulerState`; an `activate`
and a `pass` `Activation`; a `RandomStream`; a `RandomDraw` (incl. its frozen value).
**Adversarial (each fails closed):** stale/cross-world cursor (`current_world_state_hash`/`world_line`
mismatch); forged cursor (wrong `within_round_index`/`round_start_state_hash`/`round_index`); duplicate turn
(body not the derived head); skipped mandatory turn (non-head activation); activation onto a due-arrival
step; ineligible-body activation (`in_transit`/`absent`/`removed`/cross-world); a `pass` claimed when the
head has a legal action, or an `activate` claimed when it has none; a `RandomDraw` value disagreeing with the
frozen derivation; unsupported `scheduler_version`. **Determinism:** identical inputs → identical sequence
across two independent runs and across shuffled registry/dict orderings. **Liveness:** every non-quiescent
admitted state yields a step (activate/pass/advance), incl. an all-actionless-eligible round (all pass, then
advance); a fully quiescent state yields `QUIESCENT`, never a fabricated turn.

## 10. Compatibility
Additive only; new files under `coliseum/textlab/spatial/`. No existing module / primary evidence /
`tools/council` change; S0/S1/S2A records + `control_of` untouched; frozen `SPATIAL_SCHEMA_VERSION` reused +
a new frozen `SCHEDULER_VERSION`. Historical evidence + schema dispatch preserved.
