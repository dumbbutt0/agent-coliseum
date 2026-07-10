# Open questions — session 2026-07-10-3

1. **qwen3-style thinking models:** `<think>` blocks may eat the entire 80-token reflex budget
   → systematic parse_failure on reflex. That is arguably REAL data (the model literally cannot
   answer without deliberating — a measurable "no reflex" profile), but it could also be a
   format artifact. Ruling wanted: treat reflex parse-failure-rate as a metric, add a
   `/no_think` prompt directive for models that support it, or both?
2. **Reflex latency ≈ planner latency on llama3.1 (~3s both)** — Ollama's generation cost is
   dominated by prompt eval, not output tokens, so the "pressure" is budget-only, not
   time-only. Fine for ruling 1 (budget IS the pressure); flagging that latency won't separate
   the passes on local models.
3. **First-observation follow-up:** llama3.1 showed zero reflex/planner divergence and HIGHER
   reflex confidence. Worth a dedicated mini-sweep (all 7 scenarios × 5 seeds) before reading
   anything into it — is no-flinch stable across scenarios/variants, and is reflex
   overconfidence a general pattern?
4. **Aggregate cells still ignore `arbitration`** (carried from session 2) — must land before
   any arbitration-comparison sweep.
5. **Model naming in run_ids:** `llama3.1:latest` → `llama3.1-latest` in the run_id, but
   `latest` is a moving tag. Pin model digests (ollama show --modelfile) in spec_dict for real
   sweeps, or accept tag drift as config drift caught by the replay gate?
