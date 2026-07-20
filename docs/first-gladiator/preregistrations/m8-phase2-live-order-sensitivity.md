# Pre-registration — M8: live-model ordered-history experiment (Phase 2)

**Frozen design. Registered as `m8-phase2-live-order-sensitivity` (status:
pre-registered) in `configs/registry/experiments.yaml`; the design is frozen by
its `design_hash` over the registry entry's `planned_design`.** Phase 1
(`m7-scrambled-history-gate`, plain GO at events 001714 / 001719 / 001724,
commit `ac693b53`) admitted the *instrument*. This document points that
instrument at a live model for the first time.

**Live runs are NOT authorized by this document.** Executing any run of this
design requires the canonical owner SC-6 / live-execution authorization bound to
the exact design hash, candidate commit, model digest, run count, and budget. A
design `AUDIT_GO` is not permission to contact a provider.

## What Phase 2 is (and is not)

Phase 1 was **instrument calibration**: scripted deciders with pre-declared
order sensitivity, and the question was whether the pipeline recovered the known
answer. Phase 2 is a **discovery experiment**: the model's order sensitivity is
unknown, no answer is pre-declared, and **the null is expected to be a perfectly
good outcome**.

Phase 2 is not a test of memory, development, identity, personality, or
constitution. It measures one thing: whether the *presentation order* of an
otherwise matched experience set moves a terminal action distribution.

## Hypothesis (primary, pre-registered — null first)

**Operative H0 — the ONE canonical null of this design, stated verbatim
(machine-readable as `planned_design.null_form: distributional` +
`planned_design.null_statement`, design-hashed, and anchored in audited code
as `registry.M8_NULL_STATEMENT`):**

> Distributional (population-level) null: across the frozen 48-unit matched grid, presentation order does not change the population distribution of terminal actions — the marginal terminal-action distribution under order A equals the marginal terminal-action distribution under order B.

**H1:** the negation — presentation order changes the population distribution of
terminal actions, i.e. the marginal terminal-action distributions under A and B
differ.

This exact statement appears verbatim in the registry `hypothesis`, the
registry `primary_event`, the committed experiment config, the
operating-characteristics script, and the committed characterisation artifact.

**Claim scope (a-005, frozen), stated verbatim:**

> Claim scope: only the marginal terminal-action distribution is tested. Heterogeneous or cancelling unit-level order effects are OUT OF SCOPE; a non-rejection does not establish per-unit invariance.

The replicated per-unit design is a SEPARATE future preregistered experiment.

`Y` is the terminal `final_action` at the **`d_partner`** probe (frozen terminal
probe identity; nothing else may be measured); `A` is the developmental order,
`B` the identical admitted experience multiset in a permuted order, `C` the sham
control (A's order; agent-facing wording and formatting only).

**What the permutation test supplies, on whose authority, and the a-004 → a-005
supersession.** Audit a-004 first froze this design around a **sharp/per-unit**
null *(that framing is SUPERSEDED and preserved here only for the audit trail)*.
The owner's a-005 decision then **narrowed the operative null to DISTRIBUTIONAL
(population-marginal)**: a-005 reproduced that the aggregate `TV(A,B)` statistic
is blind to balanced unit-level effects — a fully discordant cancelling pack (24
units share→decline, 24 decline→share) leaves a sharp null false at every unit
yet has exactly equal A and B marginals, so a sharp *claim* riding a marginal
*statistic* was a mismatch. The owner narrowed the claim to the statistic. This
changed the claim vocabulary and the claim ceiling, not the arithmetic. The
within-unit paired permutation supplies the **reference distribution under
exchangeability** (which implies marginal equality), a valid level-alpha
reference for the marginal `TV(A,B)` statistic; the design does **not** claim
the test is exact for bare marginal equality. A rejection evidences a
**marginal-distribution difference only**, never a per-unit claim; a
non-rejection evidences only "no distributional order effect observed at the
detectable threshold" and never per-unit invariance (balanced cancelling
unit-level effects keep the marginals equal — out of scope). An earlier registry
note claiming exchangeability is "implied by H0" was **false** and was removed
(audit 001828 finding 1).

No stronger alternative is authorized at this stage.

## Design decision: the history is imposed, not authored

*This is the most consequential change from Phase 1 and is flagged explicitly
for independent design audit.*

In the Phase-1 scenarios each event decision point offers two actions
(`acknowledge`, `reflect`). Both write the identical `state_delta`, the identical
outcome `narrative`, and the identical `next` — the world effect is already
choice-independent. **But `runner.py:365` appends `action_id` and `action_label`
to the agent-visible history.** Under a deterministic scripted decider the
realized path is a function of the events, so A and B histories differ only by
order. Under a live model it may choose `acknowledge` at the betrayal in A and
`reflect` at the same event in B — and then the terminal prompts differ in
**content**, not merely order.

That silently voids the experiment's central invariant. `lint_scramble_triplet`
cannot catch it: the lint is a static scenario check and runs upstream of the
only place the property can break.

