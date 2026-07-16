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
>
> **Revision 2:** addresses every reproduced finding in `AUDIT_BLOCKED`
> `001491-15a91e44`: OS-enforced worker confinement; scheduler-minted distinct
> principals and assessor-owned complete finding manifests; exact identities
> and one complete evidence root for every derived record; and a closed
> exact-path change algebra bound into the ordinary final audit request.

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
10. Section workers run inside an OS-enforced mount/capability sandbox and can
    write only a private output leaf and private temporary memory; source,
    integration, Git metadata, Council state, and all other host paths are
    read-only or absent.
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

No Section Council receives a Council sender credential. Its scheduler-minted
assignments, principal credentials, and launcher receipts are evidence
identities, not new Council roles and not authority tokens.

### 4.2 Section Councils

A Section Council is a derived execution unit operating under one immutable
`section_contract.v1`. It may contain these logical roles:

- planner;
- builder;
- deterministic test/check runner;
- adversarial local assessor;
- evidence packager.

One process may perform several **non-conflicting mechanical** roles, but never
the builder and adversarial assessor roles for the same section. Before either
role starts, the trusted parent scheduler mints a `section_assignment.v1` from
its event-pinned program. The assignment binds the role, principal credential
identity, launcher/session receipt, attempt, exact context, sandbox profile,
workspace, and permitted output leaf. A worker cannot mint, select, or edit its
assignment.

Builder and assessor assignments must carry different allowlisted
`principal_id` values and different launcher/session receipts. Unequal opaque
execution ids alone are explicitly insufficient. In the first model-assisted
pilot the builder principal is the existing Claude builder context and the
assessor principal is a separately launched Codex assessor context. A
deterministic assessor may replace the model only where the assessment profile
contains no judgment; that result is described as deterministic validation,
not independent adversarial review.

The assessor writes one sealed `section_assessment_manifest.v1` into an output
root that is unavailable to the builder. That manifest enumerates the complete
finding set, check set, input/output digests, and predecessor reassessment
lineage. The packager inventories the whole sealed assessor root and recomputes
the manifest; it cannot select favorable findings. Model separation is helpful
but not the sole control: scheduler-owned assignments, distinct principals,
separate execution contexts, OS write isolation, complete root inventories,
and immutable evidence bindings enforce the role boundary.

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

### 6.0 Closed encoding and type algebra

All HSC records use the existing strict JSON parser and canonical JSON. Every
top-level record has **exactly three keys**:

```text
{"schema_version": V, ID_FIELD: H, "payload": OBJECT}
```

For the domain and `ID_FIELD` assigned in §6.1:

```text
record[ID_FIELD] = domain_hash(
    DOMAIN,
    {"schema_version": record["schema_version"], "payload": record["payload"]}
)
```

Missing or extra keys, unknown versions, duplicate keys, a mismatched self-id,
or a mismatched content-file SHA-256 are refused. A reference is always the
exact two-key object `{"record_id": H, "content_sha256": H}`. It binds both
semantic identity and stored bytes. Cross-type use is rejected from the
referencing field's required schema version.

The schema notation is:

```text
H       lowercase [0-9a-f]{64}
G       lowercase Git commit [0-9a-f]{40}
E       Council event id [0-9]{6}-[0-9a-f]{8}
R       existing Council request slug
S       [a-z0-9][a-z0-9-]{1,63}
P       normalized repository-relative path from §7.1
N       JSON integer, bool excluded, 0 <= N <= declared bound
B       JSON boolean
T       bounded nonempty UTF-8 string
REF     exact {"record_id": H, "content_sha256": H}
NULLREF JSON null or REF
```

All set-like arrays are sorted by their canonical JSON bytes and reject
duplicates. Ordered arrays contain exact objects with contiguous `ordinal: N`
starting at zero. Maps are forbidden in record payloads unless their exact key
set is specified below. Timestamps, PID, host scheduling, queue order, and
mutable status never appear in these identities. They may be captured in a
non-authoritative operation log whose content file is inventoried by the root,
but they cannot satisfy a gate.

Exact nested value types:

