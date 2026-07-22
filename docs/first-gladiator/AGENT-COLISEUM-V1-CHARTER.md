# Agent Coliseum v1 — Gated Completion Charter

> **Status:** proposed repository design source, pending Council ratification
> through the single-use `first-gladiator-coliseum-v1-charter-*` request
> lineage initiated by `first-gladiator-coliseum-v1-charter-001`.
>
> This document grants no blanket execution authority. Integrating it adopts
> the release sequence and its gates only. Every live experiment still requires
> its own owner authorization, exact design identity, budget, and evidence root.

## 1. Purpose and binding state

This charter turns the Agent Coliseum v1 directive into an ordered release
program. It is not one implementation source and it does not collapse research,
instrument, kernel, frontend, or release review into a single approval.

The immutable Round 4 candidate is:

| Field | Value |
|---|---|
| Candidate | `4506fce78a495c0761a6b5ed5181c3909cc750a4` |
| Observed baseline suite at `4506fce` | 2,193 passed, 13 skipped |
| A-011 | GO, event `002158-cd263e97` |
| B-009 | BLOCKED, event `002157-c48a1587` |
| C-009 | BLOCKED, event `002151-a355a61c` |
| D-009 | GO, event `002153-6e1c5e4c` |
| E-009 | GO, event `002155-87cfc64b` |

The candidate remains historical evidence and must not be amended. Repairs are
made on a descendant commit. Any semantic change makes all earlier GOs
historical; no verdict transfers to changed bytes.

Claude remains the overall Director. For the owner-authorized Round 4 handoff,
the primary Codex agent may build on a separate descendant branch only when a
separate subagent independently audits the governing protocol and contributes
no implementation. Council publication and integration remain Claude-attributed
actions. No implementation contributor may perform or submit a fresh A–E
verdict. The fresh A–E reviewers remain independent and must bind the exact
frozen repair commit.

The required read-only protocol audit was performed on 2026-07-22 by separate
subagent `/root/protocol_audit`. It contributed no implementation. This
attribution is durable handoff metadata only; it is not a canonical Council
source verdict, because the Council schema records the source auditor role as
`codex` rather than individual subagent identity.

### 1.1 Pre-repair ratification sequence

Runtime repair work begins only after this exact sequence completes:

1. freeze a clean charter doc/metadata commit;
2. the Director publishes the next unused request ID in the
   `first-gladiator-coliseum-v1-charter-*` lineage with
   `live_experiment_allowed: false` and `human_approval_required: true`;
3. if that request is terminally blocked, preserve it as historical evidence,
   correct the finding on a descendant commit, and publish a new single-use
   successor request; no blocked request is required to become a GO;
4. an independent reviewer returns a plain GO bound to the exact latest
   charter doc/metadata commit;
5. the Director records integration of that GO-bound charter source;
6. create the runtime repair as a descendant of the integrated charter.

The unratified charter and runtime repair must not be combined into one commit.

## 2. MV0 — Round 4 closure and M8 sealing

### 2.1 Canonical finding union

Round 4 has exactly two admitted repair findings.

#### R4-C009-1 — contradictory terminal records

The implementation must load and validate the entire success manifest and the
entire tombstone ledger before execution setup, fast return, counting,
generation, terminal writes, completion calculation, or publication. It must
reject `success_keys ∩ tombstone_keys` unconditionally on every path, including
partial grids and grids with unresolved coordinates.

Both validated ledgers become immutable initial in-memory snapshots. A local
working accumulator, held under the same lock, adds every terminal outcome
created by the current call. Resume, counting, balance checks, and completion
use the combined initial-plus-new working state. They must never use stale
initial snapshots alone or independently reload ledger state mid-call.

Required regressions cover partial and full contradictions, unresolved
coordinates, replay-only and execution-backed paths, and duplicate, foreign,
or malformed tombstones. Contradictions must be rejected before setup or output.

#### R4-B009-1 — concurrent manifest lifecycle

Round 4 evidence demonstrated that two processes can read the same empty
manifest, execute the same effective unit, and separately append success and
tombstone outcomes for that unit. The conditional threshold for including a
lock in this repair is therefore met.

