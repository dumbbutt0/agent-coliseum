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

## Human identity + control record (hardening H1)

Human authority is a burned one-time token, never a `--role` string. The
owner's passphrase derives an S/KEY hash chain (`tools/council/
identity.py`); the council stores only the tip verifier
(`council/identity/human-tip.json`), and the tip is pinned into the event
chain by `HUMAN_IDENTITY_INITIALIZED`/`ROTATED`. Every human-authority
event (`EXPERIMENT_APPROVED`, `CONDITIONS_SATISFIED`, human
`REQUEST_CANCELED`, `STATUS_CHANGED`, `POLICY_INITIALIZED`,
`HUMAN_IDENTITY_ROTATED`) carries the next preimage, bound to the exact
action, verified and BURNED inside the events lock before the line lands
(a crash wastes one token, never leaves a spendable one). A missing or
substituted verifier where the chain pins one fails closed everywhere
(append, guard preflight, `cli identity-status`). Same-user interception
between keystroke and append is documented out of scope.

The run/pause STATE lives in `council/control.json` — missing or invalid
reads as PAUSED ALL (fail closed). It changes only through the
human-token `STATUS_CHANGED` event (`cli status-set`); the log.md STATUS
line is a cosmetic mirror with zero authority. `council/STOP` remains the
independent hard emergency stop: bootstrap/control events pass a
control-record pause (that is how the owner un-pauses) but never STOP.
Generic `cli record` emits ONLY non-authority bookkeeping
(`BUILD_STARTED`, `BUILD_READY`, `FIX_STARTED`, `WATCHER_ERROR`,
`AUTONOMY_PAUSED`).

Bootstrap trust anchor (cycle-2 blocker 3): the FIRST identity on a root
may not be established by whoever writes first. `identity-init` requires
an enrollment token whose sha256 (domain `council:enrollment:v1`) lives
at the FIXED path `/etc/coliseum/enrollment.sha256` — root-owned and
agent-unwritable, provisioned ONCE by the owner:

    # choose a secret; remember it (it is asked at identity-init)
    printf 'council:enrollment:v1\0%s' 'YOUR-SECRET' | sha256sum
    sudo mkdir -p /etc/coliseum
    echo '<that hash>' | sudo tee /etc/coliseum/enrollment.sha256
    sudo chmod 0644 /etc/coliseum/enrollment.sha256

No anchor file → identity-init fails closed (no automated bootstrap path
exists). The OS boundary is root vs the agent user: if agents hold
passwordless sudo, there is no boundary — a documented requirement.
Bootstrap ordering is pin-before-install: the PIN event lands first,
then the verifier file; any pre-pin failure leaves no verifier, and a
verifier without a chain pin authorizes NOTHING. Recovery
(`identity-restore-from-pin`) derives the CURRENT state by replaying
every post-pin burn from the chain — spent tokens stay spent.

Bootstrap on a fresh (fail-closed) root, owner-attended:
`cli --role human identity-init` (enrollment token + new passphrase)
then `cli --role human status-set --status active`.

## Strict parsing + versioned hashing (hardening H2)

Every council JSON input routes through `tools/council/strictjson.
loads_strict` (item 8): duplicate keys, `NaN`/`Infinity`, trailing data,
and invalid UTF-8 are rejected, and byte/depth/string/collection/node
limits apply before hashing or validation. The bytes that get hashed are
the bytes that get validated, unambiguously.

Hashing is domain-separated (item 12): `domain_hash(domain, obj) =
sha256(domain + NUL + canonical_json)` with distinct domains
(`council:event:v2`, `council:request:v2`, `council:source-verdict:v2`,
`council:result-verdict:v2`, `council:evidence-inventory:v1`, ...), so a
payload can never be reinterpreted across schemas. `PROTOCOL_VERSION` is
`2.0`; hashing and validation DISPATCH on each object's own version, so
new 2.0 events chain onto the 1.0 history with no break, and 1.0 events
remain valid on replay while only 2.0 may be appended. `atomic_write_json`
uses per-process-unique tmp names (no concurrent-writer race).

Request validation (item 11) enforces strict list-element types, bounded
lists/strings, a non-bool bounded test count, and — for v2 requests —
safe relative path fields. Verdict validation additionally enforces an
`audit_mode` enum and an ISO-8601 UTC `timestamp_utc` (carried from the
codex-auto-launcher-audit-002 conditions).

## Authority-context bindings + evidence manifest (hardening H3)

Every v2 verdict binds to its exact authority context (item 3), verified
against the chain at the append boundary (`crosscheck_verdict_bindings`):
`request_payload_hash`, `publication_event_id`+`publication_event_hash`,
`audit_cycle`, `auditor` (must be codex), plus the schema-version domain.
`tests_observed` must equal the request's event-pinned
`expected_test_count` (the semantic check deferred from H2). A result
verdict additionally binds `experiment_config_hash`, `run_id`, `run_dir`,
`evidence_inventory_hash`, `validation_report_hash`, `replay_result`,
`counts`, and `conclusion_scope`. `codex_watch.submit_verdict` populates
the derivable bindings from the verified request and chain, so the
auditor supplies only its judgments; a forged or mismatched binding is
refused at append.

The runner pins an EVIDENCE MANIFEST before `EXPERIMENT_COMPLETE`: a
sorted relpath→sha256 map over the produced `run_dir`, hashed under
`council:evidence-inventory:v1` (CONTENT-only — no wall-clock, so it is
deterministic), stored as a sibling `<run_dir>.manifest.json` outside the
manifested tree. `EXPERIMENT_COMPLETE` and `RESULT_AUDIT_REQUESTED` pin
the inventory hash, so a result approval binds exactly the bytes the
runner produced. `cli verify-evidence <rid>` recomputes and compares,
detecting any post-audit tamper.

## Quarantine projection + hardened chain verification (hardening H4)

Chain verification (item 9) now rejects duplicate event_ids, seq≠position,
malformed event_ids, and REPORTS a torn trailing line
(`ChainReport.suffix_incomplete`/`.torn_bytes`; `.healthy` = ok AND not
torn). Reads may use a valid prefix, but every authority consumer
(guard, policy, launcher, watcher) requires `.healthy`, and `append_event`
refuses to append after a torn tail (which would fuse two lines).
`cli repair-tail` (owner) truncates torn bytes so appends resume.

Projection is quarantine-aware (item 5): `state_machine.authority_status`
re-validates every verdict-authority event during replay and QUARANTINES
a request only when it currently SITS in a pending-authority state
derived from an invalid, unblessed verdict — settled/terminal requests
with a bad historical verdict are flagged but never quarantined, so the
chain stays inspectable and no legacy invalid verdict silently grants
authority. `cli chain-report` shows the picture; `cli bless-event <id>
--reason ...` (owner token → `MIGRATION_APPROVED`, binding the exact
event_id+hash) blesses a reviewed legacy event so it counts again.

The H1 cycle-5 residual is closed by a ROOT-OWNED CHAIN-HEAD CHECKPOINT
(`/etc/coliseum/chain-head.sha256`, owner-provisioned via sudo, holding
`{length, head_hash}`): `checkpoint.verify_checkpoint` confirms the live
chain still carries that event_hash at that position, so any in-place
rewrite of the prefix — undetectable by any agent-recomputable value —
fails closed in guard preflight. Absent file = no constraint (not yet
provisioned). `cli checkpoint-status` prints the JSON to sudo-install.
`policy.milestone_status` now also requires the explicit codex signature.

## Crash-safe transactions + lease locks (hardening H5)

Multi-step council operations that would be inconsistent if interrupted
mid-way now run under a JOURNAL (`council/txn/<txn_id>.json`, `txn.v1`;
item 6). The journal records the ordered steps, which have completed, and
the compensation data. `txn.recover(root, cfg)` — run at codex_watch
startup and the launcher loop top — scans the journal, and for each
interrupted transaction consults the AUTHORITATIVE event chain: it rolls
FORWARD when the terminal event landed and BACK when it did not, and it is
idempotent (a second recovery is a no-op). The claim path is the first
adopter: `codex_watch.claim` runs `[locked → moved → event]`, and a STOP
engaged before the `AUDIT_CLAIMED` append compensates — the request moves
back to `ready/` and the lock is released, leaving no stranded lock and no
half-moved request.

Locks are now leases (item 7). A `lock.v1` body carries an `owner_token`
(`secrets.token_hex`), a `lease_expires_utc`, and a `kind`. `release()`
and `renew()` are COMPARE-AND-DELETE on the token: the holder is read, the
token verified, and only then is the lock removed (rename-then-unlink, a
drvfs-safe commit point) or extended. A wrong or absent token is a no-op,
so a reused PID cannot steal a live lock — authority is the random token,
not the pid. Expiry only makes a lock ELIGIBLE for the existing logged
clearance paths (`cli clear-lock`, the launcher stale-gate, which now reads
`lease_expires_utc` instead of file mtime) — never a silent steal.

## Protocol integrity

The council protocol and the autonomy policy cannot approve modifications
to themselves. Any change to role permissions, event schemas, state
transitions, allowed experiment classes, policy limits, STATUS/STOP
behavior, or approval rules must be committed separately and receive a
dedicated Codex protocol audit before activation. `policy.evaluate`
enforces this mechanically: a request whose scope touches
`tools/council/`, `autonomy_policy.json`, or `PROTOCOL.md` fails
`no_protocol_self_modification` and falls to the human gate.
