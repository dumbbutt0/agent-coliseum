# SC-7 Activation Package — autonomous ollama_local experiment loop

**Status: awaiting the owner's single `amend-policy` token.** Until then the live
policy is v1 and nothing auto-runs. This package is the one owner-input moment
M7 was built toward.

## What activation does

After your token, registered `ollama_local` experiments **auto-approve and run
without per-batch tokens**. The autonomous loop (M7d) proposes the next
registered experiment → the Codex launcher source-audits it → `policy.evaluate`
(the *sole* auto-approval authority) checks every condition → run-task executes
→ offline replay + independent result audit → register/report → next experiment
→ repeat. You stay above it as the constitutional owner; you never approve a
routine batch again.

## The exact policy change (minimal semantic diff, v1 → v2)

```
auto_approval.allowed_experiment_classes:  [sandbox_local]        -> [sandbox_local, ollama_local]
auto_approval.allowed_data_sources:        [synthetic]            -> [synthetic, local_model]
policy_version:                            (absent, =1)           -> 2
amends:                                    (absent)               -> 1
```

**Everything else is byte-identical** — `forbidden_capabilities`
(destructive_tools, cloud_apis, website_automation, weight_training),
`require_go_verdict`, `require_clean_tree`, all `limits`
(compute 240m / wall 360m / storage 2048MB / retries 2 / scenarios 60),
`bounded_loops`, `protected_paths`, `society_milestone`.

- v1 content hash: `4f5b341d26490f8006f2e7ad6f4a8905f637944a3be24d064a33a147a12f1215`
- v2 content hash: `f695acec75ea8486510e85b96b42ddf01129abc1b2d9b4c46d3c4f3baceb67f9`
- live policy is a clean code-defined v1; the chain-head checkpoint (length 265,
  intact) covers the identity root, so the amendment takes effect immediately.

## Every eligibility condition an auto-approved experiment must pass

Enforced by `policy.evaluate` + the runner, re-checked on every run (agent-immutable):
belongs to the ratified active roadmap · design + config frozen and REGISTERED
(a live experiment with no registered `design_hash` is refused, M7b) · source
audit is unconditional GO bound to the exact commit · model digests match
exactly (run_sweep preflight, atomic) · scenario/behavioral/prompt/parser/metrics/
comparison-regime identities match registered values (lint_experiment_config) ·
runs + resources within policy ceilings · external API cost zero
(cloud_apis forbidden) · working tree clean · evidence/retry/resume/replay rules
not weakened · held-out inaccessible · no protected files modified · result still
gets an independent Codex audit.

## Stays human-gated (never auto)

Any NEW experiment class or data source, changed limits/ceilings, changes to the
policy itself, training/weights, held-out access, metrics/judge changes, external
spend, builder/training/society/Hunger-Games automation, public claim acceptance,
identity/enrollment/chain authority — each needs a fresh owner token or amendment.

## Safety envelope (M7c) — your always-on off-switches

- **Return to manual:** `touch <council>/MANUAL` disables auto-approval instantly
  (experiments fall back to the human gate; the council keeps running). Remove it
  to resume.
- **Emergency STOP:** `touch <council>/STOP` halts every transition.
- **Auto-halt on runaway:** 3 consecutive autonomous failures (BLOCKED/PAUSED) OR
  720 minutes rolling autonomous compute → auto-approval halts to the human gate.
  Both counters reset when you re-assert control (`status-set` / a policy action).

## "Agents cannot expand their own authority" — proven, not asserted

The amendment mechanism (M7a) survived three escalating adversarial audit attacks,
each closed + regression-locked:
1. forged amendment payload → policy replay re-authenticates (human sender + token)
2. forged token on a human event → `identity.replay_identity` re-validates every
   token, action-bound
3. forged identity *root* → an amendment is honored only when the root-owned
   chain-head checkpoint (agent-unwritable) anchors the root

## Audit trail (all GO, all integrated)

| Milestone | commit | GO event |
|---|---|---|
| M7a amendment core | e93fad78 | 000465 |
| M7b eligibility | f4f9458 | 000471 |
| M7c safety envelope | 94669123 | 000477 |
| M7d loop driver | 5156bbfd | 000483 |

Adversarial security tests: `tests/test_council_policy_amend.py` (13),
`tests/test_council_policy_envelope.py`, `tests/test_autonomy_experiment_loop.py`,
`tests/test_autonomy_runner.py::test_ollama_local_without_registered_design_is_refused`.
Full suite: 871 passed, 13 skipped.

## Rollback

An invalid token leaves BOTH the file and the effective pin at v1 (atomic
`amend-policy`, `restore_policy_version`). To revert after activation: create a v3
that restores the v1 allowances and amend to it (a fresh owner token) — the
monotonic version chain forbids silently going backward, and `MANUAL` disables
auto-approval immediately in the meantime.

## THE ACTIVATION COMMAND

```
cd ~/agent-coliseum && python3 -m tools.council.cli --role human amend-policy \
    --target-version 2 --impl-commit 5156bbfd843e034728757ad796b8bdce48d28220
```

It prompts for your passphrase (burns one S/KEY token), writes v2, and records a
`POLICY_AMENDED` event binding {v1 hash → v2 hash, version 2, the exact diff, the
audited impl commit, your token}. After it lands, the autonomous loop runs B1
(sequential rerun) and B3 (paraphrase) — its first two experiments — and
continues through the ratified roadmap.
