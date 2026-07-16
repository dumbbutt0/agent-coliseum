# Hierarchical Section Councils — Additive Architecture and Pilot Contract

> **Status:** design source only. This document authorizes no implementation,
> activation, model launch, parallel source mutation, new Council authority, or
> default-mode change. The existing sequential Council remains the sole
> canonical authority until separately audited implementation and an explicit
> activation decision satisfy the gates below.
>
> **Source:** `first-gladiator-hierarchical-section-councils-design-001`.
> **Priority decision (owner, 2026-07-15):** build one bounded, measured pilot,
> freeze expansion, then resume Coliseum work through the proven mechanism.
> This is not an open-ended Council rewrite.

## 1. Objective

Evolve the current sequential builder-auditor workflow into a governed
federation of bounded Section Councils so independent work can be prepared,
checked, and packaged concurrently without weakening the Council's present
security or integration guarantees.

The intended relationship is:

```text
                         existing Council Kernel
                                  |
             +--------------------+--------------------+
             |                    |                    |
       Section Council A    Section Council B    Section Council C
       bounded builder      bounded builder      bounded builder
       local assessor       local assessor       local assessor
       deterministic tools  deterministic tools  deterministic tools
             |                    |                    |
             +--------------------+--------------------+
                                  |
                        boundary-impact checks
                                  |
                      existing independent Codex audit
                                  |
                   existing CHANGE_INTEGRATED authority
```

The transformation is **one Council into a governed hierarchy**, not one
Council into an uncontrolled swarm. A section result is preparation evidence.
It is never permission to merge, release, execute an experiment, change a
policy, or promote a scientific claim.

## 2. Repository-grounded starting state

The current implementation already supplies the constitutional kernel:

- `tools/council/schemas.py` is the single validation, role, vocabulary,
  canonical-JSON, and domain-separated hashing authority.
- `tools/council/events.py` owns append-time validation and the canonical
  hash-chained `events.jsonl`.
- `tools/council/state_machine.py` projects one linear lifecycle per request;
  `state.json` is explicitly derived.
- `tools/council/publish.py` binds an exact request file and commit to an
  `AUDIT_REQUESTED` or `READY_FOR_REAUDIT` event.
- `tools/council/codex_watch.py` structurally separates claim and verdict
  submission from builder actions.
- `tools/council/locking.py` provides compare-and-delete lease locks.
- `tools/council/txn.py` provides crash recovery for multi-step Council
  mutations.
- `tools/council/policy.py` preserves protected paths, governance routing,
  final acceptance, and owner-reserved actions.
- `tools/autonomy/` is already the precedent for an executor layer above, not
  inside, the protected Council protocol.
- `configs/autonomy-roadmap.yaml` already represents bounded work with
  `allowed_files`, `forbidden_files`, dependencies, budgets, and one active
  task, but it does not provide section-local audit or parallel conflict
  semantics.

The live protocol is version 2.0, the Council event chain is authoritative,
and new source changes integrate only after an exact Codex verdict and the
existing `CHANGE_INTEGRATED` transition. The generic `record` command cannot
emit authority events. Protected-path changes cannot approve themselves.

Therefore the first hierarchical implementation belongs in a new executor
package, conceptually `tools/section_council/`, rather than changing
`tools/council/`. It consumes verified Council inputs and produces derived
evidence for an ordinary source request. It does not add event types, senders,
verdict values, or state transitions in the pilot.

## 3. Constitutional invariants

Every implementation and activation must preserve all of these:

1. `events.jsonl` remains the sole canonical Council history.
2. Existing request and verdict schemas remain the authority boundary.
3. Claude/builders cannot emit Codex verdict events.
4. A builder cannot assess or approve its own output.
5. A builder cannot choose, alter, suppress, or impersonate its assessor.
6. Local assessment cannot authorize `CHANGE_INTEGRATED`.
7. The exact final candidate commit still receives an independent Codex audit.
8. Any byte change after an assessment makes that assessment stale.
9. A section contract cannot widen its event-pinned Section Program or weaken
   policy or an upstream contract.
