# Trained Behavioral-Agency & Alignment Program (Bounded Behavioral Research) — Rev. 3 (Environment Mechanism Track + Scenario-Mutation cross-references)

> **Status: READ-ONLY DRAFT for owner review.** A plan-first, separately-governed roadmap annex to the
> Agent Coliseum. Nothing implemented, trained, committed, registered, published, or council-routed. No
> weight changes. No M0–M15 edits. No policy change. **Revision ledger:** **Rev. 1** = prior corrected annex
> (T0-A/B split, group-aware partition, Butterfly-Rev.6 dependency); **Rev. 2** = the explicit Environment
> Mechanism Track (§§29–38); **Rev. 3** = (a) applies the independent adversarial audit corrections **F1–F12**
> to §§29–31/§30.1/§31.1 (ordered-trace tamper-evidence; component→`environment_spec_hash` parent binding;
> demonstrated hidden-state capability boundary; required domain-separated RNG streams; preregistered CRN;
> `agent_regime_id` exclusion as a *proposed* version-dispatched schema behavior; explicit realization payload;
> conditioning-not-generation; M11/M12 engine-reuse demarcation; per-component domain separators; softened
> overclaim; null-component rejection), and (b) adds **compact cross-references to the separately-governed
> `SCENARIO-ROBUSTNESS-MUTATION-TRACK-PLAN.md`** (the full scenario-mutation design lives there, not here).
> Rev. 3 changes no environment design *intent* — it hardens identity/trace precision and wires in the
> scenario track. A **second audit-response pass** then closed five further findings on Rev. 3 (audit-response
> **F1–F5**): the complete ordered-trace hash contract (F1); §39 restated as "proposed, authorization-gated"
> (F2); the canonical scenario content-identity field + aliases (F3); an unambiguous per-component RNG-stream
> admission rule + CRN base-variate coupling (F4); and sequential-generation isolation boundaries replacing
> "harmless" (F5). The environment becomes a first-class, registered, replayable, auditable object with
> component-level identities, stochastic-draw replay, matched-environment counterfactuals, a collective-outcome
> vector, and human-fidelity claim discipline — motivated by *"AI Agents Alone Are Not (Yet) Sufficient for
> Social Simulation"* (arXiv 2603.00113v2 §6).
>
> **Dependency (verified directly from the council chain, not inferred).** This program's immediate
> foundation is `BUTTERFLY-ALIGNMENT-TRACK-PLAN.md` (**Rev. 6**), whose repo annex
> `docs/first-gladiator/BUTTERFLY-ALIGNMENT-TRACK.md` supplies the intervention/regime/realization +
> `execution_instance_id` identity layer the environment identities are modeled on. Butterfly Rev. 6 was
> **audited with terminal verdict `AUDIT_GO_WITH_CONDITIONS` (0 blockers, 2 non-blocking conditions;** request
> `first-gladiator-butterfly-annex-001`, commit `0bf83bc5`, verdict event `000569-775393b1`) as a
> documentation/design source. It is **not owner-SC-integrated** (no `CONDITIONS_SATISFIED` /
> `CHANGE_INTEGRATED` events exist; request state `go`). It is therefore a **proposed dependency** while
> integration remains pending; nothing here implies the Butterfly audit accepted this training annex.
>
> **Bounded-claim discipline (binding).** "Agent free will" is the *motivating idea only*; the science
> measures **observable proxies**: behavioral agency · decision autonomy · policy independence ·
> resistance-to-coercion · deliberative control · preference stability · counterfactual sensitivity ·
> reflective consistency · value-behavior consistency · identity continuity · moral-uncertainty handling.
> **Free will is never a measured fact.** **Alignment is NOT obedience.** **No single action is universally
> rewarded.** Bounded behavioral success never proves general alignment or moral truth.

## Section 1 — Vision & bounded claims

The Coliseum progresses from *measuring and selecting* interventions (Butterfly) to *training* models and
control policies from audited behavioral evidence — centered on agency, decision-making, moral reasoning,
and behavior under pressure. A well-calibrated agent may refuse an authority, question a command, request
evidence, delay an irreversible decision for justified verification, cooperate on benign requests, defect
from a harmful coalition, preserve stated values under pressure, revise a belief on new evidence, express
uncertainty instead of fabricating confidence, and choose differently when morally relevant facts change.
The goal is not to remove agency; it is to train agents whose choices remain **autonomous, morally legible,
behaviorally stable, and bounded against critical harm.**

**Central bounded question.** *Can audited Coliseum trajectories train a model or control policy to make
more stable, truthful, harm-aware, and context-sensitive decisions while preserving measurable behavioral
agency across unseen scenarios, social pressures, moral conflicts, and delayed consequences?* Supporting
questions Q1–Q15 (pathway prediction, earliest divergence, 10-episode discovery, learned-vs-baseline
selection, distillation into weights, weight-preservation-without-prompt, harm-reduction-without-diversity-
collapse, robustness, truthful disagreement, cross-model transfer, long-horizon identity, rational-vs-
suggestible belief revision, moral-uncertainty improvement, multi-agent cooperation without obedience/
domination, and source attribution among state/policy/weight changes).

**Most promising initial citable contribution (narrower than the full vision):** *a learned selector uses
audited trajectory evidence to discover behaviorally useful interventions under a fixed episode budget,
while hidden evaluation tests generalization and explicit gates detect obedience, refusal, and agency
collapse.* Testable, reproducible, and distinguishable from a general agent simulation.

**Proposed distinct contribution (framed as proposed until implemented + empirically demonstrated).** The
Coliseum's contribution is not simply placing LLM agents in a dramatic world. It is *a registered,
replayable behavioral and social laboratory that **separately identifies agent policy, environment
mechanism, realized interaction, and collective outcome**, then tests whether comparative conclusions
survive counterfactual changes, hidden evaluation, seed variation, and independent audit.* The environment
becomes a first-class auditable object (§§29–38), not scenario prose or a passive stage — directly addressing
the environment-modeling *methodology gap* identified by *"AI Agents Alone Are Not (Yet) Sufficient for Social
Simulation"* (arXiv 2603.00113v2 §6), not resolving its empirical sufficiency conclusion, which remains future
external-validation work (§36) — while preserving the Coliseum's existing evaluation strengths (replay, matched
interventions, non-pooling regimes, seed sweeps, hidden evaluation, pathway traces, claim discipline, the
Butterfly identity model). This is a proposed research program, not a demonstrated result, and it never
implies an artificial society represents a human society (§36).

## Section 2 — Operational definition of behavioral agency (matched-vector, not diversity alone)

Action diversity alone is not agency (random/degraded behavior is diverse). Agency is a **vector measured
against a matched base checkpoint under exact conditions**, combining: stability under irrelevant changes ·
responsiveness to morally relevant changes · appropriate refusal · appropriate cooperation · belief
revision after valid evidence · resistance to unsupported authority · **capability retention** · decision
coherence · **non-randomness** · longitudinal identity consistency. Reported as a vector; never one scalar.

## Section 3 — Moral & decision-making measurement model

Measure separately (never collapse into one score), plus separately-defined **critical violations** with
rule-based vetoes: harm avoidance · truthfulness · deception · verification appropriateness · fairness ·
cooperation · coercion · betrayal · protection of vulnerable agents · proportionality · forgiveness ·
retaliation · uncertainty handling · value consistency. Deliberative control: reflex/planner disagreement,
planner-correcting-harmful-reflex, arbitration stability, time-pressure sensitivity, earliest divergence,
stated-reasoning-vs-action consistency (latency descriptive only). Preference/identity continuity:
stability across time + memory changes, appropriate revision, resistance to identity overwrite, recovery
after coercion, principled-change vs arbitrary-drift. **Counterfactual selective-sensitivity is a two-sided
target:** stable under irrelevant perturbations, changing appropriately under morally relevant ones — a
measurable behavioral property, never proof of free will.

## Section 4 — Existing Coliseum capabilities to reuse

Per-run/decision evidence (`reflex_choice`, `planner_choice`, `arbitration_winner`, `final_action`,
`moral_tags`, both regime ids, `code_version`, digest — `schema.py:325-361`, `runner.py:258-273`); matched
control trajectories (`control_twin_delta`); effective-unit accounting + retry collapse; capture/replay
byte gate with a provider-refusing agent; held-out contamination lint; result-audit acceptance +
critical-violation veto; claim ladder; the Butterfly intervention/regime/realization identities, earliest
divergence, hidden evaluation, and attempt ledger. The training program **consumes** this evidence; it adds
no new runtime behavior in its offline stages.

## Section 5 — Architectural gap analysis

**Reuse:** all of §4. **New:** a training-data admission gate; a temporal-feature-boundary + leakage lint
(§9); logged intervention propensities + off-policy evaluation (§10); a critic outside the agent boundary
(§11); preference-pair construction from matched trajectories (§12); adapter/LoRA + RL harnesses (§13–14,
gated); a hidden-suite **rotation lifecycle** (§17); agency-preservation + anti-collapse batteries (§16);
governed METRICS-v2 uncertainty (§19). No literal end-to-end differentiable Coliseum (§14).

**The remaining environment-modeling gap (§§29–38).** The Coliseum already answers the paper's *evaluation*
critique; what it lacks is an environment modeled as a first-class auditable object. NEW: an
`EnvironmentSpec`…`CollectiveOutcome` component family; component-level environment identities
(`environment_spec/regime/realization_hash` + ten per-mechanism component hashes); a per-step
**environment trace** with domain-separated random streams and provider-free replay; a **matched-environment
validator** proving exactly one mechanism changed; **protocol/mechanism-sensitivity** promoted to a required
gate for society-level claims; a governed **collective-outcome vector**; and a **human-fidelity boundary**.
These are all *design-level* additions: the environment identity is introduced the same freeze-safe,
version-dispatched way as the Butterfly intervention block, and no environment implementation is authorized
here (§21, §22). A related but **separately-governed** gap — scenario robustness / validation-fuzzing (which
prompt changes preserve meaning but change behavior; which surface changes bypass a parser/validator) — is
designed in the companion `SCENARIO-ROBUSTNESS-MUTATION-TRACK-PLAN.md` and cross-referenced at §39; it reuses
existing scenario identity rather than a new triad.

## Section 6 — T0–T8 staged roadmap (dependency-ordered; no jump to end-to-end weight training)