```text
REF_ITEM = {"record_id": H, "content_sha256": H}

FILE_REF = {
  "path": P, "blob_sha256": H,
  "git_mode": "100644" | "100755", "kind": "file"
}

PREDICTED_CHANGE = {
  "path": P,
  "allowed_kinds": nonempty sorted subset of
      ["add", "delete", "modify", "mode", "rename"],
  "rename_source": P | null,
  "required": B
}

ACTUAL_CHANGE = {
  "path": P,
  "kind": "add" | "delete" | "modify" | "mode" | "rename",
  "rename_source": P | null,
  "blob_before": H | null, "blob_after": H | null,
  "mode_before": "100644" | "100755" | null,
  "mode_after": "100644" | "100755" | null
}

BUDGET = {
  "max_wall_seconds": N, "max_cpu_seconds": N,
  "max_output_bytes": N, "max_attempts": N
}

INTERFACE_REF = {"interface_id": S, "version": N, "digest": H}

CHECK_RESULT = {
  "check_id": S, "status": "pass" | "fail" | "error",
  "evidence_ref": REF
}

METRIC = {
  "metric_id": S, "availability": "measured" | "estimated" | "unavailable",
  "unit": S, "value": N | null, "evidence_ref": NULLREF
}
```

Symlinks, submodules, special files, directories as write grants, arbitrary
Git modes, and unbounded maps are not representable in v1.

### 6.1 Record registry

| `schema_version` | ID field | Domain |
| --- | --- | --- |
| `section_program.v1` | `section_program_id` | `council:section-program:v1` |
| `section_contract.v1` | `section_contract_id` | `council:section-contract:v1` |
| `section_work_graph.v1` | `section_work_graph_id` | `council:section-work-graph:v1` |
| `section_context_bundle.v1` | `section_context_bundle_id` | `council:section-context-bundle:v1` |
| `section_content_record.v1` | `section_content_record_id` | `council:section-content-record:v1` |
| `section_assignment.v1` | `section_assignment_id` | `council:section-assignment:v1` |
| `worker_sandbox_profile.v1` | `worker_sandbox_profile_id` | `council:worker-sandbox-profile:v1` |
| `worker_sandbox_attestation.v1` | `worker_sandbox_attestation_id` | `council:worker-sandbox-attestation:v1` |
| `section_finding.v1` | `section_finding_id` | `council:section-finding:v1` |
| `section_assessment_manifest.v1` | `section_assessment_manifest_id` | `council:section-assessment-manifest:v1` |
| `section_evidence_bundle.v1` | `section_evidence_bundle_id` | `council:section-evidence-bundle:v1` |
| `boundary_impact_report.v1` | `boundary_impact_report_id` | `council:boundary-impact-report:v1` |
| `section_comparison_report.v1` | `section_comparison_report_id` | `council:section-comparison-report:v1` |
| `final_scope_manifest.v1` | `final_scope_manifest_id` | `council:final-scope-manifest:v1` |
| `section_evidence_root.v1` | `section_evidence_root_id` | `council:section-evidence-root:v1` |

Every payload below has exactly the listed keys and types. References are
type-checked and must resolve inside the same root unless a field explicitly
names an existing Council event/Git commit or the comparison report's two
already sealed external evidence roots. External comparison roots are verified
by exact id/content SHA-256 and are never made members of the new root, avoiding
a reference cycle.

### 6.2 `section_program.v1` — pre-build root

Payload keys:

```text
planned_request_id: R
repository: T
base_commit: G
execution_mode: "sequential" | "hierarchical"
section_declarations: sorted nonempty array of {
  "section_id": S,
  "predicted_changes": sorted nonempty array[PREDICTED_CHANGE] by path,
  "read_inventory_refs": sorted array[REF],
  "dependency_section_ids": sorted array[S],
  "budget": BUDGET,
  "assessment_profile_id": S
}
schema_profile_refs: sorted nonempty array[REF]
root_policy_version: N
```

Section declarations reject duplicate paths across sections and dependency
cycles. The program contains no contract ids and no self-id.

Before source work, the HSC wrapper computes and stores the record, then emits
an existing ordinary `BUILD_STARTED` whose payload includes exactly these HSC
bindings in addition to the normal objective/scope fields:

```text
"section_program_id": H
"section_program_content_sha256": H
"hsc_base_commit": G
"hsc_execution_mode": "sequential" | "hierarchical"
```

