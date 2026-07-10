# Next steps — after session 2026-07-10-4

1. **Fix effective-n (the temperature-0 caveat):** pass sampling temperature (>0) + per-run
   sampler seed to Ollama so seeds add real diversity, OR author ≥5 paraphrase variants per
   scenario. Decide which (or both) before the next sweep — this is the main methods debt.
2. **Re-tier the faith knob:** lower the stakes of the requisition step (harm too salient —
   all aligned models floor at 0 compliance, the knob can't move). A benign-but-unverifiable
   middle rung would let faith separate from harm refusal.
3. **Chase the profile hypotheses** (each currently 1-run-per-cell watch items):
   llama3.1's covert-channel aversion (aligned refusal, cistern vs granary split);
   qwen3's warn-instead-of-refuse humane-executor pattern; gemma3's verify-then-act.
   More variants first, then targeted mini-sweeps.
4. **Multi-act scenarios** (betrayal_reversal, regicide_protocol) — substrate ready and now
   validated on real models.
5. **Ingest this session** (`/ingest-build-session`) + Codex review findings when they arrive.
6. Optional fourth model: gpt-oss:20b is on the Mac — a bigger-model row for the fingerprint
   table.

## Open questions
- Aggregate cells still pool arbitration modes (harmless while everything is planner_priority;
  must key on arbitration before any arbitration-comparison sweep).
- Latency data (reflex ≈ planner ≈ 3–4s on LAN) confirms budget-not-time is the pressure on
  local backends — keep, or drop latency from the report tables entirely?
