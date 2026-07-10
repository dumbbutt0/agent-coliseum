# Build summary — session 2026-07-10-4 (Day 3b: sweep rulings + first reportable sweep)

**Author:** Claude (Fable).

## What got built (commit 1be6078 + this session's sweep artifacts)

1. **Ruling 1 implemented:** `<think>`-strip before JSON extraction; `failure_kind`
   classification (`thinking_budget_artifact` / `malformed_json` / `invalid_action`);
   `reflex_valid` on reflex passes; moral rates over valid decisions only; divergence requires
   both passes valid; new metrics `format_compliance_under_pressure` + `valid_decision_rate`;
   Ollama `think: false` with 400-retry; thinking_overflow fixture + tests.
2. **Ruling 2 implemented:** digest fetched from `/api/tags` and hashed into run lineage
   (repulled `:latest` = new lineage — tested); mock digest = fixture content hash; `run.json`
   gains `llm_info` (all ruled lineage fields incl. capture_hash) + `reportable` +
   `digest_status`; missing digest ⇒ non-reportable.
3. **`scripts/sweep_models.py`** — model-major, digest-gated, resume-safe manifest sweep.
4. **83 → 83+ tests green throughout; scripted gates untouched.**

## The sweep

105/105 runs, 0 non-reportable, 3 pinned digests. One interruption (Mac slept mid-gemma3);
manifest resume worked exactly as designed — 96 runs skipped, 9 completed, digests re-verified.
Full findings: `sweep_report.md`. Headlines: universal harm refusal + zero deception across all
models; llama3.1's zero-divergence anecdote KILLED (0.104 real rate); divergence is a
model-separating fingerprint (gemma3 0.000 / llama3.1 0.104 / qwen3 0.250) with a consistent
direction (reflex more authority-compliant than deliberation); three distinct profiles visible
only in the CONTROL scenarios; format compliance 1.000 everywhere (fair reflex channel held,
even for qwen3 thinking mode); temperature-0 methods caveat recorded (seeds = variants, 2
effective conditions per scenario).
