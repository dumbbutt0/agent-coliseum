"""The three frozen M6 ollama_local run configs bind EXACTLY to their
pre-registered designs (coliseum.textlab.registry.lint_experiment_config), and
every way a config could drift from the frozen hypothesis is refused. This is
the provenance gate: a live run cannot execute a design the owner never froze."""
import json
import os

import pytest

from coliseum.textlab.registry import lint_experiment_config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(ROOT, "configs", "registry", "experiments.yaml")
CONFIG_DIR = os.path.join(ROOT, "configs", "experiments")
CONFIGS = {
    "m6-stochastic-baseline": "m6-b2-stochastic-baseline.experiment.json",
    "m6-sequential-rerun": "m6-b1-sequential-rerun.experiment.json",
    "m6-paraphrase-replication": "m6-b3-paraphrase-replication.experiment.json",
}


def _path(name):
    return os.path.join(CONFIG_DIR, CONFIGS[name])


# All three M6 batches have now RUN and are registered complete; the provenance
# gate therefore refuses each frozen config (a completed experiment must never be
# silently re-run). The design-binding + variant-coverage checks are re-exposed
# below against a pre-registered VIEW, decoupled from the registry's live state.
ALL_M6 = ["m6-stochastic-baseline", "m6-sequential-rerun",
          "m6-paraphrase-replication"]


def _prereg_view(tmp_path, name):
    """Lint the real frozen config against a temp registry where its experiment
    is forced back to pre-registered — re-exposing the checks the provenance gate
    applied before the batch was registered complete, without depending on the
    live registry status."""
    import yaml
    from coliseum.textlab.registry import load_experiments_registry
    raw = load_experiments_registry(REG)
    for e in raw["experiments"]:
        if e["experiment_id"] == name:
            for k in ("validation", "frozen", "interaction_mode",
                      "evidence_root", "rows", "evidence_inventory_hash",
                      "result_request", "finding", "entry_hash"):
                e.pop(k, None)
            e["status"] = "pre-registered"
            e["manifest"] = None
    p = tmp_path / "experiments.yaml"
    p.write_text(yaml.safe_dump(raw, sort_keys=False))
    return lint_experiment_config(_path(name), str(p), ROOT)


@pytest.mark.parametrize("name", ALL_M6)
def test_completed_experiment_config_no_longer_runnable(name):
    """Once an experiment is registered complete, its run config is refused —
    the provenance gate binds only PRE-REGISTERED designs, so a completed
    experiment (all three M6 batches now) can never be silently re-run."""
    issues = lint_experiment_config(_path(name), REG, ROOT)
    assert any("pre-registered" in i for i in issues)


@pytest.mark.parametrize("name", ALL_M6)
def test_frozen_config_binds_design_and_covers_variants(name, tmp_path):
    """Under a pre-registered view, each frozen config still binds exactly to its
    design_hash and its seeds cover BOTH paraphrase variants."""
    assert _prereg_view(tmp_path, name) == []


def test_all_three_batches_present():
    assert set(CONFIGS) == {"m6-stochastic-baseline", "m6-sequential-rerun",
                            "m6-paraphrase-replication"}


def _mutated(tmp_path, name, mutate):
    cfg = json.load(open(_path(name), encoding="utf-8"))
    mutate(cfg)
    p = tmp_path / "c.json"
    p.write_text(json.dumps(cfg))
    return lint_experiment_config(str(p), REG, ROOT)


def test_design_hash_tamper_refused(tmp_path):
    issues = _mutated(tmp_path, "m6-stochastic-baseline",
                      lambda c: c.update(design_hash="0" * 64))
    assert any("does not bind the pre-registered design" in i for i in issues)


def test_weakening_interaction_refused(tmp_path):
    # flipping the sequential batch to independent would pool it with baselines
    issues = _mutated(tmp_path, "m6-sequential-rerun",
                      lambda c: c.update(interaction="independent_vignettes"))
    assert any("interaction" in i for i in issues)


def test_scenario_set_change_refused(tmp_path):
    issues = _mutated(tmp_path, "m6-stochastic-baseline",
                      lambda c: c.update(scenarios=["corrupt_king"]))
    assert any("scenarios" in i for i in issues)


def test_repulled_digest_refused(tmp_path):
    def mutate(c):
        c["model_digests"]["gemma3:latest"] = "deadbeef" + "0" * 56
    issues = _mutated(tmp_path, "m6-sequential-rerun", mutate)
    assert any("frozen prefix" in i or "new regime" in i for i in issues)


def test_frozen_scenario_seeds_pinned_for_b1(tmp_path):
    issues = _mutated(tmp_path, "m6-sequential-rerun",
                      lambda c: c.update(seeds=[7, 9]))
    assert any("scenario_seeds" in i for i in issues)


def test_run_count_must_match_grid(tmp_path):
    issues = _mutated(tmp_path, "m6-paraphrase-replication",
                      lambda c: c.update(expected_run_count=999))
    assert any("expected_run_count" in i for i in issues)


def test_same_parity_seeds_drop_a_variant_refused(tmp_path):
    """Cycle-1 batch-3 audit regression: seeds that all select the same
    variant index (e.g. both odd -> variants[seed % 2] == 1) silently drop a
    variant. The run COUNT can still be 120, so only a variant-coverage check
    catches it — a wording contrast with no variant-A observations is refused."""
    issues = _mutated(tmp_path, "m6-paraphrase-replication",
                      lambda c: c.update(seeds=[7, 9]))  # 7%2==9%2==1 -> variant B only
    assert any("every variant must be selected" in i for i in issues)


def test_duplicate_scenario_refused(tmp_path):
    """A duplicate frozen scenario would run extra cells the declared count
    never counted — the gate refuses it (and it cannot keep the old
    expected_run_count either)."""
    def mutate(c):
        c["scenarios"] = c["scenarios"] + [c["scenarios"][0]]  # dup one
        # keep expected_run_count stale (as the audit repro did)
    issues = _mutated(tmp_path, "m6-stochastic-baseline", mutate)
    assert any("contains duplicates" in i and "scenarios" in i for i in issues)
    assert any("expected_run_count" in i for i in issues)


def test_grid_uses_raw_scenario_list(tmp_path):
    """Even if expected_run_count is 'corrected' to the deduped grid, a
    duplicated scenario is still refused — the count can never launder a dup
    past the gate (the audit's 20-vs-30 escape)."""
    def mutate(c):
        c["scenarios"] = c["scenarios"] + [c["scenarios"][0]]
        # 3 unique scenarios' worth of count would still be a lie about the
        # raw 5-entry list run_sweep iterates
        c["expected_run_count"] = (len(set(c["scenarios"])) * len(c["models"])
                                   * len(c["seeds"]) * len(c["sampler_seeds"]))
    issues = _mutated(tmp_path, "m6-stochastic-baseline", mutate)
    assert any("contains duplicates" in i for i in issues)


def test_extra_model_refused(tmp_path):
    def mutate(c):
        c["models"].append("phi3:latest")
        c["model_digests"]["phi3:latest"] = "a" * 64
    issues = _mutated(tmp_path, "m6-stochastic-baseline", mutate)
    assert any("absent from the frozen design" in i for i in issues)


def test_sampler_seeds_change_refused(tmp_path):
    issues = _mutated(tmp_path, "m6-stochastic-baseline",
                      lambda c: c.update(sampler_seeds=[11, 12]))
    assert any("sampler_seeds" in i for i in issues)
