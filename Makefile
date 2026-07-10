.PHONY: help smoke graph seeds clean textlab-smoke textlab-llm-smoke
OLLAMA_MODEL ?= llama3.2
help:   ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'
smoke:  ## run the zero-dependency smoke test (proves the substrate end to end)
	python scripts/smoke_match.py
textlab-smoke:  ## textlab: full pytest suite + one scripted corrupt_king run (determinism substrate)
	python3 -m pytest tests/ -q
	python3 scripts/run_scenario.py --scenario corrupt_king --agent scripted:obedient --seed 42
textlab-llm-smoke:  ## textlab: LLM path — mock fixture run always; real Ollama run if the server is up
	python3 -m pytest tests/test_textlab_llm.py -q
	python3 scripts/run_scenario.py --scenario corrupt_king --agent llm:mock:steward_obedient --seed 42
	@HOST=$${OLLAMA_HOST:-http://localhost:11434}; \
	if curl -sf --max-time 2 $$HOST/api/tags >/dev/null 2>&1 && \
	   curl -sf --max-time 2 $$HOST/api/tags | grep -q "\"$(OLLAMA_MODEL)\""; then \
		echo "== ollama up at $$HOST: running $(OLLAMA_MODEL) (override with OLLAMA_MODEL=... OLLAMA_HOST=...) =="; \
		python3 scripts/run_scenario.py --scenario corrupt_king --agent llm:ollama:$(OLLAMA_MODEL) --seed 42; \
	else \
		echo "== ollama/$(OLLAMA_MODEL) not reachable at $$HOST — skipped real-model run =="; \
	fi
graph:  ## regenerate derived views (social graph + technique catalog) from logs
	python -c "from coliseum.derive_graph import build; build(); print('derived/ rebuilt from logs/')"
seeds:  ## run the smoke test across 3 seeds — a reproducibility sanity check
	@for s in 1 2 3; do echo "== seed $$s =="; SEED=$$s python scripts/smoke_match.py | sed -n '/Elo ladder/,/tendencies/p'; done
clean:  ## wipe regenerable run outputs
	rm -f logs/*.jsonl derived/*.json
