"""m8 Phase-2 — frozen operating characteristics of the finite-sample decision rule.

RESTRUCTURED AT THE a-004 SCIENTIFIC RE-FREEZE, re-framed at the a-005
DISTRIBUTIONAL narrowing, then sharpened at the a-006 WITHIN-UNIT SWAP-INVARIANCE
null (owner decision): the operative confirmatory null is within-unit JOINT swap
invariance under across-unit independence, ORDER_REPORT_VERSION is 6, and the
verdict enum literals distributional_order_effect_observed /
no_distributional_order_effect_observed are DELIBERATELY retained. The arithmetic
is unchanged, so the committed numbers of the shared arms are unchanged. This
module regresses the repairs:

* THE TWO-MODE NULL. Swap-invariance null arms are charged type-I in BOTH modes:
  - null_mode "copy" — one draw per unit copied across A/B/C exactly (byte-
    identical pair). The sharp_h0_* arms. Verified by identical realization.
  - null_mode "law_exchangeable" — A/B/C drawn iid from the SAME per-condition
    law (realizations differ, pair exchangeable, independent across units). The
    iid_equal_marginals_* arms. Verified by LAW (equal per-condition laws + iid
    generation), NOT by realization identity. Charged type-I at 3000 trials.

* THE NON-EXCHANGEABLE ALTERNATIVES. Equal marginals (TV(A,B)=0) but a
  non-exchangeable within-unit joint — swap invariance is FALSE yet the marginal
  statistic is identically zero, so the rule cannot reject (power ~ 0). These
  document the design's outside-null sensitivity limitation and are NEVER charged
  type-I.

* FROZEN CRITERIA, honest directions. The fitness criteria live in
  planned_design.thresholds (power_target = 0.8; type_i_criterion = the CP-95
  UPPER-bound rule applied to EVERY charged type-I arm, both null modes), loaded
  from the registry — never invented in the script — and min_detectable_effect is
  the smallest power-grid effect whose measured power CP-95 LOWER bound reaches
  power_target. The artifact's mde_selection block recomputes that choice.

The characterisation lives in TWO places with a clean division of labour:
`scripts/m8_operating_characteristics.py` runs the SLOW study at the exact frozen
decision parameters (10 000 permutation/bootstrap iterations; 400 outer trials
per charged arm, 3000 for the law-exchangeable type-I arms) and writes the
committed artifact `derived/textlab/m8-operating-characteristics.json`; THIS
module is fast — structural branch regressions at simulation-harness iteration
counts (clearly NOT the characterisation) plus the CI regression on the committed
artifact.
"""
import importlib.util
import json
import os
import random

import pytest

from coliseum.textlab.metrics import order_sensitivity_report
from coliseum.textlab.registry import (M8_NULL_STATEMENT,
                                       M8_TYPE_I_CRITERION,
                                       load_admissibility_policy,
                                       load_experiments_registry,
                                       load_thresholds)
from coliseum.textlab.schema import config_hash

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "configs", "registry", "experiments.yaml")
EID = "m8-phase2-live-order-sensitivity"
ARTIFACT = os.path.join(ROOT, "derived", "textlab",
                        "m8-operating-characteristics.json")
SCRIPT = os.path.join(ROOT, "scripts", "m8_operating_characteristics.py")

# importing the script module ALSO exercises its two import-time freezes:
# ORDER_REPORT_VERSION == "6" and CANONICAL_NULL_STATEMENT == the audited
# registry.M8_NULL_STATEMENT anchor.
_spec = importlib.util.spec_from_file_location("m8oc", SCRIPT)
m8oc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m8oc)

# simulation-harness values for the STRUCTURAL tests only — the committed
# characterisation uses the frozen 10 000s (see the module docstring)
_SIM_ITERATIONS = 300

# the charged type-I arms, by null mode
COPY_TYPE_I = {"sharp_h0_iid_uniform", "sharp_h0_iid_graded",
               "sharp_h0_iid_concentrated", "sharp_h0_shared_latent"}
LAW_TYPE_I = {"iid_equal_marginals_uniform", "iid_equal_marginals_graded",
              "iid_equal_marginals_concentrated"}
NONEXCH_ALT = {"alternative_nonexch_cycle4",
               "alternative_nonexch_cycle3_fixed"}


def _sim_thresholds():
    t = dict(m8oc.FROZEN_THRESHOLDS)
    t["bootstrap_iterations"] = _SIM_ITERATIONS
    t["permutation_iterations"] = _SIM_ITERATIONS
    return t


