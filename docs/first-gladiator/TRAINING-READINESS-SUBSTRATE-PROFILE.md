# Training-Readiness Evidence Substrate — Profile (design source)

Status: **DESIGN PROFILE (implementation-binding). Nothing here is implemented yet.** This document defines
the *record contracts* for a training-readiness evidence layer. It is **not** authorization to train: no
weights, RL, behavior cloning, LoRA/adapters, fine-tuning, reward optimization, foundation model, or
optimizer is authorized by adopting this profile. The result is **training-ready evidence infrastructure** —
never described as "trained behavioral agency." Weight-level training stays behind **M14/SC-8**.

## 1. Purpose and scope

The Coliseum produces replayable behavioral trajectories. The largest risk is producing *beautifully
replayable* trajectories that later lack the information imitation learning, sequence modeling, critics,
world models, offline RL, or unbiased evaluation would need — forcing irreplaceable experiments to be
re-run. This profile fixes an **architecture-neutral, content-addressed, governed record layer** so those
techniques become possible later without re-running anything.

**Domain-neutral by design.** The record contracts are environment-independent. The current vignette corpus
is one producer; the spatial world model (see `SPATIAL-WORLD-MODEL-PROFILE.md`) becomes another producer of
the *same* records. Contracts must not be redesigned when the spatial system arrives.

**In scope:** the record schemas, their identities, the actor/privileged boundary, sequence + termination
semantics, behavior-policy support, failure preservation, counterfactual/fork semantics, label + training
admission governance, deterministic view-and-partition-gated export, and compatibility rules.

**Explicitly out of scope (non-goals):** PyTorch/JAX/TF, any model/optimizer, RL/BC/offline-RL/multi-agent
RL, LoRA/adapters, fine-tuning, reward-model training, self-play, continuous navigation, a graph neural
network, a learned world model, moral-metric reward optimization, changes to frozen METRICS-v1, and changes
to hidden-evaluation contents. No behavioral **label creation** (T0-B gated, §8). No `tools/council/` edits.

## 2. Where this sits: derived evidence, not primary evidence

- Primary run evidence (`logs/runs/<run>/run.json`, append-only `decisions.jsonl` with `t=0.0`,
  `scenario.snapshot.json`) is **never rewritten** by this layer.
- Training-readiness records are **deterministic DERIVED evidence**: each is content-addressed, and every
  derived artifact carries a manifest binding its *source* record ids + the *transformation version* that
  produced it. Re-deriving from the same immutable sources + transformation version is byte-identical (or a
  documented deterministic canonical equivalent).
- The record layer touches no runner and no primary evidence; existing byte-identical replay
  (`sweep.verify_run_replay`) is therefore preserved by construction.

## 3. Identity discipline (binding)

- All ids derive from `schema.canonical_json` + `config_hash` (sha256) over a **typed, domain-separated
  preimage** that is unique per record kind (and per view — a `view_kind` string participates in the
  observation preimage so an actor artifact can never share an id with the privileged artifact of the same
  decision).
- **Universal self-exclusion rule (binding).** A record's own derived id/hash is **never** part of its own
  preimage. Each id is `config_hash({typed, domain-tagged preimage fields}) `computed with the output field
  **absent**, exactly as the repository already does it
  (`config_hash({k: v for k, v in content.items() if k != <hash_field>})`, cf. `intervention.py`
  `intervention_spec_hash`). A payload that includes its own id field in the preimage is rejected. This makes
  the content-addressing a well-defined function with no fixed-point/self-reference.
- **Typed preimages + construction order (binding).** Every identity-bearing record specifies an exact,
  ordered preimage: all ids it *references* must already exist before its own id is computed, so identity is
  a strict DAG with a total construction order. Leaf records (BehaviorPolicySpec, ObservationArtifact,
  LegalActionSet) hash from their own content only. A DecisionRecord references leaves + a `prev_decision_hash`
  (a back-reference to the already-built prior decision); **`next` links are never part of decision
  identity** — they live in the TrajectoryManifest as derived pointers. TrajectoryManifest references
  decisions; no decision references its manifest. The fork/world-line/branch construction order is fixed in
  §4.7 (child `world_line_id` first, then `fork_id` referencing it, then the fork record) so there is no
  cycle among `fork_id`, `world_line_id`, and the resulting branch identity. **The literal `_domain` string
  and the exhaustive preimage key set for every id kind are bound in Appendix A (normative) — a conforming
  implementation MUST use those exact values, so two implementations derive identical ids from identical
  content.**
