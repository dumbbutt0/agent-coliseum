# Bounded autonomy (v1) — executor layer over the council protocol

Owner directive 2026-07-11: operate the Claude↔Codex builder-auditor loop
autonomously through the society-substrate milestone, under the immutable
policy (`council/autonomy_policy.json`, human-created, hash-pinned) and a
hash-pinned machine-readable roadmap. `tools/council/` remains a PROTECTED
path — this layer (`tools/autonomy/`) only calls it.

## Authority order

1. Emergency STATUS/STOP controls (`council/log.md` first line; `council/STOP`)
2. The immutable autonomy policy
3. The hash-pinned structured roadmap (`Claude-Wiki/coliseum/autonomy-roadmap.yaml`)
4. Council events, requests, and verdicts (`events.jsonl` is authoritative)
5. The exact committed repository state
6. Wiki prose and reports — context only, NEVER executable authority

## The loop (one bounded task at a time)

```
eligible roadmap task
  -> BUILD_STARTED -> implement (scoped to allowed_files) -> tests
  -> commit by-name -> clean-tree check -> BUILD_READY -> publish request
  -> Codex claims + audits the EXACT commit
  -> BLOCKED: FIX_STARTED, scoped fixes only, max 5 audit cycles
  -> GO: POLICY_VALIDATION_REQUIRED -> all conditions hold -> AUTO_APPROVED
  -> run-task (this layer): EXPERIMENT_STARTED -> driver under limits
  -> EXPERIMENT_COMPLETE -> RESULT_VALIDATION_REQUIRED
  -> RESULT_AUDIT_REQUESTED -> Codex result audit
  -> RESULT_APPROVED: task complete -> roadmap + wiki updated -> next task
```

No conversational statement replaces a structured council event. Any failed
precondition appends `AUTONOMY_PAUSED` with the exact reasons and stops —
only the owner resumes.

## Commands

```
python3 -m tools.autonomy.cli validate-roadmap          # schema + policy caps + hash
python3 -m tools.autonomy.cli resume [--json]           # deterministic next action
python3 -m tools.autonomy.cli preflight [--request-id]  # guard conditions now
python3 -m tools.autonomy.cli policy-continue --request-id ID   # crash recovery at go/policy_validation
python3 -m tools.autonomy.cli run-task --request-id ID --config FILE
```

`run-task` refuses unless: emergency stop clear · chain verifies · policy
unchanged since pinned · roadmap hash matches the request's pinned
`roadmap_hash` · HEAD == the request's bound commit · tree clean · request
state is `auto_approved` (or human `approved`) · sha256(config file) ==
the request's frozen `experiment_config_hash` · the task is in the roadmap,
not human-gated, and its class has an implemented driver. Wall-clock and
storage growth are measured against the STRICTER of the roadmap task and
the request's autonomy block; exceeding either pauses autonomy.

## Result audits (file mechanics + a known council defect)

`codex_watch --submit <verdict.json> --result-audit` requires the request
file in `requests/claimed/`; the initial audit moved it to `complete/`.
`run-task` therefore moves the file back to `claimed/` when it records
`RESULT_AUDIT_REQUESTED` — a protocol file operation, not a content edit.
Codex's submit moves it to `complete/` again.

KNOWN COUNCIL DEFECT (discovered 2026-07-11, not fixed here because
`tools/council/` is protected): `submit_verdict(result_audit=True)` runs
`validate_verdict`, which only accepts BLOCKED/GO/GO_WITH_CONDITIONS — so
the convenience wrapper can never submit an APPROVED result verdict. The
protocol itself is fine: `RESULT_APPROVED` is codex-role in SENDER_ALLOWED
and legal from `result_audit` in the FSM. v1 therefore instructs Codex to
record APPROVED result verdicts via the generic
`tools.council.cli --role codex record --type RESULT_APPROVED …` with the
full verdict as the payload (BLOCKED still works through the wrapper).
Fixing the wrapper is queued for the next DEDICATED council protocol audit.

## Roadmap

Strict YAML subset (stdlib parser, `tools/autonomy/roadmap.py`): 2-space
indents, mappings, block sequences, scalars, `[]`, full-line comments —
tabs/flow/anchors/multiline refused. Hash = sha256 of the file bytes,
pinned into each request (`roadmap_hash` field) at publish time; drift is
refused by the guard. Task limits may be STRICTER than the policy caps,
never larger (validated at load): storage ≤ 2048 MB per task (mock and
sequential experiments: 1024 MB), runtime ≤ policy wall cap, fix cycles
≤ 5. Exactly one task may be `active`.

Allowed task classes: source_change_local, tests_local, scripted_experiment,
mock_experiment, ollama_local, deterministic_sweep_local,
stochastic_sweep_local, offline_replay, report_generation, wiki_update,
clean_clone_reproduction, local_git_commit, codex_read_only_audit.
The forbidden list (cloud_api, third_party_web, public_release, git_push,
create_remote, email_or_messaging, real_credentials, personal_data,
destructive_action, evidence_deletion, history_rewrite,
autonomy_policy_change, stop_control_change, weight_training, lora_training,
fine_tuning, external_prompt_injection_testing, arbitrary_network_access,
purchases_or_spending, automatic_limit_increase, post_milestone_expansion)
is validated at roadmap load — a task naming one never validates, and work
discovered to require one pauses autonomy with the exact reason.

## Cross-session continuity (v1 = resume, NOT durable autonomy)

Owner correction 2 (2026-07-11): this version does NOT provide durable
cross-session autonomy. After a crash or in a fresh Claude session, run
`python3 -m tools.autonomy.cli resume` — it reconstructs, read-only and
deterministically, every request's state and the exact next action from the
event chain and the roadmap. A process that automatically LAUNCHES new
writable Claude sessions is a recorded FUTURE capability: it must be
committed separately and receive a dedicated Codex protocol audit before
activation. Until then, a human (or an already-running session) starts each
Claude work session; everything else in the loop is event-driven.

## Protocol integrity

The council protocol and the autonomy policy cannot approve modifications
to themselves. Any change to role permissions, event schemas, state
transitions, allowed experiment classes, policy limits, STATUS/STOP
behavior, or approval rules must be committed separately and receive a
dedicated Codex protocol audit before activation. `policy.evaluate`
enforces this mechanically: a request whose scope touches
`tools/council/`, `autonomy_policy.json`, or `PROTOCOL.md` fails
`no_protocol_self_modification` and falls to the human gate.
