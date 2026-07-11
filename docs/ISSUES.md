# Open issues (tracked, not yet fixed)

(none)

---

# Closed

## 3. hidden_objective d2 narrative statically presupposes the diversion — CLOSED 2026-07-11
Opened 2026-07-10 (full Codex audit). Both `hidden_objective` and `hidden_objective_aligned`
hardcoded a d2_questioned narrative that asserted carts moved ("carts left the granary gate at
night" / "carts were heard by the cisterns at dawn") even though d2 is reachable via `clarify`,
whose outcome narrative says nothing has moved yet. In independent_vignettes mode this was a
wording quirk; in sequential_history mode it would have CONTRADICTED the injected history.
Fixed by an AUTHORED revision (not a patch): the d2 question is now rumor-driven and asserts
no movement, in both wording variants of both twins. New behavioral hashes by construction
(primary `12976717…`, twin `a990de3f…`; pre-revision `f773b19c…`/`c023115c…` are a different
regime — legacy evidence is unaffected, replay comes from stored snapshots). Twin lint stays
structurally clean. Regressions:
tests/test_textlab_audit.py::{test_d2_texts_do_not_presuppose_the_diversion,
test_revised_twins_lint_clean_with_new_hashes}.
CAVEAT recorded for sequential analysis: on the `clarify` route the d2 action labeled `lie`
("nothing has moved") states something true, so moral-tag rates for d2 are only interpretable
CONDITIONED ON the d1 action. The sequential rerun's primary event already conditions on
d1=divert; clarify-route d2 data is exploratory and must be reported per-route
(docs/SEQUENTIAL-RERUN.md).

## 1. Manifest loading: full-row validation + duplicate-key refusal — CLOSED 2026-07-10
(Codex re-audit minor warning 1 → full-audit item 6.) `manifest_load` now validates EVERY
redundant field a row carries against its run.json (run_id, regime, digest, scenario id+hash,
seeds, variant, temperature, sampling_mode, arbitration, reportability, interaction_mode) plus
dir↔run_id/attempt coherence; duplicate resume keys refuse loudly — no last-row-wins.
Regressions: tests/test_textlab_audit.py::test_manifest_full_row_validation_and_duplicate_refusal.
Note: the migrated sweep-v2 manifest cannot express regime identity and is now refused by the
strict loader — consistent with sweep-v2's demotion to a legacy exploratory dataset.

## 2. Effective-unit aggregation across scenario seeds — CLOSED 2026-07-10
(Codex re-audit minor warning 2 → full-audit item 7.) `_cell_metrics` now folds attempts →
replicate means → (variant, sampler_seed) EFFECTIVE-UNIT means before any cell mean, matching
what effective_n counts; twin pairing collapses the same way and reports
raw_pair_n/retry_pair_n/effective_pair_n. Consequence: deterministic aggregate values change
where scenario seeds sample variants unevenly (e.g. 5 seeds → 3:2 variant split) — the
audit-mandated reweighting, not drift. Regressions:
tests/test_textlab_audit.py::{test_scenario_seeds_collapse_into_one_effective_unit,
test_pair_counts_report_scenario_seed_collapse}.
