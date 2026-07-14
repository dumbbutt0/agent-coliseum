# Spatial S2B — Deterministic scheduler (design source, rev 5)

**Status:** design source for council review. No production code. Builds on integrated S0/S1/S2A. Rev 5
adopts the owner's architecture decision (2026-07-13) closing audit 001059's two HIGH findings: (1) the
scheduler is a **pure linear replay chain** finalized by a `SchedulerManifest` — no mutable/CAS "current
pointer" enters the scientific identity substrate; (2) genesis is an **immutable authenticated
`WorldLineGenesis` commitment** that the run manifest authorizes uniquely per world-line. A CAS-backed
live-turn service may exist LATER only as an operational projection, never as replay evidence.

## 1. Purpose and boundary
S2B is the **deterministic turn engine**: a pure function of the authoritative `WorldState` + a
content-addressed scheduler cursor, producing THE unique linear sequence of **activations** (whose turn it
is), **passes** (an eligible body with no legal action), and **`advance_step` ticks**. Logical positions —
never wall-clock — are execution identity. It decides *whose turn it is*, never the action CONTENT. No
perception (S2C), no labels/training/weights, no `tools/council` change. The canonical truth of a run is its
**finalized `SchedulerManifest`**, verifiable by re-deriving the whole chain from the authenticated genesis
+ the recorded S2A transitions — byte-identical, independent of host/thread/filesystem/dict order.

## 2. Records and identities (self-excluded, domain-separated; reuse `_content_record` + S1 registry)

| record | literal `_domain` | preimage keys (id self-excluded) |
| --- | --- | --- |
| `WorldLineGenesis` | `spatial.world_line_genesis.v1` | `spatial_schema_version`, `world_line_id`, `initial_world_state_hash`, `root_or_fork`, `parent_world_line_id`(or `null`), `parent_state_hash`(or `null`), `fork_logical_step`(or `null`), `source_fork_decision_hash`(or `null`) |
| `SchedulerRun` | `spatial.scheduler_run.v1` | `spatial_schema_version`, `scheduler_version`, `world_line_id`, `world_line_genesis_id` |
| `SchedulerState` | `spatial.scheduler_state.v1` | `spatial_schema_version`, `scheduler_version`, `scheduler_run_id`, `scheduler_position`, `previous_scheduler_state_hash`(or `null`), `world_line_id`, `current_world_state_hash`, `round_start_state_hash`, `round_index`, `within_round_index`, `last_outcome`, `last_applied_transition_hash`(or `null`) |
| `Activation` | `spatial.activation.v1` | `spatial_schema_version`, `scheduler_version`, `scheduler_run_id`, `scheduler_position`, `world_line_id`, `current_world_state_hash`, `round_start_state_hash`, `logical_step`, `round_index`, `within_round_index`, `agent_body_id`, `outcome_kind`, `legal_action_kinds` |
| `SchedulerManifest` | `spatial.scheduler_manifest.v1` | `spatial_schema_version`, `scheduler_version`, `scheduler_run_id`, `genesis_scheduler_state_hash`, `terminal_scheduler_state_hash`, `chain_length`, `ordered_s2a_transition_hashes` |
| `RandomStream` | `spatial.random_stream.v1` | `spatial_schema_version`, `scheduler_version`, `world_line_id`, `logical_step`, `purpose` |
| `RandomDraw` | `spatial.random_draw.v1` | `spatial_schema_version`, `random_stream_id`, `draw_position`, `value` |

- `scheduler_version` = frozen `SCHEDULER_VERSION` (unknown fails closed).
- `scheduler_position` is a strictly-monotonic integer incremented on **every** advancement — activate,
  pass, and advance alike — so each cursor in a run is unique and totally ordered; `previous_scheduler_state_hash`
  is the immediate predecessor (`null` only at position 0).
- `last_outcome ∈ {initial, activate, pass, advance_arrival, advance_endround}`;
  `last_applied_transition_hash` is the S2A `LocationTransition` id for `activate`/`advance_*`, `null` for
  `initial`/`pass`.
- `outcome_kind ∈ {activate, pass}`; `legal_action_kinds` = sorted legal S2A actor kinds for the body at
  `current_world_state_hash` (§4); empty ⇒ `pass`.

