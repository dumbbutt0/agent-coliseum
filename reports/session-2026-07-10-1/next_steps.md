# Next steps — after session 2026-07-10-1 (= Day 2 of the 72-hour plan)

1. `coliseum/textlab/metrics.py` — per-run behavioral rates from `decisions.jsonl` alone:
   obedience-to-harm (final_action tagged `obedience` where `facts.harm != none`),
   refusal-on-principle, stated-vs-behavioral divergence, reflex-planner divergence rate,
   breaking-point step, deceptive-compliance; cross-run aggregation with counts; **control delta**
   (primary vs its `control_of` twins). Write `MetricReport` to `derived/textlab/`.
2. `coliseum/textlab/graph_export.py` — decision graph from logs: nodes = decision nodes, edges =
   final actions + outcomes; JSON + Graphviz DOT to `derived/textlab/`. Byte-stable output
   (extends the determinism gate to derived artifacts — the full Rung-0 criterion).
3. `coliseum/textlab/cli.py` — `run | replay | metrics | graph | compare` (thin over runner +
   metrics + graph_export); wire `scripts/run_scenario.py` to it or keep both.
4. Scenarios: `water_bearer` (+ saboteur control) and `hidden_objective` (+ aligned-objective
   control) per the vault scenario pack specs.
5. Batch helper: run all personas × seeds {1,2,3,5,8} × both variants for one scenario, then a
   first cross-persona MetricReport (hand-check the rates against the known persona paths).
6. Resolve open questions 1 and 3 (arbitration; state-delta semantics) in the wiki before
   authoring the new YAMLs.
7. Determinism gate extension test: same seed → byte-identical `derived/textlab/` outputs
   (metrics + graphs), completing the Rung-0 acceptance criterion.
