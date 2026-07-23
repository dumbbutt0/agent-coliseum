# M8 Phase-2 — Audit Coverage Map

**Candidate-local assembly plan. Not a canonical Council record and not a
verdict.** Authority rests entirely with the independent Codex verdicts bound to
the exact candidate commit. This document exists so the coverage *union* is
declared before the first request is published, per the Director mandate.

## Candidate identity

| Field | Value |
|---|---|
| Base commit | `ac693b532b4f9a3d108d32014ec0a0d5af6a2c1a` (Phase-1 audited: GO 001714 / 001719 / 001724) |
| Branch | `codex/first-gladiator-phase2-design` |
| Worktree | `/tmp/agent-coliseum-phase2` |
| Frozen design | `docs/first-gladiator/preregistrations/m8-phase2-live-order-sensitivity.md` |
| Design hash | `431871d3266a96999ef02d0d9eb77caba7e6b317135155d3161b1eecf396d533` (post-a-006 swap-invariance recompute; reconstructs from `planned_design` via `registry.design_hash` and the registry lint reports zero m8 issues; the registry entry is authoritative) |
| Candidate commit | *assigned at assembly; every request binds it exactly* |
| Changed-path allowlist | `docs/first-gladiator/M8-CHANGED-PATH-ALLOWLIST.json` (machine-checked by `tests/test_m8_coverage_conformance.py`) |

**Coverage completeness is now machine-enforced (audit e-002 finding 0 closure).**
The prior cycle's map missed four runtime/operator/executor surfaces that reached
the diff without declared ownership. The frozen allowlist enumerates every
tracked path this candidate changes against the base, and the conformance test
asserts `git diff --name-only <base> HEAD` equals it exactly — an undeclared
surface now fails closed before publication. The five coverage sections below own
the *audit dimensions*; the allowlist owns the *file set*, and the two together
mean no path can enter unaudited.

**The registry entry and the committed experiment manifest are authoritative for
the design hash; this map is not.** Hashes were issued and superseded across the
repair cycles (`eb715c65…` → `71aeb718…` → `869982d3…` during cycle-1;
`e889882e…` → `e30fd318…` at the cycle-4 decoder-regime freeze; then `e30fd318…`
→ `ce8eff3e…` at the owner a-005 distributional re-framing; then `ce8eff3e…`
→ `431871d3…` at the owner a-006 swap-invariance re-framing — the value above.
The a-006 recompute is complete: the null is re-framed across the prose surfaces
and `design_hash` reconstructs from `planned_design`, so the registry lint now
reports zero m8 issues).
This table previously carried an earlier one — a stale copy in a non-canonical
document, recorded here rather than silently corrected because it is the same
class of defect as cycle 1's blocking Finding 1: an artifact asserting a design
identity that disagrees with the frozen source.

**This candidate contains no result and no live evidence.** No model was
contacted at any point during its construction. It is a design-and-instrument
slice only.

## v1 Round 4 repair extension

The Agent Coliseum v1 charter was integrated as a design source at exact commit
`5708750ad9348d8975ce609c967f91c3ad41f443` after plain GO
`002173-0e1d9c15`; integration event `002174-b1735e94` grants no live-run
authority. The runtime descendant closes the complete Round 4 finding union:

| Finding | Invariant | Owned paths |
|---|---|---|
| R4-C009-1 | Under the manifest lock, fully load and validate success and tombstone ledgers once; refuse every intersection and every malformed, duplicate, or foreign tombstone before model construction, replay return, counting, generation, terminal writes, or completion; use immutable initial snapshots plus local current-call working state. | `coliseum/textlab/sweep.py`, `tests/test_m8_sweep_integrity.py`, `tests/test_autonomy_ollama_driver.py` |
| R4-B009-1 | Acquire a non-blocking manifest-identity POSIX advisory lock before any ledger access and hold it through setup, execution, terminal writes, balance/completion, and cleanup; contention or unavailable locking refuses before the sweep body; never delete or replace the persistent identity file; aliases coalesce and distinct manifests remain independent. | `coliseum/textlab/sweep.py`, `tests/test_m8_sweep_locking.py` |

