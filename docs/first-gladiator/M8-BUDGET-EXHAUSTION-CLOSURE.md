# M8 budget-exhaustion incomplete closure

This source slice implements the owner-selected Option A protocol. It does not
run the protocol and grants no permission to inspect or transform the captured
M8 evidence.

## Fixed outcome

The only supported outcome is:

```json
{
  "analysis_status": "budget_exhausted_incomplete",
  "scientific_verdict": "inconclusive",
  "statistics_computed": false,
  "claimable": false,
  "conclusion_scope": "The frozen M8 execution did not complete within its owner-selected budget. The captured evidence is authenticated, but no order-effect or null claim is licensed."
}
```

The closure path has no import or call to the M8 order report. It authenticates
105 completed runs, one nonterminal partial attempt, and 38 unattempted
coordinates. It emits no distance, interval, threshold comparison, effect
estimate, null statement, or order-effect finding.

## Separate owner gate

The result request is exactly
`first-gladiator-m8-incomplete-result-001`. Its lifecycle is:

```text
RESULT_HANDOFF_APPROVAL_REQUIRED
-> RESULT_HANDOFF_APPROVED
-> RESULT_HANDOFF_READY
-> RESULT_AUDIT_REQUESTED
-> RESULT_APPROVED or RESULT_BLOCKED
```

The proposal performs read-only admission and creates no derived artifact.
`RESULT_HANDOFF_APPROVED` is a distinct owner-token action. It is neither
`EXPERIMENT_APPROVED` nor execution authority. The provider-free builder is
unreachable before that event.

If a semantic descendant is required while a source review is merely pending
or has returned an unintegrated GO, `FIX_STARTED` conservatively rewinds that
request to the build gate. An active claimed audit cannot be displaced. The
descendant still requires a new `BUILD_READY`, same-commit re-audit, plain GO,
and integration record; no prior verdict transfers.

For the five closure source ids, the rewind is performed only by
`supersede-audit`. It takes the same request lock used by the auditor claim,
appends `FIX_STARTED`, and moves the prior request and verdict bytes to
digest- and cycle-bound immutable archive names under a recoverable journal.
It refuses an active claim, foreign bytes, an existing archive, or a
same-id race. A later publication is mechanically required to use
`READY_FOR_REAUDIT`.

Request publication holds that same request-scoped lock from the pre-attempt
chain boundary through file publication, event append, and rollback. A refused
cycle cannot mistake a historical event for current authority, cannot remove a
concurrent publisher's file, and leaves no unpublished ready file.

The existing Society handoff command remains:

```text
python3 -m tools.council.cli --role claude result-handoff --file REQUEST.json
```

The M8 continuation, after separate owner direction, is:

```text
python3 -m tools.council.cli --role claude result-handoff \
  --request-id first-gladiator-m8-incomplete-result-001
```

## Evidence and output rules

The primary root remains
`logs/runs/m8-phase2-live-order-sensitivity`. Every admitted file must be a
regular, single-link file under a non-symlink directory. The success manifest,
canonical absent tombstone ledger, partial attempt, inventory, and full
144-coordinate census must match the closed authorization.

Replay uses `build_pack_replay_core_locked`, which performs no write and
records no clock field. The existing `verify_pack_replay` wrapper retains its
historical timestamped file behavior.

The derived root is fixed:

`logs/results/m8-phase2-live-order-sensitivity-budget-exhausted`

It contains exactly:

1. `primary_inventory.json`
2. `replay_attestation.json`
3. `coordinate_census.json`
4. `incomplete_report.json`
5. `incomplete_result_package.json`
6. `validation_report.json`

All bytes are deterministic. A sibling temporary directory is flushed and
renamed once, then the parent directory is flushed. A matching completed
transaction may be adopted after interruption; foreign or changed output is
refused. The primary inventory is compared before and after replay.

## Final disposition

An independent `RESULT_APPROVED` certifies the bundle and the inconclusive
claim ceiling only. It does not establish an M8 order effect or null. Resume
then directs the owner to the human-token `close-paused-result` action, which
binds that exact approved result and cancels the original paused request
without deleting evidence or changing launcher state.
