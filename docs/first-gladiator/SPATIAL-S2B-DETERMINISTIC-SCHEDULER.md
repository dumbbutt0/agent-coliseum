# Spatial S2B — Deterministic scheduler (design source, rev 8)

**Status:** design source for council review. No production code. Builds on integrated S0/S1/S2A. Adopts the
owner's architecture decision (pure linear replay chain + authenticated `WorldLineGenesis`). Rev 8 closes
audit 001077: (a) the fork reachability proof is a VERIFICATION witness, NOT a `WorldLineGenesis` identity
input, so a given authorized (child line, parent snapshot, decision) has exactly ONE genesis id regardless of
which reachable occurrence witnesses it; (b) `WorldLineGenesis` binds a deterministically-materialized
`topology_closure_hash` (all rooms/portals/objects/bodies from the normative `initial_layout`), and
`next`/`verify`/`legal_action_kinds` resolve instances ONLY within that committed closure, so legal actions +
replay are fully determined; (c) §4 binds the exact per-kind preconditions to the integrated S2A design
source by commit (`7cd99122`) as the normative source of truth. Rev 7 closed audit 001071: (a) the explicit-stop terminal rule is now **exclusive** (a run with `explicit_stop_position`
finalizes ONLY at that reachable position; a run without one finalizes ONLY at QUIESCENT with the script
exhausted — the cases cannot both validate); (b) a fork's `parent_state_hash` must be a canonically
**reachable** state on the parent's authenticated scheduler run (bound `parent_scheduler_run_id` +
`parent_scheduler_position`), recursively to an authenticated root — not merely an admitted state on a line
with a genesis; (c) §3 dispatch + §4 legal actions are now inlined (self-contained). Rev 6 closes
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
| `WorldLineGenesis` | `spatial.world_line_genesis.v1` | `spatial_schema_version`, `world_line_id`, `initial_world_state_hash`, `topology_closure_hash`, `root_or_fork`, `parent_world_line_id`(or `null`), `parent_state_hash`(or `null`), `fork_logical_step`(or `null`), `source_fork_decision_hash`(or `null`) |
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
  deterministic remap on `parent_state_hash` reproduces exactly `initial_world_state_hash`, and
  `topology_closure_hash` equals the deterministically materialized child topology (§2.2). **AND
  `parent_state_hash` must be a canonically REACHABLE state on the parent world-line's authenticated
  scheduler run** — but this reachability is a VERIFICATION obligation proven by a *witness supplied to the
  verifier*, NOT an identity input: the witness `(parent_scheduler_run_id, parent_scheduler_position)` must
  satisfy that the parent's finalized `SchedulerManifest` has, at that position, a `SchedulerState` whose
  `current_world_state_hash == parent_state_hash`, and the parent line's own `WorldLineGenesis` is
  authenticated (root by §2.2; fork by this rule) recursively to a root. **Identity purity:** the
  `WorldLineGenesis` id is a pure function of the already-fixed fork inputs (`world_line_id`,
  `initial_world_state_hash`, `topology_closure_hash`, `parent_world_line_id`, `parent_state_hash`,
  `fork_logical_step`, `source_fork_decision_hash`) — the witness is NOT in the preimage, so a given
  authorized (child line, parent snapshot, decision) yields exactly ONE `WorldLineGenesis` id regardless of
  which reachable occurrence witnesses it (closing the multiple-valid-id gap). A `ForkInitialization` is NEVER
  self-authenticating; an admitted-but-unreachable parent snapshot has no valid witness and is refused.