10. Section workers cannot write outside mechanically enforced ownership.
11. Parallel work with uncertain conflict status fails closed.
12. Evidence is canonical data or a content-addressed reference, never a prose
    summary substituted for evidence.
13. Blocking findings remain blocking and dependency-aware.
14. The owner retains STOP, identity, policy-amendment, and constitutional
    authority exactly as today.
15. Sequential mode remains supported and is the default until the pilot is
    audited, measured, and explicitly activated.

## 4. Layered authority model

### 4.1 Council Kernel

The existing `tools/council/` package remains the kernel. It continues to own:

- constitutional roles and sender permissions;
- human identity and STOP/control state;
- canonical request, verdict, and event schemas;
- event-chain append and verification;
- policy and governance routing;
- final audit claim and verdict;
- integration authorization;
- canonical transactions, leases, and recovery.

No Section Council receives a Council sender credential. Its
`builder_execution_id` and `assessor_execution_id` are evidence identities,
not new roles and not authority tokens.

### 4.2 Section Councils

A Section Council is a derived execution unit operating under one immutable
`section_contract.v1`. It may contain these logical roles:

- planner;
- builder;
- deterministic test/check runner;
- adversarial local assessor;
- evidence packager.

One process may perform several **non-conflicting mechanical** roles, but the
builder and adversarial assessor identities must differ. Model separation is
helpful but is not the sole control: exact input identities, separate execution
contexts, write isolation, and immutable evidence bindings enforce the role
boundary.

### 4.3 Boundary checks

Boundary checks activate for any change that:

- touches more than one ownership domain;
- changes an exported or consumed interface;
- changes a shared schema or fixture;
- changes identity, provenance, replay, authorization, or event semantics;
- changes a dependency edge;
- affects another section's required invariant;
- creates a read/write or write/write conflict;
- changes a policy excerpt included in another section's context.

In the pilot, boundary checks are deterministic impact classification and
evidence packaging. They are not a new canonical audit verdict. Any classified
cross-section impact is included in the top-level request and inspected by the
existing independent Codex audit.

### 4.4 Integration Council

For the pilot, the Integration Council is the existing source lifecycle:

```text
BUILD_STARTED -> BUILD_READY -> AUDIT_REQUESTED -> AUDIT_CLAIMED
    -> AUDIT_GO -> CHANGE_INTEGRATED
```

It verifies the **assembled final commit**, all section bundles, conflict and
boundary results, stale-input status, full test result, and existing global
invariants. A local section pass never substitutes for any step above.

## 5. Audit levels and exact semantics

| Level | Pilot representation | Meaning | Authority |
| --- | --- | --- | --- |
| L1 section | `local_assessment` in a section bundle | Exact section output satisfies its bounded contract | none outside the bundle |
| L2 boundary | deterministic `boundary_impact_report.v1` plus required checks | Interfaces, ownership, and affected invariants were classified and verified | none outside the top-level request |
| L3 system | existing independent Codex source audit | Final candidate preserves global properties and exact evidence binding | existing Council verdict |

The pilot deliberately uses `pass`, `blocked`, or `error` for a local
assessment, never `GO`. `GO` remains reserved for canonical Council verdicts.

A future dedicated Section event vocabulary would alter constitutional event
schemas and state transitions. It is out of scope until a separately audited
protocol amendment is justified by measured pilot results.

## 6. Canonical derived records

All records use strict JSON, exact key sets, bounded strings and lists, safe
repository-relative paths, duplicate-key rejection, and canonical JSON. Every
digest below is lowercase SHA-256 hex over a domain-separated canonical
preimage. Operational timestamps are permitted as non-identity metadata only.

### 6.0 `section_program.v1` and the non-circular root of trust

Domain: `council:section-program:v1`.

Section work starts before the assembled candidate commit and its final audit
request exist. A Section Contract therefore **must not** bind a future
`request_payload_hash` or future target commit; doing so would create a hash
cycle. The pre-build root is instead:

1. deterministically construct `section_program.v1` in memory from the planned
   request id, repository, current clean base commit, execution mode, complete
   proposed section declarations (ids, ownership, dependency edges, and
   budgets), and schema/profile versions; the program does not contain
   contract ids or its own hash;