The resulting event grants no new authority. Every child record binds the
program REF and the exact `BUILD_STARTED` event id/hash. The final audit request
does not yet exist, so this ordering is non-circular.

### 6.3 `section_contract.v1`

Payload keys:

```text
program_ref: REF
planned_request_id: R
parent_build_event_id: E
parent_build_event_hash: H
base_commit: G
section_id: S
contract_version: N (>= 1)
objective: T
predicted_changes: sorted nonempty array[PREDICTED_CHANGE] by path
read_inventory_refs: sorted array[REF]
forbidden_host_roots: sorted nonempty array[T]
allowed_operations: sorted nonempty subset of
  ["analyze", "emit_patch", "emit_report", "run_allowlisted_check"]
forbidden_operations: sorted nonempty subset of
  ["council_write", "git_write", "integration_write", "network",
   "process_escape", "unregistered_output"]
upstream_contract_refs: sorted array[REF]
consumed_interfaces: sorted array[INTERFACE_REF] by interface_id
exported_interfaces: sorted array[INTERFACE_REF] by interface_id
required_invariant_ids: sorted nonempty array[S]
required_check_ids: sorted nonempty array[S]
required_evidence_ids: sorted nonempty array[S]
threat_ids: sorted nonempty array[S]
assessment_profile_ref: REF
budget: BUDGET
executor_profile_ids: sorted nonempty array[S]
escalation_rule_ids: sorted nonempty array[S]
completion_condition_ids: sorted nonempty array[S]
integration_precondition_ids: sorted nonempty array[S]
```

The contract must equal or narrow its program declaration. Every predicted
write is an exact file path; there is no write glob or owned directory.

### 6.4 `section_work_graph.v1`

Payload keys:

```text
program_ref: REF
contract_refs: sorted nonempty array[REF]
work_items: sorted nonempty array by work_item_id of {
  "work_item_id": H,
  "section_contract_ref": REF,
  "operation": "analyze" | "emit_patch" | "emit_report" |
               "run_allowlisted_check",
  "dependency_work_item_ids": sorted array[H],
  "read_inventory_refs": sorted array[REF],
  "predicted_changes": sorted array[PREDICTED_CHANGE] by path,
  "shared_interfaces": sorted array[INTERFACE_REF] by interface_id,
  "required_audit_levels": sorted nonempty subset of
      ["section", "boundary", "system"],
  "priority": N,
  "budget": BUDGET
}
```

For each work item, `work_item_id = domain_hash(
"council:section-work-item:v1", exact work-item object with work_item_id
omitted plus program_ref)`. The graph is frozen membership only. Execution
identity and mutable status are forbidden in it.

### 6.5 `section_context_bundle.v1`

Payload keys:

```text
program_ref: REF
contract_ref: REF
work_item_id: H
base_commit: G
role: "builder" | "assessor"
source_files: sorted array[FILE_REF] by path
interface_refs: sorted array[INTERFACE_REF] by interface_id
policy_files: sorted array[FILE_REF] by path
test_files: sorted array[FILE_REF] by path
prior_finding_refs: sorted array[REF]
proposal_ref: REF | null
deterministic_result_refs: sorted array[REF]
omitted_category_ids: sorted array[S]
```

An assessor context must include the proposal, exact diff preview, required
deterministic results, all affected upstream/downstream interfaces, and every
prior finding in the lineage. Context minimality never overrides those
requirements.

### 6.6 Closed content records

Every referenced non-JSON-record blob is wrapped by
`section_content_record.v1`. Payload keys:

```text
program_ref: REF
artifact_type: one of
  "schema_profile" | "read_inventory" | "assessment_profile" |
  "launcher_receipt" | "source_snapshot" | "proposal" | "diff_preview" |
  "test_manifest" | "test_result" | "check_evidence" |
  "finding_evidence" | "reproduction" | "resolution" |
  "protected_inventory" | "operation_log" | "conflict_evidence" |
  "assembler_binary"
storage_relpath: P
media_type: "application/json" | "text/plain" | "text/x-diff" |
            "application/octet-stream"
byte_length: N
blob_sha256: H
producer_assignment_ref: NULLREF
parent_content_refs: sorted array[REF]
```