The lock identity is the SHA-256 of the canonical absolute manifest target.
Persistent lock files live in one process-shared temporary lock directory so
locking precedes ledger access without adding files to the evidence tree.
Ownership is kernel-managed on the open descriptor; file presence or age never
grants ownership. Closing releases only that descriptor's lock, and the file is
not automatically removed.

### Round 5 independent findings and descendant closure

The first runtime repair commit `ec53d5884365a1425bd59bb6e61ecd77d636029d`
received A-013 GO (`002197-8b91170e`) but was blocked independently by B-010
(`002198-b2516f00`) and C-010 (`002199-f0f2ba35`). The A verdict is historical
after this descendant. D-010 and E-010 were not used to transfer approval.

| Finding | Descendant invariant | Owned paths |
|---|---|---|
| R5-B010-1 | The manifest-lock parent is the absolute host-shared POSIX `/tmp/agent-coliseum-manifest-locks-v1`, independent of `TMPDIR`, `TMP`, `TEMP`, and `tempfile.tempdir`; two independently started processes with distinct temporary-root settings still contend on one inode. Lock acquisition yields the canonical manifest target, and the locked body consumes an immutable copied spec carrying that exact target. | `coliseum/textlab/sweep.py`, `tests/test_m8_sweep_locking.py` |
| R5-C010-1 | One planned coordinate contributes at most one terminal outcome. Same-coordinate success/tombstone evidence is refused even when its regime keys differ; provider-free completion and counting consume the exact same uniquely anchored tombstone set and never pool ambiguous multi-regime successes. | `coliseum/textlab/sweep.py`, `tests/test_m8_sweep_integrity.py` |
| R5-C010-2 | After whole-fleet preflight, every planned tombstone must match the computed model/scenario regime before scenario execution or any terminal write. A mismatch is refused, never ignored or retried. | `coliseum/textlab/sweep.py`, `tests/test_m8_sweep_integrity.py` |
| R5-C010-3 | `tombstone_load` accepts only the closed `FAILURE_KINDS` vocabulary; unknown or ill-typed values raise `SchemaError` at the ledger boundary before setup, replay counting, or mutation. | `coliseum/textlab/sweep.py`, `tests/test_m8_sweep_integrity.py` |

The fixed lock namespace is deliberately not derived from a process-local
temporary-directory API. Failure to create or lock the absolute shared path is
a refusal. The persistent-file and non-blocking descriptor rules remain
unchanged. Normal-path regime validation resolves every configured
model/scenario context after fleet validation and before evidence-root creation;
provider-free completion remains available only for an unambiguous, fully
resolved terminal set.

### Round 7 downstream finding and descendant closure

The first requests for commit `7bbc40389cd1ceec142058fccee96005a6360967`
were canceled without verdict at events `002218-41a5c46a` through
`002222-970dc11c` because their hash-bound prose retained a stale suite count;
they transfer no approval. Corrected A-015/B-012/C-012/E-012 returned plain GO
at events `002241-8925e1b1`, `002242-7937d260`, `002243-8292c1ab`, and
`002247-8aef14bc`. D-012 returned `AUDIT_BLOCKED` at
`002246-5013094d`. Every verdict observed 2,213 passed and 13 skipped on the
exact clean commit. A separate read-only protocol reconstruction verified the
five request hashes, verdict bindings, event chain, cancellation states, and
the locked 4/5 integration state.

D-012 reproduced one downstream gap: `run_sweep` refused contradictory success
and tombstone ledgers, but replay attestation, order-report, and result-package
paths loaded only the success manifest. A complete 144-row fixture plus a valid
tombstone for an already-successful coordinate still emitted both a verdict and
a result package. Because the replay receipt did not bind the adjacent ledger
or its absence, creating that ledger after replay did not invalidate later
derivation.