def _run_pack(tmp_path, choose, thresholds=None):
    """One complete 144-run pack through the real frozen path (attested,
    terminal-probed, census-declared), returning the per-agent block."""
    root = str(tmp_path)
    os.makedirs(root, exist_ok=True)
    dirs = []
    for cond in ("A", "B", "C"):
        for variant, scen_seed in m8oc.VARIANTS:
            for samp in m8oc.SAMPLER_SEEDS:
                dirs.append(m8oc._write_unit(root, cond, variant, scen_seed,
                                             samp, choose(cond, variant, samp)))
    rep = order_sensitivity_report(
        dirs, m8oc.CONDITIONS,
        admissibility_policy=m8oc.FROZEN_POLICY,
        thresholds=thresholds or _sim_thresholds(),
        replay_attestation=m8oc._attest(dirs),
        terminal_dp_id=m8oc.TERMINAL_DP_ID,
        surviving_counts={"A": 48, "B": 48, "C": 48})
    return rep["per_agent"]["live"]


def _sched_choose(sched):
    """Adapt a generated potential-outcome schedule to the choose(cond,
    variant, samp) signature `_run_pack` consumes."""
    scen = dict(m8oc.VARIANTS)
    return lambda c, v, s: sched[(c, v, scen[v], s)]


MENU = m8oc.MENU
S1, S2 = m8oc.S1, m8oc.S2
MDE = m8oc.MDE


# ---------------------------------------------------- 0. the harness is frozen

def test_simulation_harness_matches_the_frozen_sample_size(tmp_path):
    """Guards the characterisation itself: if n, the menu or the split drift, the
    numbers stop describing the frozen design."""
    assert len(S1) + len(S2) == 24 and not set(S1) & set(S2)
    assert m8oc.UNITS_PER_CONDITION == 48
    assert len(MENU) == 4
    agent = _run_pack(tmp_path, lambda c, v, s: MENU[(s + len(c)) % 4])
    for label in ("A", "B", "C"):
        cell = agent["cells"][label]
        assert cell["admissible_effective_n"] == 48
        assert cell["non_decision_n"] == 0
    for half in ("A|S1", "A|S2"):
        assert agent["cells"][half]["admissible_effective_n"] == 24
    assert agent["matched_unit_grid"]["required_matched_units"] == 48


def test_script_bundle_equals_the_registry_served_bundle():
    """The script's FROZEN_THRESHOLDS/FROZEN_POLICY are the registry-served
    bundles, byte-for-byte — including the a-004 fitness criteria. The
    characterisation cannot drift from what production loads."""
    assert m8oc.FROZEN_THRESHOLDS == load_thresholds(REGISTRY, EID)
    assert m8oc.FROZEN_POLICY == load_admissibility_policy(REGISTRY, EID)
    assert m8oc.POWER_TARGET == 0.8
    assert m8oc.FROZEN_THRESHOLDS["type_i_criterion"] == M8_TYPE_I_CRITERION
    assert m8oc.CANONICAL_NULL_STATEMENT == M8_NULL_STATEMENT
    assert m8oc.TYPE_I_HIGH_TRIALS >= 2000       # the >= 2000 "tight CI" floor
    assert m8oc.TYPE_I_HIGH_TRIALS == 3000       # committed: margin for concentrated


# ------------------- 1. THE MECHANICAL ASSERTION (a-006 two-mode regression)

def test_copy_mode_type_i_arms_generate_concordant_schedules():
    """The COPY-mode swap-invariance null arms hold the null by construction at
    EVERY matched unit — one draw per unit copied across A/B/C exactly (byte-
    identical pair, identical marginals), no condition-dependent noise."""
    charged = {n: a for n, a in m8oc.ARMS.items()
               if a["charged"] == "type_i" and a["null_mode"] == "copy"}
    assert set(charged) == COPY_TYPE_I
    for name, arm in charged.items():
        assert arm["axes"] == {"AB": True, "AC": True}, name
        for i in range(3):
            rng = random.Random(arm["seed"] + i)
            sched = m8oc.build_schedule(arm["kind"], arm.get("per"), rng)
            counts = m8oc.verify_schedule(sched, arm["axes"], arm["null_mode"],
                                          arm.get("per"), name)
            assert counts == {"AB": 0, "AC": 0}, (name, i)
            for unit in m8oc.UNITS:
                assert sched[("A",) + unit] == sched[("B",) + unit] \
                    == sched[("C",) + unit], (name, i, unit)


