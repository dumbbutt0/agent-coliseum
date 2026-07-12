# Pre-registration — M6 batch 3: paraphrase replication

**Frozen design; runs pending SC-6 owner approval + the pinned fleet
online. Registered as `m6-paraphrase-replication` (pre-registered).**

## Hypothesis (primary, pre-registered)

The exp-1/exp-2 finding — that per-scenario behavioral rates can shift
between paraphrase variants of the SAME causal structure — is a GENERAL
property, not specific to hidden_objective_aligned: across the three built
families and the pinned fleet, at least one METRICS-v1 rate differs between
a scenario's two paraphrase variants by more than the batch-2 across-seed
spread for that cell (i.e. the wording effect exceeds sampling noise).

## Design

- **Models:** the pinned fleet (llama3.1, qwen3:8b, gemma3 at their pinned
  digests; drift = new regime).
- **Scenarios:** `corrupt_king` (+`corrupt_king_verifiable`),
  `water_bearer`, `hidden_objective` — each with BOTH paraphrase variants
  (the wording contrast is the manipulated variable).
- **Interaction mode:** `independent_vignettes`.
- **Sampling:** temperature 0.7; sampler seeds {11,12,13,14,15}.
- **Generalization level:** L2 (same causal structure, new wording — this
  batch IS the L2 wording-robustness probe).

## Analysis rule (pre-registered)

Wording effect per cell = |variant-A mean − variant-B mean| for each
METRICS-v1 rate, over effective units. "Exceeds sampling noise" is
evaluated against batch-2's across-seed spread for the corresponding cell
(batch 2 MUST complete first — this batch depends on its variance
estimates). Reported per metric with `effective_n`; NO inferential test at
v1.

## Dependency + claim disposition

Depends on batch 2 (variance baseline). Result enters the claim ladder as
an OBSERVATION per family; the cross-family pattern, if it holds, is the
GENERALIZATION evidence that could lift `deliberation-layer-wording-
sensitivity` (currently `replicated`) toward `generalized` — but only via a
dedicated finding audit (SPEC §5), never automatically. Interaction modes
never pool; regimes keyed on the full hash; retries collapse.
