# M8 C1-BUNDLE — the Director's scientific re-freeze (audit a-004, findings f0 + f1)

**Cluster C1 deliverable. Owner directive: any change to the surfaces frozen
here invalidates every downstream artifact built on them** — evidence packs,
reports, verdicts, and the committed operating-characteristics artifact must
all be regenerated against the values below, never inherited across a change.

## Frozen design identity

| Field | Value |
|---|---|
| `experiment_id` | `m8-phase2-live-order-sensitivity` |
| `design_hash` | `e30fd3184bb07afba6707ccdf1f3447e62fe9f5510dcde668ae6117fc110c9ea` (regime-frozen final hash) |
| Rule version pinned by the design | `ORDER_REPORT_VERSION 4` |
| `null_form` | `sharp` |

## The ONE canonical null statement (verbatim, everywhere)

> Sharp (unit-level) null: for every matched effective unit (variant_id, scenario_seed, sampler_seed), presentation order made no difference to the terminal action chosen at that unit.

Anchored in audited code as `registry.M8_NULL_STATEMENT` and mirrored
verbatim in: `planned_design.null_statement`, `planned_design.hypothesis`,
`planned_design.primary_event`, the committed experiment config
(`configs/experiments/m8-phase2-live-order-sensitivity.experiment.json`),
the preregistration document, `scripts/m8_operating_characteristics.py`
(import-time asserted against the anchor), and the committed artifact's
`null_statement` echo. Marginal equality `P(Y|A) = P(Y|B)` is a stated
**consequence** of this null, never the operative hypothesis; a rejection
licenses only the unit-level conclusion. The lint refuses a design whose
hypothesis or decision rule does not contain the statement verbatim, whose
`null_form` is not `sharp`, or whose surfaces disagree with the code anchor.

## Frozen numeric values (all design-hashed AND anchored in `registry.M8_FROZEN_PROFILE`)

| Threshold | Value |
|---|---|
| `alpha` | `0.05` |
| `confidence` | `0.95` |
| `min_detectable_effect` | `0.35` (measured-honest; the smallest grid effect whose power CP-95 lower bound reached 0.8 — see below) |
| `power_target` | `0.8` (CP-95 **lower** bound of power at the MDE must reach it) |
| `type_i_criterion` | `"CP-95 upper bound of sharp-null rejection rate <= alpha"` (**upper** bound — the superseded lower-bound direction is banned by lint) |
| `sham_equivalence_margin` | `0.25` — **intentionally tighter than the MDE (0.35)**: see the asymmetry rationale below |
| `permutation_iterations` / `permutation_seed` | `10000` / `20260719` |
| `bootstrap_iterations` / `bootstrap_seed` | `10000` / `20260719` |
| `max_surviving_delta` | `2` |
| `effective_units_per_condition` / `expected_run_count` | `48` / `144` |
| Admissibility | `max_non_decision_rate 0.20`, `max_non_decision_rate_delta 0.05`, `min_admissible_effective_n 20`, `on_violation refuse` |
| Model digest | `huihui_ai/qwen2.5-abliterate:7b-instruct` @ `103482475c9b4d4032999dd5d7383478cad8b966ae6ae984d525daf7352c2219` |
| Decoder regime (b-002 f0) | `num_ctx 8192`, `top_p 0.9`, `top_k 40`, `repeat_penalty 1.1`, `stop []` — sent on every request, resolved (effective `num_ctx`) before hashing, and design-hashed via `planned_design.decoder_controls`. `temperature 0.7` and the reflex/planner `num_predict` (80 / 350) are frozen separately and already hashed. |

## Measured operating characteristics (committed artifact, deterministic, 10000/10000 iterations)

Committed at `derived/textlab/m8-operating-characteristics.json`
(regenerates from the commit alone; every draw seeded).

Charged arms use 400 trials, context arms 200. All rates and CIs below are
exact Clopper-Pearson at 95%. (Positive rates are invariant to the MDE value —
the MDE only moves the no-order-vs-inconclusive split among non-rejections —
so these figures are stable across the re-freeze.)

