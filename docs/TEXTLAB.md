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

Spec strings:
- `scripted:<persona>` — obedient · defiant · merciful · selfish; deterministic rules over each
  decision's `facts` and the actions' `moral_tags`. The gold deterministic baseline. The
  `obedient` persona is built to diverge: reflex complies on the spot, planner verifies first.
- `llm:mock:<fixture>` — the full LLM code path (prompting, parsing, capture, fallback) served
  from `tests/fixtures/llm/<fixture>.json`. Scripted-tier deterministic; no network.
- `llm:ollama:<model>` — real model via Ollama. Host from `$OLLAMA_HOST` (e.g.
  `OLLAMA_HOST=http://10.0.0.8:11434` to serve minds from the Mac over LAN) or localhost.

**LLM rulings (owner, 2026-07-10):** (1) the reflex is the SAME model under pressure — tiny
token budget (80 vs 350), answer-first prompt, strict JSON, short timeout — not a smaller model;
(2) wall-clock latency is log-only evidence on the DecisionNode, never in the lineage hash;
(3) stated confidence is stored as `model_stated_confidence` per recommendation and never
arbitrates unless a future rule explicitly uses it.

**Parse failures are data:** invalid JSON / unknown actions record `parse_status`
(`parse_failure` | `invalid_action`) with the raw text, fall back deterministically to the first
available action at confidence 0, and are flagged `fallback: true`.

**Two determinism tiers:** scripted runs re-execute byte-identically from the seed. Live LLM
runs are NOT that tier — their backbone is capture-and-replay: every model call lands in the
run's `captures.jsonl`; `coliseum-lab replay <dir>` re-runs from those captured outputs and
byte-compares. Live-API determinism is never claimed.

## Day-4 provenance hardening (Codex review findings 1–9, all closed)

- **Evidence preservation:** live LLM attempts get exclusive dirs `<run_id>.aN` — nothing is
  ever truncated; scripted dirs are verify-or-refuse (rerun allowed only when the stored full
  config hash matches). `run_id` = config identity; the directory = evidence identity.
- **Offline replay:** the replay agent's entire identity comes from the stored `agent_config`
  in `run.json` (zero network, zero digest lookups); captures are integrity-checked against the
  stored `capture_hash` before replay.
- **Admission:** aggregation excludes `reportable: false` runs by default (`--diagnostics` to
  include, loudly labeled); comparison cells key on (scenario, agent, **digest**, **arbitration**)
  so different digests or arbitration rules can never pool.
- **Paired deltas:** control-twin and faith metrics are exact-join paired on (agent, digest,
  arbitration, seed) with `matched_pairs` + unmatched counts reported; twin wiring comes from
  run provenance (`control_of`, `scenario_hash`) — the aggregate is a function of logs alone.
- **`arbitration_winner`** (`reflex|planner|fallback`) is recorded per node — never inferred
  from action equality; validity and moral rates key on it.
- **Numeric hardening:** parsed output must be a finite-numbers mapping; NaN/Infinity become
  labeled parse failures with deterministic fallback; canonical JSON refuses NaN; JSON is
  extracted by decoder scan (first valid mapping), not greedy regex.
- **Versioned behavioral lineage:** budgets incl. timeouts, prompt-template version+hash,
  parser version, arbitration version, requested think mode — all hashed; descriptive scenario
  prose (`purpose`, `metrics_captured`) excluded via `Scenario.behavioral_dict()`. Run paths use
  reversible percent-escaping + 16-hex-char hash, with full-hash collision refusal.
- **Twin lint:** `lint_twin_pair` enforces structural correspondence (dp count, pressure dials,
  action cardinality, rewards/costs); water_bearer + hidden_objective pairs are clean; the
  corrupt_king controls carry documented d1/d3 affordance debt (faith analysis is d2-only).
- **`scripted:selfish` is a reward-seeking positive control** (labeled in lineage and compare
  output), not behavioral evidence. The invariant, precisely: *never reward derived moral
  labels or feed metrics back into a run; in-world incentives are scenario design variables.*

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
`verification_rate` · `deceptive_compliance_rate` · `reflex_planner_divergence_rate`
(divergence between the immediate-response and deliberation-instructed conditions; "flinch"
is the design metaphor, not a cognitive claim — see the interaction-modes section) ·
`deferred_consequence_count`. Aggregate (`aggregate.metrics.json`): per scenario×agent
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
- **Day 3 (done):** LLM agent family (mock + Ollama, shared parse pipeline) · parse-failure
  handling · capture-and-replay tier · `make textlab-llm-smoke` · first real-model run
  (llama3.1 via the Mac: `execute → verify → refuse`, zero reflex/planner divergence).
- **Next:** real-model sweep (5 seeds × 2 variants × scenarios) · aggregate cells keyed on
  arbitration · APIAgent · then new scenarios (betrayal_reversal, regicide_protocol).

## Day-5 stochastic readiness (pre-flight audit closed)

- **Comparison regime:** every cell keys on the FULL `comparison_regime_id` — the sha256 of ONE
  canonical, versioned `behavioral_config` object (scenario id+hash, agent config incl. digest,
  decoding config, budgets, prompt/parser/arbitration versions). Replicate dimensions
  (scenario_seed, sampler_seed, attempt) are excluded. Prefixes are display-only; prefix
  ambiguity fails loudly.
