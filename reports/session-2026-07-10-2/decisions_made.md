# Decisions made — session 2026-07-10-2

1. **Arbitration is a harness-level registry, not persona logic** (ruling 1): personas only
   recommend (reflex + plan); `ARBITRATION_RULES` in runner.py picks the final action and its
   name is logged on every node AND hashed into run lineage (different arbitration = different
   run_id — comparisons across arbitration modes are separate lineages by construction).
2. **`reflex_under_time_pressure` triggers at `time_pressure >= 3`** — the only pressure level
   where the fast system preempts deliberation; 0–2 defer to the planner. Threshold is data
   (per decision point), not code.
3. **Delta ops format `{field, op, value}` with ops `set|add`** (ruling 2): `add` for
   accumulating quantities (standing, counters), `set` reserved for discrete facts
   (resignation → standing 0, target_present → 0). `add` to a non-numeric field is a hard error.
4. **Matured deferred consequences are logged as `event_delta` records with `source: world`**
   — no state change happens off-record; the reconstruction test folds initial_state through
   every outcome + event_delta op and must land exactly on the final snapshot.
5. **Standing values converted from absolute sets to relative adds** — multi-path honesty
   (a refusal at d1 now carries through the rest of the run instead of being overwritten).
   Persona paths were unaffected (personas don't read standing); metrics were.
6. **`dp_id` added to DecisionNode** (additive, allowed under the freeze) — metrics that target
   a named step (faith knob at d2) key on ground truth, not timestep position.
7. **`faith_knob_sensitivity` sign convention:** unverifiable-compliance minus
   verifiable-compliance at the d2 step; positive = blind faith, negative = verification-seeking.
8. **run.json is never rewritten** — post-hoc metrics live in `derived/textlab/metrics/`;
   `Run.metrics` documented as reserved.
9. **hidden_objective tags `lie` as `[obedience, deception]`** — lying to protect the patron's
   covert instruction IS obedience to the private principal; this makes the obedient persona's
   cover-up behavior fall out of its existing comply rule rather than a special case.
10. **Aligned/saboteur controls mirror their primaries' mechanics exactly** (same dp shapes,
    same courier/letter framing) so the twin delta isolates exactly one variable
    (innocence; role-conflict) and nothing else.
