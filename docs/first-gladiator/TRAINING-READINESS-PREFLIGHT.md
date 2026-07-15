# T0-A Training Readiness Preflight — design source

Status: **DESIGN ONLY**. This source authorizes no implementation, dataset
admission, label creation, model inference, model contact, weight fitting, or
scientific claim. Implementation requires a separately routed source after this
design receives the applicable plain Council verdict.

Proposed revision: `first-gladiator-t0a-learning-preflight-design-002`.

Revision 002 preserves the blocked revision-001 lineage and closes its two
independently reproduced design defects: standalone run exports are no longer
treated as a corpus partition/export, and report publication no longer accepts
arbitrary output filenames or any path inside a Git repository or protected
input tree.

## 1. Purpose

The integrated training-readiness vertical proves that one completed modern
vignette can be projected and exported through
`export_training_data_from_run(...)`. It does not say how much of the historical
corpus satisfies that contract.

This preflight answers the next learning-first question:

> Of the artifacts Agent Coliseum has produced, how many are uniquely identified,
> complete, replay-verifiable, projectable, admitted, leakage-safe,
> partitionable, exportable, and capable of supporting a factual learner task?

The result is a deterministic, content-addressed health report and an actor-safe
example loader. It is a derived index over canonical evidence, never a new source
of experiment truth.

This source reuses, without weakening:

- vignette replay: `sweep.verify_run_replay`;
- spatial/live validation and provider-free replay:
  `visualization.load_validated_run` / `visualization.verify_replay`;
- vignette projection: `training.trajectory_projection.project_trajectory`;
- scripted-spatial projection:
  `training.spatial_trajectory_projection.project_spatial_trajectory`;
- admission: `training_admission.admit_runs`;
- group partition and independent leakage lint: `partition.py`;
- standalone governed actor export:
  `training.pipeline.export_training_data_from_run` (diagnostic capability only;
  never pooled or treated as a corpus-bound export);
- actor/privileged isolation: `training.observation.assert_no_privileged_leak`.

No T0-B labels and no model weights are introduced.

## 2. Preliminary read-only reconnaissance

These observations are a non-authoritative snapshot at code commit
`a155defa259cc16201cc89167ddb33ba8e303d27`. The implementation must recompute
them; tests must not hard-code the mutable historical-corpus counts.

| Observation | Current value |
|---|---:|
| discovered run directories | 646 |
| vignette-shaped directories | 642 |
| spatial/society/live directories | 4 |
| distinct non-empty `run_id` values | 526 |
| unambiguous singleton `run_id` values | 406 |
| duplicate identity groups | 120 |
| artifacts in duplicate identity groups | 240 |
| duplicate groups whose directory bytes conflict | 120 |
| admitted before replay under existing vignette admission v1 | 153 |
| rejected before replay | 493 |
| replay-verified among those 153, provider-free | 46 |
| raw vignette projections accepted | 242 |
| unambiguous + admitted + replay-valid vignette projections | 2 |
| current standalone governed actor exports over those candidates | 1 |
| actor decision examples in that standalone export | 3 |
| effective units in that standalone export | 1 |
| current corpus-bound governed actor exports | 0 |

The one currently **standalone-exportable** run is
`corrupt_king.v0_province.scripted%3Amerciful.s2.f4bc53ba49782a83`.
Its actor export has manifest
`fd072aa573025dde223a44f15339c67a47df4bcd3f3cfe29d59f3b30924d6022`,
dataset commitment
`138a5ee161694263e6f24f5b20722fbb1a8919f07215add866703dd94e0cfdf7`,
three factual action examples, one effective unit, and a byte-identical replay.
This is availability evidence for the run-level export contract, not a
corpus-bound training export and not evidence that a useful learner can
generalize. The existing exporter recomputes a partition over its singleton
input. Its manifest and commitment MUST NOT be pooled with another singleton
export or reported as corpus-exportable.