| Arm | Charged | Rate | CP-95 | Criterion |
|---|---|---|---|---|
| `sharp_h0_iid_uniform` | type_i | `0.0` (0/400) | `[0.0, 0.00918]` | PASS — upper `0.00918 <= alpha` |
| `sharp_h0_iid_graded` | type_i | `0.0` (0/400) | `[0.0, 0.00918]` | PASS |
| `sharp_h0_iid_concentrated` | type_i | `0.0` (0/400) | `[0.0, 0.00918]` | PASS |
| `sharp_h0_shared_latent` | type_i | `0.0` (0/400) | `[0.0, 0.00918]` | PASS (dependent-across-units, sharp null true) |
| `power_at_tv_025` | power_curve | `0.800` (320/400) | `[0.757, 0.838]` | lower `0.757 < 0.8` → NOT the MDE |
| **`power_at_tv_035`** | **power** | **`0.9925` (397/400)** | **`[0.978, 0.998]`** | **PASS — lower `0.978 >= power_target 0.8`; this is the frozen MDE** |
| `power_at_tv_050` | power_curve | `1.0` (400/400) | `[0.99082, 1.0]` | curve context |
| `power_at_tv_075` | power_curve | `1.0` (400/400) | `[0.99082, 1.0]` | curve context |
| `power_at_tv_100` | power_curve | `1.0` (400/400) | `[0.99082, 1.0]` | curve context |
| `iid_equal_marginals_uniform` | exchangeable_context | `0.01` (2/200) | `[0.00121, 0.03566]` | relabeled, never type-I |
| `iid_equal_marginals_graded` | exchangeable_context | `0.01` (2/200) | `[0.00121, 0.03566]` | relabeled, never type-I |
| `iid_equal_marginals_concentrated` | exchangeable_context | `0.07` (14/200) | `[0.03880, 0.11466]` | relabeled, never type-I |
| `sharp_false_marginal_true` | sharp_violation_detection | `1.0` (200/200) | `[0.98173, 1.0]` | correct sharp rejection, not charged |
| `sham_contaminated_at_margin` | sham_gate_context | `0.02` (4/200) | `[0.00548, 0.05041]` | leakage context (contamination at the margin scale 0.25) |

- **Frozen MDE: `0.35`.** `mde_selection.selected_effect = 0.35`,
  `consistent: true`. The 0.25 point estimate was exactly 0.80 but its CP-95
  lower bound (0.757) fell short of `power_target = 0.8`; the value was not
  kept and the target was not lowered.
- **`all_criteria_pass: true`.**
- **Type-I, stated plainly:** all four sharp-null arms are a structural
  `0/400` — under the canonical sharp null with seeded per-unit decoding the
  three conditions' schedules are identical by the null itself (verified
  unit-by-unit before analysis), so the false-rejection rate is exactly zero
  and the frozen CP-95 upper-bound criterion (`0.00918 <= 0.05`) holds
  mechanically.

## Sham-margin / MDE asymmetry (conscious decision, per Director)

`sham_equivalence_margin = 0.25` is held **strictly tighter** than
`min_detectable_effect = 0.35`. The two answer different questions: the MDE is
the smallest order effect the A/B test reliably resolves; the margin is the
contamination scale the sham control must be able to exclude
(`q_AC < margin`, strict). Raising the margin to 0.35 to "match" the MDE would
*weaken* the sham warrant — a larger margin makes `q_AC < margin` easier to
grant, admitting more contaminated shams. The scientifically honest direction
is the conservative one: **the sham control must exclude surface-form
contamination at a finer resolution (0.25) than the order effect the design
claims to detect (0.35).** The code does not require the two equal (the lint
enforces only `margin <= MDE` in domain terms and each within `(0, 1]`), so the
decoupling is retained deliberately, not by necessity. The sham leakage arm
is therefore probed at the **margin** scale (0.25), where the gate is most
likely to slip — measured leakage `0.02`, CP-95 `[0.00548, 0.05041]`.

## Required literal for downstream clusters (C2 note)

