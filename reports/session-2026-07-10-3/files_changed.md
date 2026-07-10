# Files changed — session 2026-07-10-3

New:
- `tests/fixtures/llm/steward_obedient.json` — mock moral profile (divergence at d2+d3, one prose-wrapped JSON)
- `tests/fixtures/llm/garbled.json` — parse-failure coverage (prose, invalid action, broken JSON)
- `tests/test_textlab_llm.py` — 10 tests: parse paths, rulings, replay tier, scripted-baseline guard

Modified:
- `coliseum/textlab/agents.py` — Choice gains `model_stated_confidence` + `meta`; `build_prompt`,
  `parse_llm_response`, `LLMAgent` base (capture/replay), `MockLLMAgent`, `OllamaAgent`
  ($OLLAMA_HOST, warmup); `make_agent` specs `llm:mock:` / `llm:ollama:`
- `coliseum/textlab/runner.py` — `replay_from` param, `dp_id` in state_before, latencies from
  choice meta, `captures.jsonl` persistence
- `coliseum/textlab/cli.py` — `replay` auto-detects LLM runs → replays from captures
- `Makefile` — `textlab-llm-smoke` target (+ OLLAMA_MODEL var)
- `docs/TEXTLAB.md` — LLM agents, rulings, determinism tiers, Day-3 status