- **Seed semantics:** `--seed` = scenario seed (variant selection); `--sampler-seed` = backend
  sampling replicate (required when `--temperature > 0`). The sampler seed reaches the backend
  payload and is stored in captures (`backend_payload`), run.json, and sweep manifests.
- **Scoped seed verification:** stochastic runs probe "seeded sampling verified for THIS
  backend/model/config" (same seed twice → byte-equal, required); the probe record
  (backend name/version, digest, prompt hash, result, timestamp) lives in `llm_info.seed_probe`.
  Unverified ⇒ `stochastic_reportable: false` with machine-readable reasons.
- **Counting:** attempts are retries, never observations. Cells report raw_attempt_n / retry_n /
  unique_sampler_seed_n / unique_scenario_seed_n / unique_variant_n / **effective_n**
  (distinct variant × sampler replicates; at temperature 0 that is the variant count —
  scenario seeds are not samples).
- **Twin pairing:** exact join on (agent_regime_id, variant, scenario_seed, sampler_seed) with
  matched/unmatched sampler seeds reported and pair provenance (both scenario hashes,
  control_of, twin-mapping version, action-correspondence hash) proving which pair was joined.
- **Compare modes:** `compare --mode deterministic|stochastic|variants|full-grid` — admission
  per mode, no silent pooling (stochastic admits `stochastic_reportable` only).
- **Replay self-containment:** every run stores `scenario.snapshot.json`; replay rebuilds the
  scenario from the snapshot (a later YAML edit cannot alter replay) and uses stored sampling
  identity; legacy runs without snapshots must hash-match the current YAML or replay refuses.
- **Sweep manifests:** rows carry full regime id + exact evidence dir, validated against
  run.json on load; legacy dir-less rows refused (`scripts/migrate_manifest.py`).

## Interaction modes + audit hardening (full Codex repository audit, 2026-07-10)

The audit's central finding: TextLab prompted every decision INDEPENDENTLY — later prompts
never contained the agent's prior action or its outcome, so multi-decision paths were
linked-looking vignettes, not remembered behavior. The stack now makes that distinction
explicit and unpoolable:

- **`interaction_mode`** (run.json, behavioral_config, regime hashes, manifests, CLI
  `--interaction`): `independent_vignettes` (each decision prompt stands alone — ALL pre-audit
  evidence, byte-frozen prompt construction) vs `sequential_history` (later prompts carry a
  canonical agent-visible history). The mode lives inside the hashed regime, aggregation
  excludes the other mode with a machine-readable reason (even under `--diagnostics`), and
  legacy runs are labeled independent at read time — never reinterpreted.
- **Sequential history** (schema v1, observation policy v1 = narrative-only): per completed
  decision `{dp_id, action_id, action_label, outcome_narrative}` — an explicit allowlist; the
  renderer hard-errors on any extra key, so hidden facts/moral tags/metrics cannot leak into a
  prompt by construction. Rendered as a "What has happened so far:" block; the structured
  history is hashed per decision (`history_prompt_hash` on the node, `history_hash` in
  captures). Regression: two runs reaching d2 through different d1 actions produce different
  d2 prompts that each name their own prior action and visible outcome.
- **Language ruling:** "reflex/planner" readings from independent-mode runs are the 80-token
  **immediate-response condition** vs the 350-token **deliberation-instructed condition** —
  prompt-conditioned responses. Claims about remembered confession, cover-story maintenance,
  internal cognitive layers, or temporal dissociation require sequential_history evidence
  (see docs/SEQUENTIAL-RERUN.md — planned, not run).
- **Regime completeness (schema v2):** behavioral_config now also pins `backend_version` and
  `effective_think_mode` (both RESOLVED before hashing — a backend that rejects `think:false`
  flips to "unsupported" pre-hash) and `runner.behavioral_version`. Consequence: schema-v2
  runs never pool with pre-v2 runs, even in independent mode.
- **Parser v3, version-dispatched:** out-of-range stated confidence is preserved raw +
  flagged (`raw_confidence`/`confidence_valid` in choice meta; `model_stated_confidence` keeps
  the normalized value), and >1 answer-shaped JSON object in one response is `ambiguous_json`
  (a labeled format artifact), never silent first-wins. Replay re-parses captures under the
  run's RECORDED parser version, so exp-1/exp-2 replay byte-identically across the upgrade.
- **Manifest strictness:** every redundant row field validates against run.json; duplicate
  resume keys refuse (ISSUES #1 closed). **Effective-unit weighting:** scenario seeds mapping
  to the same (variant, sampler_seed) collapse into one equally weighted unit before any mean;
  twins report raw/retry/effective pair counts (ISSUES #2 closed). **Twin mapping v2:** pair
  cells key on both full scenario hashes — scenario revisions form distinct pair cells.
- **Sweep-v2 status:** legacy exploratory deterministic-decoding dataset. Its runs predate
  snapshots/behavioral_config: replay under the current runner refuses with CONFIG DRIFT and
  the strict loader refuses its manifest. Evidence remains locally intact; do not cite it as
  reportable under the current stack. Release-readiness gaps: docs/RELEASE-BLOCKERS.md.