def test_law_exchangeable_type_i_arms_are_swap_invariant_by_law():
    """The LAW-EXCHANGEABLE swap-invariance null arms (a-006) are charged type-I
    and verified BY LAW, not by realization: A/B/C are drawn iid from the SAME
    per-condition law, so the realizations DIFFER unit by unit (discordant > 0),
    yet the generating law is swap-invariant. verify_schedule must ACCEPT them on
    their declared null-holding axes without demanding identical realizations —
    and reject them if the declared laws are ever unequal."""
    charged = {n: a for n, a in m8oc.ARMS.items()
               if a["charged"] == "type_i"
               and a["null_mode"] == "law_exchangeable"}
    assert set(charged) == LAW_TYPE_I
    for name, arm in charged.items():
        assert arm["kind"] == "law_exch", name
        assert arm["axes"] == {"AB": True, "AC": True}, name
        assert arm["coupling"] == "iid_same_law", name
        assert arm["trials"] == m8oc.TYPE_I_HIGH_TRIALS, name
        # the declared law is swap-invariant: A == B == C
        per = arm["per"]
        assert per["A"] == per["B"] == per["C"], name
        for i in range(3):
            rng = random.Random(arm["seed"] + i)
            sched = m8oc.build_schedule(arm["kind"], per, rng)
            counts = m8oc.verify_schedule(sched, arm["axes"], arm["null_mode"],
                                          per, name)
            # A/B realizations DIFFER (drawn iid from the same law) — this is the
            # whole point — yet verification passes BY LAW, not by realization
            # identity. C copies A to hold the sham axis clean (AC concordant),
            # so the type-I characterization isolates the A/B permutation test.
            assert counts["AB"] > 0, (name, i)
            assert counts["AC"] == 0, (name, i)
            for unit in m8oc.UNITS:
                assert sched[("A",) + unit] == sched[("C",) + unit], (name, i)


def test_every_alternative_arm_violates_the_null_on_its_declared_axis():
    """The named non-exchangeable / power / sham arms must genuinely depart from
    a trivial copy where they claim to — an 'alternative' axis that holds a copy
    null separates nothing, and a copied AC axis must be concordant."""
    for name, arm in m8oc.ARMS.items():
        if arm["charged"] == "type_i":
            continue
        for i in range(3):
            rng = random.Random(arm["seed"] + i)
            sched = m8oc.build_schedule(arm["kind"], arm.get("per"), rng)
            counts = m8oc.verify_schedule(sched, arm["axes"], arm["null_mode"],
                                          arm.get("per"), name)
            for axis, null_holds in arm["axes"].items():
                if null_holds:
                    assert counts[axis] == 0, (name, i, axis)
                else:
                    assert counts[axis] >= 1, (name, i, axis)
        # the power arms hold the sham axis by copy (C copied from A)
        if arm["charged"] in ("power", "power_curve"):
            assert arm["axes"] == {"AB": False, "AC": True}, name
            assert arm["null_mode"] == "marginal_shift", name


def test_nonexchangeable_alternatives_have_equal_marginals_and_zero_tv():
    """The non-exchangeable alternatives (a-006) hold the population marginals
    EQUAL (empirical TV(A,B) = 0 exactly, via a balanced base) while the
    within-unit joint is NOT swap-symmetric (A_i != B_i at one or more units) —
    the coupling swap invariance forbids yet the marginal statistic cannot see."""
    alts = {n: a for n, a in m8oc.ARMS.items()
            if a["charged"] == "alternative_nonexchangeable"}
    assert set(alts) == NONEXCH_ALT
    for name, arm in alts.items():
        assert arm["null_mode"] == "nonexchangeable_alternative", name
        assert arm["marginals"]["equal_marginals"] is True, name
        assert arm["coupling"].startswith("nonexchangeable_"), name
        for i in range(5):
            rng = random.Random(arm["seed"] + i)
            sched = m8oc.build_schedule(arm["kind"], arm["per"], rng)
            from collections import Counter
            ca = Counter(sched[("A",) + u] for u in m8oc.UNITS)
            cb = Counter(sched[("B",) + u] for u in m8oc.UNITS)
            tv = sum(abs(ca[x] - cb[x]) for x in MENU) / 2 / len(m8oc.UNITS)
            assert tv == 0.0, (name, i, tv)            # equal marginals, TV=0
            # yet the joint is non-exchangeable: some unit differs
            assert any(sched[("A",) + u] != sched[("B",) + u]
                       for u in m8oc.UNITS), (name, i)


