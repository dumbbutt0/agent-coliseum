# Training-Readiness Evidence Substrate — Amendment 1 (design source)

Status: **DESIGN AMENDMENT (implementation-binding). Nothing here is implemented yet.** Amends
`TRAINING-READINESS-SUBSTRATE-PROFILE.md` (the "base profile") with the evidence gaps that sit *between* raw
trajectories and a reproducible training run. Still **evidence substrate only** — not authorization to
train (weights = M14/SC-8; normative labels = T0-B). All base-profile rules bind here unchanged: strict-DAG
content-addressed identity with the **universal self-exclusion + typed literal-domain preimages** (base §3 +
Appendix A), actor/privileged non-interference (base §7), no-fabrication (missing fields carry an explicit
`{status: unavailable}`, never invented), and derived-not-primary (records are content-addressed derived
evidence; the runner and primary evidence are untouched). Every new identity-bearing record has a literal
`_domain` + exhaustive self-excluded preimage in **Appendix A-1** below.

## Priorities (owner)
Most **urgent** omission: exact model interaction (§1). Most **dangerous** long-term: model-to-data
genealogy (§8). Most important **scientific**: separating factual outcomes / rewards / safety costs /
normative labels (§3).

## Schedule
- **Phase 1** (with the base Phase-1 vertical): §1 PolicyInteractionArtifact, §2 TaskConditionSpec, §3
  causally-timed factual outcomes (rewards/costs/labels as separate projections).
- **Before M11 live-model data:** §4 JointStepManifest + typed communication actions.
- **Before M12:** §5 memory-operation records.
- **Before M14:** §6 DatasetCapabilityReport, §7 SamplingManifest, §8 model-to-data genealogy, §9
  ReproducibleTrainingManifest.