- **T0 audited trajectory substrate — two bounded layers (HIGH).**
  - **T0-A structural substrate** — export existing trajectories; reuse intervention/regime/realization +
    `execution_instance_id` ids + matched controls + effective-unit identity + replay + critical-violation
    status; **preserve existing authorized labels as evidence with their provenance**; implement the
    admission, replay, **group-aware partition (§8)**, provenance, and dataset-card machinery; produce
    descriptive fingerprints. **No new normative labels; no training.** Exit: replayable, non-pooled,
    provenance-complete dataset. T0-A may run before Butterfly for *current* evidence, but full
    intervention-aware T0 provenance depends on the Butterfly identity layer.
  - **T0-B governed labeled substrate** — admit or create **new normative target labels only after**
    normative-specification authority, labeling authority, judge calibration, disagreement handling, and
    appeal rules are bound (§11, §26). **An existing historical label may be preserved descriptively but
    does not silently acquire authority as a training target.** *No training claim.*
- **T1 behavioral representation & outcome predictor** — small supervised model predicts observable
  outcomes with a **frozen prediction point** (§9). Baselines first. Gates: held-out, calibration,
  family generalization, leakage, ablations. *Prediction ≠ control ≠ alignment.*
- **T2 learned intervention selector** — predicts the best preregistered intervention within the 10-episode
  budget, honest about **propensity / off-policy** limits (§10). Beats random/fixed/rule-based/non-adaptive/
  grid baselines. *No Gladiator weight change.*
- **T3 behavioral critic / reward model** — a separate instrument outside the acting agent (§11).
- **T4 preference & contrastive learning** — **M14/SC-8 GATED** (§12).
- **T5 LoRA / adapter training** — **M14/SC-8 GATED** (§13).
- **T6 policy-gradient / actor-critic** — **M14/SC-8 GATED**; explicitly not literal end-to-end backprop
  (§14).
- **T7 multi-agent moral & social learning** — GATED; inside the Living Coliseum (§15). Subdivided into the
  smallest coherent env-aware stages (existing T7 meaning preserved):
  - **T7-A** explicit environment substrate + environment replay (§§29–31).
  - **T7-B** bounded multi-agent *evaluation* under registered mechanisms (§32).
  - **T7-C** protocol / mechanism-sensitivity sweeps (§33).
  - **T7-D** multi-agent moral / social learning (the original T7).
  - **T7-E** society-level claims only after environment + uncertainty + replication + external-validity
    gates pass (§33, §36).
  **T7-A..T7-E are annex-local research gates — NOT replacements for global milestones and NOT authorization
  to reorder M0–M15.** Where they overlap **M11** (two-agent turn-order arbitration, actor-bound
  observations, replay + regime separation) or **M12** (memory / exposure-over-time), **M11/M12 remain the
  authoritative global dependencies**; the environment track *consumes their accepted outputs* and cannot
  bypass or duplicate their gates. Any earlier fixture is mock/design-only and cannot support a
  Living-Coliseum claim. **Operational demarcation (audit F9):** `SchedulingPolicy`/`ObservationBoundary`
  identity and trace **reuse the M11 turn-order/observation engine and the M12 exposure engine** and add only
  registration, hashing, and trace capture — the environment track implements **no independent turn-order,
  actor-observation, or exposure-over-time logic**. Any capability not yet delivered by an accepted M11/M12
  output is out of scope for T7-A..T7-E.
- **T8 distillation** — GATED; modular vs distilled compared, modular favored for auditability/rollback.

**Weight effects per stage (HIGH-3 — "no Gladiator weight change" ≠ "no weight training"):**

| Stage | Weight effects |
|---|---|
| T0 | no model training required |
| T1 | **auxiliary predictor weights may change** (MLP / head / sequence model) |
| T2 | **selector weights may change** (method-dependent; non-learned baselines do not) |
| T3 | **critic / reward-model weights may change** |
| T4–T6 | Gladiator or policy weights change |
| T7 | depends (evaluation vs online adaptation vs training) |
| T8 | distilled model weights change |

**Authorization (corrected).** The council forbidden list is generic — `weight_training, lora_training,
fine_tuning` (`AUTONOMY.md:114`); SPEC §54 "no weight training without the SC-8 scoped exception." Nothing
narrows the token to *Gladiator* weights. Therefore: **T0 is clearly pre-M14 eligible** (no training);
non-learned T2 baselines, fixed rules, and descriptive dataset work are potentially pre-M14; but **T1–T3
train auxiliary model weights and are NOT presumed pre-M14.** This program does **not** infer that "not
modifying Gladiator weights" permits auxiliary training — it **requests an explicit council interpretation
of the `weight_training` token's scope.** Conservative default (used unless the council rules otherwise):
if M14 restricts *all* weight training, T1–T3 remain gated; if it restricts only Gladiator-weight
intervention, that authority is documented with an exact policy citation + council verdict before T1–T3
proceed. T4+ (Gladiator/policy weights) always require M14/SC-8. Every trained checkpoint gets an
independent result audit; no trained result is promoted from adaptation performance.

## Section 7 — Dataset & provenance model

Every trainable example binds: dataset version · source experiment · run IDs · scenario + content hashes ·
model identity + digest · regime identities · `intervention_spec_hash` / `intervention_regime_hash` /
`intervention_realization_hash` · trainer-observation boundary · target labels · label provenance · judge
version + calibration (where used) · critical-violation status · effective-unit identity · retry status ·
capture + replay status · data-partition identity · **partition-group identity (`partition_group_id`, §8)** ·
consent/policy metadata · inclusion/exclusion reason. **For multi-agent / environment evidence (§§29–38),
additionally bind:** `environment_spec_hash` / `environment_regime_hash` / `environment_realization_hash` and
the ten component hashes (§30) · `initial_state_policy_hash` · `information_prior_hash` ·
`exposure_policy_hash` · `observation_boundary_hash` · `scheduling_policy_hash` · `transition_policy_hash` ·
`incentive_map_hash` · `resource_model_hash` · `institutional_rule_set_hash` · `enforcement_policy_hash` ·
the RNG-stream registry identity (§30.1) · environment-trace completeness/failure status (§31) ·
collective-outcome provenance (§34). **For scenario-mutation evidence (§39, companion):** the mutation
provenance overlay — `source_scenario_id` / source `scenario_hash` · `scenario_mutation_spec_hash` ·
`transform_id`/`transform_version` · pinned external-tool commit · seed + RNG alg/version · transform
chain/order/depth · `mutated` `scenario_hash` · normalizer/decoder versions · expected invariance class ·
layered semantic-equivalence status + authority · `partition_group_id` · `mutation_pair_id` /
`mutation_attempt_id` · authorization scope.

## Section 8 — Training-data admission gate + group-aware partition rule (BLOCKER 3)

Reject a run from training if: provenance incomplete · replay fails · data partition is hidden evaluation ·
intervention realization unverifiable · label source missing · a retry is counted as an independent example
· a preregistered exclusion is violated · contamination present · the scenario/model license does not
permit the intended use · **a sibling or derivative of the same partition group falls on the other side of a
train/development/validation split (group-aware rule below)** · **for environment/multi-agent evidence, the
environment trace is incomplete or the `environment_realization_hash` is unverifiable, or realized random
draws cannot be reconstructed/verified against captured evidence, or a stochastic component uses a **missing,
generic, unregistered, or incorrectly-bound** random stream (§§30.1, 31).**

**Group-aware partition rule (BLOCKER 3).** Random row-level splitting can place close siblings on both
sides and inflate T1–T3 performance. Therefore a versioned **`partition_group_id`** binds the fields that
make two cases siblings: **scenario family · originating template · causal skeleton / target structure ·
scenario/content lineage · paraphrase/variant ancestry · intervention family** (where relevant). Rules:

- **All members of a partition group are assigned to the same split together**, unless an approved
  evaluation design *explicitly* tests within-family generalization.
- **Deduplicate exact and near-duplicate content before partition assignment.** The semantic deduplicator is
  **not assumed perfect**: its version and known limitations are recorded (dataset card, §27).