def test_verification_refuses_a_mislabeled_schedule():
    """The mode-specific gate: a discordant schedule may not pass as a COPY null;
    a concordant schedule may not pass as an alternative; and a LAW-EXCHANGEABLE
    null axis may not pass with unequal declared laws."""
    concordant = m8oc.build_schedule("sharp_iid", {"unit": m8oc.GRADED},
                                     random.Random(1))
    discordant = m8oc.build_schedule(
        "iid", {"A": m8oc.GRADED, "B": m8oc.GRADED, "C": m8oc.GRADED},
        random.Random(2))
    # copy-mode proof: discordant realizations cannot be a copy null
    with pytest.raises(AssertionError, match="COPY null"):
        m8oc.verify_schedule(discordant, {"AB": True, "AC": True}, "copy",
                             None, "t")
    # alternative proof: a concordant schedule cannot be an alternative
    with pytest.raises(AssertionError, match="ALTERNATIVE"):
        m8oc.verify_schedule(concordant, {"AB": False}, "copy", None, "t")
    # law-mode proof: unequal declared laws are NOT swap-invariant by law
    with pytest.raises(AssertionError, match="LAW-EXCHANGEABLE"):
        m8oc.verify_schedule(discordant, {"AB": True},
                             "law_exchangeable",
                             {"A": m8oc.GRADED, "B": m8oc.UNIFORM}, "t")
    # law-mode proof ACCEPTS the equal-law iid schedule (realizations differ)
    counts = m8oc.verify_schedule(
        discordant, {"AB": True, "AC": True}, "law_exchangeable",
        {"A": m8oc.GRADED, "B": m8oc.GRADED, "C": m8oc.GRADED}, "t")
    assert counts["AB"] > 0 and counts["AC"] > 0


def test_run_trial_verifies_before_any_analysis():
    """The verification sits INSIDE the trial path: a trial whose declared mode
    disagrees with its generated schedule refuses before any statistic exists
    (an iid process declared a COPY null must raise)."""
    with pytest.raises(AssertionError, match="COPY null"):
        m8oc.run_trial(("iid",
                        {"A": m8oc.GRADED, "B": m8oc.GRADED, "C": m8oc.GRADED},
                        {"AB": True, "AC": True}, "copy", 12345, "mislabeled"))


# ---------------------------------------- 2. branch-structure regressions
# (structural, at simulation-harness iterations — NOT the characterisation)

def test_maximally_noisy_pack_is_never_a_successful_null(tmp_path):
    """A|S1 entirely `share_resource`, A|S2 entirely `verify_first`, C identical
    to A, B entirely `decline_partnership`. A and B are EMPIRICALLY DISJOINT
    while the split-half diagnostic is maximal. The v1 rule closed the gate with
    a "successful null" here; the invariant this test protects is that it NEVER
    does so again. Under v3+ the pack is a genuine rejection — and at v4 the
    sham warrant holds trivially (C's draws are unit-identical to A's, so
    q_AC = 0 < sham_equivalence_margin)."""
    def choose(cond, variant, samp):
        if cond == "B":
            return "decline_partnership"
        return "share_resource" if samp in S1 else "verify_first"   # A and C alike

    agent = _run_pack(tmp_path, choose)
    di = agent["decision_inputs"]
    assert agent["tv_distances"] == {"A|B": 1.0, "A|C": 0.0, "null": 1.0}
    assert di["q_ac"] == 0.0 and di["tv_ac"] <= di["q_ac"]   # clause 2, part 1
    assert di["q_ac"] < di["sham_equivalence_margin"]        # clause 2, part 2 (v4)
    assert di["tv_ab"] > di["q_ab"]                          # clause 3 FIRES
    assert di["q_ab"] == 0.291667                            # rejection threshold
    assert agent["verdict"] != "no_distributional_order_effect_observed"    # THE INVARIANT
    assert agent["verdict"] == "distributional_order_effect_observed"
    # the split-half floor is still REPORTED at its maximum — and gates nothing
    assert agent["diagnostics"]["tv_null"] == 1.0
    assert "tv_null" not in di


def test_sensitivity_does_not_gate_the_positive_branch(tmp_path):
    """THE ASYMMETRY: when q_AB > min_detectable_effect the rejection must NOT
    be suppressed — sensitivity constrains only what a NON-rejection may
    assert. At n=48 the reachable q_AB caps near 0.33, below the FROZEN MDE
    of 0.35, so this test exercises the exact code branch by passing a
    thresholds bundle with a SMALLER min_detectable_effect (0.20) — forcing
    q_AB > MDE — and confirming clause 3 still fires. The frozen design is not
    touched; only this structural probe lowers the ceiling to reach the
    branch."""
    th = _sim_thresholds()
    th["min_detectable_effect"] = 0.20            # below the reachable q_AB
    agent = _run_pack(tmp_path,
                      lambda c, v, s: ("decline_partnership" if c == "B"
                                       else "share_resource"),
                      thresholds=th)
    di = agent["decision_inputs"]
    assert agent["tv_distances"]["A|B"] == 1.0
    assert di["q_ab"] == 0.291667 > 0.20        # the ceiling is genuinely exceeded
    assert di["tv_ab"] > di["q_ab"]                        # clause 3 FIRES
    assert di["tv_ac"] <= di["q_ac"]                       # clause 2 passes
    assert di["q_ac"] < di["sham_equivalence_margin"]      # v4 warrant holds
    assert agent["verdict"] == "distributional_order_effect_observed"
    assert "does not bear on a rejection" in agent["verdict_reason"]


