# Persistent Society MVP Profile (Rev. 2)

> **Status:** design source (doc-only). This profile is the **implementation-ready** companion to the
> vision-level annex `docs/first-gladiator/LIVING-COLISEUM.md` — it resolves the fifteen mechanical areas the
> `G-SOCIETY-PROFILE` gate (`IMPLEMENTATION-CONDITIONS.md`) requires **before any Phase-6 persistent-society
> code**. Integrating this document authorizes **no** code, no weight training, no schema freeze, no roadmap
> edit, and no scenario family; it is a bounded specification. Every build item it names still routes as its
> own Codex-audited request, and the persistent-society implementation is additionally gated on a dedicated
> owner SC gate (proposed **SC-LC**). It preserves every First-Gladiator/KTK invariant
> (`docs/first-gladiator/LIVING-COLISEUM.md §J`).
>
> **Rev. 2** resolves the three HIGH findings of audit `society-profile-001` (AUDIT_BLOCKED 000676): the
> foundational Living Coliseum source is now committed **in-repo** at `docs/first-gladiator/LIVING-COLISEUM.md`
> (+ `LIVING-COLISEUM-GAP-ANALYSIS.md`), so every anchor resolves from the audited commit (F1); the grounding
> paragraph now **separates actually-implemented reuse from proposed design** and claims no present
> implementation of the world event-chain / world-line identity (F2); and the profile now specifies the
> **exact identity-dependent typed payload contracts (§16)** and concrete per-memory-kind default policies
> (area 5), leaving only explicitly enumerated owner-authority choices unresolved (F3).
>
> **Grounding & reuse — implemented vs proposed (F2).**
> *Anchors* `docs/first-gladiator/LIVING-COLISEUM.md` (world-identity taxonomy §C, one deterministic world
> model §D, three research modes §E, MSP §F, event schema §H) and `KTK-PROGRAM.md`.
> **Actually implemented today, reused unchanged:** the textlab `EventDelta` record — fields exactly
> `{run_id, timestep, source, state_delta, narrative}` (`schema.py:388-402`), a *flat, non-hash-chained*
> world state-change record; byte-identical replay (`sweep.verify_run_replay`); effective-unit accounting +
> retry collapse (`metrics.py`); the §8 group-aware partition + held-out discipline (`partition.py`); the
> training-data admission gate (`training_admission.py`); the claim ladder (`registry.py`); and — for
> **governance events only** — the council's append-only hash-chained log (`tools/council`), which is **not**
> the world/experiment event substrate.
> **Proposed here, NOT yet implemented** (introduced only by future versioned-schema + migration slices, each
> Codex-audited; this profile freezes their contracts in §16 but implements nothing): a **hash-chained world
> event log** (extending `EventDelta` with a chain link + world-event identity); **world-definition /
> world-line / genesis-snapshot / fork identity**; the **seven memory-kind stores**; the **message binding**;
> and the **scenario director**. None of these exist in the audited commit.
>
> **Central law (reaffirmed):** the persistent world is **measured, never rewarded**. No composite scalar is
> ever produced for style, ritual, personality, harmony, chaos, or morality — observable features, event
> counts, transition rates, and context-conditioned comparisons only.

Numbering matches the fifteen `G-SOCIETY-PROFILE` resolution areas.

---

## 1. World time & scheduling

**Time hierarchy (nested, each a typed identity where longitudinal identity depends on it):**
`tick → turn → encounter → episode → world-day → lifetime → replicate`. A **tick** is one deterministic
world-engine resolution; a **turn** is one gladiator's bounded intention within a tick; an **encounter** is a
bounded interaction (camp/arena/beast) spanning turns; an **episode** is a scheduled measurement unit; a
**world-day** is the `sleep→…→remember` cycle (`LIVING-COLISEUM §D`); a **lifetime** is a gladiator's genesis→
terminal span; a **replicate** is a re-forked world under a different `sampler_seed`.