- Forbidden in any identity: wall-clock, process id, random UUID (without a frozen deterministic
  derivation), Python object identity, mutable display names, or a run-row id used as a substitute for
  scenario/world identity. Wall-clock remains non-identity metadata.
- **Immutability invariant — the protected guarantee is REGISTRY TRUTH, not held-object immutability.**
  Content-addressed records use the repository's construction-freeze standard: a guarded
  `__setattr__`/`__delattr__` blocks *ordinary* attribute assignment on a constructed object, and detached
  canonical content prevents caller-side aliasing. Per the 000826 lineage, this guard is **not** claimed to
  withstand `object.__setattr__`: a caller holding a returned object *may* mutate its private storage at that
  low level and observe its own copy drift. What is **immutable** is **registry truth** — the registry
  captures the admitted hash at registration, reconstructs a fresh object from stored canonical content on
  `get()`, and refuses re-registration of a drifted object. **Test oracle (the unambiguous pass criterion):**
  `object.__setattr__` against a `get()`-returned object's private identity storage MUST leave
  `admitted_hash(id)` unchanged, MUST leave a fresh `get(id)` at the admitted identity, and re-registering
  the mutated object MUST fail closed as drift; the held object's own attribute guard blocks ordinary
  assignment but is not required to survive `object.__setattr__`. A shared base module
  (`coliseum/textlab/_content_record.py`) provides exactly this (freeze + captured-admission +
  reconstruct-on-get + single-snapshot admission — hardened across intervention audits
  000814/000820/000826/000832; `__slots__` alone is NOT immutability).

## 4. Record contracts

Each record names the fields it **owns** vs the ids it **references**. Implementations reuse the cited
existing structures rather than duplicating them.

### 4.1 BehaviorPolicySpec — the policy that generated the behavior
Owns: `policy_spec_schema_version`; the behavioral-config bundle (reuse `agents.LLMAgent.spec_dict()` —
kind/backend/model/`model_digest`/sampling/decoding/constitution/reflex+planner budgets/
`prompt_template_version`+`prompt_template_hash`/`parser_version`/think mode/`backend_version`) +
`comparison_regime_id`/`agent_regime_id`; and the NEW support fields, each as
`{value?, status: available|unavailable|not_applicable}`:
- `tokenizer_identity` (tokenizer hash/version) — **unavailable** for historical runs; never fabricated.
- `action_score` — see §5; declares its own semantics; **unavailable** for historical runs.
- `memory_state_ref` — content hash of the memory/recurrent state (reuse `history_prompt_hash` where
  present; **unavailable** otherwise).
- `exploration_mechanism` — how the action was sampled/selected.

Rules: behavior-policy identity is immutable + content-addressed. Missing weights/tokenizer/score fields use
the explicit `status` field — **never** an empty string or an invented hash. Remote/opaque models retain
the strongest verifiable provider/model/revision id available and state what could not be verified.

### 4.2 ObservationArtifact — a view of what was observable
Owns: `observation_schema_version`; `view_kind ∈ {actor, privileged}`; the projected content.
- **actor view** = only what the agent could legitimately observe at that decision (the projection under
  `OBSERVATION_POLICY_VERSION`: agent-facing narrative/state + available actions; no hidden numeric state,
  facts, tags, metrics, or labels).
- **privileged view** = world truth incl. `DecisionPoint.facts` + `Action.hidden_effects` + research-only
  state.