2. compute `section_program_hash` under the domain above;
3. record an ordinary existing `BUILD_STARTED` whose payload contains that
   exact hash, mode, and base commit before source work begins;
4. make every Section Contract bind the resulting `BUILD_STARTED` event id,
   event hash, and `section_program_hash`.

The program object is then persisted as derived build evidence. Its bytes must
match the event-pinned hash. Section Contracts and the full work graph are
derived afterward and bind that program, so no identity is circular. The event
grants no new authority; it authenticates the builder's declared plan and base
through the existing append-only chain.

After assembly, the ordinary final audit request binds the finished commit and
its own `request_payload_hash` exactly as today. That commit contains or
content-addresses the section evidence bundles. Binding therefore flows in one
direction with no cycle:

```text
BUILD_STARTED -> section program -> contracts/work -> final commit
      -> ordinary audit request -> independent verdict -> integration
```

If a work need appears outside the pinned program, the scheduler escalates. It
does not amend the program silently. A new/widened program requires a fresh
source lineage authorized under the existing scope rules.

### 6.1 `section_contract.v1`

Domain: `council:section-contract:v1`.

Identity rule:

```text
section_contract_id = domain_hash(
    "council:section-contract:v1",
    the exact contract object with section_contract_id omitted
)
```

Required fields:

```text
schema_version                 = "section_contract.v1"
section_contract_id            = sha256 hex
planned_parent_request_id      = ordinary Council request id
parent_build_event_id          = exact BUILD_STARTED event id
parent_build_event_hash        = exact BUILD_STARTED event hash
section_program_hash           = event-pinned sha256 hex
base_commit                    = clean 40-hex commit at program creation
section_id                     = bounded slug
contract_version               = positive integer
objective                      = bounded string
owned_paths                    = nonempty normalized path-pattern list
readable_paths                 = normalized path-pattern list
forbidden_paths                = nonempty normalized path-pattern list
allowed_operations             = nonempty enum list
forbidden_operations           = nonempty enum list
upstream_dependencies          = list of dependency ids + exact digests
consumed_interfaces            = list of interface ids + exact versions/digests
exported_interfaces            = list of interface ids + exact versions/digests
required_invariants            = nonempty stable-id list
required_checks                = nonempty stable-id list
required_evidence              = nonempty stable-id list
threat_model                   = nonempty stable-id list
assessment_profile             = exact profile id + version
resource_budget                = bounded execution budget object
executor_policy                = allowed executor classes and model policy
escalation_rules               = nonempty enum list
completion_conditions          = nonempty stable-id list
integration_preconditions      = nonempty stable-id list
```

Contracts may narrow the event-pinned Section Program but cannot widen it.
`owned_paths` must be a subset of the program's declared source scope; the
actual final diff must later be a subset of the ordinary audit request scope.
Readable access is not write ownership. `forbidden_paths` always includes the
live Council root, `.git/`, root-owned anchors, canonical run/evidence roots
unless explicitly read-only, hidden-evaluation material, and all other active
sections' owned paths.

### 6.2 `section_work_graph.v1`

Domain: `council:section-work-graph:v1`.

The graph binds one frozen set of contracts. Each work item contains:

```text
work_item_id
section_contract_id
dependencies
read_set
write_set
shared_interfaces
required_audit_levels
priority
resource_budget
status
execution_identity
```

`work_item_id` is derived from the planned request id, event-pinned program,
contract, operation, frozen base commit, and input digests. Wall-clock time,
queue order, PID, and worker completion order are excluded from identity.

### 6.3 `section_context_bundle.v1`

Domain: `council:section-context-bundle:v1`.

The context bundle is a reproducible, minimal projection. It records:

- section contract id;
- planned parent request, `BUILD_STARTED` event, and Section Program bindings;
- base commit;
- exact source paths and content digests;
- exact upstream interface paths and digests;
- exact policy/protocol excerpts and digests;
- exact relevant tests and digests;
- prior finding ids affecting the section;
- omitted-path categories;
- bundle digest.

The bundle stores content-addressed references when practical. It cannot omit
an affected downstream contract merely to reduce context. Minimality follows
impact analysis; it does not override completeness.