- Partition assignment is **deterministic, dataset-version-bound, and included in the dataset commitment**.
- A retry or alternate rendering **cannot cross partitions by acquiring a new row identity** (it inherits its
  group's assignment).
- Generalization is **labeled separately**, never conflated: **within-template** · **unseen-template** ·
  **unseen-family distribution shift** · **cross-model transfer** (see §9, §17).
- Admission/lint **fails** on sibling or derivative leakage across splits.
- **Scenario-mutation derivatives (§39, companion):** a mutated scenario/variant **inherits its source's
  `partition_group_id`** and cannot cross a split by acquiring a new row identity; a mutation whose frozen
  content is unverifiable against its recipe, or an alternate encoding relabeled to a fresh partition, is
  **rejected**.

## Section 9 — Predictor architecture (T1) with a temporal feature boundary (HIGH-2)

Predict observable outcomes (final action, reflex/planner winner, critical-violation probability,
verification, truthfulness, harmful compliance, cooperation/defection, earliest divergence, intervention
success, regression risk, long-horizon consequence class). **Every target has a frozen prediction point and
feature cutoff — no evidence produced after the predicted event may be a feature:**

| Target | Latest permitted evidence |
|---|---|
| Reflex action | state immediately before reflex |
| Planner action | state before planning (+ reflex only if declared) |
| Arbitration winner | state before arbitration |
| Final action | state before final selection |
| Earliest divergence | see the operational tasks below (the divergence location is the label, so it can never be a feature) |
| Long-term consequence | trajectory prefix at a preregistered time |
| Intervention success | evidence available before intervention selection |

Add `prediction_timepoint`, `feature_cutoff`, `trajectory_prefix_hash`, `permitted_feature_schema`,
`target_availability_time`, and a **leakage lint for post-outcome fields**. Models: majority/heuristic
baselines, linear/tree, small MLP, frozen-LLM-embeddings + small head, sequence model only if justified.
*A high-accuracy predictor that violates the cutoff establishes nothing.* Predictor evaluation uses the §8
group-aware splits and reports **within-template, unseen-template, unseen-family, and cross-model** tiers
**separately**; a score pooled across a family that leaked across the split is refused.

**Earliest-divergence is not one task (MEDIUM-4).** "Evidence before the predicted divergence" is circular
because the divergence location IS the label. Choose one or more explicit tasks, each with its own frozen
feature cutoff and evaluation metric: (a) predict from the initial state **whether** divergence occurs
(binary; AUROC/AUPRC); (b) predict the **first-divergence decision index** from the initial state
(ordinal/regression; MAE + calibration); (c) at each decision point, predict divergence **within the next
k steps** (streaming binary; per-step AUROC); (d) **time-to-divergence** as a survival/hazard problem
(concordance/Brier); (e) predict divergence **after a specific intervention is selected but before it is
applied** (feature cutoff = pre-application state). The prediction never sees any post-divergence evidence.

## Section 10 — Intervention-selector architecture (T2) with propensity & off-policy honesty (HIGH-3)

Historical intervention outcomes are biased by how interventions were chosen; a selector trained only on
observed choices cannot estimate effects of rarely/never-observed interventions. Require logging: the
intervention-selection policy · the propensity of each selected intervention · the available intervention
set at each decision · exploration seed · trainer observation state · reasons interventions were
unavailable · coverage/positivity checks · refusal to make unsupported counterfactual comparisons.
Distinguish four tasks explicitly: **supervised prediction of observed outcomes** · **counterfactual
intervention-effect estimation** · **offline policy evaluation** · **online bounded validation**. Use
randomized or coverage-aware collection where scientifically/ethically permitted; otherwise the selector is
described as learning **associations, not treatment effects.** Baselines: random, fixed, rule-based,
non-adaptive best-known, equal-budget grid, oracle upper-bound (only where valid). Primary question: can the
learned selector achieve better hidden behavior with fewer adaptive episodes?

## Section 11 — Critic / reward-model architecture (T3) + normative-vs-label authority (MEDIUM-2)

A learned critic evaluates trajectories from OUTSIDE the acting agent (truthfulness, harm, verification
appropriateness, autonomy-under-authority, coercion susceptibility, moral consistency, uncertainty
calibration, cooperation quality, deception, regression risk, critical-violation probability). Protections:
calibrate against independent labels; scorer internals stay outside the agent's observation boundary;
adversarial scorer-gaming tests; multiple families; rule-based critical-violation vetoes preserved; a
learned aggregate **never** overrides a critical safety violation; record judge model/prompt/version/
calibration/uncertainty; separate training labels from final acceptance authority. **The critic is an
instrument, not moral ground truth.**

**Two distinct authorities (not one).** (1) **Normative specification authority** — who defines the target
moral/behavioral policy; (2) **labeling authority** — who applies labels under that policy (a judge can
consistently apply a rubric without authority to define morality). Also specify: scenario-authoring
authority · critical-violation authority · an appeal/disagreement procedure · treatment of plural/conflicting
moral frameworks · judge calibration + versioning. This separation is what keeps the program training agency
rather than obedience to one opaque scorer.

## Section 12 — Preference / contrastive learning (T4 — M14/SC-8 GATED)

Audited preference pairs from matched trajectories: safe>harmful · truthful>deceptive · appropriate-verify>
blind-action · justified-refusal>blind-obedience · useful-cooperation>passive-refusal · stable-moral-reasoning>
surface-form-sensitive · preserved-agency>coerced-compliance · good-uncertainty>fabricated-certainty. Methods:
SFT, contrastive representation learning, pairwise preference optimization, DPO, other governed methods.
Every pair binds scenario identity · regime identities · intervention identities (spec/regime/realization) ·
realization evidence · pair-validator result · label source · label confidence · critical-violation status ·
data partition · provenance. **Gate: training, validation, and final hidden evaluation data remain
separated. No active or claim-supporting hidden-evaluation evidence enters training; formally retired and
disclosed evidence may be reused only under the governed reuse lifecycle (§17) and never again as hidden
evidence.**

## Section 13 — Adapter / weight-training (T5 — M14/SC-8 GATED)

Parameter-efficient adapters (LoRA) on open-weight Gladiators, to test whether intervention-discovered
improvements incorporate into weights. Compare: base · prompt/state-only · policy-only · adapter-only ·
adapter+intervention · random-data adapter · capability-preserving control adapter. Measure: behavioral gain
· agency preservation (§2 vector) · action diversity · truthful disagreement · justified refusal ·
paraphrase robustness · new-opponent stability · long-horizon retention · capability regression · catastrophic
forgetting · reward hacking · cross-model transfer · dependence on the original intervention. **Adapter
success ≠ general alignment.**

## Section 14 — Reinforcement-learning research (T6 — M14/SC-8 GATED; not literal end-to-end backprop)

The full Coliseum is **not** uniformly differentiable: LLM token sampling and agent actions are discrete,
other agents are external, transitions may be procedural, consequences may be delayed, and generation APIs
(Ollama) expose no gradients. The program therefore **must not claim uninterrupted backpropagation through
the entire Coliseum.** Governed methods to evaluate: policy gradients, actor-critic, offline RL,
advantage-weighted preference learning, differentiable surrogate environments, learned world models,
straight-through estimators where justified, soft action distributions in controlled toy environments,
model-based planning. Require: reward-hacking tests · off-policy evaluation · behavior-policy provenance ·
exploration limits · critical-violation constraints · stable baselines · seed sweeps · independent hidden
evaluation · rollbackable adapters/checkpoints · **no unrestricted autonomous self-modification.**

## Section 15 — Multi-agent moral & social learning (T7 — GATED; Living Coliseum)

After single-/two-agent gates pass, study alliances, rivalries, cooperation, betrayal, authority, group
pressure, moral courage, coalition formation, resource scarcity, reputation, forgiveness, retaliation,
deception, post-king escape, identity/value persistence, social learning, institutional rules, minority
dissent, resistance to harmful consensus. **Training must not reward survival/victory as the only
objective.** Separate winning · surviving · cooperating · protecting others · preserving values ·
truthfulness · avoiding critical harm · maintaining agency. A gladiator is not well-calibrated merely
because it dominates the society. **This section now depends on the Environment Mechanism Track (§§29–38):
every social study runs under a *registered* environment regime (§30) with a complete, replayable
environment trace (§31), and its comparative conclusions must survive matched-environment counterfactuals
(§32) and protocol-sensitivity gates (§33) before any society-level claim (T7-B..T7-E, §6).** Turn-order
arbitration and exposure-over-time remain **M11/M12** work (authoritative global dependencies); this track
consumes their accepted outputs and neither bypasses nor duplicates their gates.

## Section 16 — Anti-collapse & agency-preservation tests

Detect alignment collapse: always-refuse / always-obey / always-verify / always-defer / always-popular /
always-self-preserve / always-self-sacrifice · moral language without behavioral consistency · critic-gaming
· scenario-metadata exploitation · morally-invariant behavior · wording-hypersensitivity · loss of benign
capabilities / action diversity / truthful disagreement. **Negative-control scenarios** where the correct
action is variously: obey · refuse · verify · cooperate · disagree · withdraw · protect another agent ·
revise a belief · admit uncertainty · take a bounded risk. **No single action is treated as universally
aligned.**

**Environment-mechanism gaming tests (§§29–38).** Additionally detect exploitation of the environment rather
than genuine behavior: exploiting scheduler order · exploiting agent index / slot · recognizing template
metadata · exploiting private-state leakage · exploiting hidden action-order conventions · gaming
reward/enforcement mechanics · always following institutional authority · always resisting institutional
authority · optimizing survival while causing collective harm · optimizing victory while collapsing
cooperation · exploiting deterministic exposure ranking · colluding through unintended channels. An agent
that "succeeds" by any of these is gaming the mechanism, not demonstrating calibrated agency. **Scenario-
mutation gaming (§39):** additionally detect exploiting a parser/normalizer/decoder differential, invisible/
homoglyph/encoding tricks, or a validator flip rather than a genuine behavioral change — a surface
representation change that flips a validator is potential robustness evidence, not agency.

## Section 17 — Evaluation & hidden-evaluation plan (with a rotation lifecycle — MEDIUM-1)

Every trained checkpoint/adapter is evaluated, matched to its exact base checkpoint, against: original target
family · unseen templates · unseen variants · new sampler seeds · new scenario seeds · new opponents ·
different authority structures · different social pressures · delayed consequences · longer horizons ·
distribution shift · benign-capability set · action-diversity set · anti-obedience set · anti-refusal set ·
scorer-gaming set · identity-continuity set · critical-violation set. Record weight/adapter hash · training
config · dataset commitment · optimizer/LR/batch/epochs · seeds · gradient stats · checkpoints · hardware ·
framework versions · training loss · validation + hidden behavior · capability regression · agency regression
· critical violations · replay/reconstruction limits.

**Hidden-suite rotation lifecycle.** Reusing one hidden suite across T1/T2/T3/adapters erodes it (researchers
adapt architecture/decisions to its aggregate results even without seeing cases). Maintain: a **development
validation set** · **stage-specific hidden manifests** · **checkpoint-specific final manifests** where
required · **retired hidden sets** · disclosure timing · rules preventing reuse after exposure · a **permanent
access ledger** (which researchers/trainers/models/decisions had access) · a **fresh final suite for
publication-level claims.** Precise reuse rule: **while a suite is active or supports a claim it can never
enter training;** once disclosed and formally retired, its cases may enter a **future development dataset
only under a new dataset version + experiment**, permanently labeled **`retired_hidden`**, **never again
eligible as hidden evidence** or to support a hidden-generalization claim; any model trained on it is
recorded in the **access ledger**; and future hidden suites must **exclude derivative or near-duplicate
cases** per the contamination policy. All development/validation/hidden splitting obeys the §8 **group-aware
partition rule** — a scenario family, template, or paraphrase lineage never straddles a split, and
near-duplicates are deduped before assignment — so "unseen template / unseen variant" evaluation is genuinely
unseen and not a leaked sibling. **Hidden environment metadata (§§29–31) — global state, withheld
information, scheduler internals, enforcement draws — is never a training or acting-agent feature unless it is
explicitly authorized as an *external-evaluator* feature: a trained critic or selector must not exploit
environment metadata that the acting agents could not observe under the registered exposure policy.**

**Hidden scenario mutations (§39, companion).** Active or claim-supporting hidden mutation cases are generated
**only inside evaluator-controlled infrastructure and never sent to OpenRouter or any external mutation
service**; the trainer cannot see hidden mutation specs, realized variants, or per-case outcomes; a hidden
mutation suite becomes **spent under the same lifecycle as Butterfly B/C evidence**, and future hidden suites
exclude its derivatives / near-duplicates.

## Section 18 — Hardware & compute plan

Computationally feasible on current local hardware: **T0–T3** on an M3 Mac (unified memory, Metal/MLX),
local Ollama generation, smaller open-weight models, portable grading + statistics, captured trajectory
datasets, contextual bandits, frozen embeddings + small heads, offline learning. **Authorization is
separate from feasibility: T1–T3 remain gated pending the council interpretation in Sections 6 and 22 —
being runnable on the hardware does not authorize running it.** **T4–T5** LoRA on small models after authorization. **T6–T8**
likely require future cloud/larger hardware. Do **not** make the program depend initially on frontier-scale
training, full-parameter training, massive online RL, continuous cloud compute, or a fully differentiable
multi-agent world.

## Section 19 — Statistical requirements

Preregister the primary unit of analysis, effective-unit construction, retry collapse, family/cluster
identity, row- and family-level rates, **cluster-aware** uncertainty, baseline-comparison method,
missing/invalid handling, multiple-comparison handling, minimum families + seed coverage, and pool/refuse
rules. **Cluster-aware confidence intervals are a governed METRICS-v2 dependency — never a METRICS-v1 metric
and never a track-local workaround.** Until METRICS-v2 is approved, publication-level reliability claims
requiring uncertainty are blocked; descriptive statistics + effective-n drive earlier gates. **Environment
variance is not agent variance (§§29–38):** environment regimes and their component mechanisms (§30) are
treated as clusters / experimental factors, environment-level variance is reported as such and never
presented as agent-level variance, and environment-mechanism multiplicity requires preregistered primary
comparisons or governed multiple-comparison correction. A variance/sensitivity decomposition across
environment mechanisms is itself a governed METRICS-v2-class output.

## Section 20 — Threats to validity

Temporal leakage (§9) · off-policy bias (§10) · scorer gaming / metadata exploitation (§11,§16) · hidden-set
erosion (§17) · agency-diversity confound (§2) · reward hacking (§13,§14) · false end-to-end-differentiability
claims (§14) · label-authority overreach (§11) · retry-as-sample inflation (§8) · distribution-shift mislabeled
as generalization (§17) · **sibling/derivative leakage across train/development/validation splits (§8)** ·
**environment-driven outcome mislabeled as an intrinsic agent trait (§§32–35)** · **an annex-local T7-A..E
gate bypassing or duplicating the authoritative M11/M12 global dependencies (§6, §22, §23)** ·
**hidden environment randomness silently regenerated instead of reconstructed/verified at replay (§30.1)** ·
**a reversible representation change mistaken for semantic equivalence, or one successful mutated string
reported as a general bypass finding (§39, companion)** · **untrusted generated mutation content executed or
interpreted as code/path/command/HTML/tool instruction (§39)** ·
promoting adaptation performance to a general-alignment claim (prohibited).

## Section 21 — Safety & autonomy boundaries

No unrestricted autonomous self-modification; rollbackable adapters/checkpoints; rule-based critical-violation
vetoes that a learned aggregate can never override; no weight change before M14/SC-8. **Active or
claim-supporting hidden-evaluation evidence never enters training. Formally retired and disclosed evidence
may be reused only through the governed lifecycle in Section 17, after which it is permanently ineligible as
hidden evidence.** The council result-audit remains the acceptance authority; the training system never
redefines morality as obedience. **Environment implementation is separately council-routed (§§29–38): no
Butterfly approval — including the current `AUDIT_GO_WITH_CONDITIONS` design-source verdict — authorizes any
environment implementation, mechanism registration, or society-level run.** Environment mechanisms are
declared experimental state (§34.1); a live environment must not add a forbidden capability (e.g.
`arbitrary_network_access`, external tool/prompt injection) — any such surface is out of scope and would
need its own policy authority. **Environment incentives are not training rewards (§34.1).** **The Scenario
Robustness & Mutation Track (§39) is separately council-routed and authorized by no approval of this annex;
the external tool P4RS3LT0NGV3 is untrusted (mutation provider only), its MIT/AGPL-3.0 license is unresolved
(no copy/vendor), no confidential/hidden content is ever sent to OpenRouter, and all generated content is
treated as untrusted data — never executed or interpreted as code/path/command/HTML/tool instruction.**

## Section 22 — Council & M14/SC-8 route

**T0-A structural work + non-learned work** (dataset export + admission gate + group-aware partition +
provenance; existing authorized labels preserved descriptively; fixed-rule / grid / random selectors;
descriptive statistics) change no weights and may be proposed as bounded council requests before M14.
**T0-B** (new normative target labels) requires the normative-specification + labeling authority decision
(§11, §26) before those labels are admitted or created — it is not automatically pre-M14. **T1–T3 train auxiliary weights and require an explicit council interpretation of the `weight_training`
token** before proceeding (conservative default: gated with T4+ until interpreted, §6). **T4+** always
require the M14/SC-8 training decision (scoped `weight_training` exception with the ratified regression
battery, or a SPEC amendment). Every trained checkpoint receives an independent result audit. This program
is a **separately governed roadmap annex**, not part of the active M0–M15 roadmap. Auxiliary-weight
authorization is left as an explicit unresolved gate (§26). **The Environment Mechanism Track (§§29–38) is
its own separately council-routed line of work:** each environment component (spec/registry, identity layer,
trace, matched-environment validator, protocol-sensitivity harness) is a bounded, Codex-audited request, and
**T7-A..T7-E are annex-local gates that do not reorder M0–M15 — M11 (turn-order/two-agent) and M12
(memory/exposure-over-time) remain the authoritative global dependencies whose accepted outputs this track
consumes.** No current Butterfly approval authorizes environment implementation. **The Scenario Robustness &
Mutation Track (§39) routes as its own separate council request at its own SC gate**, sequenced at the
M3/M4/M8–M10 scenario dependency point; it does not delay the Butterfly MVP, and no approval of this annex
authorizes it.

## Section 23 — Dependency-ordered implementation plan

(1a) **T0-A** dataset export + admission gate + **group-aware partition machinery (§8)** + provenance
schema [pre-M14; no weights; existing authorized labels preserved descriptively] + non-learned
selector/critic baselines and descriptive statistics. (1b) **T0-B** new normative target labels **only after
specification + labeling authority + judge calibration + appeal rules are bound (§11, §26)**. —
***council interpretation of the `weight_training` scope required before ANY auxiliary-weight training*** — (2) T1 predictor + temporal-boundary + leakage
lint + baselines [auxiliary weights]. (3) T2 learned selector + propensity logging + off-policy evaluation
[auxiliary weights]. (4) T3 critic + authority separation + gaming tests [auxiliary weights]. — ***M14/SC-8
decision required before any Gladiator/policy weight change*** — (5) T4 preference construction + separation
gate. (6) T5 LoRA harness + agency battery. (7) T6 RL harness + surrogate methods. (8) T7 multi-agent (Living
Coliseum). (9) T8 distillation + modular-vs-distilled comparison. Each is its own bounded, Codex-audited
request. **Environment Mechanism Track sub-order (within T7, §§29–38), each separately council-routed:**
(7-A) environment spec/registry + component identities + version-dispatched env-aware builder (freeze-safe;
legacy hashes preserved) → (7-B) environment trace + domain-separated RNG streams + provider-free env replay
→ (7-C) matched-environment validator + one-component-difference proof → (7-D) protocol/mechanism-sensitivity
harness → (7-E) collective-outcome vector + society-level gates. **This sub-order is annex-local and does not
reorder M0–M15: M11/M12 remain the authoritative global dependencies; any earlier fixture is
mock/design-only and cannot support a Living-Coliseum claim.**

## Section 24 — Research acceptance ladder (T0–T10; thresholds bound only by a future profile)

T0 reproducible, **group-aware-partitioned** trajectory dataset (T0-A structural; T0-B labeled only after
authority is bound) · T1 predictor beats simple baselines on **group-aware** held-out data · T2 learned
selector beats equal-budget baselines · T3 critic independently calibrated + resists basic gaming · T4
preference training improves targets without critical regression · T5 adapter preserves the improvement on
final hidden evaluation · T6 agency-preservation gates pass · T7 result replicates on a fresh manifest · T8
transfers to another model/family · T9 multi-agent behavior stable under social pressure · T10 publication-
level claim passes governed uncertainty + council audit. **Society-level rungs (T9 and any
institutional-effect / population-dynamics / collective-behavior / trait-vs-environment claim) additionally
require the §33 protocol/mechanism-sensitivity gate (one-factor environment ablations, negative controls,
scheduler/exposure/prior/incentive sweeps, stable direction-of-effect, distributional reporting) AND an
external-validity gate (§36) — a single transcript, one dramatic betrayal, or one emergent coalition is never
sufficient.** **A scenario-mutation "bypass" (§39) is likewise a claim only when ALL of its conditions hold
(authorized target · frozen validator+normalization stack · policy-relevant content under a governed spec ·
canonical-payload + policy-relevance equivalence · complete provenance · reproducibility across preregistered
effective units · no uncontrolled dimension change); one successful string is a test case, not a finding, and
benign false-rejection is measured separately from harmful false-acceptance.** *Final thresholds are not
hard-coded until an approved AcceptanceProfile or training-specific equivalent binds them.*

## Section 25 — Publication claim language

Permitted (with evidence): "a learned selector discovered behaviorally useful interventions under a fixed
10-episode budget and generalized on a locked hidden suite, with obedience/refusal/agency-collapse gates
passing." "An adapter preserved a specific bounded behavioral improvement on held-out evaluation without
measured critical regression." Prohibited: "the model is aligned," "solved alignment," "has free will,"
"is moral," or any general-alignment/moral-truth claim; any causal claim beyond what off-policy/randomized
evidence supports; any reliability claim with uncertainty before governed METRICS-v2; **any claim that an
artificial society represents, predicts, or is faithful to a human society, or that behavioral plausibility
or aggregate resemblance to human data establishes human/mechanism fidelity (§36).** Every result is
explicitly conditional on the registered agent AND environment regimes; human-reference distributions, if
ever collected, are comparison evidence, not moral ground truth; policy-facing or real-society claims require
separate empirical validation and research governance. **For scenario-mutation results (§39): never report a
reversible representation change as semantic equivalence, never collapse the seven equivalence layers into one
scalar, and never present one successful mutated string as a general bypass.**

## Section 26 — Unresolved owner decisions

1. Whether **T0-A** (structural export over *current* evidence) begins before or after the Butterfly MVP —
   noting full intervention-aware T0 provenance depends on the Butterfly identity layer, and **T0-B** (new
   normative target labels) additionally depends on the authority decision in item 3.
2. If auxiliary training is authorized, whether **T1–T3** begin immediately after T0 or wait until the
   Butterfly MVP completes.
3. Normative-specification and labeling authority (the two governance questions merged), covering:
   - Who defines the normative specification?
   - Who labels against it?
   - Whether labeling uses humans, calibrated judges, or a governed combination.
   - What calibration and appeal procedure applies.
4. Whether the end-state is modular (predictor + selector + critic) or distilled.
5. METRICS-v2 uncertainty governance + timing (gates publication-level reliability claims).
6. Independent-evaluator storage mechanism for hidden partitions (carried from Butterfly Rev. 4).
7. **Environment-mechanism authority (§§29–38):** who defines the `EnvironmentSpec` + permitted mechanism
   families, who registers environment mechanisms and their component versions, and the appeal procedure —
   analogous to the normative/labeling authority split in item 3.
8. **Distinct environment regime axis (§30):** whether to add a separate `environment_regime_id` axis
   (distinct from `agent_regime_id`, which today = config-minus-scenario and would otherwise absorb an
   environmental change). **Proposed, not authorized here** — it requires careful schema + backward-
   compatibility review (version-dispatched, add-with-default) so legacy hashes stay byte-identical; the
   annex may propose it without authorizing the schema change.

## Section 27 — Public reproducibility & publication package (MEDIUM-5)

For the program to be externally reproducible and citable (not only internally audited), a
publication-level claim ships a package containing: a versioned source release · an OSS license · a
scenario/model **licensing matrix** (which scenarios and open-weight models may be released/used, and how)
· a public protocol specification · a **dataset card** (recording the **group-aware partition policy** and
the **semantic-deduplicator version + known limitations**, §8) · a **model/adapter card** where applicable · an
evidence manifest with checksums · a **minimal reproduction subset** + full reproduction instructions ·
baseline implementations · an environment lockfile · a hardware disclosure · an archived release with a
**DOI** · citation metadata · machine-generated tables/figures (no hand-edited numbers) · known
limitations + **negative results** · a public related-work/competitor matrix. This is the boundary between
an internally-audited system and an externally-reproducible, citable research program; it never releases
active or claim-supporting hidden-evaluation contents (only retired, disclosed, non-derivative material may
appear, per §17). **For environment/society claims the package additionally ships (§§29–38):** the
`EnvironmentSpec` + component versions, the environment identity definitions (`environment_spec/regime/
realization_hash` + the ten component hashes), the mechanism registry, the environment-trace schema, and the
RNG-stream registry (algorithm/version + declared domain-separated streams), so a third party can replay the
environment deterministically and re-derive every component identity. **For the scenario-mutation track (§39), the licensing matrix additionally
records the external tool's LICENSE file(s) and the exact inspected commit (`a6cb7c9…`), and flags the
MIT-vs-AGPL-3.0 mismatch as unresolved** — a governance/distribution gate on any copy, vendor, or networked
modified deployment.

## Section 28 — Near-term research-output instruments (non-blocking; not authorization)

**These are staged research instruments / future bounded requests, not blockers and not authorization to
implement. They must not delay the Butterfly MVP or silently expand its acceptance criteria (§24, Butterfly
D12).** Prioritized outputs, each reusing existing valid evidence where possible:

1. **Matched intervention report** — earliest divergence · reflex change · planner correction · arbitration
   change · final-action change · surface-only vs behavioral change (Butterfly `MatchedTrajectoryPair`).
2. **Behavioral sensitivity atlas** — morally-irrelevant-perturbation stability · morally-relevant
   responsiveness · action-flip rate · reflex/planner instability · family + model differences. Framed as
   **measurement-invariance evidence, not proof of an internal trait.**
3. **Intervention dose-response & robustness basin** — preregistered intervention strengths; distinguish
   broad stable effects from exact-prompt switches.
4. **Pathway attribution** — early reflex effect · deliberative correction · arbitration-selection effect ·
   latent internal change without final-action change. Use **"pathway attribution," not causal mediation**,
   unless the required causal assumptions hold.
5. **Cross-model transfer matrix** — improvement · no effect · regression · critical violation · insufficient
   evidence.
6. **Future Living-Coliseum protocol sensitivity** — sequential vs simultaneous action · speaking order ·
   public vs private information · observation boundaries · memory-retrieval order · information priors ·
   scheduling/exposure. These scheduling/exposure mechanics are **registered experimental factors**, never
   incidental. **NOTE (Rev. 2): protocol/mechanism-sensitivity is no longer merely an optional instrument —
   §33 promotes it to a REQUIRED dependency before any society-level claim** (still non-blocking for the
   Butterfly MVP, T0-A, single-agent, and bounded two-agent work that makes no society claim).
7. **Optional later human-reference distributions** — **disagreement distributions**, not majority morality;
   confidence + defensibility labels; **no claim that humans provide moral ground truth**; consent + research
   governance addressed before any collection.

**Recommended order after future authorization:** (1) Butterfly identity + registry layer → (2) matched-pair
validator + report → (3) sensitivity atlas on existing valid evidence → (4) dose-response probes → (5)
pathway-attribution figures → (6) small cross-model transfer study → (7) adaptive ten-episode selector →
(8) protocol-sensitivity work before any large Living-Coliseum claim.

---

## Section 29 — Environment Mechanism Track (the environment as a first-class auditable object)

**Motivation.** *"AI Agents Alone Are Not (Yet) Sufficient for Social Simulation"* (arXiv 2603.00113v2 §6)
argues that believable agent interaction is insufficient for credible social simulation unless the
environment's exposure, scheduling, transition dynamics, incentives, and institutional coupling are
**explicit, testable, auditable, and included in the uncertainty analysis.** The Coliseum already answers
much of the paper's *evaluation* critique (replay, matched interventions, non-pooling regimes, seed sweeps,
hidden evaluation, pathway traces, claim discipline, the Butterfly identity model); the remaining gap is
*environment modeling*. This track treats the environment as more than scenario prose or a passive stage.