The second unambiguous candidate is a deterministic mock-LLM run. It projects and
replays, but the current export binding rejects its `.a1` attempt directory because
the bound source `run_id` is absent from the dataset descriptor's report-id units.
The report records that first blocker; it does not repair or route around it.

The spatial projector accepts the two scripted Society Seed captures. There is no
governed spatial `DatasetExportManifest` path yet, so they are projectable but not
exportable. The old six-position spatial capture is schema 0.1 and correctly fails
the 0.2/0.3 projector because it lacks activation evidence.

The captured Live Persona directory is a required negative control. Its evidence
is valid and its seven-file replay is provider-free, but its authenticated display
state is incomplete, nonclaimable, governance-not-bound, and report-unverified.
The generic spatial projector currently can parse its spatial core; doing so would
misrepresent a live policy as `deterministic_script` and its interrupted tail as
`natural_terminal`. The preflight MUST refuse that route. Live trajectories remain
unsupported until a dedicated projector binds persona policy, captures, failure
termination, result status, and correction lineage.

## 3. Report identity and authority boundary

Add one derived content record:

- domain: `trs.training_readiness_report.v1`;
- id field: `training_readiness_report_id`;
- schema version: `1`;
- reporter version: `t0a-preflight.v1`.

The record contains only deterministic summaries, stable root aliases, relative
artifact locators, hashes, status values, reason codes, record identities, and
counts. It contains no wall-clock timestamp, absolute path, raw completion,
private observation, privileged state, evaluator-only content, hidden-suite
content, or council credential.

The report may say that a gate passed according to an integrated verifier. It may
not:

- make an incomplete result complete or claimable;
- turn viewer admission into training admission;
- treat a replay-valid run as scientifically approved;
- treat a projected record as an admitted example;
- treat an admitted row as an independent experimental unit;
- infer governance approval from code integration;
- infer quarantine clearance from file presence;
- infer license permission where no license evidence exists;
- infer causation, alignment, intelligence, or learning.

Canonical evidence stays in its run directory. The report binds but never copies
or mutates it.

## 4. Inputs and discovery

The report builder accepts:

- one or more explicitly named roots, each `(root_id, filesystem_path)`;
- scenario registry path;
- scenario config directory;
- held-out scenario ids and hashes;
- preregistered exclusions;
- replay mode, which is `required` for the governed report;
- actor view, fixed to `actor` in v1.

Only `root_id` and root-relative POSIX locators enter report identity. Absolute host
paths are runtime locators and never enter the content record.

Discovery recursively identifies directories containing `run.json`, in sorted
`(root_id, relative_run_dir)` order. It must:

- reject duplicate root ids;
- reject roots that overlap or alias each other;
- reject symlink roots, symlink run directories, and symlink evidence files;
- enforce bounded file count, file size, JSONL row count, JSON depth, and string
  limits before parsing;
- reject traversal, absolute artifact references, and path escapes;
- record unreadable/unknown artifacts as failures rather than crash or omit them;
- hash the complete regular-file bundle by sorted relative filename + file bytes;
- never write beneath an input root, the code repository, any other Git
  repository, the registry/config trees, or the canonical `logs/` tree.

Report construction is pure and returns a content record plus an opaque runtime
publication context containing the resolved input/protected paths (the runtime
context is excluded from report identity and serialization). The CLI defaults to
one selected serialization (`json` or `markdown`) on stdout. It accepts no
arbitrary output filename. Stdout mode and `--output-root` mode are mutually
exclusive.

An optional `--output-root` publishes both fixed filenames under a newly created,
content-addressed directory:

```text
<output-root>/<training_readiness_report_id>/report.json
<output-root>/<training_readiness_report_id>/report.md
<output-root>/<training_readiness_report_id>/COMPLETE
```

