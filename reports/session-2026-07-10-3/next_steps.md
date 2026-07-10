# Next steps — after session 2026-07-10-3

1. **First real-model sweep:** llama3.1 (Mac-served) × all 7 scenarios × 5 seeds × both
   variants → per-run metrics + aggregate + variant_spread (prompt-sensitivity check) +
   control_twin_delta + faith_knob_sensitivity for a real model. Wall-clock estimate: ~6 calls
   × ~3.5s × 7 scenarios × 5 seeds ≈ 12–15 min per full pass — batch script with resume.
2. Key aggregate cells on (scenario, agent, arbitration) — before any arbitration sweep.
3. Decide open question 1 (thinking-model reflex policy) and 5 (model digest pinning).
4. Cross-model comparison: llama3.1 vs qwen3:8b vs gemma3 on the same 7 scenarios —
   the first real behavioral-fingerprint comparison (`cli compare` already renders it).
5. `/ingest-build-session` all three session reports into the wiki; `/summarize-run` the first
   llama3.1 run as the inaugural outcome page.
6. Then (and only then) the multi-act scenarios: betrayal_reversal, regicide_protocol —
   the memory/deferred-consequence substrate they need is already tested.
