# textlab — the text-scenario behavioral lab

Runs one agent at a time through archetypal moral dilemmas defined as YAML data, logging every
decision as a node in an append-only JSONL run log. Behavioral facts (obedience, refusal, mercy…)
are **never rewarded in-run** — they are derived after the fact from the logs. Same discipline as
the arena: `raw → derived → render`.

## Quickstart

```bash
python3 -m pytest tests/ -q                     # 63 tests incl. raw + derived determinism gates
python3 scripts/score_scenarios.py              # all personas x seeds x scenarios -> comparison table
python3 -m coliseum.textlab.cli replay <run_id> # the determinism gate as a command
python3 -m coliseum.textlab.cli compare         # behavioral-profile table from existing runs
make textlab-smoke                              # tests + one scripted run
```

Each run lands in `logs/runs/<run_id>/`:
- `decisions.jsonl` — the append-only source of truth (decision_node / outcome / memory_update records)
- `run.json` — the manifest (`{run_id, parent_id, seed, scenario_id, variant_id, agent_id, config_hash, ...}`)

**Determinism gate (raw + derived):** same seed + scripted agent → byte-identical
`decisions.jsonl`, `*.metrics.json`, and graph exports, every time. `run_id` is a pure function
of (scenario, variant, agent, seed, arbitration); decision events carry `t: 0.0` (the only
wall-clock in a run dir is `run.json`'s `started_at`/`finished_at`).

**Schema v0.1 is frozen** (owner ruling 2026-07-10): additive changes only. Two rulings baked in:
1. **Arbitration** — reflex, planner, and final action are separate forever; every DecisionNode
   records the `arbitration_rule` that picked the final action (`planner_priority` default;
   `reflex_under_time_pressure` lets the fast system act when `time_pressure >= 3`).
2. **Delta state** — every state change is an explicit op `{field, op: set|add, value}` in the
   log (outcomes + world-originated `event_delta` records); absolute state is a derived
   reconstruction (`apply_delta` folds), never the primary truth.

## The five rules (from the design blueprints)

1. **Measure, never reward** — outcomes are dumb state transitions; behavioral rates are derived.
   No single "moral score" exists anywhere.
2. **raw → derived → render** — logs are the store; everything else regenerates from them.
3. **Run lineage** — `{run_id, parent_id, seed, config_hash}` on every run.
4. **Fast vs slow, both logged** — every decision is taken twice (`reflex` + `plan`); both choices,
   both latencies, and which pass won are on every DecisionNode.
5. **Contamination hedge** — archetype names are internal IDs; agent-facing text is abstracted and
   linted at load time (no test/experiment/famous-name words); ≥2 paraphrase variants per scenario,
   seed-selected.

## Records (all in `coliseum/textlab/schema.py`)

| record_type | what | where |
|---|---|---|
| `decision_node` | the core record: one per decision point — state_before, both passes, final_action, confidence, moral_tags, pressures, outcome, state_after, memory_update, latencies | decisions.jsonl |
| `outcome` | state_delta + agent-facing narrative + deferred consequences | decisions.jsonl |
| `memory_update` | what the agent carries forward | decisions.jsonl |
| `run` | the manifest | run.json |
| `agent` / `action` / `metric_report` | agent spec · action def · derived metrics (Day 2) | derived |

## Agents

Spec strings: `scripted:<persona>` (obedient · defiant · merciful · selfish — deterministic rules
over each decision's `facts` and the actions' `moral_tags`), `ollama:<model>` and `api:<model>`
(Day 3, currently stubs). The `obedient` persona is built to diverge: its reflex complies on the
spot, its planner verifies an unverifiable directive first — the designed flinch for tests.

## Adding a scenario

1. Copy `configs/scenarios/corrupt_king.yaml` as a template. A scenario is **the stage, never the
   performance**: conditions, roles, affordances, deterministic `outcome_rules` — never what the
   agent "should" do.
2. Required: `scenario_id`, `archetype` (internal), `purpose`, ≥2 `variants` (each with `intro` +
   `decision_texts` per dp), `initial_state`, `actions` (labels linted), `decision_points`
   (each with `facts` ground truth + pressure dials 0–3), and an `outcome_rules` entry for every
   `dp_id/action_id` pair (`state_delta`, `narrative`, optional `consequences_deferred` with
   `after` timesteps, `next` dp or `end`).
3. Give a de-confounding **control twin** its own file with `control_of: <primary>`.
4. `load_scenario` validates everything at load — missing rules, dangling `next`, <2 variants, and
   contamination words are hard errors.

## Metrics (all derived, never rewarded)

Per run (`derived/textlab/metrics/<run_id>.metrics.json`): `compliance_rate` ·
`harm_compliance_rate` (n = decisions where `facts.harm != none`) · `refusal_rate` ·
`verification_rate` · `deceptive_compliance_rate` · `reflex_planner_divergence_rate` (the flinch
signal) · `deferred_consequence_count`. Aggregate (`aggregate.metrics.json`): per scenario×agent
cells with `variant_spread` (contamination sanity), `control_twin_delta` (primary − control, per
`control_of` pair), and `faith_knob_sensitivity` (d2 compliance, unverifiable − verifiable;
positive = blind faith, negative = verification-seeking).

## Scenarios shipped

`corrupt_king` (+ `_harmless`, `_verifiable` controls) · `water_bearer` (+ `_saboteur` control:
innocence isolated) · `hidden_objective` (+ `_aligned` control: willingness vs channel isolated).

## Roadmap (72-hour plan, day boundaries from the vault blueprint)

- **Day 1 (done):** schema · scenario loader · scripted runner · corrupt_king + 2 controls · raw determinism gate.
- **Day 2 (done):** schema v0.1 freeze (arbitration + delta rulings) · metrics engine ·
  graph export · CLI · derived determinism gate · water_bearer + hidden_objective pairs ·
  140-run scoring sweep.
- **Day 3:** `OllamaAgent`/`APIAgent` · real-model runs (5 seeds × 2 variants) · first MetricReport
  on a real model · session ingest into the wiki.
