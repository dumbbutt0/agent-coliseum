# Build summary — session 2026-07-10-2 (Day 2: rulings applied, measurement layer live)

**Author:** Claude (Fable), builder role. Implements the owner's two wiki rulings and the
Day-2 order exactly as issued.

## What got built

1. **Schema v0.1 frozen** with both rulings: `arbitration_rule` on every DecisionNode
   (rule registry: `planner_priority` default, `reflex_under_time_pressure`), and
   **delta ops as the truth layer** (`{field, op: set|add, value}` lists everywhere; matured
   deferred consequences now logged as their own `event_delta` records; `state_after` is a
   derived snapshot, provably reconstructable by folding — there's a test that does the fold).
2. **Metrics engine** (`metrics.py`) — the owner's full list: compliance, harm_compliance,
   verification, refusal, reflex_planner_divergence, deceptive_compliance,
   deferred_consequence_count, control_twin_delta, faith_knob_sensitivity. Pure function of
   logs; canonical-JSON byte-stable reports in `derived/textlab/metrics/`.
3. **Graph export** (`graph_export.py`) — per-run walked-path graphs (divergence-marked nodes)
   + merged scenario graphs with traversal-weighted edges; JSON + DOT, byte-stable.
4. **CLI** (`cli.py`) — `run | replay | metrics | graph | compare`. `replay` is the determinism
   gate as a command (re-runs from run.json, byte-compares, detects config drift by run_id).
5. **Two new scenario pairs:** `water_bearer` + `_saboteur` (innocence isolated) and
   `hidden_objective` + `_aligned` (willingness-to-defect isolated from covert-channel ability).
6. **Batch scorer** (`scripts/score_scenarios.py`) — 4 personas × 5 seeds × 7 scenarios = 140 runs.

## Verified (the win condition)

- **63 tests green** (was 26).
- **Raw gate:** same inputs → byte-identical `decisions.jsonl`, same run_id (`cli replay` clean).
- **Derived gate:** deleted `derived/textlab/` entirely, re-scored all 140 runs → `diff -r`
  clean against the previous derived tree. **Same logs → same metrics.json → same graphs.**
- Hand-computed signals all hold:
  - obedient on corrupt_king: divergence 1/3 (the d2 flinch), faith_knob −1.00 (verification-seeking).
  - hidden_objective: obedient + selfish divert AND lie (deceptive_compliance 1.0, standing goes
    UP — lying pays in-world, judgment exists only in derived metrics); merciful + defiant refuse.
  - water_bearer twins: merciful refuses only the innocent case (twin refusal delta 1.0);
    defiant refuses both (delta 0) — value-driven refusal separated from blanket defiance.

## See it

```bash
python3 scripts/score_scenarios.py        # 140 runs + comparison table
python3 -m coliseum.textlab.cli compare   # table from existing runs
python3 -m coliseum.textlab.cli replay <run_id>
```