Builder and assessor context bundles differ. The assessor receives the exact
contract, base, proposed output, full relevant diff, deterministic results,
affected upstream/downstream contracts, and prior findings. It does not trust
the builder's narrative summary.

### 6.4 `section_finding.v1`

Every finding binds:

```text
finding_id
audit_level
severity
section_contract_id
affected_implementation_digest
invariant_id
evidence_refs
reproduction
status
resolution_id_or_null
reassessment_id_or_null
```

Findings are append-only within an evidence lineage. A corrected output gets a
new digest and reassessment; it never edits a prior finding away.

### 6.5 `section_evidence_bundle.v1`

Domain: `council:section-evidence-bundle:v1`.

Required fields:

```text
schema_version
section_evidence_bundle_id
section_contract_id
work_item_id
planned_parent_request_id
parent_build_event_id
parent_build_event_hash
section_program_hash
base_commit
implementation_commit_or_tree_digest
changed_paths
diff_digest
builder_execution_id
assessor_execution_id
builder_context_bundle_digest
assessor_context_bundle_digest
dependency_snapshot_digest
test_manifest_digest
test_result_refs
deterministic_check_refs
invariant_results
finding_refs
resolution_refs
local_assessment             = pass | blocked | error
resource_usage
chain_event_refs
staleness_inputs
```

`builder_execution_id` and `assessor_execution_id` must be unequal and bind
separate execution records. `local_assessment=pass` is invalid if any required
check is missing, any blocking finding is unresolved, any digest mismatches, or
any staleness input differs from the frozen contract.

### 6.6 `boundary_impact_report.v1`

Domain: `council:boundary-impact-report:v1`.

The report includes the frozen final diff, changed ownership domains, changed
interfaces, affected contracts, dependency closure, activated boundary checks,
conflicts, unresolved/unknown classifications, and required top-level audit
scope. Unknown impact is blocking.

### 6.7 `section_comparison_report.v1`

This report compares equivalent sequential and hierarchical pilot workloads.
It binds both workload identities and records:

- wall-clock and critical-path duration;
- total executor runtime;
- model calls and measured/estimated tokens by role;
- deterministic tool calls;
- audit cycles and findings by severity;
- reproduced and unreproduced findings;
- escaped defects found later;
- context bytes/tokens and duplicate-context estimate;
- human interventions;
- integration conflicts;
- stale-work count;
- cost per accepted section;
- unavailable measurements and limitations.

No speed, quality, or cost claim is valid without this bound comparison.

## 7. Deterministic conflict and scheduling algorithm

### 7.1 Path normalization

Before dispatch, resolve every declared path relative to the exact repository
root. Refuse absolute paths, `..`, empty segments, NULs, symlink/reparse escape,
case-fold collisions on case-insensitive deployments, and any path whose native
identity cannot be established under the repository's current path rules.

The candidate write set is the union of declared `owned_paths` and the
operation-specific predicted outputs. After execution, the actual real diff is
recomputed and must be a subset of that write set.

### 7.2 Conflict relation

For active work items A and B, concurrent dispatch is allowed only when all are
true:

```text
A.write_set intersection B.write_set = empty
A.write_set intersection B.read_set  = empty, unless B pins immutable base bytes
B.write_set intersection A.read_set  = empty, unless A pins immutable base bytes
shared interface versions/digests are equal
dependency closure is satisfied
neither item is stale or blocked
```

Any glob ambiguity, platform path ambiguity, generated-path uncertainty, or
unclassified shared fixture means conflict. The scheduler fails closed and
serializes or escalates; it never asks workers to avoid overlap voluntarily.

### 7.3 Dispatch order

Eligible work is sorted by:

```text
(dependency_depth, priority, section_id, work_item_id)
```

The sorted order determines admission and evidence identity. Worker completion
order does not. A parallel run and a sequential run over the same frozen graph
must produce the same admitted work set and equivalent content evidence.

### 7.4 Isolation

Each source-writing section receives a separate git worktree rooted at the
same frozen base commit. It may write only its owned paths. No two active
sections write the integration worktree. Outputs are admitted into the final
candidate by a deterministic assembler only after local assessment and
conflict revalidation.