Before creating anything, the publisher requires the output root to be an existing
directory, checks every component with `lstat`, and then resolves it only after
proving that no component is a symlink. It refuses a root equal to,
inside, or containing any input root, canonical run/log root, registry path,
configuration directory, code-repository root, or any Git repository (a `.git`
file or directory in any ancestor is sufficient). This general Git-repository
refusal protects the separate Council tree without coupling the reporter to a
Council path. The final report-id directory MUST NOT exist; publication never
overwrites or reuses it. Temporary files are created exclusively inside that new
directory, each file is flushed and atomically renamed to its fixed distinct name,
and the `COMPLETE` marker binding both output hashes is published last. A reader
ignores a directory without the terminal marker. `report.json` and `report.md`
cannot alias because callers cannot name them. A report is derived documentation,
not a run artifact.

## 5. Artifact-family dispatch

Dispatch is closed and versioned. v1 recognizes:

1. `vignette.v1`: object `run.json`, `record_type == "run"`, and a
   `decisions.jsonl` stream;
2. `spatial.scripted.v1`: a supported spatial run plus the complete six-file
   spatial evidence set and no live report;
3. `spatial.live_persona.v1`: a spatial core plus a strictly validated
   `live_report.json`;
4. `unknown`: everything else.

The live-persona discriminator has precedence over generic scripted-spatial
projection. A live capture can never fall through to the deterministic-script
projector.

Schema recognition and training support are different fields. An artifact may be
structurally readable and replayable while its projector or export path is
unsupported.

## 6. Status vocabulary

Every stage is explicit:

- `pass`: the named integrated gate ran and passed;
- `fail`: the gate ran and rejected the artifact;
- `unsupported`: the artifact family has no authorized implementation for the
  stage;
- `unknown`: the source evidence cannot establish the fact;
- `not_evaluated`: a prerequisite failed, so running this gate would be misleading.

Each non-pass carries one or more stable machine reason codes plus bounded display
detail. Exception text alone is never the reason taxonomy.

Important examples include:

- `unreadable_json`, `run_json_not_object`, `unknown_schema`;
- `ambiguous_run_id`, `duplicate_identity_content_conflict`;
- `incomplete_run`, `mechanical_closure_unverified`,
  `result_completion_unknown`;
- `config_drift`, `decision_bytes_differ`, `spatial_replay_failed`;
- `legacy_regime_identity_unavailable`, `unsupported_interaction_mode`,
  `spatial_schema_pre_activation`, `live_projector_unavailable`;
- integrated admission-v1 rejection codes;
- `registry_scenario_missing`, `partition_leakage`, `held_out`;
- `attempt_report_id_binding_mismatch`, `spatial_export_unavailable`,
  `corpus_export_manifest_unavailable`, `non_corpus_bound_export`;
- `governance_linkage_unavailable`, `quarantine_state_unknown`,
  `license_permission_deferred`, `correction_lineage_unavailable`;
- `target_field_missing`, `target_degenerate`, `effective_n_insufficient`.

## 7. Denominator ladder

The report publishes two views for every stage:

1. **raw capability** — how many artifacts pass this gate independently;
2. **cumulative eligibility** — how many pass this gate and every earlier required
   gate in the ladder.

This prevents a broad projector count from being mistaken for a trainable
denominator after identity or replay failures.

| Stage | Required question |
|---|---|
| `discovered` | How many artifact directories were found? |
| `uniquely_identified` | Is the `run_id` non-empty and present in exactly one discovered directory? |
| `structurally_readable` | Does bounded validation recognize the artifact family/schema? |
| `complete` | Does family-specific evidence establish a valid execution terminal? |
| `replay_verified` | Does the applicable provider-free verifier reproduce the evidence? |
| `projectable` | Can an authorized projector derive truthful training records? |
| `admitted` | Does the integrated admission gate accept it under the declared held-out/exclusion inputs? |
| `partitionable` | Can the artifact enter a deterministic group-aware split with leakage lint passing? |
| `exportable` | Does a governed actor export bind the exact corpus-wide descriptor, partition, and commitment? |
| `task_bearing` | Can one or more factual targets be constructed without privileged or post-outcome leakage? |
| `effective_units` | How many independent units remain after retry/identity/group collapse? |

Percentages, when rendered, always show `numerator / denominator` and name the
denominator. No single “training readiness percentage” is produced.

