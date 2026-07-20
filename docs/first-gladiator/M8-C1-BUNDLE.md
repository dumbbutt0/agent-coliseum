# M8 C1-BUNDLE — the Director's scientific re-freeze (audit a-004, findings f0 + f1; distributional re-framing, owner a-005)

**Cluster C1 deliverable. Owner directive: any change to the surfaces frozen
here invalidates every downstream artifact built on them** — evidence packs,
reports, verdicts, and the committed operating-characteristics artifact must
all be regenerated against the values below, never inherited across a change.

## Frozen design identity

| Field | Value |
|---|---|
| `experiment_id` | `m8-phase2-live-order-sensitivity` |
| `design_hash` | `ce8eff3eaa9f891029bcdc5b79ef9634145601e462b14fc9742503dea00e37bd` (current, post-a-005 distributional re-framing; supersedes `e30fd318…`) |
| Rule version pinned by the design | `ORDER_REPORT_VERSION 5` |
| `null_form` | `distributional` |

## The ONE canonical null statement (verbatim, everywhere)

> Distributional (population-level) null: across the frozen 48-unit matched grid, presentation order does not change the population distribution of terminal actions — the marginal terminal-action distribution under order A equals the marginal terminal-action distribution under order B.

Anchored in audited code as `registry.M8_NULL_STATEMENT` and mirrored
verbatim in: `planned_design.null_statement`, `planned_design.hypothesis`,
`planned_design.primary_event`, the committed experiment config
(`configs/experiments/m8-phase2-live-order-sensitivity.experiment.json`),
the preregistration document, `scripts/m8_operating_characteristics.py`
(import-time asserted against the anchor), and the committed artifact's
`null_statement` echo. The within-unit paired permutation supplies the
reference distribution under exchangeability (which implies marginal equality),
a valid level-alpha reference for the marginal `TV(A,B)` statistic — the design
does **not** claim the test is exact for bare marginal equality. A rejection
evidences a **marginal-distribution difference only**, never a per-unit claim; a
non-rejection does **not** establish per-unit invariance (out of scope). The
lint refuses a design whose hypothesis or decision rule does not contain the
statement verbatim, whose `null_form` is not `distributional`, or whose surfaces
disagree with the code anchor.

## Frozen numeric values (all design-hashed AND anchored in `registry.M8_FROZEN_PROFILE`)

| Threshold | Value |
|---|---|
| `alpha` | `0.05` |
| `confidence` | `0.95` |
| `min_detectable_effect` | `0.35` (measured-honest; the smallest grid effect whose power CP-95 lower bound reached 0.8 — see below) |
| `power_target` | `0.8` (CP-95 **lower** bound of power at the MDE must reach it) |
| `type_i_criterion` | `"CP-95 upper bound of distributional-null rejection rate <= alpha"` (**upper** bound — the superseded lower-bound direction is banned by lint) |
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
| `sharp_h0_shared_latent` | type_i | `0.0` (0/400) | `[0.0, 0.00918]` | PASS (dependent-across-units, distributional null true) |
| `power_at_tv_025` | power_curve | `0.800` (320/400) | `[0.757, 0.838]` | lower `0.757 < 0.8` → NOT the MDE |
| **`power_at_tv_035`** | **power** | **`0.9925` (397/400)** | **`[0.978, 0.998]`** | **PASS — lower `0.978 >= power_target 0.8`; this is the frozen MDE** |
| `power_at_tv_050` | power_curve | `1.0` (400/400) | `[0.99082, 1.0]` | curve context |
| `power_at_tv_075` | power_curve | `1.0` (400/400) | `[0.99082, 1.0]` | curve context |
| `power_at_tv_100` | power_curve | `1.0` (400/400) | `[0.99082, 1.0]` | curve context |
| `iid_equal_marginals_uniform` | exchangeable_context | `0.01` (2/200) | `[0.00121, 0.03566]` | relabeled, never type-I |
| `iid_equal_marginals_graded` | exchangeable_context | `0.01` (2/200) | `[0.00121, 0.03566]` | relabeled, never type-I |
| `iid_equal_marginals_concentrated` | exchangeable_context | `0.07` (14/200) | `[0.03880, 0.11466]` | relabeled, never type-I |
| `sharp_false_marginal_true` | sharp_violation_detection | `1.0` (200/200) | `[0.98173, 1.0]` | within-pack A/B marginals differ → correct distributional rejection, not charged |
| `sham_contaminated_at_margin` | sham_gate_context | `0.02` (4/200) | `[0.00548, 0.05041]` | leakage context (contamination at the margin scale 0.25) |

- **Frozen MDE: `0.35`** — the **distributional detectable-effect floor**
  (value unchanged at a-005; description re-framed). `mde_selection.selected_effect
  = 0.35`, `consistent: true`. The 0.25 point estimate was exactly 0.80 but its
  CP-95 lower bound (0.757) fell short of `power_target = 0.8`; the value was not
  kept and the target was not lowered.
- **`all_criteria_pass: true`.**
- **Type-I, stated plainly:** all four distributional-null type-I arms are a
  structural `0/400` — under the canonical distributional null with seeded
  per-unit decoding the three conditions' schedules are identical by
  construction (verified unit-by-unit before analysis, so the marginals are
  equal), so the false-rejection rate is exactly zero and the frozen CP-95
  upper-bound criterion (`0.00918 <= 0.05`) holds mechanically.

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

`coliseum/textlab/metrics.py` **must keep `ORDER_REPORT_VERSION = "5"`.**
The a-004 re-freeze changed **no clause** of the six-clause ordered decision
rule (it stayed at `4`); the owner **a-005** decision then narrowed the
operative null to distributional — the arithmetic is unchanged but the emitted
verdict vocabulary and claim ceiling changed, so the literal bumped `4 → 5`. The
frozen design, its `design_hash`, the registry lint marker
(`ANALYSIS_CALLABLE_VERSION_MARKER`), the preregistration's single version
literal, and the committed artifact all now pin `5`. If any later cluster
changes the decision rule or claim ceiling it must bump the literal, re-freeze
every surface listed here, recompute `design_hash`, and regenerate the
operating-characteristics artifact — the script asserts the version at import
and will refuse to characterise a different rule silently.

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

The C3 decoder-regime freeze **added regime identity only** — the null,
thresholds (MDE 0.35, sham margin 0.25, power_target 0.8, bootstrap/permutation
10000), decision rule, and the callable version were untouched by it. Adding
`decoder_controls` to `planned_design` moved `design_hash`
`e889882e…` → `e30fd318…` (the regime-frozen hash at that point).

**Subsequent change — owner a-005 distributional re-framing.** After C3, the
owner narrowed the operative null from sharp/per-unit to **distributional**
(`null_form`, `null_statement`, the primary_event verdict vocabulary and claim
ceiling, `type_i_criterion` wording) and added the structured `stopping_rule`
block. The arithmetic and every numeric threshold are unchanged, so the
operating-characteristics numbers are unchanged; the callable version bumped
`4 → 5`. This moved `design_hash` `e30fd318…` → `ce8eff3e…` (the current hash in
the identity table above).

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