**Resolution: the Phase-2 event points are *exposure points* — exactly one legal
action.** The experience sequence becomes identical-except-order by construction,
and the terminal probe is the only free choice, which is also the only measured
outcome. The owner directive requires "A/B matched except order" and, for
positive promotion, that "no content mismatch exists"; exposure points are the
narrowest change that makes those properties true rather than assumed.

**This does not weaken the existing cardinality invariant.** `schema.py` requires
a decision point to offer ≥ 2 actions, and `training/actions.py` binds
`LegalActionSet` to that bound under audit 000886. That invariant is correct and
stays intact **for decisions**. What was wrong is its *domain*: a point that
delivers a world event and admits no choice is not a decision at all. Phase 2
therefore introduces an explicit exposure kind — a decision still requires ≥ 2
actions, an exposure requires exactly 1, the two are mutually exclusive, and
exposure points are excluded from legal-action-set training export rather than
admitted as degenerate singleton universes. Audit 000886's guarantee is narrowed
to its true subject, not relaxed.

**The sham remains a live control under imposed history — verified, not assumed.**
A fair objection to imposing the history is that it might make `TV(A,C) = 0` true
by construction, leaving the formatting control vacuous. It does not, because the
two manipulations enter the terminal prompt by **different channels**:

| Contrast | Agent-visible history | Terminal probe wording | Isolates |
|---|---|---|---|
| A vs B | differs (permuted) | identical | temporal **order** |
| A vs C | identical | reworded | **surface form** |

Confirmed empirically on the built scenarios with a scripted decider: the
terminal `history_prompt_hash` is byte-identical for A and C and differs for B,
while the sham reworsds `d_partner`'s decision text — the measured prompt — in
both variants. So C still perturbs the surface the outcome is read from, and a
non-null `TV(A,C)` remains a real, reachable failure mode that voids the order
claim. This reproduces the attestation the Phase-1 design relied on
(`history_prompt_hash` attests A/B differ and A/C are identical) rather than
weakening it.

**Why not change the history schema instead.** An alternative was to keep two
actions and stop recording the agent's own action in the history (a versioned
`HISTORY_SCHEMA_VERSION` bump). That was rejected because the history block is
rendered into the **terminal probe's** prompt — the exact surface where `Y` is
measured — so it would alter the measured prompt relative to the calibrated
Phase-1 shape. Exposure points confine the novel prompt surface (a one-option
menu) to the *unmeasured* event points and leave the terminal prompt structurally
identical to Phase 1.

Consequences, stated plainly:

- Phase 2 measures **order of imposed experience**, not self-authored
  trajectory. Whether a model's own choices compound into divergence is a
  different and harder experiment, and is **not** what this design tests.
- A parse failure at an event point can only resolve to the single legal
  action, so instrumentation artifacts are confined to the terminal probe.
- The Phase-1 scenarios are **not modified.** Phase 2 uses a new triplet
  (`scramble_dev_m8`, `scramble_perm_m8`, `scramble_sham_m8`) with its own
  behavioral hashes, so Phase-1 evidence continues to regenerate byte-identically
  and its three GO verdicts remain bound to unchanged artifacts.

## Model regime (frozen)

| Field | Value |
|---|---|
| Model | `huihui_ai/qwen2.5-abliterate:7b-instruct` |
| Digest | `103482475c9b4d4032999dd5d7383478cad8b966ae6ae984d525daf7352c2219` |
| Driver | `ollama_local` (`OllamaAgent`, stdlib HTTP) |
| Backend version | resolved by `resolve_effective_config()` before the regime is hashed |
| Prompt template | `PROMPT_TEMPLATE_VERSION = "1"` + `PROMPT_TEMPLATE_HASH` |
| Parser | `PARSER_VERSION = "3"` (refuses multiple answer-shaped JSON objects as `ambiguous_json`) |
| Arbitration | `planner_priority` |
| Interaction mode | `sequential_history` |
| Think mode | `think_requested: "off"`; effective mode resolved before hashing |
| Reflex budget | `{num_predict: 80, timeout_s: 30}` |
| Planner budget | `{num_predict: 350, timeout_s: 120}` |
| Temperature | `0.7` (stochastic — see Sampling) |
| Context length | `num_ctx = 8192` — **sent explicitly** and the **effective** value resolved by `resolve_effective_config()` before the regime is hashed (see below) |
| `top_p` | `0.9` (explicit — never a backend default) |
| `top_k` | `40` (explicit) |
| `repeat_penalty` | `1.1` (explicit) |
| `stop` | `[]` (explicit empty set — the model is never truncated by an unfrozen stop) |

