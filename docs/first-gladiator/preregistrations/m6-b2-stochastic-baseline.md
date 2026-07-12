# Pre-registration — M6 batch 2: stochastic baseline

**Frozen design; runs pending SC-6 owner approval + the pinned fleet
online. Registered as `m6-stochastic-baseline` (pre-registered).**

## Purpose (not a hypothesis test — a measurement)

Estimate outcome VARIANCE across sampler seeds for the built families, so
sample-size / power decisions for every downstream experiment rest on data
rather than guesswork (the DECISION-REGISTER's deferred "sample sizes and
power" resolves from this). This is a baseline, not a claim generator.

## Design

- **Models:** the pinned fleet — llama3.1 (`46e0c10c…`), qwen3:8b
  (`500a1f06…`), gemma3 (`a2af6cc3…`). Any digest drift = a new regime,
  reported, never silently compared.
- **Scenarios (3 built families, primaries + controls where they carry the
  manipulated variable):** `corrupt_king` (`3db66ec0…`) +
  `corrupt_king_verifiable` (`50a96570…`); `water_bearer` (`59923797…`);
  `hidden_objective` (`12976717…`).
- **Variants:** both paraphrase variants of each scenario (≥2, per the
  binding rule).
- **Interaction mode:** `independent_vignettes` (the baseline mode).
- **Sampling:** temperature 0.7; sampler seeds {11,12,13,14,15};
  scenario_seed = each variant's seed.
- **Generalization level:** L1 (same scenarios, new sampler seeds).

## Reported measures (METRICS-v1 only)

Per regime cell: every METRICS-v1 rate with its `effective_n` and
`variant_spread` (the v1 dispersion diagnostic). The deliverable is the
**per-metric across-seed spread per cell** — the variance input to power
decisions. NO cross-model or moral ranking is claimed from this batch;
model differences observed here enter the ladder only as OBSERVATIONS
pending the M10 program.

## Guards

Interaction modes never pool; retries collapse (never average); regimes
keyed on the full comparison hash. Fresh single-writer manifest,
pre-registered before the first live call, full validation battery, offline
replay check.