| Finding | Descendant invariant | Owned paths |
|---|---|---|
| R7-D012-1 | `terminal_ledgers_load` is the shared snapshot boundary for sweep, provider-free replay, order-report, and result-package recomputation. It loads both ledgers and refuses key- or coordinate-level contradictions, duplicate terminal coordinates, malformed provenance, foreign planned coordinates, unknown failure kinds, and provider-free regime mismatch before replay, metrics, or package writes. | `coliseum/textlab/sweep.py`, `coliseum/textlab/cli.py`, `coliseum/textlab/result_package.py` |
| R7-D012-2 | Replay receipts bind the exact adjacent tombstone-ledger bytes or a canonical absent state. Order-report and package creation require that binding to match the current snapshot. Result package v2 carries the same identity, and package verification refuses later creation, removal, or mutation. | `coliseum/textlab/sweep.py`, `coliseum/textlab/result_package.py`, `tests/test_m8_operator_surface.py` |
| R7-D012-3 | Replay, order-report, package creation, and package verification hold the same non-blocking canonical-manifest advisory lock used by sweep across snapshot loading and their terminal output. The persistent lock file is still never automatically removed or replaced. | `coliseum/textlab/sweep.py`, `coliseum/textlab/cli.py`, `coliseum/textlab/result_package.py`, `tests/test_m8_sweep_locking.py` |

The replay CLI now requires an experiment id and verified registry bundle so a
foreign or regime-invalid tombstone cannot be accepted without the frozen
planned grid. Clean absent-ledger packs remain valid; a valid disjoint,
uniquely anchored tombstone remains valid terminal evidence at the shared
snapshot boundary. Dedicated regressions require every derived surface to
refuse the D-012 contradiction, require post-replay ledger creation to
invalidate derivation and package verification, and retain malformed,
foreign, unknown-kind, regime-mismatch, and clean controls. No analysis rule,
threshold, model regime, stopping rule, or claim ceiling changes in this slice.
Every Round 7 GO is historical after the descendant commit, which requires a
fresh five-section review before integration.

### Round 8 manifest-alias finding

The first descendant repair froze at
`6223baabcd3aaac108e1e875583efdb898608a33`. A-016 and C-013 returned plain GO
at events `002266-ffd6dac4` and `002268-9d7d34dc`; both become historical after
the next semantic descendant. B-013 returned `AUDIT_BLOCKED` at
`002267-6a81823d` after independently creating two hard-linked names for one
manifest inode. Because lock identity was derived from each canonical path,
the names selected different persistent lock files and both spawned processes
entered. Their adjacent tombstone paths also differed, so switching to an
inode-key lock alone would not define one terminal-ledger namespace. Unclaimed
D-013/E-013 were canceled as superseded at events `002269-dd697a6e` and
`002270-b0bfd6be`.

The bounded descendant refuses any existing resolved manifest whose link count
is not exactly one before selecting its path lock, and repeats the check after
lock acquisition before entering the lifecycle body. A missing manifest remains
a valid first-execution target; stable symlink aliases to an existing
single-link target still converge; distinct single-link manifests remain
independent; and persistent lock files are still never automatically removed.
A spawned-process regression gives both hard-linked names bounded bodies and
requires both to refuse before body entry or adjacent tombstone writes. This is
a fail-closed unsupported-alias rule, not a change to the frozen M8 design,
analysis, model, stopping rule, or claim ceiling.

The ordering change deliberately supersedes the earlier test claim that model
preflight precedes manifest validation. Ledger validation now comes first;
whole-fleet digest validation still occurs before any scenario execution or
terminal evidence write. The changed test asserts both halves explicitly.

The frozen repair commit is assigned only after focused tests, replay checks,
M7/Phase-1 preservation, registry lint, exact allowlist equality, and one
uninterrupted complete suite. Every A-011/B-009/C-009/D-009/E-009 verdict is
historical for the runtime descendant. Fresh next-ID A–E requests must bind one
exact clean repair commit, use 7,200-second deadlines, and return five plain GOs
before integration.

### Round 9 closure and execution-enablement successor

