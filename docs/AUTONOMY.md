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
  -> GO, experiment task:
       POLICY_VALIDATION_REQUIRED -> all conditions hold -> AUTO_APPROVED
       -> run-task (this layer): EXPERIMENT_STARTED -> driver under limits
       -> EXPERIMENT_COMPLETE -> RESULT_VALIDATION_REQUIRED
       -> RESULT_AUDIT_REQUESTED -> Codex result audit
       -> RESULT_APPROVED -> NEXT_MILESTONE_READY: task complete
  -> GO, source-change task:
       fast-forward-only integration of the audited candidate commit
       -> CHANGE_INTEGRATED -> NEXT_MILESTONE_READY: task complete
       (non-fast-forward pauses; nothing is ever rebased or rewritten)
  -> next task
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

`run-task` refuses unless: the request FILE verifies against its root of
trust (cycle-2 audit blocker) — full schema validation including its own
canonical `request_payload_hash`, AND that hash equals the hash pinned by
the authoritative `AUDIT_REQUESTED`/`READY_FOR_REAUDIT` event for the same
commit, so post-audit edits to the mutable lifecycle file (stale hash or
freshly recomputed) never reach policy evaluation or a driver · emergency
stop clear · chain verifies · policy unchanged since pinned · roadmap hash
matches the request's pinned `roadmap_hash` · HEAD == the request's bound
commit · tree clean · request state is `auto_approved` (or human
`approved`) · the request binds BOTH a
frozen `experiment_config_hash` and a canonical `experiment_config_file`
(UNCONDITIONAL — the human-approved path too; audit blocker 1), `--config`
IS that file, and its sha256 equals the frozen hash, all verified before
the config is parsed or a driver selected · the task is in the roadmap,
not human-gated, and its class has an implemented driver · the frozen
config's declared `scenario_count` and `retries_per_unit` are within the
effective limits BEFORE launch (audit blocker 2).

ALL FIVE limits are enforced (audit blocker 2): the effective limit set is
the strictest of the roadmap task, the request's autonomy block, and the
immutable policy caps — wall, storage, compute, retries/unit, scenarios.
The driver runs in a KILLABLE CHILD process
(`tools/autonomy/child_runner.py`): the parent hard-kills it when the
min(wall, compute) deadline passes or when live-monitored storage growth
exceeds the cap (overrun bounded by the 0.25 s poll interval), then pauses
autonomy with the exact reason.

## Result audits (file mechanics)

`codex_watch --submit <verdict.json> --result-audit` requires the request
file in `requests/claimed/`; the initial audit moved it to `complete/`.
`run-task` therefore moves the file back to `claimed/` when it records
`RESULT_AUDIT_REQUESTED` — a protocol file operation, not a content edit.
Codex's submit moves it to `complete/` again.

Result verdicts use the same required fields and hashing as audit verdicts;
`validate_verdict(..., result_audit=True)` accepts APPROVED/BLOCKED, so
both result outcomes go through `codex_watch --submit --result-audit`.
(A 2026-07-11 council defect — the wrapper rejecting APPROVED — was fixed
in the dedicated council-protocol-delta-001 audit; the generic `cli record`
workaround is no longer needed.) After RESULT_APPROVED lands, the Claude
watcher wakes and records NEXT_MILESTONE_READY, completing the task.

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

## Cross-session continuity (resume + the Codex audit auto-launcher)

After a crash or in a fresh Claude session, run
`python3 -m tools.autonomy.cli resume` — it reconstructs, read-only and
deterministically, every request's state and the exact next action from the
event chain and the roadmap.

The CODEX side is automated (separately audited capability, commit 2 of
the launcher plan): `python3 -m tools.autonomy.cli codex-launcher` polls
the chain and, for a request resting at `requested` (source audit) or
`result_audit` (result audit), launches ONE bounded non-interactive
`codex exec` session with a fixed argv, a sanitized environment, a hard
timeout, and a prompt built exclusively from the root-of-trust-verified
request (integrity failure pauses autonomy without launching). The Codex
session claims and submits through `tools.council.codex_watch` itself, so
codex-role events stay signed by Codex. The launcher then verifies
advancement from the chain alone; a non-advancing session records
WATCHER_ERROR and three consecutive failures per published cycle pause
autonomy. STATUS/STOP, the paused flag, and the milestone stop it cleanly.
Service unit (shipped disabled): `tools/systemd/coliseum-codex-launcher.
service` — install only after this capability's own audit returns GO.
Stateless: crash recovery is a restart; nothing depends on process memory.

A process that automatically LAUNCHES new writable CLAUDE builder sessions
remains a recorded FUTURE capability: it must be committed separately and
receive a dedicated Codex protocol audit before activation (commit 3 of
the launcher plan). Until then, a human (or an already-running session)
starts each Claude work session; everything else in the loop is
event-driven.

## Protocol integrity

The council protocol and the autonomy policy cannot approve modifications
to themselves. Any change to role permissions, event schemas, state
transitions, allowed experiment classes, policy limits, STATUS/STOP
behavior, or approval rules must be committed separately and receive a
dedicated Codex protocol audit before activation. `policy.evaluate`
enforces this mechanically: a request whose scope touches
`tools/council/`, `autonomy_policy.json`, or `PROTOCOL.md` fails
`no_protocol_self_modification` and falls to the human gate.