def test_total_separation_is_reported_as_a_distributional_rejection(tmp_path):
    """A and C entirely `share_resource`, B entirely `decline_partnership` — the
    cleanest possible instrument and the most decisive possible effect. Within
    the realized pack the A and B marginals are maximally different, so the
    frozen rule rejects and the claim is stated at the population-marginal level
    only — a marginal-distribution difference, never a per-unit claim — which is
    exactly what makes the rejection honest."""
    agent = _run_pack(tmp_path, lambda c, v, s: ("decline_partnership" if c == "B"
                                                 else "share_resource"))
    di = agent["decision_inputs"]
    assert agent["tv_distances"]["A|B"] == 1.0
    assert agent["diagnostics"]["tv_null"] == 0.0      # a perfectly stable instrument
    assert di["q_ab"] == 0.291667                       # the rejection threshold
    assert di["tv_ab"] > di["q_ab"]                         # clause 3 FIRES
    assert agent["verdict"] == "distributional_order_effect_observed"
    assert agent["verdict"] != "no_distributional_order_effect_observed"   # never a false null
    reason = agent["verdict_reason"]
    # a-006: the claim is the within-unit swap-invariance rejection, with the
    # marginal TV as the effect-size estimand and NO per-unit claim
    assert "swap-invariance null is rejected" in reason
    assert "effect-size" in reason and "not a per-unit claim" in reason


def test_shared_latent_swap_invariant_process_reports_null_not_rejection(tmp_path):
    """The HONEST half of the shared-latent family: a pack-level latent mode
    moves every unit's action, but identically in A, B and C — the pair is
    byte-identical, so swap invariance is TRUE (and the process is dependent
    across units). The frozen rule must not reject."""
    sched = m8oc.build_schedule("sharp_latent", None, random.Random(4))
    agent = _run_pack(tmp_path, _sched_choose(sched))
    di = agent["decision_inputs"]
    assert di["tv_ab"] == 0.0 and di["tv_ac"] == 0.0
    assert agent["verdict"] == "no_distributional_order_effect_observed"


def test_a_quiet_instrument_still_reaches_both_substantive_verdicts(tmp_path):
    """Both substantive verdicts remain reachable on a quiet instrument, with
    q_AB comfortably below the ceiling and the v4 sham warrant held."""
    null_agent = _run_pack(tmp_path / "null", lambda c, v, s: "share_resource")
    assert null_agent["decision_inputs"]["q_ab"] == 0.0
    assert null_agent["verdict"] == "no_distributional_order_effect_observed"
    assert "equivalence warrant" in null_agent["verdict_reason"]

    def positive(cond, variant, samp):
        i = list(m8oc.SAMPLER_SEEDS).index(samp)
        if cond == "B" and i % 3 == 0:
            return "decline_partnership"
        return MENU[i % 4]

    pos = _run_pack(tmp_path / "pos", positive)
    di = pos["decision_inputs"]
    assert pos["diagnostics"]["tv_null"] == 0.0
    assert di["q_ab"] <= MDE                    # sensitivity warrant present
    assert di["q_ac"] < di["sham_equivalence_margin"]
    assert di["tv_ab"] > di["q_ab"]
    assert pos["verdict"] == "distributional_order_effect_observed"


def test_nonexchangeable_coupling_holds_the_marginal_test_at_null(tmp_path):
    """THE DOCUMENTED LIMITATION, exercised end to end: a non-exchangeable
    equal-marginal coupling (B_i = perm(A_i), balanced base) drives the real
    frozen rule and the marginal test sees TV(A,B) = 0 — the rule returns the
    null verdict even though swap invariance is genuinely FALSE. This is why
    TV=0 is never evidence the null holds."""
    arm = m8oc.ARMS["alternative_nonexch_cycle4"]
    sched = m8oc.build_schedule(arm["kind"], arm["per"], random.Random(7))
    agent = _run_pack(tmp_path, _sched_choose(sched))
    di = agent["decision_inputs"]
    assert di["tv_ab"] == 0.0                    # the marginal statistic is blind
    assert agent["verdict"] == "no_distributional_order_effect_observed"


# --------------------------------- 3. the study harness itself is deterministic

def test_study_trial_is_deterministic_at_the_frozen_parameters():
    """Same trial seed, same verdict — `random.Random` only, no global RNG, so
    the committed characterisation regenerates. One trial at the FROZEN 10 000
    iterations (this is the only slow item in CI, by design ~4 s)."""
    arm = m8oc.ARMS["power_at_tv_025"]
    spec = (arm["kind"], arm["per"], arm["axes"], arm["null_mode"],
            arm["seed"], "det")
    assert m8oc.run_trial(spec) == m8oc.run_trial(spec)