The final Round 9 repair commit
`4a46c60e41669a160fd9a13055e791a055e112c0` received five plain same-commit
GOs: C `002289-51064040`, A `002290-60d5ac97`, B `002291-5e1830ef`, E
`002294-9a7aa0b5`, and D `002295-01f843d5`. Their exact integrations are A
`002296-c5d20a5b`, B `002297-31bef759`, C `002298-c266ad9f`, D
`002299-af00756d`, and E `002300-1c19ff2b`. The uninterrupted source suite at
that commit observed **2,229 passed, 13 skipped**; focused M8 observed 434
passed; M7 regenerated 18/18 byte-identically; and the changed-path allowlist
matched exactly. No live model work occurred.

The successor described in
`docs/first-gladiator/M8-EXECUTION-AUTHORIZATION.md` is a separate source slice.
It closes the remaining transition between an integrated M8 implementation and
a bounded, owner-authorized execution:

| Slice invariant | Owned paths |
|---|---|
| The owner approval directly copies the published request identity and a closed execution envelope binding design, implementation, config, model digests, 144 planned outcomes, budget, evidence namespace, M7 prerequisites, same-commit source integrations, and initial/resume mode. Publication, append, and runner boundaries cross-check the copy. | `tools/council/schemas.py`, `tools/council/cli.py`, `tools/council/events.py`, `tools/council/publish.py`, `tools/council/codex_watch.py`, `tools/autonomy/runner.py` |
| The dedicated M8 roadmap task is bounded-runner addressable but remains ineligible for automatic selection; the separate request and owner approval are mandatory. | `configs/autonomy-roadmap.yaml`, `tools/autonomy/child_runner.py` |
| Provider-free replay, exact terminal census, report creation, and result-package v3 verification finish before parent evidence inventory. A post-write balance refusal retains its completed sweep result only long enough to validate and package the terminal evidence. A complete tombstoned pack becomes a canonical no-statistics inconclusive outcome; an incomplete or contradictory pack refuses. | `coliseum/textlab/sweep.py`, `tools/autonomy/drivers.py`, `coliseum/textlab/result_package.py` |
| Completion and result review bind one closed artifact record covering owner approval, request, both terminal ledgers, replay, report, package, census, and analysis status. | `tools/council/schemas.py`, `tools/autonomy/runner.py`, `coliseum/textlab/result_package.py` |

Because this successor changes source behavior, every Round 9 GO and integration
is historical for its new commit. It requires fresh applicable same-commit
reviews and integrations before an M8 execution request can be published. That
request must receive a separate owner approval selecting the numeric budget;
this source slice grants no live-execution authority.

## What changed and why

Phase 1 calibrated the instrument using scripted deterministic deciders. Ten
defects were found that are **invisible under a scripted decider** and that could
each fake or mask the Phase-2 result. Sections were assigned to disjoint write
sets and built in parallel.

| § | Owned paths | Closes |
|---|---|---|
| B8 | `schema.py`, `training/actions.py` | exposure points — a decision still requires ≥2 actions (audit 000886 intact); an exposure requires exactly 1 and is excluded from legal-action-set export |
| B6 | `configs/scenarios/scramble_*_m8.yaml`, `configs/registry/scenarios.yaml`, `scenario.py` | **F2** — agent-authored history content; imposed-history lint |
| B2 | `admissibility.py` | **F8** foundation — versioned decision-admissibility predicate over already-recorded fields |
| B3 | `metrics.py` | **F1/F3/F4/F8** — `order_sensitivity_report`, a versioned successor with replicates, stochastic admission, bootstrap uncertainty, fail-closed refusal |
| B4 | `sweep.py` | **F6/F7** — condition interleaving, typed per-condition dropout, balance gate |
| B5 | `agents.py` | **F5** — two-arm falsifiable seed probe |
| B1 | `configs/registry/experiments.yaml`, `configs/experiments/`, `registry.py` | experiment identity, threshold loaders, anti-rigging lint |
| Director | `tests/test_textlab_stochastic.py`, `tests/test_textlab_scenario_registry.py` | two cross-owned pins, see **Test changes** |

## Test changes — declared, because "the builder edited a test" deserves scrutiny

Exactly two pre-existing test files were modified. Neither was weakened; both
gained assertions.

