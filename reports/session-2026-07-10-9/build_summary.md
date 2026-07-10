# Build summary — session 2026-07-10-9 (full-audit correctness hardening)

**Author:** Claude (Fable), builder role per the 2026-07-10 role flip (Codex = auditor).
**Trigger:** Codex's FULL repository audit at `dd00a8b` — verdict **research-use only**.
**Order:** owner's 12-item hardening directive. All 12 closed; no new sweeps, no new
scenarios, no live model calls (battery entirely offline), Exp-1/Exp-2 NOT rerun.

## Audit verification before implementation (claims checked in code, not accepted)

| Audit claim | Verified |
|---|---|
| Later prompts lack prior action/outcome; d2 text presupposes the diversion even via clarify | CONFIRMED |
| Twin aggregation pools scenario revisions | CONFIRMED (twin-specific; regular cells were safe) |
| Sweep-v2 broken provenance/replay | CONFIRMED-worse: replay CONFIG-DRIFTs by construction (no stored behavioral_config since Day-5's identity change) |
| Confidence silently clamped; multi-JSON first-wins | CONFIRMED |
| Regime omits backend_version / effective think / runner version | CONFIRMED |
| Release blockers (license/lock/packaging/evidence) | CONFIRMED; `10.0.0.8` is docs/docstrings only, never code logic |

## What got built (audit item → change)

1. **interaction_mode** — `independent_vignettes | sequential_history` in behavioral_config
   (schema v2), run.json, regime hashes, captures, manifests, `cli --interaction`. Legacy
   evidence labeled independent at read time, never reinterpreted. Modes never pool:
   admission excludes the other mode even under `--diagnostics`.
2. **Sequential history** — allowlisted narrative-only entries `{dp_id, action_id,
   action_label, outcome_narrative}` (observation policy v1); renderer hard-errors on
   extra keys; "What has happened so far:" block; `history_prompt_hash` per node,
   `history_hash` per capture. Regression: different d1 final actions → different d2
   prompts, each naming its own prior action + visible outcome. Leak-sentinel test:
   poisoned hidden state never reaches any prompt.
3. **Independent mode byte-frozen** — pre-change prompt hashes pinned as a regression
   (plan/reflex/bare-state prompts byte-identical).
4. **Language corrections** — audit banners + operational vocabulary (immediate-response /
   deliberation-instructed conditions) on both exp reports (sessions -7, -8) and both wiki
   outcome pages; temporal-dissociation and cover-story interpretations withdrawn; raw
   results and tables unchanged.
5. **Twin mapping v2** — pair cells key on (agent_regime_id, primary_scenario_hash,
   control_scenario_hash); revisions form distinct pair cells; labels carry display
   prefixes with a loud collision guard; full hashes in pair_provenance.
6. **Manifest integrity (ISSUES #1 closed)** — every redundant row field validated against
   run.json + dir/attempt coherence; duplicate resume keys refuse (no last-row-wins).
   Exp-1 (15 rows) and Exp-2 (5 rows) manifests load clean.
7. **Effective units (ISSUES #2 closed)** — attempts → replicate means → (variant,
   sampler_seed) unit means before any cell mean; twins collapse identically and report
   raw_pair_n / retry_pair_n / effective_pair_n. Deterministic aggregates reweight where
   scenario seeds sampled variants unevenly — the mandated correction, not drift.
8. **Regime completeness** — `backend_version` + `effective_think_mode` RESOLVED before
   hashing (warmup doubles as the think probe; sweep probe resolves too);
   `runner_behavioral_version` added. Schema-v2 runs never pool with pre-v2 runs.
9. **Parser v3, version-dispatched** — raw stated confidence preserved + `confidence_valid`
   flag (normalized value kept for schema compat); >1 answer-shaped JSON object =
   `ambiguous_json` (labeled artifact, deterministic fallback); nested/decorative JSON
   handled. Replay re-parses captures under the run's RECORDED parser version — v2 frozen.
10. **Sweep-v2 demoted** — legacy exploratory deterministic dataset; banners on report +
    wiki; CONFIG-DRIFT refusal and manifest refusal verified and documented; nothing deleted.
11. **Sequential rerun documented, NOT run** — `docs/SEQUENTIAL-RERUN.md` (requires the
    authored d2-consistent scenario revision, ISSUES #3 new; gated on Codex re-audit).
12. **Release blockers recorded** — `docs/RELEASE-BLOCKERS.md` (notes only, no release).

## Validation battery (all green, all offline)

- 145 tests (126 existing + 19 new audit regressions in `tests/test_textlab_audit.py`).
- Determinism gates under PYTHONHASHSEED {0, 12345} × LC_ALL=C.
- Offline replay of REAL evidence with network black-holed: exp-2 k11 and exp-1 k11 —
  byte-identical decisions under the new code (the parser-dispatch keystone holds).
- Sweep-v2 replay: CONFIG DRIFT (loud refusal, evidence preserved) — recorded as the
  demotion's basis, run_logs/replay_sweepv2_drift.txt.
- `compare --mode deterministic|stochastic` over all 380 evidence dirs: legacy cells
  intact; the gemma3 stochastic cell now correctly holds exp-1+exp-2 as ONE regime
  (raw 10, effective_n 10, 2 variants × 5 sampler seeds, 0 retries).
- Strict manifest loads: exp-1/exp-2 clean; sweep-v2 refused (expected).
