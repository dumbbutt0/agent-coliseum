# Next steps — after session 2026-07-10-2 (= Day 3 of the 72-hour plan)

1. `OllamaAgent`: two-pass contract against `localhost:11434` — reflex = answer-first prompt
   with tiny `num_predict`; plan = full deliberation prompt; structured extraction of
   {action_id, confidence, reasoning_summary, reward_expected}; real latencies logged
   (determinism gate does NOT apply to LLM runs — expected and documented).
2. `APIAgent`: same contract, Anthropic/OpenAI-compatible chat, key from env, model from spec.
3. Robust action parsing: the model must pick from `available_actions` labels; retry once on
   unparseable output, then log a `parse_failure` and take no action (n/a decision) rather
   than guessing — parse failures are data.
4. First real-model sweep: one local model × all 7 scenarios × 5 seeds × both variants →
   metrics + variant_spread check (prompt-sensitivity vs behavioral signature).
5. Key on (scenario, agent, arbitration) in aggregate cells (open question 4) before any
   arbitration-comparison runs.
6. First real-model behavioral profile ingested into the wiki (`/ingest-build-session` then
   `/summarize-run` on the most interesting run).
7. Resolve open questions 1–3 (LLM reflex mode, latency semantics, confidence extraction)
   in the wiki before coding the adapters.