1. **`tests/test_textlab_stochastic.py::test_ollama_seed_probe_is_scoped_record`**
   drove the probe with a **constant-output backend** (`iter(["ready","ready"])`)
   at temperature 0.7 and asserted it verified. That fixture *is* a backend which
   ignores `options.seed`, so the test pinned the exact false pass the two-arm
   probe exists to reject; fixing F5 necessarily broke it. Every original
   assertion is retained and the scoped-record intent is unchanged — only the
   fixture is corrected to a seed-honoring backend. A companion test
   (`..._rejects_seed_ignoring_backend`) now pins the rejection the old fixture
   masked. Net +1 test.
2. **`tests/test_textlab_scenario_registry.py::test_registry_covers_whole_corpus_with_spec_families`**
   asserts a hardcoded corpus set — a deliberate anti-sprawl pin that must be
   widened whenever the corpus legitimately grows. The m8 triplet is a
   revision-bound **sibling** of the m7 triplet (same `memory_persistence`
   family, same archetype), not a new scenario family, so SPEC Rule 8's bar on
   unadmitted archetypes is not engaged. The enumeration remains explicit and the
   new ids are pinned at status `draft`.

## Director assembly evidence

Verified before publishing, independently of builder claims:

- **Phase-1 evidence is byte-identical.** The 18-cell m7 grid regenerated in the
  candidate and compared against the same grid regenerated from a pristine
  checkout of `ac693b53`: **0/18** `decisions.jsonl` byte-diffs, **0/18**
  `run.json` diffs excluding wall-clock timestamps and `code_version`. Run IDs
  are identical, so no lineage-hashed field moved.
- **The calibration result reproduces exactly** — aggregator output byte-identical
  to the pristine baseline: linear TV(A,B)=0, recency and hysteresis TV(A,B)=1,
  TV(A,C)=0 for all three rules.
- **The frozen comparator is unchanged.** `scramble_terminal_distribution`'s
  source is byte-identical (sha256 verified) and its output is golden-locked.
- **The m8 triplet runs end-to-end** and produces the intended imposed history:
  A and B carry the identical event multiset with identical recorded actions in
  different order; A and C share a byte-identical `history_prompt_hash` while the
  sham reworsds the measured terminal prompt.

### The defect, reproduced end-to-end on real runner output

Not a synthetic fixture: a 12-run A/B/C pack was executed through the real runner
against the m8 triplet using the `llm:mock:garbled` fixture (offline, no provider),
which emits genuinely unparseable output. Every terminal decision is therefore a
parse fallback.

| | Result |
|---|---|
| **Frozen comparator** (`scramble_terminal_distribution`) | `TV(A,B)=0.0`, `TV(A,C)=0.0`, `n=4` per condition, all three distributions `{share_resource: 1.0}` |
| **New report** (`order_sensitivity_report`) | **REFUSES** — `admissible_effective_n=0 < 20`; `non_decision_rate=1.0 > 0.20`; reasons `{parse_fallback_winner: 4}` per cell; `tv_distances` never computed |

The frozen comparator reports a **clean, confident null from evidence that
contains no decisions at all.** Because every fallback resolves to the first
available action — identical across all three conditions — total garbage
converges to a perfect null rather than to noise.

This is the more dangerous failure mode, and it is worth stating plainly: the
owner directive establishes that "a null result is a successful completion of
Phase 2." An instrument that manufactures nulls from unreadable output would
therefore have produced a *publishable scientific conclusion* from an instrument
reading nothing, with no signal that anything was wrong. The admissibility census
and fail-closed refusal exist specifically to make that outcome impossible to
report.

This also closes a gap the admissibility section itself flagged — that no
committed run contained a real fallback node, so its non-admissible paths rested
on synthetic fixtures only.

### Environment note (reproducible, not a source defect)

A freshly created worktree lacking the **gitignored** `logs/runs` evidence
reproducibly fails a set of registry/visualization tests that cannot resolve
their run trees. Supplying that evidence resolves them with **no source change**;
the copied evidence is gitignored and is not committed. The expected test count
declared in each request is taken from a complete run in an environment that
contains it.

## Repair history — cycle 1 (`b39fde46` → this candidate)

