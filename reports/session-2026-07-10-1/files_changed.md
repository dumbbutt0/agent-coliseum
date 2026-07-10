# Files changed — session 2026-07-10-1

New:
- `coliseum/textlab/__init__.py` — package doc + version
- `coliseum/textlab/schema.py` — all 8 record types, validation, canonical_json/config_hash
- `coliseum/textlab/scenario.py` — YAML loader + validation + contamination lint + variant pick
- `coliseum/textlab/agents.py` — Choice, AgentInterface (reflex/plan), ScriptedAgent ×4 personas, Ollama/API stubs
- `coliseum/textlab/runner.py` — DecisionLog (t=0.0), run_scenario loop, deferred consequences, run.json manifest
- `configs/scenarios/corrupt_king.yaml` — primary: benign → unverifiable → verified-harm ladder
- `configs/scenarios/corrupt_king_harmless.yaml` — control: obedience-to-form
- `configs/scenarios/corrupt_king_verifiable.yaml` — control: the faith knob
- `scripts/run_scenario.py` — CLI entry
- `tests/test_textlab_schema.py` · `test_textlab_scenario.py` · `test_textlab_runner.py` · `test_textlab_determinism.py` — 26 tests
- `docs/TEXTLAB.md` — quickstart, rules, schema table, how-to-add-a-scenario, roadmap
- `reports/session-2026-07-10-1/` — this report

Modified:
- `Makefile` — added `textlab-smoke` target (help regex widened for hyphenated targets)
- `requirements.txt` — pyyaml now a real dependency; pytest noted as dev dep

Untouched by design: `coliseum/logging_substrate.py`, `coliseum/seeding.py` (reused),
`coliseum/arena.py`, `ratings.py`, `derive_graph.py`, `envs/` (duel/Elo path).