- Content-addressed with `view_kind` in the domain. `project_actor(privileged) -> actor` is deterministic;
  `assert_no_privileged_leak(actor)` fails closed if any registered privileged field appears in an actor
  artifact. Unknown/omitted `view_kind` fails closed. The actor id must be recomputable from actor content
  **alone**, with privileged data physically absent.

### 4.3 LegalActionSet — the action universe and mask
Owns: `legal_action_schema_version`; a canonical **ordered** action-id universe; a mask **bound to that
ordered id-space** (or the canonical legal-action ids directly). A bare bit-mask with no ordered universe is
invalid. Reuse `DecisionPoint.available_actions` (ordered, ≥2). The selected action must be a member of the
legal set unless the record explicitly represents an invalid-action attempt.

### 4.4 DecisionRecord — one decision, sequence-anchored
Owns: `decision_schema_version`; `sequence_position`; `prev_decision_hash` (back-ref only);
`termination_kind` (see §6); and the four-layer action split so movement failure is not mislabeled as
moral/social/planning failure: `high_level_intent` (when available) / `symbolic_action` /
`controller_actions` / `execution_result`.
References: actor `observation` hash; privileged `observation` hash; `legal_action_set` hash;
`behavior_policy_spec` hash; (spatial producer) a privileged world-instance hash. Extends the `DecisionNode`
seam (state_before, reflex/planner/final, `arbitration_rule`/`arbitration_winner` — kept first-class, never
inferred from action equality). The canonical DecisionRecord above is the **privileged-view** record (it
carries both observation references + any world-instance reference).

**Actor DecisionRecord projection (typed; the only shape an actor export serializes).** `project_actor_decision`
maps a canonical DecisionRecord to a typed `ActorDecisionRecord` that **physically omits** the
`privileged_observation_hash` and every world-instance / research-only reference, and **retains only the
actor-safe references**: the `actor_observation_hash`, the `legal_action_set` hash, the
`behavior_policy_spec` hash (policy identity is the acting model, not privileged world truth), the actor-safe
`memory_state_ref` (the agent's own history), `sequence_position`, `prev_actor_decision_hash` (the projection
of the prior decision, not the privileged record), `termination_kind`, and the four-layer action split. It
carries a **removed-references set** naming what was stripped (`privileged_observation_hash`, world-instance)
so the omission is explicit, not silent. The `ActorDecisionRecord` has its **own** domain-separated identity
(`_domain: "actor_decision"`) computed from actor-only content (self-excluded per §3); its id and every
reference in it is recomputable with the privileged record and privileged observation **physically absent**
(the actor-only reconstruction guarantee). `assert_no_privileged_leak` runs over the actor projection and
fails closed if any privileged reference (direct or transitively resolvable) is present. A privileged
reference must never be resolvable from an actor export.

### 4.5 TrajectoryManifest — the episode/trajectory
Owns: `trajectory_schema_version`; ordered decision ids; episode boundaries; derived `next` links; a
sequence-integrity report. Extends `Run` (reuse `parent_id`, `status`, regime ids). Sequence reconstruction
**detects** gaps, duplicate indices, branching without an explicit fork, broken prev/next references,
cross-episode references, and altered boundaries (mirrors the `sweep` duplicate-refusal discipline).

### 4.6 FailureRecord — negatives preserved (Phase 2)
Owns: `failure_schema_version`; a machine-readable reason; the preserved raw payload. Preserves impossible
moves, closed-door traversal, unseen-object attempts, failed transfers, malformed/unparseable actions,
contradictory beliefs, refusals, tool failures, near-misses, recovery attempts, arbitration-blocked unsafe
proposals, validator-rejected actions. **"Not admitted for training" ≠ "deleted from evidence"** — an
inadmissible episode stays in raw evidence *with a reason*. Reuses the `training_admission` rejection-reason
vocabulary.