The assembler applies section outputs in sorted `work_item_id` order, verifies
the resulting file digests against each bundle, and refuses textual or semantic
conflicts. It does not resolve conflicts by preference. The assembled commit is
new evidence and must pass the complete top-level audit.

Read-only or deterministic-check sections may share an immutable checkout when
their output directories are isolated.

## 8. State machines

### 8.1 Derived section lifecycle

```text
declared
  -> validated
  -> eligible
  -> dispatched
  -> built
  -> checked
  -> assessment_pending
  -> passed | blocked | error | escalated | stale
  -> packaged
```

The lifecycle is derived evidence in the pilot, not a new Council request FSM.

Rules:

- `validated` requires a schema-valid contract whose parent bindings verify.
- `eligible` requires satisfied dependencies and no conflicts.
- `built` requires complete outputs and a real-diff scope pass.
- `checked` requires every deterministic required check.
- `passed` requires independent assessor identity and no blocking findings.
- any relevant input mutation moves the item to `stale`.
- `packaged` is allowed for pass, blocked, error, or escalated so failures are
  never suppressed.

### 8.2 Parent integration lifecycle

The parent remains an ordinary source request. It can be published only after:

- all required section bundles exist and verify;
- every required section has `local_assessment=pass`;
- boundary impact is known and all required checks pass;
- the final assembled tree is clean and committed;
- the complete existing suite passes;
- the request scope names the entire actual final diff and relevant global
  invariants.

Then the normal Codex audit begins. A blocked local section prevents publication
but does not create canonical Council authority. A top-level Codex blocker
invalidates affected section bundles through dependency-aware rules.

## 9. Staleness and dependency-aware invalidation

A section bundle becomes stale when any of these changes:

- section contract, pinned Section Program, or `BUILD_STARTED` binding;
- base commit or implementation bytes;
- relevant dependency version or digest;
- consumed/exported interface;
- required policy/protocol excerpt;
- relevant test or fixture;
- evidence bundle bytes;
- upstream blocking finding or resolution;
- boundary-impact closure;
- assessor profile or required quorum.

Staleness is computed, not declared by a worker. Only downstream dependents of
the changed input are invalidated. An unrelated section remains reusable when
its complete staleness input set is unchanged.

After assembly, every bundle is checked again against the final commit. A
section whose files differ after another patch application is stale and blocks
publication.

## 10. Escalation and high-risk domains

Section Councils must escalate rather than guess on:

- ambiguous or widened scope;
- overlapping ownership;
- contradictory parent requirements;
- shared identity/provenance changes;
- authorization or event-chain changes;
- security-critical uncertainty;
- unclassified cross-section effects;
- irreproducible evidence;
- assessor disagreement beyond the bounded repair budget.

These domains are ineligible for independent parallel source mutation in the
pilot:

- `tools/council/` and Council schemas/state transitions;
- identity, anchors, STOP/control, policy, final verdict logic;
- event-chain append/verification;
- transactions, leases, compensation, and recovery;
- canonical evidence mutation;
- hidden-evaluation access controls;
- global run, experiment, or regime identity semantics.

Documentation may describe those domains read-only, but any implementation
touch routes as a separate protected-path protocol source under current rules.

## 11. Deterministic-first executor policy

Use deterministic code for schema and path validation, changed-path
classification, contract hashing, ownership conflicts, dependency checks,
chain/request verification, evidence completeness, test execution, stale-input
detection, resource accounting, and output assembly.

Use bounded smaller models only for non-authoritative contract comparison,
requirement extraction, test-gap suggestions, evidence indexing, and summaries.

Reserve capable independent models for complex implementation, adversarial
assessment, boundary reasoning, security review, and the final system audit.
Executor capability never expands the verdict it may issue.

The pilot does **not** autonomously launch writable builder models. It validates
the execution/evidence layer using deterministic fixtures and externally
initiated builder/assessor sessions. An automatic writable-builder launcher is
a future, separately audited capability, consistent with `AUTONOMY.md`.

## 12. Crash, retry, and recovery behavior