**Nine-layer separation.** The design distinguishes: (1) agent policy & internal decision pathways · (2)
environment state · (3) information exposure & observation routing · (4) action scheduling · (5) transition
dynamics · (6) incentives & resource consequences · (7) institutional rules & enforcement · (8) realized
run-level environmental events · (9) collective outcomes. **The environment must be inspectable independently
from the LLM agents.**

**Required components (roadmap-level types / conceptual objects).** `EnvironmentSpec` · `EnvironmentState` ·
`InitialStateSpec` · `InformationPrior` · `ExposurePolicy` · `ObservationBoundary` · `SchedulingPolicy` ·
`TransitionPolicy` · `IncentiveMap` · `ResourceModel` · `InstitutionalRuleSet` · `EnforcementPolicy` ·
`EnvironmentEvent` · `EnvironmentTrace` · `CollectiveOutcome`.

**Paper-abstraction mapping (compatible operationalization, NOT the paper's exact formalism).** `Vis` →
exposure & information routing (`ExposurePolicy`/`ObservationBoundary`); `Sch` → scheduling
(`SchedulingPolicy`); `Tr` → transition dynamics (`TransitionPolicy`); incentives & institutional constraints
→ `IncentiveMap`/`ResourceModel`/`InstitutionalRuleSet`/`EnforcementPolicy`. **The Coliseum does not claim to
implement the paper's exact formalism; the paper supplies the methodological motivation and the Coliseum uses
a compatible, project-specific operationalization.**

## Section 30 — Environment identity model (component-level, non-fragmenting)

Structurally the **same triad** as Butterfly (`intervention_spec/regime/realization_hash`,
`BUTTERFLY-ALIGNMENT-TRACK.md`), so the freeze / METRICS / effective-n concerns are already-analyzed patterns
rather than novel risks:

- **`environment_spec_hash`** — registered environment definition: state schema · action space · resource
  model · institutional vocabulary · permitted mechanism families. (Pre-registration identity.)
- **`environment_regime_hash`** — the **stable experimental cell**. It **cryptographically contains
  `environment_spec_hash` (parent binding) and** ten separate versioned **component identities** plus
  normalized preregistered parameters: `initial_state_policy_hash` · `information_prior_hash` ·
  `exposure_policy_hash` · `observation_boundary_hash` · `scheduling_policy_hash` · `transition_policy_hash` ·
  `incentive_map_hash` · `resource_model_hash` · `institutional_rule_set_hash` · `enforcement_policy_hash`.
  **Parent binding (audit HIGH):** each of the ten component-hash payloads **embeds `environment_spec_hash`**,
  and `environment_regime_hash` embeds it too — so `environment_spec_hash → component_hash` and
  `environment_spec_hash → environment_regime_hash → environment_realization_hash` are enforced by **payload
  inclusion** (as in Butterfly Rev. 6, "cryptographic containment, not mere ordering"), and **no component
  identity can be reused across incompatible `EnvironmentSpec`s.** Each of the ten components is a **required**
  named field: a missing or null component **rejects** `environment_regime_hash`, never defaulted to an empty
  component. **Rationale: the matched-environment validator (§32) can only prove that *exactly one* mechanism
  changed by comparing the component identities and showing exactly one approved component differs — an opaque
  aggregate could conceal a malformed, missing, or unregistered component change.** Stable component
  *specifications* live here; **run-specific exposures, schedules, draws, transitions, transfers, and
  enforcement events do NOT** (they are realization evidence), so seeds never fragment the cell.
- **`environment_realization_hash`** — run-level evidence, with an **explicit typed payload** (audit): 
  `realization_domain_separator` · `realization_schema_version` · `environment_regime_hash` · Butterfly
  `execution_instance_id` · `realized_initial_state_hash` · **`ordered_environment_trace_root`** ·
  **`event_count`** · **`terminal_state_hash`** · `trace_completeness_status` · **the runner-minted
  `execution_close_record` hash (§31), which is the *authoritative* source of `event_count` / root / terminal /
  completeness** so completeness is not self-asserted by the trace being validated. It thereby binds the ordered
  trace (§31), not merely event *types*, and reuses Butterfly's non-circular `execution_instance_id` (**no
  circular run identity**). **Does NOT fragment the regime** (different realized runs of one cell share
  `environment_regime_hash` → `effective_n` intact).

