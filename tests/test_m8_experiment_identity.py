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

from coliseum.textlab.registry import (M8_NULL_STATEMENT,
                                       M8_TYPE_I_CRITERION,
                                       design_hash,
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
PREREG_DOC = os.path.join(ROOT, "docs", "first-gladiator", "preregistrations",
                          "m8-phase2-live-order-sensitivity.md")
OC_SCRIPT = os.path.join(ROOT, "scripts", "m8_operating_characteristics.py")

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
    # a-005: the ONE canonical null is now DISTRIBUTIONAL, machine-readable
    # and verbatim
    assert pd["null_form"] == "distributional"
    assert pd["null_statement"] == M8_NULL_STATEMENT
    assert pd["null_statement"] in pd["hypothesis"]
    assert pd["null_statement"] in pd["primary_event"]
    # only the marginal distribution is tested; per-unit effects are OUT OF SCOPE
    assert "CLAIM SCOPE" in pd["hypothesis"]
    assert "OUT OF SCOPE" in pd["hypothesis"]
    assert "per-unit invariance" in pd["hypothesis"]
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
    # a-005: the callable bumps to version 5 because the CLAIM changed — the
    # operative null narrowed from sharp/per-unit to DISTRIBUTIONAL
    assert "ORDER_REPORT_VERSION 5" in pe
    assert "ORDER_REPORT_VERSION 2" not in pe
    assert "ORDER_REPORT_VERSION 3" not in pe
    assert "ORDER_REPORT_VERSION 4" not in pe
    # the Phase-1 comparator may not be the frozen path
    assert "scramble_terminal_distribution" not in pe
    # and the frozen bounds it consumes are named in the identity — including
    # the a-004 fitness criteria, which gate design fitness before execution
    for k in ("min_detectable_effect", "max_surviving_delta",
              "noise_floor_split", "bootstrap_seed", "sham_equivalence_margin",
              "permutation_iterations", "permutation_seed", "alpha",
              "power_target", "type_i_criterion"):
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
    # a-004: the HONEST measured MDE — 0.35, the smallest grid effect whose
    # measured power CP-95 lower bound reached power_target (0.25 measured
    # 0.757 < 0.8 and was NOT kept to look better)
    mde = pd["thresholds"]["min_detectable_effect"]
    assert mde == 0.35
    assert isinstance(mde, float) and 0 < mde <= 1


def test_new_bounds_load_through_the_single_thresholds_bundle():
    """Every bound the execution/report path needs comes out of ONE frozen
    read. A bound the caller has to assemble separately is a bound the caller
    can omit — which is exactly how the balance gate got skipped. The a-004
    fitness criteria travel in the SAME bundle: production loaders expose
    them, so the characterisation cannot invent its own."""
    bundle = load_thresholds(REGISTRY, EID)
    assert bundle["min_detectable_effect"] == 0.35
    assert bundle["sham_equivalence_margin"] == 0.25
    assert bundle["max_surviving_delta"] == 2
    assert bundle["bootstrap_iterations"] == 10000
    assert bundle["bootstrap_seed"] == 20260719
    assert bundle["confidence"] == 0.95
    assert bundle["noise_floor_split"] == {"S1": S1, "S2": S2}
    assert bundle["power_target"] == 0.8
    assert bundle["type_i_criterion"] == M8_TYPE_I_CRITERION
    assert set(bundle) == {"bootstrap_iterations", "bootstrap_seed",
                           "confidence", "min_detectable_effect",
                           "sham_equivalence_margin",
                           "permutation_iterations", "permutation_seed",
                           "alpha", "noise_floor_split", "max_surviving_delta",
                           "power_target", "type_i_criterion"}


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
    other bounds without it. The a-004 fitness criteria (power_target,
    type_i_criterion) ride in the same bundle so the committed
    characterisation is judged against registry-served values, never
    script-local ones."""
    assert load_thresholds(REGISTRY, EID) == {
        "bootstrap_iterations": 10000,
        "bootstrap_seed": 20260719,
        "confidence": 0.95,
        "min_detectable_effect": 0.35,
        "sham_equivalence_margin": 0.25,
        "permutation_iterations": 10000,
        "permutation_seed": 20260719,
        "alpha": 0.05,
        "power_target": 0.8,
        "type_i_criterion":
            "CP-95 upper bound of distributional-null rejection rate <= alpha",
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
    # a-004: the canonical null and the fitness criteria are design-hashed too
    ("null_form",
     lambda e: e["planned_design"].__setitem__("null_form", "marginal")),
    ("null_statement",
     lambda e: e["planned_design"].__setitem__(
         "null_statement", "the distributions look about the same")),
    ("power_target",
     lambda e: e["planned_design"]["thresholds"].__setitem__(
         "power_target", 0.5)),
    ("type_i_criterion",
     lambda e: e["planned_design"]["thresholds"].__setitem__(
         "type_i_criterion",
         "CP-95 lower bound of sharp-null rejection rate <= alpha")),
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

def test_primary_event_expresses_the_six_clause_ordered_rule():
    """The frozen decision rule mirrors the prereg's clause 0-5 rule exactly
    (ORDER_REPORT_VERSION 5): clause 0 evidence admission, clause 1 policy
    refusal, clause 2 sham adequacy, clause 3 rejection, clause 4 warranted
    null, clause 5 inconclusive."""
    pe = _entry()["planned_design"]["primary_event"]
    assert "ORDERED" in pe
    assert "the FIRST clause that matches decides" in pe
    assert "NO distance, quantile, or verdict may be computed or emitted " \
           "once any admission clause refuses" in pe
    # clause 0: mandatory typed evidence admission
    assert "(0) EVIDENCE ADMISSION (all mandatory; refusal is typed)" in pe
    assert "provider-free replay attestation bound to that exact run " \
           "identity" in pe
    assert "reportable / stochastic_reportable booleans alone are never " \
           "sufficient" in pe
    assert "dp_id == d_partner" in pe
    assert "refuses with missing_terminal_probe" in pe
    assert "the terminal NEVER being inferred from list position" in pe
    assert "matched_units == 48 for A|B and for A|C" in pe
    assert "unmatched units are never silently held fixed" in pe
    assert "max_surviving_delta is a REQUIRED threshold" in pe
    assert "enforced before any statistic" in pe
    assert "surviving counts spreading beyond it refuse" in pe
    # clause 1: refusal / seed probe / digest drift / floor -> inconclusive
    assert "the admissibility policy refuses" in pe
    assert "effective n falls below min_admissible_effective_n, the verdict " \
           "is inconclusive" in pe
    # clause 2: the sham-adequacy warrant (both halves, strict margin)
    assert "(2) SHAM-CONTROL ADEQUACY" in pe
    assert "a sham non-rejection needs a warrant exactly as a null claim " \
           "does" in pe
    assert "BOTH that the observed TV(A,C) does NOT exceed q_AC AND that " \
           "q_AC < sham_equivalence_margin" in pe
    assert "observed TV(A,C) exceeds q_AC the verdict is inconclusive" in pe
    assert "If q_AC >= sham_equivalence_margin the sham warrant is missing" \
        in pe
    assert "a positive verdict is unreachable" in pe
    # the audit's pinned boundary case decides INCONCLUSIVE, never positive
    assert "TV(A,C) = q_AC = sham_equivalence_margin is inconclusive under " \
           "the strict inequality, never a positive" in pe
    # clause 3: rejection + sham warrant -> positive (distributional, a-005)
    assert "the observed TV(A,B) exceeds q_AB AND the sham warrant of " \
           "clause (2) holds, the verdict is DISTRIBUTIONAL ORDER EFFECT " \
           "OBSERVED" in pe
    # clause 4: sensitivity warrants the null claim
    assert "q_AB is less than or equal to min_detectable_effect" in pe
    assert "NO DISTRIBUTIONAL ORDER EFFECT OBSERVED" in pe
    # clause 5: neither rejected nor entitled to assert absence
    assert "(5) else the verdict is inconclusive" in pe
    assert "NOT evidence of absence" in pe


def test_sham_equivalence_margin_is_frozen_with_the_right_type():
    """a-004: the margin is DELIBERATELY decoupled from min_detectable_effect.
    Enlarging the margin weakens the sham-adequacy warrant (q_AC < margin
    becomes easier to grant), so it stays at 0.25 — the smallest
    contamination scale this program has claimed to police — whatever value
    the MDE freezes at. It must never silently follow the MDE upward."""
    th = _entry()["planned_design"]["thresholds"]
    sem = th["sham_equivalence_margin"]
    assert sem == 0.25
    assert isinstance(sem, float) and not isinstance(sem, bool)
    assert sem <= th["min_detectable_effect"]


@pytest.mark.parametrize("label,mutate,needle", [
    ("sham margin omitted",
     lambda e: e["planned_design"]["thresholds"].pop("sham_equivalence_margin"),
     "sham_equivalence_margin"),
    ("zero sham margin",
     lambda e: e["planned_design"]["thresholds"].__setitem__(
         "sham_equivalence_margin", 0.0), "sham_equivalence_margin"),
    ("sham margin above 1",
     lambda e: e["planned_design"]["thresholds"].__setitem__(
         "sham_equivalence_margin", 1.5), "sham_equivalence_margin"),
    ("non-numeric sham margin",
     lambda e: e["planned_design"]["thresholds"].__setitem__(
         "sham_equivalence_margin", "wide"), "sham_equivalence_margin"),
])
def test_bad_sham_margin_is_refused(tmp_path, label, mutate, needle):
    path = _rehashed(tmp_path, mutate)
    issues = _m8_issues(lint_experiments_registry(path, ROOT))
    assert any(needle in i for i in issues), f"{label}: {issues}"


@pytest.mark.parametrize("marker", [
    "provider-free replay", "missing_terminal_probe", "matched_units == 48",
    "before any statistic", "d_partner"])
def test_dropping_a_clause0_admission_marker_fails_the_lint(tmp_path, marker):
    """A rule that loses any clause-0 admission requirement can be read as
    re-admitting the audited escapes; the lint refuses it independent of
    design_hash."""
    pe = _entry()["planned_design"]["primary_event"]
    stripped = pe.replace(marker, "[redacted]")
    assert marker not in stripped
    path = _rehashed(
        tmp_path, lambda e: e["planned_design"].__setitem__(
            "primary_event", stripped))
    issues = _m8_issues(lint_experiments_registry(path, ROOT))
    assert not any("design_hash" in i for i in issues)
    assert any(marker in i for i in issues), issues


def test_dropping_the_sham_adequacy_warrant_fails_the_lint(tmp_path):
    pe = _entry()["planned_design"]["primary_event"]
    stripped = pe.replace("q_AC < sham_equivalence_margin",
                          "q_AC compared to the margin")
    assert "q_AC < sham_equivalence_margin" not in stripped
    path = _rehashed(
        tmp_path, lambda e: e["planned_design"].__setitem__(
            "primary_event", stripped))
    issues = _m8_issues(lint_experiments_registry(path, ROOT))
    assert not any("design_hash" in i for i in issues)
    assert any("sham-adequacy" in i or "sham_equivalence_margin" in i
               for i in issues), issues


def test_notes_preserve_the_exchangeability_correction_and_distributional_reframing():
    """Audit a-003 finding 0: the registry note claiming the permutation null's
    exchangeability is 'implied by H0' was FALSE (marginal equality does not
    imply within-pair exchangeability) and was removed. a-005 then narrowed the
    operative null to DISTRIBUTIONAL while keeping the within-unit permutation as
    the reference distribution under exchangeability, capping the claim there."""
    pd = _entry()["planned_design"]
    assert "exchangeability implied by H0" not in pd["notes"]
    assert "WITHIN-PAIR EXCHANGEABILITY" in pd["notes"]
    assert "FALSE and is removed" in pd["notes"]
    # a-005 distributional re-framing is recorded, and the claim is capped there
    assert "DISTRIBUTIONAL RE-FRAMING" in pd["notes"]
    assert "per-unit invariance" in pd["notes"]
    # the primary_event states the operative distributional null and keeps the
    # permutation as the exchangeability reference
    assert "distributional" in pd["primary_event"]
    assert "reference distribution under exchangeability" in pd["primary_event"]


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
                                   "ORDER_REPORT_VERSION 2",
                                   "ORDER_REPORT_VERSION 3",
                                   "ORDER_REPORT_VERSION 4"])
def test_a_stale_callable_version_fails_the_lint(tmp_path, stale):
    """A verdict emitted by an older callable implements a DIFFERENT decision
    rule and must not be able to claim this design."""
    pe = _entry()["planned_design"]["primary_event"]
    rigged = pe.replace("ORDER_REPORT_VERSION 5", stale)
    assert stale in rigged
    path = _rehashed(
        tmp_path, lambda e: e["planned_design"].__setitem__(
            "primary_event", rigged))
    issues = _m8_issues(lint_experiments_registry(path, ROOT))
    assert not any("design_hash" in i for i in issues)
    assert any("ORDER_REPORT_VERSION 5" in i for i in issues), issues


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
    assert cfg["thresholds"]["min_detectable_effect"] == 0.35
    # audit repair R4: both files also mirror the permutation null's parameters
    assert cfg["thresholds"]["permutation_iterations"] == 10000
    assert cfg["thresholds"]["permutation_seed"] == 20260719
    assert cfg["thresholds"]["alpha"] == 0.05
    # R7/a-005: both files carry the sham-adequacy margin and the v5 rule
    assert cfg["thresholds"]["sham_equivalence_margin"] == 0.25
    assert "ORDER_REPORT_VERSION 5" in cfg["primary_event"]
    assert "ORDER_REPORT_VERSION 2" not in cfg["primary_event"]
    assert "ORDER_REPORT_VERSION 3" not in cfg["primary_event"]
    assert "ORDER_REPORT_VERSION 4" not in cfg["primary_event"]
    assert "LOWER bound of TV(A,B)" not in cfg["primary_event"]
    # R6: and both files carry the corrected asymmetric sensitivity requirement
    assert "attaches ONLY to the null branch" in cfg["primary_event"]
    # b-001 finding 2: the frozen arbitration regime is mirrored exactly
    assert cfg["arbitration"] == pd["arbitration"] == "planner_priority"
    # d-001 driver side: the config declares the preregistered interleaved
    # execution order the driver forwards to run_sweep
    assert cfg["execution_order"] == "interleaved"
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


# ------------------- b-001 finding 1: the digest boundary is EXACT equality
#
# The live config provenance gate must compare config.model_digests to
# planned_design.model_digests digest-for-digest. A same-tag 64-hex
# substitution used to return no lint issues and became the live pin.

def _lint_cfg(tmp_path, cfg, name="mutated.experiment.json"):
    path = tmp_path / name
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return lint_experiment_config(str(path), REGISTRY, ROOT)


@pytest.mark.parametrize("label,digest", [
    ("all-f substitution", "f" * 64),
    ("all-e substitution", "e" * 64),
    ("one-hex-char drift", DIGEST[:-1] + ("0" if DIGEST[-1] != "0" else "1")),
])
def test_same_tag_full_digest_substitution_is_refused(tmp_path, label, digest):
    """A model swap under the same tag is a NEW regime: the lint must refuse
    with a digest-specific error BEFORE the driver treats the substituted
    mapping as the expected pin."""
    cfg = _config()
    cfg["model_digests"] = {MODEL: digest}
    cfg["design_hash"] = _entry()["design_hash"]     # hash kept — no cover
    issues = _lint_cfg(tmp_path, cfg)
    assert issues, f"{label}: substitution passed the gate"
    assert any("model_digests" in i and "frozen digest" in i
               for i in issues), f"{label}: {issues}"


def test_missing_and_extra_digest_mappings_are_refused(tmp_path):
    cfg = _config()
    cfg["model_digests"] = {}      # frozen model's digest dropped entirely
    issues = _lint_cfg(tmp_path, cfg)
    assert any("missing frozen models" in i for i in issues), issues

    cfg = _config()
    cfg["model_digests"]["phantom:latest"] = "a" * 64
    issues = _lint_cfg(tmp_path, cfg)
    assert any("extra models" in i for i in issues), issues


def test_malformed_digest_shape_is_refused(tmp_path):
    """A digest that is not a full immutable 64-hex value pins nothing."""
    for bad in ("103482", "z" * 64, ""):
        cfg = _config()
        cfg["model_digests"] = {MODEL: bad}
        issues = _lint_cfg(tmp_path, cfg)
        assert any("64-hex" in i or "frozen digest" in i
                   or "no pinned digest" in i for i in issues), (bad, issues)


# --------------------- b-001 finding 2: arbitration is bound to the design
#
# The frozen planner_priority arbitration rule must be enforced at the
# design-to-live-config boundary: a valid ALTERNATE rule used to pass the
# lint and flow straight into run_sweep.

def test_alternate_arbitration_rule_is_refused(tmp_path):
    cfg = _config()
    cfg["arbitration"] = "reflex_under_time_pressure"
    issues = _lint_cfg(tmp_path, cfg)
    assert any("arbitration" in i and "reflex_under_time_pressure" in i
               for i in issues), issues


def test_missing_arbitration_is_refused(tmp_path):
    """arbitration is a REQUIRED config field — absence must refuse, not
    fall through to a driver default."""
    cfg = _config()
    del cfg["arbitration"]
    issues = _lint_cfg(tmp_path, cfg)
    assert any("arbitration" in i for i in issues), issues


def test_wrong_execution_order_is_refused(tmp_path):
    """The prereg requires interleaved execution; a blocked pack perfectly
    confounds condition with backend state drift."""
    for bad in ("blocked", None):
        cfg = _config()
        if bad is None:
            del cfg["execution_order"]
        else:
            cfg["execution_order"] = bad
        issues = _lint_cfg(tmp_path, cfg)
        assert any("execution_order" in i for i in issues), (bad, issues)


# --------- b-001 finding 3: the REHASH ATTACK fails against the code profile
#
# design_hash is self-derived from planned_design, so mutate + recompute +
# mirror-into-config defeats hash reconstruction entirely. The audited
# code-level M8_FROZEN_PROFILE is the independent authority: BOTH lints must
# refuse every weakened-but-type-valid load-bearing value with the hash
# fully consistent.

def _mirrored_attack(tmp_path, reg_mutate, cfg_mutate):
    """Mutate the registry entry, recompute design_hash, and mirror the same
    mutation + new hash into the config. Returns (registry_issues,
    config_issues) — the attack succeeds only if BOTH are empty."""
    new_hash = {}

    def _m(e):
        reg_mutate(e)
        e["design_hash"] = design_hash(e["planned_design"])
        new_hash["v"] = e["design_hash"]
    reg_path = _write_mutated(tmp_path, _m)
    cfg = _config()
    cfg_mutate(cfg)
    cfg["design_hash"] = new_hash["v"]
    cfg_path = tmp_path / "mirrored.experiment.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    reg_issues = [i for i in lint_experiments_registry(reg_path, ROOT)
                  if i.startswith(EID + ":")]
    cfg_issues = lint_experiment_config(str(cfg_path), reg_path, ROOT)
    return reg_issues, cfg_issues


def _set_policy(key, val):
    return lambda d: d["admissibility_policy"].__setitem__(key, val)


def _set_thresh(key, val):
    return lambda d: d["thresholds"].__setitem__(key, val)


@pytest.mark.parametrize("label,reg_mutate,cfg_mutate,needle", [
    # weakened admissibility rates (the audit's exact reproduction values)
    ("max_non_decision_rate 0.20 -> 0.90",
     lambda e: _set_policy("max_non_decision_rate", 0.9)(e["planned_design"]),
     _set_policy("max_non_decision_rate", 0.9), "max_non_decision_rate"),
    ("max_non_decision_rate_delta 0.05 -> 0.5",
     lambda e: _set_policy("max_non_decision_rate_delta", 0.5)(
         e["planned_design"]),
     _set_policy("max_non_decision_rate_delta", 0.5),
     "max_non_decision_rate_delta"),
    ("effective-n floor 20 -> 2",
     lambda e: _set_policy("min_admissible_effective_n", 2)(
         e["planned_design"]),
     _set_policy("min_admissible_effective_n", 2),
     "min_admissible_effective_n"),
    # weakened inferential parameters
    ("bootstrap_iterations 10000 -> 100",
     lambda e: _set_thresh("bootstrap_iterations", 100)(e["planned_design"]),
     _set_thresh("bootstrap_iterations", 100), "bootstrap_iterations"),
    ("bootstrap_seed re-drawn",
     lambda e: _set_thresh("bootstrap_seed", 1)(e["planned_design"]),
     _set_thresh("bootstrap_seed", 1), "bootstrap_seed"),
    ("confidence 0.95 -> 0.5",
     lambda e: _set_thresh("confidence", 0.5)(e["planned_design"]),
     _set_thresh("confidence", 0.5), "confidence"),
    ("permutation_iterations 10000 -> 100",
     lambda e: _set_thresh("permutation_iterations", 100)(e["planned_design"]),
     _set_thresh("permutation_iterations", 100), "permutation_iterations"),
    ("permutation_seed re-drawn",
     lambda e: _set_thresh("permutation_seed", 1)(e["planned_design"]),
     _set_thresh("permutation_seed", 1), "permutation_seed"),
    ("alpha 0.05 -> 0.2",
     lambda e: _set_thresh("alpha", 0.2)(e["planned_design"]),
     _set_thresh("alpha", 0.2), "alpha"),
    ("min_detectable_effect 0.25 -> 0.9",
     lambda e: _set_thresh("min_detectable_effect", 0.9)(e["planned_design"]),
     _set_thresh("min_detectable_effect", 0.9), "min_detectable_effect"),
    ("sham_equivalence_margin 0.25 -> 0.9",
     lambda e: _set_thresh("sham_equivalence_margin", 0.9)(
         e["planned_design"]),
     _set_thresh("sham_equivalence_margin", 0.9), "sham_equivalence_margin"),
    # the audit's exact dropout-bound weakening: 2 -> 40
    ("max_surviving_delta 2 -> 40",
     lambda e: e["planned_design"].__setitem__("max_surviving_delta", 40),
     lambda c: c.__setitem__("max_surviving_delta", 40),
     "max_surviving_delta"),
    # sampled-unit identity
    ("a sampler seed replaced",
     lambda e: e["planned_design"]["sampler_seeds"].__setitem__(0, 9999),
     lambda c: c["sampler_seeds"].__setitem__(0, 9999), "sampler_seeds"),
    ("the noise-floor split re-drawn",
     lambda e: e["planned_design"].__setitem__(
         "noise_floor_split", {"S1": list(range(2001, 2011)),
                               "S2": list(range(2011, 2025))}),
     lambda c: c.__setitem__(
         "noise_floor_split", {"S1": list(range(2001, 2011)),
                               "S2": list(range(2011, 2025))}),
     "noise_floor_split"),
    ("a scenario seed replaced",
     lambda e: e["planned_design"].__setitem__("scenario_seeds", [42, 2]),
     lambda c: c.__setitem__("seeds", [42, 2]), "scenario_seeds"),
    # regime identity
    ("temperature 0.7 -> 0.0",
     lambda e: e["planned_design"].__setitem__("temperature", 0.0),
     lambda c: c.__setitem__("temperature", 0.0), "temperature"),
    ("arbitration substituted",
     lambda e: e["planned_design"].__setitem__(
         "arbitration", "reflex_under_time_pressure"),
     lambda c: c.__setitem__("arbitration", "reflex_under_time_pressure"),
     "arbitration"),
    ("model digest substituted",
     lambda e: e["planned_design"]["model_digests"].__setitem__(
         MODEL, "e" * 64),
     lambda c: c["model_digests"].__setitem__(MODEL, "e" * 64),
     "model_digests"),
    # a-004 finding 1: the fitness criteria are profile-anchored — weakening
    # the power target or flipping the type-I direction refuses on the code
    # profile even after a clean rehash+mirror
    ("power_target 0.8 -> 0.5",
     lambda e: _set_thresh("power_target", 0.5)(e["planned_design"]),
     _set_thresh("power_target", 0.5), "power_target"),
    ("type_i_criterion direction flipped to lower-bound",
     lambda e: _set_thresh(
         "type_i_criterion",
         "CP-95 lower bound of sharp-null rejection rate <= alpha")(
             e["planned_design"]),
     _set_thresh("type_i_criterion",
                 "CP-95 lower bound of sharp-null rejection rate <= alpha"),
     "type_i_criterion"),
    # a-004 finding 0: the canonical null is profile-anchored the same way
    ("null_form re-declared marginal",
     lambda e: e["planned_design"].__setitem__("null_form", "marginal"),
     lambda c: c.__setitem__("null_form", "marginal"), "null_form"),
    ("null_statement weakened",
     lambda e: e["planned_design"].__setitem__(
         "null_statement", "the A and B distributions are equal"),
     lambda c: c.__setitem__(
         "null_statement", "the A and B distributions are equal"),
     "null_statement"),
])
def test_rehash_and_mirror_attack_fails_both_lints(tmp_path, label,
                                                   reg_mutate, cfg_mutate,
                                                   needle):
    """For every load-bearing value: weaken it to a type-valid alternative,
    recompute design_hash, mirror the config — and BOTH lints must refuse on
    the audited code profile, independent of any hash mismatch."""
    reg_issues, cfg_issues = _mirrored_attack(tmp_path, reg_mutate, cfg_mutate)
    # the hash is fully consistent, so no refusal may rest on design_hash
    assert not any("design_hash" in i for i in reg_issues), (label, reg_issues)
    assert not any("design_hash" in i for i in cfg_issues), (label, cfg_issues)
    assert any(needle in i for i in reg_issues), (label, reg_issues)
    assert any(needle in i for i in cfg_issues), (label, cfg_issues)


def test_profile_constant_matches_the_shipped_design():
    """The audited code profile and the shipped registry/config agree — the
    profile is an anchor, never a second source of drift."""
    from coliseum.textlab.registry import (M8_FROZEN_PROFILE,
                                           FROZEN_NUMERIC_PROFILES)
    assert FROZEN_NUMERIC_PROFILES[EID] is M8_FROZEN_PROFILE
    pd = _entry()["planned_design"]
    for key in ("max_surviving_delta", "sampler_seeds", "noise_floor_split",
                "scenario_seeds", "temperature", "arbitration",
                "model_digests", "null_form", "null_statement"):
        assert pd[key] == M8_FROZEN_PROFILE[key], key
    for k, v in M8_FROZEN_PROFILE["admissibility_policy"].items():
        assert pd["admissibility_policy"][k] == v, k
    for k, v in M8_FROZEN_PROFILE["thresholds"].items():
        assert pd["thresholds"][k] == v, k
    assert M8_FROZEN_PROFILE["model_digests"] == {MODEL: DIGEST}
    # a-004/a-005: the profile anchors the canonical null and both fitness criteria
    assert M8_FROZEN_PROFILE["null_form"] == "distributional"
    assert M8_FROZEN_PROFILE["null_statement"] == M8_NULL_STATEMENT
    assert M8_FROZEN_PROFILE["thresholds"]["power_target"] == 0.8
    assert M8_FROZEN_PROFILE["thresholds"]["type_i_criterion"] == \
        M8_TYPE_I_CRITERION


# --------------------- a-004 finding 0: ONE null everywhere, mechanically

def test_canonical_null_statement_is_mirrored_across_every_surface():
    """The exact canonical statement — not a paraphrase — appears in the
    registry hypothesis, the registry primary_event, the committed config,
    the preregistration document, and the operating-characteristics script.
    A surface that answers a different hypothesis is unauditable."""
    pd = _entry()["planned_design"]
    cfg = _config()
    assert pd["null_statement"] == M8_NULL_STATEMENT
    assert cfg["null_form"] == "distributional"
    assert cfg["null_statement"] == M8_NULL_STATEMENT
    assert M8_NULL_STATEMENT in pd["hypothesis"]
    assert M8_NULL_STATEMENT in pd["primary_event"]
    assert M8_NULL_STATEMENT in cfg["primary_event"]
    with open(PREREG_DOC, encoding="utf-8") as fh:
        prereg = fh.read()
    assert M8_NULL_STATEMENT in prereg
    with open(OC_SCRIPT, encoding="utf-8") as fh:
        script = fh.read()
    # the statement is line-wrapped in source; compare whitespace-normalized.
    # The script ALSO asserts runtime equality against the audited anchor at
    # import time (CANONICAL_NULL_STATEMENT == M8_NULL_STATEMENT), which the
    # operating-characteristics test module exercises by importing it.
    assert M8_NULL_STATEMENT in " ".join(script.split())


def test_the_distributional_null_is_the_operative_hypothesis():
    """a-005 owner decision (the INVERSE of the a-004 posture): the operative
    null is now the DISTRIBUTIONAL (population-marginal) null and the claim is
    capped there. The hypothesis leads with the canonical distributional
    statement, marks per-unit / cancelling effects OUT OF SCOPE, and never
    reintroduces the sharp/per-unit null as operative; the frozen surfaces emit
    no per-unit claim."""
    pd = _entry()["planned_design"]
    hyp = pd["hypothesis"]
    # the hypothesis leads with the canonical distributional null, IS operative
    assert hyp.index("Distributional (population-level) null") \
        < hyp.index("CLAIM SCOPE")
    assert "null_form: distributional" in hyp
    # per-unit / cancelling effects are explicitly OUT OF SCOPE, not operative
    assert "OUT OF SCOPE" in hyp and "per-unit invariance" in hyp
    assert "Sharp (unit-level) null" not in hyp
    # a rejection is capped at the marginal level and never a per-unit claim
    assert "never a per-unit claim" in pd["primary_event"]
    assert "never per-unit" in pd["primary_event"]


def test_prereg_doc_pins_exactly_one_callable_version_literal():
    """a-004 finding 0 evidence, held through a-005: the prereg once named two
    callable versions at once. One literal now, everywhere — bumped to 5 at the
    distributional re-framing."""
    with open(PREREG_DOC, encoding="utf-8") as fh:
        prereg = fh.read()
    assert "ORDER_REPORT_VERSION 5" in prereg
    for stale in ("ORDER_REPORT_VERSION 1", "ORDER_REPORT_VERSION 2",
                  "ORDER_REPORT_VERSION 3", "ORDER_REPORT_VERSION 4"):
        assert stale not in prereg, stale


@pytest.mark.parametrize("label,mutate,needle", [
    ("null_form omitted",
     lambda e: e["planned_design"].pop("null_form"), "null_form"),
    ("null_form marginal",
     lambda e: e["planned_design"].__setitem__("null_form", "marginal"),
     "null_form"),
    ("null_statement omitted",
     lambda e: e["planned_design"].pop("null_statement"), "null_statement"),
    ("null_statement empty",
     lambda e: e["planned_design"].__setitem__("null_statement", "  "),
     "null_statement"),
])
def test_a_design_without_the_canonical_null_fails_the_lint(tmp_path, label,
                                                            mutate, needle):
    path = _rehashed(tmp_path, mutate)
    issues = _m8_issues(lint_experiments_registry(path, ROOT))
    assert any(needle in i for i in issues), f"{label}: {issues}"


def test_a_hypothesis_that_paraphrases_the_null_fails_the_lint(tmp_path):
    """VERBATIM means verbatim: a hypothesis restating the null in different
    words is a second null. The lint requires the canonical statement itself
    inside both the hypothesis and the decision rule."""
    path = _rehashed(
        tmp_path, lambda e: e["planned_design"].__setitem__(
            "hypothesis",
            "H0: order does not matter for any unit; H1: it does."))
    issues = _m8_issues(lint_experiments_registry(path, ROOT))
    assert any("hypothesis does not contain the canonical" in i
               for i in issues), issues


def test_a_rule_that_drops_the_canonical_null_fails_the_lint(tmp_path):
    pe = _entry()["planned_design"]["primary_event"]
    stripped = pe.replace(M8_NULL_STATEMENT, "the null of this design")
    assert M8_NULL_STATEMENT not in stripped
    path = _rehashed(
        tmp_path, lambda e: e["planned_design"].__setitem__(
            "primary_event", stripped))
    issues = _m8_issues(lint_experiments_registry(path, ROOT))
    assert any("primary_event does not contain the" in i for i in issues), \
        issues


# ------------- a-004 finding 1: fitness criteria frozen, honest directions

@pytest.mark.parametrize("label,mutate,needle", [
    ("power_target omitted",
     lambda e: e["planned_design"]["thresholds"].pop("power_target"),
     "power_target"),
    ("power_target zero",
     lambda e: e["planned_design"]["thresholds"].__setitem__(
         "power_target", 0.0), "power_target"),
    ("power_target at alpha (indistinguishable from the FP floor)",
     lambda e: e["planned_design"]["thresholds"].__setitem__(
         "power_target", 0.05), "power_target"),
    ("power_target above 1",
     lambda e: e["planned_design"]["thresholds"].__setitem__(
         "power_target", 1.5), "power_target"),
    ("type_i_criterion omitted",
     lambda e: e["planned_design"]["thresholds"].pop("type_i_criterion"),
     "type_i_criterion"),
    ("type_i_criterion empty",
     lambda e: e["planned_design"]["thresholds"].__setitem__(
         "type_i_criterion", ""), "type_i_criterion"),
])
def test_missing_or_degenerate_fitness_criteria_are_refused(tmp_path, label,
                                                            mutate, needle):
    path = _rehashed(tmp_path, mutate)
    issues = _m8_issues(lint_experiments_registry(path, ROOT))
    assert any(needle in i for i in issues), f"{label}: {issues}"


def test_the_lower_bound_type_i_direction_is_refused(tmp_path):
    """THE DIRECTION IS THE FINDING: a lower-bound non-excess check tests
    only whether a rate materially ABOVE alpha was demonstrated — it cannot
    support an at-or-below-alpha claim. The superseded direction must fail
    the lint independently of the profile mismatch."""
    path = _rehashed(
        tmp_path, lambda e: e["planned_design"]["thresholds"].__setitem__(
            "type_i_criterion",
            "CP-95 lower bound of distributional-null rejection rate <= alpha"))
    issues = _m8_issues(lint_experiments_registry(path, ROOT))
    assert any("SUPERSEDED lower-bound direction" in i for i in issues), \
        issues
    # and a criterion that names no upper bound at all is equally refused
    path = _rehashed(
        tmp_path, lambda e: e["planned_design"]["thresholds"].__setitem__(
            "type_i_criterion", "rejection rate looks fine near alpha"))
    issues = _m8_issues(lint_experiments_registry(path, ROOT))
    assert any("does not bound the UPPER" in i for i in issues), issues


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
