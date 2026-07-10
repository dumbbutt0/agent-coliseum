# Build summary — session 2026-07-10-6 (Day 5: stochastic-readiness hardening)

**Author:** Claude (Fable). Source of truth: Codex's pre-flight audit (verdict: blocked)
+ the owner's 10-step directive with 4 amendments. All 7 findings closed; stochastic
sampler-seed sweeps remain GATED on Codex's narrow re-audit.

## Fixed (finding → change)

1. **Comparison regime (blocker):** cells now key on the FULL sha256 of ONE canonical,
   versioned `behavioral_config` object (regime + behavioral-config schema versions inside);
   agent_regime_id (scenario block excluded) for twin joins; prefixes display-only with a
   loud collision guard. Temp-0 vs temp-0.7, changed scenario_hash, budgets, prompt/parser
   versions, arbitration, digest: none can pool (tested each).
2. **Sampling provenance (blocker):** scenario_seed vs sampler_seed split; sampling config
   (mode/temperature/decoding) in run.json + behavioral_config + captures; sampler seed
   reaches the Ollama payload (`options.seed`) and the exact payload is stored per capture;
   `stochastic_reportable` with machine-readable exclusion reasons; SCOPED seed-probe record
   (backend name/version, digest, prompt hash, result, timestamp) — "verified for this
   backend/model/config," never universal.
3. **Counting:** attempts are retries, not observations — cells report raw_attempt_n /
   retry_n / unique_{sampler_seed,scenario_seed,variant}_n / effective_n; metric means are
   over replicate means. Sweep-v2 cells now truthfully report effective_n=2.
4. **Sweep resume:** manifest rows keyed (full regime_id, scenario_seed, sampler_seed) with
   exact evidence dirs, validated against run.json on load; legacy dir-less rows REFUSED;
   numeric-only attempt parsing (.a10 can never beat .a2 lexicographically).
5. **Twin pairing:** exact join on (agent_regime_id, variant, scenario_seed, sampler_seed);
   attempts collapse first; unmatched sampler seeds/variants + excluded attempts reported;
   pair provenance (both scenario hashes, control_of, twin_mapping_version,
   action_correspondence_hash from the runs' snapshots) proves WHICH pair was joined.
6. **Replay self-containment:** every run stores scenario.snapshot.json; replay rebuilds the
   scenario from the snapshot (YAML edits cannot alter replay — tested), uses stored sampling
   identity; legacy runs without snapshots must hash-match or replay refuses loudly.
7. **Manifest/report mismatch:** sweep-v2 manifest MIGRATED (105/105 exact dirs, original at
   .pre-migration, ambiguity-refusing migrator kept as scripts/migrate_manifest.py); report
   provenance line amended.
8. **Compare modes:** deterministic | stochastic | variants | full-grid with per-mode
   admission; stochastic admits stochastic_reportable only; no silent cross-mode pooling.

## Verified (owner's step 9, in order)

126 tests green (18 new stochastic regressions) · env gates 4/4 combos · deterministic mock
smoke · stochastic mock smoke (reportable) · real Ollama deterministic smoke · **real
stochastic Ollama smoke** (llama3.1, temp 0.7, k=11: seed probe VERIFIED against ollama
0.31.1, payload carries seed, stochastic_reportable=true) · **offline replay of the real
stochastic run byte-identical** (OLLAMA_HOST black-holed) · sweep-v2 deterministic compare:
21 cells, 3 models, 0 excluded, honest counts, paired twins with provenance.

## NOT done (by design)
The target stochastic sweep (hidden_objective_aligned × 3 models × t0.7 × 5 sampler seeds)
is GATED on Codex's narrow re-audit. No new scenarios, models, or claims.