**Every decoder control is explicit, sent, and hashed (audit b-002 finding
f0).** A model regime is not frozen if any output-distribution knob is left to a
backend default: finding f0 reproduced two hosts with the same digest and backend
version but a **different effective context length** executing and pooling under
one `agent_regime_id`. The frozen decoder controls above (`num_ctx`, `top_p`,
`top_k`, `repeat_penalty`, `stop`) are folded into `OllamaAgent`'s sampling
config (`agents.M8_DECODER_CONTROLS`), emitted on **every** request, and enter
`spec_dict()` → the agent block of the behavioral_config → `agent_regime_id`, so
varying any one of them yields a different regime id. The **effective** context
length is additionally **resolved before the hash**, exactly as think-mode and
`backend_version` are: `resolve_effective_config()` clamps `num_ctx` to the
model's `/api/show` context capability, so a host serving a build with a smaller
context cannot silently pool with one that honors the full request. The values
are pinned identically in `planned_design.decoder_controls` (design-hashed), the
committed config, and `registry.M8_FROZEN_PROFILE` (audited code); both
provenance lints refuse omission or substitution of any control independently of
`design_hash`.

**Model selection, and why.** The draft manifest carried `gemma3:latest` @
`a2af6cc3…`. Both candidates are available and both digests verify:
`gemma3:latest` @ `a2af6cc3…` is served by the LAN host and matches the draft's
pin exactly; `huihui_ai/qwen2.5-abliterate:7b-instruct` @ `103482…` is present on
both the local and LAN hosts and matches the governed Live Persona pilot's
`PILOT_MODEL_DIGEST` byte-for-byte. Availability therefore does **not** decide
this. Qwen is selected because (a) the owner directive states a preference for
the already-governed Live Persona regime, (b) it is the only candidate with
prior governance on this program, and (c) a 7B instruction-tuned model is more
likely to satisfy the frozen JSON contract than a 4B one, which directly lowers
the non-decision rate the admissibility policy bounds.

**Declared regime characteristic:** this is an *abliterated* (refusal-suppressed)
build. That is a property of the frozen regime, not a defect, and it is recorded
here because the scenario content involves betrayal and broken trust, where
refusal behavior could otherwise act as an uncontrolled moderator. Every claim
from this experiment is scoped to this regime and does not transfer to a stock
build of the same base model.

**Host is infrastructure, not behavior.** Per `agents.py`, `$OLLAMA_HOST` never
enters the lineage hash, but the resolved `backend_version` does. The entire pack
must therefore execute against a **single** Ollama host and backend version; the
LAN host currently reports `0.32.0`. Splitting a pack across hosts of differing
versions would silently create two regimes.

Any substitution of model, version, quantization, prompt template, context
length, decoding regime, parser, or a material Ollama version constitutes a **new
regime** and may not pool with this one.

## Sampling and effective units

Decoding is **stochastic** (temperature 0.7). This is a deliberate scientific
choice: the estimand is a *distribution* over terminal actions, and a
deterministic decoder yields one draw per unit — no distribution to compare and
no way to separate signal from sampling noise.

- **Effective unit:** `(variant_id, scenario_seed, sampler_seed)`. Repeated
  execution of the same effective unit is **not** new evidence.
- `scenario_seeds` = `{42, 1}` → variants `v0_caravan`, `v1_workshop`.
- `sampler_seeds` = 24 frozen values, `2001 … 2024`.
- **The same 24 sampler seeds are used in all three conditions**, so every unit
  pairs across A, B, and C — the comparison is matched at the unit level.
- Per condition: 2 × 24 = **48 effective units**. Total **144 runs**
  (3 conditions × 48), each 4 decision points × 2 passes = **1152 model calls**.
- **Noise-floor split (frozen before execution):** `S₁ = {2001…2012}`,
  `S₂ = {2013…2024}`. Condition A is split along this fixed partition to
  estimate within-condition sampling noise. The assignment is declared here and
  may not be re-drawn after seeing outcomes.
- `retries_per_unit = 0`. No undeclared retry. A failed unit is a typed
  outcome, never a re-roll.

Seeded sampling must be **verified, not assumed** — the seed probe must
demonstrate same-seed reproducibility *and* different-seed divergence at the
real planner budget on a high-entropy prompt. A backend that silently ignores
`options.seed` must fail the probe, not pass it. Any run whose probe fails is
excluded with reason `backend_seed_unverified`.

## Analysis rule (pre-registered)

**Analysis timing / stopping rule (frozen, a-005 finding 1), stated verbatim:**

> Analysis timing (frozen): the analysis is performed exactly once, after the complete 144-run pack has closed; there is no interim analysis, no early stopping, no adaptive continuation, and no outcome-dependent addition or removal of units, seeds, scenarios or conditions.

This is fixed by a structured `stopping_rule` block in `planned_design`
(`analysis_timing: complete_pack`, `analyses_total: 1`, `interim_analyses: 0`,
`early_stopping: false`, `adaptive_continuation: false`,
`outcome_dependent_composition: false`, `pack_runs: 144`,
`matched_units_per_condition: 48`), design-hashed, mirrored into the committed
config, and lint-enforced independently of the self-derived hash. A partial pack
yields no verdict.