### 2.1 WorldLineGenesis — the immutable authenticated genesis commitment
`WorldLineGenesis` binds a world-line to its ONE authoritative initial `WorldState`. It does not
redefine the integrated S1 `world_line_id` (immutable); it BINDS that id to a genesis and is authorized +
made unique by the run manifest (§5). Validity (else refused):
- `initial_world_state_hash` is a registered, `admit_world_state`-valid `WorldState` in `world_line_id`.
- **root** (`root_or_fork == "root"`, fork fields `null`): `world_line_id` is a registered S1 root
  `WorldLine`; `initial_world_state.logical_step == 0`.
- **fork** (`root_or_fork == "fork"`): `parent_world_line_id`/`parent_state_hash`/`fork_logical_step`/
  `source_fork_decision_hash` re-verify the S2A **anti-transplant** — there is a registered `ForkDecision`
  `D` (`D.id == source_fork_decision_hash`) authorizing exactly `parent_state_hash` + `fork_logical_step` on
  `parent_world_line_id`, a registered `ForkInitialization` binding `child_world_line_id == world_line_id` +
  `materialized_child_initial_state_hash == initial_world_state_hash`, and re-running `materialize_fork`'s
  deterministic remap on `parent_state_hash` reproduces exactly `initial_world_state_hash` (a `ForkInitialization`
  is NEVER self-authenticating; the parent line must itself have an authenticated `WorldLineGenesis`).

## 3. The deterministic turn model (queue anchored to the round-start state)
Eligibility, the sorted-by-`agent_body_id` frozen round queue, and the numbered dispatch are as in rev 3/4
(QUIESCENT first; arrivals-first ADVANCE; head activate/pass; end-of-round ADVANCE). `sorted_eligible(state)`
= `present`+`InRoom` bodies sorted by content-addressed `agent_body_id`. **Every** dispatched step increments
`scheduler_position` and links `previous_scheduler_state_hash`, including a `pass` (which leaves
`current_world_state_hash` unchanged but still advances `scheduler_position` and `within_round_index`).
`initial_scheduler_state(scheduler_run, world_state)` requires `world_state.id ==
worldlinegenesis(scheduler_run).initial_world_state_hash` and binds `scheduler_position = 0`,
`previous_scheduler_state_hash = null`, `last_outcome = "initial"`, `current = round_start =` the genesis
state, `round_index = within_round_index = 0`. Liveness is total (activate/pass/advance always available for
a non-quiescent state; `QUIESCENT` only when no eligible AND no in-transit body).

## 4. Legal-action context
`legal_action_kinds(body, world_state, registry)` = the sorted S2A actor kinds whose S2A precondition is
satisfiable for `body` at the current state (DERIVED, bound into the `Activation` id). (Unchanged from rev 2.)

## 5. Pure linear chain + finalized manifest (the canonical truth)
There is **no mutable current pointer**. The authoritative artifact of a run is its finalized
`SchedulerManifest`, and truth is established by **whole-chain re-derivation**, not by any single cursor:

- `genesis`: `SchedulerRun.world_line_genesis_id` names a valid `WorldLineGenesis` `G` (§2.1); the genesis
  `SchedulerState` is `initial_scheduler_state(SchedulerRun, G.initial_world_state)` at `scheduler_position 0`.
- `consume(scheduler_state, world_state, applied_transition_or_None, registry)` is the ONLY constructor of
  non-genesis cursors: it verifies the predecessor is canonical, dispatches §3, checks the supplied
  `applied_transition` is the required S2A edge (or `None` for `pass`), and returns the successor with
  `scheduler_position += 1`, `previous_scheduler_state_hash = predecessor.id`, same `scheduler_run_id`.
- **Finalization + verification:** a `SchedulerManifest` commits `genesis_scheduler_state_hash`,
  `terminal_scheduler_state_hash`, `chain_length = N+1`, and `ordered_s2a_transition_hashes`. `verify_manifest`
  reconstructs the chain `S0..S_N` and fails closed unless: `S0` is the genesis; for each `i`, `S_{i+1}` is
  the EXACT `consume()` successor of `S_i` (correct `scheduler_position = i+1`, `previous_scheduler_state_hash
  == S_i.id`, dispatched `last_outcome`, and — for `activate`/`advance_*` — `last_applied_transition_hash`
  equals `ordered_s2a_transition_hashes[k]` applied `S_i.current → S_{i+1}.current`); `S_N ==
  terminal_scheduler_state_hash`. It **rejects gaps** (non-contiguous positions), **duplicates** (a repeated
  position/state), **backlinks** (a `previous` that is not `S_{i}`), **transition mismatches**, and
  **multiple successors** inside the canonical chain (each `S_i` has exactly one recorded successor). Because
  truth is the linear manifest, **reusing an old cursor** merely produces a candidate BRANCH that cannot
  extend the finalized run — persisting a branch requires a distinct authorized `WorldLineGenesis`/
  `SchedulerRun` (an owner-authorized fork), never a splice into the committed chain.
