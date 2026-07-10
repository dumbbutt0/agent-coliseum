# Open issues (tracked, not yet fixed)

## 1. Manifest loading: full-row validation + duplicate-key refusal
Opened 2026-07-10 (Codex re-audit minor warning 1). `scripts/sweep_models.py::manifest_load`
validates dir + run_id against run.json but not every resume-key field (digest, scenario_hash,
temperature, sampling_mode); duplicate resume keys are last-row-wins. Required: validate every
field a resume key depends on, and fail loudly on duplicate keys. Blocking: any multi-writer
or long-lived shared manifest (single-writer fresh manifests are safe meanwhile).

## 2. Effective-unit aggregation across scenario seeds
Opened 2026-07-10 (Codex re-audit minor warning 2). `metrics.py` replicate keys include
scenario_seed, so two scenario seeds mapping to the SAME (variant, sampler_seed) are averaged
as separate replicates while effective_n counts distinct (variant, sampler_seed) — inconsistent
weighting. Harmless for single-scenario-seed designs (exp-1) and for temp-0 sweeps; MUST be
fixed before any stochastic grid that uses multiple scenario seeds per variant.