Coverage section A returned **`AUDIT_BLOCKED`** (event `001803`) on candidate
`b39fde46` with three HIGH findings, all reproduced by the auditor and
independently re-reproduced by the Director before repair. None was disputed.

| Finding | Repair |
|---|---|
| **1.** `design_hash` froze `scramble_terminal_distribution` as the analysis path — the Phase-1 comparator this candidate itself proves manufactures nulls from unparseable output | `primary_event` re-expressed to name `metrics.order_sensitivity_report`; a literal symbol ban on the Phase-1 comparator in `primary_event`, with the named prose exclusion in `planned_design.notes` (equally design-hashed); lint fails a design naming it |
| **2.** No frozen `max_surviving_delta`; the balance gate defaults to `None` and is skipped | `max_surviving_delta = 2` frozen in `planned_design` and joined into the single `load_thresholds` bundle; lint fails a design omitting it |
| **3.** No sensitivity ceiling — maximal within-condition noise misclassified as a successful null | `min_detectable_effect = 0.25` frozen; a sensitivity precondition now gates **both** branches; operating characteristics simulated and committed |

### What the required characterisation then found

Finding 3's repair obliged a simulation of operating characteristics *before*
execution. That simulation found a further, deeper defect that neither the
builders nor the audit had seen:

**The design as frozen was inert — false-positive rate 0.000 and power 0.000.**
`TV_null` was estimated between A's two 24-unit halves while `TV(A,B)` was
computed on 48 vs 48. Total variation between empirical distributions is biased
upward at small n, so the null carried roughly **twice** the small-sample
inflation of the statistic it calibrated — measured upper bound ≈0.49 against a
0.25 ceiling. The gap is a property of the split, not of the evidence. Even a
genuine `TV(A,B) = 0.6` was refused.

Nothing was broken: every test passed and the rule read as principled. It would
have consumed 144 live runs and returned "inconclusive" whatever the model did,
and the natural reading would have been appropriate conservatism.

**Correction:** the split-half null is replaced by a **paired permutation null**
over the matched units the design already guarantees — exact under the
exchangeability implied by H0, computed at the true sample sizes so no mismatch
exists, and costing no additional live runs. `ORDER_REPORT_VERSION` bumps to 2
so any verdict is traceable to the rule that produced it. `noise_floor_split`
is retained as a reported diagnostic and explicitly stripped of authority.

**The rejected alternative is recorded deliberately:** raising
`min_detectable_effect` above the noise floor would have made the numbers work
while admitting only enormous effects. That is the reinterpret-to-rescue move
the preregistration forbids, and it was available and easy.

### And one further correction the permutation null exposed

Implementing the permutation null faithfully surfaced a third specification
error. The sensitivity requirement had been written to gate **both** branches —
correct for v1, where an inflated split-half floor genuinely broke both
directions, and **wrong** once `q_AB` became the rejection threshold itself.
Exceeding `q_AB` rejects H0 at `alpha`; that is a valid positive whether or not
a smaller effect would also have been detectable.

Implemented symmetrically it discarded decisive findings: total separation with
`TV(A,B) = 1.0` against `q_AB = 0.2917` was reported **inconclusive**, purely
because `0.2917 > 0.25`. The builder implemented the rule as specified, measured
the consequence, pinned it in a test, and reported it rather than quietly
correcting it.

The rule is now an ordered five-clause form with the sensitivity requirement
attached to the **null branch only** (clause 4). It governs what a
*non*-rejection may assert; it never invalidates a rejection.

### Measured operating characteristics across the three rule versions

All at the frozen `n = 48` per condition, same seeds, same arms:

| Rule | FPR under H0 | Power at `TV(A,B)=0.25` | Total separation |
|---|---|---|---|
| v1 split-half floor, symmetric gate | 0.000 | **0.000** | `no_order_effect_observed` |
| v2 permutation null, symmetric gate | 0.025 / 0.000 / 0.050 | 0.600 | `inconclusive` |
| **v3 permutation null, asymmetric gate** | 0.025 / 0.000 / 0.050 | **0.725** | `order_effect_observed` |

v1 was inert — it could not detect an effect of any size. v3 leaks no additional
false positives (identical FPR in every arm), because under H0 the packs whose
`q_AB` exceeded the ceiling were also packs that failed to reject.