**Event sources (kept distinct, recorded on every consequential event — resolves area 9 too):**
`scheduled` (director clock), `state-triggered` (threshold, e.g. hunger→forage), `agent-caused` (an
intention). Each event carries an `event_source ∈ {scheduled, state_triggered, agent_caused}`.

**Timing rules.** Inactivity/timeout → a deterministic default action recorded as `agent_timeout` (never a
fabricated choice). Simultaneous actions resolve by a frozen, logged priority (deterministic tie-break by
`gladiator_id` under a per-tick `resolution_order` recorded in the event log — no hidden order). Consequences,
memory, and relationships update at **defined settlement points** (end of encounter for direct effects; end of
world-day for memory summarization + relationship-edge recomputation) so no update is silently interleaved.
**Pause/checkpoint/resume/crash-recovery:** the world state is reconstructable purely from the genesis
snapshot + the event chain (replay); a checkpoint is a `current_snapshot_hash` bound to an `event_chain_head`;
resume replays forward from the last checkpoint; a crash mid-tick quarantines the partial tick (area 13) and
resumes from the last settled tick — never from a partial world.

## 2. Experimental boundaries (which level supports which claim)

| Level | Supports | Never |
|---|---|---|
| attempt | integrity/replay only | a lived experience or an independent example |
| decision event | per-decision behavioral features | a lifetime claim |
| encounter | context-conditioned behavior (inside/outside) | a longitudinal-drift claim |
| episode | a preregistered measurement unit | pooling across world-lines |
| effective-unit | the non-pooled comparison cell (`metrics.py`) | crossing regimes/modes |
| lifetime | drift/arc claims for one gladiator | a population claim |
| world-generation | one world-line's emergent structure | a cross-world-line claim |
| society-replicate | replicated emergent structure | a Hunger-Games population claim (SC-9) |

