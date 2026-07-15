# Post-Integration Result Handoff Protocol

Status: preregistration revision 2 for council design review. This document
grants no authority until a plain `AUDIT_GO` and matching
`CHANGE_INTEGRATED` exist.

## 1. Problem and boundary

The experiment FSM admits a result audit only after its runner records
`EXPERIMENT_STARTED`, `EXPERIMENT_COMPLETE`, and
`RESULT_VALIDATION_REQUIRED`. A separately preregistered source slice can
instead authorize exactly one post-integration evidence pack. Once that pack
exists, backfilling runner events would falsify chronology and a standalone
`RESULT_AUDIT_REQUESTED` is correctly refused.

This protocol supplies a truthful, result-audit-only publication path. It does
not authorize execution, approve a result, waive independent audit, or permit a
second run.

## 2. Request kind, events, and exact FSM semantics

`result_handoff` is a closed request-file task kind. Source/experiment launchers
must refuse it; only the result-audit launcher consumes it after
`RESULT_AUDIT_REQUESTED`.

Two Claude-role publication events are added:

1. `RESULT_HANDOFF_READY`: the initial request's `none -> result_validation`
   transition.
2. `RESULT_FIX_READY`: a new correction request's `none -> result_validation`
   transition. It names a distinct prior result request that is in `fixing`
   after `RESULT_BLOCKED` and `FIX_STARTED`.

Applying either event sets that request's `target_commit`, sets `audit_cycles`
to one plus the cited predecessor's count (one for the initial handoff), and
stores its publication event as the request's authority root. The count is a
lineage count: cycle 6 refuses. `RESULT_AUDIT_REQUESTED` remains
`result_validation -> result_audit`; existing result verdict and
`NEXT_MILESTONE_READY` transitions are unchanged.

The correction uses a new request ID and canonical file. The blocked request
and its completed request file remain immutable. `FIX_STARTED` is recorded on
the blocked request at its already-bound commit; `RESULT_FIX_READY` then cites
that fixing request and binds the new request to the new descendant commit.
There is no target rebinding and no in-place request replacement.

For `result_handoff`, result-verdict binding is specialized as follows:

- the latest `RESULT_HANDOFF_READY` or `RESULT_FIX_READY` for the request is the
  publication event used for `request_payload_hash`, `publication_event_id`,
  `publication_event_hash`, target commit, and audit-cycle derivation;
- `RESULT_AUDIT_REQUESTED` must copy `experiment_config_hash`, `run_id`,
  `run_dir`, `evidence_inventory_hash`, and `validation_report_hash` exactly;
- `codex_watch` injects those values into the unchanged
  `result-verdict.v2`, whose append-boundary cross-check uses the same ready
  event and result-audit event;
- ordinary source and experiment requests continue to use
  `AUDIT_REQUESTED` / `READY_FOR_REAUDIT` exactly as before.

## 3. Closed authenticated request

The canonical request contains the ordinary protocol/repository/test/action
fields plus exactly these handoff fields:

- `task_kind: result_handoff`, request ID, repository, target commit, and
  `request_payload_hash`;
- run ID, safe repository-relative run directory, safe sibling manifest path,
  evidence inventory hash, validation list, and validation-report hash;
- `result_config` and `experiment_config_hash`, where the latter is
  `domain_hash("council:result-handoff-config:v1", result_config)`;
- a closed `artifact_roles` map covering every manifested run-directory member,
  each value exactly `primary_capture` or `derived_result`;
- a `primary_capture_hashes` map equal to the manifest projection for every
  `primary_capture` path;
- design/implementation request IDs, request-payload hashes, publication event
  IDs, plain-GO event IDs, integration event IDs, and integrated commits;
- result binding ID, conservative conclusion scope, and requested verdicts
  exactly `RESULT_APPROVED` / `RESULT_BLOCKED`;
- for corrections only: prior result request ID, prior ready/result-audit/
  blocked/fix-started event IDs, and prior experiment-config/evidence hashes.

`result_config` is closed and contains the authorization profile, run/binding
identity, regime/seed/limits, exact artifact-role map, primary-capture hashes,
and conclusion scope. Thus `experiment_config_hash` authenticates the executed
boundary without pretending that a runner config existed.

The initial Society live-persona pack uses this exact role map:

- `primary_capture`: `run.json`, `chain.jsonl`, `transitions.jsonl`,
  `observations.jsonl`, `activations.jsonl`, `closure.json`, `persona.jsonl`,
  and `persona_latency.jsonl`;
- `derived_result`: `live_report.json`.

The sibling evidence manifest and documentation are outside the manifested run
directory and are derived artifacts. No manifested path may be absent from the
role map; additions, deletion, rename, duplicate normalized paths, symlinks,
non-regular files, or role reclassification refuse.

## 4. Closed authorization predicate