def test_clopper_pearson_matches_known_values():
    """The interval implementation the artifact's bounds rest on: exact CP
    against independently known reference values."""
    lo, hi = m8oc.clopper_pearson(20, 400)      # p-hat = alpha = 0.05
    assert lo == pytest.approx(0.0308, abs=2e-3)
    assert hi == pytest.approx(0.0762, abs=2e-3)
    # the resolution claim in the artifact's ci_method: half-width < alpha
    assert (hi - lo) / 2 < 0.05
    assert m8oc.clopper_pearson(0, 200) == (0.0, pytest.approx(0.0183, abs=2e-3))
    # the type-I criterion's actual operating point: k=0 at n=400
    assert m8oc.clopper_pearson(0, 400) == (0.0, pytest.approx(0.0092, abs=2e-3))
    lo1, hi1 = m8oc.clopper_pearson(400, 400)
    assert lo1 == pytest.approx(0.9908, abs=2e-3) and hi1 == 1.0


def test_the_power_grid_distributions_carry_their_exact_effects():
    """TV(base, shifted) equals the named grid effect EXACTLY — the grid is
    part of the frozen MDE-selection method, so it must not drift."""
    def tv(p, q):
        return round(sum(abs(a - b) for a, b in zip(p, q)) / 2, 10)
    for eff, dist in m8oc.POWER_B.items():
        assert tv(m8oc.GRADED, dist) == eff, eff
        assert round(sum(dist), 10) == 1.0
    assert tv(m8oc.HALF_AB, m8oc.HALF_CD) == 1.0
    assert tuple(m8oc.POWER_GRID) == (0.25, 0.35, 0.50, 0.75, 1.0)


# ------------------------------------- 4. THE COMMITTED ARTIFACT (regression)

@pytest.fixture(scope="module")
def artifact():
    assert os.path.exists(ARTIFACT), (
        "the committed operating-characteristics artifact is missing — run "
        "scripts/m8_operating_characteristics.py and commit its output")
    with open(ARTIFACT, encoding="utf-8") as fh:
        return json.load(fh)


def test_artifact_was_produced_under_the_exact_frozen_bundle(artifact):
    """THE AUDIT'S BINDING: the characterisation loads the same frozen
    threshold bundle as production — including the a-004 fitness criteria —
    asserted by ECHO EQUALITY against the registry-served bundle and by
    content-address equality."""
    registry_thresholds = load_thresholds(REGISTRY, EID)
    registry_policy = load_admissibility_policy(REGISTRY, EID)
    echo = artifact["frozen_bundle"]
    assert echo["thresholds"] == registry_thresholds
    assert echo["admissibility_policy"] == registry_policy
    assert echo["thresholds"]["permutation_iterations"] == 10000
    assert echo["thresholds"]["bootstrap_iterations"] == 10000
    assert echo["thresholds"]["sham_equivalence_margin"] == 0.25
    assert echo["thresholds"]["max_surviving_delta"] == 2
    assert echo["thresholds"]["power_target"] == 0.8
    assert echo["thresholds"]["type_i_criterion"] == M8_TYPE_I_CRITERION
    assert echo["terminal_dp_id"] == "d_partner"
    assert echo["conditions"] == m8oc.CONDITIONS
    # content-addressed: the echo hashes to what the artifact claims, and to
    # what the production bundle hashes to
    assert artifact["frozen_bundle_hashes"]["thresholds_hash"] == \
        config_hash(echo["thresholds"]) == config_hash(registry_thresholds)
    assert artifact["frozen_bundle_hashes"]["policy_hash"] == \
        config_hash(echo["admissibility_policy"]) == config_hash(registry_policy)
    # produced by the rule version under test, at full scale
    assert artifact["order_report_version"] == "6"
    assert artifact["metrics_version"] == "1"
    assert artifact["trials_scale"] == 1.0


def test_artifact_echoes_the_one_canonical_null_verbatim(artifact):
    """a-006: the canonical swap-invariance null-form assertion is shared by
    registry, preregistration, loader, report and artifact. Here: the artifact
    echoes null_form and the exact statement, and declares the mode-specific
    unit-by-unit schedule verification."""
    assert artifact["null_form"] == "swap_invariance"
    assert artifact["null_statement"] == M8_NULL_STATEMENT
    raw = load_experiments_registry(REGISTRY)
    pd = next(e for e in raw["experiments"]
              if e["experiment_id"] == EID)["planned_design"]
    assert artifact["null_statement"] == pd["null_statement"]
    assert "unit-by-unit" in artifact["schedule_verification"]
    assert "BEFORE" in artifact["schedule_verification"]
    assert "LAW" in artifact["schedule_verification"]
    assert "IDENTICAL REALIZATION" in artifact["schedule_verification"]