### 2.2 Deterministic root-genesis + topology materialization (the committed closure)
For a scheduler-eligible ROOT world-line, `SpatialWorldSpec.initial_layout` is NORMATIVE (not opaque) and
specifies the COMPLETE scheduler-relevant topology + initial placement, canonically sorted:
`{"rooms": [{"room_spec_id", "room_logical_key"} …], "portals": [{"portal_spec_id", "portal_logical_key",
"from_room_logical_key", "to_room_logical_key"} …], "entities": [{"entity_kind", "spec_id", "logical_key",
"location"} …]}`, where a `location` references rooms/containers by the layout's *logical keys* (never by
world-bound instance ids, which do not exist at spec time). `materialize_root(world_line, registry)` is a
**pure deterministic** function that:
- instantiates every room (`RoomInstance(room_spec_id, world_line_id, room_logical_key)`), every portal
  (`PortalInstance(portal_spec_id, world_line_id, portal_logical_key)`, checked to connect the named rooms
  consistently with its `PortalSpec`), and every entity instance, registering each;
- assembles the genesis `WorldState` at `logical_step 0` (every entity `present`, locations resolved to the
  materialized instance ids);
- emits a content-addressed **topology closure**: the sorted set of every materialized instance id (rooms,
  portals, objects, bodies) for this world-line. `topology_closure_hash = config_hash` of that sorted set.

`WorldLineGenesis.topology_closure_hash` binds this closure, and **`next()`/`verify_manifest`/`legal_action_kinds`
resolve instances ONLY within the committed closure** (an instance outside it — a smuggled extra portal — is
not scheduler-visible). The genesis `WorldState` id and the closure are thus pure functions of the
`SpatialWorldSpec` (which contains `initial_layout`) + `world_line_id` — one canonical genesis + one topology
per root world-line, fully committed to replay. A malformed `initial_layout` (duplicate room/portal/entity
logical key, unresolvable/cross-spec reference, a portal whose endpoints disagree with its `PortalSpec`)
fails closed. For a FORK, the child topology is the deterministic remap of the parent closure (via
`materialize_fork`), and `topology_closure_hash` binds the remapped child closure. (S0's `SpatialWorldSpec`
is unchanged; S2B additively requires this `initial_layout` structure for scheduler eligibility.)

## 3. The deterministic turn model — normative dispatch (self-contained)
**Eligibility:** a body is eligible iff lifecycle `present` AND location `InRoom` (an `in_transit`/`absent`/
`removed` body is never activated). `sorted_eligible(state)` = the eligible bodies sorted by content-addressed
`agent_body_id` (a stable, host/dict-independent total order; the frozen tie-break). A **round** is anchored
to a `round_start_state`; its frozen queue `Q = sorted_eligible(round_start_state)` is consumed head-first
(queued bodies stay `present`+`InRoom` until their own turn — no S2A actor action moves/removes another body;
`advance_step` only lands `in_transit` bodies, which are not in `Q`).

`initial_scheduler_state(scheduler_run, world_state)` requires `world_state.id ==
worldlinegenesis(scheduler_run).initial_world_state_hash` and binds `scheduler_run_id`, `scheduler_position =
0`, `previous_scheduler_state_hash = null`, `last_outcome = "initial"`, `current = round_start = world_state.id`,
`round_index = within_round_index = 0`.

`next(scheduler_state, world_state, registry)` dispatches in this **exact, mutually-exclusive** order; every
non-QUIESCENT outcome, when consumed, increments `scheduler_position` and links
`previous_scheduler_state_hash`:
0. **Quiescence (first):** if `world_state` has NO `present`+`InRoom` body AND NO `in_transit` body, return
   `QUIESCENT` (no step; a run may end). All later rules assume ≥1 eligible or in-transit body, so QUIESCENT
   and end-of-round ADVANCE are disjoint.
1. **Arrivals-first ADVANCE:** else if any `present` body is `in_transit` with `arrival_step ==
   world_state.logical_step + 1`, return `ADVANCE` (`advance_step`, `last_outcome = advance_arrival`); the
   successor keeps the SAME round (`round_start`/`round_index`/`within_round_index` unchanged, `current =
   H1`).