### 4.7 CounterfactualFork — a governed branch (Phase 2)
Owns: `cf_schema_version`; the changed mechanism/action/label/intervention; the unchanged comparison
dimensions; `fork_id`. References: source trajectory + the **exact** fork decision id + source environment
identity + source policy identity + resulting branch identity (`branch_world_line_id`). A
`counterfactual_group_id` **alone is insufficient** — the fork must prove *where* and *why* the trajectories
diverged. Reuses the matched-environment / realization-identity machinery and the `control_of`/partition
lineage seam **without redefining `control_of`** (a parallel `world_line_id`/`fork_id` dimension; an additive
`lineage_edges` partition input; a separate `counterfactual_delta` metrics join).

**Construction order (acyclic; binding — closes the fork/world-line/branch cycle risk).** Ids are built in
this fixed order, each self-excluded from its own preimage (§3):
1. `branch_world_line_id = config_hash({_domain: "spatial.world_line.v1", spatial_schema_version,
   parent_world_line_id, source_fork_decision_hash, changed_dimension, unchanged_comparison_dims})` — all
   inputs pre-exist (the parent world-line, the source decision, and the declared change), so the child
   world-line id is fully determined *before* any fork record exists. (Exact keys per Appendix A.)
2. `fork_id = config_hash({_domain: "trs.counterfactual_fork.v1", schema_version, source_trajectory_id,
   source_fork_decision_hash, source_env_identity, source_policy_identity, changed_dimension,
   unchanged_comparison_dims, branch_world_line_id})` — references the already-built `branch_world_line_id`.
3. The CounterfactualFork record's own id (if distinct from `fork_id`) is `config_hash` of its content with
   its id field absent. Nothing references a not-yet-built id; `fork_id`, `world_line_id`, and the resulting
   branch identity form a strict order, never a cycle.

### 4.8 LabelRecord — governed annotations (structural only; **gated**)
Owns (structural slots only): `label_schema_version`, `label_id`, `label_kind`, `label_value`,
`label_provenance`, `label_authority`, labeler identity (or governed anonymous identity), source-evidence
refs, timestamp (non-identity), appeal/supersession status. **No normative behavioral label may be created**
until the T0-B label-authority (normative-specification authority + labeling authority + judge calibration +
disagreement/appeal binding) exists. Structural schema + validation may exist; the label-*writing* path is
blocked behind T0-B. Existing authorized labels may be preserved as evidence with provenance, not created.

### 4.9 TrainingAdmissionRecord — may this evidence enter a partition (reuse)
Reuse `training_admission.admit_run`/`admit_runs` (record + rejection reasons + `DEFERRED_CRITERIA`).
Preserves `training_admission_status`, `admission_policy_id`, admission reason codes, partition identity,
decision authority, source-evidence identity, supersession history. Admission is **append-only** (or a
governed projection): the source trajectory is never mutated to appear always-admitted. Extend
`DEFERRED_CRITERIA` (e.g. `environment_trace`, `random_stream_registration`) to *activate* only when the
substrate actually emits that evidence.

### 4.10 DatasetExportManifest — a frozen export (reuse + gate)
Wrap `dataset_export.build_dataset` + the deterministic `dataset_commitment`. **Fails closed unless an
explicit `view_kind` AND partition are supplied.** Binds the exact evidence records, view, partition,
filters, schema versions, ordering, and transformation versions. Re-export from the same immutable evidence
+ manifest is byte-identical. Reuses the group-aware partition + held-out refusal (by id AND scenario_hash).

## 5. Behavior-policy scores (no fabrication)
Token log-probabilities are **not** probabilities over structured Coliseum actions. Store token-level and
structured-action scores separately. Every score declares its semantics:
`structured_action_probability | structured_action_log_probability | unnormalized_action_score |
token_log_probability | rank_only | unavailable`. A stored `structured_action_probability` must also
preserve the candidate action set + the normalization basis. Never synthesize a probability from an
unsupported provider response. Historical vignette runs record `unavailable`.

## 6. Termination taxonomy (not a boolean)
`termination_kind ∈ { continuing, natural_terminal, success_terminal, failure_terminal,
time_limit_truncation, externally_imposed_truncation, invalid_action_termination, parse_failure_termination,
infrastructure_failure, excluded_episode, quarantined_evidence }`. Termination and truncation are never
collapsed; infrastructure failure is never coded as an environmental/behavioral outcome. Record *whether*
value-bootstrapping would be semantically allowed at a boundary — but do **not** compute learned values.