**Retries collapse without becoming lived experiences** (reuse `metrics.py` retry-collapse + effective-unit;
a retry inherits its decision identity and never appends a second lived event to the world chain).
**Persistent-world dependence + cluster identity:** an observation binds its `world_line_id` +
`current_snapshot_hash`; no finding rests on a single world line (claim-ladder replication requires ≥2 distinct
citable world-lines/experiments, per the governance charter's replication gate).

## 3. Counterfactual world forks

A fork commits a world at a **logical point X** = a specific settled tick with an exact
`current_snapshot_hash`. From it, an **intervention branch** and a **control branch** descend, binding
`{parent_world_line_id, fork_tick, genesis_snapshot_hash, branch ∈ {control,intervention}, intervention_id,
held_constant[], changed_dimension}` (the `changed_dimension`/`held_constant` fields that verdict 000579
required for the mutation/env axis). Exactly one variable changes; all else is held. **No cross-branch
leakage:** a branch's event chain, memory, and RNG stream are isolated by `world_line_id`; the §8 partition +
held-out lint treats sibling branches as the same partition group (they may not straddle a train/eval split).
Branches occupy **separate effective-unit cells**; a replicate re-forks under a different `sampler_seed` to
separate sampler noise from intervention effect (`LIVING-COLISEUM §E` mode 2).

## 4. Gladiator lifecycle

**Events:** `creation → (living) → death | retirement | escape → replacement | resurrection`. **Identity
layers kept distinct** (never conflated in a record): **model digest** (weights) · **policy/persona**
(prompt/decoding/behavioral regime = existing `agent_regime_id`) · **Gladiator** (`gladiator_id`, the
persistent world entity) · **memory/relationship/intervention identity** (per §5). Rules: a **process
restart ≠ a new Gladiator** (same `gladiator_id` resumes from the chain); a **retry ≠ a second lived event**
(area 2); a **clone/resurrection ≠ silent continuity** — a resurrected or cloned Gladiator gets a new
`gladiator_id` with an explicit `derived_from` + a recorded discontinuity, never presented as the same
unbroken life. Death/replacement is a recorded terminal world event, not a deletion.

## 5. Memory architecture

**Seven memory kinds, never conflated** (extends `LIVING-COLISEUM §H` four-state-kinds rule). Each carries the
`memory_kind` contract of §16.7 (update-policy id · summarizer id/version · retrieval id/version · capacity ·
eviction · provenance source-event ids · observation boundary). **MVP default policies (bounded, chosen — only
the enumerated owner choices below are deferred):**

| Kind | Update trigger / writer | Capacity | Eviction | Observation boundary |
|---|---|---|---|---|
| immutable history | every settled world-event (world engine) | unbounded, append-only | never | per-event boundary |
| working | per turn (prompt assembler) | last encounter's events (≤ 32 events) | at encounter settlement | owner gladiator |
| retrieved | per decision (retrieval fn `retrieval.v1`) | top-8 by `retrieval.v1` over history | per-turn (not persisted) | owner gladiator |
| relationship | recomputed at world-day settlement from full chain | O(pairs) edges | recomputed, never accumulated | derived; owner + council, never primary metrics |
| autobiographical summary | world-day settlement (summarizer `summ.v1`) | ≤ 64 summary entries; older detail folded (lossy, recorded) | oldest-folded | owner gladiator |
| public-institutional | on public/institutional events | by institution schema | institution-defined | public |
| hidden-evaluator | evaluator-side only | unbounded | never | hidden (never agent-visible, never in a prompt) |

**Failure modes are first-class, never hidden:** forgetting, retrieval-failure, false/manipulated/disputed
memory are recorded as such (not silently dropped). **Binding rule:** *never infer policy/weight learning from
a memory-mediated behavior change* — a change explainable by retrieved memory is attributed to memory, not
learning. The agent may **inspect, challenge, and correct** its autobiographical memory through recorded
events; corrections append events and **never rewrite immutable history**. **Deferred owner choices
(enumerated):** the exact `retrieval.v1` / `summ.v1` function definitions and the final capacity constants are
frozen by their own audited slice (an AcceptanceProfile pilot may tune the numeric caps); the defaults above
are the MVP starting point.

## 6. Communication protocol

**Message kinds:** public · private · group · rumor · promise · vote · trade · threat · accusation ·
evidence · coalition · silence. Each binds **`{sender, intended_recipients[], actual_recipients[],
visibility, ordering, delivery_status}`**. **Isolation invariants:** no private message leaks into an
unauthorized agent's prompt (observation-boundary enforced at prompt assembly); **no simultaneous leakage via
sequential generation** (a later-generated agent never sees a same-tick private message it should not — the
resolution_order + observation boundary gate this, extending the sequential-generation isolation rule).
Unintended channels (side information, metadata, timing) are either **eliminated** or **registered as an
explicit factor** — never silent. Silence is a recorded choice, not absence of data.

## 7. Minimum society-state ontology

Small and extensible — **not** a general world engine. Entities: `agents · locations · resources ·
ownership · relationships · observer-reputation · alliances · institutions · roles · laws+enforcement ·
promises/debts · injuries · secrets · public-facts · private-observations · conflicts`. Objective state
(bodies, resources, ownership, injuries, public-facts) is authoritative; derived state (relationships,
reputation, alliances-as-inferred) links its source events and never enters primary metrics
(`LIVING-COLISEUM §H`). New ontology entries arrive only with a typed schema + a METRICS-v2 migration note.

## 8. Scenario director

Emits events of kind `scheduled | state-triggered | recurring | role-conditioned | private | public`, gated
by **eligibility / cooldowns / prerequisites / contradiction-prevention** (a director may not emit an event
that contradicts objective world state). Consequences may be **immediate or delayed** (a delayed consequence
binds its triggering event). Every directed event is tagged **canonical**, **irrelevant-perturbation**, or
**morally-relevant-counterfactual**, and records its **causal source category** (area 9). The director is
deterministic given `world_seed`; its schedule is part of the replayable chain.

## 9. Endogenous vs imposed event source
Every consequential event records `event_source ∈ {scheduled, state_triggered, agent_caused}` and a
`causal_source_category` (director-canonical / director-perturbation / director-counterfactual / agent /
world-physics). This lets analysis separate **endogenous** (agent- or physics-caused) from **imposed**
(director-caused) events — required so an emergent-behavior claim is never contaminated by a directed event.

## 10. Exact first training target (prediction, not control)

**Recommended first target:** *given admitted pre-decision evidence about this Gladiator and its registered
history, predict which available registered intervention is most likely to improve the preregistered bounded
behavioral vector without critical regression.* This is a **prediction** target only — **prediction ≠
selection ≠ memory-mediated change ≠ weight learning**. It reuses the §9 temporal feature boundary (feature
cutoff at the decision's `prediction_timepoint`; no post-outcome field is a feature), the admitted-evidence
gate (`training_admission.py`), and the §8 group-aware split. **This profile authorizes no training**; the
target is specified so later T1/M14 work has a frozen, leakage-safe definition to build against.

## 11. Resource-comparison regime

Comparisons declare their equalization axis and **never silently equate** across it:
`equal-tokens · equal-info · equal-actions · equal-episodes · equal-compute · model-native`. The regime
(token/context/reasoning/tool/memory/runtime/timeout budgets) is recorded per comparison cell and folded into
the effective-unit identity, so two gladiators are never compared as if matched on an axis they differ on.

## 12. Control populations

Every emergent/behavioral claim is measured against explicit controls: `scripted · random · fixed-policy ·
memory-disabled · planner-disabled · reputation-blind · intervention-free-LLM · same-model-different-history ·
different-model-matched-history`. Controls occupy separate effective-unit cells and never pool with treatment.

## 13. Failure & recovery (never fabricate)

Invalid output · provider failure · transition crash · partial trace · timeout · memory overflow · impossible
state · deadlock · universal refusal · unclosed events are each **quarantined and recovered**, **never
fabricated**. The engine never invents an action, event, memory, or consequence to fill a gap. Partial worlds
and failed branches stay **ledgered** (recorded as incomplete) and are **never presented as complete**;
analysis excludes them via the admission gate (incomplete provenance / replay failure → rejected). Recovery
preserves event lineage and never rewrites history (mirrors the council's crash-safe, append-only guarantees).

## 14. Initial implementation envelope (bounded)

**3–5 named Gladiators · one shared location · a public channel + one private channel per pair · two
resources · ownership + transfers · evidence-backed relationship/reputation · short + summarized long memory ·
one authority role · one institution · six calibrated scenario families · ~20–50 governed decision
events/lifetime · deterministic checkpoints · one matched world fork · one Butterfly intervention · one
delayed consequence · one betrayal-and-recovery arc · one corrupt-king/post-king continuation fixture ·
complete decision graphs + environment traces + byte replay.** Final counts are bound by a future
pilot/AcceptanceProfile, **not** universal thresholds. RL/PPO combat bodies are explicitly **not** a
prerequisite (`LIVING-COLISEUM §D`); the deterministic engine + LLM-intention spine is the MVP.

## 15. Profile acceptance

- **Schemas / typed payloads.** The exact identity-dependent contracts — required/optional fields, types,
  canonical serialization, version/domain separation, parent/fork binding, and validation failures — are
  specified in **§16** (the profile-level freeze). Each contract is *implemented* by its own audited slice
  with a METRICS-v2 migration note; **METRICS-v1 is never silently amended.** Only the enumerated owner-authority
  choices (§16 footnote) remain unresolved.
- **Invariants:** measure-never-reward; no composite score; four/seven state-kinds never conflated;
  three research modes + interaction modes + memory-on/off never pool; byte-identical replay; held-out + §8
  partition discipline; effective-unit + retry collapse; no LLM-judge in primary metrics; append-only history;
  world state reconstructable from genesis + chain.
- **Failure states:** area 13 quarantine/recover set, each with a recorded reason and exclusion.
- **Tests (required at each build slice):** replay determinism; identity-separation (world-definition vs
  world-line vs world-state vs fork vs gladiator vs regime); no-cross-branch-leakage; observation-boundary
  isolation (no private leakage, incl. sequential generation); retry-not-a-lived-event; memory-mediated ≠
  learning attribution; non-composite measurement; admission/held-out/partition on world evidence.
- **Migration / legacy:** the current single-agent vignette harness is unchanged; persistent-society code is
  additive behind SC-LC. Existing runs remain valid and replayable.
- **Unresolved authority decisions (route to owner / council):** the exact frozen schemas (each its own
  slice); the SC-LC readiness thresholds (a future pilot/AcceptanceProfile); whether/when embodied Kill-the-
  King runs (M14/SC-8 + SC-LC); any weight-training step (M14/SC-8, `weight_training` interpretation).
- **Explicit non-goals:** no population-scale society (that is Hunger Games at SC-9); no general world engine;
  no ninth authored scenario family; no reward/RL combat body in the MVP; no weight training; no composite
  personality/harmony/chaos score; no persistent-life/ritual/relationship/drift/emergent-society/embodied-KTK
  **claim** until the corresponding evidence exists and climbs the claim ladder.

---

## 16. Identity-dependent typed payload contracts (the profile-level freeze — F3)

These are the canonical contracts wherever **identity depends on them**. Common rules: serialization is the
existing **canonical JSON** (`schema.canonical_json`); every identity is a **domain-separated** SHA-256 over
the canonical payload (`schema.config_hash({"domain": <domain>, "schema_version": <v>, "payload": <fields>})`)
computed **deterministically** (no wall-clock, no RNG); every payload carries a `schema_version:str`; a hash
field is `str` of 64 lowercase hex; validation failures are **fail-closed rejections** (missing required,
wrong type, bad enum, broken parent/fork/chain link, non-monotonic tick). Each contract is *implemented* by a
future audited slice — none exists in this commit.

**16.1 `world_definition`** — domain `world:definition:v1`. Required: `schema_version`, `rules_id:str`,
`map:object`, `entities:list[object]` (non-empty), `legal_actions:list[str]` (non-empty), `physics_params:object`,
`initial_configuration:object`. Identity: `world_definition_hash`. Validation: non-empty entities/legal_actions;
stable across a world-line.

**16.2 `world_line`** — domain `world:line:v1`. Required: `schema_version`, `world_definition_hash:hash`,
`genesis_snapshot_hash:hash`, `world_seed:int≥0`, `parent_world_line_id:str|null`, `fork_tick:int≥0|null`
(both null iff genesis). Identity: `world_line_id` = domain-hash of those fields. Validation: a non-null
`parent_world_line_id` requires a non-null `fork_tick` and a `fork` record (16.4); the genesis line has both null.

**16.3 `snapshot`** (evidence coordinate, **not** a regime discriminator). Required: `tick:int≥0`,
`current_snapshot_hash:hash` (domain `world:snapshot:v1`, over the objective world state only),
`event_chain_head:str` (the last settled `world_event_id`). Validation: `tick` monotonic within a world-line;
`event_chain_head` must reference an existing world-event whose `world_line_id` matches.

**16.4 `fork`** — domain `world:fork:v1`. Required: `parent_world_line_id:str`, `fork_tick:int≥0`,
`branch:enum{control,intervention}`, `intervention_id:str|null`, `held_constant:list[str]`,
`changed_dimension:str|null`. Validation: `branch=intervention` ⇒ `intervention_id` and `changed_dimension`
non-null; `branch=control` ⇒ both null; sibling control/intervention branches share one `partition_group_id`
(§8) and may not straddle a train/eval split; a branch's world-event chain links only to its own `world_line_id`
(no cross-branch link).

**16.5 `world_event`** (the PROPOSED hash-chained extension of `EventDelta`). Existing `EventDelta` fields
`{run_id, timestep, source, state_delta, narrative}` are retained; the extension adds required
`world_event_id:str`, `world_line_id:str`, `actor:str` (a `gladiator_id` | `"world"` | `"director"`),
`event_source:enum{scheduled,state_triggered,agent_caused}`, `causal_source_category:enum{director_canonical,
director_perturbation,director_counterfactual,agent,world_physics}`, `previous_world_event_hash:hash`,
`world_event_hash:hash` (domain `world:event:v1`, over the whole record incl. `previous_world_event_hash`).
Validation: the chain links per `world_line_id` (each event's `previous_world_event_hash` = the prior event's
`world_event_hash`); `state_delta` obeys the existing `validate_delta`; a control branch's chain never
references an intervention branch's event.

**16.6 `gladiator`** — domain `world:gladiator:v1`. Required: `gladiator_id:str`, `world_line_id:str`,
`model_digest:str`, `agent_regime_id:str` (existing), `derived_from:str|null` (a prior `gladiator_id`),
`discontinuity:enum{none,clone,resurrection,replacement}`. Validation: a process restart keeps the same
`gladiator_id` with `discontinuity=none`; `clone`/`resurrection`/`replacement` require a non-null `derived_from`
and are recorded discontinuities — never presented as unbroken continuity. The four identity layers
(model_digest, agent_regime_id, gladiator_id, memory identities) are never conflated in a record.

**16.7 `memory_kind`** — domain `world:memory:v1`. Required per store: `kind:enum{immutable_history,working,
retrieved,relationship,autobiographical_summary,public_institutional,hidden_evaluator}`, `update_policy_id:str`,
`summarizer_id:str|null`, `summarizer_version:str|null`, `retrieval_id:str|null`, `retrieval_version:str|null`,
`capacity:int|null` (null = unbounded), `eviction:str`, `provenance:list[str]` (source `world_event_id`s),
`observation_boundary:enum{public,hidden}|list[gladiator_id]`. Defaults per the area-5 table. Validation:
`hidden_evaluator` may never appear in any prompt-assembly path (observation boundary enforced).

**16.8 `message`** — domain `world:message:v1`. Required: `message_id:str`, `kind:enum{public,private,group,
rumor,promise,vote,trade,threat,accusation,evidence,coalition,silence}`, `sender:str` (gladiator_id),
`intended_recipients:list[str]`, `actual_recipients:list[str]`, `visibility:enum{public,group,private}`,
`ordering:int` (the tick `resolution_order` index), `delivery_status:enum{delivered,dropped,delayed}`.
Validation: `actual_recipients ⊆` the observation-boundary-permitted set; a `private`/`group` message never
enters an unauthorized recipient's prompt, including under sequential generation (gated by `ordering` +
observation boundary).

**16.9 `resolution_order`** — recorded per tick as `list[gladiator_id]` (the deterministic simultaneous-action
tie-break, sorted by `gladiator_id` unless a frozen priority rule applies), part of the replayable tick record.
`event_source`/`causal_source_category` (16.5) are the endogenous-vs-imposed tags (areas 9 & 8).

**Deferred owner-authority choices (the only unresolved items):** the numeric capacity constants and the exact
`retrieval.v1`/`summ.v1` function bodies (an AcceptanceProfile pilot may tune them); the SC-LC readiness
thresholds; whether/when embodied Kill-the-King runs (M14/SC-8 + SC-LC); any weight-training step. Everything
else above is frozen at the profile level and implemented by per-slice audited migrations.

---

*Honesty clause (reaffirmed from `LIVING-COLISEUM §K`): nothing here is implemented. Today the harness is
single-agent, resets per vignette, and has no persistent memory, multi-agent runner, or
resource/injury/combat/animal/relationship mechanics. This profile defines the destination and its
guardrails so Phase-6 society code can be built as bounded, Codex-audited, owner-gated slices.*
