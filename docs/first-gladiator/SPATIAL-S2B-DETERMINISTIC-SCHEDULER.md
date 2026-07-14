# Spatial S2B — Deterministic scheduler (design source, rev 6)

**Status:** design source for council review. No production code. Builds on integrated S0/S1/S2A. Adopts the
owner's architecture decision (pure linear replay chain + authenticated `WorldLineGenesis`). Rev 6 closes
audit 001065's two HIGH findings within that architecture: (1) a run's canonical manifest is made **unique
and terminal-bound** — the `SchedulerRun` commits the complete authorized action script (and an explicit
stop, if any), so there is exactly ONE canonical `SchedulerManifest` per run and an arbitrary non-quiescent
prefix / competing extension / branch is refused; (2) a **root** genesis is normatively **materialized**
from the `SpatialWorldSpec.initial_layout` + the world-line, so each root world-line has exactly one
re-derivable canonical genesis `WorldState` (no chosen-snapshot ambiguity); forks require **recursive**
parent-genesis authentication. (Rev 5 adopted the linear-chain + WorldLineGenesis architecture.)

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
| `SchedulerRun` | `spatial.scheduler_run.v1` | `spatial_schema_version`, `scheduler_version`, `world_line_id`, `world_line_genesis_id`, `action_script_commitment`, `explicit_stop_position`(or `null`) |
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

### 2.1 WorldLineGenesis — the immutable authenticated, UNIQUE genesis commitment
`WorldLineGenesis` binds a world-line to its ONE authoritative, **re-derivable** initial `WorldState`. It
does not redefine the integrated S1 `world_line_id` (immutable); it BINDS that id to a genesis that is
uniquely determined by S1/S2A inputs (so two different snapshots cannot both be genesis). Validity (else
refused):
- `initial_world_state_hash` is a registered, `admit_world_state`-valid `WorldState` in `world_line_id`.
- **root** (`root_or_fork == "root"`, fork fields `null`): `world_line_id` is a registered S1 root
  `WorldLine`, and `initial_world_state_hash == materialize_root_initial_state(world_line, registry).id`
  (§2.2) — the ONE canonical genesis deterministically materialized from the `SpatialWorldSpec.initial_layout`.
  Any other admitted `logical_step==0` snapshot is NOT the genesis and is refused, so root genesis is unique.
- **fork** (`root_or_fork == "fork"`): `parent_world_line_id`/`parent_state_hash`/`fork_logical_step`/
  `source_fork_decision_hash` re-verify the S2A **anti-transplant** — there is a registered `ForkDecision`
  `D` (`D.id == source_fork_decision_hash`) authorizing exactly `parent_state_hash` + `fork_logical_step` on
  `parent_world_line_id`, a registered `ForkInitialization` binding `child_world_line_id == world_line_id` +
  `materialized_child_initial_state_hash == initial_world_state_hash`, re-running `materialize_fork`'s
  deterministic remap on `parent_state_hash` reproduces exactly `initial_world_state_hash`, **AND the parent
  world-line itself has a registered valid `WorldLineGenesis` (recursively to an authenticated root)** — a
  `ForkInitialization` is NEVER self-authenticating. Uniqueness: the fork genesis is fully determined by
  (authenticated parent snapshot + authorized `ForkDecision`), so at most one valid `WorldLineGenesis` exists
  per forked line.

### 2.2 Deterministic root-genesis materialization
For a scheduler-eligible ROOT world-line, `SpatialWorldSpec.initial_layout` is NORMATIVE (not opaque): a
dict `{"entities": [ … ]}` whose entries are canonically sorted and each is
`{"entity_kind": "agent_body"|"object", "spec_id": <S0 spec id>, "logical_key": <str>, "location": <layout
location>}`, where a layout location references rooms/containers by *spec* coordinates
(`{"tag":"in_room","room_spec_id":…,"room_logical_key":…}`, `held_by`/`inside` analogously) — never by
world-bound instance ids (which do not exist at spec time). `materialize_root_initial_state(world_line,
registry)` is a **pure deterministic** function: for each entity it derives the S1 instance
`instance(spec_id, world_line_id, logical_key)` (registering it), resolves each layout location to the
corresponding in-world instance id, and assembles the `WorldState` at `logical_step 0` with every entity
`present`. Its id is therefore a deterministic function of the `SpatialWorldSpec` (which contains
`initial_layout`) + `world_line_id` — one canonical genesis per root world-line. A malformed/ambiguous
`initial_layout` (duplicate entity, unresolvable location, cross-spec reference) fails closed; such a world
is simply not scheduler-eligible until it has a conforming layout. (S0's `SpatialWorldSpec` is unchanged;
S2B additively requires this structure for scheduler eligibility.)

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

