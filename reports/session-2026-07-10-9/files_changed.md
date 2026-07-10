# Files changed — session 2026-07-10-9

## Code
- coliseum/textlab/schema.py — BEHAVIORAL_CONFIG_SCHEMA_VERSION 2, TWIN_MAPPING_VERSION 2,
  INTERACTION_MODES, HISTORY_SCHEMA_VERSION/OBSERVATION_POLICY_VERSION/
  RUNNER_BEHAVIORAL_VERSION; build_behavioral_config(+interaction/runner blocks);
  Run.interaction_mode; DecisionNode.history_prompt_hash (conditional emission).
- coliseum/textlab/agents.py — PARSER_VERSION 3 + DISPATCHABLE_PARSER_VERSIONS;
  _extract_json_mapping_v3; parse_llm_response(parser_version=...) with raw-confidence
  meta; classify_failure ambiguous_json; HISTORY template constants +
  build_history_block (allowlist-enforcing); build_prompt history support;
  LLMAgent.{parser_version, backend_version, resolve_effective_config}, meta merge,
  history_hash in captures, spec_dict + effective_think_mode/backend_version;
  OllamaAgent.resolve_effective_config (warmup = think probe + version fetch);
  ReplayLLMAgent recorded parser/backend versions.
- coliseum/textlab/runner.py — interaction_mode param/validation/replay-inheritance;
  resolve_effective_config pre-hash; history accumulation + state injection +
  history_prompt_hash; Run field.
- coliseum/textlab/metrics.py — interaction_mode in per-run report; _admit mode exclusion
  (+ belt-and-braces pool check); _cell_metrics effective-unit collapse; twin pairing
  rewritten revision-keyed (pair prefixes guard, raw/retry/effective pair counts);
  aggregate/write_aggregate interaction_mode param + non-clobbering filenames.
- coliseum/textlab/cli.py — --interaction on run/metrics/compare; mode line in output.
- scripts/sweep_models.py — manifest_load full-row validation + duplicate refusal +
  dir/attempt coherence; probe.resolve_effective_config; interaction_mode in rows.

## Tests (126 → 145)
- tests/test_textlab_audit.py — NEW: 19 regressions (one per audit guarantee).
- tests/test_textlab_hardening.py — fake-Ollama helper resolves effective config offline;
  decoder-scan test split into frozen-v2 + v3 assertions.

## Docs
- docs/TEXTLAB.md — interaction-modes + audit-hardening section; flinch phrasing bounded.
- docs/ISSUES.md — #1/#2 closed with regressions named; #3 opened (d2 presupposition).
- docs/SEQUENTIAL-RERUN.md — NEW (planned experiment, not run).
- docs/RELEASE-BLOCKERS.md — NEW (item 12, notes only).

## Reports (amendments, results unchanged)
- reports/session-2026-07-10-8/sweep_report.md — audit banner + operational decomposition.
- reports/session-2026-07-10-7/sweep_report.md — audit banner.
- reports/session-2026-07-10-5/sweep_v2_report.md — demotion banner.

## Wiki (vault, outside this repo)
- 01_raw/coliseum-build-sessions/codex-audit-2026-07-10/audit-verdict.md (staged) +
  SOURCES.md entry; decisions/coliseum-interaction-mode-ruling.md (new);
  outcomes/coliseum-exp{1,2}-* audit banners (+ exp-2 lesson rewritten);
  outcomes/coliseum-sweep-v2-reportable.md retitled/demoted; index.md lines amended
  (+1 decision line); log.md build entry; council/log.md disposition + re-audit request;
  memory/coliseum-project-state.md updated.