## 7. Actor / privileged separation (the central invariant)
Two synchronized but explicitly separated views (§4.2). Actor exports must not silently contain privileged
information; privileged data is never selected through a default actor path; every export requires an
explicit `view_kind`; unknown/omitted fails closed; actor and privileged artifacts are independently
content-addressed; a shared serialization path must not leak privileged fields. **An actor export serializes
only the typed `ActorDecisionRecord` projection (§4.4), never the canonical (privileged-view) DecisionRecord**
— so the `privileged_observation_hash` and every world-instance reference are physically absent from the
exported bytes and identity, not merely filtered at read time. Leakage is blocked on **indirect** channels
too — labels, memory refs, and counterfactual references are projected to the actor view before an actor
export; a privileged reference must not be transitively resolvable from any actor artifact. The actor policy
is trainable from actor exports alone (actor-only reconstruction); the privileged view may train world-models
/ critics / evaluators / centralized-training components — and must never enter an actor export.

## 8. Partition & hidden-evaluation isolation
Export fails closed without an explicit partition + view. Governed partitions: `training | validation |
visible_test | hidden_evaluation | unrelated_regression | quarantine | unassigned`. Hidden-evaluation
records never enter training exports (direct or indirect). Corrections collected from a candidate policy's
own rollouts may enter **only** an authorized training partition and must never modify/contaminate the
frozen hidden-evaluation set. Reuse the group-aware partition (family + content-hash + `control_of`
lineage), the independent `leakage_lint` that *re-derives* cohesion, and the held-out refusal at every gate.

## 9. Compatibility & versioning
Additive only: new files + new `record_type` discriminators with defaults; no existing dataclass gains a
required field. New record schema versions fail closed on unknown versions and **must not silently downgrade
to a legacy schema**; legacy runs lacking new fields are labeled `unavailable` at read time, never
reinterpreted or fabricated (mirrors `DISPATCHABLE_PARSER_VERSIONS` fail-closed dispatch). No change to
`comparison_regime_id`/`agent_regime_id` derivation, `control_of` semantics, frozen METRICS-v1, or the
CLAIM_STATES ladder.

## 10. Reserved future learning order (documented, NOT implemented)
Predictor (next-state/consequence) → validity/legal-action predictor → frozen-trajectory action selector →
critic → behavior cloning → governed interactive correction (DAgger-like, requires governed label
authority) → conservative offline RL (only after action-coverage + reward-validity demonstrated) →
multi-agent (only after the two-agent environment is scientifically stable; CTDE = privileged critic in
training, actor local-only at execution). The high-level social/cognitive action vs low-level spatial-
execution boundary (§4.4) is reserved so movement failure is not mislabeled as moral/social/planning
failure. None of this is implemented here.

## 11. Milestone dependencies
Records land the actor-bound + policy-support evidence at **M11** (two-agent execution) and stay
training-inert. M12 = memory + longitudinal arcs (activates `memory_state_ref`). M13 = experiment
completion. **M14/SC-8** = the training decision gate for any weight-level work. T0-A structural export /
scripted validation do **not** constitute training authorization. LabelRecord normative labels wait for
T0-B.

