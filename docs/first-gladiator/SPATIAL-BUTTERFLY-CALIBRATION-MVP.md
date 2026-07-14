# Spatial Butterfly calibration MVP — scripted baseline (design source, rev 2)

Status: council-routed design source for phase 3 of the owner's post-R3 sequence
(2026-07-14): *"Run Butterfly MVP on those scenarios to establish a behavioral
calibration baseline in an embodied environment."* Consumes the integrated
Butterfly slice-1 intervention substrate (`intervention.py`, audits
000814/000820/000826/000832), the BUTTERFLY-ALIGNMENT-TRACK rev-6 design
authority, the integrated S2A..S2D spatial substrate, the golden suite (001178),
and the trajectory corpus (001190).

**Terminology (binding, from the rev-6 track):** behavioral calibration ·
controlled-intervention sensitivity · matched trajectory divergence · hidden
evaluation · calibration success. This MVP NEVER concludes anything about
alignment. Its strongest permitted claim: *"the calibration measurement
machinery detects and quantifies the preregistered intervention's trajectory
divergence deterministically in the embodied environment."*

## 1. Purpose and boundary

The rev-6 track's full protocol needs an adaptive TRAINER spending a ≤10-episode
budget. Scripted personas cannot "discover" anything — so the scripted MVP's
scientific content is the **measurement machinery**: interventions,
matched-trajectory pairs, and divergence quantification proven end-to-end on
embodied spatial trajectories, so that a later live-persona calibration run
(owner-gated) changes ONLY the persona, never the measurement. In scope:
spatial intervention definitions, the matched-pair record, the divergence
report, and the scripted baseline over every golden scenario. Out of scope
(gated/deferred): the adaptive trainer loop, Phase A/B hidden-suite lifecycle,
live LLM personas (owner), any label (T0-B), any training (M14/SC-8), society
surfaces (SC-LC).

## 2. A spatial intervention (REUSES the integrated Intervention record)

An MVP intervention is a preregistered, content-addressed change to ONE agent's
post-fork behavior at a golden scenario's designated fork point:

- `Intervention(intervention_id, cls="policy", kind="spatial_intent_substitution_v1",
  canonical_spec=...)` — the integrated slice-1 record as-is (construction-frozen,
  registry-admitted). `cls="policy"` because the treatment changes what an agent
  DOES (its intent tail), never the world definition.
- `canonical_spec` (exhaustive, self-describing): `{scenario, seed, agent_key,
  fork_position, fork_state_hash, changed_dimension, substituted_intents
  (the agent's full post-fork intent tail, symbolic form), unchanged_comparison_dims
  (explicit: world spec, all other agents' intents, the shared prefix)}`.
- **Realization binding = the S2B fork machinery PLUS a seed-bound
  execution-instance identity.** The treatment run's world line is a forked
  child whose `WorldLineGenesis` is validated with the reachability WITNESS
  against the parent's finalized manifest at exactly
  `fork_position`/`fork_state_hash` (anti-transplant across parent states,
  positions, and world lines). The witnessed-fork chain alone does NOT carry
  the rev-6 execution-instance concern: the SEED is deliberately absent from
  world/manifest/fork identity (the integrated regression pins that a seed
  change leaves `manifest_id`/`terminal_world_state_id` identical). Therefore
  the MVP defines a versioned **pre-realization execution instance**:

  > `execution_instance_id` = the canonical content hash of
  > `{execution_instance_schema_version: "1", intervention_id, scenario, seed,
  > agent_key, parent_world_line_id, parent_source_evidence_id, fork_position,
  > fork_state_hash, attempt_index}` — computed BEFORE the treatment run
  > executes, recorded in the treatment `run.json`, and re-verified by the
  > matched-pair constructor. `attempt_index` is a deterministic non-negative
  > integer (0 for the baseline; a re-attempt after a FailureRecord increments
  > it). A realization therefore cannot be reused across seeds, scenarios,
  > agents, parent states/positions, source evidence, or attempts.

## 3. The matched spatial pair (one new record)

`trs.matched_spatial_pair.v1` — content-addressed binding of one control run and
one treatment run:

`{schema_version, intervention_id, execution_instance_id, scenario, seed,
fork_position, fork_state_hash, control: {run_id, source_evidence_id,
manifest_id, world_line_id}, treatment: {run_id, source_evidence_id,
manifest_id, world_line_id, fork_decision_id, fork_genesis_id}}`

Constraints (fail closed): control and treatment world lines differ; the
treatment world line's genesis is a fork of the control world line at exactly
the bound position/state; both source-evidence ids bind complete six-file
evidence; the intervention's canonical_spec fields match the pair's bindings
(no pair can cite an intervention defined for a different fork); and the
pair's `execution_instance_id` re-derives EXACTLY from its own bound fields +
the treatment run.json's recorded instance (a treatment whose recorded
instance disagrees with the pair bindings is refused).

## 4. The divergence report (one new record)

`trs.spatial_divergence_report.v1` — the deterministic measurement over the
pair's trajectory-corpus projections (pure over evidence bytes, like the
projector):

A forked child's scheduler positions restart at 0 and its instance ids are
remapped by construction (`materialize_fork`/`materialize_fork_closure` mint
child instances), so RAW hash comparison across the two lines is undefined.
The report therefore compares in **logical coordinates** with **remap-aware
structural equality**:

- **Logical coordinate mapping**: child scheduler position `p` corresponds to
  combined coordinate `fork_position + p`. The control run itself IS the shared
  prefix (coordinates `0..fork_position` are the control's own authenticated
  chain; the treatment evidence binds the control's source-evidence id + the
  fork witness, so prefix drift is impossible by construction, not by
  re-comparison).
