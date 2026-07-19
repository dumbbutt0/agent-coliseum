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
    for phrase in ("observed TV(A,B) exceeds q_AB",
                   "observed TV(A,C) does NOT exceed q_AC",
                   "paired permutation null", "does NOT exceed"):
        assert phrase in pe, phrase
    # the vague draft language must be gone
    assert "sampler-noise band" not in pe
    # R4: the superseded bootstrap-bound-comparison rule must be gone too
    assert "LOWER bound of TV(A,B)" not in pe
    assert "UPPER bound of TV_null" not in pe


# ------------------------------------------- R1a: frozen ANALYSIS IDENTITY
#
# Audit finding 1 (HIGH): the design hash froze the WRONG analysis path. The
# original primary_event said distributions were "computed by
# metrics.scramble_terminal_distribution" — the Phase-1 comparator, which
# admits parse fallbacks as decisions and was demonstrated on this very
# candidate to return TV(A,B)=TV(A,C)=0.0 from 12 runs of wholly unparseable
# output. A design_hash that does not cover WHICH analysis runs freezes
# nothing that matters.

def test_primary_event_freezes_the_successor_analysis_callable():
    pe = _entry()["planned_design"]["primary_event"]
    assert "order_sensitivity_report" in pe
    # R6: the callable bumps to version 3 because the decision rule changed
    # AGAIN (the sensitivity requirement became asymmetric)
    assert "ORDER_REPORT_VERSION 3" in pe
    assert "ORDER_REPORT_VERSION 2" not in pe
    # the Phase-1 comparator may not be the frozen path
    assert "scramble_terminal_distribution" not in pe
    # and the frozen bounds it consumes are named in the identity
    for k in ("min_detectable_effect", "max_surviving_delta",
              "noise_floor_split", "bootstrap_seed",
              "permutation_iterations", "permutation_seed", "alpha"):
        assert k in pe, k


def test_the_named_exclusion_of_the_phase1_comparator_is_design_hashed():
    """The prose exclusion lives in planned_design.notes rather than in
    primary_event so the lint can ban the symbol from primary_event outright
    instead of parsing an English negation. notes is under planned_design, so
    the exclusion is equally covered by design_hash."""
    pd = _entry()["planned_design"]
    assert "metrics.scramble_terminal_distribution" in pd["notes"]
    assert "may NOT be used" in pd["notes"]


def test_naming_the_phase1_comparator_fails_the_lint(tmp_path):
    """Proves the GUARD, not merely the current value: a design that freezes
    the unsafe Phase-1 analysis path must FAIL rather than load quietly."""
    pe = _entry()["planned_design"]["primary_event"]
    rigged = pe + (" Distributions computed by "
                   "metrics.scramble_terminal_distribution over effective "
                   "units.")
    path = _rehashed(
        tmp_path, lambda e: e["planned_design"].__setitem__(
            "primary_event", rigged))
    issues = _m8_issues(lint_experiments_registry(path, ROOT))
    assert not any("design_hash" in i for i in issues)
    assert any("scramble_terminal_distribution" in i for i in issues), issues


def test_dropping_the_successor_callable_fails_the_lint(tmp_path):
    path = _rehashed(
        tmp_path, lambda e: e["planned_design"].__setitem__(
            "primary_event", "Order effect observed iff TV(A,B) > 0."))
    issues = _m8_issues(lint_experiments_registry(path, ROOT))
    assert any("order_sensitivity_report" in i for i in issues), issues


# ------------------------------------ R1b: the frozen sensitivity + dropout bounds
#
# Audit finding 2 (HIGH): the promised differential-dropout refusal had no
# frozen bound. sweep.run_sweep defaults max_surviving_delta to None and SKIPS
# the balance gate when None, so a condition-imbalanced pack could complete
# with the guard never invoked, leaving differential provider dropout
# confounded with order.

def test_new_bounds_are_frozen_with_the_right_types():
    pd = _entry()["planned_design"]
    msd = pd["max_surviving_delta"]
    assert msd == 2
    assert isinstance(msd, int) and not isinstance(msd, bool) and msd >= 0
    mde = pd["thresholds"]["min_detectable_effect"]
    assert mde == 0.25
    assert isinstance(mde, float) and 0 < mde <= 1