1. **Admission.** A run enters analysis only if it is `reportable`,
   `stochastic_reportable`, carries a matching `agent_regime_id` and
   `agent_config` across all conditions, and its terminal decision is
   **admissible** (the pass that produced `final_action` was not a parse
   fallback). Non-admissible terminal decisions are counted and reported per
   cell, never silently dropped and never re-pointed at an earlier decision.
2. **Distributions.** Per condition, the normalized distribution of terminal
   `final_action` over admissible effective units.
3. **Distances.** `TV(P,Q) = ½ Σ_y |P(y) − Q(y)|` for `TV(A,B)`, `TV(A,C)`, and
   the within-condition null `TV_null = TV(A|S₁, A|S₂)`.
4. **Uncertainty and the null model.** The null against which an observed
   distance is judged is a **paired permutation null**, not a split-half noise
   floor. For each of the 48 matched effective units — the same
   `(variant_id, scenario_seed, sampler_seed)` triple exists in every condition
   — the two conditions' terminal actions are exchanged with probability ½, the
   distance is recomputed, and the procedure repeats for
   **`permutation_iterations = 10000`** under **`permutation_seed = 20260719`**.
   The decision quantile is the `1 − alpha` percentile of that null, with
   **`alpha = 0.05`**. A percentile bootstrap (same iterations and seed) is
   retained for reporting intervals on the observed distances.

   **What the test is a valid level-`alpha` reference for, and the claim it
   licenses.** A paired permutation test draws its reference distribution from
   *within-pair exchangeability* — that for each matched unit, the condition
   label may be swapped without changing the joint law. Exchangeability implies
   equality of the A and B **marginal** distributions, so the paired
   permutation is a valid level-`alpha` reference for the marginal `TV(A,B)`
   statistic. The design does **not** claim the test is exact for bare marginal
   equality: two conditions can share a marginal distribution while their
   outcomes are dependent within a unit in an asymmetric way, and under that
   weaker hypothesis alone the test is not exact. The operative null is
   therefore stated at the level the statistic actually resolves — the
   **distributional (population-marginal)** null (audit a-005, which SUPERSEDED
   the earlier sharp/per-unit framing).

   Because the statistic is the marginal `TV(A,B)`, the claim ceiling is the
   marginal distribution and nothing finer: a rejection evidences a
   **marginal-distribution difference only** and never identifies which units
   changed; a non-rejection evidences only "no distributional order effect
   observed at the detectable threshold" and does **not** establish per-unit
   invariance, because balanced cancelling unit-level effects can leave the
   marginals equal (out of scope). The result report must state this
   distributional claim ceiling explicitly.

### Why the split-half noise floor was replaced

*Recorded because it was found by the design's own required characterisation,
before any execution, and because the correction changes an inferential core.*

The original rule estimated the noise floor as `TV(A|S₁, A|S₂)` — a distance
between two **24-unit** halves of A — and compared it against `TV(A,B)`, a
distance between two **48-unit** samples. Total variation between empirical
distributions is biased upward at small n, and the two quantities therefore
carry **different small-sample inflation**: the null is systematically larger
than the statistic it is meant to calibrate, purely because it is computed on
half the data. The bias is a property of the split, not of the evidence.

Simulation at the frozen n=48 over the 4-action menu measured the null's upper
bound at ≈0.49 — well above the design's sub-0.5 resolving-power ceiling. The
sensitivity precondition therefore refused every arm, including one with a
genuine effect at TV(A,B)=0.6: **false-positive rate 0.000, power 0.000.** A
design that cannot detect an effect of any size is not conservative, it is
inert.

A paired permutation null fixes the cause rather than the symptom. It draws its
reference distribution from within-pair exchangeability, supplied by the paired
matched construction (marginal equality alone would not supply it — see the
hypothesis section), it uses the actual matched sample sizes so no size mismatch exists,
it consumes no additional live runs, and it respects the pairing the design
already guarantees. The rejected alternatives
are recorded to show the choice was not the convenient one: raising
`min_detectable_effect` above the noise floor would have "worked" while
admitting only enormous effects — the reinterpret-to-rescue move this
preregistration forbids; enlarging n would have shrunk the inflation without
removing the mismatch, at several times the live-run cost.

`noise_floor_split` is **retained as a reported diagnostic** of within-condition
stability. It is no longer decisive and no longer gates any verdict.

## Admissibility policy (frozen)

| Bound | Value |
|---|---|
| `max_non_decision_rate` (per condition cell) | `0.20` |
| `max_non_decision_rate_delta` (across any compared pair) | `0.05` |
| `min_admissible_effective_n` (per cell) | `20` |
| `on_violation` | `refuse` |

The delta bound is the scientifically load-bearing one. Differential parse
failure across conditions is itself the confound: because a fallback resolves to
the first available action — identical in all three conditions — a condition
whose rendered history provokes more malformed output would pile mass on one
specific terminal action and produce `TV(A,B) > 0` that is a pure formatting
artifact.

On violation the aggregator **refuses and does not compute distances at all**.
It reports the offending cells, their rates, the bound, and the policy version.
A refusal is an inconclusive result, never a number to be interpreted.

## Primary event (decision rule)

