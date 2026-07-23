# M8 execution authorization and result closure

**Source specification only. This document grants no permission to contact a
model or start M8.** The initial M8 run requires a separately published
experiment request and a separate owner `EXPERIMENT_APPROVED` event after this
source slice has received fresh same-commit review and integration.

## Purpose

The frozen M8 design says what is to be measured. This slice defines the exact
transition from an integrated source commit to one bounded execution and the
exact artifacts that must exist before a result review can begin. It does not
change the frozen design, prompts, model regime, planned count, stopping rule,
analysis, or claim ceiling.

## Direct owner binding

An M8 request carries a closed `execution-authorization.v1` object. The owner
approval copies that object verbatim and also binds the request publication
event and request payload hash. The authorization contains:

- experiment id, design hash, implementation commit, experiment-config hash,
  model names and digests, and the 144-run planned count;
- maximum units, compute minutes, wall minutes, storage, retries per unit, and
  scenarios;
- the evidence root and manifest paths;
- the three prerequisite M7 GO event ids and five same-commit source
  integration event ids; and
- either `resume_from: null` for an initial execution or the exact prior
  request and owner-approval event for a resume.

Publication re-reads the config bytes, reconstructs the verified registry
bundle, checks the prerequisite and integration events, and checks the evidence
namespace. Approval uses `experiment-approval.v2` and directly copies the
authorization, request hash, request publication event id and hash, owner
identity, and approved commit. The append boundary and bounded runner recheck
the same values. Effective runner limits may be narrower but never wider than
the owner-bound maxima.

The owner must choose the compute, wall-time, and storage maxima in the eventual
request. Repository policy ceilings are not substitutes for that choice.

## Initial execution and exact resume

For an initial request, the authorized evidence root and manifest must not
exist at publication or immediately before `EXPERIMENT_STARTED`. The system
does not create them while requesting or approving execution.

A resume is a new request and a new owner approval. It is allowed only when:

1. `resume_from` names a prior owner-approved request whose projected state is
   `autonomy_paused`;
2. every frozen pack binding and budget is identical to the prior approval;
3. the original evidence root is reused; and
4. at least one existing success or tombstone ledger is present.

No automatic retry, replacement evidence namespace, changed model, changed
budget, or changed pack may pass as a resume.

## Bounded result closure

The dedicated roadmap entry makes the already frozen M8 task addressable by the
bounded runner. Its unresolved dependency keeps it out of automatic task
selection; the separate request and owner event remain mandatory.

Inside the child process, M8 must finish these steps before the parent performs
its final evidence inventory:

1. run or exactly resume the sweep under the existing manifest-scoped lock;
2. perform provider-free pack replay;
3. load the success and tombstone ledgers through the shared terminal snapshot
   boundary;
4. require exactly 144 unique terminal outcomes;
5. generate either the frozen order-sensitivity report for an all-success pack
   or a canonical no-statistics terminal-failure report when one or more
   durable tombstones exist;
6. atomically write the report; and
7. build and independently verify result package version 3.

A complete pack containing tombstones is a completed scientific outcome with
`analysis_status: terminal_failure_inconclusive`. Its report contains no effect
estimate, interval, test statistic, or p-value. An incomplete or contradictory
terminal census refuses.

The child returns a closed `result_artifacts` record binding the owner approval,
request hash, success manifest, tombstone ledger identity, replay attestation,
order report, result-package file and content hashes, terminal census, and
analysis status. `EXPERIMENT_COMPLETE`, `RESULT_AUDIT_REQUESTED`, and the result
verdict must agree on this record.

## Frozen M8 identity

| Field | Frozen value |
|---|---|
| Experiment | `m8-phase2-live-order-sensitivity` |
| Design hash | `431871d3266a96999ef02d0d9eb77caba7e6b317135155d3161b1eecf396d533` |
| Config hash | `4847cadfdac059195986114fed6d61850f3c1d925ca4b97618a06cff59e5c960` |
| Model | `huihui_ai/qwen2.5-abliterate:7b-instruct` |
| Model digest | `103482475c9b4d4032999dd5d7383478cad8b966ae6ae984d525daf7352c2219` |
| Planned terminal outcomes | 144 |
| Evidence root | `logs/runs/m8-phase2-live-order-sensitivity` |
| Manifest | `logs/runs/m8-phase2-live-order-sensitivity/manifest.jsonl` |
| M7 prerequisite GOs | `001714-6f7a48e0`, `001719-21604e97`, `001724-8cebf880` |

The implementation commit and five source-integration event ids are assigned
only after this slice is frozen, independently reviewed, and integrated. Their
absence here is deliberate; no earlier GO or integration transfers to the new
commit.

## Acceptance tests

- Closed-schema and exact-copy rejection for request, approval, start, result,
  and verdict payloads.
- Config, registry, prerequisite-event, source-integration, and evidence-path
  cross-checks at publication and start.
- Initial namespace freshness and exact-resume continuity.
- Runner refusal for absent, altered, stale, or over-budget authorization.
- Replay, terminal census, report, package, and final-inventory ordering.
- All-success analyzed package and complete tombstoned inconclusive package.
- Existing M8 sweep, replay, locking, result-package, Council, roadmap, and
  bounded-runner regressions.