The implementation must acquire a manifest-scoped POSIX advisory lock before
any ledger pre-scan or load and retain it across validation, setup, execution,
terminal writes, balance checks, completion calculation, and return cleanup.
Lock identity derives from the canonical manifest target, including aliases and
symlinks. Contention and unavailable POSIX locking refuse the call before setup
or evidence mutation. The implementation must never remove, replace, age out,
or override another process's live lock.

Required process-level regressions prove that two calls for the same manifest
cannot overlap and that the non-holder performs no setup, call, or write;
distinct manifests remain independent; an exception releases only the holder's
kernel-managed lock; aliases resolve to one lock identity; unavailable locking
refuses execution; and no foreign lock is cleared.

### 2.2 Single repair boundary

The two findings are implemented once in one bounded repair. The critical order
is:

```text
canonicalize manifest identity
→ acquire non-blocking manifest lock
→ fully load and validate both ledgers
→ reject every success/tombstone intersection
→ derive one validated state snapshot
→ resolve replay or perform execution
→ persist terminal outcomes
→ calculate balance and completion
→ release only the held kernel lock
```

The changed-path allowlist and A–E coverage map must explicitly include every
new or changed source, test, and document. No unrelated architecture change is
admitted into this repair.

### 2.3 Repair verification and integration

Before freezing the repair commit, run:

1. focused contradiction, malformed-ledger, resume, and two-process tests;
2. one complete socket-capable `python3 -m pytest tests/ -q` invocation;
3. deterministic M7 regeneration and Phase-1 byte comparison;
4. replay identity checks with no model call;
5. registry lint and changed-path allowlist validation.

The complete suite must be one uninterrupted invocation, not a composite of
separate modules. Its newly observed exact pass/skip count is the repair
baseline and must be pinned in every fresh A–E request; the historical 2,193/13
observation is not presumed to remain the new count.

Freeze one clean repair commit. Publish fresh A–E requests using the next
canonical request IDs and 7,200-second deadlines. Each request must declare its
coverage and the union must cover every changed path and invariant. Integration
requires five plain GOs on that exact commit. A conditional or blocked verdict
requires a new repair commit and fresh applicable reviews.

### 2.4 M8 execution and result gate

Integration of the repair does not authorize M8 execution. A separate owner
event must bind all of the following before any run:

- the M8 design hash;
- the integrated implementation commit;
- the model digest;
- exactly 144 planned runs;
- the approved budget;
- the evidence root.

Only then may the frozen pack execute. Replay must run without a model call,
results must be regenerated from authenticated evidence, and evidence and claim
audits must finish before `RESULT_APPROVED`. Null, failed, and inconclusive
experiments are completed scientific outcomes when their evidence and audits
are valid.

The first approved overnight window contains only M8 capture, replay, and report
regeneration. Paraphrase, delay, and cross-model work require separate prior
registrations, experiment identities, budgets, and live authorizations.

## 3. MV1–MV5 — Measurement Validity Program

Each MV stage is a separate Council source. Sample sizes and multiplicity rules
are frozen in that stage's audited design using evidence available before the
stage. They must never be guessed or changed after outcomes are visible.

### MV1 — Control Panel

Implement known-answer negative, positive, swap-null, cancellation,
adversarial-evidence, and broken-instrument fixtures. Every fixture must detect
the intended defect or preserve the intended null, with frozen expected
outcomes and explicit failure meanings. Any mismatch blocks release.

### MV2 — Construct Ledger

Add versioned construct records separating operational definition,
observables, metrics, supported claims, unsupported claims, rival explanations,
falsification criteria, and discriminating studies. Every analysis declares
`confirmatory`, `secondary`, or `exploratory` before execution.

### MV3 — Replication

Repeat M8 under a new independent execution identity with separately reviewed
sample and analysis plans.

### MV4 — Robustness

Separately preregister paraphrase, neutral-delay or event-distance, and
cross-model studies. Do not pool these studies with M8.

### MV5 — Recovery

Preregister corrective-experience, persistence, hysteresis, and
mechanism-discrimination studies. Mechanism claims remain unsupported until
competing explanations are experimentally separated.