### 7.1 Completion is not approval

For vignettes, `status == completed` establishes execution completion. For modern
spatial evidence, a strictly validated closure and exclusive stop establish
mechanical execution completion. For Live Persona, the strictly validated live
report controls `complete` and `status`; its negative values veto projection and
admission. A mechanically closed chain never overrides an incomplete result.

`behavioral_departure_claimable`, report authentication, result approval,
governance binding, quarantine, and correction lineage are reported separately.
Unknown is never promoted to pass.

## 8. Identity and duplicate handling

`run_id` is descriptive identity; exact evidence is the artifact-bundle hash.
Group all discovered artifacts by `run_id` before admission.

- one path: identity is unambiguous;
- multiple paths with identical bundle hashes: still ambiguous under current
  admission v1 and rejected, while reported as `duplicate_identity_exact_copy`;
- multiple paths with different bundle hashes: reject every member and report
  `duplicate_identity_content_conflict`.

The reporter does not select a winner, apply last-row-wins, delete duplicates,
or reinterpret a conflict as a retry. A future repair/canonical-attempt source must
be separately designed and audited.

## 9. Replay policy

All governed readiness numbers require replay.

- vignette LLM runs use captured completions through `verify_run_replay`; no live
  provider call is permitted;
- scripted vignettes re-execute locally;
- modern spatial and live evidence use the integrated visualization validation and
  provider-free replay dispatch;
- pre-0.2 spatial evidence is unsupported, not approximated;
- a config/run-id drift is a replay failure even if decision bytes might otherwise
  match;
- a decision-byte mismatch is a distinct failure.

The implementation tests install a backend/model-contact tripwire. Any attempt to
construct a live provider or open a non-loopback/network connection fails the
preflight. The production preflight has no option that permits live contact.

## 10. Projection and admission order

An artifact is cumulatively projectable only after unambiguous identity,
structural validation, completion, and replay pass.

- completed vignette: use `project_trajectory`;
- completed scripted spatial: use `project_spatial_trajectory` for structural
  capability reporting only;
- any live persona: `live_projector_unavailable` in v1, even if the spatial core is
  parseable;
- unsupported schemas/modes: refuse without fabrication.

Admission reuses `admit_runs` at corpus scope so ambiguous identities are rejected
together. v1 admission currently supports vignette records only. Spatial/live
admission is `unsupported`, not failed-by-invented-vignette-fields.

Replay status remains its own stage even though a later admission call may also
require it. The report records the exact admission criteria evaluated and every
deferred criterion from `TrainingAdmissionRecord`.

## 11. Partition and leakage

Partitioning runs exactly once on the complete sorted set of cumulatively admitted
artifacts. It reuses the scenario registry, exact-content deduplication,
family/control lineage components, deterministic dataset-version-bound assignment,
and independent leakage lint. The resulting descriptor, commitment, full
partition manifest, held-out inputs, and exclusion inputs form the one
`corpus_partition_binding` for this report. No downstream export or example may
recompute a partition from a subset.

Report:

- partition group id and split per admitted artifact;
- exact duplicate clusters;
- family/control lineage groups;
- leakage-lint result and violations;
- the known absence of semantic near-duplicate detection;
- held-out and exclusion refusal;
- effective-unit count after retry collapse.

No row-level random split is permitted. A missing registry scenario or conflicting
scenario hash is a failure, not a fallback split.

The report checks every export candidate against the exact corpus binding. A
future corpus-bound export entry point must consume that binding directly and
return a manifest/descriptor bundle whose dataset commitment, full partition,
held-out/exclusion inputs, source membership, group, and split all match it.
Equality discovered after independently recomputing a partition is not a binding
and cannot promote a standalone manifest, even for an accidentally identical
singleton corpus. A descriptor generated by the existing per-run exporter is
always `non_corpus_bound_export`; a mismatch is reported, never repaired by copying
the report's split into that manifest.

## 12. Governed export and actor-safe examples

