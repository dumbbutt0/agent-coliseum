# Hybrid Trajectory Scaling — design contract

Status: **design-only Slice A** for Council source
`first-gladiator-hybrid-trajectory-scaling-001`. This document does not authorize
implementation, branch execution, live-model contact, labels, weight changes,
hidden-suite access, or a scientific claim. Slices B–D require their own exact
commits, tests, independent audits, and authorized integrations after this design
receives the required plain verdict.

## 1. Objective and constitutional boundary

Agent Coliseum will combine two representations with deliberately different
responsibilities:

1. **Canonical execution and storage:** every execution is an immutable linear
   history identified by the integrated run, scheduler, manifest, world-line, and
   evidence identities. A fork is a new execution authenticated from an exact,
   reachable parent state. No ancestor is edited.
2. **Derived analysis and presentation:** eligible completed executions are
   projected into a deterministic, typed, rebuildable experience graph. The graph
   can show timelines, forks, interventions, convergence, divergence, and outcomes,
   but it is not evidence and is never required for replay.

In short: the canonical layer safely creates histories; the derived graph lets a
researcher observe the resulting possibility space.

This source builds the contract for bounded trajectory search. It does not build an
all-possibilities generator, graph database, morality oracle, learned selector,
real-world forecaster, or canonical history-merging system.

## 2. Reconciliation with the integrated substrate

The implementation SHALL extend the existing records and validators rather than
rename or duplicate them.

| Concern | Integrated authority to reuse | Hybrid rule |
|---|---|---|
| canonical execution | `spatial.scheduler_run.v1` | `scheduler_run_id` remains the scheduler execution identity; do not add a second canonical `run_id` to this record |
| run evidence directory | supported `run.json` plus source-evidence binding | descriptive `run_id` continues to identify the evidence bundle; it is not substituted for `scheduler_run_id` or `manifest_id` |
| linear replay | `SchedulerManifest` plus `verify_manifest()` | every child run has its own whole-chain re-derivable manifest; no graph edge enters the scheduler chain |
| world ancestry | `spatial.world_line.v1`, `WorldLineGenesis` | root/fork identity and parent-line ancestry stay unchanged |
| fork authorization | `spatial.fork_decision.v1`, `spatial.fork_initialization.v1` | an admitted branch must reuse the exact authenticated parent state, step, decision, child remap, and registered initialization |
| parent reachability | S2B recursive witness validation | a parent state is usable only when its scheduler state occurs at the exact position in the canonically re-derived parent manifest |
| intervention identity | integrated `Intervention` and spatial calibration records | candidates reference registered interventions and execution-instance bindings; they do not invent untyped changes |
| evidence authentication | provider-free/zero-model replay and complete evidence-file bindings | a hash commitment without replay verification is insufficient for scientific graph admission |
| eligibility | T0-A family dispatch, status vocabulary, training-admission and quarantine rules | the graph uses explicit versioned eligibility; unsupported is not pass |
| grouping | partition groups, lineage edges, effective-unit rules | graph topology never changes partition or effective-unit identity |
| content addressing | `ContentRecord`, domain-separated `content_id`, registry admission | all new authoritative search records use the same construction and validation discipline |

No existing schema is migrated by Slice B. New record variants are additive and
version-dispatched. Unknown versions fail closed. Historical artifacts remain
unchanged and are included only through an adapter that can authenticate every
required binding; otherwise they receive a stable exclusion reason.

## 3. Identity and time domains

The system MUST keep execution identity, position, simulated time, search order,
and operations metadata separate.

| Domain | Meaning | Identity rule |
|---|---|---|
| `run_id` | identity of a supported evidence bundle | reuse the artifact-family contract; never derive from day/year or directory traversal order |
| `scheduler_run_id` | identity of one committed scheduler execution | reuse `SchedulerRun`; one pure linear history |
| `manifest_id` | identity of the finalized canonical scheduler chain | reuse `SchedulerManifest` |
| `world_line_id` | root or forked world ancestry | reuse `WorldLine` and genesis/fork bindings |
| `scheduler_position` | ordered position inside one scheduler execution | local to that execution; a forked child may restart at position zero |
| `logical_step` | time represented by the integrated world state | remains the current simulated-world clock for the spatial substrate |
| `scenario_time` | optional future domain-specific world-time projection | never fabricated; v1 exposes `logical_step` or `unsupported`, and a later adapter may bind a richer versioned clock |
| `search_epoch` | generation of frozen candidate selection | belongs only to the search orchestration records, never the canonical world or scheduler identity |
| `recorded_at` | operational wall-clock metadata where permitted | excluded from deterministic selection, candidate admission, canonical replay, and graph content identity |

