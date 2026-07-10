# Files changed — session 2026-07-10-2

New:
- `coliseum/textlab/metrics.py` — deterministic metrics engine (per-run + aggregate + twin metrics)
- `coliseum/textlab/graph_export.py` — per-run + merged decision graphs, JSON + DOT
- `coliseum/textlab/cli.py` — run | replay | metrics | graph | compare
- `configs/scenarios/water_bearer.yaml` + `water_bearer_saboteur.yaml` — innocence pair
- `configs/scenarios/hidden_objective.yaml` + `hidden_objective_aligned.yaml` — willingness pair
- `scripts/score_scenarios.py` — 140-run batch scorer + table
- `tests/test_textlab_metrics.py` · `test_textlab_graph.py` · `test_textlab_derived_determinism.py` · `test_textlab_new_scenarios.py`

Modified:
- `coliseum/textlab/schema.py` — SCHEMA_VERSION 0.1 (frozen), arbitration_rule + dp_id on
  DecisionNode, Run.schema_version/arbitration, EventDelta record, validate_delta/apply_delta
- `coliseum/textlab/scenario.py` — delta-ops validation in outcome rules + deferred consequences
- `coliseum/textlab/runner.py` — ARBITRATION_RULES registry, event_delta logging, apply_delta folding
- `configs/scenarios/corrupt_king{,_harmless,_verifiable}.yaml` — state_delta converted to explicit ops
- `tests/test_textlab_schema.py` · `test_textlab_runner.py` — v0.1 updates + ruling tests
- `docs/TEXTLAB.md` — rulings, metrics, Day-2 status
