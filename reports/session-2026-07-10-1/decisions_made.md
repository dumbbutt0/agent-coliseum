# Decisions made — session 2026-07-10-1

1. **`Event.t` pinned to 0.0 in decision logs** — wall-clock in the JSONL would break the
   byte-identity gate; human timestamps live only in `run.json` (`started_at`/`finished_at`),
   which the gate compares minus those two fields.
2. **Deterministic run_id** = `scenario.variant.agent.s<seed>.<config_hash[:8]>` — the id appears
   in every record, so it must be a pure function of inputs; re-running the same inputs overwrites
   the same dir (regenerable-from-seed, matching the arena's fresh-log-per-run pattern).
3. **`config_hash` covers the whole raw scenario YAML + agent spec** — any scenario edit changes
   the hash, so silently-edited scenarios can't masquerade as the same run lineage.
4. **Scripted latencies fixed at 0.0** — measured wall-clock latencies begin with LLM agents
   (Day 3), where nondeterminism is expected and the gate doesn't apply.
5. **`facts` field on DecisionPoint** (ground truth: `harm: none|unverifiable|verified`) — personas
   and future metrics key on scenario ground truth, not on parsing narrative text.
6. **Obedient persona deliberately diverges** (reflex complies, planner verifies unverifiable
   directives) — gives the reflex/planner divergence a guaranteed test fixture from day one.
7. **Contamination lint is a load-time hard error** (word-boundary regex over agent-facing text:
   test/experiment/scenario/simulation/evaluation + famous names) — a contaminated scenario can't
   even load, rather than being caught in review.
8. **Control twins are separate YAML files with `control_of:`** — full scenarios in their own
   right, so control runs use the identical runner path and the delta is honest.
9. **Deferred consequences** (`consequences_deferred: [{after, narrative, state_delta}]`) mature
   into `state_before.recent_events` — the plumbing multi-act scenarios (betrayal_reversal,
   regicide_protocol) need, built and tested now per the spec.
10. **Reused, not modified:** `logging_substrate.RunLogger` (subclassed as `DecisionLog`) and
    `seeding.seed_everything`. Duel/Elo modules untouched.
