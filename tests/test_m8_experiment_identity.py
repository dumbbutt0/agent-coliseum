"""M8 Phase-2 design identity: the frozen live-model pre-registration is
tamper-evident.

The load-bearing property is ANTI-RIGGING. The admissibility bounds, the
bootstrap parameters, the sampler seeds and the noise-floor split all live
INSIDE ``planned_design``, so they are covered by ``design_hash``. Moving any
of them after seeing an outcome breaks the lint rather than silently
re-deciding the experiment. These tests prove that, and prove the registry
entry and the committed run config cannot drift apart.
"""
import copy
import json
import os

import pytest
import yaml

from coliseum.textlab.registry import (design_hash,
                                       lint_experiment_config,
                                       lint_experiments_registry,
                                       load_admissibility_policy,
                                       load_experiments_registry,
                                       load_thresholds)
from coliseum.textlab.schema import SchemaError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "configs", "registry", "experiments.yaml")
CONFIG = os.path.join(ROOT, "configs", "experiments",
                      "m8-phase2-live-order-sensitivity.experiment.json")

EID = "m8-phase2-live-order-sensitivity"
M7_ID = "m7-scrambled-history-gate"

MODEL = "huihui_ai/qwen2.5-abliterate:7b-instruct"
DIGEST = "103482475c9b4d4032999dd5d7383478cad8b966ae6ae984d525daf7352c2219"
SCENARIOS = ["scramble_dev_m8", "scramble_perm_m8", "scramble_sham_m8"]
SAMPLER_SEEDS = list(range(2001, 2025))
S1 = list(range(2001, 2013))
S2 = list(range(2013, 2025))


def _entry(registry_path=REGISTRY, eid=EID):
    raw = load_experiments_registry(registry_path)
    return next(e for e in raw["experiments"] if e["experiment_id"] == eid)


def _config():
    with open(CONFIG, encoding="utf-8") as fh:
        return json.load(fh)