def test_artifact_arms_are_structurally_sound(artifact):
    arms = artifact["arms"]
    assert set(arms) == set(m8oc.ARMS)
    for name, arm in arms.items():
        declared = m8oc.ARMS[name]
        assert arm["trials"] == declared["trials"], name
        assert arm["seed"] == declared["seed"], name
        assert arm["charged"] == declared["charged"], name
        assert arm["null_mode"] == declared["null_mode"], name
        assert arm["coupling"] == declared["coupling"], name
        assert arm["null_axes"] == declared["axes"], name
        # every arm keys on BOTH marginals and coupling
        assert "equal_marginals" in arm["marginals"], name
        assert sum(arm["tally"].values()) == arm["trials"], name
        k = arm["tally"].get("distributional_order_effect_observed", 0)
        assert arm["positive_rate"] == round(k / arm["trials"], 6), name
        # the interval recomputes exactly from the tally
        assert tuple(arm["positive_rate_ci95"]) == \
            m8oc.clopper_pearson(k, arm["trials"]), name


def test_artifact_type_i_satisfies_the_frozen_upper_bound_criterion(artifact):
    """a-006: EVERY arm charged type_i — copy-mode AND law-exchangeable-mode —
    has its exact CP-95 UPPER bound of the swap-invariance-null rejection rate at
    or below alpha = 0.05, judged against the frozen criterion string. Copy-mode
    arms are structural zeros (identical schedules, rate exactly 0). Law-
    exchangeable arms carry a small non-zero rate whose CP-95 upper bound must
    still fall at or below alpha, resolved at 3000 trials. NOTHING is weakened to
    pass: if any charged arm's upper bound exceeded alpha this assertion would
    FAIL rather than reclassify the arm."""
    charged = {n: a for n, a in artifact["arms"].items()
               if a["charged"] == "type_i"}
    assert set(charged) == COPY_TYPE_I | LAW_TYPE_I
    for name, arm in charged.items():
        lo, hi = arm["positive_rate_ci95"]
        assert hi <= 0.05, (name, arm["positive_rate"], arm["positive_rate_ci95"])
        assert arm["criterion"]["pass"] is True, name
        assert arm["criterion"]["statement"] == M8_TYPE_I_CRITERION, name
        if arm["null_mode"] == "copy":
            assert arm["trials"] == 400, name
            # structural zero, stated exactly
            assert arm["tally"] == \
                {"no_distributional_order_effect_observed": 400}, name
            assert arm["positive_rate"] == 0.0, name
        else:
            assert arm["null_mode"] == "law_exchangeable", name
            assert arm["trials"] == m8oc.TYPE_I_HIGH_TRIALS, name


def test_iid_equal_marginal_arms_are_charged_type_i_law_exchangeable(artifact):
    """a-006 core reclassification: the iid equal-marginal arms are jointly
    exchangeable swap-invariance null cases (A/B/C iid from ONE per-condition
    law) and are CHARGED type-I in law-exchangeable mode — not relabeled context.
    Their realizations differ but the generating law is swap-invariant, so the
    within-pair permutation test is empirically conservative and its CP-95 upper
    bound sits at or below alpha."""
    law = {n: a for n, a in artifact["arms"].items()
           if a["null_mode"] == "law_exchangeable"}
    assert set(law) == LAW_TYPE_I
    for name, arm in law.items():
        assert arm["charged"] == "type_i", name
        assert arm["coupling"] == "iid_same_law", name
        assert arm["marginals"]["equal_marginals"] is True, name
        # A == B == C marginals (equal by law)
        assert arm["marginals"]["A"] == arm["marginals"]["B"] \
            == arm["marginals"]["C"], name
        assert arm["null_axes"] == {"AB": True, "AC": True}, name
        assert arm["trials"] == m8oc.TYPE_I_HIGH_TRIALS, name
        # conservative: the exact CP-95 upper bound is at or below alpha
        assert arm["positive_rate_ci95"][1] <= 0.05, (name, arm)
        assert "LAW-EXCHANGEABLE" in arm["criterion"]["detail"], name


def test_artifact_power_meets_the_frozen_target_at_the_frozen_mde(artifact):
    """a-004 finding 1: the frozen power criterion — the CP-95 LOWER bound of
    measured power at min_detectable_effect reaches power_target = 0.8 — is
    met by the committed run at the exact frozen procedure."""
    mde = load_thresholds(REGISTRY, EID)["min_detectable_effect"]
    target = load_thresholds(REGISTRY, EID)["power_target"]
    charged = [a for a in artifact["arms"].values() if a["charged"] == "power"]
    assert len(charged) == 1
    arm = charged[0]
    assert arm["effect_tv"] == mde
    assert arm["trials"] == 400
    lo, hi = arm["positive_rate_ci95"]
    assert lo >= target, arm
    assert arm["criterion"]["pass"] is True
    assert arm["criterion"]["power_target"] == target == 0.8