`storage_relpath` must begin exactly
`artifacts/section-council/<planned_request_id>/content/`; all segments still
obey §7.1. No absolute or external path is representable. The packager opens it
no-follow, verifies size and SHA-256, and inventories the record and blob. Every generic `REF` field in
this design that does not name another explicit §6.1 schema must resolve to a
content record with the artifact type implied by the field name. For example,
`schema_profile_refs` permits only `schema_profile`, `proposal_ref` only
`proposal`, and `test_result_refs` only `test_result`. Type substitution is
invalid.

### 6.7 Assignments and structural principal separation

`section_assignment.v1` payload keys:

```text
program_ref: REF
contract_ref: REF
work_item_id: H
role: "builder" | "assessor"
principal_id: S
principal_credential_digest: H
launcher_receipt_ref: REF (artifact_type="launcher_receipt")
session_nonce: H
attempt: N
context_ref: REF
sandbox_profile_ref: REF
workspace_id: H
output_leaf: S
```

The parent scheduler writes assignments into its protected orchestration root
before dispatch. Worker sandboxes receive them read-only. `principal_id` and
credential digest must match a scheduler-owned allowlist pinned by the program's
schema profile. For one section, builder and assessor must differ in
`principal_id`, credential digest, launcher receipt, and session nonce. The
builder cannot supply the assessor fields.

`worker_sandbox_profile.v1` payload keys:

```text
platform: "linux-bwrap-v1"
launcher_binary_sha256: H
argv_template_sha256: H
source_snapshot_ref: REF
read_only_mount_refs: sorted nonempty array[REF]
writable_mountpoint: "/out"
private_tmpfs_bytes: N
unshare_user: true
unshare_pid: true
unshare_net: true
no_new_privileges: true
capability_set: []
seccomp_profile_sha256: H
environment_allowlist: sorted array[S]
```

`worker_sandbox_attestation.v1` payload keys:

```text
program_ref: REF
assignment_ref: REF
sandbox_profile_ref: REF
observed_mount_table_ref: REF (artifact_type="check_evidence")
observed_process_status_ref: REF (artifact_type="check_evidence")
observed_environment_ref: REF (artifact_type="check_evidence")
source_snapshot_ref: REF (artifact_type="source_snapshot")
output_inventory_ref: REF (artifact_type="read_inventory")
protected_host_before_ref: REF (artifact_type="protected_inventory")
protected_host_after_ref: REF (artifact_type="protected_inventory")
external_write_attempt_count: N
external_write_success_count: N
exit_status: N
```

Eligibility requires zero external-write successes and equal before/after
protected-host digests. An attestation is supporting evidence, not a substitute
for the kernel-enforced mount namespace.

### 6.8 Findings and complete assessor ownership

`section_finding.v1` payload keys:

```text
program_ref: REF
contract_ref: REF
assessor_assignment_ref: REF
affected_proposal_ref: REF (artifact_type="proposal")
audit_level: "section" | "boundary" | "system"
severity: "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
invariant_id: S
claim: T
evidence_ref: REF (artifact_type="finding_evidence")
reproduction_ref: REF (artifact_type="reproduction")
affected_path: P | null
blocks_local_pass: B
status: "open" | "resolved" | "unreproduced"
predecessor_finding_ref: NULLREF
resolution_evidence_ref: NULLREF
```

`section_assessment_manifest.v1` payload keys:

```text
program_ref: REF
contract_ref: REF
work_item_id: H
assessor_assignment_ref: REF
assessor_context_ref: REF
proposal_ref: REF (artifact_type="proposal")
check_results: sorted nonempty array[CHECK_RESULT] by check_id
finding_refs: sorted array[REF]
finding_inventory_sha256: H
finding_count: N
open_blocking_count: N
local_assessment: "pass" | "blocked" | "error"
predecessor_assessment_ref: NULLREF
```

The assessor writes findings and the manifest into its isolated output leaf.
The trusted packager seals and inventories **every file** in that leaf. The
recomputed finding inventory must contain exactly `finding_count` finding
records and exactly the sorted `finding_refs`; missing, extra, swapped, or
unreferenced finding bytes refuse packaging. `pass` requires
`open_blocking_count=0`, all required checks present/pass, and complete prior
lineage. A reassessment references its predecessor and carries every prior
finding either unchanged or with a valid resolution; dropping one is invalid.