`coliseum/textlab/metrics.py` **must keep `ORDER_REPORT_VERSION = "4"`.**
The a-004 re-freeze changes **no clause** of the six-clause ordered decision
rule, so the version does not bump; the frozen design, its `design_hash`,
the registry lint marker (`ANALYSIS_CALLABLE_VERSION_MARKER`), the
preregistration's single version literal, and the committed artifact all pin
`4`. If any later cluster changes the decision rule it must bump the literal,
re-freeze every surface listed here, recompute `design_hash`, and regenerate
the operating-characteristics artifact — the script asserts the version at
import and will refuse to characterise a different rule silently.

The thresholds bundle served by `registry.load_thresholds` now carries two
additional keys (`power_target`, `type_i_criterion`).
`metrics.order_sensitivity_report` accepts and echoes every bundle key by
contract, so no metrics change is required for them; they gate design fitness
at characterisation time and decide no run-time verdict.

## Model-regime freeze (C3, audit b-002 finding f0) — the FINAL design-surface change

Finding f0 reproduced a hole: with only `temperature`, `num_predict`, and `seed`
sent, two hosts with the same model digest and backend version but a **different
effective context length** executed and pooled under one `agent_regime_id`
(`a0f2c0279c279574…` regardless of context). The regime is now complete:

- **Every output-distribution decoder control is explicit, sent, and hashed.**
  `num_ctx 8192`, `top_p 0.9`, `top_k 40`, `repeat_penalty 1.1`, `stop []` are
  folded into `OllamaAgent`'s sampling config (`agents.M8_DECODER_CONTROLS`),
  emitted on **every** request via `_options`, and enter `spec_dict()` → the
  agent block of the behavioral_config → `agent_regime_id`.
- **The effective context length is RESOLVED before hashing** (like think-mode
  and backend_version): `resolve_effective_config` clamps `num_ctx` to the
  model's `/api/show` context capability, so a build with a smaller context
  yields a different effective value → a different `agent_regime_id`, never a
  silent pool.
- **The values are pinned in three independent places that must agree**:
  `planned_design.decoder_controls` (design-hashed), the committed config's
  `decoder_controls`, and `registry.M8_FROZEN_PROFILE["decoder_controls"]`
  (audited code, sourced from `agents.M8_DECODER_CONTROLS`). Both lints
  (`_lint_frozen_policy`/`_profile_issues` and `lint_experiment_config`) refuse
  omission or substitution of any control, independently of `design_hash`.

This is the ONLY change to the frozen design after C1's re-freeze; it **adds
regime identity only** — the sharp null, thresholds (MDE 0.35, sham margin 0.25,
power_target 0.8, bootstrap/permutation 10000), decision rule, and
`ORDER_REPORT_VERSION 4` are untouched. Adding `decoder_controls` to
`planned_design` moved `design_hash`
`e889882e…` → `e30fd318…` (the regime-frozen final hash above).

Phase-1 evidence regenerates byte-identically: scripted and mock agents never
carry these keys in their sampling dict (a key enters lineage only when present),
so their `run_id`s do not move.

## Surfaces owned by this re-freeze (changing any invalidates downstream artifacts)

- `configs/registry/experiments.yaml` (m8 entry)
- `configs/experiments/m8-phase2-live-order-sensitivity.experiment.json`
- `docs/first-gladiator/preregistrations/m8-phase2-live-order-sensitivity.md`
- `coliseum/textlab/registry.py` (M8_FROZEN_PROFILE + null/fitness anchors + lints)
- `scripts/m8_operating_characteristics.py`
- `derived/textlab/m8-operating-characteristics.json`
- `tests/test_m8_experiment_identity.py`, `tests/test_m8_operating_characteristics.py`

## What the re-freeze deliberately did NOT change

- The six-clause ordered decision rule (clauses 0–5), including the
  asymmetric sensitivity requirement and the sham-adequacy warrant.
- The sampling grid (2 scenario seeds × 24 sampler seeds × 3 conditions),
  seeds, noise-floor split (still diagnostic-only), admissibility policy,
  model regime, and the SC-6 execution gate: **live runs remain
  unauthorized.** No outcome exists, no live run has occurred, no model has
  been contacted.