def test_new_bounds_load_through_the_single_thresholds_bundle():
    """Every bound the execution/report path needs comes out of ONE frozen
    read. A bound the caller has to assemble separately is a bound the caller
    can omit — which is exactly how the balance gate got skipped."""
    bundle = load_thresholds(REGISTRY, EID)
    assert bundle["min_detectable_effect"] == 0.25
    assert bundle["max_surviving_delta"] == 2
    assert bundle["bootstrap_iterations"] == 10000
    assert bundle["bootstrap_seed"] == 20260719
    assert bundle["confidence"] == 0.95
    assert bundle["noise_floor_split"] == {"S1": S1, "S2": S2}
    assert set(bundle) == {"bootstrap_iterations", "bootstrap_seed",
                           "confidence", "min_detectable_effect",
                           "permutation_iterations", "permutation_seed",
                           "alpha", "noise_floor_split", "max_surviving_delta"}


@pytest.mark.parametrize("label,mutate,needle", [
    ("max_surviving_delta omitted",
     lambda e: e["planned_design"].pop("max_surviving_delta"),
     "max_surviving_delta"),
    ("min_detectable_effect omitted",
     lambda e: e["planned_design"]["thresholds"].pop("min_detectable_effect"),
     "min_detectable_effect"),
])
def test_omitting_either_new_bound_is_refused(tmp_path, label, mutate, needle):
    """A Phase-2 config cannot execute without the dropout bound: absence is a
    lint failure, never a None default that silently skips the gate."""
    path = _rehashed(tmp_path, mutate)
    issues = _m8_issues(lint_experiments_registry(path, ROOT))
    assert any(needle in i for i in issues), f"{label}: {issues}"


@pytest.mark.parametrize("label,mutate,needle", [
    ("negative delta",
     lambda e: e["planned_design"].__setitem__("max_surviving_delta", -1),
     "max_surviving_delta"),
    ("non-int delta",
     lambda e: e["planned_design"].__setitem__("max_surviving_delta", 2.5),
     "max_surviving_delta"),
    ("bool delta",
     lambda e: e["planned_design"].__setitem__("max_surviving_delta", True),
     "max_surviving_delta"),
    ("zero mde",
     lambda e: e["planned_design"]["thresholds"].__setitem__(
         "min_detectable_effect", 0.0), "min_detectable_effect"),
    ("mde above 1",
     lambda e: e["planned_design"]["thresholds"].__setitem__(
         "min_detectable_effect", 1.5), "min_detectable_effect"),
    ("non-numeric mde",
     lambda e: e["planned_design"]["thresholds"].__setitem__(
         "min_detectable_effect", "small"), "min_detectable_effect"),
])
def test_badly_typed_new_bounds_are_refused(tmp_path, label, mutate, needle):
    path = _rehashed(tmp_path, mutate)
    issues = _m8_issues(lint_experiments_registry(path, ROOT))
    assert any(needle in i for i in issues), f"{label}: {issues}"


# ------------------------- R4: the paired-permutation null replaces the split
#
# Audit finding (deeper, found by the design's OWN required characterisation
# before any execution): the split-half noise floor made the design INERT.
# TV_null between two 24-unit halves carries ~2x the small-sample inflation of
# TV(A,B) computed on 48-vs-48, putting the floor near 0.49 against a 0.25
# ceiling — measured false-positive rate 0.000 AND power 0.000. The null is now
# a paired permutation null; `noise_floor_split` is retained but DEMOTED to a
# reported diagnostic that gates nothing.

def test_permutation_parameters_are_frozen_with_the_right_types():
    th = _entry()["planned_design"]["thresholds"]
    assert th["permutation_iterations"] == 10000
    assert isinstance(th["permutation_iterations"], int) \
        and not isinstance(th["permutation_iterations"], bool)
    assert th["permutation_seed"] == 20260719
    assert isinstance(th["permutation_seed"], int) \
        and not isinstance(th["permutation_seed"], bool)
    assert th["alpha"] == 0.05
    assert isinstance(th["alpha"], float) and 0 < th["alpha"] < 0.5


def test_permutation_parameters_are_in_the_single_bundle():
    """The aggregator reads its decision quantile out of the SAME frozen read as
    every other bound; a parameter the caller must fetch separately is one the
    caller can omit."""
    bundle = load_thresholds(REGISTRY, EID)
    assert bundle["permutation_iterations"] == 10000
    assert bundle["permutation_seed"] == 20260719
    assert bundle["alpha"] == 0.05


@pytest.mark.parametrize("key", ["permutation_iterations", "permutation_seed",
                                 "alpha"])