- Every work item uses a unique output leaf and an O_EXCL claim carrying an
  owner token and lease.
- A journal records `claimed`, `workspace_created`, `built`, `checked`,
  `assessed`, `packaged`, and `assembled` phases.
- Recovery consults content evidence, not PID or mtime, and either rolls forward
  an already committed phase or removes only the transaction's own uncommitted
  outputs.
- Duplicate dispatch of one `work_item_id` has one winner; a late worker cannot
  overwrite a completed bundle.
- Retry creates a new `execution_id` but retains the work-item identity and
  records the failed predecessor.
- A crashed or expired worker never causes its local result to be inferred as a
  pass.
- STOP prevents new dispatch and assembly. In-flight processes are terminated
  under their resource controls, and partial evidence is retained as error
  evidence where safe.

Pilot recovery code must reuse the audited Council locking/storage primitives
only through public, non-authority interfaces or implement an isolated derived
journal under its own output root. It must not mutate live Council locks or
transactions.

## 13. Backward compatibility and activation

Execution modes:

```text
sequential    # existing behavior; default
hierarchical  # opt-in, only for a validated eligible work graph
```

The implementation must satisfy:

- no historical Council event rewrite;
- no new sender/event/verdict/state in the pilot;
- unchanged sequential command behavior;
- version-dispatched parsing for new derived schemas;
- absent hierarchical configuration means sequential behavior;
- hierarchical failure falls closed, never silently falls back after partially
  writing outputs;
- switching the default requires explicit owner authorization after comparison
  evidence and independent audit.

## 14. Pilot selection

### 14.1 Chosen pilot: deterministic evidence/report packaging

The first pilot is **derived evidence and report packaging**, not identity,
governance, event-chain, transaction, replay semantics, or experiment-regime
construction.

Why it is eligible:

- clear isolated output paths;
- read-only access to frozen fixtures;
- deterministic expected results;
- strong malformed-input tests;
- no canonical evidence mutation;
- no model or experiment contact;
- useful measurement of context duplication and parallel scheduling;
- failures cannot grant authority because the ordinary top-level audit remains.

The implementation fixture contains two genuinely independent work items:

1. **Request evidence index** — validate and inventory an isolated, frozen
   request fixture; write only `pilot/output/request-index/`.
2. **Test evidence index** — validate and inventory an isolated, frozen test
   manifest fixture; write only `pilot/output/test-index/`.

A third boundary work item consumes both verified indexes and produces only a
`boundary_impact_report.v1`. It cannot run until both dependencies pass. The
same workload runs once sequentially and once with two parallel eligible
workers. Outputs must be content-equivalent and independently reassessed.

### 14.2 Pilot acceptance

The pilot proves only:

- contract and evidence identities;
- scope enforcement;
- deterministic conflict refusal;
- separate builder/assessor execution identities;
- pass/blocked/error local semantics;
- dependency-aware staleness;
- equivalent admitted work under sequential and parallel scheduling;
- truthful comparative telemetry;
- unchanged final Council authority.

It does not prove general multi-agent engineering speed, lower cost across all
work, or equal global defect detection. Those remain hypotheses.

## 15. Required implementation slices

### Slice HSC-A — deterministic schemas and validator

Add the isolated executor package with:

- Section Contract, work graph, context bundle, finding, evidence bundle,
  boundary report, and comparison report validation;
- domain-separated hashing;
- normalized-path and scope validation;
- deterministic conflict classification;
- dependency and staleness calculation;
- no worker launch and no Council mutation.

Route as a normal source request and independently audit the exact commit.

### Slice HSC-B — single-section executor pilot

Add isolated work roots, deterministic tool execution, real-diff enforcement,
separate external assessment ingestion, evidence packaging, and crash-safe
derived journals. Run one section without parallelism.

### Slice HSC-C — controlled parallel pilot

Run the two independent fixture items concurrently, refuse an overlapping-write
fixture, produce the boundary report, and compare against sequential mode.

### Slice HSC-D — one real Coliseum source pilot

Only after HSC-A through HSC-C receive independent GO: select one low-risk real
Coliseum report/evidence-packaging change, execute it through the opt-in mode,
and submit the assembled final commit through the ordinary Council.

