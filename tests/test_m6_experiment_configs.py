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


@pytest.mark.parametrize("name", list(CONFIGS))
def test_committed_config_binds_to_frozen_design(name):
    assert lint_experiment_config(_path(name), REG, ROOT) == []


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