### 6.9 Section, boundary, comparison, and scope results

`section_evidence_bundle.v1` payload keys:

```text
program_ref: REF
contract_ref: REF
work_item_id: H
base_commit: G
builder_assignment_ref: REF
assessor_assignment_ref: REF
builder_context_ref: REF
assessor_context_ref: REF
builder_sandbox_attestation_ref: REF
assessor_sandbox_attestation_ref: REF
proposal_ref: REF (artifact_type="proposal")
diff_preview_ref: REF (artifact_type="diff_preview")
assessment_manifest_ref: REF
test_manifest_ref: REF (artifact_type="test_manifest")
test_result_refs: sorted array[REF] (artifact_type="test_result")
invariant_results: sorted nonempty array[CHECK_RESULT] by check_id
local_assessment: "pass" | "blocked" | "error"
resource_metrics: sorted array[METRIC] by metric_id
dependency_snapshot_ref: REF (artifact_type="read_inventory")
staleness_input_refs: sorted nonempty array[REF]
```

Its local assessment must equal the assessor manifest and cannot be supplied by
the builder or packager.

`boundary_impact_report.v1` payload keys:

```text
program_ref: REF
work_graph_ref: REF
section_bundle_refs: sorted nonempty array[REF]
final_scope_ref: REF
changed_section_ids: sorted array[S]
changed_interfaces: sorted array[INTERFACE_REF]
affected_contract_refs: sorted array[REF]
dependency_closure_ref: REF (artifact_type="read_inventory")
activated_check_results: sorted nonempty array[CHECK_RESULT]
conflict_evidence_refs: sorted array[REF]
unknown_classification_count: N
required_system_audit_scope_ids: sorted nonempty array[S]
```

Any conflict evidence or nonzero unknown count blocks publication.

`section_comparison_report.v1` payload keys:

```text
program_ref: REF
workload_identity_sha256: H
sequential_root_ref: REF
hierarchical_root_ref: REF
metric_results: sorted nonempty array[METRIC] by metric_id
seeded_defect_ids: sorted nonempty array[S]
sequential_detected_defect_ids: sorted array[S]
hierarchical_detected_defect_ids: sorted array[S]
escaped_defect_ids: sorted array[S]
limitations: sorted nonempty array[T]
conclusion: "improved" | "non_inferior" | "inconclusive" | "worse"
```

Unknown/unavailable metrics use `availability="unavailable"`, `value=null`,
and `evidence_ref=null`; they are never encoded as zero.

A comparison report is produced in a later comparison evidence root after both
input roots are sealed. Its `sequential_root_ref` and `hierarchical_root_ref`
are the only permitted external HSC-root references. Neither input root may
inventory the comparison report that references it.

`final_scope_manifest.v1` payload keys:

```text
program_ref: REF
work_graph_ref: REF
base_commit: G
predicted_changes: sorted nonempty array[PREDICTED_CHANGE] by path
actual_changes: sorted array[ACTUAL_CHANGE] by (path, kind)
section_bundle_refs: sorted nonempty array[REF]
assembler_binary_ref: REF (artifact_type="assembler_binary")
assembled_tree_sha256: H
```

Every actual change path must occur in exactly one predicted change and its kind
must be allowed. Every predicted `required=true` path must occur. No ownership
directory or glob can authorize an unpredicted child.

### 6.10 Complete root and ordinary request binding

`section_evidence_root.v1` payload keys:

```text
planned_request_id: R
program_ref: REF
parent_build_event_id: E
parent_build_event_hash: H
base_commit: G
work_graph_ref: REF
final_scope_ref: REF
record_inventory: sorted nonempty array by (schema_version, record_id) of {
  "schema_version": one value in §6.1 except section_evidence_root.v1,
  "record_id": H,
  "content_sha256": H,
  "repository_relpath": P
}
operation_log_ref: REF (artifact_type="operation_log")
record_count: N
```

The root enumerates **every** program, contract, context, content record,
assignment, sandbox profile/attestation, finding, assessment, evidence bundle,
boundary report, comparison report, work graph, and final scope record for the
source. The validator walks all references, requires one reachable acyclic
graph, rejects unreachable extras, requires
`record_count == len(record_inventory)`, and rejects member omission, addition,
reordering, cross-program reuse, or stale child reuse. The root does
not list itself, so there is no self-cycle.