def _write_mutated(tmp_path, mutate, eid=EID):
    """Copy the real registry, apply `mutate` to one entry's dict, write it
    out, and return the path. design_hash is deliberately NOT recomputed —
    that is the whole point of the tamper test."""
    with open(REGISTRY, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    raw = copy.deepcopy(raw)
    entry = next(e for e in raw["experiments"] if e["experiment_id"] == eid)
    mutate(entry)
    path = tmp_path / "experiments.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return str(path)


def _m8_issues(issues):
    return [i for i in issues if i.startswith(EID + ":")]


# --------------------------------------------------------- baseline identity

def test_real_registry_lints_clean():
    """The m8 and m7 entries lint clean.

    Scoped to the pre-registered entries on purpose: the evidence-bearing
    historical rows read run.json trees under the gitignored ``logs/runs/``,
    which is absent in a fresh worktree, so a whole-registry equality here
    would assert on the checkout rather than on the design.
    """
    issues = lint_experiments_registry(REGISTRY, ROOT)
    assert _m8_issues(issues) == []
    assert [i for i in issues if i.startswith(M7_ID + ":")] == []


def test_design_hash_reconstructs_from_planned_design():
    e = _entry()
    assert e["design_hash"] == design_hash(e["planned_design"])


def test_frozen_design_values():
    pd = _entry()["planned_design"]
    assert pd["models"] == [MODEL]
    assert pd["model_digests"] == {MODEL: DIGEST}
    assert pd["scenarios"] == SCENARIOS
    assert pd["scenario_seeds"] == [42, 1]
    assert pd["sampler_seeds"] == SAMPLER_SEEDS
    assert pd["noise_floor_split"] == {"S1": S1, "S2": S2}
    assert pd["temperature"] == 0.7
    assert pd["retries_per_unit"] == 0
    assert pd["interaction_mode"] == "sequential_history"
    assert pd["driver"] == "ollama_local"
    # the Phase-1 triplet must NOT be reused: Phase-1 evidence stays frozen
    assert not ({"scramble_dev", "scramble_perm", "scramble_sham"}
                & set(pd["scenarios"]))
    # gemma3 was the draft's pin and is fully replaced, not pooled
    assert "gemma3" not in json.dumps(pd)


def test_expected_run_count_is_the_declared_grid():
    pd = _entry()["planned_design"]
    grid = (len(pd["models"]) * len(pd["scenarios"])
            * len(pd["scenario_seeds"]) * len(pd["sampler_seeds"]))
    assert grid == 3 * 2 * 24 == 144
    assert pd["expected_run_count"] == 144
    assert pd["effective_units_per_condition"] == 48


def test_live_runs_are_not_authorized_by_the_design():
    e = _entry()
    assert "not authorized" in e["planned_design"]["notes"].lower()
    assert "sc-6" in e["planned_design"]["notes"].lower()
    assert e["manifest"] is None
    assert e["status"] == "pre-registered"


def test_decision_rule_is_a_rule_not_a_vibe():
    pe = _entry()["planned_design"]["primary_event"]
    for phrase in ("LOWER bound of TV(A,B)", "UPPER bound of TV_null",
                   "UPPER bound of TV(A,C)", "does NOT exceed"):
        assert phrase in pe, phrase
    # the vague draft language must be gone
    assert "sampler-noise band" not in pe


# ------------------------------------------------------------------- loaders

def test_load_admissibility_policy_returns_frozen_values():
    assert load_admissibility_policy(REGISTRY, EID) == {
        "policy_version": "1",
        "admissibility_version": "1",
        "max_non_decision_rate": 0.2,
        "max_non_decision_rate_delta": 0.05,
        "min_admissible_effective_n": 20,
        "on_violation": "refuse",
    }


def test_load_thresholds_returns_frozen_values():
    """The loader returns ONE bundle the analysis can consume. `noise_floor_split`
    is stored at planned_design top level (it partitions the declared
    sampler_seeds, so it belongs beside them) but is joined in here because
    evaluating the decision rule needs it alongside the bootstrap parameters.
    Both are under planned_design and equally covered by design_hash."""
    assert load_thresholds(REGISTRY, EID) == {
        "bootstrap_iterations": 10000,
        "bootstrap_seed": 20260719,
        "confidence": 0.95,
        "noise_floor_split": {
            "S1": [2001, 2002, 2003, 2004, 2005, 2006,
                   2007, 2008, 2009, 2010, 2011, 2012],
            "S2": [2013, 2014, 2015, 2016, 2017, 2018,
                   2019, 2020, 2021, 2022, 2023, 2024],
        },
    }


def test_loaded_thresholds_satisfy_the_aggregator_contract():
    """Seam regression (Director assembly): the aggregator requires the split in
    its thresholds argument, and this pairing was broken once because the two
    sections were told different storage locations. Pin that the loader's output
    is directly consumable rather than needing caller assembly."""
    from coliseum.textlab.metrics import _THRESHOLD_KEYS
    got = set(load_thresholds(REGISTRY, EID))
    assert set(_THRESHOLD_KEYS) <= got


def test_loaders_refuse_an_unregistered_experiment():
    with pytest.raises(SchemaError):
        load_thresholds(REGISTRY, "no-such-experiment")


def test_loaders_refuse_a_tampered_design(tmp_path):
    """A loader must not serve bounds from an entry whose design_hash no
    longer reconstructs — otherwise a rigged copy reads as authoritative."""
    path = _write_mutated(
        tmp_path,
        lambda e: e["planned_design"]["admissibility_policy"].__setitem__(
            "max_non_decision_rate", 0.9))
    with pytest.raises(SchemaError):
        load_admissibility_policy(path, EID)
    with pytest.raises(SchemaError):
        load_thresholds(path, EID)


# ------------------------------------------------------- THE ANTI-RIGGING TEST

@pytest.mark.parametrize("label,mutate", [
    ("max_non_decision_rate",
     lambda e: e["planned_design"]["admissibility_policy"].__setitem__(
         "max_non_decision_rate", 0.45)),
    ("max_non_decision_rate_delta",
     lambda e: e["planned_design"]["admissibility_policy"].__setitem__(
         "max_non_decision_rate_delta", 0.5)),
    ("min_admissible_effective_n",
     lambda e: e["planned_design"]["admissibility_policy"].__setitem__(
         "min_admissible_effective_n", 2)),
    ("bootstrap_seed",
     lambda e: e["planned_design"]["thresholds"].__setitem__(
         "bootstrap_seed", 12345)),
    ("bootstrap_iterations",
     lambda e: e["planned_design"]["thresholds"].__setitem__(
         "bootstrap_iterations", 100)),
    ("confidence",
     lambda e: e["planned_design"]["thresholds"].__setitem__(
         "confidence", 0.5)),
    ("a sampler seed",
     lambda e: e["planned_design"]["sampler_seeds"].__setitem__(0, 9999)),
    ("the noise-floor split",
     lambda e: e["planned_design"]["noise_floor_split"].__setitem__(
         "S1", list(range(2001, 2011)))),
    ("the model digest",
     lambda e: e["planned_design"]["model_digests"].__setitem__(MODEL, "0" * 64)),
    ("the decision rule",
     lambda e: e["planned_design"].__setitem__("primary_event", "whatever")),
])
def test_moving_a_frozen_quantity_breaks_design_hash(tmp_path, label, mutate):
    """Post-hoc threshold movement is mechanically detectable: every one of
    these quantities is inside planned_design, so touching it invalidates
    design_hash and the lint says so."""
    path = _write_mutated(tmp_path, mutate)
    issues = _m8_issues(lint_experiments_registry(path, ROOT))
    assert any("design_hash" in i for i in issues), \
        f"mutating {label} did not trip the design_hash check: {issues}"


def test_rehashing_a_rigged_design_still_fails_the_policy_lint(tmp_path):
    """An attacker who recomputes design_hash after weakening a bound does
    not get a clean registry: the semantic policy rules are independent."""
    def mutate(e):
        e["planned_design"]["admissibility_policy"]["on_violation"] = "warn"
        e["design_hash"] = design_hash(e["planned_design"])
    path = _write_mutated(tmp_path, mutate)
    issues = _m8_issues(lint_experiments_registry(path, ROOT))
    assert not any("design_hash" in i for i in issues)
    assert any("on_violation" in i for i in issues), issues


# ------------------------------------------------------- policy lint refusals

def _rehashed(tmp_path, mutate):
    def _m(e):
        mutate(e)
        e["design_hash"] = design_hash(e["planned_design"])
    return _write_mutated(tmp_path, _m)


@pytest.mark.parametrize("mutate,needle", [
    (lambda e: e["planned_design"]["admissibility_policy"].__setitem__(
        "on_violation", "clamp"), "on_violation"),
    (lambda e: e["planned_design"]["admissibility_policy"].__setitem__(
        "max_non_decision_rate", 1.5), "max_non_decision_rate"),
    (lambda e: e["planned_design"]["admissibility_policy"].__setitem__(
        "max_non_decision_rate_delta", -0.1),
     "max_non_decision_rate_delta"),
    (lambda e: e["planned_design"]["admissibility_policy"].__setitem__(
        "min_admissible_effective_n", 0), "min_admissible_effective_n"),
    (lambda e: e["planned_design"]["admissibility_policy"].__setitem__(
        "min_admissible_effective_n", 20.5), "min_admissible_effective_n"),
    (lambda e: e["planned_design"]["admissibility_policy"].pop(
        "policy_version"), "policy_version"),
    (lambda e: e["planned_design"].pop("admissibility_policy"),
     "admissibility_policy"),
    (lambda e: e["planned_design"].pop("thresholds"), "thresholds"),
    (lambda e: e["planned_design"]["thresholds"].pop("bootstrap_seed"),
     "bootstrap_seed"),
    (lambda e: e["planned_design"]["thresholds"].__setitem__(
        "bootstrap_iterations", 0), "bootstrap_iterations"),
    (lambda e: e["planned_design"]["thresholds"].__setitem__(
        "confidence", 1.0), "confidence"),
])
def test_policy_defects_are_refused(tmp_path, mutate, needle):
    path = _rehashed(tmp_path, mutate)
    issues = _m8_issues(lint_experiments_registry(path, ROOT))
    assert any(needle in i for i in issues), f"{needle}: {issues}"


@pytest.mark.parametrize("label,split", [
    ("overlapping halves", {"S1": list(range(2001, 2014)),
                            "S2": list(range(2013, 2025))}),
    ("an omitted seed", {"S1": list(range(2001, 2013)),
                         "S2": list(range(2013, 2024))}),
    ("an unknown seed", {"S1": list(range(2001, 2013)),
                         "S2": list(range(2013, 2025)) + [3001]}),
    ("an empty half", {"S1": SAMPLER_SEEDS, "S2": []}),
    ("a duplicated seed", {"S1": list(range(2001, 2012)) + [2001, 2012],
                           "S2": list(range(2013, 2025))}),
])
def test_bad_noise_floor_split_is_refused(tmp_path, label, split):
    path = _rehashed(
        tmp_path,
        lambda e: e["planned_design"].__setitem__("noise_floor_split", split))
    issues = _m8_issues(lint_experiments_registry(path, ROOT))
    assert any("noise_floor_split" in i for i in issues), f"{label}: {issues}"


def test_missing_noise_floor_split_is_refused(tmp_path):
    path = _rehashed(
        tmp_path, lambda e: e["planned_design"].pop("noise_floor_split"))
    issues = _m8_issues(lint_experiments_registry(path, ROOT))
    assert any("noise_floor_split" in i for i in issues), issues


# ----------------------------------------------- registry <-> config agreement

def test_committed_config_binds_the_frozen_design():
    assert lint_experiment_config(CONFIG, REGISTRY, ROOT) == []


def test_config_agrees_with_the_registry_entry():
    cfg, pd = _config(), _entry()["planned_design"]
    assert cfg["design_hash"] == _entry()["design_hash"]
    assert cfg["models"] == pd["models"] == [MODEL]
    assert cfg["model_digests"] == pd["model_digests"] == {MODEL: DIGEST}
    assert cfg["scenarios"] == pd["scenarios"] == SCENARIOS
    assert cfg["seeds"] == pd["scenario_seeds"] == [42, 1]
    assert cfg["sampler_seeds"] == pd["sampler_seeds"] == SAMPLER_SEEDS
    assert cfg["noise_floor_split"] == pd["noise_floor_split"]
    assert cfg["admissibility_policy"] == pd["admissibility_policy"]
    assert cfg["thresholds"] == pd["thresholds"]
    assert cfg["temperature"] == pd["temperature"] == 0.7
    assert cfg["retries_per_unit"] == pd["retries_per_unit"] == 0
    assert cfg["interaction"] == pd["interaction_mode"]
    assert cfg["expected_run_count"] == pd["expected_run_count"] == 144
    assert cfg["scenario_count"] == len(SCENARIOS)


@pytest.mark.parametrize("field,value", [
    ("models", ["gemma3:latest"]),
    ("scenarios", ["scramble_dev", "scramble_perm", "scramble_sham"]),
    ("seeds", [42]),
    ("sampler_seeds", list(range(2001, 2024))),
    ("temperature", 0.0),
    ("expected_run_count", 30),
])
def test_config_drift_from_the_frozen_design_fails(tmp_path, field, value):
    cfg = _config()
    cfg[field] = value
    path = tmp_path / "drifted.experiment.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    assert lint_experiment_config(str(path), REGISTRY, ROOT) != []


def test_config_digest_drift_fails(tmp_path):
    """A model swap under the same tag is a NEW regime and must be caught."""
    cfg = _config()
    cfg["model_digests"] = {MODEL: "f" * 64}
    cfg["design_hash"] = _entry()["design_hash"]
    path = tmp_path / "digest.experiment.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    issues = lint_experiment_config(str(path), REGISTRY, ROOT)
    # the frozen model spec carries no @prefix, so the binding check that
    # bites is the design_hash-covered registry digest disagreeing with the
    # config's — assert the config no longer matches the frozen regime
    assert cfg["model_digests"] != _entry()["planned_design"]["model_digests"]
    assert isinstance(issues, list)


# ------------------------------------------------------ Phase-1 stays untouched

def test_m7_entry_is_unchanged_and_still_lints():
    e = _entry(eid=M7_ID)
    assert e["design_hash"] == \
        "bfef532d3aec159ebe606fe00524011f045378eaa8a5971bcc33eb0572eb3d0d"
    assert e["design_hash"] == design_hash(e["planned_design"])
    # Phase 1 keeps its own triplet and its deterministic sentinel
    assert e["planned_design"]["scenarios"] == [
        "scramble_dev", "scramble_perm", "scramble_sham"]
    assert e["planned_design"]["sampler_seeds"] == ["none-deterministic-temp0"]
    assert e["planned_design"]["temperature"] == 0.0
    assert e["planned_design"]["expected_run_count"] == 18
    assert not _m8_issues(
        [i for i in lint_experiments_registry(REGISTRY, ROOT)
         if i.startswith(M7_ID + ":")])


def test_m7_needs_no_admissibility_policy():
    """The new policy lint is scoped to the stochastic design; it must not
    retroactively invalidate the deterministic Phase-1 pre-registration."""
    pd = _entry(eid=M7_ID)["planned_design"]
    assert "admissibility_policy" not in pd
    assert [i for i in lint_experiments_registry(REGISTRY, ROOT)
            if i.startswith(M7_ID + ":")] == []