Two branches can occupy the same simulated year while having different scheduler
positions, decisions, ancestry, and execution duration. Worker completion order,
filesystem ordering, process ids, host paths, and wall-clock time MUST NOT alter
candidate selection or a canonical result.

## 4. State machine and responsibility split

```text
search manifest frozen
        |
        v
epoch OPEN -> evidence set frozen -> candidates GENERATED
        |                              |
        |                              v
        |                         VALIDATED/REFUSED
        |                              |
        |                              v
        |                       admission manifest sealed
        |                              |
        v                              v
 admitted slots execute independently; every slot reaches a terminal handling state
        |
        v
epoch CLOSED -> newly eligible evidence may enter only the next epoch
        |
        v
derived graph rebuilt from a separately frozen eligible-evidence commitment
```

Canonical execution never waits on or reads the derived graph. Search selection may
consume only allowlisted, versioned evidence products committed before its epoch
opens. It may not consume an in-place mutable graph view.

### 4.1 Epoch states

The initial state vocabulary is closed:

- `open`: the input commitment is sealed and generation may run;
- `admissions_sealed`: accepted/refused decisions are immutable;
- `executing`: admitted slots may be claimed and completed independently;
- `closed`: every admitted slot has an authenticated success, failure,
  incomplete, or quarantine disposition and the closure record is sealed;
- `aborted`: a governed operator stop prevents new execution; recorded admissions
  remain immutable and already produced evidence is not deleted.

An interrupted epoch remains in its last authenticated state. It is resumed; it is
not regenerated with new inputs. `aborted` does not silently become `closed`, and an
operational timeout does not remove or reassign a selected candidate.

## 5. New additive record family

Names are binding for this design unless implementation reconnaissance finds an
integrated record with the same semantics; in that case the implementation source
must document the exact reuse and may not create a duplicate.

All records below are `ContentRecord` values with exhaustive versioned content,
strict key sets, construction-frozen admission, domain-separated ids, and no
self-id in their preimage. References must resolve to the expected domain before a
record is admitted.

### 5.1 `trajectory.branch_search_budget.v1`

`branch_search_budget_id` binds:

- schema and budget versions;
- maximum total admitted branch executions;
- maximum admitted executions per epoch;
- maximum branch depth;
- maximum generated candidates per epoch and per parent;
- maximum live-model calls and generated tokens;
- maximum integer execution-cost units;
- maximum supported scenario-time/logical-step horizon;
- closed allowed candidate categories;
- exact per-category caps;
- required replication and rare-risk reserves;
- reserve borrowing policy, fixed to `none` in v1.

All hard limits are non-negative integers, with internally consistent maxima.
Unlimited sentinels are forbidden. An experiment needing a larger bound gets a new
budget identity. Wall-clock allowance may be carried by a separate operational
launch envelope but is never a budget identity input and never changes admissions.

### 5.2 `trajectory.branch_selection_policy.v1`

`branch_selection_policy_id` binds:

- closed candidate category vocabulary;
- allowlisted candidate-producer versions;
- exact eligibility profile;
- exact integer/lexicographic selection-vector definition;
- category order and quota handling;
- deterministic tie-break field, ending in `branch_candidate_id`;
- cost estimator version;
- deduplication version;
- unsupported-category behavior, fixed to refusal;
- policy claim ceiling, fixed to transparent bounded selection rather than
  scientific value or optimality.

The first implementation uses no fitted score, floating-point weighted sum,
random tie-break, LLM judgment, or runtime heuristic.

### 5.3 `trajectory.branch_search_manifest.v1`

`branch_search_manifest_id` binds:

- experiment and search-program identity;
- budget and selection-policy ids;
- eligible artifact-family/profile versions;
- intervention, environment, agent, scheduler, and replay-regime commitments;
- permitted execution-adapter versions;
- partition/hidden-evaluation visibility class;
- maximum epoch count;
- authorization ceiling (`scripted_only` in the first implementation);
- source code commit and record-schema set.

Changing a budget, policy, producer, execution adapter, visibility class, or regime
produces a distinct search manifest. Searches with different manifests may not be
silently pooled.

### 5.4 `trajectory.search_epoch_open.v1`

`search_epoch_open_id` binds:

- search manifest id;
- zero-based epoch index;
- prior epoch-closure id, null exactly for epoch zero;
- sorted eligible source-evidence ids;
- frozen eligible-evidence-set digest;
- cumulative authenticated budget consumption before this epoch;
- producer input commitments;
- opening state.