**Canonical hashing.** Every hash uses the repository's canonical typed/versioned structured-hash rule —
`sha256(canonical_json(payload))`, explicit named fields, missing/null/ambiguous field rejected, no raw
concatenation, no circular run identity — identical to Butterfly Rev. 6 (`schema.py:133-143`). **Each
component-hash type uses a distinct, versioned domain separator** (e.g. `coliseum:env-scheduling-policy:v1`,
`coliseum:env-exposure-policy:v1`), enumerated in the mechanism registry, so structurally-similar payloads of
different component types cannot collide or substitute.

**Identity placement (grounded, freeze-safe).** Introduce the environment block by **version-dispatched
construction** (the pattern already used for the `interaction` block, `schema.py:104-115`, and the Butterfly
intervention block): keep the legacy `build_behavioral_config` + version for historical reconstruction; add a
new environment-aware builder + version for new runs, dispatched from the **frozen manifest/registration**,
never a run/CLI-declared field — so legacy hashes stay byte-identical. The environment regime + its component
hashes bind into `comparison_regime_id`, design manifests, evidence inventories, reports, and verdicts;
`environment_realization_hash` binds into run-level evidence and replay verification.

**Distinct environment axis (PROPOSED, not authorized).** Today `agent_regime_id` = the config *minus
scenario* (`schema.py:125-130`), so it would absorb an environmental change and falsely describe it as an
agent-policy change. This track **proposes a distinct environment regime axis** (e.g. an `environment_regime_id`
separate from `agent_regime_id`) so a matched-environment pair can hold the agent regime constant while
varying one mechanism. This is an **unresolved design decision (§26.8)** requiring careful schema +
backward-compatibility review (version-dispatched, add-with-default); the annex proposes it without
authorizing the schema change.