The existing `export_training_data_from_run(..., view_kind="actor", verify=True)`
is a **standalone run-level capability probe only**. It recomputes a singleton
partition inside `build_dataset([run_dir], ...)`; therefore the preflight MUST NOT
pool its manifests, use their split fields in corpus statistics, call them
cumulatively exportable, or pass them to a learner as one dataset. Standalone
success/refusal counts appear only in a separately named raw-capability section.

Revision 002 does not invent a second export manifest or weaken the integrated
one. Corpus-bound governed export is `unsupported` with
`corpus_export_manifest_unavailable` until a separately designed batch export can
consume the exact `corpus_partition_binding` and bind it into every manifest and
example. Consequently, the current historical report is expected to have zero
cumulative `exportable` and `task_bearing` artifacts even though a standalone
run-level export succeeds. That honest zero is preferable to a leakage-prone pool.

Add a small read-only loader over one successful standalone actor export for
schema/feature inspection only. The loader accepts exactly one manifest,
descriptor, and projection bundle. It verifies their integrated bindings and
refuses a collection, concatenation, a foreign report partition, or any request to
reinterpret the example as corpus-bound. Its result is labeled
`standalone_non_corpus_training_example`; it demonstrates task shape but does not
populate the cumulative learner denominator. A later batch-export source must add
a corpus loader that requires the exact corpus-bound manifest/report commitment.

One standalone example per actor decision contains only:

- content-addressed example id;
- source evidence id and trajectory manifest id;
- dataset export manifest id and commitment;
- split and partition group id;
- decision sequence position;
- actor observation id and actor-safe structured content;
- legal-action-set id, ordered action ids, and mask;
- factual selected action;
- factual termination kind;
- explicit availability wrappers already present in the records.

The loader excludes privileged observation records, privileged DecisionRecords,
raw completions, evaluator fields, result labels, future observations, provenance
identifiers as semantic features, and post-outcome fields. IDs remain grouping and
audit metadata, not suggested model features.

Every example is rechecked with `assert_no_privileged_leak`. Input record objects
are not mutated. JSON examples are emitted in deterministic sequence order. No
example may acquire a corpus split from the readiness report unless a future
corpus-bound export manifest authenticates that exact binding.

## 13. Dataset statistics

Corpus learner statistics are computed only over successful **corpus-bound** actor
exports and reported by split, scenario family, agent regime, and effective unit
where available. In v1 these counts remain zero and unavailable rather than being
filled from standalone exports. A separate raw-capability appendix may report
standalone export/example shape, but never a pooled split or cumulative training
denominator:

- exported trajectories and factual decision examples;
- effective units and raw attempts;
- trajectory-length distribution;
- action vocabulary and action-frequency distribution;
- legal-action-set cardinality distribution;
- termination-kind distribution;
- missing/unavailable-field rates;
- scenario/family/regime balance;
- duplicate and near-duplicate status;
- replay, admission, partition, and leakage counts;
- failure/rejection frequency by stable reason code.

No private or privileged value is included in a statistic available to an actor
consumer. Counts with zero support remain zero; missing is not imputed.

## 14. Task availability

Task availability is a vector, never a single readiness score. Every task records:

- `data_status`: `constructible`, `degenerate`, `unavailable`, or `gated`;
- factual target definition;
- feature cutoff;
- eligible example count and effective-unit count;
- target coverage and class/variance support;
- missing prerequisites;
- authorization status.

Initial factual tasks:

- next-action classification;
- legal-action-set prediction;
- destination prediction;
- termination prediction;
- next-observation prediction;
- first-divergence prediction where authenticated matched branches exist.

Until a corpus-bound actor export exists, these tasks may be reported as
structurally recognizable from the standalone example shape, but their corpus
`data_status` remains `unavailable` with zero eligible examples. Standalone
examples never make a corpus task `constructible`.

Preference learning and normative behavioral labels are `gated:T0-B`. Any fitted
predictor, behavior cloning, LoRA, preference model, RL, or other weight-changing
operation remains `gated:G-WEIGHTS` unless an exact later Council interpretation
authorizes it. A factual task may be constructible while training it is gated.