## 4. MV6 — Scenario Kernel and Kaleidoscope

MV6 begins only after MV1–MV5 complete. Extract the smallest reusable kernel
from admitted behavior; do not replace the working runner speculatively.

The stable typed interfaces are:

- `ScenarioSpec` and `ScenarioCompiler`;
- `CompiledScenario`, containing canonical hash, rendered prompts, branch
  graph, coordinates, parser contract, observables, controls, and claim ceiling;
- `ExperimentDesign` and `ExecutionRequest`;
- `ModelAdapter` and `ExecutionBackend`;
- `EvidenceExporter` and `ReplayVerifier`;
- `Metric` and `VisualizationPlugin`;
- `ReplayBundle`, the validated frontend input.

The canonical data flow is:

```text
ScenarioSpec
→ deterministic compilation
→ frozen experiment coordinates
→ sequential model execution
→ success/tombstone evidence validation
→ replay without a model call
→ within-model metrics
→ authenticated ReplayBundle
→ derived frontend
```

Acceptance occurs in order:

1. Compile M8 and prove identity, prompts, coordinates, replay, and results
   equivalent to the frozen bespoke path.
2. Run a new betrayal-to-authority experiment without a bespoke runner.
3. Run the frozen water-bearer moral-conflict and control family through
   configuration only.
4. Require a third party to author a valid scenario without modifying kernel
   source.

The v1 Kaleidoscope fleet is the existing digest-pinned M6 fleet:

- `llama3.1:latest` at `46e0c10c…`;
- `qwen3:8b` at `500a1f06…`;
- `gemma3:latest` at `a2af6cc3…`.

M8's qwen2.5 regime remains separate unless a later audited design adds it.
Models execute sequentially. Effects are estimated within each model first;
cross-model summaries are secondary or exploratory unless explicitly
preregistered.

## 5. Frontend and release

Extend the existing vanilla JavaScript and SVG viewer; introduce no frontend
framework.

- **Replay browser:** experiment, scenario, model, and condition selection;
  event timeline; terminal action; replay/evidence status; claim classification.
- **Kaleidoscope graph:** shared roots, interventions, matched branches, model
  lanes, divergence, unresolved units, and tombstones.
- **Comparison dashboard:** per-model distributions, total variation,
  paired-change rate, uncertainty, controls, persistence/recovery, and analysis
  category.
- **Live view:** planned, completed, and tombstoned counts plus worker health;
  it must never represent scientific completion.
- **Static export:** authenticated replay-only bundles containing no model
  endpoint, credentials, hidden material, or private Council state. Public
  deployment is a separate authorization.

JavaScript may display authenticated derived values but must not recompute
canonical scientific results.

The release manifest binds source commit, evidence-package digests, result
events, control-panel status, kernel version, frontend bundle, and reproduction
instructions. Final A–H reviews must bind the same release commit and evidence
manifest before tagging `agent-coliseum-v1`.

## 6. Program-wide test and claim rules

- **M8 repair:** contradiction ordering, process ownership, no premature setup,
  durable outcomes, exact resume, replay, full suite, M7/Phase-1 preservation.
- **Measurement validity:** every known-answer fixture has a frozen outcome and
  explicit failure meaning; broken instruments and altered evidence are
  rejected.
- **Kernel:** canonical compilation, deterministic hashes, M8 bespoke
  equivalence, scenario isolation, configuration-only water-bearer execution,
  and third-party authoring.
- **Kaleidoscope:** regime separation, coordinate matching, no cross-model
  pooling, effective-unit accounting, resume, capture, and replay.
- **Frontend:** authenticated-source tracing, no scientific recomputation,
  accurate claim labels, clear live/replay distinction, and static-bundle
  leakage checks.
- **Release:** fresh-environment replay of one complete result, evidence
  regeneration, exact manifest verification, and A–H coverage union.

Frontend data is always downstream of authenticated evidence and never becomes
canonical. No training, weight modification, hidden-suite access, cloud
execution, automatic retries, or unapproved model update is included in this
charter.
