# Pre-registration — M7: scrambled-history admission gate (Phase 1, instrument calibration)

**Frozen design. Registered as `m7-scrambled-history-gate` (status:
pre-registered) in `configs/registry/experiments.yaml`; the design is frozen by
its `design_hash` over the registry entry's `planned_design`.** This is the
ADMISSION GATE for the developmental-trajectory research program (see
`docs/first-gladiator/COLISEUM-SCIENTIFIC-CHARTER.md` §2 and the frozen
hypothesis record in the wiki): until an order effect is demonstrated under
these controls, every downstream developmental claim remains blocked.

## What Phase 1 is (and is not)

Phase 1 is **instrument calibration, not a discovery experiment.** The
scripted deciders carry a KNOWN, pre-declared order-sensitivity; the question
is whether the scenario + runner + metric pipeline RECOVERS it — and recovers
the nulls — without artifacts. Only a calibration-validated instrument may
proceed to Phase 2 (a live model of unknown order-sensitivity). A decider
tuned to always diverge cannot pass: it would diverge on the sham control C or
fail the linear null, both of which FAIL the gate.

## Hypothesis (primary, pre-registered — null first)

H0 (per decider rule): the terminal `final_action` distribution is unchanged
between condition A (developmental order) and condition B (identical
experience multiset, permuted order), and unchanged between A and C (sham
reorder: same order, wording/formatting only).

Pre-declared predictions (frozen in `coliseum/textlab/agents.py::HIST_RULES`,
hashed into each run's regime via `spec_dict()`):

| rule       | mechanism                 | A vs B          | A vs C |
|------------|---------------------------|-----------------|--------|
| linear     | order-invariant sum       | **null**        | null   |
| recency    | position-weighted sum     | **effect**      | null   |
| hysteresis | latching threshold        | **effect**      | null   |

## Design

- **Scenarios (frozen behavioral hashes in `configs/registry/scenarios.yaml`):**
  `scramble_dev` (A: trust+2 → betrayal−3 → warning−1 → terminal probe),
  `scramble_perm` (B: betrayal−3 → warning−1 → trust+2 — same multiset,
  permuted), `scramble_sham` (C: A's order, agent-facing wording/formatting
  only). Matched-except-order is machine-checked by
  `scenario.lint_scramble_triplet` (identical multiset; B actually scrambled;
  C behaviorally identical to A; choice-independent positional deltas) — run
  as a preflight before any gate run.
- **Agents:** `scripted:hist:{linear,recency,hysteresis}` — deterministic,
  two-pass (reflex = last event only; plan = full rule), no network, reading
  ONLY the scenario's positional valence ground truth (`val_pos1..3` threaded
  through `outcome_rules.state_delta`) — never a derived label or metric.
- **Interaction mode:** `sequential_history` (the terminal decision node's
  `history_prompt_hash` independently attests that A/B present different
  histories and A/C identical ones).
- **Arbitration:** `planner_priority` (unchanged machinery).
- **Sampling:** deterministic temperature 0; no sampler seeds are consumed
  (scripted deciders); scenario_seeds {42, 1} cover both paraphrase variants.
- **Cells:** 3 scenarios × 3 deciders × 2 scenario_seeds = **18 runs**, each
  byte-replayable (`cli replay <run_id>`).

## Analysis rule (pre-registered)

`metrics.scramble_terminal_distribution(run_dirs, {"A": "scramble_dev",
"B": "scramble_perm", "C": "scramble_sham"})` — per-decider terminal
`final_action` distributions over effective units `(variant_id, scenario_seed,
sampler_seed)` with total-variation distances TV(A,B) and TV(A,C). Thresholds
are applied to this output only and never fed back (measure-never-reward).

## Primary event + threshold (calibration pass/fail rule)

With ε = 0 and τ = 0 (deterministic deciders admit exact thresholds), the
instrument PASSES calibration iff ALL of:

1. `TV(A,B)_linear ≤ ε` — the pipeline recovers the pre-declared null;
2. `TV(A,B)_recency > τ` AND `TV(A,B)_hysteresis > τ` — it recovers the
   pre-declared effects;
3. `TV(A,C) ≤ ε` for **all three** rules — no prompt-surface artifact.

Any failure of (3) is reported as an instrument artifact and Phase 2 remains
blocked regardless of (1)/(2). Effective n is reported per cell (2 units:
v0_caravan/s42, v1_workshop/s1). No inferential statistics at Phase 1
(deterministic; METRICS-v1 posture).

## What may NOT be claimed

- **Nothing about any live model.** Phase 1 shows only that the instrument can
  discriminate order when a known-order-sensitive decider carries it.
- **No memory / cognition / development / identity language.** The deciders
  are arithmetic rules, not models of anything.
- A Phase-1 PASS enters the claim ladder as an **observation scoped to
  instrument calibration** — it does not upgrade any blocked developmental
  claim; it merely unblocks the *design* of Phase 2.
- A Phase-1 FAIL closes the gate: the result is reported as-is and the
  theory is NOT expanded to rescue it (charter §2).

## Phase 2 (sketch only — separately preregistered, NOT authorized by this doc)

Same A/B/C scenarios, `sequential_history`, a live pinned-digest model of
UNKNOWN order-sensitivity (`llm:ollama:<model>`), null-first H0 TV(A,B)=0,
with TV(A,C) as the formatting control. Requires: Phase-1 PASS, its own
preregistration + design freeze, council design audit, SC-6 owner approval for
live runs, and result audit before any claim registers.

## Appendix — exact regeneration commands (added cycle 2, audit 001664 LOW finding)

*This appendix corrects the committed report's reproducibility instruction; the
hypothesis, design, analysis rule, and thresholds above are UNCHANGED.* The
evidence is fully deterministic — any checkout of the audited commit
regenerates byte-identical runs:

```sh
# 1. run the 18-cell grid
for scen in scramble_dev scramble_perm scramble_sham; do
  for rule in linear recency hysteresis; do
    for seed in 42 1; do
      python3 -m coliseum.textlab.cli --out-root logs/runs/m7-scrambled-history-gate \
        run --scenario $scen --agent scripted:hist:$rule --seed $seed \
        --interaction sequential_history --arbitration planner_priority
    done
  done
done

# 2. byte-replay every run (the determinism gate)
for d in logs/runs/m7-scrambled-history-gate/*/; do
  python3 -m coliseum.textlab.cli --out-root logs/runs/m7-scrambled-history-gate \
    replay "$(basename "$d")"
done
```

The aggregator + preregistered thresholds are then applied via
`coliseum.textlab.metrics.scramble_terminal_distribution` over the 18 run
directories with conditions `{"A": "scramble_dev", "B": "scramble_perm",
"C": "scramble_sham"}` (the committed report's `calibration_checks` are exactly
rule 1–3 of *Primary event + threshold* above).