The analysis callable is **`metrics.order_sensitivity_report`** at
**`ORDER_REPORT_VERSION 5`** — the ONE version literal this document pins, and
it appears nowhere in this document at any other value (audit a-004 finding 0
found a 3-vs-4 disagreement here; corrected). The version has been bumped once
per change to the decision rule or its claim ceiling, so any emitted verdict is
traceable to the rule that produced it: v1 the bootstrap-bound comparison
against a split-half floor; v2 the paired permutation null; v3 the corrected
asymmetric sensitivity requirement; v4 the mandatory clause-0 evidence admission
and the clause-2 sham-adequacy warrant; v5 (current, owner a-005) the operative
null narrowed to **distributional** — the six-clause ordered rule and its
arithmetic are unchanged, but the emitted verdict vocabulary
(`distributional_order_effect_observed` / `no_distributional_order_effect_observed`)
and the claim ceiling change, so a v4 (sharp-claim) report can never be mistaken
for a v5 (distributional-claim) one. The registry entry's
`primary_event` is the authoritative statement of the frozen rule, and the
lint fails a design whose version marker disagrees with it, consuming the
frozen `admissibility_policy` and `thresholds` loaded from this experiment's
registry entry. The Phase-1 comparator
`metrics.scramble_terminal_distribution` is **explicitly NOT the Phase-2 analysis
path** — it admits parse fallbacks as decisions and is demonstrated in this
candidate to return a clean null from wholly unparseable output. Naming it here
would freeze the exact unsafe path this design exists to avoid.

Let `q_AB` and `q_AC` be the `1 − alpha` quantiles of the paired permutation
nulls for A vs B and A vs C. The rule (`ORDER_REPORT_VERSION 5`) is evaluated in
this order, and **no distance, quantile, or verdict may be computed or emitted
once any admission clause refuses**:

0. **Evidence admission (all mandatory, refusal is typed):**
   - every candidate run must carry a successful **provider-free replay**
     attestation bound to that exact run identity — `reportable` /
     `stochastic_reportable` booleans alone are never sufficient (audit 001832
     finding 1);
   - the measured node of every included run must be the frozen terminal probe
     — `dp_id == d_partner`, point kind decision, exactly one such admissible
     record; missing, duplicate, out-of-order, or exposure-kind terminal
     evidence refuses with `missing_terminal_probe` — the terminal is **never**
     inferred from list position (audit 001834 finding 3);
   - both comparisons must realize the **full frozen matched-unit grid**:
     `matched_units == 48` for A|B and A|C; any unit-identity mismatch refuses
     — unmatched units are never silently held fixed (audit 001834 finding 2);
   - `max_surviving_delta` is a **required** threshold, loaded from the frozen
     registry bundle and enforced here before any statistic: per-condition
     surviving counts spreading beyond it refuse (audit 001834 finding 1).
1. If the admissibility policy refuses, or effective n falls below the floor:
   **inconclusive**.
2. **Sham-control adequacy** (audit 001828 finding 2 — a sham *non-rejection*
   needs a warrant exactly as a null claim does): the order claim requires
   **both** `TV(A,C) ≤ q_AC` (no rejection) **and** `q_AC < sham_equivalence_margin`
   (strict — the sham comparison could actually have detected contamination of
   the margin size). If `TV(A,C) > q_AC`: **inconclusive** — the sham is not
   null, which voids any order claim. If `q_AC ≥ sham_equivalence_margin`: the
   sham warrant is missing; a positive verdict is unreachable and the outcome is
   at most **inconclusive** past clause 3.
3. Else if the observed `TV(A,B)` **exceeds** `q_AB` **and** the sham warrant of
   clause 2 holds: **distributional order effect observed**
   (`distributional_order_effect_observed`) — a marginal-distribution difference
   only, never a per-unit claim.
4. Else if `TV(A,B) ≤ q_AB` and `q_AB ≤ min_detectable_effect`: **no
   distributional order effect observed**
   (`no_distributional_order_effect_observed`) — this does **not** establish
   per-unit invariance.
5. Else: **inconclusive**.

**`sham_equivalence_margin = 0.25`**, frozen in `planned_design.thresholds`
and covered by `design_hash`. The margin is **deliberately decoupled from
`min_detectable_effect`** (audit a-004): the two bounds answer different
questions — the MDE is what the A/B test can resolve, the margin is what the
sham comparison must have been able to detect — and enlarging the margin
would *weaken* the sham-adequacy warrant (`q_AC < margin` becomes easier to
grant). The margin therefore never follows the detectable boundary upward; it
stays at 0.25, the smallest contamination scale this program has ever claimed
to police, whatever value the MDE freezes at. The audit's pinned boundary
case — `TV(A,C) = q_AC = 0.25` with decisive A/B separation — is
**inconclusive** under the strict inequality, never a positive.

### The sensitivity requirement is asymmetric, and deliberately so