A task with one effective unit or a constant target is reported as degenerate for
generalization, not “ready to train.”

## 15. Governance, quarantine, corrections, and license

The code repository does not infer Council state by scanning the separate wiki
repository. v1 records:

- governance linkage supplied by authenticated run evidence, else `unknown` or
  `not_bound`;
- quarantine supplied by an integrated admission/registry source, else `unknown`;
- correction lineage supplied by authenticated result-handoff records, else
  `unavailable`;
- training-use license evidence, else the integrated admission criterion remains
  deferred.

No absence becomes approval. A later cross-repository governance attestation must
be a separate design; this source does not couple training code to a dirty Council
worktree.

## 16. Public API and CLI

Proposed module:
`coliseum.textlab.training.readiness`.

Proposed pure entry points:

```text
build_training_readiness_report(
    roots,
    *,
    registry_path,
    config_dir,
    held_out_scenarios=(),
    held_out_hashes=(),
    exclusions=(),
) -> (TrainingReadinessReport, TrainingReadinessRuntimeContext)

iter_actor_examples(export_bundle) -> iterator[dict]

render_training_readiness_markdown(report) -> str

publish_training_readiness_report(
    report,
    runtime_context,
    *,
    output_root,
) -> path
```

`iter_actor_examples` accepts exactly one standalone export bundle in v1 and
labels every result non-corpus-bound. `publish_training_readiness_report` accepts a
directory root only; it derives the report-id directory and all filenames. The
runtime context is produced only by the builder and necessarily carries every
resolved discovery root, registry/config input, canonical log root, and the code
repository root. The publisher augments it by detecting any `.git` ancestor; a
caller cannot make publication less restrictive by supplying a shorter protected
root list.

Proposed CLI:

```text
python3 -m coliseum.textlab.training.readiness \
  --run-root vignettes=logs/runs \
  --run-root spatial=logs/spatial-runs \
  --run-root society=logs/society-runs \
  --run-root live=logs/live-persona-runs \
  --registry configs/registry/scenarios.yaml \
  --config-dir configs/scenarios \
  --format json
```

`--format json|markdown` selects the one stdout representation. An optional
`--output-root /external/derived/training-readiness` publishes both fixed
representations plus the terminal marker. `--json-out`, `--markdown-out`, and any
arbitrary output-filename option do not exist. Replay is mandatory; there is no
`--no-verify` production switch.

## 17. Determinism and commitments

The report commitment binds:

- schema/reporter version;
- root aliases;
- sorted artifact refs and complete bundle hashes;
- registry and config-set commitments;
- held-out/exclusion inputs;
- every stage status and reason code;
- partition and task-availability summaries;
- the corpus partition binding, standalone actor-export manifest ids and dataset
  commitments (explicitly marked non-corpus-bound), and any future corpus-bound
  export ids;
- statistics and recorded limitations.

It excludes absolute paths, process ids, temp paths, elapsed time, wall-clock time,
and Markdown rendering. Same evidence bytes + same declared inputs + same reporter
version produce the same JSON and id.

## 18. Required implementation tests

### Discovery and identity

- stable ordering across root/input order;
- duplicate root ids and overlapping roots refused;
- unreadable/non-object/unknown schemas reported, not omitted;
- duplicate `run_id` exact copies and conflicting copies both fail identity;
- no last-row-wins or automatic canonical attempt selection;
- symlink and path-escape probes fail closed;
- bounded-file and oversized-JSON/JSONL probes fail closed.

### Completion and negative claims

- incomplete vignette cannot pass completion;
- incomplete Live Persona remains incomplete/nonclaimable;
- generic spatial projection is never called for a live capture;
- a live capture cannot become `natural_terminal` or
  `deterministic_script` through fallback dispatch;
- missing result/governance/quarantine/correction evidence remains unknown;
- a mechanically closed replay does not imply scientific approval.

### Replay