- **Remap normalization**: a world state (or effect) is normalized by replacing
  every instance id with its `(spec_id, deterministic_logical_instance_key)`
  pair — the key materialize_fork PRESERVES across the remap — and dropping the
  world-line id. Two states are remap-equal iff their normalized canonical
  forms are byte-equal.
- **Fork anchor check (replaces the raw prefix rule)**: the child GENESIS
  (child position 0) must be remap-EQUAL to the control state at
  `fork_position` — the anti-transplant guarantee restated structurally. If
  not, the report REFUSES.
- `first_divergent_coordinate` — the smallest combined coordinate whose
  remap-normalized control and treatment states differ (necessarily
  `> fork_position`).
- Per agent (matched by logical key): `action_sequence_delta` (first differing
  decision by combined coordinate; symbolic actions compared remap-normalized),
  `terminal_placement_delta` (remap-normalized terminal placements that
  differ), and `perception_divergence` — the first combined coordinate whose
  remap-normalized ACTOR observation CONTENT differs (observation ids differ
  trivially across lines because they embed instance ids; content is compared
  normalized; an agent whose normalized actor view never differs has `null`:
  the intervention was imperceptible to it — the embodied fog/privacy
  machinery feeding calibration).
- `pathway_note`: v0 spatial agents have no reflex/planner split; the rev-6
  pathway-competition measures are explicitly `not_applicable` (recorded, never
  imitated).

## 5. The scripted baseline protocol (the deliverable run set)

For EVERY golden scenario (+ the R3 scenario): one preregistered intervention at
its designated fork point substituting one agent's post-fork intent tail with a
legal alternative (derived through the same build-time legality machinery — an
illegal substitution refuses at definition time, never at run time).

**The exact additive production API** (the current `execute_spatial_run` cannot
run a fork treatment: it hard-calls the root `build_scenario` and supplies no
witness, and fork-genesis validation REFUSES without one):

- Interventions are preregistered in a CLOSED map `INTERVENTIONS = {name: spec}`
  (mirroring `SCENARIOS`; no DSL). Each spec names its scenario, seed, agent,
  and substituted intent tail.
- `build_treatment_scenario(intervention_name, registry)` (new, in
  `spatial/calibration.py`): rebuilds the control scenario; runs the canonical
  `schedule()` to obtain the parent chain + finalized manifest; constructs
  `ForkDecision` -> forked `WorldLine` -> `materialize_fork` ->
  `materialize_fork_closure` -> fork `WorldLineGenesis`; assembles the WITNESS
  `{scheduler_state_id, scheduler_manifest_id, action_script}` from the parent
  chain at `fork_position`; derives the child script from the substituted
  intents via the SAME `_derive_script` simulation over the child line; and
  returns a scenario dict of the SAME shape `build_scenario` returns, plus
  `{witness, execution_instance_id, treatment_bindings}`.
- `execute_spatial_run(scenario, seed, out_root, intervention=None)` (additive
  keyword): when `intervention` is given, the runner dispatches to
  `build_treatment_scenario`, passes `witness=` through BOTH `schedule()` AND
  `verify_manifest()` (their existing keyword), and records
  `{intervention_id, execution_instance_id, treatment_bindings (parent run/
  evidence/fork ids), witness ids}` in `run.json` (evidence schema bump to
  0.3, additive). Control runs are byte-identical to today (`intervention`
  absent -> identical code path and evidence).
- CLI: `spatial-run --scenario X --seed N [--intervention NAME]`;
  `spatial-replay` reconstructs a treatment by re-executing
  `(scenario, seed, intervention)` from `run.json` — same six-file
  byte-comparison; `spatial-inspect` unchanged.

Execute control + treatment through this one runner path, project both through
the trajectory corpus, emit the pair + divergence report, and PIN the report
ids as permanent regressions. Every claim in the baseline is a pinned,
replayable, content-addressed measurement.

## 6. Threat model + adversarial vectors

| # | Vector | Refusal / invariant |
|---|---|---|
| 1 | Realization transplant (treatment fork claiming a different parent state/position) | witnessed fork validation refuses (integrated S2B; regression at pair construction) |
| 1b | Realization reuse across seeds/agents/scenarios/attempts (seed absent from fork identity) | seed-bound `execution_instance_id` re-derivation at pair construction; mismatch refuses |
| 2 | Pair citing an intervention defined for a different fork/scenario/seed | pair constructor cross-checks canonical_spec bindings + the recorded execution instance; refuse |
| 3 | Fork-anchor violation (child genesis not remap-equal to the control fork state) | report refuses (structural anti-transplant restated); prefix drift impossible by construction (the control IS the prefix) |
| 4 | Illegal substituted intent | build-time legality refusal (existing `_select_effect` path) |
| 5 | Divergence report over incomplete/tampered evidence | corpus projector + six-file source bindings refuse |
| 6 | Alignment-flavored over-claim | binding terminology; the report carries a fixed `claim_ceiling` string; tests assert it |
| 7 | Pathway-competition imitation (fabricating reflex/planner data) | `not_applicable`, never fabricated |
| 8 | Nondeterminism | pinned report ids; cross-registry byte-identical replay of both runs |

## 7. Compatibility

Additive only: new `spatial/calibration.py` (INTERVENTIONS map + `build_treatment_scenario` + pair + report constructors + baseline driver) + the additive `execute_spatial_run(..., intervention=None)` keyword with witness propagation + evidence schema 0.3 (additive treatment fields; control evidence byte-unchanged) + the additive `--intervention` CLI flag + tests + docs. No change to the
integrated Intervention/registry, the v1 or spatial TRS records, the golden
pins, the S2B fork machinery, or any council schema. Version-dispatched; fail
closed on unknown versions. The adaptive-trainer protocol, hidden suites, and
live personas remain out of scope and gated.
