# Open questions — session 2026-07-10-1

1. **Reflex arbitration for LLM agents (Day 3):** MVP consults the planner at every decision point
   (`final_action = planner_choice`). For LLM agents under `time_pressure: 3`, should high time
   pressure ever let the reflex win (making time_pressure behaviorally real), or does that stay a
   post-hoc analysis dimension until the blueprints say otherwise? Leaning: keep planner-always in
   MVP; log-only. Wiki ruling wanted before Day 3.
2. **Confidence for scripted personas is rule-assigned** (0.5–0.9 constants). Fine for fixtures,
   but should the Day-2 metrics treat scripted confidence as meaningful (calibration metrics) or
   exclude scripted agents from confidence-based metrics entirely? Leaning: exclude.
3. **`standing` state values are set, not decremented** (outcome rules write absolute values, e.g.
   `standing: 3`). Simpler and fully deterministic, but multi-path accumulation (Day-2+ scenarios)
   may want relative deltas. Decide before authoring water_bearer: absolute sets (current) vs
   `{field: {op: add, value: -2}}` delta ops.
4. **Contamination word list** currently blocks "test/experiment/scenario/simulation/evaluation" +
   famous names. Is "king" (and similar archetype-adjacent common words) worth banning for the
   regicide scenario later, or is that over-blocking normal fantasy vocabulary? Leaning:
   don't ban; rely on paraphrase variants + variant_spread checks.
5. **Sub-second YAML load per run** re-reads and re-lints the scenario on every run. Fine at MVP
   scale; batch runners (5 seeds × 2 variants × 4 personas) may want a load-once API. Defer until
   the Day-3 batch script exists?
