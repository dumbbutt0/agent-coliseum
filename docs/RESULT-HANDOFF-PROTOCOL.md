# Post-Integration Result Handoff Protocol

Status: preregistration for council design review. This document grants no
authority until a plain `AUDIT_GO` and matching `CHANGE_INTEGRATED` exist.

## 1. Problem and boundary

The experiment state machine admits a result audit only after the bounded
runner records `EXPERIMENT_STARTED`, `EXPERIMENT_COMPLETE`, and
`RESULT_VALIDATION_REQUIRED`. A separately authorized source slice can instead
integrate an implementation and then produce exactly one governed evidence pack.
If that pack is already complete, backfilling runner events would falsify event
chronology, while a standalone `RESULT_AUDIT_REQUESTED` is correctly refused.

This protocol adds a truthful handoff for that narrow case. It does not approve
an experiment, authorize execution, waive result audit, or permit a second run.

## 2. New task kind and events

`result_handoff` is a request-file task kind used only for a result audit. It is
never accepted by the source or experiment launch paths.

Two Claude-role events are added:

1. `RESULT_HANDOFF_READY`: `none -> result_validation`. It records that an
   already-produced evidence pack is ready for independent result audit.
2. `RESULT_FIX_READY`: `fixing -> result_validation`. It records corrected
   derived evidence after `RESULT_BLOCKED`, without claiming another execution.

Both enter the existing `RESULT_VALIDATION_REQUIRED` destination state so the
unchanged next transition is `RESULT_AUDIT_REQUESTED -> result_audit`. Existing
`RESULT_APPROVED`, `RESULT_BLOCKED`, `FIX_STARTED`, and
`NEXT_MILESTONE_READY` semantics remain unchanged.

## 3. Authenticated handoff

The official `result-handoff` command accepts one closed JSON request and
performs these operations in order:

1. Validate the request and all repository paths under the configured roots.
2. Confirm the code repository HEAD equals `target_commit` and the tree is clean.
3. Recompute the sibling `evidence-manifest.v1` inventory from `run_dir` and
   require exact `run_id`, `run_dir`, file map, and `evidence_inventory_hash`.
4. Locate the cited design and implementation `CHANGE_INTEGRATED` events and
   their cited plain, unconditional `AUDIT_GO` events.
5. Require both integrations to name the same code repository; require
   `target_commit` to descend from the integrated implementation commit.
6. Refuse reuse of any cited integration event, run ID, run directory, evidence
   inventory hash, or result binding already present in a prior
   `RESULT_HANDOFF_READY` event.
7. Atomically create the canonical request file directly in `claimed/`, append
   `RESULT_HANDOFF_READY`, then append `RESULT_AUDIT_REQUESTED`. If interrupted
   after the first append, rerunning the same command resumes idempotently after
   verifying byte-identical inputs. Any different input refuses.

The closed request contains:

- protocol version, `task_kind: result_handoff`, request ID, repository, and
  target commit;
- run ID, run directory, manifest file, evidence inventory hash, validation
  list, and validation-report hash;
- design and implementation request IDs, `CHANGE_INTEGRATED` event IDs,
  `AUDIT_GO` event IDs, and integrated commits;
- result binding ID and a conservative conclusion-scope string;
- requested verdicts exactly `RESULT_APPROVED` and `RESULT_BLOCKED`;
- read-only allowed actions and explicit forbidden execution/mutation actions.

`RESULT_AUDIT_REQUESTED` copies the evidence, validation, authorization, and
conclusion bindings from the authenticated request. The result verdict must bind
the same fields under the existing result-verdict schema.

## 4. Result correction

After `RESULT_BLOCKED`, the builder records `FIX_STARTED` normally. The official
`result-fix-ready` command then:

1. Requires state `fixing`, a new clean HEAD, and a commit descending from the
   blocked target.
2. Recomputes the evidence manifest and validation hash.
3. Requires the primary captured files named by the prior handoff to retain
   their hashes; only derived reports, manifests, documentation, or protocol
   fixes may change.
4. Updates the canonical claimed request atomically, appends
   `RESULT_FIX_READY`, and appends a fresh `RESULT_AUDIT_REQUESTED`.

It cannot emit `EXPERIMENT_STARTED` or invoke any experiment driver. A changed
run ID, run directory, primary-capture hash, authorization anchor, or result
binding refuses and requires owner escalation rather than another run.

## 5. Roles, failure handling, and compatibility

- Claude may publish handoff/fix-ready events but may not publish a verdict.
- Codex may claim and publish `RESULT_APPROVED` or `RESULT_BLOCKED` but may not
  construct or alter the handoff.
- Human authority is not synthesized by this protocol: the cited integrations
  and their audited preregistrations must already authorize the governed pack.
- Source and experiment requests retain their current transitions and task-kind
  defaults. Launchers must ignore `result_handoff` except at `result_audit`.
- Council files are changed only through official storage/event helpers. A
  refused or interrupted operation leaves no unpinned ready request.
- The bounded audit-cycle limit remains five. No event is backdated.

## 6. Required regressions

Pin acceptance of one valid handoff and one result-fix cycle. Pin refusal for a
missing/conditional/wrong integration verdict, wrong event or commit, unrelated
or non-descendant HEAD, dirty tree, malformed or drifted manifest, validation
hash drift, reused run/binding/authorization, wrong sender, wrong task kind,
launcher execution, changed primary capture, and invalid source state. Retain
all existing source-task, experiment-task, result-verdict, evidence-verification,
request-transaction, and chain-rebuild tests unchanged.