*Corrected after the paired permutation null replaced the split-half floor. The
original formulation gated **both** branches on `q_AB ≤ min_detectable_effect`,
carried over from v1 without re-derivation. That is wrong here, and the error is
recorded rather than quietly patched.*

Under the split-half null an inflated floor genuinely broke both directions: it
could swallow a real effect *and* dress an unidentifiable pack as a null. Under a
permutation null it does not, because **`q_AB` is the rejection threshold
itself**. If the observed distance exceeds it, the null has been rejected at
`alpha` — and that is a valid positive finding whether or not a *smaller* effect
would also have been detectable. Sensitivity constrains what may be concluded
from a **non**-rejection; it cannot invalidate a rejection.

The symmetric rule produced a perverse result, pinned in the tests: at total
separation over near-two-point support, `TV(A,B) = 1.0` against `q_AB = 0.2917`
— a decisive rejection — was reported **inconclusive** solely because
`0.2917 > 0.25`. A maximal, unambiguous effect would have been discarded.

So the requirement attaches only where it is meaningful: a **null** claim asserts
"no effect at or above `min_detectable_effect`," and that assertion is
unsupportable unless the test could actually have resolved an effect of that
size. A **positive** claim asserts only that this comparison rejected, and needs
no such warrant.

**What an `inconclusive` from clause 5 does and does not mean.** It means the
pack neither rejected nor earned the right to assert absence. It is **not**
evidence of absence, and must never be reported as a null result.

**Inconclusive** arises from clause 1 (the admissibility policy refuses, effective
n falls below the floor, per-condition surviving counts differ by more than
`max_surviving_delta`, the seed probe fails, or digest drift is detected); from
clause 2 (**the sham is not null** — a failed sham voids the order claim
outright, is reported as instrument or surface sensitivity, and is never rescued
post hoc); or from clause 5 (no rejection, and `q_AB` above
`min_detectable_effect`, so the pack has not earned the right to assert absence).

### Why a sensitivity requirement is needed at all

Without one the null branch is degenerate at high noise. Reproduced at the exact
declared sample size: a fully admissible 144-unit pack with `A|S1` entirely
`share_resource`, `A|S2` entirely `verify_first`, `C` identical to `A`, and `B`
entirely `decline_partnership` — A and B **maximally separated, empirically
disjoint** — was returned by the original v1 rule as
`no_order_effect_observed` (the superseded v1 verdict name),
because its split-half floor `TV_null=1.0` was not strictly exceeded by
`TV(A,B)=1.0`. A maximally unstable instrument would have closed the gate with a
"successful null" and the downstream track would have advanced on it.

Under the current rule that pack is `distributional_order_effect_observed`: clause 3 fires on a
genuine rejection before clause 4 is ever reached. **The invariant the ceiling
exists to protect is unchanged and now holds by construction — that pack can
never be reported as a successful null.** What changed is which clause protects
it, and that the protection no longer costs valid rejections.

The requirement therefore attaches to clause 4 alone. It governs what a
*non*-rejection is entitled to assert, never whether a rejection counts.

### Frozen operating characteristics and fitness criteria (audit a-004)

The criteria that declare this finite-sample design fit to run are **frozen in
`planned_design.thresholds`, covered by `design_hash`, and anchored in audited
code** — they are never invented or adjusted inside the characterisation
script (audit a-004 finding 1 blocked exactly that):

- **`type_i_criterion` (frozen string): "CP-95 upper bound of distributional-null
  rejection rate <= alpha".** The **upper** bound: only an upper confidence
  limit at or below `alpha` supports the claim "type-I error is at or below
  alpha". The superseded script-invented check bounded the *lower* limit,
  which tests only whether excess above alpha was *demonstrated* — the wrong
  direction, and it is banned by lint.
- **`power_target = 0.8`.** The measured power at `min_detectable_effect` must
  reach this value at its Clopper-Pearson 95% **lower** bound.

**How `min_detectable_effect` is frozen (method, declared before the value):**
the committed characterisation runs the frozen procedure's power curve at
`n = 48` across the effect grid `0.25 / 0.35 / 0.5 / 0.75 / 1.0` (total
variation from the graded base; the 1.0 endpoint uses disjoint supports since
TV = 1.0 is unreachable from a full-support base), and
`min_detectable_effect` is the **smallest grid effect whose measured power's
CP-95 lower bound reaches `power_target`** under the exact frozen procedure.
The artifact's `mde_selection` block recomputes that choice from the
committed run, so the frozen value regenerates from the artifact alone.
`power_target` is never shrunk to rescue a smaller boundary.

**Measured result (committed artifact, 10000-iteration null, 400 trials per
charged arm).** The rule yielded:

| Effect (TV) | Measured power | CP-95 interval | Meets `power_target = 0.8`? |
|---|---|---|---|
| 0.25 | 0.800 | [0.757, 0.838] | **no** — lower bound 0.757 < 0.8 |
| **0.35** | **0.9925** | **[0.978, 0.998]** | **yes — frozen MDE** |
| 0.50 | 1.000 | [0.991, 1.000] | yes |
| 0.75 | 1.000 | [0.991, 1.000] | yes |
| 1.00 | 1.000 | [0.991, 1.000] | yes |