The committed paths are fixed by v1:

```text
artifacts/section-council/<planned_request_id>/root.json
artifacts/section-council/<planned_request_id>/final-scope.json
```

Before calling the unchanged ordinary publisher, the HSC pre-publish wrapper
recomputes the root, final scope, actual Git diff, and clean candidate tree. It
requires one exact scope-list entry:

```text
HSC_V1 root_path=<P> root_id=<H> root_sha256=<H>
       scope_path=<P> scope_id=<H> scope_sha256=<H>
```

The entry is one line with single ASCII spaces, in the shown key order, and no
extra fields. The wrapper rejects its absence, duplication, malformed spacing,
or mismatch. Existing `publish_request` then hashes that exact scope string into
the ordinary `request_payload_hash` and pins it in `AUDIT_REQUESTED`. Thus the
current request schema and authority remain unchanged while the HSC path gains a
machine-readable, request-bound scope root. A caller bypassing the HSC wrapper
has no hierarchical evidence claim and cannot present local bundles as such.

After assembly, binding remains acyclic:

```text
BUILD_STARTED -> program -> contracts/work/assessments -> scope + evidence root
    -> final commit -> ordinary request hash -> Codex verdict -> integration
```

No speed, quality, completeness, or cost claim is valid without a verified root
and, where applicable, a verified comparison report.

## 7. Deterministic conflict and scheduling algorithm

### 7.1 Path normalization

HSC v1 has no path patterns or write globs. `P` is a POSIX-style relative path
whose UTF-8 bytes satisfy all of:

- total length 1..1024 bytes and at most 64 segments;
- `/` is the only separator;
- each segment matches `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`;
- no segment is `.`, `..`, `.git`, a Windows reserved device name
  (`CON`, `PRN`, `AUX`, `NUL`, `COM1`..`COM9`, `LPT1`..`LPT9`, case-insensitive),
  or ends in dot/space;
- the path is not absolute, drive-qualified, UNC, NUL-containing, or
  backslash-containing;
- NFC and case-fold keys are unique across every declared/read/actual path;
- every existing ancestor is a real directory, not a symlink, reparse point,
  submodule, mount transition, or special file.

The trusted host validator uses descriptor/handle-relative no-follow traversal
from an already validated repository-root handle. String prefix checks never
grant access. A not-yet-created output is valid only when every existing
ancestor passes that traversal and the exact file path appears in one
`PREDICTED_CHANGE`.

Write authority is the exact set of predicted file paths and permitted change
kinds. A directory name confers no authority over its children. Rename requires
both the exact `rename_source` and destination; delete and mode change are
explicit kinds. The actual diff is an exact sorted list of `ACTUAL_CHANGE`
objects and no actual path may be absent from the predicted list. A required
predicted path may not be absent. The final scope manifest independently
recomputes blobs and modes from Git, not worker claims.

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

Any path ambiguity, unpredicted generated path, rename-source collision,
case-fold/NFC collision, or unclassified shared fixture means conflict. The
scheduler fails closed and serializes or escalates; it never asks workers to
avoid overlap voluntarily.

### 7.3 Dispatch order

Eligible work is sorted by:

```text
(dependency_depth, priority, section_id, work_item_id)
```

The sorted order determines admission and evidence identity. Worker completion
order does not. A parallel run and a sequential run over the same frozen graph
must produce the same admitted work set and equivalent content evidence.

### 7.4 Isolation

Git worktrees are explicitly **not** a security boundary: they share reachable
Git metadata and a same-user worker can address another checkout. A writable
HSC worker instead uses `linux-bwrap-v1`:

1. The trusted host exports the exact base commit into a content-inventoried
   source snapshot with no `.git` directory.
2. Bubblewrap creates new user, PID, and network namespaces with no
   capabilities and `no_new_privileges`; a pinned seccomp profile applies.
3. The source snapshot and required tool/runtime image are mounted read-only.
4. The integration checkout, its `.git`/common Git metadata, the live Council
   root, root-owned anchors, other worker leaves, canonical evidence, hidden
   suites, and arbitrary host user paths are absent from the namespace; if a
   runtime dependency forces visibility, it is read-only and named in the
   sandbox profile.