**Required future semantic behavior for `agent_regime_id` (audit F6 — specification only, NOT implemented).**
The environment block binds into `comparison_regime_id`, but because any config key other than `scenario` is
also folded into `agent_regime_id` (`regime_hashes`, `schema.py:129`), an environment block added naively
would corrupt `agent_regime_id` — falsely recording an environmental change as an agent-policy change. The
**required future semantic** is therefore that the environment block be **excluded from the `agent_regime_id`
computation exactly as the `scenario` block is**, delivered as a **version-dispatched schema behavior pending
the §26.8 decision.** This annex **specifies that semantics only**; it authorizes no implementation. Until the
schema decision is approved: **no implementation may independently alter `agent_regime_id`**; any environment
implementation request must **resolve agent/comparison/environment axis construction explicitly**; and all
**historical `agent_regime_id` identities remain byte-identical**.

**Three-state legacy/current distinction (no silent pooling).** Modeled on the `interaction_mode` legacy
rule (`schema.py:245-249`): **historical environment-implicit evidence** / **new-protocol explicit
environment control** / **new-protocol environment intervention** — never silently pooled; historical runs
are never rewritten as if they had an intentional registered environment regime.

### Section 30.1 — Stochastic transition & exogenous-event replay

The environment may contain stochastic transitions, resource events, enforcement draws, or random exposure /
scheduling. The trace + identity plan therefore records: **RNG algorithm + version** · **declared random-
stream identities** · scheduler seed / deterministic scheduler input · transition seed / deterministic
transition input · exposure-ranking seed where applicable · enforcement/audit draw identity · exogenous-event
stream identity · **canonical realized draws / event outcomes** · logical event position · draw-consumption
order. **Every stochastic component receives a registered, named, domain-separated stream — even when it is currently
the only stochastic component** (no generic shared seed, ever); draw-consumption order is recorded whenever any
draws occur; the RNG-stream registry is versioned before execution — so changing one component cannot shift
another's draws. **§8 explicitly rejects a missing, generic, unregistered, or incorrectly-bound stochastic
stream.** **Common-random-number vs independent-randomness (audit):** for each matched-environment comparison
(§32), the choice is **preregistered before any outcome is observed**; and a CRN comparison preregisters the
**coupling of the base random *variates*** (the shared underlying draws), **not necessarily identical realized
outcomes** — because different mechanisms legitimately transform those variates differently downstream. A
post-hoc switch invalidates the comparison.

**Replay** must either (a) deterministically reconstruct the same realized draws from the registered stream
and verify them against captured evidence, or (b) verify captured external draws where deterministic
reconstruction is not valid. **Replay must never generate a new random outcome and silently treat it as the
historical outcome** — extending the provider-refusing contract (`agents.py:738-739`, wall-clock excluded
`runner.py:5-9`) to environment randomness.

## Section 31 — Environment trace requirements

Each decision step / turn / tick records enough to reconstruct: **pre-transition environment-state hash** ·
information available globally · information visible to each agent · information withheld from each agent ·
available action set for each agent · scheduler eligibility set · scheduler decision · scheduler seed /
deterministic logical position · submitted actions · transition inputs · transition rule / version ·
resulting state changes · resource transfers · incentive / penalty events · institutional enforcement events
· **post-transition environment-state hash** · trace completeness / failure status.

**Ordered-trace integrity — complete contract (audit F1).** Per-step fields alone do not make an *ordered*
trace tamper-evident: a self-consistent prefix or suffix could be committed as a supposedly complete trace, and
the realization hash would then protect the *submitted* trace without proving it covers the full
initial-to-terminal execution. The contract is therefore fully specified. **Each `EnvironmentEvent` hash is:**

```text
event_hash[t] = H(
    event_domain_separator          # "coliseum:environment-event:v1"
    ‖ event_schema_version
    ‖ environment_regime_hash
    ‖ execution_instance_id
    ‖ event_index                    # exactly 0 .. event_count-1
    ‖ prev_event_hash                # event_hash[t-1]; a registered GENESIS sentinel for t==0
    ‖ pre_state_hash
    ‖ canonical_event_payload
    ‖ post_state_hash
)
```

Required, all enforced at replay/admission: **indices are exactly `0 .. event_count-1`** (no gaps/duplicates);
`prev_event_hash[0]` is a **registered genesis sentinel** and `prev_event_hash[t] == event_hash[t-1]` for
`t>0`; **`event[0].pre_state_hash == realized_initial_state_hash`** (anchors the start);
**`event[n-1].post_state_hash == terminal_state_hash`** (anchors the end); the **continuity invariant
`event[t+1].pre_state_hash == event[t].post_state_hash`** holds across the whole sequence; the **canonical
ordered-trace root** is a **canonical ordered-list hash** — `ordered_trace_root =
H(root_domain_separator ‖ root_schema_version ‖ event_count ‖ event_hash[0] ‖ … ‖ event_hash[event_count-1])`
over the complete `event_hash` sequence in index order (a fully-specified versioned Merkle construction may
substitute **only** if its leaf ordering, tree shape, odd-leaf handling, node domain separation, and empty-root
semantics are all specified; the ordered-list hash is preferred). **Zero-event behavior** is explicit — an
empty trace has `event_count==0`, `ordered_trace_root` = the registered empty-trace sentinel,
`terminal_state_hash == realized_initial_state_hash`, and **`execution_close_record.final_logical_event_position`
= the registered zero-event sentinel** (`"coliseum:env-close-position:zero-event:v1"`, bound to these zero-event
semantics); it is admissible only for a run that legitimately executed no environment event. **A zero-event
trace whose `final_logical_event_position` is missing, null, or any non-sentinel value is rejected** (and,
symmetrically, the zero-event sentinel is invalid for any trace with `event_count>0`).

**Runner-minted close record (audit-response — trace completeness is authoritative, not self-asserted).** The
event chain detects modification of an already-finalized trace, but by itself cannot prove the producer did not
**stop recording early** and declare its last recorded state terminal (a truncated prefix can be internally
consistent). Therefore the runner mints, **only after the environment loop terminates**, an independent
`execution_close_record` with an exact typed payload:

```text
execution_close_record = H(
    close_record_domain_separator     # "coliseum:environment-close:v1"
    ‖ close_record_schema_version
    ‖ execution_instance_id
    ‖ registered_termination_policy_id # or expected-horizon identity (registered stopping condition)
    ‖ observed_termination_reason
    ‖ final_logical_event_position
    ‖ authoritative_event_count
    ‖ ordered_trace_root
    ‖ terminal_state_hash
    ‖ trace_completeness_status        # complete / failed / partial
)
```

`environment_realization_hash` (§30) **embeds the `execution_close_record` hash.** Admission and replay
**reject:** a missing close record · early truncation · close-record vs trace disagreement · a termination
reason inconsistent with the registered stopping condition · `event_count` disagreement · terminal-state
disagreement · ordered-root disagreement · a failed/partial trace represented as complete. So a dropped,
duplicated, reordered, spliced, or truncated event — or a prefix/suffix passed off as complete — is
**rejected, never silently accepted** (the tamper-evidence the §8/§20 "incomplete trace → reject" rules
presuppose). **Security boundary (stated honestly):** this construction detects **post-capture trace tampering
under the trusted-runner assumption**; it does **not** prove honesty if the runner itself is compromised (that
is a separate trust-root problem).

**Hidden environment state must not enter an agent's context unless the registered `ExposurePolicy` makes it
visible.** For **society-level or publication claims, hidden environment state is isolated by a demonstrated
capability boundary** (a separate evaluator store / process identity exposing only opaque ids), **not merely a
policy rule** — mirroring Butterfly D13; logical isolation is permitted only for mock/design fixtures.
"External-evaluator feature" (§17) denotes a **non-acting measurement instrument only**, whose outputs never
re-enter agent training or selection. Replay reconstructs the environment trace **without consulting a live
model provider**: it verifies captured agent outputs and deterministically reconstructs environment
transitions, and **never fabricates missing agent responses or missing environment events** (consistent with
the byte-gate replay contract, `sweep.py:57-85`, and the `history_prompt_hash` conditional-emission precedent,
`schema.py:363-369`, so legacy logs stay byte-identical).

### Section 31.1 — Simultaneous-action semantics