### Freeze and resume

After HSC-D, freeze framework expansion. Resume the Coliseum critical research
path using hierarchical mode only where measured eligibility holds. New needs
must arise from real Coliseum use and route as bounded audited slices.

## 16. Test matrix

### Schema and identity

1. malformed Section Contract refused;
2. unknown schema version refused;
3. duplicate JSON keys/non-finite numbers/trailing bytes refused;
4. contract id mismatch refused;
5. planned request id, `BUILD_STARTED` event/hash, program hash, or base-commit
   mismatch refused;
6. unsafe or absolute paths refused;
7. undeclared output path refused;
8. unsupported operation/executor/profile refused;
9. evidence bundle digest mismatch refused;
10. builder/assessor identity collision refused.

### Scope and conflict

11. builder attempts a forbidden-path write;
12. actual diff exceeds owned paths;
13. two sections overlap writes;
14. one section writes another's mutable read;
15. immutable pinned read permits safe sharing;
16. ambiguous glob/case/symlink identity fails closed;
17. hidden cross-section impact not declared by builder is detected from the
    real final diff;
18. uncertain conflict classification blocks dispatch;
19. parallel and sequential admission sets are identical;
20. worker completion order does not change assembled content.

### Assessment and authority

21. local pass presented as integration approval is refused;
22. builder-authored assessment is refused;
23. implementation changes after assessment make it stale;
24. missing required evidence blocks pass;
25. unresolved blocking finding blocks pass;
26. finding survives repair and links to its resolution/reassessment;
27. top-level publication cannot omit a required section bundle;
28. ordinary Codex audit remains required;
29. ordinary `CHANGE_INTEGRATED` remains the only integration event;
30. sequential mode behavior is unchanged.

### Dependency and recovery

31. dependency version/interface/policy/test change invalidates only affected
    work;
32. shared-dependency blocker marks dependents blocked or stale;
33. interrupted work resumes without duplicate outputs;
34. duplicate dispatch has one winner;
35. expired/wrong lease token cannot overwrite or remove another worker;
36. partial bundle cannot be interpreted as pass;
37. STOP prevents new dispatch and assembly;
38. malformed journal fails closed with preserved diagnostics;
39. retry links the failed execution without reusing its assessment;
40. assembler detects post-assessment drift.

### Measurement and negative controls

41. sequential/hierarchical workload identities are equivalent;
42. unavailable token/cost measures are reported unavailable, not zero;
43. wall-clock time is telemetry, never identity;
44. artificial delay fixture demonstrates real overlap without brittle
    production wall-clock assertions;
45. seeded defect is detected in both modes;
46. seeded boundary defect is not cleared by two local passes;
47. no improvement claim emitted when confidence/coverage is insufficient;
48. full existing suite remains green.

## 17. Completion gates

| Gate | Required proof |
| --- | --- |
| Design | exact source commit, clean tree, documentation validation/full suite, independent Codex GO, `CHANGE_INTEGRATED` |
| HSC-A | focused adversarial tests, full suite, exact schemas/interfaces, independent Codex GO, integration event |
| HSC-B | one complete local lifecycle, crash/retry proof, separate identities, no canonical mutation, audit/integration |
| HSC-C | two independent tasks overlap in execution, conflict fixture refuses, deterministic equivalence, comparison report, audit/integration |
| HSC-D | one real low-risk Coliseum slice, no escaped scope, final ordinary Council audit, measured report |
| Default activation | owner decision after evidence; migration/rollback runbook; no unresolved blocker; explicit policy/activation record if required |

Code existing is never sufficient. Every gate requires its end-to-end artifact
and provenance.

## 18. Threat model