5. Exactly one private output leaf is writable. `/tmp` is a bounded private
   tmpfs. No host environment variable or inherited descriptor exposes another
   writable path. Network is unshared.
6. The worker emits a reviewed patch/report plus its closed output inventory;
   it never edits a Git checkout.
7. A separate assessor sandbox receives the same read-only source plus the
   sealed proposal and deterministic evidence, and has a different output
   leaf unavailable to the builder.

If `bwrap`, mount namespaces, no-follow source export, seccomp, or a required
read-only/absent-root assertion is unavailable, writable hierarchical execution
is **ineligible**. The task may use the existing sequential Council, but it may
not claim section isolation. Windows or macOS require a future separately
audited equivalent profile; v1 does not silently emulate one.

The trusted deterministic assembler is the only HSC component permitted to
write the integration checkout. It runs only after a complete assessor pass,
revalidates the program/root/scope, parses the proposal without shell
evaluation, refuses binary/symlink/submodule/special-file patches, validates
every old blob/mode against the frozen base, and applies exact changes in sorted
`work_item_id` order using handle-relative no-follow operations. Before and
after each application it verifies protected integration and common-Git
metadata inventories; only the declared candidate paths may differ. Any drift,
external modification, semantic/text conflict, or unexpected Git metadata
change aborts without choosing a winner.

The assembled bytes are re-read, hashed into `ACTUAL_CHANGE`, compared with the
final scope, committed by the normal parent builder, and subjected to the full
existing top-level audit. Read-only/deterministic workers may share one source
snapshot, but their writable output leaves and assignments remain distinct.

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
- `built` requires a sealed proposal/output inventory from the confined builder
  sandbox; no integration-tree write has occurred.
- `checked` requires every deterministic required check and an exact predicted
  change/diff-preview pass.
- `passed` requires structurally distinct principal assignments, a complete
  sealed assessor manifest, and no blocking findings.
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
- the final scope manifest exactly matches the actual diff;
- the request carries the one exact HSC root/scope binding string from §6.10 and
  names the relevant global invariants in its remaining prose scope entries.

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
- scheduler assignment, principal credential/launcher receipt, sandbox profile,
  or protected-host attestation;
- assessor manifest inventory or any finding member;
- upstream blocking finding or resolution;
- boundary-impact closure;
- final scope or evidence-root membership;
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
- Retry creates a new scheduler assignment with a new session nonce, launcher
  receipt, and incremented attempt while retaining the work-item identity and
  recording the failed predecessor assessment/output inventory.
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
   request fixture; emit the exact predicted proposal files in its private
   `/out` leaf.
2. **Test evidence index** — validate and inventory an isolated, frozen test
   manifest fixture; emit a disjoint exact predicted proposal in its private
   `/out` leaf.

A third boundary work item consumes both verified indexes and produces only a
`boundary_impact_report.v1`. It cannot run until both dependencies pass. The
same workload runs once sequentially and once with two parallel eligible
workers. Outputs must be content-equivalent and independently reassessed.
Each fixture uses a scheduler-assigned deterministic builder executable and a
different allowlisted deterministic assessor executable, with different binary
digests, credentials/launcher receipts, sessions, contexts, and sealed output
leaves. This proves structural separation and complete evidence ingestion; it
does not claim model-diverse adversarial judgment.

### 14.2 Pilot acceptance

The pilot proves only:

- contract and evidence identities;
- scope enforcement;
- deterministic conflict refusal;
- scheduler-owned distinct builder/assessor principal assignments and complete
  assessor finding manifests;
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

- every §6 record schema, nested type, exact key set, domain-separated self-id,
  typed reference walk, and complete evidence-root validation;
- domain-separated hashing;
- the closed exact-path/change algebra, final-scope validator, and fixed HSC
  ordinary-request binding parser;
- deterministic conflict classification;
- dependency and staleness calculation;
- no worker launch and no Council mutation.

Route as a normal source request and independently audit the exact commit.

### Slice HSC-B — single-section executor pilot