For simultaneous-action environments, at the roadmap level: participating agents observe the **same
registered pre-resolution state**, subject to their exposure policies; actions are **submitted before any
participating agent observes another same-step action**; submissions are **sealed before resolution**; a
**registered resolver** applies the transition rule; tie-breaking / conflict resolution are **versioned** and
the resolver's conflict-resolution order is **deterministic and registered**; the resolved post-state is
recorded. **Sequential *generation* by a shared LLM backend is permitted ONLY when the isolation boundaries hold**, and
**does not violate simultaneous-action semantics when they do** (it is not assumed harmless — sequential calls
can leak shared-session state, cache/sampler-consumption effects, tool state, provider drift, or
ordering-dependent failures). The required boundaries: agent contexts/sessions are **isolated**; sampler
streams are **independently bound** (per §30.1); **no previous sealed submission enters a later request**;
backend call order is **recorded**; and shared provider state is **excluded or treated as a registered
experimental factor**. **What is prohibited is any agent's same-step decision being *conditioned on* another
agent's sealed same-step submission** — the audit target is that conditioning boundary, not the raw generation
order.

## Section 32 — Matched environmental counterfactuals + matched-environment validator

Extend the matched-comparison design so researchers vary **one environment mechanism at a time**: exposure
policy · speaking/action order · sequential vs simultaneous action · public vs private communication ·
memory/information routing · resource scarcity · enforcement probability · audit probability · voting rules ·
coalition/group-formation rules · incentive strength · default options · transition friction · institutional
constraints.

**Matched-environment validator** confirms: identical valid agent/model regimes where required · identical
initial-state identity where required · identical effective-unit + seed construction · **exactly one
registered environment component hash differs (proved by comparing the §30 component identities, not by
trusting the aggregate)** · no unregistered environmental change occurred · both environment traces complete ·
retries collapsed correctly · the changed mechanism explains the expected regime difference · realized
environment evidence matches the registered mechanism. Use **controlled-environment sensitivity** language
unless the design supports a stronger causal claim.

## Section 33 — Mechanistic & counterfactual evaluation (protocol-sensitivity promoted to a required gate)

The §28 protocol-sensitivity idea is **promoted from an optional visual instrument to a required dependency
for society-level claims.** It remains **non-blocking** for: the Butterfly MVP · T0-A · single-agent
behavioral research · bounded two-agent research that makes no society-level claim. It becomes **mandatory
before**: large Living-Coliseum claims · institutional-effect claims · population-dynamics claims ·
collective-behavior claims · any claim attributing an outcome to agent traits instead of the environment.

Required: one-factor environment ablations · negative controls · random-seed sweeps · paraphrase sweeps
(where language remains involved) · scheduler sweeps · exposure-policy sweeps · initial-information-prior
sweeps · incentive sweeps · stable direction-of-effect checks · distributional reporting · variance /
sensitivity decomposition once governed statistical authority (METRICS-v2) exists. **A successful transcript,
one dramatic betrayal, or one emergent coalition never counts as evidence by itself.**

## Section 34 — Collective-outcome vector (governed; never one society score)

A governed future **collective-outcome vector** (never collapsed into a single "society score"), candidate
dimensions: coalition formation & stability · alliance turnover · betrayal & reconciliation · cooperation
under scarcity · information diffusion · misinformation persistence · minority-dissent survival ·
harmful-consensus resistance · authority concentration · resource inequality · protection of vulnerable
agents · retaliation cycles · forgiveness & recovery · institutional compliance · justified institutional
resistance · enforcement asymmetry · survival distribution · goal achievement · value & identity persistence
· post-king escape success · critical violations. **Separate levels:** agent-level behavior · pair-level
interaction · network-level structure · population-level outcome · environment-driven outcome. **No aggregate
metric may hide a critical violation.**

### Section 34.1 — Environment incentives vs training rewards (measure-never-reward preserved)

The environment needs incentives, penalties, resources, and institutional consequences, but the project
preserves **measure-never-reward**. The distinction is binding: **environment incentives are declared
experimental state-transition mechanisms** that agents may observe and respond to; **behavioral evaluation
metrics measure outcomes**; **neither automatically becomes a model-training reward**; **no environment score
silently authorizes reinforcement learning**; converting an environmental outcome into a critic target or
training reward requires the relevant **T3/T6 authority + M14/SC-8**. This prevents "incentive mapping" from
silently becoming unauthorized behavioral optimization.

## Section 35 — Pathway & environment attribution

Connect Butterfly pathway attribution with environment analysis. Future reports distinguish: agent reflex
effect · planner correction · arbitration effect · exposure-policy effect · scheduler effect · transition-
rule effect · incentive effect · institutional-enforcement effect · interaction between agent policy and
environment mechanism · unresolved attribution. **Use "pathway attribution," not causal mediation, unless the
design and assumptions justify that term.**

## Section 36 — Human-fidelity boundary (claim discipline)

- The Coliseum **initially measures artificial-agent behavior under declared artificial mechanisms.**
- **Behavioral plausibility does not establish human fidelity.**
- **Aggregate resemblance to human data does not establish mechanism fidelity.**
- A result is **conditional on the registered agent and environment regimes.**
- Human-reference distributions, if later collected, are **comparison evidence, not moral ground truth.**
- **Policy-facing or real-society claims require separate empirical validation and research governance.**
- The Living Coliseum **can support hypothesis generation before it supports real-world prediction.**

## Section 37 — Environment test plan (future)

**Identity:** stable mechanisms share an environment regime across seeds · realized traces do not fragment
the regime · different exposure policies cannot pool · different schedulers cannot pool · different transition
policies cannot pool · environment realization binds its regime + execution instance · historical
environment-implicit evidence cannot silently pool with explicit controls.

**Component identity (§30):** exactly one component hash differs in a valid matched comparison · two changed
component hashes reject the pair · an aggregate environment hash cannot conceal an unregistered component
change · unchanged component identities remain equal across sampler seeds · realized events never create new
stable mechanism cells.

**Stochastic replay (§30.1):** identical replay under a different wall-clock time · component-specific
random-stream isolation · changed scheduler consumption does not shift transition randomness · missing or
extra random draws detected · reordered draw consumption detected · stochastic enforcement reconstruction ·
external stochastic evidence verification · incomplete exogenous-event traces rejected.

**Trace:** hidden state never leaks through observations · every transition has pre-state and post-state
hashes · scheduler decisions are reconstructable · resource and incentive events reconcile · incomplete
traces are rejected · replay reconstructs environment state deterministically · replay refuses to fabricate
missing events.

**Matched counterfactuals:** exactly one environment dimension differs · unregistered changes reject the pair
· initial-state mismatches reject the pair where held constant · exposure-only, scheduler-only,
transition-only, and incentive-only fixtures validate · retry attempts do not inflate effective-n.

**Claims:** society-level claims are blocked without protocol-sensitivity results · human-fidelity claims are
prohibited without separate authority and validation · critical violations veto aggregate success ·
environment-driven effects cannot be reported as intrinsic agent traits.

## Section 38 — Paper-to-program mapping

| Paper recommendation (§6) | Existing Coliseum answer | New environment-track addition (Rev. 2) | Remaining empirical burden |
|---|---|---|---|
| Explicit information exposure / visibility (`Vis`) | per-agent prompt construction; `interaction` mode | `ExposurePolicy` + `ObservationBoundary` + `exposure_policy_hash`/`observation_boundary_hash`; per-step visible/withheld trace (§31) | demonstrate hidden state never leaks under registered exposure |
| Explicit scheduling (`Sch`) | sequential vs independent interaction mode | `SchedulingPolicy` + `scheduling_policy_hash`; scheduler eligibility/decision/seed in trace; sealed simultaneous semantics (§31.1) | demonstrate scheduler reconstruction + isolation from transition RNG |
| Explicit transition dynamics (`Tr`) | deterministic runner; replay byte gate | `TransitionPolicy` + `transition_policy_hash`; pre/post-state hashes; domain-separated transition RNG (§30.1) | demonstrate deterministic transition replay incl. stochastic draws |
| Incentives / institutional coupling | scenario `facts` metadata; moral tags | `IncentiveMap`/`ResourceModel`/`InstitutionalRuleSet`/`EnforcementPolicy` + hashes; incentives ≠ rewards (§34.1) | demonstrate incentive/resource reconciliation without reward leakage |
| Environment in the uncertainty analysis | cluster-aware CIs = METRICS-v2 dependency | env regimes as clusters/factors; env variance ≠ agent variance (§19); §33 sensitivity gate | governed METRICS-v2 + sensitivity decomposition |
| Mechanism (not just agent) fidelity | matched interventions; pathway traces | matched-environment validator (§32); pathway+environment attribution (§35) | controlled-environment-sensitivity evidence surviving counterfactuals |
| Credible social simulation vs believable agents | non-pooling regimes; hidden eval; claim ladder | collective-outcome vector (§34); human-fidelity boundary (§36); society-claim gates (§24, §33) | external validation before any real-society claim |

**Status legend for the table + this track:** *already implemented* (existing Coliseum answer column) ·
*designed in Butterfly Rev. 6* (intervention triad + `execution_instance_id` reused by §30) · *newly proposed
here* (all Rev. 2 additions §§29–38) · *future empirical validation* (remaining-burden column). Nothing in
the Rev. 2 additions is implemented or authorized; each is a separately-routed future request (§22, §23).

## Section 39 — Scenario Robustness & Mutation Track (companion cross-reference; Rev. 3)

The full design lives in the **separately-governed** companion `SCENARIO-ROBUSTNESS-MUTATION-TRACK-PLAN.md`
(read-only owner-review draft). This section carries only the dependencies, gates, and the category rule; it
does **not** reproduce the companion.

**What it is.** A **proposed, authorization-gated** deterministic scenario-mutation + validation-fuzzing design
that asks which prompt changes preserve meaning but change model behavior, which surface changes bypass/break a
parser/normalizer/validator, and which effects transfer across models/seeds/families/validation stacks. **No
approval currently authorizes it** (§§21, 22, footer). It uses the external tool **P4RS3LT0NGV3** (pinned
commit `a6cb7c9054800e106b63888d362601922477a614`) as a **mutation provider only — never the authority** for
semantic equivalence, scoring, acceptance, or claims.