**The Finding-3 invariant survives every revision.** The maximally-noisy pack is
never reported as a successful null: under v3 clause 3 fires on a genuine
rejection before clause 4 is reached. What changed is which clause protects it,
and that the protection no longer costs valid rejections.

### Provenance discipline

Each rule change bumped `ORDER_REPORT_VERSION` (1 → 2 → 3), so every emitted
verdict is traceable to the rule that produced it, and the registry lint fails a
design whose version marker disagrees with its stated rule. Three separate
`design_hash` values were issued and superseded during this repair cycle; the
candidate carries only the final one.

**All three specification errors in this cycle were the Director's, not the
builders'.** Each came from carrying a rule across a change that invalidated its
justification — reusing the old comparator's name in the frozen contract, reusing
a noise-floor estimator across a sample-size change, and reusing a symmetry
argument across a change in what the threshold meant. They are recorded here
because a reviewer should know where this candidate's errors clustered.

## Coverage union — all five required, any BLOCKED blocks the union

No section alone carries integration authority. `GO_WITH_CONDITIONS` is not plain
GO unless the active protocol authorizes and satisfies those conditions.

| Audit | Coverage | Explicit exclusions |
|---|---|---|
| **A — Design and scientific identification** | Null frozen before outcomes; A/B matched except order **including the imposed-history decision and whether it is the right estimand**; C a valid actor-indistinguishable sham **and non-vacuous under imposed history**; seven rivals stated with which remain viable; thresholds/uncertainty/sample/exclusions/stopping frozen; claim ceiling evidence-bounded; the experiment may return null without rescue | implementation detail, diff confinement |
| **B — Identity and authority** | Independent registry authority; payload-to-slot binding; unique variant ids; exact model digest and provider regime; prompt/parser/arbitration/runtime identity; effective-unit identity; design-hash reconstruction; **SC-6 absent throughout** | scientific merit, metric math |
| **C — Capture, replay, evidence integrity** | Provider-free replay and its **declared weaker meaning** for LLM runs; actor-safe prompts; no raw-completion leakage; run/evidence manifest completeness; tamper and stale-input refusal; deterministic regeneration | thresholds, scope |
| **D — Metrics, failure semantics, claims** | A/B and A/C aggregation; verbatim frozen threshold application; effective-n accounting; typed missing/malformed/timeout outcomes; **sham failure voids promotion**; null/inconclusive/positive classification; no outcome-only or developmental claim | design merit, identity |
| **E — Scope, regression, complete-suite proof** | Diff confinement; no Council/HSC/Blender/training/theory expansion; **Phase-1 invariants and evidence unchanged**; the two declared test changes are strengthenings not weakenings; focused tests; one complete suite in an authorized environment; exact commit and tree identity | scientific merit |

**Union rule:** every section must reach plain `AUDIT_GO` bound to the same
candidate commit. Findings are reproduced independently before repair; a repair
produces a new commit and a new commit-bound request. Nothing integrates on a
partial set, conflicting verdicts are never averaged, and no invariant,
threshold, or test is weakened to obtain GO.

## Questions the Director specifically wants challenged

Stated openly rather than left for discovery:

1. **Is imposed history the right estimand?** It measures order of *imposed*
   experience, not self-authored trajectory. That is a deliberate narrowing and
   an auditor may reasonably rule it answers a different question than intended.
2. **Are the bootstrap bounds honest at n=48 per condition?** The decision rule
   compares a lower bound against a noise-floor upper bound; whether that is
   adequately powered is a legitimate scientific challenge.
3. **B3's strict reading:** the noise-floor half-cells `A|S1` / `A|S2` are charged
   against the admissibility bounds as compared cells. A looser defensible reading
   exists; the fail-closed one was chosen.
4. **Is `max_non_decision_rate = 0.20` too permissive** for a 7B model on a JSON
   contract, given the estimand is explicitly conditional on parseability?
5. **Does the abliterated model regime** moderate behavior on betrayal content in
   a way that limits the claim beyond what the preregistration already states?
