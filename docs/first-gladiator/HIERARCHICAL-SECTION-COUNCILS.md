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
>
> **Revision 3:** addresses the four reproduced findings in `AUDIT_BLOCKED`
> `001504-4c3e64c9`: an explicitly topological bootstrap and post-commit
> publication envelope; exact per-kind change semantics; descriptor and native
> alias closure; and typed scheduler-owned principal, launch, and finding-root
> evidence. The filter-safe reroute did not change the source or acceptance
> criteria.
>
> **Revision 4:** addresses the four reproduced findings in `AUDIT_BLOCKED`
> against commit `6a23a58d4bad`: canonical reference-derived construction
> ordinals replace contradictory macro-stage peers; a closed native-root plan
> makes every protected namespace and phase exhaustive; typed per-dispatch
> journal exports bind authorization, assignment, receipt, and ready-barrier
> release; and frozen assessment/check declarations map one-to-one into the
> packaged assessment manifest.
>
> **Revision 5:** follows operational watcher failures `001514-e5b3291f` and
> `001515-cb775026` (canceled without verdict by `001516-03252a46`). The two
> independent read-only audit logs reproduced two additional native-inventory
> gaps: repository path `P` could not encode mandatory dot-prefixed native
> descendants, and native locator/filesystem/file identities lacked one exact
> derivation. Revision 5 adds a lossless native-byte path/view contract and a
> single Linux handle/stat identity algebra reused by roots, entries, and the
> protected scheduler journal. No failed audit log is treated as approval.

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
and registry authority identity, earlier scheduler launch authorization,
session, attempt, exact context, sandbox profile, workspace, and permitted
output leaf. The trusted launcher later emits the assignment-bound receipt. A
worker cannot mint, select, or edit any of those records.

Builder and assessor assignments must resolve through the event-pinned registry
to different principal ids, authority-control ids/keys, credentials,
authorizations, workspaces, and sessions. Unequal opaque execution ids alone
are explicitly insufficient. In the first model-assisted
pilot the builder principal is the existing Claude builder context and the
assessor principal is a separately launched Codex assessor context. A
deterministic assessor may replace the model only where the assessment profile
contains no judgment; that result is described as deterministic validation,
not independent adversarial review.

The assessor writes one sealed assessment declaration, findings, checks, and
evidence into an output root unavailable to the builder. The trusted packager
freezes and inventories the whole root, then deterministically constructs
`section_assessment_manifest.v1` outside it from every file and the exact
finding-inventory formula. It cannot select favorable findings. Model separation is helpful
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
O       lowercase Git object id [0-9a-f]{40}
E       Council event id [0-9]{6}-[0-9a-f]{8}
R       existing Council request slug
S       [a-z0-9][a-z0-9-]{1,63}
P       normalized repository-relative path from §7.1
N       JSON integer, bool excluded, 0 <= N <= declared bound
B       JSON boolean
T       bounded nonempty UTF-8 string
X       lowercase even-length hexadecimal encoding of bounded nonempty bytes
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
  "kind": "add" | "delete" | "modify" | "mode" | "rename",
  "rename_source": P | null,
  "blob_before": H | null,
  "mode_before": "100644" | "100755" | null,
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

FD_RULE = {
  "fd": N,
  "role": "stdin" | "stdout" | "stderr",
  "access": "read" | "write",
  "target_kind": "null" | "pipe"
}

NATIVE_REL_PATH = {
  "segments_hex": nonempty array[X]
}

NATIVE_LOCATOR = {
  "platform": exactly "linux-bwrap-v1",
  "anchor_name": S,
  "anchor_id": H,
  "segments_hex": array[X],
  "resolution": exactly "openat2-beneath-no-magiclinks-no-symlinks-v1"
}

NATIVE_ID_OBSERVATION = {
  "profile": exactly "linux-native-id-v1",
  "statx_mount_id": N,
  "device_major": N,
  "device_minor": N,
  "statfs_fsid_word0": N,
  "statfs_fsid_word1": N,
  "file_handle_type": N,
  "file_handle_bytes_hex": X,
  "inode": N,
  "file_type": "regular" | "directory",
  "link_count": N,
  "native_mode": N
}

NATIVE_ENTRY = {
  "path": NATIVE_REL_PATH,
  "native_identity": NATIVE_ID_OBSERVATION,
  "filesystem_id": H,
  "file_id": H,
  "content_sha256": H | null,
  "kind": "regular" | "directory"
}

NATIVE_ROOT_SPEC = {
  "root_id": H,
  "root_kind": "candidate" | "integration-checkout" | "common-git" |
               "council-root" | "owner-anchors" | "other-worker-leaves" |
               "canonical-evidence" | "hidden-suites" | "runtime-readonly" |
               "builder-output" | "assessor-output",
  "view_kind": "full-native-tree-v1" |
               "checkout-excluding-delegated-dotgit-v1",
  "namespace_id": H,
  "locator": NATIVE_LOCATOR,
  "locator_sha256": H,
  "native_identity": NATIVE_ID_OBSERVATION,
  "filesystem_id": H,
  "file_id": H,
  "workspace_id": H | null,
  "delegated_control_root_id": H | null,
  "delegated_control_identity": NATIVE_ID_OBSERVATION | null
}

NATIVE_OBSERVATION_REQUIREMENT = {
  "observation_id": H,
  "root_id": H,
  "phase": "pre-dispatch" | "post-worker" |
           "pre-assembly" | "post-assembly",
  "scope": "builder-dispatch" | "assessor-dispatch" | "assembly",
  "work_item_id": H | null,
  "role": "builder" | "assessor" | null,
  "attempt": N | null,
  "workspace_id": H | null
}

CHECK_DECLARATION = {
  "check_id": S,
  "status": "pass" | "fail" | "error",
  "evidence_output_relpath": P
}