def test_omitting_a_permutation_parameter_is_refused(tmp_path, key):
    path = _rehashed(
        tmp_path, lambda e: e["planned_design"]["thresholds"].pop(key))
    issues = _m8_issues(lint_experiments_registry(path, ROOT))
    assert any(key in i for i in issues), f"{key}: {issues}"


@pytest.mark.parametrize("label,mutate,needle", [
    ("zero iterations",
     lambda e: e["planned_design"]["thresholds"].__setitem__(
         "permutation_iterations", 0), "permutation_iterations"),
    ("non-int iterations",
     lambda e: e["planned_design"]["thresholds"].__setitem__(
         "permutation_iterations", 1000.5), "permutation_iterations"),
    ("bool iterations",
     lambda e: e["planned_design"]["thresholds"].__setitem__(
         "permutation_iterations", True), "permutation_iterations"),
    ("non-int seed",
     lambda e: e["planned_design"]["thresholds"].__setitem__(
         "permutation_seed", "20260719"), "permutation_seed"),
    ("zero alpha",
     lambda e: e["planned_design"]["thresholds"].__setitem__("alpha", 0.0),
     "alpha"),
    ("alpha at the median",
     lambda e: e["planned_design"]["thresholds"].__setitem__("alpha", 0.5),
     "alpha"),
    ("alpha above the median",
     lambda e: e["planned_design"]["thresholds"].__setitem__("alpha", 0.9),
     "alpha"),
    ("non-numeric alpha",
     lambda e: e["planned_design"]["thresholds"].__setitem__("alpha", "5%"),
     "alpha"),
])
def test_badly_typed_permutation_parameters_are_refused(tmp_path, label,
                                                        mutate, needle):
    path = _rehashed(tmp_path, mutate)
    issues = _m8_issues(lint_experiments_registry(path, ROOT))
    assert any(needle in i for i in issues), f"{label}: {issues}"


def test_primary_event_expresses_the_permutation_rule():
    pe = _entry()["planned_design"]["primary_event"]
    assert "paired permutation null" in pe
    assert "q_AB" in pe and "q_AC" in pe
    assert "1 - alpha" in pe
    # the bootstrap survives only as a REPORTING device
    assert "decides nothing" in pe


def test_the_superseded_bootstrap_bound_rule_fails_the_lint(tmp_path):
    """Proves the GUARD, not merely the current text: a design still expressing
    the inert bootstrap-bound-comparison rule must FAIL rather than load
    quietly behind a perfectly valid design_hash."""
    old = ("Order effect observed iff the bootstrap LOWER bound of TV(A,B) "
           "exceeds the bootstrap UPPER bound of TV_null, computed by "
           "metrics.order_sensitivity_report; q_AB and the paired permutation "
           "null are not used.")
    path = _rehashed(
        tmp_path,
        lambda e: e["planned_design"].__setitem__("primary_event", old))
    issues = _m8_issues(lint_experiments_registry(path, ROOT))
    assert not any("design_hash" in i for i in issues)
    assert any("SUPERSEDED" in i for i in issues), issues


def test_dropping_the_permutation_rule_fails_the_lint(tmp_path):
    path = _rehashed(
        tmp_path, lambda e: e["planned_design"].__setitem__(
            "primary_event",
            "Computed by metrics.order_sensitivity_report; effect iff "
            "TV(A,B) > 0."))
    issues = _m8_issues(lint_experiments_registry(path, ROOT))
    assert any("permutation" in i for i in issues), issues


def test_noise_floor_split_is_retained_but_declared_diagnostic_only():
    """It still partitions the declared sampler seeds and is still frozen and
    design-hashed — but a future reader must not be able to believe it still
    decides anything."""
    pd = _entry()["planned_design"]
    assert pd["noise_floor_split"] == {"S1": S1, "S2": S2}
    assert load_thresholds(REGISTRY, EID)["noise_floor_split"] == \
        {"S1": S1, "S2": S2}
    pe = pd["primary_event"]
    assert "DIAGNOSTIC ONLY" in pe
    assert "gates NO verdict" in pe
    assert "DIAGNOSTIC" in pd["notes"] and "no longer gates any verdict" in \
        pd["notes"]