The evidence set is complete and frozen before candidate generation. Later worker
completion cannot enter the current epoch.

### 5.5 `trajectory.branch_candidate.v1`

`branch_candidate_id` binds:

- search manifest and epoch-open ids;
- experiment id;
- candidate category and producer version;
- parent evidence `run_id`, source-evidence id, `scheduler_run_id`, manifest id,
  world-line id, exact scheduler-state id, scheduler position, world-state hash,
  and logical step;
- authenticated fork decision or preregistered branch specification;
- intervention, environment, agent, and policy regime ids where applicable;
- scenario identity and seed plus the registered randomness/stream identity where
  the execution family uses stochasticity (a stochastic candidate without that
  binding is ineligible rather than assigned a fabricated seed);
- fixed-versus-changed dimension declaration;
- proposed execution-adapter version;
- estimated live calls, tokens, cost units, and scenario horizon;
- parent branch depth;
- category-specific evidence references;
- deterministic selection-feature prefix (never the candidate's own id);
- candidate-equivalence key.

The candidate-equivalence key is separately domain-separated over the stable
semantic execution request: search manifest, experiment, complete authenticated
parent binding, fork/intervention/regime bindings, and execution adapter. It omits
only the epoch-open id so the same execution request cannot consume budget twice in
later epochs. The `branch_candidate_id` retains the epoch-open id so generation
lineage is never lost. Cross-experiment reuse is refused even if other fields match.

Identity construction is nonrecursive: the record preimage binds only the
selection-feature prefix. After `branch_candidate_id` is computed once, the selector
forms the sortable vector as `(selection_feature_prefix..., branch_candidate_id)`.
That complete sortable vector is not embedded back into the candidate preimage.

A candidate is a proposal, not a run and not evidence. It always carries
`execution_status: unexecuted` in candidate/preview views. A UI may not depict it as
an observed trajectory.

### 5.6 `trajectory.epoch_candidate_generation.v1`

`epoch_candidate_generation_id` binds:

- epoch-open id;
- every invoked producer id/version and input commitment;
- complete deterministically sorted generated candidate ids;
- validation result and stable reason codes for every produced candidate;
- exact duplicate-equivalence groups;
- per-parent, per-category, and total counts;
- generation status (`complete` or `failed`);
- bounded failure reasons, including candidate-count overflow.

Only `complete` generation may proceed to admission. If a producer crashes,
overflows its bound, omits an input, or cannot prove complete enumeration, the
record is `failed`; no traversal prefix is admitted. Retrying generation over the
same frozen epoch inputs must reproduce the same complete record or preserve the
failed attempt as operational lineage and refuse.

### 5.7 `trajectory.epoch_admission_manifest.v1`

`epoch_admission_manifest_id` binds:

- epoch-open and complete candidate-generation ids;
- complete sorted candidate-id set and generation statistics;
- one decision for every validated or refused candidate;
- ordered admitted candidate ids and their zero-based execution-slot ordinals;
- stable refusal reason codes;
- budget consumption before and after admission;
- unused and reserved capacity;
- selection-policy re-derivation digest.

Each decision is one of `admitted`, `duplicate`, `ineligible`, `unsupported`, or
`over_budget`. Admission is all-at-once and immutable. It occurs before any branch
executes. A preview returns this same record content but does not publish execution
claims or launch work.

Execution-slot identity is also nonrecursive. The admission preimage stores only the
ordered `(ordinal, branch_candidate_id)` allocation. After the admission-manifest id
is computed once, a slot is referenced by
`(epoch_admission_manifest_id, execution_slot_ordinal)`; no derived slot locator or
manifest id is embedded back into the admission preimage.

### 5.8 `trajectory.branch_execution_binding.v1`

`branch_execution_binding_id` is the pre-realization bridge from an admitted slot
to one child execution. It binds:

- search manifest, epoch-open, candidate-generation, and admission-manifest ids;
- execution-slot ordinal and exact candidate id;
- complete parent/fork/intervention/regime binding copied and revalidated from the
  candidate;
- execution adapter and pre-realization execution-instance identity;
- reserved run/call/token/cost/horizon allocation;
- attempt policy and attempt identity (`0` only for the first deterministic slice);
- authorization ceiling inherited from the search manifest.

It binds no outcome. A new branch run uses an additive evidence schema or sidecar to
carry this id; existing run bytes remain unchanged. The execution adapter must
re-derive the binding before launch, and the disposition must prove that the child
evidence carries the same id. This prevents a valid child from another slot, search,
experiment, retry, or budget from being transplanted into the admission.

### 5.9 `trajectory.branch_execution_disposition.v1`

`branch_execution_disposition_id` binds one admitted slot by exact
`(epoch_admission_manifest_id, execution_slot_ordinal, branch_candidate_id,
branch_execution_binding_id)` to exactly one terminal handling result:

- successful canonical child evidence and its fork/genesis/manifest/source-evidence
  references;
- schema-valid recorded failure;
- authenticated incomplete result; or
- quarantine record and reasons.

This record does not promote completeness, reportability, claimability, governance,
or training admission. Corrections remain in the integrated correction lineage;
this disposition only references the currently valid result identity and cannot
replace it.

Duplicate workers may submit byte-identical evidence for the same slot; the first
valid disposition wins and a byte-identical retry is recorded as a duplicate
operational observation. Conflicting evidence is quarantined and prevents epoch
closure until resolved by the established governed mechanism. No last-writer-wins
state exists.

### 5.10 `trajectory.search_epoch_closure.v1`

`search_epoch_closure_id` binds:

- epoch-open and admission-manifest ids;
- every accepted slot and its exact terminal disposition;
- counts by completion/failure/incomplete/quarantine class;
- final budget consumption;
- unused reserves;
- closure state and bounded reason codes;
- eligible-success ids proposed for the next epoch, subject to fresh eligibility
  validation when that epoch opens.

Closure does not make unsuccessful evidence admissible and does not turn proposed
next-epoch evidence into current-epoch input.

### 5.11 `trajectory.graph_evidence_eligibility.v1`

`graph_evidence_eligibility_id` binds the closed artifact-family adapters, required
schema/completion/replay/fork/correction/quarantine statuses, safety view, and stable
exclusion-reason vocabulary. It is intentionally distinct from training admission.
An implementation may reuse a T0-A result as evidence for one gate, but it may not
reinterpret `unsupported`, `unknown`, or `not_evaluated` as graph eligibility.

### 5.12 `trajectory.experience_graph_projection.v1`

`experience_graph_projection_id` binds:

- graph schema and projector versions;
- safety view (`research` or `actor_safe`);
- eligibility profile;
- sorted eligible source-evidence records;
- input-evidence-set digest;
- node and edge stream digests;
- projection statistics and exclusions by stable reason;
- optional cluster-analysis spec and digest;
- projector code commit;
- fixed claim ceiling: derived indexing and comparison only.

The serialized graph streams are derived artifacts bound by the projection record.
They live outside canonical run directories and can be deleted.

### 5.13 `trajectory.scaling_benchmark_report.v1`

`scaling_benchmark_report_id` binds the generator/profile versions, input and output
digests, record counts, depth distribution, repeated-content statistics,
determinism checks, canonical-duplication check, and observed resource measurements.
Machine, runtime, and hardware describe the observation but do not turn a timing
number into a correctness requirement.

## 6. Candidate categories and first-slice support

The closed category vocabulary is:

1. `preregistered` — exact branch required by an authenticated experiment spec;
2. `replication` — repeated realization under a preregistered independent unit;
3. `novel_state` — branch supported by a versioned novelty measurement;
4. `uncertainty_disagreement` — branch supported by committed predictor
   disagreement evidence;
5. `butterfly_high_impact` — branch supported by a prior authenticated divergence
   report and a preregistered expansion rule;
6. `rare_risk` — branch supported by a versioned, non-normative risk-event predicate;
7. `representative_cluster` — branch sampled from a derived cluster through a
   committed representative-selection rule.

The vocabulary does not imply that all producers exist. Slice B SHALL execute only
`preregistered` and `replication` candidates whose interventions can be realized by
an existing allowlisted scripted spatial adapter. Other categories are representable
but MUST return `unsupported_producer` until a separately audited evidence producer
exists. Graph adjacency, prose, visual salience, or an LLM assertion is never a
category score.

## 7. Deterministic generation, ordering, and admission

For epoch `N`, the algorithm is:

1. Authenticate the search manifest, prior closure, and cumulative budget.
2. Discover and validate all source evidence under the frozen eligibility profile.
3. Sort source identities and seal `SearchEpochOpen`.
4. Invoke every allowlisted producer in its declared order over the complete frozen
   input; producers return data, never launch work. Producers use bounded sorted
   iteration. If the complete candidate count would exceed the manifest's generation
   bound, generation fails with `candidate_generation_bound_exceeded`; v1 does not
   select from a traversal-order-dependent prefix.
5. Validate exact parent reachability, intervention/regime bindings, estimates,
   category evidence, branch depth, visibility, and candidate key shape.
6. Deduplicate within the generated set by equivalence key, keeping the
   lexicographically smallest candidate id and recording every duplicate.
7. Reject equivalence keys already admitted by an earlier closure in this search.
8. Partition eligible candidates by category.
9. Sort each category by its exact policy vector. V1 vectors contain only bounded
   integers/enums/content ids and end in `branch_candidate_id`; no platform float.
10. Fill required reserves first, then ordinary category caps in the policy's fixed
    category order. V1 never borrows unused reserved capacity.
11. Before each admission, test every hard limit against cumulative plus proposed
    consumption. Refuse the candidate that would exceed any limit; never admit then
    roll back.
12. Seal the complete admission manifest before any worker can claim a slot.

Candidate file ordering, registry insertion order, worker count, process scheduling,
and completion time cannot influence this result. Parallel and sequential preview
must produce byte-identical admission content.

### 7.1 Initial lexicographic vector

For the first supported producers the vector is:

```text
(category_rank,
 replication_reserve_rank,
 parent_branch_depth,
 parent_source_evidence_id,
 parent_scheduler_position,
 intervention_id,
 execution_adapter_version,
 branch_candidate_id)
```

All ordering is ascending. A future scientific value or uncertainty score requires a
new audited policy version and must define integer quantization, missing-data
handling, provenance, and sensitivity. It may not be slipped into this vector.

## 8. Budget semantics

Budgets constrain selection, not scientific truth.

- Every accepted slot consumes one run unit immediately at admission, even if its
  execution later fails. Retrying the same slot does not consume another run unit;
  a scientifically distinct retry requires an already authorized attempt identity
  and a new candidate.
- Live-call and token estimates are upper admission bounds. Runtime meters refuse
  before crossing the bound and record an incomplete/failure disposition if the
  branch cannot finish within its allocation.
- A live call cannot be moved from one agent/candidate to another.
- Cost estimates are non-negative integers from the bound estimator version.
- Branch depth is root `0`; a child is parent depth plus one and must agree with the
  recursively authenticated fork ancestry.
- Per-parent limits bind the complete authenticated parent state, not a display
  label or visible-state cluster.
- Operational wall-clock stop requests cease new work but do not alter admission
  identity or discard evidence.
- Budget differences always imply distinct search identity. Results from different
  budgets may be compared explicitly but never pooled invisibly.

## 9. Fork execution and storage efficiency

An admitted branch becomes a canonical child only through the existing fork path:

```text
authenticated parent evidence
  -> exact SchedulerState in canonically verified parent manifest
  -> registered ForkDecision
  -> child WorldLine
  -> deterministic materialize_fork + ForkInitialization
  -> fork WorldLineGenesis with recursive reachability witness
  -> independent child SchedulerRun and SchedulerManifest
  -> complete child evidence binding and replay verification
```

Search records neither manufacture a parent witness nor bypass this chain. A stale,
forged, cross-experiment, or unreachable parent fails before execution.

Before the adapter launches, it validates the sealed admission and publishes the
pre-realization `BranchExecutionBinding`. The child evidence carries that binding
through an additive, strictly dispatched schema/sidecar, and replay re-derives it.
The scheduler's canonical preimage is unchanged: search provenance authenticates
why this child was executed but does not redefine the child's world or chain.

The child stores its own genesis, transitions, decisions, observations, and terminal
evidence and references its authenticated parent. It does not copy the parent's
entire trajectory into its canonical bundle. Existing content-addressed records and
periodic snapshots may be shared by reference where their contracts allow it, but
ancestry remains explicit. The derived graph can index repeated content without
changing canonical ownership.

## 10. Derived experience graph

### 10.1 Eligibility

The v1 scientific graph includes only artifacts for which all applicable gates in a
separate `graph_evidence_eligibility.v1` profile are explicit `pass`:

- recognized supported schema and family;
- unique, conflict-free canonical identity;
- complete terminal handling appropriate to the family;
- complete evidence bundle;
- provider-free/zero-model replay verification where required;
- authenticated fork ancestry for forked runs;
- not quarantined;
- valid correction lineage with incomplete corrections remaining incomplete;
- required graph-evidence admission and visibility profile.

Graph-evidence admission is not training admission. A run may be valid graph evidence
while training use is unsupported or not authorized. A training-oriented graph view
must additionally bind and satisfy the exact `TrainingAdmissionRecord`, dataset,
partition, and hidden-evaluation commitments; graph construction never promotes one.

`unknown`, `unsupported`, `not_evaluated`, or `fail` never becomes `pass` through
graph construction. Excluded artifacts remain counted by stable reason. A later
diagnostic graph that depicts failures would need a distinct view/schema and must
visibly preserve negative status; it is not part of v1.

### 10.2 Nodes

Typed nodes include:

- run origin, referencing canonical run/genesis/evidence identities;
- canonical state reference, never a copied or normalized state authority;
- decision/fork point, referencing exact scheduler and state positions;
- registered intervention;
- terminal outcome/result reference;
- optional derived cluster, explicitly marked analytical and noncanonical.

### 10.3 Edges

Typed edges include:

- `within_run_transition`;
- `parent_to_fork`;
- `intervention_realization`;
- `terminates_as`;
- `derived_similarity`;
- `derived_convergence`.

Every edge carries exact evidence references and its derivation version. Derived
similarity/convergence edges cannot be used as fork parents, replay inputs, partition
identity, or proof of state equivalence.

### 10.4 Convergence without merging

Two visible states can show the same rooms, agents, and resources while differing in
private knowledge, relationships, memory, commitments, scheduler history, or
institutional state. Therefore:

- byte-identical content records may share storage identity;
- versioned projections may cluster similar states;
- the UI may show convergence;
- canonical nodes and both ancestries remain distinct unless a future separately
  audited equivalence theorem proves complete causally relevant equivalence.

V1 performs no canonical merge and no history-independent deduplication.

### 10.5 Deterministic representation

The initial implementation uses bounded, sorted JSON/JSONL plus a content-addressed
projection manifest; it introduces no external graph service. Node order is by
`(node_type, canonical_reference, node_id)` and edge order by
`(edge_type, source_id, target_id, edge_id)`. Input discovery is sorted and complete.
Identical eligible evidence produces byte-identical streams and projection identity.

Deleting every graph artifact leaves canonical replay unchanged. Rebuilding from the
same evidence recreates the same bytes. A stale input digest refuses verification.

### 10.6 Derived indexes and resumable construction

Query indexes, adjacency tables, cluster indexes, and validation caches are derived
and disposable. A cache key binds source-evidence digest, adapter version,
eligibility-profile id, and projector version; a mismatch is a miss, never a pass.
Construction emits bounded content-addressed chunks into a fresh staging directory,
then publishes the projection manifest and terminal marker last. An interrupted
build may reuse only verified complete chunks and cannot expose a partial projection.
This permits incremental work and bounded queries without replaying 10,000 complete
histories on every request while preserving a deterministic clean rebuild path.

## 11. Research-safe and actor-safe exports

The research graph and actor-safe graph are distinct projection identities.

- `research` may contain authorized privileged state references but never hidden-suite
  contents beyond the caller's bound access class.
- `actor_safe` is produced server-side from allowlisted public/actor fields before
  serialization. It excludes privileged observations, other agents' private state,
  raw completions, evaluator-only data, hidden evaluation identifiers, and Council
  internals.
- Graph labels, tooltips, accessibility text, filenames, debug payloads, and cluster
  explanations obey the same boundary.
- Provenance ids remain trace metadata, not semantic agent features.

An actor-safe export cannot be reconstructed by deleting fields from a browser-side
privileged payload. The projector must never load unauthorized fields into that
serialization path.

## 12. Crash, concurrency, and recovery

The admission manifest is the immutable work ledger.

- A worker claims only an admitted slot and writes to a fresh slot-scoped staging
  directory outside canonical inputs.
- Claims are leases and operational metadata; they do not change selection identity.
- Publication uses create-once content-addressed/fixed outputs and a terminal marker.
- A crash before terminal publication leaves the slot resumable.
- Resume revalidates the admission manifest, existing artifacts, and budget meters;
  it never regenerates candidates.
- The same slot cannot publish two conflicting dispositions. Conflicts quarantine
  the slot and preserve both operational reports for audit.
- Epoch closure requires exactly one terminal disposition for every admitted slot.
- A partial or aborted epoch cannot supply candidates to the next epoch.
- Sequential and parallel execution of the same sealed admissions must yield the same
  admitted set. Canonical result bytes remain subject to each execution regime's own
  determinism contract; the selector never overclaims provider nondeterminism.

## 13. Security and integrity boundaries

Implementation must fail closed against:

- path traversal, symlink/junction/reparse aliases, overlapping input/output roots,
  and writes beneath canonical runs, repository source, or Council trees;
- forged parent hashes, unreachable scheduler states, stale manifests, and fork
  witness transplant;
- candidate or execution reuse across experiments, epochs, policies, regimes, or
  hidden-access classes;
- malformed/oversized records, excessive depth, count, JSON depth, strings, and
  graph streams;
- unregistered candidate producers, execution adapters, scripts, plugins, or remote
  content;
- browser or graph input that starts execution or mutates evidence;
- quarantine, incomplete, unauthenticated, unsupported, or corrected-to-incomplete
  evidence entering the scientific graph;
- hidden evaluation leakage through candidate scores, graph labels, trace endpoints,
  logs, or actor-safe export;
- effective-unit inflation caused by branches, repetitions, shared models, or graph
  clusters.

No arbitrary Python/plugin execution, remote graph fetching, automatic model contact,
or public branch-execution endpoint is authorized.

## 14. Programmatic API and CLI contract

Slice B and C expose narrow repository-native commands equivalent to:

```text
coliseum-lab trajectory-search-validate MANIFEST
coliseum-lab trajectory-search-candidates MANIFEST --epoch N
coliseum-lab trajectory-search-preview MANIFEST --epoch N
coliseum-lab trajectory-search-run-scripted ADMISSION_MANIFEST
coliseum-lab trajectory-search-resume ADMISSION_MANIFEST
coliseum-lab trajectory-search-status SEARCH_MANIFEST

coliseum-lab experience-graph-build ELIGIBILITY_MANIFEST
coliseum-lab experience-graph-verify PROJECTION
coliseum-lab experience-graph-export PROJECTION --view actor-safe|research
coliseum-lab experience-graph-trace PROJECTION NODE_OR_EDGE_ID
```

Exact spelling may follow implementation reconnaissance, but semantics may not be
combined with the existing generic vignette `graph` command without versioned
dispatch. Preview is pure and launches nothing. Scripted execution accepts only the
sealed admission manifest and allowlisted adapter. Trace reports canonical refs and
validation status; it never returns evidence outside the view authority.

Outputs default to stdout or a protected derived-output root. Commands never accept
an arbitrary canonical run destination. Publishing is atomic, create-once, and
terminal-marker guarded.

## 15. Test and adversarial proof matrix

### 15.1 Canonical identity and forks

- A root and every child remain pure linear replay chains.
- An unauthenticated/unreachable parent state cannot create a fork.
- A child cannot mutate or replace its parent history.
- Forged parent state, manifest, scheduler position, fork decision, or witness fails.
- Multi-generation depth and recursive ancestry re-derive exactly.
- `logical_step`/scenario time never substitutes for run/scheduler identity.
- Wall-clock or worker completion order does not alter admission.

### 15.2 Generation and admission

- Identical frozen inputs generate byte-identical candidates.
- Candidate enumeration order and registry insertion order do not affect output.
- Exact equivalence keys cannot be admitted twice in one or later epochs.
- Cross-experiment candidate reuse fails.
- Candidate-order manipulation fails to change the sealed selection.
- Policy or budget changes produce distinct manifest identity.
- Hard run, depth, parent, category, call, token, cost, and horizon limits refuse the
  next candidate before exceeding the bound.
- Reserve rules and no-borrow behavior are exact.
- Unsupported categories remain unsupported rather than falling back.

### 15.3 Epochs and recovery

- Parallel and sequential previews have identical admission bytes.
- A partial crash resumes without regenerating or duplicating admissions.
- Duplicate worker completion cannot consume another slot or overwrite evidence.
- Conflicting completion is quarantined.
- Budget-exhaustion races cannot exceed the sealed allocation.
- An unclosed/aborted epoch cannot feed the next epoch.
- Restart does not lose recorded failure/incomplete dispositions.

### 15.4 Graph

- Incomplete, invalid, unverified, unsupported, corrected-incomplete, and quarantined
  runs are excluded with reasons.
- Deleting the graph has no effect on canonical replay.
- Rebuilding from identical evidence is byte-identical.
- A stale projection input digest fails verification.
- Orphan, reversed, cross-run, or malformed graph edges fail.
- Similar visible states with different hidden histories remain distinct.
- Derived convergence never merges ancestry or becomes a fork parent.
- Actor-safe node/edge/label/tooltip/accessibility/debug payloads contain no
  privileged or hidden fields.
- Graph construction is read-only and output cannot alias canonical roots.

### 15.5 Compatibility

- Existing spatial scheduler, fork, Society Seed, Butterfly calibration, replay,
  trajectory projection, training readiness, result correction, visualization, and
  zero-model replay tests remain green.
- Existing artifacts and golden pins remain byte-identical.
- Unknown record versions fail closed.
- Branch count never becomes effective sample size without existing grouping rules.

## 16. Scaling proof

Slice D creates a deterministic scripted benchmark with no model contact. The target
is at least 10,000 synthetic canonical trajectory bundles and 100,000 derived graph
nodes. If the implementation preflight proves that materializing those complete
bundles would violate bounded CI resources, the source must instead:

1. establish and record the safe in-process ceiling;
2. run the largest safe complete evidence-backed benchmark;
3. separately exercise a deterministic streaming projection fixture whose committed
   cardinality is at least 100,000 nodes;
4. explain why this is equivalent for the graph path and not represent it as 10,000
   scientifically completed experiments.

The proof includes multiple depths, repeated content-addressed states, independent
ancestries, failure/incomplete exclusions, deterministic rebuilds, streaming or
bounded-memory processing, and a check that graph construction creates no canonical
record copies.

Correctness tests use bounded fixtures in normal CI. The larger benchmark is an
explicit reproducible command and evidence report. Peak resident memory, CPU time,
I/O, and output size are observations, not brittle pass/fail wall-clock thresholds.
Any claimed memory bound must name the measurement method and platform.

## 17. Compatibility and migration plan

- No changes to `SchedulerRun`, `SchedulerState`, `SchedulerManifest`, `WorldLine`,
  `ForkDecision`, `ForkInitialization`, `WorldLineGenesis`, or canonical state ids.
- No change to current run evidence bytes or replay entry points.
- Search records reference existing identities through strict adapters.
- V1 supports the exact spatial scripted families whose parent chain, fork witness,
  evidence bundle, and replay can be re-derived. Other families receive explicit
  `unsupported_family`/`missing_binding` reasons.
- Historical evidence is never rewritten to become graphable.
- A later family adapter is additive, versioned, tested, and audited.
- The derived representation can be replaced or indexed differently if the same
  projection contract and canonical references are preserved.
- Existing partition, correction, report, and Council records remain authoritative.

## 18. Delivery slices and authorization gates

### Slice A — this design contract

Deliver this document with repository reconnaissance and documentation validation.
Route its exact clean commit to the independent Council. Do not implement before the
required plain design verdict and authorized integration event.

### Slice B — canonical fork-search foundation

After Slice A approval, implement the budget, policy, search manifest, epoch,
candidate generation, admission, pre-realization execution binding,
execution-disposition, closure, scripted adapter, recovery, CLI, and tests. Only
deterministic scripted branches are eligible. Route as a fresh implementation source.

### Slice C — derived experience graph

After Slice B approval, implement the projection, deterministic streams, validation,
trace, safe exports, CLI, and tests. Route independently.

### Slice D — scaling proof

After Slice C approval, implement and execute the deterministic benchmark, publish
the evidence-backed report, and route any claim through the established audit path.

Each slice requires an exact source commit, clean candidate tree, focused and full
tests, independent audit, additive revisions for findings, plain required verdict,
authorized integration, chain-health check, and post-integration validation. A
failed or operationally interrupted audit remains in lineage and is not approval.

## 19. Explicit exclusions and future gates

This design does not authorize:

- live-model or Ollama execution;
- weight training, LoRA, preference learning, RL, or learned branch selection;
- behavioral or normative labels;
- hidden-suite access or using hidden results for selection;
- causal claims from graph adjacency or one branch;
- motive inference;
- a single greater-good score or morality oracle;
- real-world population targeting, prediction, or automatic intervention;
- an external distributed graph service;
- canonical merging of histories;
- execution of every possible action;
- arbitrary plugins, scripts, remote assets, or public execution endpoints.

These require their existing or separately audited authorization gates. Planning a
category is not authorization to produce or execute it.

## 20. Completion criteria for the program

The hybrid scaling foundation is complete only after all four slices are approved
and integrated and the evidence shows that:

- canonical executions remain immutable linear histories;
- forks are independent runs authenticated from exact reachable parent states;
- the branch selector is deterministic, bounded, recoverable, and order-independent;
- hard limits refuse before overrun;
- repeated candidates cannot consume budget twice;
- the experience graph is deterministic, evidence-traceable, deletable, and
  rebuildable;
- visually similar histories do not collapse;
- actor-safe views do not leak privileged data;
- the scaling proof meets its declared bounded profile;
- existing replay, scientific-integrity, and Council contracts remain intact;
- final commits, tests, benchmark evidence, verdicts, integrations, and limitations
  are reported exactly.

The smallest scientifically valuable experiment enabled afterward is a bounded,
preregistered scripted Butterfly search: start from one replay-authenticated spatial
state, admit a small fixed set of registered one-factor interventions and replication
branches under an explicit budget, execute them as independent witnessed forks,
rebuild the graph, and compare first divergence and terminal outcomes without making
a causal, alignment, or learning claim.
