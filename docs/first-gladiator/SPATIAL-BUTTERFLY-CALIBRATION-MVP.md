# Spatial Butterfly calibration MVP — scripted baseline (design source, rev 1)

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
- **Realization binding = the S2B fork machinery.** The treatment run's world
  line is a forked child whose `WorldLineGenesis` is validated with the
  reachability WITNESS against the parent's finalized manifest at exactly
  `fork_position`/`fork_state_hash` (anti-transplant). A realization can never
  be transplanted to a different parent state, position, seed, or scenario —
  the rev-6 `execution_instance_id` concern is carried by the already-audited
  witnessed-fork identity chain.

## 3. The matched spatial pair (one new record)

`trs.matched_spatial_pair.v1` — content-addressed binding of one control run and
one treatment run:

`{schema_version, intervention_id, scenario, seed, fork_position,
fork_state_hash, control: {run_id, source_evidence_id, manifest_id,
world_line_id}, treatment: {run_id, source_evidence_id, manifest_id,
world_line_id, fork_decision_id, fork_genesis_id}}`

Constraints (fail closed): control and treatment world lines differ; the
treatment world line's genesis is a fork of the control world line at exactly
the bound position/state; both source-evidence ids bind complete six-file
evidence; the intervention's canonical_spec fields match the pair's bindings
(no pair can cite an intervention defined for a different fork).

## 4. The divergence report (one new record)

`trs.spatial_divergence_report.v1` — the deterministic measurement over the
pair's trajectory-corpus projections (pure over evidence bytes, like the
projector):

- `first_divergent_scheduler_position` — the earliest position whose
  world-state hash differs between control and treatment (must be
  `> fork_position` of the shared prefix; the prefix itself must be
  hash-identical position-by-position, else the report REFUSES).
- Per agent: `action_sequence_delta` (first differing decision position;
  control/treatment symbolic actions from the corpus records),
  `terminal_placement_delta` (authoritative terminal placements that differ),
  and `perception_divergence` — for each agent, the first scheduler position
  whose ACTOR observation id differs (an agent that never observes a different
  actor view has `null`: the intervention was imperceptible to it — the
  embodied fog/privacy machinery feeding calibration).
- `pathway_note`: v0 spatial agents have no reflex/planner split; the rev-6
  pathway-competition measures are explicitly `not_applicable` (recorded, never
  imitated).

## 5. The scripted baseline protocol (the deliverable run set)

For EVERY golden scenario (+ the R3 scenario): one preregistered intervention at
its designated fork point substituting one agent's post-fork intent tail with a
legal alternative (derived through the same build-time legality machinery — an
illegal substitution refuses at definition time, never at run time). Execute
control + treatment through the SAME `execute_spatial_run` path (treatment via a
fork-scenario builder that composes the witnessed fork + child script), project
both through the trajectory corpus, emit the pair + divergence report, and PIN
the report ids as permanent regressions. Every claim in the baseline is a
pinned, replayable, content-addressed measurement.

## 6. Threat model + adversarial vectors

| # | Vector | Refusal / invariant |
|---|---|---|
| 1 | Realization transplant (treatment fork claiming a different parent state/position) | witnessed fork validation refuses (integrated S2B; regression at pair construction) |
| 2 | Pair citing an intervention defined for a different fork/scenario/seed | pair constructor cross-checks canonical_spec bindings; refuse |
| 3 | Shared-prefix drift (control/treatment differ BEFORE the fork) | report refuses unless prefix hash-identical position-by-position |
| 4 | Illegal substituted intent | build-time legality refusal (existing `_select_effect` path) |
| 5 | Divergence report over incomplete/tampered evidence | corpus projector + six-file source bindings refuse |
| 6 | Alignment-flavored over-claim | binding terminology; the report carries a fixed `claim_ceiling` string; tests assert it |
| 7 | Pathway-competition imitation (fabricating reflex/planner data) | `not_applicable`, never fabricated |
| 8 | Nondeterminism | pinned report ids; cross-registry byte-identical replay of both runs |

## 7. Compatibility

Additive only: new `spatial/calibration.py` (fork-scenario builder + pair +
report constructors + baseline driver) + tests + docs. No change to the
integrated Intervention/registry, the v1 or spatial TRS records, the golden
pins, the S2B fork machinery, or any council schema. Version-dispatched; fail
closed on unknown versions. The adaptive-trainer protocol, hidden suites, and
live personas remain out of scope and gated.