def test_the_null_model_replacement_is_justified_in_the_design_hashed_notes():
    """The correction is legitimate because it is pre-execution: no outcome
    exists, no live run has occurred, no model has been contacted. The reasoning
    lives under planned_design, so it is covered by design_hash."""
    notes = _entry()["planned_design"]["notes"]
    assert "no live run has occurred" in notes
    assert "no model has been contacted" in notes
    assert "inert" in notes.lower()
    # the rescue move that was REJECTED is recorded, so the choice reads as the
    # inconvenient one
    assert "reinterpret-to-rescue" in notes


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
    Both are under planned_design and equally covered by design_hash.

    `max_surviving_delta` is joined in for the same reason (audit repair R1c):
    it bounds differential provider DROPOUT, a property of execution rather
    than of the bootstrap, but the report path must not be able to obtain the
    other bounds without it."""
    assert load_thresholds(REGISTRY, EID) == {
        "bootstrap_iterations": 10000,
        "bootstrap_seed": 20260719,
        "confidence": 0.95,
        "min_detectable_effect": 0.25,
        "permutation_iterations": 10000,
        "permutation_seed": 20260719,
        "alpha": 0.05,
        "max_surviving_delta": 2,
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
    # audit repair R1b: the two NEW bounds are inside planned_design too, so
    # they are equally immovable once an outcome exists
    ("min_detectable_effect",
     lambda e: e["planned_design"]["thresholds"].__setitem__(
         "min_detectable_effect", 0.9)),
    ("max_surviving_delta",
     lambda e: e["planned_design"].__setitem__("max_surviving_delta", 40)),
    ("the analysis identity",
     lambda e: e["planned_design"].__setitem__(
         "primary_event",
         e["planned_design"]["primary_event"].replace(
             "order_sensitivity_report", "scramble_terminal_distribution"))),
    # audit repair R4: the permutation null's parameters ARE the decision
    # threshold, so they are exactly as immovable as the bootstrap ones
    ("permutation_iterations",
     lambda e: e["planned_design"]["thresholds"].__setitem__(
         "permutation_iterations", 100)),
    ("permutation_seed",
     lambda e: e["planned_design"]["thresholds"].__setitem__(
         "permutation_seed", 999)),
    ("alpha",
     lambda e: e["planned_design"]["thresholds"].__setitem__("alpha", 0.2)),
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


# ------------------- R6: the sensitivity requirement is asymmetric, by design
#
# Audit repair R6. The requirement `q_AB <= min_detectable_effect` had been
# specified as a precondition gating BOTH branches — carried over from the
# superseded split-half null without re-derivation. Under a paired permutation
# null `q_AB` IS the rejection threshold, so exceeding it rejects H0 at `alpha`;
# that is a valid positive whether or not a smaller effect would also have been
# resolvable. Implemented symmetrically it discarded a decisive rejection:
# TV(A,B)=1.0 against q_AB=0.2917 returned `inconclusive` because 0.2917 > 0.25.

def test_primary_event_expresses_the_five_clause_ordered_rule():
    pe = _entry()["planned_design"]["primary_event"]
    assert "ORDERED" in pe
    assert "the FIRST clause that matches decides" in pe
    # clause 1: refusal / floor / dropout spread -> inconclusive
    assert "the admissibility policy refuses" in pe
    assert "max_surviving_delta, the verdict is inconclusive" in pe
    # clause 2: sham not null -> inconclusive
    assert "observed TV(A,C) exceeds q_AC the verdict is inconclusive" in pe
    # clause 3: rejection -> positive
    assert "observed TV(A,B) exceeds q_AB the verdict is ORDER EFFECT " \
           "OBSERVED" in pe
    # clause 4: sensitivity warrants the null claim
    assert "q_AB is less than or equal to min_detectable_effect" in pe
    assert "NO ORDER EFFECT OBSERVED" in pe
    # clause 5: neither rejected nor entitled to assert absence
    assert "(5) else the verdict is inconclusive" in pe
    assert "NOT evidence of absence" in pe


def test_the_sensitivity_requirement_is_declared_null_branch_only():
    pe = _entry()["planned_design"]["primary_event"]
    assert "attaches ONLY to the null branch" in pe
    assert "never invalidates a rejection" in pe
    # and the reason is stated, not merely asserted
    assert "q_AB IS the rejection threshold" in pe
    # the perverse result the symmetric rule produced is pinned in the design
    assert "0.2917" in pe


def test_the_symmetric_both_branches_precondition_fails_the_lint(tmp_path):
    """Proves the GUARD, not the current text: a design still gating the
    POSITIVE branch on min_detectable_effect must FAIL rather than load quietly
    behind a perfectly valid design_hash."""
    pe = _entry()["planned_design"]["primary_event"]
    rigged = pe + (
        " SENSITIVITY PRECONDITION (evaluated FIRST): if q_AB exceeds "
        "min_detectable_effect the verdict is inconclusive whatever else holds. "
        "Order effect observed iff the sensitivity precondition holds AND the "
        "observed TV(A,B) exceeds q_AB.")
    path = _rehashed(
        tmp_path, lambda e: e["planned_design"].__setitem__(
            "primary_event", rigged))
    issues = _m8_issues(lint_experiments_registry(path, ROOT))
    assert not any("design_hash" in i for i in issues)
    assert any("SYMMETRIC" in i for i in issues), issues


def test_dropping_the_asymmetry_statement_fails_the_lint(tmp_path):
    pe = _entry()["planned_design"]["primary_event"]
    stripped = pe.replace("attaches ONLY to the null branch",
                          "applies to the rule")
    path = _rehashed(
        tmp_path, lambda e: e["planned_design"].__setitem__(
            "primary_event", stripped))
    issues = _m8_issues(lint_experiments_registry(path, ROOT))
    assert any("asymmetric sensitivity requirement" in i for i in issues), \
        issues


@pytest.mark.parametrize("stale", ["ORDER_REPORT_VERSION 1",
                                   "ORDER_REPORT_VERSION 2"])
def test_a_stale_callable_version_fails_the_lint(tmp_path, stale):
    """A verdict emitted by an older callable implements a DIFFERENT decision
    rule and must not be able to claim this design."""
    pe = _entry()["planned_design"]["primary_event"]
    rigged = pe.replace("ORDER_REPORT_VERSION 3", stale)
    assert stale in rigged
    path = _rehashed(
        tmp_path, lambda e: e["planned_design"].__setitem__(
            "primary_event", rigged))
    issues = _m8_issues(lint_experiments_registry(path, ROOT))
    assert not any("design_hash" in i for i in issues)
    assert any("ORDER_REPORT_VERSION 3" in i for i in issues), issues


def test_the_asymmetry_correction_is_justified_in_the_design_hashed_notes():
    notes = _entry()["planned_design"]["notes"]
    assert "SENSITIVITY-ASYMMETRY CORRECTION" in notes
    assert "ORDER_REPORT_VERSION bumped 2 -> 3" in notes
    assert "no live run has occurred" in notes
    assert "Nothing is weakened" in notes


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
    # audit repair R1a/R1b: the two files mirror the analysis identity and both
    # new bounds, so they cannot drift into disagreeing about what was frozen
    assert cfg["primary_event"] == pd["primary_event"]
    assert "order_sensitivity_report" in cfg["primary_event"]
    assert "scramble_terminal_distribution" not in cfg["primary_event"]
    assert cfg["max_surviving_delta"] == pd["max_surviving_delta"] == 2
    assert cfg["thresholds"]["min_detectable_effect"] == 0.25
    # audit repair R4: both files also mirror the permutation null's parameters
    assert cfg["thresholds"]["permutation_iterations"] == 10000
    assert cfg["thresholds"]["permutation_seed"] == 20260719
    assert cfg["thresholds"]["alpha"] == 0.05
    assert "ORDER_REPORT_VERSION 3" in cfg["primary_event"]
    assert "ORDER_REPORT_VERSION 2" not in cfg["primary_event"]
    assert "LOWER bound of TV(A,B)" not in cfg["primary_event"]
    # R6: and both files carry the corrected asymmetric sensitivity requirement
    assert "attaches ONLY to the null branch" in cfg["primary_event"]
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


def test_m7_planned_design_is_byte_unchanged_by_the_m8_repair():
    """The M8 audit repair touched only the M8 entry. Phase-1 evidence must keep
    regenerating byte-identically against its three GO verdicts, so m7's frozen
    design must still hash to exactly the value those verdicts were bound to."""
    e = _entry(eid=M7_ID)
    assert design_hash(e["planned_design"]) == \
        "bfef532d3aec159ebe606fe00524011f045378eaa8a5971bcc33eb0572eb3d0d"
    # the new M8 bounds and analysis identity must not have leaked into m7
    pd = e["planned_design"]
    assert "max_surviving_delta" not in pd
    assert "min_detectable_effect" not in json.dumps(pd)
    assert "order_sensitivity_report" not in json.dumps(pd)


def test_m7_needs_no_admissibility_policy():
    """The new policy lint is scoped to the stochastic design; it must not
    retroactively invalidate the deterministic Phase-1 pre-registration."""
    pd = _entry(eid=M7_ID)["planned_design"]
    assert "admissibility_policy" not in pd
    assert [i for i in lint_experiments_registry(REGISTRY, ROOT)
            if i.startswith(M7_ID + ":")] == []
