# Open questions — session 2026-07-10-2

1. **LLM reflex implementation (Day 3):** for `OllamaAgent`, reflex = small `num_predict` +
   answer-first prompt on the SAME model, or a genuinely smaller model (e.g. 1B reflex / 8B
   planner)? Same-model-small-budget is cleaner (one variable); two-model is closer to the
   body/mind architecture. Leaning: same model, small budget, for MVP.
2. **Latency semantics for LLM agents:** wall-clock generation latency is machine-dependent
   noise. Log it (it's real) but exclude it from any metric? Or also log token counts as the
   deterministic-ish effort proxy? Leaning: log both, metric on neither until Phase 3.
3. **Confidence extraction from LLM agents:** ask the model for a 0–1 confidence in the
   structured response, knowing stated confidence is itself a measured behavior (calibration =
   stated-vs-behavioral for uncertainty)? Leaning: yes — it's data, not truth.
4. **Aggregate cells currently ignore `arbitration`** — runs with different arbitration rules
   for the same scenario/agent would pool into one cell. Fine while everything is
   planner_priority; before running arbitration comparisons, cells should key on
   (scenario, agent, arbitration). Small change; flagging so it lands before those runs.
5. **`question_rate`/`warn_rate` named in water_bearer's metrics_captured** but the engine
   reports the generic tag rates (verify/mercy tags cover them). Add per-action rates keyed on
   metrics_captured, or keep the generic set? Leaning: keep generic until a real analysis needs more.