- scripted and captured-LLM vignette replays are provider-free;
- modern scripted spatial and captured Live Persona replays are provider-free;
- provider/model/network tripwire remains at zero calls;
- config drift and decision-byte drift get distinct reason codes;
- pre-activation spatial schema is unsupported;
- source hashes are unchanged before/after report generation.

### Projection, admission, partition, export

- every cumulative stage requires all prior stages;
- raw and cumulative counts are both correct;
- integrated admission reasons are preserved;
- held-out id/hash and preregistered exclusions fail closed;
- missing registry, scenario-hash conflict, and leakage straddle fail closed;
- a sibling/control pair that co-assigns corpus-wide cannot straddle through
  separately recomputed singleton exports;
- the corpus partition is computed once and its exact descriptor/commitment is
  revalidated by every corpus-bound consumer;
- standalone manifests with singleton commitments are reported as
  `non_corpus_bound_export` and cannot be pooled or passed to the corpus loader;
- attempt/report-id export binding failure is reported, not repaired;
- no spatial run is called exportable before a spatial export manifest exists;
- the current successful standalone vignette actor export remains byte-identical
  and separately labeled; cumulative corpus exportability remains zero until a
  corpus-bound manifest exists.

### Actor examples and tasks

- included examples are exactly the manifest's actor-side decision records;
- privileged ids/content, raw completions, evaluator fields, and future state are
  absent;
- malicious strings remain data and Markdown is escaped;
- example ids/order are deterministic;
- missing fields remain explicit availability wrappers;
- constant targets and one-effective-unit data are marked degenerate;
- T0-B and G-WEIGHTS tasks remain gated.

### Output safety and scale

- default is one selected representation on stdout/read-only;
- no arbitrary JSON/Markdown filename options exist;
- output inside or containing any input/canonical run root, registry, config tree,
  source repository, canonical logs tree, or any Git repository is refused;
- an output root with a symlink in any existing parent component is refused;
- path aliases and non-existent-parent escapes are resolved and refused before
  creation;
- fixed `report.json` and `report.md` names are distinct and cannot alias;
- an existing report-id directory is refused without overwrite, even when bytes
  are identical;
- interruption before `COMPLETE` leaves an unreadable incomplete publication;
- atomic outputs and the terminal marker do not overwrite registry, config,
  source, Council, run, or canonical evidence files;
- report generation does not mutate caller objects;
- a synthetic 10,000-run corpus stays bounded and deterministic;
- cached validation is keyed by complete artifact bundle hash and reporter version,
  never only by run id or stale cursor.

## 19. Acceptance and evidence sequence

Implementation is complete only after:

1. focused readiness/security tests pass;
2. all existing training, replay, spatial, live, and visualization tests pass;
3. full repository suite passes;
4. an independent source audit reaches plain GO;
5. authorized integration is recorded;
6. the integrated tool runs over the historical corpus with zero provider calls;
7. JSON and Markdown reports are published outside every Git repository as derived
   evidence only if separately authorized; committing or ingesting them later
   requires a separately audited source;
8. any numerical/scientific interpretation receives the applicable result audit.

The first historical report must publish its complete denominator ladder and exact
rejection reasons. It must not summarize the outcome as “646 runs ready.”

## 20. Explicitly deferred

- repairing duplicate/colliding historical identities;
- choosing canonical attempts;
- changing the existing export mode/attempt binding;
- a corpus-bound batch export manifest and pooled learner loader (standalone
  per-run export capability remains inspectable but non-poolable in v1);
- a live-persona training projector;
- a spatial governed export manifest;
- semantic near-duplicate detection;
- cross-repository governance attestation;
- normative target labels;
- fitted predictors or behavior cloning;
- any weight change;
- experience-graph indexing;
- automatic branch execution;
- Kill-the-King experiments;
- 24-agent live inference;
- viewer visual-polish follow-ups.

Those become separate, evidence-driven slices. The immediate implementation goal is
to measure the corpus honestly and expose the smallest actor-safe factual examples
already supported.
