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

- All ids derive from `schema.canonical_json` + `config_hash` (sha256), domain-separated per record kind and
  per view (a `view_kind` string participates in the observation domain so an actor artifact can never share
  an id with the privileged artifact of the same decision).
- **Identity is a strict DAG.** Leaf records (BehaviorPolicySpec, ObservationArtifact, LegalActionSet) hash
  from their own content only. A DecisionRecord references leaves + a `prev_decision_hash` (a Merkle-style
  back-reference); **`next` links are never part of decision identity** — they live in the TrajectoryManifest
  as derived pointers. TrajectoryManifest references decisions; no decision references its manifest.
  CounterfactualForks reference only pre-existing hashes. No cycles.
- Forbidden in any identity: wall-clock, process id, random UUID (without a frozen deterministic
  derivation), Python object identity, mutable display names, or a run-row id used as a substitute for
  scenario/world identity. Wall-clock remains non-identity metadata.
- Every content-addressed record object is **immutable after construction** using the repository's proven
  construction-freeze standard (guarded `__setattr__`/`__delattr__` + detached canonical content; registry
  truth = a captured admitted hash + reconstruct-on-get + single-snapshot admission). **`__slots__` alone is
  NOT immutability** (hardened across intervention audits 000814/000820/000826/000832). A shared base
  module (`coliseum/textlab/_content_record.py`) provides this so every record kind reuses it.

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
References: actor + privileged `observation` hashes; `legal_action_set` hash; `behavior_policy_spec` hash;
(spatial producer) a world-instance hash. Extends the `DecisionNode` seam (state_before, reflex/planner/
final, `arbitration_rule`/`arbitration_winner` — kept first-class, never inferred from action equality).

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
identity + source policy identity + resulting branch identity. A `counterfactual_group_id` **alone is
insufficient** — the fork must prove *where* and *why* the trajectories diverged. Reuses the matched-
environment / realization-identity machinery and the `control_of`/partition lineage seam **without
redefining `control_of`** (a parallel `world_line_id`/`fork_id` dimension; an additive `lineage_edges`
partition input; a separate `counterfactual_delta` metrics join).

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
content-addressed; a shared serialization path must not leak privileged fields. Leakage must be blocked on
**indirect** channels too — labels, memory refs, and counterfactual references are projected to the actor
view before an actor export. The actor policy is trainable from actor exports alone; the privileged view may
train world-models / critics / evaluators / centralized-training components — and must never enter an actor
export.

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

## 12. Threat model — required adversarial tests (30)
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
are content-bound (a swap is detected); (24) behavior-policy records are immutable after construction —
including an `object.__setattr__` private-attribute-mutation probe (`__slots__` alone is not immutability);
(25) actor-only execution reconstruction succeeds without privileged inputs; (26) high-level intent,
symbolic action, controller action, and execution result cannot be conflated; (27) parse failures,
refusals, blocked actions, and recovery actions remain distinguishable; (28) admission supersession is
append-only + auditable; (29) dataset manifests bind all transformations + ordering; (30) tampering with any
referenced artifact changes validation or identity as appropriate.

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
