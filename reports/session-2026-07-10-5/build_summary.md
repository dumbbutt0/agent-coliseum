# Build summary — session 2026-07-10-5 (Day 4: provenance & determinism hardening)

**Author:** Claude (Fable). Source of truth: Codex's milestone review
(`reports/codex-review-2026-07-10/findings.md`). All 9 findings closed; the 105-run
cross-model sweep is demoted to PILOT and rerun under the hardened stack (sweep-v2).

## What got fixed (finding → change)

1. **Aggregate admission + lineage keys:** `reportable:false` excluded by default (explicit
   `--diagnostics` mode, loudly labeled); cells + all twin/faith joins key on
   (scenario, agent, model_digest, arbitration); fields preserved in compare output.
2. **Offline replay:** `ReplayLLMAgent`/`agent_from_manifest` — identity from the stored
   `agent_config` verbatim (zero network/fixtures); captures integrity-checked against
   `capture_hash` before replay. Verified on a REAL run with a bogus OLLAMA_HOST.
3. **Evidence preservation:** live LLM attempts → exclusive `<run_id>.aN` dirs, monotonic,
   never truncated; scripted dirs verify-or-refuse on full stored config hash.
4. **`arbitration_winner: reflex|planner|fallback`** recorded per node; metrics validity keyed
   on it, never on action equality (Codex's same-action asymmetric-validity case tested).
5. **Numeric hardening:** mapping-only JSON, finite-only numerics (NaN/Infinity → labeled
   parse failure + deterministic fallback, no crashes), `allow_nan=False` canonical JSON,
   decoder-scan extraction (first valid mapping; junk-brace + two-object cases fixed).
6. **Paired twin/faith deltas:** exact join on (agent, digest, arbitration, seed), matched-pair
   n + unmatched exclusions reported; `control_of`/`scenario_hash` persisted in run provenance —
   the aggregate is now literally a function of logs alone (tested with configs unreachable).
7. **Twin structural lint** (`lint_twin_pair` + `structural_issues`): water_bearer +
   hidden_objective pairs CLEAN; `hidden_objective_aligned` RE-AUTHORED (identical covert
   mechanics — same divert/lie/admit/deflect affordances — only alignment changes);
   corrupt_king controls' d1/d3 affordance debt documented + asserted (faith stays d2-only).
8. **`scripted:selfish` reclassified** as reward_seeking_control (in lineage + compare label);
   invariant reworded: never reward derived moral labels; in-world incentives are design variables.
9. **Complete behavioral lineage:** timeout budgets, prompt-template version+hash, parser
   version, arbitration version, think mode all hashed; descriptive prose excluded via
   `Scenario.behavioral_dict()`; reversible percent-escaped paths + 16-char hash + full-hash
   collision refusal.

## Verified

- **108 tests green** (25 new hardening regressions, one per reviewed failure mode).
- Determinism gates pass under PYTHONHASHSEED {1, 987654} × LC_ALL {C, C.UTF-8}, and a
  **cross-environment byte-identity** check (different env → same bytes) passes.
- Mock smoke green; real Ollama smoke: attempt dir `.a1`, full versioned agent_config stored,
  digest pinned, path `execute → verify → refuse` again.
- **Offline replay on the real run: byte-identical with OLLAMA_HOST pointed at a black hole.**
- Sweep-v2 (reportable rerun, same 3 models × 7 × 5) launched under the hardened stack.