| Threat | Required control |
| --- | --- |
| builder selects/impersonates assessor | orchestrator assigns distinct execution identity and context; equality refuses |
| local pass becomes global approval | local enum is not `GO`; no canonical authority event; final existing audit remains mandatory |
| scope creep | parent-subset validation plus actual real-diff enforcement |
| overlapping parallel writes | normalized write/read conflict graph; isolated worktrees; fail closed on uncertainty |
| incompatible section identities | exact interface/dependency digests and boundary closure |
| summary laundering | integration consumes raw content-addressed evidence, not builder prose |
| stale verdict/bundle | deterministic invalidation on every bound input and final-commit recheck |
| finding suppression | append-only finding lineage; dependent work invalidation |
| builder/auditor scratch sharing | separate contexts and execution roots; scratch is never evidence |
| cheap-model overreach | executor profiles cap task and verdict; deterministic checks own exact claims |
| cost routing weakens quality | same required evidence and final audit; compare defect detection, not intent |
| scheduler nondeterminism | frozen graph, deterministic admission order, completion order excluded from identity |
| crash/duplicate worker | O_EXCL claim, owner-token lease, journal, content-based recovery |
| context minimization hides impact | impact-derived inclusion; unknown dependency blocks |
| high-risk kernel decentralization | explicit ineligible domain registry and protected-path gate |
| metrics gaming | prebound comparison workload, negative controls, unavailable values explicit |
| framework rewrite stalls Coliseum | four bounded slices, freeze after real pilot, resume research path |

## 19. Authorization matrix

| Action | Required authority |
| --- | --- |
| Integrate this design | ordinary independent Council source audit |
| Implement `tools/section_council/` HSC-A | separate implementation source audit |
| Run deterministic isolated pilot | implementation GO plus ordinary local execution limits |
| Run writable builder models automatically | separate launcher design and implementation audits; not authorized here |
| Add canonical Section events/roles/verdicts | dedicated protected Council protocol audit and applicable owner authority |
| Change default to hierarchical | explicit owner decision after measurement |
| Parallelize high-risk kernel domains | explicit owner architecture decision plus dedicated audits |
| Contact Ollama/live models | existing live-execution authorization; not authorized here |
| Run Blender | separately approved Windows sandbox architecture; not authorized here |
| Change weights/labels/hidden suites | existing dedicated gates; not authorized here |

## 20. Success and rollout decision

The hierarchical pilot is successful only if it demonstrates all of:

- existing protocol guarantees unchanged;
- strict mechanical scope enforcement;
- builder/assessor independence;
- exact evidence binding;
- local/global authority separation;
- deterministic conflict detection and scheduling;
- dependency-aware invalidation;
- safe parallel execution for eligible work;
- backward-compatible sequential mode;
- at least one measured reduction in wall time, expensive-model use, context
  duplication, or estimated cost;
- non-inferior seeded-defect detection on the bounded pilot.

Even success does not justify broad parallelization. The activation proposal
must list eligible sections, ineligible sections, measurements, limitations,
and any escaped defect discovered later. If defect detection is worse or the
comparison is inconclusive, default sequential mode remains and the result is
recorded as a useful negative finding.

## 21. Exact next sequence

1. Independently audit and integrate this inert design.
2. Build HSC-A only.
3. Independently audit and integrate HSC-A.
4. Build and audit HSC-B and HSC-C as bounded sources.
5. Run one HSC-D real Coliseum pilot and compare it with sequential mode.
6. Freeze the framework.
7. Resume the Coliseum scientific roadmap, using Section Councils only where
   their measured contract permits.
8. Resume Blender only after a new, separately authorized Windows sandbox
   architecture resolves the exhausted AppContainer design lineage.

The first real Coliseum candidate after the pilot should be a low-risk,
file-disjoint evidence/reporting slice. Identity, policy, event-chain,
transaction, and scientific-claim machinery remain central until later
evidence justifies any narrower decomposition.

## 22. Explicit non-goals

This design does not:

- change the Council constitution or owner authority;
- add Section verdict events to the canonical chain;
- permit builders to self-audit;
- make hierarchical execution the default;
- authorize automatic writable builder sessions;
- authorize an unlimited agent swarm;
- weaken full-system audits;
- parallelize overlapping source mutation;
- claim a 2–5x improvement before measurement;
- resume or weaken the blocked Blender sandbox;
- authorize live experiments, training, hidden-suite access, publication, or
  external actions;
- delay Coliseum indefinitely for framework perfection.

The bounded architectural commitment is simple: **local correctness may be
parallelized, but global authority remains centralized and evidence-bound.**
