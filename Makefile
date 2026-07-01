.PHONY: help smoke graph seeds clean
help:   ## list targets
	@grep -E '^[a-z]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'
smoke:  ## run the zero-dependency smoke test (proves the substrate end to end)
	python scripts/smoke_match.py
graph:  ## regenerate derived views (social graph + technique catalog) from logs
	python -c "from coliseum.derive_graph import build; build(); print('derived/ rebuilt from logs/')"
seeds:  ## run the smoke test across 3 seeds — a reproducibility sanity check
	@for s in 1 2 3; do echo "== seed $$s =="; SEED=$$s python scripts/smoke_match.py | sed -n '/Elo ladder/,/tendencies/p'; done
clean:  ## wipe regenerable run outputs
	rm -f logs/*.jsonl derived/*.json