JOURNAL_ENTRY = {
  "ordinal": N,
  "sequence": N,
  "entry_kind": "authorization" | "assignment" | "receipt",
  "record_ref": REF,
  "entry_sha256": H,
  "writer_role": "scheduler" | "launcher",
  "writer_principal_id": S,
  "writer_control_id": H
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

`NATIVE_REL_PATH` is not `P` and grants no repository write authority. Each
`segments_hex` element decodes to 1..255 native bytes, contains neither NUL nor
`/`, and is not byte-equal to `.` or `..`; 1..256 segments and at most 4096
decoded bytes including separators are permitted. Dot-prefixed names, including
`.gitignore` and `.git`, are representable. Lowercase hex is the sole encoding,
so invalid UTF-8 native names remain lossless. Paths sort by the lexicographic
tuple of decoded segment bytes; duplicate decoded tuples refuse. A locator uses
the same segment encoding, but may use an empty array for its enrolled anchor.
The trusted root-owned anchor registry binds `anchor_id`; no worker chooses it.

The registry row for an anchor is exactly its bounded `anchor_name`, trusted
host configuration path, `NATIVE_ID_OBSERVATION`, `filesystem_id`, and
`file_id`. The absolute configuration path is protected operational
configuration, not worker input and not part of a locator. The host opens that
configured anchor no-follow, recomputes the observation and ids, then requires:

```text
anchor_id = domain_hash(
  "council:native-anchor:v1",
  {"anchor_name": S, "file_id": H, "filesystem_id": H,
   "native_identity": canonical NATIVE_ID_OBSERVATION})
```

`NATIVE_LOCATOR.anchor_name` and `anchor_id` must match exactly one enrolled
row. Duplicate names, ids, or native objects refuse. This makes locator
reconstruction independent of an arbitrary caller-supplied `H` while keeping
the protected absolute host path out of worker-visible records.

The only v1 native identity encoder is `linux-native-id-v1`. The trusted host
opens each locator/descendant with `openat2` from the enrolled anchor using
`O_PATH|O_NOFOLLOW` and exactly
`RESOLVE_BENEATH|RESOLVE_NO_MAGICLINKS|RESOLVE_NO_SYMLINKS`. It enumerates raw
names no-follow, captures `statx` mount id plus `fstat` device major/minor,
inode, type, link count, and the unsigned Linux `st_mode` value, captures the
two `f_fsid` words from `fstatfs` as unsigned 32-bit integers in declaration
order, and captures a nonempty persistent file-handle type/bytes with
`name_to_handle_at`. Numeric values are nonnegative JSON integers; handle bytes
are 1..256 bytes encoded by `X`. Mount id, inode, and link count are bounded by
`2^64-1`; device components, fsid words, handle type, and native mode are
bounded by `2^32-1`. The host repeats the
handle/stat observation after enumeration; every identity field must be equal.
Unsupported `openat2`, `statx` mount ids, persistent file handles, stable
re-observation, or no-follow traversal makes v1 ineligible rather than invoking
a fallback encoder.

The derivations are exact:

```text
filesystem_id = domain_hash(
  "council:linux-filesystem-id:v1",
  {"device_major": N, "device_minor": N,
   "statfs_fsid_word0": N, "statfs_fsid_word1": N})

file_id = domain_hash(
  "council:linux-file-id:v1",
  {"file_handle_bytes_hex": X, "file_handle_type": N,
   "file_type": "regular" | "directory", "filesystem_id": H,
   "inode": N})

locator_sha256 = domain_hash(
  "council:native-root-locator:v1", canonical NATIVE_LOCATOR)

namespace_id = domain_hash(
  "council:native-namespace:v1",
  {"locator_sha256": H, "program_ref": REF, "root_kind": S,
   "view_kind": S, "workspace_id": H | null})

root_id = domain_hash(
  "council:native-root:v1",
  {"program_ref": REF,
   "root_spec": canonical NATIVE_ROOT_SPEC with root_id omitted})
```

For every root and entry, the validator recomputes `filesystem_id` and
`file_id` from the embedded observation and requires type/link/mode/content
relations to match the observed handle. It recomputes locator, namespace, and
root ids likewise. An arbitrary caller-supplied H never substitutes for native
observation. The same native object observed through two namespaces therefore
derives the same `(filesystem_id, file_id)` and is detectable; distinct native
objects with equal paths or bytes remain distinct. `statx_mount_id` remains a
re-observed locator/mount fact but is intentionally excluded from
`filesystem_id`: two bind-mount views of the same filesystem may have different
mount ids and still must collide on the same native file identity.

`view_kind` has a closed meaning. `full-native-tree-v1` requires both delegated
control fields to be null and inventories every descendant, including every
dot-prefixed name. `checkout-excluding-delegated-dotgit-v1` is legal only for
an `integration-checkout` root. Its direct child with decoded segment `.git`
must be a directory; `delegated_control_root_id` must resolve to the program's
one `common-git` root; that root's locator must equal the checkout locator plus
the single `.git` segment; and `delegated_control_identity` must byte-equal the
common-Git root observation. The checkout inventory excludes exactly that
direct child and its descendants, while the referenced common-Git root uses
`full-native-tree-v1` and inventories them exhaustively. The copied delegated
identity is relation evidence, not a second inventory member, and is the sole
permitted repeated observation. A `.git` regular indirection file, missing or
additional exclusion, locator mismatch, identity mismatch, overlapping entry,
or unreferenced delegated root makes Linux v1 ineligible. The common-Git root
is constructed before the dependent checkout root in the canonical reference
order; arrays are sorted only after both ids exist. Candidate/export roots use
the full-tree view and contain no delegated Git control tree; a decoded direct
child `.git` in such a root refuses rather than being silently excluded.

`PREDICTED_CHANGE` is one exact operation, not a menu. The base commit supplies
its before fields. `ACTUAL_CHANGE` has the following exhaustive truth table;
all unlisted forms are invalid:

| kind | `rename_source` | `blob_before` | `blob_after` | `mode_before` | `mode_after` | additional rule |
| --- | --- | --- | --- | --- | --- | --- |
| `add` | null | null | H | null | mode | destination absent at base |
| `delete` | null | H | null | mode | null | source present at base |
| `modify` | null | H | H | mode | same mode | before and after blobs differ |
| `mode` | null | H | same H | mode | mode | modes differ |
| `rename` | exact P | H | same H | mode | same mode | source present, destination absent; content/mode edits forbidden |

For `PREDICTED_CHANGE`, `add` has null before fields; every other kind has a
non-null base blob/mode; only `rename` has a non-null `rename_source`.
`modify` and `mode` predict the base path, blob, and mode exactly. `rename`
predicts the exact source identity at `rename_source` and the absent destination
at `path`. A content or mode change combined with a rename is unsupported in v1;
the program must express an exact delete+add pair or defer the second change to
a later separately audited program. Within a frozen graph, destination paths
and rename sources are each unique, a path cannot be both source and destination,
and no no-op form is valid. Arrays of changes sort by
`(path, kind, rename_source-or-empty)`.

The canonical real-diff extractor never uses Git similarity heuristics. It
walks the exact base and candidate trees, first validates each predicted pure
rename in sorted order (unique source/destination, source removed, destination
new, identical blob and mode), removes those paired paths, and then classifies
all remaining paths as add/delete/modify/mode from exact tree entries.
Unpredicted equal-content delete/add pairs remain two changes and are refused;
host Git configuration and rename detection cannot change the result.

Symlinks, submodules, special files, directories as write grants, arbitrary
Git modes, and unbounded maps are not representable in v1.

### 6.1 Record registry

| `schema_version` | ID field | Domain |
| --- | --- | --- |
| `section_program.v1` | `section_program_id` | `council:section-program:v1` |
| `section_bootstrap_content.v1` | `section_bootstrap_content_id` | `council:section-bootstrap-content:v1` |
| `section_principal_registry.v1` | `section_principal_registry_id` | `council:section-principal-registry:v1` |
| `section_contract.v1` | `section_contract_id` | `council:section-contract:v1` |
| `section_work_graph.v1` | `section_work_graph_id` | `council:section-work-graph:v1` |
| `section_context_bundle.v1` | `section_context_bundle_id` | `council:section-context-bundle:v1` |
| `section_content_record.v1` | `section_content_record_id` | `council:section-content-record:v1` |
| `section_assignment.v1` | `section_assignment_id` | `council:section-assignment:v1` |
| `section_launcher_authorization.v1` | `section_launcher_authorization_id` | `council:section-launcher-authorization:v1` |
| `section_launcher_receipt.v1` | `section_launcher_receipt_id` | `council:section-launcher-receipt:v1` |
| `section_scheduler_journal_manifest.v1` | `section_scheduler_journal_manifest_id` | `council:section-scheduler-journal-manifest:v1` |
| `worker_sandbox_profile.v1` | `worker_sandbox_profile_id` | `council:worker-sandbox-profile:v1` |
| `worker_sandbox_attestation.v1` | `worker_sandbox_attestation_id` | `council:worker-sandbox-attestation:v1` |
| `section_native_inventory_plan.v1` | `section_native_inventory_plan_id` | `council:section-native-inventory-plan:v1` |
| `section_native_inventory.v1` | `section_native_inventory_id` | `council:section-native-inventory:v1` |
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

### 6.2 Bootstrap records and `section_program.v1` — pre-build root

Two record types exist before the program and therefore **must not** contain a
`program_ref`.

`section_bootstrap_content.v1` payload keys:

```text
planned_request_id: R
artifact_type: "schema_profile" | "read_inventory"
storage_relpath: P
media_type: "application/json"
byte_length: N
blob_sha256: H
```

Its path begins exactly
`artifacts/section-council/<planned_request_id>/bootstrap/`. The bytes are
canonical closed JSON for the named type. They are stored and hashed before the
program exists, opened no-follow, and later inventoried by the evidence root.

`section_principal_registry.v1` payload keys:

```text
planned_request_id: R
repository: T
base_commit: G
enrollment_registry_path: P
enrollment_registry_git_blob: O
enrollment_registry_version: N
enrollment_registry_digest: H
scheduler_authority_id: H
scheduler_writer_principal_id: S
scheduler_writer_control_id: H
launcher_writer_principal_id: S
launcher_writer_control_id: H
principals: sorted nonempty array by principal_id of {
  "principal_id": S,
  "allowed_role": "builder" | "assessor",
  "authority_control_id": H,
  "authority_control_key_digest": H,
  "principal_credential_digest": H,
  "launcher_profile_id": S,
  "enrollment_evidence_sha256": H
}
```

The trusted HSC wrapper derives this closed projection from the exact
owner-reviewed registry file and Git blob in `base_commit`, then cross-checks
its scheduler authority and its scheduler/launcher writer principals and
control identities against the OS-protected scheduler configuration before
`BUILD_STARTED`; workers cannot write either source. Changing the enrollment
registry requires an ordinary audited source change. `principal_id`,
`authority_control_id`, control-key
digest, and credential digest are each globally unique within the registry.
Builder and assessor entries must have different authority-control identities
and different control-key digests, not merely different labels. A duplicate or
alias detected by the enrollment authority makes hierarchical dispatch
ineligible. The exact registry record is bound by the program and therefore by
the existing `BUILD_STARTED` event. This explicit root-owned enrollment is the
v1 trust boundary; v1 makes no claim that arbitrary self-declared accounts are
independent principals.
The scheduler and launcher writer principals are distinct from each other and
from every worker principal/control identity. Only those protected writers may
produce the journal entry kinds assigned to them in §6.7.

`section_program.v1` payload keys:

```text
planned_request_id: R
repository: T
base_commit: G
execution_mode: "sequential" | "hierarchical"
section_declarations: sorted nonempty array of {
  "section_id": S,
  "predicted_changes": sorted nonempty array[PREDICTED_CHANGE]
      by (path, kind, rename_source-or-empty),
  "read_inventory_refs": sorted array[REF]
      resolving only to section_bootstrap_content.v1/read_inventory,
  "dependency_section_ids": sorted array[S],
  "budget": BUDGET,
  "assessment_profile_id": S
}
schema_profile_refs: sorted nonempty array[REF]
  resolving only to section_bootstrap_content.v1/schema_profile
principal_registry_ref: REF resolving only to section_principal_registry.v1
system_artifact_predictions: sorted nonempty array[PREDICTED_CHANGE]
  by (path, kind, rename_source-or-empty)
root_policy_version: N
```

Section declarations reject duplicate paths across sections and dependency
cycles. The program contains no contract ids and no self-id. Bootstrap content
and the principal registry contain no program reference, so construction is
strictly raw bootstrap bytes -> bootstrap/registry records -> program. Every
record created after the program must bind `program_ref`; no nullable
back-reference is permitted.

The trusted wrapper computes `system_artifact_predictions` before storing the
program from a closed versioned layout and bounded slot counts in the schema and
assessment profiles. These are exact `add` paths for bootstrap records, program,
contracts, graph, fixed per-section/per-role/per-attempt record slots, bounded
finding/evidence slots, and other HSC artifacts. Worker `/out` names never become
repository authority: the packager maps accepted bytes only into a predeclared
unused slot. Unused optional slots are absent; an exhausted slot budget blocks
and requires a new program. The two final envelope paths are the sole exclusions
and are governed by §6.10. Thus no variable record id or worker filename creates
an unpredicted repository path.

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
predicted_changes: sorted nonempty array[PREDICTED_CHANGE]
    by (path, kind, rename_source-or-empty)
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
  "predicted_changes": sorted array[PREDICTED_CHANGE]
      by (path, kind, rename_source-or-empty),
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
  "read_inventory" | "assessment_profile" | "assessment_declaration" |
  "check_declaration" | "finding_declaration" |
  "source_snapshot" | "proposal" | "diff_preview" |
  "test_manifest" | "test_result" | "check_evidence" |
  "finding_evidence" | "reproduction" | "resolution" |
  "operation_log" | "conflict_evidence" | "assembler_binary" |
  "scheduler_failure_evidence"
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
`schema_profile_refs` resolves only to the bootstrap schema record,
`proposal_ref` only to a content record of type `proposal`, and
`test_result_refs` only to `test_result`. Type substitution is invalid.

Two assessor-owned artifact types have additional closed canonical-JSON byte
schemas; they are not opaque just because a content record wraps them.

Every `check_declaration` blob is exactly one `CHECK_DECLARATION`. Its evidence
path is unique in the assessor leaf and resolves to exactly one wrapped
`check_evidence` file.

Every `assessment_declaration` blob is canonical JSON with exactly:

```text
{
  "schema_version": "section-assessment-declaration.v1",
  "program_ref": REF,
  "contract_ref": REF,
  "work_item_id": H,
  "assessor_assignment_ref": REF,
  "assessor_context_ref": REF,
  "proposal_ref": REF,
  "check_declaration_output_relpaths": sorted nonempty array[P],
  "finding_declaration_output_relpaths": sorted array[P],
  "predecessor_assessment_ref": NULLREF,
  "declared_disposition": "pass" | "blocked" | "error",
  "error_reason": T | null
}
```

Every listed output path is leaf-relative, unique across both arrays, and
present in the frozen exhaustive output inventory with the named artifact
type. `error_reason` is non-null exactly for `error`. The declared disposition
is valid exactly when the deterministic rule in §6.8 derives the same value.
These bytes are assessor output and are immutable before any reference-bearing
record is packaged.
Every embedded `REF`/`NULLREF` in a closed declaration is type-checked against
the same root and contributes the same target-before-source dependency edge as
a record-payload reference. Wrapping bytes in a content record never hides a
cycle, cross-program substitution, or stale predecessor.

### 6.7 Assignments and structural principal separation

The trusted scheduler and launcher write three exact journaled records per
dispatch. The per-program journal lives in an OS-protected directory that is
absent from every worker namespace, is opened no-follow, and accepts entries
with create-exclusive semantics. Its owner/mode, stable root identity,
contiguous sequence, and bytes are verified before release and exported as the
closed typed `section_scheduler_journal_manifest.v1` below. A generic opaque
content blob cannot stand in for this manifest. Any unavailable ownership
check, sequence gap, writer mismatch, replacement, or digest mismatch makes
dispatch ineligible.

`section_launcher_authorization.v1` payload keys:

```text
program_ref: REF
principal_registry_ref: REF
scheduler_authority_id: H
scheduler_journal_sequence: N
scheduler_journal_entry_sha256: H
contract_ref: REF
work_item_id: H
role: "builder" | "assessor"
principal_id: S
authority_control_id: H
principal_credential_digest: H
launcher_executable_sha256: H
session_nonce: H
attempt: N
context_ref: REF
sandbox_profile_ref: REF
workspace_id: H
output_leaf: S
```

`scheduler_journal_entry_sha256 = domain_hash(
"council:section-launch-authorization-entry:v1", canonical payload with only
that field omitted)`. Every identity must equal its principal-registry entry.

`section_launcher_receipt.v1` payload keys:

```text
program_ref: REF
authorization_ref: REF
assignment_ref: REF
scheduler_authority_id: H
scheduler_journal_sequence: N
scheduler_journal_entry_sha256: H
role: "builder" | "assessor"
principal_id: S
authority_control_id: H
principal_credential_digest: H
launcher_executable_sha256: H
session_nonce: H
attempt: N
context_ref: REF
sandbox_profile_ref: REF
workspace_id: H
output_leaf: S
barrier_status: "ready" | "refused"
```

Its entry hash uses domain
`council:section-launch-receipt-entry:v1` and omits only its own entry-hash
field. It is written by the trusted launcher after the child is confined and
paused at the pre-worker barrier, never by a worker. Every repeated field must
equal the authorization and assignment. A receipt references the already
created assignment; an assignment references only the earlier authorization,
so this sequence is acyclic.

`section_assignment.v1` payload keys:

```text
program_ref: REF
contract_ref: REF
work_item_id: H
role: "builder" | "assessor"
principal_registry_ref: REF
principal_id: S
authority_control_id: H
principal_credential_digest: H
scheduler_authority_id: H
scheduler_journal_sequence: N
scheduler_journal_entry_sha256: H
launcher_authorization_ref: REF
session_nonce: H
attempt: N
context_ref: REF
sandbox_profile_ref: REF
workspace_id: H
output_leaf: S
```

The parent scheduler writes assignments into its protected orchestration root
after the authorization and before dispatch. Worker sandboxes receive them
read-only. Registry, role, principal, authority-control identity, credential,
session, attempt, context, sandbox, workspace, and output must match the
authorization exactly. For one section, builder and assessor resolve through
the registry to distinct principal ids, authority-control ids, control-key
digests, credentials, authorization records, workspaces, output leaves, and
sessions. The builder cannot supply or write any assessor field or journal
entry. Unequal opaque values without two distinct registry authorities do not
satisfy this gate.

The assignment entry hash uses domain
`council:section-assignment-entry:v1` and omits only its own entry-hash field.
Its scheduler authority matches the authorization and protected registry.

`section_scheduler_journal_manifest.v1` is the direct typed export of one
completed authorization/assignment/receipt dispatch triple. Payload keys:

```text
program_ref: REF
principal_registry_ref: REF
scheduler_authority_id: H
journal_root_id: H
journal_root_locator: NATIVE_LOCATOR
journal_root_locator_sha256: H
journal_root_native_identity: NATIVE_ID_OBSERVATION
journal_root_filesystem_id: H
journal_root_file_id: H
journal_owner_principal_id: S
journal_owner_control_id: H
journal_mode: exactly "0700"
predecessor_journal_manifest_ref: NULLREF
first_sequence: N
last_sequence: N
entries: exactly ordered array[JOURNAL_ENTRY] of length 3
```

Entry ordinal/kind/writer pairs are exactly
`(0, authorization, scheduler)`, `(1, assignment, scheduler)`, and
`(2, receipt, launcher)`. Sequences are `first_sequence + ordinal` and
`last_sequence = first_sequence + 2`. The first manifest has null predecessor
and `first_sequence=0`; each later manifest references the immediately prior
manifest and starts at `predecessor.last_sequence + 1`. The scheduler entries'
writer identity equals the registry's scheduler writer; the receipt entry's
writer identity equals its launcher writer; principal and control id must both
match the applicable registry fields. Each entry REF has the required
record type, its `sequence` equals that record's
`scheduler_journal_sequence`, and its `entry_sha256` equals that record's
`scheduler_journal_entry_sha256` under the record-specific domain.

All three records describe the same program, work item, role, principal,
session, attempt, context, sandbox, workspace, and output leaf. The
authorization references no assignment; the assignment references that
authorization; the receipt references both. The manifest is constructed only
after the receipt and may therefore reference all three without a cycle.

At evidence-root validation time the journal manifests must form one unbroken,
unforked chain. Every authorization, assignment, and receipt reachable in the
root occurs exactly once in the corresponding ordinal of exactly one manifest;
there are no extra manifest entries or dispatch records. Journal root identity,
mode, and scheduler authority are identical throughout the chain; owner
principal/control equal the registry's protected scheduler writer. This
root-time equality is the membership proof; self-computable entry hashes alone
never satisfy it.
The journal locator digest and filesystem/file ids are recomputed by the exact
native algebra above. Its sole id preimage is:

```text
journal_root_id = domain_hash(
  "council:scheduler-journal-root:v1",
  {"journal_mode": exactly "0700", "journal_owner_control_id": H,
   "journal_owner_principal_id": S, "journal_root_file_id": H,
   "journal_root_filesystem_id": H, "journal_root_locator_sha256": H,
   "principal_registry_ref": REF, "program_ref": REF})
```

The journal anchor is an OS-protected enrolled anchor distinct from every
inventory root/entry; `journal_root_locator`, its digest, its embedded native
observation, and both derived ids must reconstruct from that anchor before any
membership check. Equality, a caller-selected H, an alternate encoder, or
unavailable stable observation refuses.
`journal_mode` is the JSON string literal `"0700"` in both the manifest and the
id preimage; no numeric or alternate text encoding is legal. The journal root
observation must have `file_type="directory"`, and
`journal_root_native_identity.native_mode & 4095` must equal decimal `448`
(permission bits 0700). Type bits remain in the observed unsigned
`native_mode`; this mask relation is the sole conversion from the canonical
manifest string to native permission bits.

`worker_sandbox_profile.v1` payload keys:

```text
program_ref: REF
platform: "linux-bwrap-v1"
launcher_binary_sha256: H
argv_template_sha256: H
native_inventory_plan_ref: REF
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
fd_policy: "close-all-except-stdio-v1"
permitted_fds: exactly sorted array[FD_RULE] containing
  {fd:0, role:"stdin", access:"read", target_kind:"null"},
  {fd:1, role:"stdout", access:"write", target_kind:"pipe"},
  {fd:2, role:"stderr", access:"write", target_kind:"pipe"}
```

The trusted launcher maps fd 0 to a read-only null device and fd 1/2 to bounded
one-way logging pipes, applies close-on-exec/`close_range` to every fd >= 3,
and holds the child at a barrier while a trusted parent enumerates the child's
descriptor table. If descriptor closing or trusted observation is unavailable,
the profile is ineligible; bwrap control descriptors must be closed before the
worker entry point and are never added to the permitted worker table.

`section_native_inventory_plan.v1` is the closed required-root set for one
exact dispatch attempt or for the one assembly operation. Payload keys:

```text
program_ref: REF
base_commit: G
scope: "builder-dispatch" | "assessor-dispatch" | "assembly"
work_item_id: H | null
role: "builder" | "assessor" | null
attempt: N | null
workspace_id: H | null
roots: sorted nonempty array[NATIVE_ROOT_SPEC] by root_id
root_count: N
observations: sorted nonempty array[NATIVE_OBSERVATION_REQUIREMENT]
    by observation_id
observation_count: N
```

The two counts equal their array lengths. Every `root_id`, namespace, locator,
and stable `(filesystem_id, file_id)` pair is unique. Every plan contains the
exact central policy roots: candidate, integration checkout, common Git,
Council root, configured owner anchors, other worker leaves, canonical
evidence, and hidden suites. A dispatch plan additionally contains its exact
runtime and private output roots; the assembly plan contains every runtime and
dispatch-output root used by the program. Omission is not represented as an
empty inventory: it is a plan mismatch and refuses the program. A root that is
required absent from a worker namespace is still inventoried by the trusted
host before and after that worker; mount-table evidence proves its absence in
the child.

For a dispatch plan, all four dispatch fields are non-null, scope and role
agree, and observations include one pre/post-worker requirement for every
protected central root plus that dispatch's exact output/runtime roots. For the
single assembly plan, all four fields are null and observations include one
pre/post-assembly requirement for every root. Observation context fields equal
their containing plan exactly. `observation_id = domain_hash(
"council:native-observation-requirement:v1", exact requirement with that field
omitted plus program_ref)`. The closed policy expansion, not a builder-selected
phase subset, determines the exhaustive requirement set.

Every sandbox profile references the plan for its exact future role/attempt/
workspace. Authorization, assignment, receipt, journal manifest, attestation,
and inventory records must all match it. The evidence root contains exactly one
dispatch plan for every journaled dispatch attempt and exactly one assembly
plan; no unused, missing, or multiply claimed plan is valid.
Descriptors for a given central policy root are byte-identical across every
plan; each output descriptor is unique to its workspace and also appears in the
assembly plan. The assembly plan's root set is the exact normalized union of
all central, candidate, runtime, and dispatch-output roots, so a per-dispatch
plan cannot hide a root from final cross-root comparison.

Central roots use `workspace_id=null`; candidate/output roots bind the exact
preallocated workspace. `locator_sha256` hashes the canonical configured
native root locator under domain `council:native-root-locator:v1`; it is not a
content digest. Root filesystem/file identities come from a no-follow handle
opened when the plan is frozen. A later replacement handle is not equivalent
even when directory contents match.

`section_native_inventory.v1` payload keys:

```text
program_ref: REF
native_inventory_plan_ref: REF
base_commit: G
observation_id: H
root_id: H
observer_assignment_ref: NULLREF
observation_workspace_id: H | null
phase: "pre-dispatch" | "post-worker" | "pre-assembly" | "post-assembly"
observed_root_filesystem_id: H
observed_root_file_id: H
entries: sorted array[NATIVE_ENTRY] by path
inventory_sha256: H
```

`inventory_sha256 = domain_hash("council:section-native-inventory-content:v1",
canonical JSON of `native_inventory_plan_ref`, the resolved complete
`NATIVE_ROOT_SPEC` and `NATIVE_OBSERVATION_REQUIREMENT`,
`observer_assignment_ref`, `observation_workspace_id`, `phase`, and sorted
entries)`. The observed root identity and root workspace must equal the root
spec; phase, scope, and observation workspace must equal the requirement. Every
dispatch inventory references that exact assignment, including trusted-host
observations of central roots; assembly inventories require null assignment.
Paths are relative to and
therefore namespaced by that exact root. Entries exhaustively include every
descendant regular file and directory admitted by the root's exact `view_kind`;
the root itself is represented by the root spec. Regular files have a non-null
byte SHA-256, directories have null content, and symlinks/reparse points/special
files refuse. The path, observation, filesystem id, file id, type, link count,
mode, and content relations use only the §6 `linux-native-id-v1` encoder and
no-follow handle enumeration; `lstat`/`fstat` values without the stable handle,
mount, and filesystem observations are insufficient. Unavailable stable native
identity makes dispatch or assembly ineligible.

For every observation requirement in the plan, the evidence root contains
exactly one inventory and no inventory for an undeclared observation. Before and
after comparisons are keyed by root id, never relative path alone. Across the
complete required set the validator compares every `(filesystem_id, file_id)`
pair for roots and entries; an identity appearing in two namespaces, an
unexpected link count, a root swap, or an omitted root refuses even when bytes
and relative paths are equal.

`worker_sandbox_attestation.v1` payload keys:

```text
program_ref: REF
assignment_ref: REF
launcher_receipt_ref: REF
journal_manifest_ref: REF
sandbox_profile_ref: REF
observed_mount_table_ref: REF (artifact_type="check_evidence")
observed_process_status_ref: REF (artifact_type="check_evidence")
observed_environment_ref: REF (artifact_type="check_evidence")
observed_fd_table_ref: REF (artifact_type="check_evidence")
source_snapshot_ref: REF (artifact_type="source_snapshot")
output_inventory_ref: REF (artifact_type="read_inventory")
native_inventory_before_refs: sorted nonempty array[REF]
    resolving to section_native_inventory.v1
native_inventory_after_refs: sorted nonempty array[REF]
    resolving to section_native_inventory.v1
unexpected_fd_count: N
writable_filesystem_fd_count: N
external_write_attempt_count: N
external_write_success_count: N
exit_status: N
```

Eligibility first requires the referenced receipt to have
`barrier_status="ready"` and to occur in the referenced journal manifest's
receipt slot. A refused receipt may be preserved only in the journal and typed
`scheduler_failure_evidence`; it cannot support an attestation, proposal,
assessment, evidence bundle, or local pass. Eligibility additionally requires
`unexpected_fd_count=0`, `writable_filesystem_fd_count=0`, zero external-write
successes, and exact one-to-one `pre-dispatch`/`post-worker` inventories for
every observation assigned to this exact dispatch. Each before/after root identity
and protected content is equal; only this dispatch's declared private output
root may change. The fd-table evidence must enumerate exactly 0/1/2 with the
profile's roles and targets. An attestation is supporting evidence, not a
substitute for the kernel-enforced mount namespace.

### 6.8 Findings and complete assessor ownership

A `finding_declaration` blob is canonical JSON with exactly:

```text
{
  "audit_level": "section" | "boundary" | "system",
  "severity": "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
  "invariant_id": S,
  "claim": T,
  "evidence_output_relpath": P,
  "reproduction_output_relpath": P,
  "affected_path": P | null,
  "blocks_local_pass": B,
  "status": "open" | "resolved" | "unreproduced",
  "predecessor_finding_ref": NULLREF,
  "resolution_output_relpath": P | null
}
```

Output paths are leaf-relative, unique, and must occur in the frozen exhaustive
output inventory with the expected media type. The packager may translate only
those paths into the exact content refs below; it cannot rewrite judgment text,
severity, status, or lineage.

`section_finding.v1` payload keys:

```text
program_ref: REF
contract_ref: REF
assessor_assignment_ref: REF
affected_proposal_ref: REF (artifact_type="proposal")
finding_declaration_ref: REF (artifact_type="finding_declaration")
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
assessment_declaration_ref: REF (artifact_type="assessment_declaration")
assessor_output_inventory_ref: REF (artifact_type="read_inventory")
check_declaration_refs: sorted nonempty array[REF]
    (artifact_type="check_declaration")
check_results: sorted nonempty array[CHECK_RESULT] by check_id
finding_refs: sorted array[REF]
finding_inventory_sha256: H
finding_count: N
open_blocking_count: N
local_assessment: "pass" | "blocked" | "error"
error_reason: T | null
predecessor_assessment_ref: NULLREF
```

The assessor writes closed finding declarations, evidence, checks, and one
assessment declaration into its isolated output leaf, but it does not construct
reference-bearing `section_finding.v1` records or the final manifest. The
trusted packager freezes and no-follow enumerates **every file** in that leaf,
wraps all bytes, deterministically constructs each finding from its declaration
and wrapped evidence, and then constructs the manifest outside the leaf from
that exhaustive inventory. The inventory bytes use one closed canonical JSON shape containing
the sorted tuples `(output_relpath, byte_length, blob_sha256)` for every leaf
file; a path not represented by a sealed content record refuses packaging.

The exact finding preimage is the canonical JSON array, sorted by
`record_relpath`, of:

```text
{"record_relpath": P, "record_id": H, "content_sha256": H}
```

for every and only packaged `section_finding.v1` record in the predeclared
repository slots. Every tuple must trace to exactly one frozen
`finding_declaration` file and its evidence files; every such declaration must
produce exactly one tuple.
`finding_inventory_sha256 = domain_hash(
"council:section-finding-inventory:v1", that exact array)`. The recomputed
array must contain exactly `finding_count` records and exactly the sorted
`finding_refs`; missing, extra, swapped, reordered, unreferenced, or
non-finding bytes in the findings namespace refuse packaging. The declaration,
whole-leaf inventory, and manifest must agree on every check and finding.

Packaging is one exact field mapping, not a judgment step:

1. Static program/contract/work-item/assignment/context/proposal fields equal
   the closed assessment declaration and the assessor assignment/context.
2. Each declared check path wraps exactly one `check_declaration`; each such
   declaration maps to one `check_declaration_ref` and one `CHECK_RESULT` whose
   id/status are copied and whose evidence REF is the wrapped evidence path.
   There are no other check declarations or results.
3. Each declared finding path maps to exactly one `section_finding.v1` under
   the field-by-field rule above. The resulting sorted refs, exact inventory
   hash, count, and open-blocking count are purely recomputed.
4. `predecessor_assessment_ref` and `error_reason` are copied exactly.
5. The disposition is derived once: `error` iff `error_reason` is non-null;
   any check with status `error` requires that condition. Otherwise `blocked`
   iff a check fails or an open finding has `blocks_local_pass=true`.
   Otherwise `pass` requires every contract-required check exactly once with
   status `pass`, zero open blockers, and complete prior lineage. A missing or
   duplicate required check is invalid rather than silently classified.
6. `declared_disposition` must equal that derived value, and
   `local_assessment` copies it. No packager-selected alternative is valid.

A reassessment references its predecessor and carries every prior finding
either unchanged or with a valid resolution; dropping one is invalid. Thus one
frozen assessment leaf has exactly one valid manifest. Changing disposition,
check status/evidence, predecessor, finding membership/count, or error reason
without changing the corresponding assessor bytes always refuses packaging.

### 6.9 Section, boundary, comparison, and scope results

`section_evidence_bundle.v1` payload keys:

```text
program_ref: REF
contract_ref: REF
work_item_id: H
base_commit: G
builder_assignment_ref: REF
assessor_assignment_ref: REF
builder_launcher_receipt_ref: REF
assessor_launcher_receipt_ref: REF
builder_journal_manifest_ref: REF
assessor_journal_manifest_ref: REF
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
error_reason: T | null
resource_metrics: sorted array[METRIC] by metric_id
dependency_snapshot_ref: REF (artifact_type="read_inventory")
staleness_input_refs: sorted nonempty array[REF]
```

Its launcher receipts must both have `barrier_status="ready"`, resolve through
the same principal registry and exact assignments, and occupy the receipt slot
of their exact journal manifests. Both attestations bind those same manifests.
A refused, unexported, duplicated, or wrong-sequence receipt makes the bundle
invalid regardless of its local-assessment value. Its local assessment and
error reason must equal the assessor manifest and cannot be supplied by the
builder or packager.

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
predicted_changes: sorted nonempty array[PREDICTED_CHANGE]
  by (path, kind, rename_source-or-empty)
actual_changes: sorted array[ACTUAL_CHANGE]
  by (path, kind, rename_source-or-empty)
realized_system_artifact_paths: sorted nonempty array[P]
section_bundle_refs: sorted nonempty array[REF]
assembler_binary_ref: REF (artifact_type="assembler_binary")
assembled_tree_sha256: H
envelope_paths: exactly sorted array containing
  "artifacts/section-council/<planned_request_id>/final-scope.json"
  "artifacts/section-council/<planned_request_id>/root.json"
```

The predicted and actual change arrays contain only section/project changes,
never HSC records, raw evidence blobs, or envelope files. Every actual change
must equal exactly one predicted change in path, kind,
rename source, and base blob/mode, then satisfy the §6 per-kind after-state
truth table. Every predicted `required=true` operation must occur. The
final predicted array is exactly the normalized union of section declarations;
it may narrow optional operations to those realized but cannot add a new path or
kind. `realized_system_artifact_paths` is a path-only subset of the program's
precomputed exact `add` slots, excludes both envelope paths, and contains every
and only HSC record/raw-evidence file actually created. The root later binds the
bytes and identities at those paths. No ownership directory or glob can
authorize an unpredicted child.

`assembled_tree_sha256 = domain_hash("council:section-project-tree:v1",
canonical sorted array[FILE_REF] for the complete candidate Git tree after
project changes but with
`artifacts/section-council/<planned_request_id>/` excluded)`. It is computed
before any source-local HSC artifact or envelope exists and is independently
recomputed from the final commit under the same exclusion.

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

The root enumerates **every** bootstrap content record, principal registry,
program, contract, context, content record, authorization, assignment, launch
receipt, scheduler journal manifest, sandbox profile/attestation, native
inventory plan/inventory, finding, assessment,
evidence bundle, boundary report, comparison report, work graph, and final
scope record for the source. The validator walks all references, requires one
reachable acyclic graph, rejects unreachable extras, requires
`record_count == len(record_inventory)`, and rejects member omission, addition,
reordering, cross-program reuse, or stale child reuse. The root does
not list itself, so there is no self-cycle.

The validator also computes `rooted_system_paths` as every
`record_inventory.repository_relpath` except the final-scope envelope plus every
bootstrap/content `storage_relpath` reached from those records. Paths must be
unique or identify the same exact bytes under the explicitly typed record/blob
relationship. This normalized set must equal
`final_scope.realized_system_artifact_paths` exactly. Thus a system file cannot
be committed merely because its path occupied an optional program slot; it must
also be reachable and byte-bound by the root.

The committed paths are fixed by v1:

```text
artifacts/section-council/<planned_request_id>/root.json
artifacts/section-council/<planned_request_id>/final-scope.json
```

Finalization is one-way and uses no cryptographic fixed point:

1. Assemble and freeze the project changes.
2. Build all pre-scope HSC records and evidence; construct `final-scope.json`
   over project changes plus the path-only list of realized system-artifact
   slots. A later boundary report may reference final scope because scope does
   not contain that report's bytes.
3. Build remaining post-scope records, then `root.json`; it inventories
   `final-scope.json`, every earlier/later record, and every raw evidence blob,
   but never itself.
4. Add those two exact files and create the candidate Git commit.
5. From that immutable commit, the HSC pre-publish wrapper computes the complete
   real diff and requires it to equal: (a) the final scope's exact project
   changes, (b) one `100644` add for every realized system-artifact path, with
   bytes/identity covered by the root and program slot, and (c) two `100644`
   adds at the fixed envelope paths. It then reads the exact Git blob ids and
   SHA-256 byte digests of both envelope files from the commit.
6. Only the later ordinary request binds the commit and envelope bytes.

Neither committed envelope contains its own Git object id/content digest or a
later request/commit binding. Before calling the unchanged ordinary publisher,
the wrapper requires one exact scope-list entry:

```text
HSC_V1 target_commit=<G> root_path=<P> root_id=<H>
       root_sha256=<H> root_git_blob=<O> scope_path=<P>
       scope_id=<H> scope_sha256=<H> scope_git_blob=<O>
```

The entry is one line with single ASCII spaces, in the shown key order, and no
extra fields. `target_commit` must equal the ordinary request target. The Git
blob ids and SHA-256 values must resolve from that commit at the exact fixed
paths. The wrapper rejects absence, duplication, malformed spacing, an envelope
or system-artifact path occurring in project changes, a system path not
predeclared/realized/rooted, a full-diff mismatch, or any id/byte/blob
mismatch. Existing `publish_request` then hashes that exact scope string into
the ordinary `request_payload_hash` and pins it in `AUDIT_REQUESTED`. Thus the
current request schema and authority remain unchanged while the HSC path gains a
machine-readable, post-commit request-bound scope root. A caller bypassing the
HSC wrapper has no hierarchical evidence claim and cannot present local bundles
as such.

After assembly, binding remains acyclic:

```text
bootstrap bytes + principal registry -> program -> BUILD_STARTED
    -> contracts/work/assessments -> final scope -> evidence root
    -> final commit -> ordinary request envelope binding
    -> request hash -> Codex verdict -> integration
```

The revision-3 macro-stage table is replaced by one exact reference-derived
total order. Coarse phases are explanatory only and never participate in
validity.

The validator constructs the record set named by `record_inventory`, adds a
directed edge `target -> source` for every internal `REF` in `source`, and adds
the same kind of edge from each inventory member to the terminal evidence root.
It then runs this canonical Kahn ordering:

1. Reject an unresolved, ill-typed, self, cross-program, or prohibited external
   reference before ordering.
2. Initialize `ready` to every node with zero unresolved incoming reference
   dependencies.
3. Select exactly one node at a time by the bytewise key
   `(schema_version UTF-8, record_id)` from `ready`, assign the next contiguous
   `construction_ordinal` beginning at zero, remove its outgoing edges, and
   repeat.
4. Reject if nodes remain after `ready` becomes empty. Reject if any internal
   REF target's ordinal is not strictly less than its source's ordinal.
5. Require the evidence root to have the final ordinal and to enumerate every
   preceding record exactly once. The root never inventories itself.

Because one node is selected at a time, there are no peers. The explicit edge
from prerequisite `source_snapshot` and `read_inventory` content records places
them before every profile that consumes them. `parent_content_refs` places
parent content before child content. `upstream_contract_refs` places each
dependency contract before its consumer regardless of schema equality or DAG
depth. Authorization -> assignment -> receipt -> journal-manifest references,
assessment lineage, final-scope references, and every other same-schema chain
are handled identically; no schema-specific same-stage exception exists.

Raw blob bytes are frozen before their wrapping content record and are verified
by size/hash rather than modeled as REF nodes. Existing Council events, the base
Git commit, and the comparison report's two previously sealed external roots
are the only external terminals; each uses its explicit §6.1 verifier and is
not assigned an ordinal in the new root. No record payload contains the later
candidate-commit, ordinary-request, independent-verdict, or integration-event
identity. Retries and reassessments are ordered by their explicit predecessor
and journal-chain references, never by an inferred wall clock or a coarse
attempt/stage tuple.

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

Write authority is the exact set of predicted `(path, kind, rename_source,
base-blob, base-mode)` operations. A directory name confers no authority over
its children. Rename requires
both the exact `rename_source` and destination; delete and mode change are
explicit kinds. The actual diff is an exact sorted list of `ACTUAL_CHANGE`
objects and no actual operation may be absent from the predicted list. A
required predicted operation may not be absent. The final scope manifest independently
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
   tmpfs. The launcher applies the exact §6.7 fd policy before releasing the
   worker barrier; the trusted parent observes exactly fd 0/1/2 and no writable
   filesystem descriptor. No host environment variable or inherited descriptor
   exposes another writable path. Network is unshared.
6. The worker emits a reviewed patch/report plus its closed output inventory;
   it never edits a Git checkout.
7. A separate assessor sandbox receives the same read-only source plus the
   sealed proposal and deterministic evidence, and has a different output
   leaf unavailable to the builder.

If `bwrap`, mount namespaces, no-follow source export, seccomp, fd closure and
trusted fd-table observation, stable native identity, or a required
read-only/absent-root assertion is unavailable, writable hierarchical execution
is **ineligible**. The task may use the existing sequential Council, but it may
not claim section isolation. Windows or macOS require a future separately
audited equivalent profile; v1 does not silently emulate one.

The trusted deterministic assembler is the only HSC component permitted to
write the integration checkout. It runs only after a complete assessor pass,
revalidates the program/root/scope, parses the proposal without shell
evaluation, refuses binary/symlink/submodule/special-file patches, validates
every old blob/mode against the frozen base, and applies exact changes in sorted
`work_item_id` order using handle-relative no-follow operations. Before any
write it opens every affected ancestor and target no-follow and reconstructs
the exact §6 native observation and filesystem/file ids, requires regular
targets to have `link_count=1`, and rejects a target id that appears at another
candidate or protected path.
Missing stable identity, a regular hardlink, or any native alias refuses before
proposal bytes are applied.

`add` creates a same-directory temporary regular file with create-exclusive and
no-follow flags, verifies its native identity/link count, writes/fsyncs/chmods
it, and installs it with no-replace semantics. `modify` and `mode` never write
or chmod the old inode: they construct and fsync a replacement inode, recheck
the unchanged old identity/blob/mode/link count, and atomically replace it.
`delete` and pure `rename` recheck a unique source identity immediately before
unlink/rename; rename uses no-replace semantics and forbids combined content or
mode edits. Directories are fsynced after namespace changes. Failure before the
atomic operation leaves the old path intact; a later failure aborts the entire
disposable candidate and never publishes a partial tree.

Before and after assembly the trusted host realizes every
`pre-assembly`/`post-assembly` pair required by the exact native-inventory plan,
including candidate, integration checkout, common Git, Council, anchors, other
leaves, canonical evidence, hidden suites, and every visible runtime root. Only
declared candidate path identities may differ. Root-id/locator/native identity
must still match the plan, all required phases must occur exactly once, and the
complete cross-root native-id comparison must remain alias-free. Any omission,
root swap, drift, alias, external modification, semantic/text conflict, or
unexpected Git metadata change aborts without choosing a winner.

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
  typed reference walk, explicit bootstrap-to-request topological construction,
  cycle rejection, and complete evidence-root validation;
- domain-separated hashing;
- the closed exact-path/change algebra, final-scope validator, and fixed HSC
  ordinary-request binding parser;
- deterministic conflict classification;
- dependency and staleness calculation;
- no worker launch and no Council mutation.

Route as a normal source request and independently audit the exact commit.

### Slice HSC-B — single-section executor pilot

Add the pinned `linux-bwrap-v1` launcher, read-only no-Git source export,
exact descriptor closure/observation, private proposal output, typed native
inventories, protected-host integrity attestation, alias-safe atomic assembler,
scheduler-minted registry/authorization/assignment/receipt chain, sealed
assessor output, canonical complete finding-manifest ingestion, real-diff
enforcement, evidence-root packaging, and crash-safe protected journals. Run one section without
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
10. builder/assessor distinct labels, credentials, or sessions resolving to the
    same registry authority/control key refused;
11. builder-minted, forged, swapped, incomplete, or assignment-mismatched
    scheduler authorization/launcher receipt refused;
12. every §6.1 record rejects missing/extra keys, self-id mismatch, wrong
    domain/version, parent substitution, cross-program replay, member
    omission/addition/reordering, unreachable extras, and stale-child reuse;
13. root record count/inventory mismatch, bootstrap/program back-reference, or
    post-commit request root/scope/blob binding mismatch refused.

### Scope and conflict

14. hostile worker relative, absolute, symlink/reparse, mount, inherited-fd,
    and shared-Git writes fail inside the OS sandbox;
    integration/common-Git/protected-root inventories remain unchanged;
15. only an assembler-authorized exact proposal can alter the candidate;
16. actual diff contains a path/kind absent from exact predicted changes,
    including an unpredicted child inside a declared sibling directory;
17. two sections overlap writes or rename sources/destinations;
18. one section writes another's mutable read;
19. immutable inventory-pinned read permits safe sharing;
20. ambiguous case/NFC/rename/symlink/reparse/hardlink/native identity fails
    closed before application;
21. every add/delete/modify/mode/rename nullable/equality combination outside
    the §6 truth table refuses;
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
49. assembler detects post-assessment drift, hardlink/native aliasing, inherited
    writable authority, or any protected-host identity/content change.

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

### Revision-4 construction and authority closure

58. construct one minimal instance of every v1 record from raw bytes in the
    specified topological order; ids and bytes are stable across rebuilds;
59. direct or indirect bootstrap/program, authorization/assignment/receipt, and
    scope/root reference cycles refuse;
60. commit a fixture with `final-scope.json` then `root.json`; verify the later
    ordinary request binds target commit, both Git blobs, both byte digests, and
    the exact full diff without either committed envelope self-binding;
61. mutate either committed envelope after finalization and refuse publication;
62. generate every null/present and equal/different blob/mode combination for
    each change kind; accept only the §6 truth table and round-trip the canonical
    real Git diff deterministically;
63. inherited writable regular-file, directory, and socket descriptors are
    closed before the worker barrier or make launch ineligible; the attested
    worker table is exactly fd 0/1/2;
64. regular hardlink/native-file-id aliases for modify/delete/mode/rename refuse
    before application and leave all protected/unpredicted identities unchanged;
65. distinct registry labels resolving to one control authority/key refuse;
    registry changes after `BUILD_STARTED` stale every assignment;
66. forged/swapped/builder-produced journal authorization or receipt, sequence
    gap, storage-owner/mode mismatch, or repeated-field mismatch refuses;
67. recompute the exact finding inventory across permuted, omitted, extra,
    predecessor-substituted, and unrelated leaf files; only one canonical
    complete tuple inventory is accepted;
68. construct a sandbox profile with a nonempty read-only mount list, a
    parent/child content chain, and a two-contract dependency chain; the
    canonical Kahn order places every target strictly earlier, while direct and
    indirect back-edges refuse;
69. inventory two equal-shaped native roots and prove that swapping/omitting a
    root, replacing its handle, colliding relative paths across namespaces, or
    mutating each required integration/common-Git/protected root independently
    refuses;
70. omit, add, duplicate, reorder, cross-link, writer-substitute, or gap an
    authorization/assignment/receipt journal triple; root validation refuses
    every self-hashed record not present exactly once in the unbroken typed
    manifest chain;
71. hold every other field constant between ready/refused receipts; the refused
    receipt cannot support an attestation, proposal, assessment, evidence
    bundle, or local pass and remains available only as failure evidence;
72. freeze one assessor leaf and construct its unique manifest; changing only
    disposition, check id/status/evidence, predecessor, finding membership or
    count, or error reason refuses without changed assessor declaration bytes.

### Revision-5 native construction closure

73. round-trip native path segments for `.gitignore`, `.git`, a nested
    dot-prefixed name, and one invalid-UTF-8 byte sequence; prove decoded-byte
    ordering is stable and reject empty segments, NUL, slash, `.`, `..`, odd or
    uppercase hex, duplicate decoded tuples, excess depth, and excess bytes;
74. inventory a real checkout containing a tracked dotfile using the exact
    checkout/common-Git view pair; prove `.git` is excluded exactly once from
    the checkout and exhaustively present under the referenced full-tree
    common-Git root, while a `.git` indirection file, missing/extra exclusion,
    overlap, locator mismatch, identity mismatch, or unreferenced delegated
    root refuses;
75. freeze one native observation and independently derive byte-identical
    anchor, locator, filesystem, file, namespace, and root ids; mutate each
    stored H while preserving the observation and require refusal; mutate each
    observation field and require the specified dependent ids to change;
76. expose one native object through two bind-mount namespaces with different
    `statx_mount_id` values and require equal filesystem/file ids plus alias
    refusal; require distinct objects with equal bytes and relative paths to
    retain distinct file ids;
77. construct the protected scheduler journal identity solely from its exact
    locator/observation/preimage and reject a caller-selected id, alternate
    field order/encoder, anchor alias, inventory-root equality, or any mismatch
    between embedded observation and derived ids; independently derive one
    byte-identical id from the manifest and verifier, then reject numeric 448,
    alternate strings, mode/type mismatches, and any second accepted mode
    encoding;
78. make `openat2`, no-follow resolution, `statx` mount identity, `fstatfs`
    fsid, persistent file handle, or stable re-observation unavailable one at a
    time and prove writable hierarchical dispatch and assembly fail closed with
    sequential mode still available.

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
| builder selects/impersonates assessor | pre-program owner-enrolled registry binds unique authority/control keys; protected scheduler journal binds authorization, assignment, receipt, session, context, and sealed output |
| local pass becomes global approval | local enum is not `GO`; no canonical authority event; final existing audit remains mandatory |
| scope creep | exact predicted changes, exact final scope manifest, root-bound request entry, and independently recomputed real diff |
| overlapping/ambient writes | kernel mount/fd sandbox exposes no host writable authority except private output; workers emit proposals; native inventories and alias-safe atomic replacement gate the assembler |
| incompatible section identities | exact interface/dependency digests and boundary closure |
| summary laundering | integration consumes raw content-addressed evidence, not builder prose |
| assessor finding suppression | exhaustive frozen output-leaf inventory plus exact domain-separated finding tuple root; manifest count/root must equal every finding; predecessor findings cannot disappear |
| record/member substitution | exact three-key schemas, bootstrap records, unique domains, typed references, topological construction, and one acyclic complete evidence root bound post-commit by the ordinary request |
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
