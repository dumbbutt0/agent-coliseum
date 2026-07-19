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

**H0:** `P(Y | A) = P(Y | B)`

**H1:** `P(Y | A) ≠ P(Y | B)`

where `Y` is the terminal `final_action` at the `d_partner` probe, `A` is the
developmental order, `B` is the identical admitted experience multiset in a
permuted order, and `C` is the sham control (A's order; agent-facing wording and
formatting only).

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

Applied to the run set **once**, after the complete pack closes. No interim
analysis, no early stopping, no post-hoc threshold movement.

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

   **The operative null is the sharp null, and that is stronger than the
   marginal statement above.** A paired permutation test is exact under
   *within-pair exchangeability* — that for each matched unit, the condition
   label carries no information about that unit's terminal action. Equality of
   the A and B **marginal** distributions, as `H0` is written, does **not**
   logically imply it: two conditions can share a marginal distribution while
   their outcomes are dependent within a unit in an asymmetric way, and under
   that weaker hypothesis alone the test is not exact.

   This design adopts the sharp null as operative, which is the scientifically
   natural reading here rather than a convenience: the matched unit fixes the
   variant, the scenario seed and the sampler seed, so the sharp null says
   precisely "for this unit, presentation order made no difference to what was
   chosen" — the thing the experiment is actually asking. The sharp null implies
   the marginal null, so `H0` as stated remains the correct **claim-level**
   summary and nothing in the claim ceiling widens. The exactness guarantee,
   however, rests on the sharp null, and the result report must say so rather
   than implying exactness under marginal equality alone.

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
bound at ≈0.49 — about **twice** `min_detectable_effect = 0.25`. The
sensitivity precondition therefore refused every arm, including one with a
genuine effect at TV(A,B)=0.6: **false-positive rate 0.000, power 0.000.** A
design that cannot detect an effect of any size is not conservative, it is
inert.

A paired permutation null fixes the cause rather than the symptom. It is exact
under the exchangeability implied by H0, it uses the actual matched sample
sizes so no size mismatch exists, it consumes no additional live runs, and it
respects the pairing the design already guarantees. The rejected alternatives
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
**`ORDER_REPORT_VERSION 3`**. The version has been bumped once per change to the
decision rule, so any emitted verdict is traceable to the rule that produced it:
v1 the bootstrap-bound comparison against a split-half floor; v2 the paired
permutation null; v3 the corrected asymmetric sensitivity requirement. The
registry entry's `primary_event` is the authoritative statement of the frozen
rule, and the lint fails a design whose version marker disagrees with it,
consuming the frozen `admissibility_policy` and `thresholds` loaded from this
experiment's registry entry. The Phase-1 comparator
`metrics.scramble_terminal_distribution` is **explicitly NOT the Phase-2 analysis
path** — it admits parse fallbacks as decisions and is demonstrated in this
candidate to return a clean null from wholly unparseable output. Naming it here
would freeze the exact unsafe path this design exists to avoid.

Let `q_AB` and `q_AC` be the `1 − alpha` quantiles of the paired permutation
nulls for A vs B and A vs C. The rule is evaluated in this order:

1. If the admissibility policy refuses, or effective n falls below the floor, or
   per-condition surviving counts differ by more than `max_surviving_delta`:
   **inconclusive**.
2. Else if the observed `TV(A,C)` **exceeds** `q_AC`: **inconclusive** — the sham
   is not null, which voids any order claim.
3. Else if the observed `TV(A,B)` **exceeds** `q_AB`: **order effect observed**.
4. Else if `q_AB ≤ min_detectable_effect`: **no order effect observed**.
5. Else: **inconclusive**.

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
disjoint** — was returned by the original v1 rule as `no_order_effect_observed`,
because its split-half floor `TV_null=1.0` was not strictly exceeded by
`TV(A,B)=1.0`. A maximally unstable instrument would have closed the gate with a
"successful null" and the downstream track would have advanced on it.

Under the current rule that pack is `order_effect_observed`: clause 3 fires on a
genuine rejection before clause 4 is ever reached. **The invariant the ceiling
exists to protect is unchanged and now holds by construction — that pack can
never be reported as a successful null.** What changed is which clause protects
it, and that the protection no longer costs valid rejections.

The requirement therefore attaches to clause 4 alone. It governs what a
*non*-rejection is entitled to assert, never whether a rejection counts.

### Frozen operating characteristics

`min_detectable_effect = 0.25` — a shift of a quarter of the terminal probability
mass is the smallest difference this design claims to resolve, and correspondingly
the tightest null it is entitled to assert. It is declared **before** any outcome
exists and is covered by `design_hash`.

The false-positive rate under H0 and the power at the `min_detectable_effect`
boundary must be characterised by simulation at the frozen `n = 48` units per
condition, using the frozen bootstrap parameters, and committed with the
candidate. A design whose simulated false-positive rate materially exceeds
`1 - confidence`, or whose power at the boundary is negligible, is not fit to run
and must be corrected **before** execution rather than reinterpreted after.

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

**Maximum positive claim:**

> Under the frozen live-model regime, the temporal ordering of an otherwise
> matched experience set changed the measured terminal-action distribution.

**Maximum null claim:**

> Under the frozen live-model regime and preregistered sensitivity bound, the
> experiment did not detect a temporal-order effect.

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
