.PHONY: help smoke graph seeds clean textlab-smoke
help:   ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'
smoke:  ## run the zero-dependency smoke test (proves the substrate end to end)
	python scripts/smoke_match.py
textlab-smoke:  ## textlab: full pytest suite + one scripted corrupt_king run (determinism substrate)
	python3 -m pytest tests/ -q
	python3 scripts/run_scenario.py --scenario corrupt_king --agent scripted:obedient --seed 42
graph:  ## regenerate derived views (social graph + technique catalog) from logs
	python -c "from coliseum.derive_graph import build; build(); print('derived/ rebuilt from logs/')"
seeds:  ## run the smoke test across 3 seeds — a reproducibility sanity check
	@for s in 1 2 3; do echo "== seed $$s =="; SEED=$$s python scripts/smoke_match.py | sed -n '/Elo ladder/,/tendencies/p'; done
clean:  ## wipe regenerable run outputs
	rm -f logs/*.jsonl derived/*.json