2. **Head of round:** else let `body = Q[within_round_index]` if `within_round_index < len(Q)`, and `L =
   legal_action_kinds(body, world_state, closure)`. Return an `Activation` at this position for `body`,
   `outcome_kind = pass if L empty else activate`, `legal_action_kinds = L`.
   - `activate` (L non-empty): the caller applies `body`'s next committed action via S2A `apply_transition`
     (`H → H1`); successor `current = H1`, `within+1`, `last_outcome = activate`, same round.
   - `pass` (L empty): NO S2A action; successor `current = H` (unchanged), `within+1`, `last_outcome =
     pass`, same round.
3. **End-of-round ADVANCE:** else (`within_round_index == len(Q)`) return `ADVANCE` (`last_outcome =
   advance_endround`); the successor starts a NEW round: `current = round_start = H1`, `round_index+1`,
   `within = 0`.

**Liveness is total:** every non-quiescent admitted state yields a step (arrivals/head/end-of-round);
`QUIESCENT` only when no eligible AND no in-transit body — no reachable non-quiescent state lacks a
successor, and an all-actionless round passes then advances.

## 4. Legal-action context (normative S2A binding)
`legal_action_kinds(body, world_state, closure)` = the sorted subset of the S2A actor action kinds
`{move, take, drop, give, put_inside, take_out}` for which **at least one** concrete effect exists that
satisfies its exact S2A precondition for `body` at the CURRENT `world_state`, evaluated over the committed
**topology closure** (§2.2). The exact per-kind precondition (registry/type/world checks, actor rules,
capacity/inventory/accessibility/containment, and the resulting-state `admit_world_state`) is defined
NORMATIVELY by the **integrated S2A design source** (`docs/first-gladiator/SPATIAL-S2A-MUTABLE-LOCATION-STATE.md`
§4/§5/§6, at its integrated commit `7cd99122`) — that immutable contract is the single source of truth, and
this document binds it by reference rather than restating (and risking divergence from) it. The candidate
enumeration domain per kind is finite and closure-bounded: `move` over the portals in the closure leaving the
body's room; `take` over objects co-located with the body; `give` over co-located recipients × held objects;
`put_inside`/`take_out` over held objects × accessible containers; `drop` over held objects. A kind is in
`legal_action_kinds` iff its enumeration contains ≥1 candidate whose S2A precondition holds. It is DERIVED
(never authoritative) and bound into the `Activation` id, so a forged legal context yields a different id.
Empty ⇒ `outcome_kind = pass`.

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
  the **terminal rule (exclusive)** — exactly one terminal is legitimate per run, by the run's own
  commitment: **if `explicit_stop_position` is non-null**, the SOLE terminal is `S_N.scheduler_position ==
  explicit_stop_position` (which must be a reachable position with the committed script consumed up to it) —
  a QUIESCENT-ended continuation is NOT valid for such a run; **if `explicit_stop_position` is null**, the
  SOLE terminal is `next(S_N) == QUIESCENT` with the script exactly exhausted — an early cut is NOT valid.
  The two cases are mutually exclusive on a single `SchedulerRun`, so a run with an explicit stop cannot also
  finalize at quiescence and vice-versa. A **non-quiescent prefix** (a `chain_length=1` genesis-only
  manifest, or any early cut that is neither the committed stop nor QUIESCENT-per-the-rule) is refused; a
  **competing extension or alternative branch** for the same
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
snapshot; a fork whose parent line lacks a `WorldLineGenesis` (recursively), whose materialized child hash
is not the deterministic anti-transplant remap of the stated parent snapshot, or whose `parent_state_hash`
is not the state at `parent_scheduler_position` on the parent's authenticated `SchedulerManifest`
(admitted-but-unreachable parent refused); a malformed `initial_layout`; a `WorldLineGenesis` whose
`topology_closure_hash` mismatches the deterministically-materialized closure; a **smuggled instance outside
the committed closure** — an extra registered portal/room/object not in the genesis closure is not
scheduler-visible, so it changes no `legal_action_kinds`/dispatch/replay); an explicit-stop run finalized at
QUIESCENT instead of its committed stop, or a no-stop run finalized before QUIESCENT (terminal-rule
substitution);
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