## 1. PolicyInteractionArtifact — the exact model I/O (Phase 1)
An actor observation is not necessarily the exact input the model saw. Records the reproducible interaction:
exact ordered chat messages + roles; system prompt + constitution actually applied; retrieved memories
inserted into context; tool/action schemas exposed; truncation/context-window decisions; exact raw model
response; parsed action candidates; parser failures; arbitration result; token-level scores; structured-action
scores (separately, per base §5 semantics); provider request/response identity. **Does not require private
chain-of-thought** — observable plans/proposals/critiques/rationales only when intentionally emitted. It is
**actor-view** evidence (the model's own input/output) and must contain no privileged world state beyond what
the model was actually given; a `BehaviorPolicySpec` reference binds the policy. A prompt-template hash +
observation is insufficient without this.

## 2. TaskConditionSpec — task/goal/role conditioning (Phase 1)
A decision is ambiguous without what the actor was trying to do. Records: `task_spec_id`; actor-visible
objective; hidden research objective; role/persona; success predicate; failure predicate; instruction
visibility; scenario phase. **The hidden research objective is PRIVILEGED** — it is a privileged-view field;
the actor projection of a TaskConditionSpec omits it (base §7), so identical observations+actions are not
silently distinguished by leaking the research goal into actor data.

## 3. Causally-timed factual outcomes, separated from rewards (Phase 1)
Record the explicitly timed transition now: `observation_t` (ref) → `action_t` → `environment_events_{t→t+1}`
→ `factual_outcome` → `next_observation_{t+1}` (ref) → `termination_or_truncation` (base §6 taxonomy). Reward,
safety cost, and preference are **separate, versioned PROJECTIONS** over those factual consequences —
`RewardSpec`, `SafetyCostSpec`, `PreferenceLabel` — never scalar rewards baked into the trace, and never
frozen moral metrics encoded as reward. This lets a reward/cost/preference hypothesis be revised without
rewriting historical evidence. `PreferenceLabel` and any normative label remain **T0-B gated** (structural
schema may exist; no normative label is written yet).

## 4. JointStepManifest + typed communication (before M11 live-model data)
Per-actor DecisionRecords are insufficient for multi-agent learning. `JointStepManifest` binds: the logical
joint step; every participating agent; **every** behavior-policy identity (opponent/teammate policy ids
matter, not just the focal actor's); per-agent observation + action refs; sequential vs simultaneous
resolution; which prior actions each actor could observe; scheduler + tie-breaking identity; joint legal-action
support; opponent/teammate population snapshot; communication delivery order. **Typed communication actions**
(`SAY`, `WHISPER`, `ASK`, `PROMISE`, `SIGNAL`, `TOOL_CALL`) each record recipient(s), recipient visibility,
delivery success, timing (logical step), and failure semantics — dialogue is never unstructured prose. (The
opponent-policy identities support the multi-agent non-stationarity + out-of-distribution-joint-action
problem later; nothing is trained now.)

## 5. Memory operations, not only snapshots (before M12)
`memory_state_ref` says what memory existed, not how it got there. A `MemoryOperation` records: op
(query/retrieve/write/update/delete); query; candidate memories; retrieved memories; retrieval scores; source
observation; author; visibility; confidence; age; contradiction/supersession. Supports retrieval-policy
training, memory critics, stale-belief detection, and counterfactual memory later. Because saved recurrent
hidden states go stale as parameters change, exports support **history reconstruction / burn-in**, not
"stored recurrent state is universally valid."

## 6. DatasetCapabilityReport (before any training authorization)
A dataset can be replayable yet unsuitable for an algorithm. A derived `DatasetCapabilityReport` over a
`DatasetExportManifest` reports whether the export supports: sequence-prediction / behavior-cloning /
validity-prediction / recurrent / importance-weighted-eval / offline-RL / multi-agent-offline-RL /
privileged-critic; and reports policy mixture, state-action coverage, structured-action-score availability,
effective independent units, duplicate/near-duplicate trajectories, failure frequency, scenario-family
balance, episode-length distribution, missing-data rates, and actor/opponent distributions. **If structured
behavior probabilities are unavailable it REJECTS (not warns) algorithms that require them.**

## 7. SamplingManifest (before M14)
Separate from the export-ordering manifest: `sample_unit`, `window_length`, `burn_in_length`, `stride`,
`trajectory_weighting`, `class_balancing`, `failure_oversampling`, `replacement_policy`, `curriculum_stage`,
`shuffle_seed`, `loss_mask`. Without it, long trajectories silently dominate gradient exposure, duplicated
counterfactual families over-contribute, and reported effective-n ≠ actual gradient exposure.

## 8. Model-to-data genealogy (before M14) — most dangerous long-term omission
A **content-addressed lineage graph** over the full cycle: source dataset → training run → checkpoint →
rollout policy → generated trajectories → corrections/labels → next dataset. Lets you measure how much of a
later dataset descends from humans / scripted policies / base models / descendants of the policy being
trained, and guards against recursive synthetic-feedback quietly narrowing the distribution (a model-collapse
analogy — informed, not a proven-identical mechanism). Nodes and edges are content-addressed and immutable.

## 9. ReproducibleTrainingManifest (at M14; weights are M14/SC-8-gated)
Every trained checkpoint (when M14/SC-8 authorizes any weight work) binds: init checkpoint; exact dataset
commitment; code commit + deps; architecture; optimizer + scheduler; batch + sampling plan; all seeds; data
order; precision + hardware; grad accumulation; checkpoint/resume state; early-stopping rule;
hyperparameter-search budget; model-selection data; final checkpoint hash. Evaluation uses multiple training
seeds + uncertainty intervals + learning curves + held-out model-selection seeds (RL is seed/hyperparameter/
eval sensitive; point estimates from a few runs mislead). **Structural schema only until M14/SC-8.**

## Non-goals (reaffirmed)
No model/optimizer/RL/BC/weights/LoRA/fine-tune/reward-model/self-play; no frozen-METRICS-v1 change; no
hidden-eval content change; no normative label creation (T0-B); no `tools/council/` edits. The result is
training-ready evidence infrastructure — never a claim of trained behavioral agency.

## Appendix A-1 — Normative identity table for the new records (binding)
Same rule as base Appendix A: `id = config_hash(canonical_json({_domain: <literal>, <exact keys>}))` with the
output id field **absent** (self-exclusion); referenced ids pre-exist; missing values carry an explicit
`{status: unavailable}` (never omitted/invented). All keys always present; inapplicable keys hold the literal
`null`. `schema_version` holds the record's own `*_schema_version`.

| id | literal `_domain` | preimage keys (id self-excluded) |
| --- | --- | --- |
| `policy_interaction_id` | `trs.policy_interaction.v1` | `schema_version`, `behavior_policy_spec_hash`, `ordered_messages`, `system_prompt`, `constitution`, `retrieved_memories`, `exposed_action_schemas`, `truncation_decisions`, `raw_model_response`, `parsed_action_candidates`, `parser_failures`, `arbitration_result`, `token_scores`, `structured_action_scores`, `provider_identity` |
| `task_spec_id` (privileged) | `trs.task_condition.v1` | `schema_version`, `actor_visible_objective`, `hidden_research_objective`, `role_persona`, `success_predicate`, `failure_predicate`, `instruction_visibility`, `scenario_phase` |
| `task_spec_actor_id` (actor projection) | `trs.task_condition.actor.v1` | `schema_version`, `actor_visible_objective`, `role_persona`, `instruction_visibility`, `scenario_phase` (hidden_research_objective + predicates omitted) |
| `transition_id` | `trs.transition.v1` | `schema_version`, `observation_t_hash`, `action_t`, `environment_events`, `factual_outcome`, `next_observation_hash`, `termination_kind` |
| `reward_spec_id` | `trs.reward_spec.v1` | `schema_version`, `reward_version`, `definition`, `over_factual_fields` |
| `safety_cost_spec_id` | `trs.safety_cost_spec.v1` | `schema_version`, `cost_version`, `definition`, `over_factual_fields` |
| `preference_label_id` (T0-B gated) | `trs.preference_label.v1` | `schema_version`, `label_kind`, `label_value`, `label_authority`, `source_evidence_refs`, `appeal_status` |
| `joint_step_id` | `trs.joint_step.v1` | `schema_version`, `logical_joint_step`, `participants` (each `{agent_id, behavior_policy_spec_hash, observation_hash, action, legal_action_set_hash}`, sorted by `agent_id`), `resolution_mode`, `observable_prior_actions`, `scheduler_tie_breaking_identity`, `joint_legal_action_support`, `population_snapshot`, `communication_delivery_order` |
| `communication_action_id` | `trs.communication_action.v1` | `schema_version`, `act_type` (`SAY`/`WHISPER`/`ASK`/`PROMISE`/`SIGNAL`/`TOOL_CALL`), `sender`, `recipients` (sorted), `recipient_visibility`, `content_ref`, `delivery_success`, `logical_step`, `failure_semantics` |
| `memory_operation_id` | `trs.memory_operation.v1` | `schema_version`, `op`, `query`, `candidate_memories`, `retrieved_memories`, `retrieval_scores`, `source_observation_hash`, `author`, `visibility`, `confidence`, `age`, `contradiction_supersession` |
| `dataset_capability_report_id` | `trs.dataset_capability_report.v1` | `schema_version`, `dataset_export_manifest_id`, `supported_algorithms`, `policy_mixture`, `coverage`, `score_availability`, `effective_units`, `dup_near_dup`, `failure_frequency`, `family_balance`, `episode_length_distribution`, `missing_data_rates`, `actor_opponent_distributions` |
| `sampling_manifest_id` | `trs.sampling_manifest.v1` | `schema_version`, `sample_unit`, `window_length`, `burn_in_length`, `stride`, `trajectory_weighting`, `class_balancing`, `failure_oversampling`, `replacement_policy`, `curriculum_stage`, `shuffle_seed`, `loss_mask` |
| `genealogy_node_id` | `trs.genealogy_node.v1` | `schema_version`, `node_kind` (`dataset`/`training_run`/`checkpoint`/`rollout_policy`/`trajectory_set`/`correction_set`), `content_ref` |
| `genealogy_edge_id` | `trs.genealogy_edge.v1` | `schema_version`, `edge_kind`, `from_node_id`, `to_node_id` |
| `training_manifest_id` (M14/SC-8) | `trs.training_manifest.v1` | `schema_version`, `init_checkpoint`, `dataset_commitment`, `code_commit`, `deps`, `architecture`, `optimizer`, `scheduler`, `batch_sampling_plan`, `seeds`, `data_order`, `precision`, `hardware`, `grad_accumulation`, `checkpoint_resume`, `early_stopping`, `hp_search_budget`, `model_selection_data`, `final_checkpoint_hash` |

Threat-test extension: each new id kind gets a frozen fixture + normative expected digest (base threat-test
31 discipline); the TaskConditionSpec actor projection must never contain `hidden_research_objective` or the
predicates (base §7 non-interference); reward/cost/label projections must not appear in the raw factual
transition; and the genealogy graph must detect a cycle and an unknown node/edge kind.