Add the pinned `linux-bwrap-v1` launcher, read-only no-Git source export,
private proposal output, protected-host integrity attestation, trusted patch
assembler, scheduler-minted principal assignments, sealed assessor output,
complete finding-manifest ingestion, real-diff enforcement, evidence-root
packaging, and crash-safe derived journals. Run one section without
parallelism. If the OS profile cannot be proven, this slice fails closed rather
than falling back to an unconfined hierarchical worker.

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
10. builder/assessor same principal with different opaque ids refused;
11. builder-minted or swapped assessor assignment/launcher receipt refused;
12. every §6.1 record rejects missing/extra keys, self-id mismatch, wrong
    domain/version, parent substitution, cross-program replay, member
    omission/addition/reordering, unreachable extras, and stale-child reuse;
13. root record count/inventory mismatch or final request root/scope binding
    mismatch refused.

### Scope and conflict

14. hostile worker relative, absolute, symlink/reparse, mount, and shared-Git
    writes fail inside the OS sandbox; integration/common-Git/protected-root
    digests remain unchanged;
15. only an assembler-authorized exact proposal can alter the candidate;
16. actual diff contains a path/kind absent from exact predicted changes,
    including an unpredicted child inside a declared sibling directory;
17. two sections overlap writes or rename sources/destinations;
18. one section writes another's mutable read;
19. immutable inventory-pinned read permits safe sharing;
20. ambiguous case/NFC/rename/symlink/reparse/native identity fails closed;
21. rename, delete, and mode changes without exact old/new bindings refuse;
22. hidden cross-section impact not declared by builder is detected from the
    real final diff;
23. uncertain conflict classification blocks dispatch;
24. parallel and sequential admission sets are identical;
25. worker completion order does not change assembled content.

### Assessment and authority

26. local pass presented as integration approval is refused;
27. builder-authored assessment or builder-writable assessor root is refused;
28. swapped assessor output or manifest/input/proposal mismatch is refused;
29. missing, extra, unreferenced, or reordered finding files are refused;
30. omitted open blocker or false finding count/open count is refused;
31. repair assessment that drops a predecessor finding or reassessment link is
    refused;
32. implementation changes after assessment make it stale;
33. missing required evidence blocks pass;
34. unresolved blocking finding blocks pass;
35. finding survives repair and links to its resolution/reassessment;
36. top-level publication cannot omit a required section bundle or root member;
37. ordinary Codex audit remains required;
38. ordinary `CHANGE_INTEGRATED` remains the only integration event;
39. sequential mode behavior is unchanged.

### Dependency and recovery

40. dependency version/interface/policy/test change invalidates only affected
    work;
41. shared-dependency blocker marks dependents blocked or stale;
42. interrupted work resumes without duplicate outputs;
43. duplicate dispatch has one winner;
44. expired/wrong lease token cannot overwrite or remove another worker;
45. partial bundle cannot be interpreted as pass;
46. STOP prevents new dispatch and assembly;
47. malformed journal fails closed with preserved diagnostics;
48. retry links the failed assignment/assessment without reusing either;
49. assembler detects post-assessment drift and any protected-host digest
    change.

### Measurement and negative controls

50. sequential/hierarchical workload identities are equivalent;
51. unavailable token/cost measures are reported unavailable, not zero;
52. wall-clock time is telemetry, never identity;
53. artificial delay fixture demonstrates real overlap without brittle
    production wall-clock assertions;
54. seeded defect is detected in both modes;
55. seeded boundary defect is not cleared by two local passes;
56. no improvement claim emitted when confidence/coverage is insufficient;
57. full existing suite remains green.

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
| builder selects/impersonates assessor | scheduler-owned assignments bind distinct allowlisted principals, credentials, launcher receipts, sessions, contexts, and sealed output roots |
| local pass becomes global approval | local enum is not `GO`; no canonical authority event; final existing audit remains mandatory |
| scope creep | exact predicted changes, exact final scope manifest, root-bound request entry, and independently recomputed real diff |
| overlapping/ambient writes | kernel mount sandbox exposes no host writable path except private output; workers emit proposals; only the deterministic assembler writes the integration tree |
| incompatible section identities | exact interface/dependency digests and boundary closure |
| summary laundering | integration consumes raw content-addressed evidence, not builder prose |
| assessor finding suppression | assessor-owned sealed output inventory; manifest count/root must equal every finding file; predecessor findings cannot disappear |
| record/member substitution | exact three-key schemas, unique domains, typed references, and one acyclic complete evidence root bound into the ordinary request |
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