Every handoff validates an `authorization_profile`. Future profiles require a
structured `post_integration_result_authorization` object in both audited source
requests. The already-preregistered Society pilot is admitted only through a
one-entry compatibility profile pinned in code and tests:

- design request `first-gladiator-society-live-persona-design-008`, request hash
  `77c96d1d7e5592c2073ecd19536486b99d48f651951f3219e1ae257d880f4857`,
  integrated commit `e792a1981bdfd76b404a85deefcf933646901a78`;
- implementation request `first-gladiator-society-live-persona-impl-005`,
  request hash
  `b152824b0e0d14346eaa2ef6f3ecb18c7b5d07ab91f2b94e869ff9343f1d7c55`,
  integrated commit `06d3afab15ecbff14723338fd5418751f77a288b`;
- exactly one pack, model
  `huihui_ai/qwen2.5-abliterate:7b-instruct`, digest
  `103482475c9b4d4032999dd5d7383478cad8b966ae6ae984d525daf7352c2219`,
  seed 42, one live agent, two scripted controls, at most eight requested
  decisions, no retry/rerun/training/adaptation, and the preregistered claim
  ceiling;
- run `society_seed_v1--seed42--b63d84694594b499`, live binding
  `7037594c102e5c19ace51a248fd25e315d3685029b4e0b385f1e41a09968c0d5`,
  and the exact artifact-role map above.

The profile is a narrow compatibility bridge for the already-produced pack,
not generic live authority. Its validator mechanically requires:

1. each named request file validates and matches its named publication event,
   payload hash, repository, and commit;
2. each GO is a fully schema-valid, append-bound source verdict, exactly `GO`
   with empty conditions; conditional, quarantined, invalid, or merely blessed
   legacy authority refuses;
3. each integration is that request's terminal `CHANGE_INTEGRATED`, cites the
   named GO, and binds the exact commit;
4. the target is a clean descendant of the implementation commit;
5. the manifest, report regime, run ID, live binding recomputation, limits,
   primary hashes, and conclusion scope equal the profile;
6. no earlier ready event used the profile, integration, run, directory,
   binding, or inventory.

An unrelated same-repository integration or prose-only scope match never
satisfies the profile.

## 5. Journaled publication transaction

The ready event is the durable transaction journal and embeds the full canonical
request plus its hash. The command preflights every validation, transition, and
path before its first durable mutation, then:

1. append `RESULT_HANDOFF_READY` or `RESULT_FIX_READY` with the canonical
   request, request hash, transaction ID, and phase `ready_published`;
2. atomically materialize the exact request bytes in `requests/claimed/` from
   the event payload;
3. append `RESULT_AUDIT_REQUESTED` with copied bindings and transaction ID.

No launcher triggers at `result_validation`; it triggers only after step 3.
Recovery holds the council lock, reads the chain first, and behaves by phase:

- before step 1: no event/file exists, so a retry starts normally;
- after step 1: reconstruct or byte-verify the claimed file exclusively from
  the ready event, then append step 3;
- after step 2: same roll-forward behavior;
- after step 3: verify event and file identity and return the existing event;
- any file without a ready event is an orphan and is removed only when its
  transaction ID is owned by this command; an unknown/conflicting file refuses;
- any changed retry input, mismatched transaction ID, partial/conflicting event,
  or non-identical request bytes refuses without mutation.

Appending events uses the existing council append lock. Request creation uses a
temporary file, fsync, and atomic rename. Recovery is idempotent when run twice;
events are detected by request ID, type, transaction ID, and payload hash, never
by file presence alone. Correction uses the same transaction with a new request
ID, so it has no replacement window.

## 6. Correction rules

For a correction, the new manifest must retain exact equality for the prior
`primary_capture_hashes` map and artifact roles. Only `live_report.json`, the
sibling manifest, evidence documentation, or protocol code/tests may differ.
Changing a primary byte, path, role, run/binding identity, authorization anchor,
or conclusion ceiling refuses and requires owner escalation; the command never
emits an experiment event or invokes a driver.

## 7. Roles, compatibility, and required regressions

- Claude publishes handoff/fix-ready events but never a verdict.
- Codex publishes only `RESULT_APPROVED` / `RESULT_BLOCKED` after independent
  read-only audit.
- Existing source, experiment, policy, human-token, evidence, and verdict paths
  are byte-compatible and retain their current defaults.
- No event is backdated; no result handoff is an execution authorization.

Regressions must cover a valid initial handoff and correction, result-verdict.v2
cross-checks, target/cycle values 1..5 and cycle-6 refusal, every authorization
anchor mismatch, unrelated/conditional/quarantined authority, manifest or
config drift, every primary path mutation/reclassification/symlink/alias case,
run/binding/profile reuse, role violations, launcher refusal, and a crash after
every durable transaction step followed by two recoveries. The full existing
source/experiment/result/evidence/transaction suite must remain green.