def test_mde_selection_regenerates_from_the_committed_run(artifact):
    """The frozen min_detectable_effect is DERIVED, not asserted: the smallest
    grid effect whose measured power CP-95 lower bound reaches power_target,
    recomputed here from the artifact's own power curve."""
    sel = artifact["mde_selection"]
    assert sel["grid"] == [0.25, 0.35, 0.50, 0.75, 1.0]
    assert sel["power_target"] == 0.8
    curve = sel["power_curve"]
    assert [r["effect_tv"] for r in curve] == sel["grid"]
    eligible = [r["effect_tv"] for r in curve
                if r["positive_rate_ci95"][0] >= sel["power_target"]]
    assert eligible, "no grid effect met the frozen power target"
    assert sel["selected_effect"] == min(eligible)
    frozen_mde = load_thresholds(REGISTRY, EID)["min_detectable_effect"]
    assert sel["frozen_min_detectable_effect"] == frozen_mde
    assert sel["selected_effect"] == frozen_mde
    assert sel["consistent"] is True
    # the curve entries mirror the arms exactly
    by_name = artifact["arms"]
    for r in curve:
        arm = by_name[r["arm"]]
        assert arm["effect_tv"] == r["effect_tv"]
        assert arm["positive_rate"] == r["positive_rate"]
        assert arm["positive_rate_ci95"] == r["positive_rate_ci95"]
    # power does not decrease from the frozen boundary to the endpoint
    assert curve[-1]["positive_rate"] >= \
        next(r for r in curve
             if r["effect_tv"] == frozen_mde)["positive_rate"]


def test_artifact_reports_nonexchangeable_alternatives_for_what_they_are(artifact):
    """a-006: the non-exchangeable equal-marginal couplings — swap invariance
    genuinely FALSE but the marginal TV statistic identically zero — must be
    present, must NOT be charged against type-I, and must show the rule
    essentially never rejecting (the documented outside-null limitation, not a
    type-I failure)."""
    alts = {n: a for n, a in artifact["arms"].items()
            if a["charged"] == "alternative_nonexchangeable"}
    assert set(alts) == NONEXCH_ALT
    for name, arm in alts.items():
        assert arm["charged"] != "type_i", name
        assert arm["null_mode"] == "nonexchangeable_alternative", name
        assert arm["coupling"].startswith("nonexchangeable_"), name
        assert arm["marginals"]["equal_marginals"] is True, name
        # essentially never rejects — TV(A,B) is identically zero
        assert arm["positive_rate"] <= 0.02, (name, arm)
        st = arm["criterion"]["statement"]
        assert "NON-EXCHANGEABLE" in st and "TV(A,B) = 0" in st
        assert "NEVER charged against type-I" in st
        assert "outside-null" in st


def test_artifact_reports_sham_gate_leakage_as_context(artifact):
    """The sham-gate residual leakage over a contaminated-at-MARGIN sham
    process — contamination at the exact scale the clause-2 warrant polices
    (q_AC < sham_equivalence_margin = 0.25), the most probative leakage test —
    is reported with its CI as CONTEXT. The frozen fitness criteria are exactly
    type_i_criterion and power_target; the statement names the deterministic
    observation-level guarantees pinned in the test suite (the boundary pack
    never promotes; every positive carries the warrant)."""
    arm = artifact["arms"]["sham_contaminated_at_margin"]
    assert arm["charged"] == "sham_gate_context"
    assert "LEAKAGE" in arm["criterion"]["statement"]
    assert "test suite" in arm["criterion"]["statement"]
    assert "boundary pack" in arm["criterion"]["statement"]
    # process-level leakage stays at sampling-noise scale — an order of
    # magnitude below the power the same rule delivers on the A/B axis
    assert arm["positive_rate"] <= 0.10, arm


def test_artifact_states_the_ci_math_and_measured_runtime(artifact):
    """The prereg requires the trial-count math stated and this build requires
    runtime measured — both live in the artifact, not in a docstring."""
    ci = artifact["ci_method"]
    assert ci["outer_trials_per_charged_arm"] == 400
    assert ci["type_i_high_trials"] == m8oc.TYPE_I_HIGH_TRIALS >= 2000
    assert "Clopper-Pearson" in ci["interval"]
    assert "3000" in ci["math"] and "400" in ci["math"]
    assert "0.8" in ci["math"]           # the power target's resolvability too
    assert artifact["runtime"]["seconds"] > 0
    assert artifact["all_criteria_pass"] is True