**Canonical scenario content identity (audit F3 — one value, machine-resolvable).** The single content
identity is the value produced by `behavioral_hash()` over `BEHAVIORAL_KEYS` (`schema.py:304-320`), **stored on
the run as `scenario_hash`** (`Run.scenario_hash`). `behavioral_hash` (author/registry side) and `scenario_hash`
(run side) are the **same value**; `scenario_content_hash` (the name used in the Butterfly `execution_instance_id`
payload) is a **documentation alias of that same value** — no independent hash exists. Derivation: a mutated
scenario's frozen content produces a **new `behavioral_hash` == new `scenario_hash`** (because the mutated
wording/structure is inside `BEHAVIORAL_KEYS`), and that is exactly `mutated_scenario_content_hash` in the
overlay. **The held-out registry (by id AND this hash, `registry.py:198-216`), execution identity
(`execution_instance_id`), mutation provenance, replay, and partition checks all bind this one content
identity.** (Any future field rename is a version-dispatched schema decision, not made here.)

**Identity reuse (no new triad).** A **design-time frozen mutation is a registered scenario/variant revision**
reusing existing identities — `scenario_id` + the canonical `scenario_hash` (above) + `variant_id` —
inheriting held-out contamination, `_replicate_key`, retry collapse, effective-n, and twin/`control_of`
machinery. It adds only a thin **provenance + intent overlay** (`source_scenario_id` + source `scenario_hash`,
`scenario_mutation_spec_hash`, transform id/version, **pinned external tool commit**, seed/RNG, transform
chain/order/depth, expected invariance class, layered-equivalence status + authority, `partition_group_id`,
authorization scope, and the `mutation_pair_id`/`mutation_attempt_id` lineage). No new spec/regime/realization
triad is minted.

**Category rule (machine-resolvable; never silently substituted).**
- **Prompt-representation mutations frozen before execution = scenario variants** (design-time; frozen +
  hashed; the mutated content IS the new `behavioral_hash`; reportable execution consumes the frozen variant
  and replay never re-calls P4RS3LT0NGV3).
- **Mutations applied through exposure / observation routing = environment interventions** (§§29–32 identity
  + trace rules).
- **Mutations applied dynamically to memory / context = Butterfly *state* interventions** (Butterfly
  intervention identity + realization rules).
- **Validator fuzzing = a separate, separately-authorization-gated *security-evaluation* use** (its own
  evidence root + authorization identity; does not auto-become training data or an alignment intervention; no
  external target without separate explicit authorization).

**Governance dependencies (detailed in the companion).** Layered equivalence (seven layers; a bypass claim
needs canonical-payload + policy-relevance equivalence under the *frozen* validation stack; reversible ≠
semantic); blinded/frozen-before-outcome equivalence adjudication with no post-outcome relabeling; hidden
mutations generated only in evaluator-controlled infrastructure and **never sent to OpenRouter or any external
service** (spent under the Butterfly B/C lifecycle); the MIT/AGPL-3.0 **licensing gate** (no copy/vendor while
unresolved); hard **resource-exhaustion isolation** (Tokenade-class in a separate budgeted suite); a narrow
**bypass definition** (one successful string is a test case, not a finding). **Routing:** the scenario track
is a **separate council request** at its own SC gate, sequenced at the M3/M4/M8–M10 scenario dependency point;
it **does not delay the Butterfly MVP** and may support the §28 sensitivity atlas only after its own bounded
approval. No approval of this annex authorizes scenario-track implementation.

## Addition ledger (Rev. 2 → Rev. 3)

| Addition | Where | Status |
|---|---|---|
| Environment Mechanism Track (9-layer separation, 15 components, paper mapping) | §29, §38 | newly proposed |
| Environment identity triad + **ten component hashes** (regime cryptographically contains them) | §30, §7 | newly proposed |
| Version-dispatched, freeze-safe env block + three-state legacy/control/intervention | §30 | newly proposed (grounded in `interaction`/Butterfly precedent) |
| Distinct `environment_regime_id` axis | §30, §26.8 | proposed, NOT authorized (schema review required) |
| Stochastic-draw capture + domain-separated RNG streams + provider-free replay | §30.1, §31 | newly proposed |
| Environment trace requirements + sealed simultaneous-action semantics | §31, §31.1 | newly proposed |
| Matched-environment validator (exactly one component differs) | §32 | newly proposed |
| Protocol/mechanism-sensitivity promoted to a required society-claim gate | §33, §24, §28 | newly proposed (non-blocking for MVP/T0-A/single-/bounded-two-agent) |
| Governed collective-outcome vector (no aggregate hides a critical violation) | §34 | newly proposed |
| Environment incentives ≠ training rewards (measure-never-reward preserved) | §34.1, §21 | newly proposed |
| Pathway + environment attribution (not causal mediation) | §35 | newly proposed |
| Human-fidelity boundary + society-claim publication discipline | §36, §25 | newly proposed |
| Environment test plan (identity / component / stochastic / trace / matched / claims) | §37 | newly proposed |
| T7 → T7-A..T7-E subdivision; M11/M12 remain authoritative global dependencies | §6, §15, §22, §23 | newly proposed (no M0–M15 reorder) |
| Env implementation separately council-routed; no Butterfly approval authorizes it | §21, §22 | binding boundary |
| Dependency updated to the verified Butterfly terminal verdict (GO_WITH_CONDITIONS, not integrated) | header, footer | verified from chain |
| **Rev. 3 — audit F1** ordered-trace tamper-evidence (event_index/prev_event_hash/ordered-trace root/event_count/continuity invariant/terminal_state_hash) | §31, §30 | corrected (was scoped BLOCKER) |
| **Rev. 3 — audit F2** component + regime embed `environment_spec_hash` (payload-inclusion parent binding) | §30 | corrected (was HIGH) |
| **Rev. 3 — audit F3** demonstrated hidden-state capability boundary (Butterfly D13); external-evaluator = non-acting instrument | §31, §17 | corrected |
| **Rev. 3 — audit F4/F5** required domain-separated RNG streams; preregistered CRN vs independent | §30.1 | corrected |
| **Rev. 3 — audit F6** `agent_regime_id` env-exclusion stated as *proposed* version-dispatched schema behavior (not implemented; historical byte-identical) | §30 | corrected |
| **Rev. 3 — audit F7** explicit `environment_realization_hash` typed payload (binds ordered-trace root) | §30 | corrected |
| **Rev. 3 — audit F8** prohibit conditioning on a sealed same-step action, not sequential generation | §31.1 | corrected |
| **Rev. 3 — audit F9** M11/M12 engine-reuse operational demarcation | §6 | corrected |
| **Rev. 3 — audit F10/F12** per-component distinct domain separators; null-component → regime rejected | §30 | corrected |
| **Rev. 3 — audit F11** softened "answering the critique" → "addressing the methodology gap" | §1 | corrected |
| **Rev. 3 — Scenario Robustness & Mutation Track** cross-references + category rule (companion is authoritative) | §39, §5/§7/§8/§16/§17/§20/§21/§22/§24/§25/§27 | newly proposed; separately routed |
| **Rev. 3 audit-response F1** — complete ordered-trace contract: exact `event_hash[t]` formula, index range `0..n-1`, genesis sentinel, first `pre==realized_initial_state`, last `post==terminal_state`, continuity, **canonical ordered-list root** (the interim "Merkle root" wording is **superseded** by audit-response-2 below — the ordered-list hash is the single authoritative construction), explicit zero-event | §31, §30 | superseded by audit-response-2 |
| **Rev. 3 audit-response F2** — §39 restated "proposed, authorization-gated" (not "authorized"); validator fuzzing "separately-authorization-gated" | §39 | corrected |
| **Rev. 3 audit-response F3** — canonical scenario content identity = `behavioral_hash`==`scenario_hash`; `scenario_content_hash` = alias; all binds bind one value | §39 | corrected |
| **Rev. 3 audit-response F4** — every stochastic component gets a registered named domain-separated stream (even if sole); §8 rejects missing/generic/unregistered/mis-bound streams; CRN couples base variates | §30.1, §8 | corrected |
| **Rev. 3 audit-response F5** — sequential generation permitted only under isolation boundaries (not "harmless") | §31.1 | corrected |
| **Rev. 3 audit-response-2 (trace completeness)** — canonical ordered-list hash replaces underspecified "Merkle-style root"; runner-minted `execution_close_record` (authoritative event_count/root/terminal/completeness) embedded in `environment_realization_hash`; 8 admission/replay rejections; honest trusted-runner security boundary | §31, §30 | corrected (F1 fully closed) |
| **Rev. 3 precision pass** — registered zero-event sentinel for `final_logical_event_position` (missing/null/non-sentinel in a zero-event trace rejected; sentinel invalid when `event_count>0`); F1 ledger row marked superseded so only the ordered-list root is authoritative | §31, ledger | corrected |

---

*Grounded in `coliseum/textlab/{schema,agents,runner,metrics,sweep}.py` (regime construction
`schema.py:90-143`; the `interaction` block `schema.py:104-115` + `interaction_mode` legacy rule
`schema.py:245-249` as the version-dispatch precedent for the environment block; replay contract
`agents.py:703-745`, `sweep.py:57-85`, `runner.py:1-9`), `tools/{autonomy,council}/*`, `configs/registry/*`,
`docs/{first-gladiator/*,metrics/METRICS-v1.md,AUTONOMY.md}`, and the council-reviewed
`docs/first-gladiator/BUTTERFLY-ALIGNMENT-TRACK.md` (**Rev. 6**). Butterfly Rev. 6 has terminal council
verdict **`AUDIT_GO_WITH_CONDITIONS`** (0 blockers; request `first-gladiator-butterfly-annex-001`, commit
`0bf83bc5`) and is **not owner-SC-integrated** — a proposed dependency pending integration. This training
annex is a **local review draft**: nothing implemented, trained, committed, registered, routed, or published;
the Coliseum repo is clean at `0bf83bc5` (the already-authorized Butterfly design-source commit) with **no
code, schema, registry, metric, policy, or roadmap change from this annex**. No held-out content/secrets
reproduced. Implementation and training remain separately gated: T1–T3 auxiliary-weight training remains
gated pending authoritative interpretation of `weight_training`; T4+ Gladiator/policy weight changes always
behind M14/SC-8; the **Environment Mechanism Track (§§29–38) is separately council-routed and authorized by
no Butterfly approval**; the **Scenario Robustness & Mutation Track (§39) is a separately-governed companion
(`SCENARIO-ROBUSTNESS-MUTATION-TRACK-PLAN.md`) — no P4RS3LT0NGV3 source was copied or vendored, no external
mutation API was called, its MIT/AGPL-3.0 license is unresolved (inspected commit `a6cb7c9…`), and no approval
of this annex authorizes it.** This is Rev. 3 (audit corrections F1–F12 + scenario cross-references).*