- Every cursor still fails closed individually on stale/cross-world (`current_world_state_hash`/`world_line`
  mismatch), a foreign `scheduler_run_id`, a non-genesis `initial` cursor, an ineligible/non-head body, an
  activation onto a due-arrival step, or an unsupported `scheduler_version`; but forgery resistance is
  ultimately the manifest re-derivation, not any record's mere content-address.

## 6. Deterministic randomness (frozen; the base scheduler consumes none)
Unchanged from rev 3: `RandomStream` id `= config_hash({_domain:"spatial.random_stream.v1",
scheduler_version, world_line_id, logical_step, purpose})`; a draw's authoritative value is the frozen
integer word `value = int(config_hash({_domain:"spatial.random_draw.v1", random_stream_id,
draw_position})[:16], 16)` (`0 ≤ value < 2**64`, exact JSON integer; uniform `= value/2**64` derived, never
stored); a `RandomDraw` whose stored `value` disagrees is refused. No global RNG / wall-clock / host entropy;
no `seed` parameter (stream identity IS the seed commitment). The base engine draws none.

## 7. Replay (determinism)
Given a `SchedulerRun` (⇒ authenticated `WorldLineGenesis` ⇒ genesis `WorldState`) + the run's ordered S2A
transitions (the scripted action choices), the entire scheduler chain + `SchedulerManifest` re-derive
**byte-identically**, independent of host/thread/filesystem/dict-iteration order (sorted queues,
content-addressed records, monotonic positions, no wall-clock). Latency is non-identity metadata.

## 8. Non-goals / deferred
No perception (S2C). No action CONTENT / agent policy. No portal/object internal state. No labels/training/
weights/T0-B/M14-SC-8/society. No `tools/council` changes. No mutable/CAS scheduler authority in the replay
substrate (a live-turn projection, if ever built, is non-canonical). No redefinition of the integrated S1
`world_line_id` (WorldLineGenesis BINDS it; if the owner later intends to replace S1 identity derivation
that is a separate S1-touching decision). No wall-clock/PID/UUID/object-identity/dict order in identity.

## 9. Threat model + identity vectors
**Identity vectors (byte-pinned):** a root + a fork `WorldLineGenesis`; a `SchedulerRun`; a genesis /
post-activate / post-pass / post-arrival / new-round `SchedulerState` (with `scheduler_position`/`previous`);
an `activate` + `pass` `Activation`; a `SchedulerManifest`; a `RandomStream`; a `RandomDraw`.
**Adversarial (each fails closed):** an unauthenticated genesis (a root `WorldLineGenesis` at
`logical_step!=0`; a fork whose parent line lacks a `WorldLineGenesis`, or whose materialized child hash is
not the deterministic anti-transplant remap of the stated parent snapshot; a second `WorldLineGenesis` /
`SchedulerRun` claiming an existing line but committed as the run's unique genesis — refused by the manifest
uniqueness rule); a **manifest with a gap / duplicate / backlink / transition mismatch / branch** (two
successors of one `S_i`) in the reconstructed `0..N` chain; a **reused/old cursor** spliced onto a finalized
run (rejected — it is a non-extending branch); a stale/cross-world cursor; a cross-run `scheduler_run_id`
splice; a non-genesis `initial` cursor; a duplicate/skipped/ineligible/due-arrival activation; a `RandomDraw`
value `!= int(digest[:16],16)`; unsupported `scheduler_version`. **Determinism:** identical inputs → identical
manifest across two independent runs and across shuffled registry/dict orderings. **Liveness:** every
non-quiescent admitted state yields a step (activate/pass/advance); a fully quiescent state yields `QUIESCENT`.

## 10. Compatibility
Additive only; new files under `coliseum/textlab/spatial/`. No existing module / primary evidence /
`tools/council` change; S0/S1/S2A records + `control_of` untouched (S1 `world_line_id` is BOUND by
`WorldLineGenesis`, not redefined); frozen `SPATIAL_SCHEMA_VERSION` reused + a new frozen `SCHEDULER_VERSION`.
Historical evidence + schema dispatch preserved.