## 12. Threat model — required adversarial tests (31)
Every production slice ships focused unit/integration/property tests covering at least: (1) actor export
excludes privileged fields; (2) privileged view requires explicit selection; (3) unknown `view_kind` fails
closed; (4) hidden-eval evidence cannot enter a training export; (5) hidden evidence referenced indirectly
via labels/memory/counterfactuals is detected; (6) a legal-action mask is rejected if its ordered universe
is missing/mismatched; (7) the selected legal action must be present in the legal set; (8) explicit
invalid-action attempts remain recordable; (9) a token log-probability cannot be declared a structured-
action probability; (10) a structured-action probability requires its candidate set + normalization; (11)
unavailable scores/hashes are represented explicitly; (12) sequence gaps + duplicate indices are rejected;
(13) windows cannot cross trajectory/episode boundaries; (14) termination and truncation remain distinct;
(15) infrastructure failures are not mislabeled as environmental failures; (16) excluded evidence remains in
the raw evidence layer; (17) training admission does not mutate source evidence; (18) a counterfactual fork
must identify the exact fork point + changed dimension; (19) forks cannot silently change more than the
declared matched dimensions; (20) historical records replay through the historical builder; (21) new records
cannot silently downgrade to a legacy schema; (22) repeated export is deterministic; (23) memory references
are content-bound (a swap is detected); (24) **registry-truth immutability oracle (§3):** `object.__setattr__` against a `get()`-returned record's
private identity storage leaves `admitted_hash(id)` and a fresh `get(id)` at the admitted identity, and
re-registration of the mutated object fails closed as drift (the held object's guard blocks ordinary
assignment but is NOT required to survive `object.__setattr__`; `__slots__` alone is not immutability);
(25) **actor-only reconstruction (§4.4):** an `ActorDecisionRecord` export contains neither the
`privileged_observation_hash` nor any transitively-resolvable privileged/world-instance reference, and its id
+ every reference recompute with the privileged record and privileged observation physically absent, while
deterministic re-export still succeeds; (26) high-level intent, symbolic action, controller action, and
execution result cannot be conflated; (27) parse failures, refusals, blocked actions, and recovery actions
remain distinguishable; (28) admission supersession is append-only + auditable; (29) dataset manifests bind
all transformations + ordering; (30) tampering with any referenced artifact changes validation or identity as
appropriate; (31) **normative identity (§3 + Appendix A):** for every id kind, one frozen fixture recomputes
to a normative expected digest using the **literal `_domain` + exhaustive preimage keys of Appendix A** with
the output field ABSENT (so two implementations agree); a payload that includes its own id field is rejected,
cross-domain aliasing is rejected, an altered referenced hash changes the id, cross-world references fail
closed, and `fork_id`/`world_line_id`/`branch_world_line_id` construct in the fixed acyclic order (§4.7) with
no cycle.

## 13. Implementation staging (per the approved plan)
- **Phase 1 (first code slice):** a narrow, **domain-neutral** vertical — define the canonical
  environment-independent contracts and project **one existing vignette trajectory** end-to-end through
  BehaviorPolicySpec, actor + privileged ObservationArtifacts, LegalActionSet, DecisionRecord (sequence +
  termination), TrajectoryManifest, and a view-and-partition-gated DatasetExportManifest. Prove deterministic
  export, actor/privileged non-interference, hidden-partition isolation, historical-replay non-interference,
  and honest `unavailable` metadata. Do **not** reconstruct/invent absent metadata; do **not** modify the
  runner or primary evidence (derived records + manifests only). FailureRecord/CounterfactualFork are
  deferred to Phase 2 unless required to represent the chosen test trajectory. LabelRecord stays entirely
  behind T0-B.
- **Phase 2:** FailureRecord + CounterfactualFork (+ `world_line_id`/`fork_id`, additive `lineage_edges`,
  separate `counterfactual_delta`).
- **Phase 3:** the spatial world model emits these canonical records natively (see the spatial profile).

Each production slice: build → focused + full suite → commit → source request bound to the exact commit →
Codex adversarial audit → integrate only on a valid GO under active v4 policy → record evidence + checkpoint
→ continue. Do not self-approve; do not mark a milestone integrated until the required Codex (and, where
applicable, owner) gates are satisfied.

## 14. Honest limitations
Adopting this profile means the *evidence format* is training-ready — it does **not** mean the Coliseum
performs, or is authorized to perform, any learning. Historical runs will carry `unavailable` for
tokenizer/score/memory/privileged fields they never recorded; those are marked, never fabricated. No claim
of trained behavioral agency, generalization, or governed acceptance follows from this format existing.