## 5. Pure linear chain + UNIQUE finalized manifest (the canonical truth)
There is **no mutable current pointer**. The `SchedulerRun` **commits the whole run**: its
`action_script_commitment` `= config_hash` of the ordered list of the run's authorized actor decisions — one
per `activate` step, in order, each the canonical chosen S2A effect for that turn — and an optional
`explicit_stop_position` (an authenticated early stop). Because the scheduler interleaves `pass`/`advance`
deterministically, the ENTIRE chain is a pure function of `(genesis, action_script, explicit_stop)`; the
`SchedulerRun` id therefore commits to exactly ONE canonical chain and manifest. Truth is established by
**whole-chain re-derivation from that commitment**:

- `genesis`: `SchedulerRun.world_line_genesis_id` names a valid `WorldLineGenesis` `G` (§2.1); the genesis
  `SchedulerState` is `initial_scheduler_state(SchedulerRun, G.initial_world_state)` at `scheduler_position 0`.
- `consume(...)` is the ONLY constructor of non-genesis cursors (verifies the predecessor, dispatches §3,
  checks the supplied S2A edge or `None` for `pass`, returns the `+1`-position successor). At each `activate`
  it MUST apply the next committed action from the script, in order — no other action is canonical there.
- **Finalization + verification:** a `SchedulerManifest` commits `genesis_scheduler_state_hash`,
  `terminal_scheduler_state_hash`, `chain_length = N+1`, and `ordered_s2a_transition_hashes`.
  `verify_manifest` reconstructs `S0..S_N` from the genesis by re-running the scheduler over the
  `SchedulerRun`'s committed `action_script`, and fails closed unless: `S0` is the genesis; each `S_{i+1}` is
  the EXACT `consume()` successor of `S_i` (contiguous `scheduler_position`, `previous == S_i.id`, dispatched
  `last_outcome`, and for `activate` the applied edge is the next committed script action; for `advance_*`
  the required `advance_step`); the `ordered_s2a_transition_hashes` equal the applied edges in order; and —
  the **terminal rule** — `S_N` is a **legitimate stop**: either `next(S_N) == QUIESCENT` (the run drove to
  quiescence and the script is exactly exhausted) OR `S_N.scheduler_position == explicit_stop_position`.
  A **non-quiescent prefix** (a `chain_length=1` genesis-only manifest, or any early cut that is neither
  QUIESCENT nor the committed stop) is refused; a **competing extension or alternative branch** for the same
  `SchedulerRun` cannot exist because the run's committed script + terminal rule determine the one canonical
  manifest. It also rejects gaps, duplicates, backlinks, transition mismatches, and multiple successors.
  **Cross-manifest uniqueness:** the canonical manifest is a pure function of the `SchedulerRun` id, so any
  two valid finalized manifests for one run are byte-identical; a genuinely different action script is a
  DIFFERENT `SchedulerRun` (different id), and a different genesis is a different `WorldLineGenesis` — an
  alternative branch must derive its own authorized `SchedulerRun` before a genesis cursor exists, never
  splice into a committed run. Per-world-line, the run manifest references exactly one `WorldLineGenesis`
  (§2.1 makes root/fork genesis unique), so there is one authenticated genesis per line within a run's scope.
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
**Adversarial (each fails closed):** an unauthenticated/non-unique genesis (a root `WorldLineGenesis` whose
`initial_world_state_hash != materialize_root_initial_state(...)` — incl. a second admitted `logical_step==0`
snapshot; a fork whose parent line lacks a `WorldLineGenesis` (recursively), or whose materialized child hash
is not the deterministic anti-transplant remap of the stated parent snapshot; a malformed `initial_layout`);
a **truncated / prefix manifest** (a `chain_length=1` genesis-only or any early cut whose terminal is neither
`QUIESCENT` nor `explicit_stop_position`); a **competing extension or alternative branch** finalized for the
same `SchedulerRun` (impossible — the committed action_script + terminal rule fix one canonical manifest); a
manifest whose `ordered_s2a_transition_hashes` diverge from the committed `action_script`; a **manifest with a
gap / duplicate / backlink / transition mismatch / branch** in the reconstructed `0..N` chain; a **reused/old
cursor** spliced onto a finalized run; a stale/cross-world cursor; a cross-run `scheduler_run_id` splice; a
non-genesis `initial` cursor; a duplicate/skipped/ineligible/due-arrival activation; a `RandomDraw` value
`!= int(digest[:16],16)`; unsupported `scheduler_version`. **Determinism:** identical inputs → identical
manifest across two independent runs and across shuffled registry/dict orderings. **Liveness:** every
non-quiescent admitted state yields a step (activate/pass/advance); a fully quiescent state yields `QUIESCENT`.

## 10. Compatibility
Additive only; new files under `coliseum/textlab/spatial/`. No existing module / primary evidence /
`tools/council` change; S0/S1/S2A records + `control_of` untouched (S1 `world_line_id` is BOUND by
`WorldLineGenesis`, not redefined); frozen `SPATIAL_SCHEMA_VERSION` reused + a new frozen `SCHEDULER_VERSION`.
Historical evidence + schema dispatch preserved.
