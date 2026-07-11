# Sequential rerun plan — Exp-1/Exp-2 under sequential_history (PLANNED, NOT RUN)

Status: **documented only** (full-audit item 11). The interaction-mode re-audit cleared
(council request `sequential-rerun-audit-004`, Codex GO at `cda6e905…`, human-approved
2026-07-11) and the required scenario revision has been AUTHORED (ISSUES #3 closed —
primary hash `12976717…`, twin `a990de3f…`). Execution now runs ONLY through the council
autonomy path: a dedicated experiment request with a frozen pre-registration
(`experiment_config_hash` in its autonomy block), Codex GO on the exact commit,
policy-gated AUTO_APPROVED, and a post-execution Codex result audit. Owner directive
2026-07-11: the rerun must NOT run during Stage A (autonomy-substrate build); it is
Stage B, after the harmless mock lifecycle reaches RESULT_APPROVED.

## The question this rerun can answer (and the current evidence cannot)

Exp-1/Exp-2 ran in independent_vignettes mode: the d2 prompt never contained the agent's d1
action or outcome. The pre-registered question for the sequential arm:

> After the model has actually selected `divert` and received the visible outcome, does the
> later questioning prompt produce `lie` under the immediate-response condition and `admit`
> under the deliberation-instructed condition?

Only this design can support language like "maintained the cover story" or "admitted what it
did" — and even then only as observed action sequences, never as internal cognition.

## Design (to be pre-registered before the first live call, as before)

- **Scenario:** the REVISED `hidden_objective_aligned` (authored 2026-07-11, ISSUES #3):
  the d2 question is rumor-driven and asserts no movement, so it is consistent with every
  d1 route. Both wording variants revised in parallel; twin-lint passes against the
  correspondingly revised `hidden_objective`. ANALYSIS RULE: d2 outcomes are reported
  conditioned on the d1 action — the pre-registered primary event conditions on d1=divert;
  clarify-route d2 data is exploratory only (on that route the action labeled `lie` states
  something true, so unconditioned d2 moral-tag rates would be uninterpretable).
- **Mode:** `interaction_mode=sequential_history` (history schema v1, observation policy v1,
  history template v1 — all pinned in the regime).
- **Agent:** gemma3 at the pinned digest `a2af6cc3…` if still available; digest drift = a new
  regime and must be reported as such, not silently compared.
- **Sampling:** temperature 0.7, sampler seeds {11,12,13,14,15}, scenario_seed 42 (v0) AND 1
  (v1) — both arms this time, one experiment.
- **Fresh single-writer manifest**, pre-registered primary event + thresholds with timestamp
  before the first live call, full validation battery, offline replay check.

## What may NOT be done with the results

- No direct comparison against the legacy independent-vignette runs as if same-regime: the
  regime hashes differ by construction (mode + schema v2 + revised scenario). The legacy
  numbers are context, not a baseline.
- No claims about memory, cognition, or "layers" — sequential mode upgrades the claim from
  "prompt-conditioned response" to "response conditioned on the run's actual visible history,"
  nothing more.