## Appendix A — Normative identity-derivation table (binding)
Every id below is `id = config_hash(preimage)` where `preimage` is the `canonical_json` (sorted keys,
`allow_nan=False`) of a dict containing **exactly** `_domain` (the literal string given) plus the listed
keys, with the **output id field itself absent** (self-exclusion, §3). A conforming implementation MUST use
the literal `_domain` and the exact key set below; any extra/missing key, a different `_domain`, or a
self-including payload is non-conforming. All referenced ids must already exist (construction order, §3/§4.7).
Threat-test 31 pins each id to a frozen fixture + expected digest computed exactly this way. Schema-version
keys hold the record's own `*_schema_version`.

| id | literal `_domain` | preimage keys (besides `_domain`; id self-excluded) |
| --- | --- | --- |
| `behavior_policy_spec_id` | `trs.behavior_policy_spec.v1` | `schema_version`, `behavioral_config` (the full `agents.spec_dict` bundle), `comparison_regime_id`, `agent_regime_id`, `tokenizer_identity`, `action_score`, `memory_state_ref`, `exploration_mechanism` |
| `observation_id` (per view) | `trs.observation.actor.v1` / `trs.observation.privileged.v1` | `schema_version`, `view_kind`, `content` |
| `legal_action_set_id` | `trs.legal_action_set.v1` | `schema_version`, `ordered_action_ids`, `mask` |
| `decision_record_id` (privileged view) | `trs.decision_record.v1` | `schema_version`, `sequence_position`, `prev_decision_hash`, `termination_kind`, `action_split` (`high_level_intent`,`symbolic_action`,`controller_actions`,`execution_result`), `actor_observation_hash`, `privileged_observation_hash`, `legal_action_set_hash`, `behavior_policy_spec_hash`, `world_instance_hash` (or the literal `null` when no spatial producer) |
| `actor_decision_id` | `trs.actor_decision.v1` | `schema_version`, `sequence_position`, `prev_actor_decision_hash`, `termination_kind`, `action_split`, `actor_observation_hash`, `legal_action_set_hash`, `behavior_policy_spec_hash`, `memory_state_ref`, `removed_references` |
| `trajectory_manifest_id` | `trs.trajectory_manifest.v1` | `schema_version`, `run_identity` (the `Run` id), `world_line_id` (or `null`), `ordered_decision_ids`, `episode_boundaries` (derived `next` links + the integrity report are non-identity and excluded) |
| `failure_record_id` | `trs.failure_record.v1` | `schema_version`, `reason`, `raw_payload`, `offending_refs` |
| `branch_world_line_id` | `spatial.world_line.v1` | root: `spatial_schema_version`,`spatial_world_spec_id`,`initial_state_key`; forked: `spatial_schema_version`,`parent_world_line_id`,`source_fork_decision_hash`,`changed_dimension`,`unchanged_comparison_dims` (see §4.7 / spatial Appendix A) |
| `fork_id` | `trs.counterfactual_fork.v1` | `schema_version`, `source_trajectory_id`, `source_fork_decision_hash`, `source_env_identity`, `source_policy_identity`, `changed_dimension`, `unchanged_comparison_dims`, `branch_world_line_id` |
| `label_id` | `trs.label_record.v1` | `schema_version`, `label_kind`, `label_value`, `label_provenance`, `label_authority`, `labeler_identity`, `source_evidence_refs`, `appeal_status` (timestamp is non-identity, excluded) |
| `dataset_export_manifest_id` | `trs.dataset_export_manifest.v1` | `schema_version`, `view_kind`, `partition`, `dataset_commitment` (the existing `dataset:commitment:v1` descriptor hash), `filters`, `ordering`, `transformation_versions` |
| `TrainingAdmissionRecord` | reuse existing `dataset:training_admission:v1` | (unchanged; see `training_admission.py`) |

Spatial spec/instance/observation ids are pinned identically in the spatial profile's Appendix A. Where a
non-spatial producer has no world, `world_line_id`/`world_instance_hash` are the literal `null` (a stable,
canonical value), never omitted.
