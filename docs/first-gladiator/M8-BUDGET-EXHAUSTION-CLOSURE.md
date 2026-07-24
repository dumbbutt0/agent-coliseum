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

## Frozen-plan resolution

The design-hashed registry entry intentionally does not carry the operational
`execution_order`. Closure therefore resolves one fresh plan from two
independently frozen inputs:

- registry design SHA-256
  `431871d3266a96999ef02d0d9eb77caba7e6b317135155d3161b1eecf396d533`;
- experiment-config SHA-256
  `4847cadfdac059195986114fed6d61850f3c1d925ca4b97618a06cff59e5c960`,
  which requires `execution_order: interleaved`.

The resolver loads the verified registry bundle, checks the exact config bytes,
runs the existing registry/config consistency lint, and copies the registry
plan before adding the config-owned order. Proposal admission, provider-free
replay, bundle verification, and final primary rederivation all consume that
same resolved plan. Missing or changed order, either changed identity, or a
lint failure refuses before evidence derivation, replay, output, or event
publication.

The integrated `-001` A–E source requests remain historical and recognized by
the state machine. This repair is reviewed only through the current source
family:

- `first-gladiator-m8-incomplete-closure-a-002`
- `first-gladiator-m8-incomplete-closure-b-002`
- `first-gladiator-m8-incomplete-closure-c-002`
- `first-gladiator-m8-incomplete-closure-d-002`
- `first-gladiator-m8-incomplete-closure-e-002`

No `-001` verdict or integration transfers to this repair.

The existing Society handoff command remains:

```text
python3 -m tools.council.cli --role claude result-handoff --file REQUEST.json
```

The M8 continuation, after separate owner direction, is:

```text
python3 -m tools.council.cli --role claude result-handoff \
  --request-id first-gladiator-m8-incomplete-result-001
```

## Interrupted publication recovery

The first owner-approved builder constructed the exact six-file bundle and
then refused because its generic publication layer treated those newly
constructed untracked files as a dirty target. The files are preserved at the
original clean-source commit and are not deleted, ignored, staged, committed,
or rewritten.

Recovery is a separate source and owner lifecycle. Its source reviews use:

- `first-gladiator-m8-incomplete-recovery-a-001`
- `first-gladiator-m8-incomplete-recovery-b-001`
- `first-gladiator-m8-incomplete-recovery-c-001`
- `first-gladiator-m8-incomplete-recovery-d-001`
- `first-gladiator-m8-incomplete-recovery-e-001`

All five require a plain GO and integration at one repair commit. The original
proposal and owner approval remain bound to the original closure-tool commit;
they do not authorize the repaired tool.

After those integrations, a second M8-specific
`RESULT_HANDOFF_APPROVAL_REQUIRED` proposal binds the repair commit, all five
integrations, the original proposal and approval, the closure authorization,
the exact six hashes and transaction, and a fresh bounded replay budget. A
second human-token `RESULT_HANDOFF_APPROVED` must exactly copy that binding.
Generic duplicate owner-gate events remain invalid.

Only then may the repaired command run from its clean audited worktree:

```text
python3 -m tools.council.cli --role claude \
  recover-m8-incomplete-handoff \
  first-gladiator-m8-incomplete-result-001
```

The command operates on the unchanged original worktree. Its status must
contain exactly the six canonical untracked files and no tracked, index, or
other untracked change. Every member must be regular, single-link, and
byte-identical to the approved transaction. Adoption performs no member
rewrite. Mandatory provider-free deep verification occurs within the fresh
budget before `RESULT_HANDOFF_READY` and `RESULT_AUDIT_REQUESTED`.
The verified publication performs the 105-run replay exactly once. If the
process stops after the ready event, an exact ready-journal roll-forward may
finish the claimed request and audit event without replaying again.

This recovery gate grants no model contact, execution retry, scientific
statistic, result verdict, source-request disposition, or later milestone.
The recovery result request binds the exact full-suite expectation of 2,414
passing tests.

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