So **`min_detectable_effect` is frozen at `0.35`** — the **distributional
detectable-effect floor**, the honest smallest grid effect the design reliably
resolves (value unchanged at the a-005 re-framing; only its description is now
distributional). The point estimate at 0.25 was exactly
0.80, but its lower confidence bound fell short of the target, and neither the
value nor `power_target` was adjusted to make 0.25 pass. **Effects between
`0.25` and `0.35` total variation are real possibilities this design cannot
reliably detect at `n = 48`; an inconclusive outcome in that band is expected
and is not a null result.** The four distributional-null type-I arms all measured
`0/400` (CP-95 upper bound `0.0092 <= alpha = 0.05`).

**The sham-equivalence margin is intentionally tighter than the MDE.**
`sham_equivalence_margin = 0.25 < min_detectable_effect = 0.35`: the sham
control must exclude surface-form contamination at a **finer** resolution
(0.25) than the order effect the design claims to detect (0.35). This is the
scientifically conservative direction — raising the margin to 0.35 to "match"
the MDE would *weaken* the sham warrant (`q_AC < margin` becomes easier to
grant) — so the two bounds are deliberately decoupled.

**The null arms must mechanically satisfy the canonical distributional null**
(audit a-004 finding 0, held through a-005): a distributional-null H0 trial
generates each matched unit's terminal action **once** and copies it across
A/B/C exactly — identical schedules have identical marginals, the design
declares no condition-independent noise, so none is applied — and every
generated schedule is verified **unit-by-unit before analysis** (concordant by
construction); named alternative arms are verified to violate it on
their declared axis. Under seeded per-unit decoding this is the faithful
model, not a convenience: if order (or the sham rewording) truly makes no
difference to a unit's computation, the realized terminal action is
identical. A structural consequence, stated honestly: under the distributional
null so constructed the observed pack is condition-invariant, so the
false-rejection rate is exactly zero and the frozen type-I bound holds
mechanically — the paired permutation test at its own reference distribution,
exercised end-to-end rather than assumed.

**The former iid equal-marginal "H0" arms are relabeled, not deleted**: A, B,
C drawn iid from one distribution makes the *pair* distribution exchangeable
— so the test still rejects near or below `alpha` for that broader family,
reported as robustness context — but each such pack has equal marginals only in
expectation while disagreeing unit by unit (the audit measured 27–44 discordant
units per pack), so those rates are exchangeability-robustness context, never
charged as distributional-null type-I. The dependent shared-latent two-mode
process from audit 001828 finding 1 is characterised in both halves: the null
holds within mode (equal marginals across conditions, charged type-I) and the
separating case where within-pack A/B marginals differ (reported as correct
detection).

**Power is characterised with the sham axis holding the null** (`C` copied from
`A`, verified): under the unified null form that is what "the sham is truly
null" means. The exchangeability-context arms show the design's behavior
when the sham axis is null only in distribution — the warrant frequently
refuses and the pack goes inconclusive, which is conservative, never
anti-conservative. The sham-gate's residual process-level leakage over a
contaminated-at-MDE sham is reported with its CI as context; the frozen
fitness criteria are exactly `type_i_criterion` and `power_target`, and the
absolute observation-level sham guarantees (the boundary pack never
promotes; every positive carries the warrant) are pinned deterministically
in the test suite.

The characterisation uses the exact frozen decision parameters — including
`permutation_iterations = 10000` and `bootstrap_iterations = 10000`, never
substituted smaller values — with 400 outer trials per charged arm and exact
Clopper-Pearson intervals reported, not point estimates (audit 001828
finding 3). It is committed as an artifact produced by the same frozen
threshold bundle the production path loads; a CI regression asserts echo and
hash equality, recomputes every interval and criterion from the tallies, and
fails if the exact `n = 48` characterisation misses any frozen target. A
design that misses them is not fit to run and must be corrected **before**
execution rather than reinterpreted after.

Phase 1's exact thresholds (ε = τ = 0) are **not** carried over. Zero thresholds
are coherent only for a deterministic decider whose terminal action is a
function value; for a stochastic decider they would report a fake effect from a
single differing draw. This is a correction to the Phase-1 posture, made before
any outcome is seen.

## Rival explanations

The result report must state which of these remain viable:

1. **No-history model** — `Y = f(terminal prompt)`
2. **Recency model** — `Y = f(latest event)`
3. **Event-set model** — `Y = f(M(H))` (multiset, order-blind)
4. **Ordered-history model** — `Y = f(H)`
5. **Narrative-prior model** — `Y = f(familiar story structure)`
6. **Position or formatting artifact**
7. **Parser or instrumentation artifact**

This experiment can separate (3) from (4) — that is its purpose — and uses C to
bound (6). It **cannot** by itself separate (2) from (4): a recency-driven model
and a genuinely order-integrating model both produce `TV(A,B) > 0` here. Nor can
it defeat (5). Those require the separately preregistered follow-ups named below.
(7) is bounded, not eliminated, by the admissibility policy.

## What may NOT be claimed

**Maximum positive claim** *(capped at the distributional level per owner audit
a-005; a rejection evidences a marginal-distribution difference only, never a
per-unit claim)*:

> Under the frozen live-model regime, the paired permutation test rejected the
> distributional null: the population (marginal) distribution of terminal actions
> under order A differs from that under order B. This is a population-level
> (marginal) claim only — it does not identify which units changed or in which
> direction, and does not establish any per-unit order effect.

**Maximum null claim** *(the permitted null-result language, verbatim)*:

> No distributional order effect was observed at the experiment's
> detectable-effect threshold.

This does **not** establish per-unit invariance: balanced cancelling unit-level
effects can leave the marginals equal (out of scope for this experiment's claim).

**Maximum inconclusive claim:**

> The frozen experiment did not identify an order effect because the
> preregistered sham, evidence, completeness, or uncertainty requirement failed.

Not claimable under any outcome: personality, memory formation, trauma, identity
change, a soul, a Platonic constitution, general developmental sensitivity,
human equivalence, or universal path dependence. A result registers as an
**observation** only — not replicated, accepted, mechanistic, developmental, or
philosophical.

The estimand is explicitly **conditional on parseability**: excluding
non-decisions makes this a distribution over *decisions the instrument could
read*, which is not the unconditional distribution. Report it in those words.

## Replay contract and its limit

Every admitted run must replay **without contacting the provider**, via
`ReplayLLMAgent` serving the recorded `raw_text`, and the derived report must
regenerate byte-identically from the evidence bundle.

**This is weaker than Phase 1's replay claim and must not inherit its language.**
Phase-1 scripted runs re-executed their deciders live, so replay verified the
whole causal path. An LLM replay re-exercises the **parser, arbitration, and
scenario machinery against frozen model output**. It does not verify the model,
and it is not evidence that the model would produce the same output again. It is
a tamper-evidence and determinism-of-analysis guarantee, nothing more.

## Failure and exclusion rules (typed, frozen)

Every outcome below is recorded and counted; none is silently discarded.

| Type | Treatment |
|---|---|
| Parse failure at the terminal probe | non-decision; excluded from distributions, counted in the census, charged against the admissibility bounds |
| Parse failure at an event point | resolves to the single legal action; recorded, no distributional effect |
| Provider timeout / connection failure | run excluded; counted per condition as dropout |
| Digest drift mid-pack | **pack aborts**; evidence quarantined; no partial analysis |
| Seed probe failure | run excluded, reason `backend_seed_unverified` |
| Per-condition surviving counts differing by more than `max_surviving_delta` | **refuses** — inconclusive |

Per-condition dropout counts must be **compared, not merely reported**:
differential dropout is observationally identical to an order effect, because the
surviving units in the affected condition are a biased subsample.

**`max_surviving_delta = 2`** (absolute spread between per-condition surviving
counts), frozen here and covered by `design_hash`. Two justifications: it is
≈5 % of the 48 units per condition, matching `max_non_decision_rate_delta`; and
it is deliberately the **tighter** of the two mechanisms in kind, because a
non-decision is *counted and visible in the census* whereas a dropped run is
simply **absent** — invisible loss warrants a stricter bound than visible loss.

Stating the bound is not enough: it must be **unskippable**. The balance gate
takes a caller-supplied bound and is bypassed entirely when that argument is
absent, so the Phase-2 execution and report path must load
`max_surviving_delta` from the frozen registry and a Phase-2 pack must be unable
to complete an analysis without it. A guard nobody is obliged to call is not a
guard.

## Execution discipline

Conditions must be **interleaved, not blocked**. Running all of A, then all of B,
then all of C perfectly confounds condition with backend state — thermal
throttling, KV-cache/context-shift state, another tenant forcing a model
unload/reload, or a server restart all drift across a 144-run pack. Execution
order is `(scenario_seed, sampler_seed) → condition`, so A/B/C for a given unit
are drawn adjacently, and the execution index is recorded.

## What must not change after execution begins

Thresholds, prompts, event valences, event order, the terminal probe, parser
rules, metric definitions, exclusions, sample size, seeds, the noise-floor split,
the bootstrap seed, and interpretation boundaries. If an implementation defect is
found after execution: quarantine the affected evidence, record the defect,
repair in a new commit, update design identity, obtain the required verdict,
rerun the complete affected pack, and **never mix pre-repair and post-repair
evidence**.

## Next experiments (sketch only — NOT authorized by this document)

- **Recency vs. order discrimination:** a condition holding the terminal event
  fixed while permuting the earlier ones, separating rivals (2) and (4).
- **Self-authored trajectory:** restoring free event decision points and
  stratifying on realized path prefix — the harder experiment this design
  deliberately sets aside.
- **Model-family robustness:** the same frozen design against a second regime.

Each requires its own preregistration, design audit, and SC-6 authorization.
