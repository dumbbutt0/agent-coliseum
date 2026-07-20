"""m8 Phase-2 — frozen operating characteristics of the finite-sample decision rule.

RESTRUCTURED AT THE a-004 SCIENTIFIC RE-FREEZE. The audit blocked the previous
shape of this characterisation on two grounds, and this module regresses the
repairs:

* Finding 0 — ONE NULL. The iid equal-marginal packs previously charged as
  sharp-null type-I arms violate the sharp null in every generated trial (the
  independent probe measured 27-44 discordant units per pack). The sharp-null
  H0 arms now generate each unit's terminal action ONCE and copy it across
  A/B/C exactly, every schedule is MECHANICALLY verified unit-by-unit before
  analysis, and the iid arms are relabeled exchangeability-robustness context,
  never charged as type-I. The canonical null statement is echoed verbatim by
  the committed artifact and anchored in registry.M8_NULL_STATEMENT.

* Finding 1 — FROZEN CRITERIA, honest directions. The fitness criteria live
  in planned_design.thresholds (power_target = 0.8; type_i_criterion = the
  CP-95 UPPER-bound rule), loaded from the registry — never invented in the
  script — and min_detectable_effect is frozen as the smallest power-grid
  effect whose measured power CP-95 LOWER bound reaches power_target. The
  artifact's mde_selection block recomputes that choice so the frozen value
  regenerates from the committed run alone.

The characterisation lives in TWO places with a clean division of labour:
`scripts/m8_operating_characteristics.py` runs the SLOW study at the exact
frozen decision parameters (10 000 permutation/bootstrap iterations, 400
outer trials per charged arm) and writes the committed artifact
`derived/textlab/m8-operating-characteristics.json`; THIS module is fast —
structural branch regressions at simulation-harness iteration counts (clearly
NOT the characterisation) plus the CI regression on the committed artifact.
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
# ORDER_REPORT_VERSION == "4" and CANONICAL_NULL_STATEMENT == the audited
# registry.M8_NULL_STATEMENT anchor.
_spec = importlib.util.spec_from_file_location("m8oc", SCRIPT)
m8oc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m8oc)

# simulation-harness values for the STRUCTURAL tests only — the committed
# characterisation uses the frozen 10 000s (see the module docstring)
_SIM_ITERATIONS = 300


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


# ------------------- 1. THE MECHANICAL ASSERTION (a-004 finding 0 regression)

def test_every_sharp_null_arm_generates_concordant_schedules():
    """For each arm charged type_i, the generated potential-outcome schedule
    satisfies the canonical sharp null at EVERY matched unit — one draw per
    unit, copied across A/B/C exactly, no condition-dependent noise."""
    charged = {n: a for n, a in m8oc.ARMS.items() if a["charged"] == "type_i"}
    assert set(charged) == {"sharp_h0_iid_uniform", "sharp_h0_iid_graded",
                            "sharp_h0_iid_concentrated",
                            "sharp_h0_shared_latent"}
    for name, arm in charged.items():
        assert arm["axes"] == {"AB": True, "AC": True}, name
        for i in range(3):
            rng = random.Random(arm["seed"] + i)
            sched = m8oc.build_schedule(arm["kind"], arm.get("per"), rng)
            counts = m8oc.verify_schedule(sched, arm["axes"], name)
            assert counts == {"AB": 0, "AC": 0}, (name, i)
            for unit in m8oc.UNITS:
                assert sched[("A",) + unit] == sched[("B",) + unit] \
                    == sched[("C",) + unit], (name, i, unit)


def test_every_alternative_arm_violates_the_null_on_its_declared_axis():
    """The named separating/context/power arms must genuinely violate the
    sharp null where they claim to — an 'alternative' that satisfies the null
    separates nothing."""
    for name, arm in m8oc.ARMS.items():
        if arm["charged"] == "type_i":
            continue
        for i in range(3):
            rng = random.Random(arm["seed"] + i)
            sched = m8oc.build_schedule(arm["kind"], arm.get("per"), rng)
            counts = m8oc.verify_schedule(sched, arm["axes"], name)
            for axis, null_holds in arm["axes"].items():
                if null_holds:
                    assert counts[axis] == 0, (name, i, axis)
                else:
                    assert counts[axis] >= 1, (name, i, axis)
        # the power arms hold the sham axis SHARPLY null (C copied from A)
        if arm["charged"] in ("power", "power_curve"):
            assert arm["axes"] == {"AB": False, "AC": True}, name


def test_verification_refuses_a_mislabeled_schedule():
    """The gate itself: a discordant schedule may not pass as a null arm, and
    a concordant schedule may not pass as an alternative."""
    rng = random.Random(1)
    concordant = m8oc.build_schedule("sharp_iid", {"unit": m8oc.GRADED}, rng)
    discordant = m8oc.build_schedule(
        "iid", {"A": m8oc.GRADED, "B": m8oc.GRADED, "C": m8oc.GRADED},
        random.Random(2))
    with pytest.raises(AssertionError, match="SHARP-NULL TRUE"):
        m8oc.verify_schedule(discordant, {"AB": True, "AC": True}, "t")
    with pytest.raises(AssertionError, match="ALTERNATIVE"):
        m8oc.verify_schedule(concordant, {"AB": False}, "t")


def test_run_trial_verifies_before_any_analysis():
    """The verification sits INSIDE the trial path: a trial whose declared
    axes disagree with its generated schedule refuses before any statistic
    exists (an iid process declared sharp-null true must raise)."""
    with pytest.raises(AssertionError, match="SHARP-NULL TRUE"):
        m8oc.run_trial(("iid",
                        {"A": m8oc.GRADED, "B": m8oc.GRADED, "C": m8oc.GRADED},
                        {"AB": True, "AC": True}, 12345, "mislabeled"))


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
    assert agent["verdict"] != "no_order_effect_observed"    # THE INVARIANT
    assert agent["verdict"] == "order_effect_observed"
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
    assert agent["verdict"] == "order_effect_observed"
    assert "does not bear on a rejection" in agent["verdict_reason"]


def test_total_separation_is_reported_as_a_sharp_unit_level_rejection(tmp_path):
    """A and C entirely `share_resource`, B entirely `decline_partnership` — the
    cleanest possible instrument and the most decisive possible effect. This is
    ALSO the separating process at a fixed latent mode: the marginal
    distributions of the PROCESS are equal across modes, but every unit is
    order-dependent — the sharp null is genuinely FALSE. The frozen rule
    rejects, and the claim is stated at the unit level with the marginal
    limitation, which is exactly what makes the rejection honest."""
    agent = _run_pack(tmp_path, lambda c, v, s: ("decline_partnership" if c == "B"
                                                 else "share_resource"))
    di = agent["decision_inputs"]
    assert agent["tv_distances"]["A|B"] == 1.0
    assert agent["diagnostics"]["tv_null"] == 0.0      # a perfectly stable instrument
    assert di["q_ab"] == 0.291667                       # the rejection threshold
    assert di["tv_ab"] > di["q_ab"]                         # clause 3 FIRES
    assert agent["verdict"] == "order_effect_observed"
    assert agent["verdict"] != "no_order_effect_observed"   # never a false null
    reason = agent["verdict_reason"]
    assert "SHARP" in reason and "unit" in reason
    assert "does not establish that the marginal" in reason
    assert "distribution changed" not in reason


def test_shared_latent_sharp_true_process_reports_null_not_rejection(tmp_path):
    """The HONEST half of the shared-latent family: a pack-level latent mode
    moves every unit's action, but identically in A, B and C — order made no
    difference to any unit, so the sharp null is TRUE (and the process is
    dependent across units). The frozen rule must not reject."""
    sched = m8oc.build_schedule("sharp_latent", None, random.Random(4))
    agent = _run_pack(tmp_path, _sched_choose(sched))
    di = agent["decision_inputs"]
    assert di["tv_ab"] == 0.0 and di["tv_ac"] == 0.0
    assert agent["verdict"] == "no_order_effect_observed"


def test_a_quiet_instrument_still_reaches_both_substantive_verdicts(tmp_path):
    """Both substantive verdicts remain reachable on a quiet instrument, with
    q_AB comfortably below the ceiling and the v4 sham warrant held."""
    null_agent = _run_pack(tmp_path / "null", lambda c, v, s: "share_resource")
    assert null_agent["decision_inputs"]["q_ab"] == 0.0
    assert null_agent["verdict"] == "no_order_effect_observed"
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
    assert pos["verdict"] == "order_effect_observed"


# --------------------------------- 3. the study harness itself is deterministic

def test_study_trial_is_deterministic_at_the_frozen_parameters():
    """Same trial seed, same verdict — `random.Random` only, no global RNG, so
    the committed characterisation regenerates. One trial at the FROZEN 10 000
    iterations (this is the only slow item in CI, by design ~4 s)."""
    arm = m8oc.ARMS["power_at_tv_025"]
    spec = (arm["kind"], arm["per"], arm["axes"], arm["seed"], "det")
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
    assert artifact["order_report_version"] == "4"
    assert artifact["metrics_version"] == "1"
    assert artifact["trials_scale"] == 1.0


def test_artifact_echoes_the_one_canonical_null_verbatim(artifact):
    """a-004 finding 0 minimum_regression: the canonical null-form assertion
    is shared by registry, preregistration, loader, report and artifact. Here:
    the artifact echoes null_form and the exact statement, and declares the
    unit-by-unit schedule verification."""
    assert artifact["null_form"] == "sharp"
    assert artifact["null_statement"] == M8_NULL_STATEMENT
    raw = load_experiments_registry(REGISTRY)
    pd = next(e for e in raw["experiments"]
              if e["experiment_id"] == EID)["planned_design"]
    assert artifact["null_statement"] == pd["null_statement"]
    assert "unit-by-unit" in artifact["schedule_verification"]
    assert "BEFORE" in artifact["schedule_verification"]


def test_artifact_arms_are_structurally_sound(artifact):
    arms = artifact["arms"]
    assert set(arms) == set(m8oc.ARMS)
    for name, arm in arms.items():
        declared = m8oc.ARMS[name]
        assert arm["trials"] == declared["trials"], name
        assert arm["seed"] == declared["seed"], name
        assert arm["charged"] == declared["charged"], name
        assert arm["sharp_null_axes"] == declared["axes"], name
        assert sum(arm["tally"].values()) == arm["trials"], name
        k = arm["tally"].get("order_effect_observed", 0)
        assert arm["positive_rate"] == round(k / arm["trials"], 6), name
        # the interval recomputes exactly from the tally
        assert tuple(arm["positive_rate_ci95"]) == \
            m8oc.clopper_pearson(k, arm["trials"]), name


def test_artifact_type_i_satisfies_the_frozen_upper_bound_criterion(artifact):
    """a-004 finding 1: for every arm charged type_i, the exact CP-95 UPPER
    bound of the sharp-null rejection rate is at or below alpha = 0.05, judged
    against the frozen criterion string. Under the canonical sharp null with
    seeded decoding the schedules are condition-invariant, so the rate is
    structurally ZERO — pinned exactly, since the study is deterministic."""
    charged = {n: a for n, a in artifact["arms"].items()
               if a["charged"] == "type_i"}
    assert set(charged) == {"sharp_h0_iid_uniform", "sharp_h0_iid_graded",
                            "sharp_h0_iid_concentrated",
                            "sharp_h0_shared_latent"}
    for name, arm in charged.items():
        lo, hi = arm["positive_rate_ci95"]
        assert hi <= 0.05, (name, arm)
        assert arm["criterion"]["pass"] is True, name
        assert arm["criterion"]["statement"] == M8_TYPE_I_CRITERION, name
        assert arm["trials"] == 400, name
        # structural zero, stated exactly: every trial returned the warranted
        # null verdict and none rejected
        assert arm["tally"] == {"no_order_effect_observed": 400}, name
        assert arm["positive_rate"] == 0.0, name


def test_iid_equal_marginal_arms_are_context_never_type_i(artifact):
    """a-004 finding 0: the relabeling itself. The iid equal-marginal arms are
    exchangeability-robustness context — present, reported with CIs, and
    never charged as sharp-null type-I."""
    context = {n: a for n, a in artifact["arms"].items()
               if a["charged"] == "exchangeable_context"}
    assert set(context) == {"iid_equal_marginals_uniform",
                            "iid_equal_marginals_graded",
                            "iid_equal_marginals_concentrated"}
    for name, arm in context.items():
        assert arm["charged"] != "type_i"
        assert "never sharp-null type-I" in arm["criterion"]["statement"] \
            or "not sharp-null false-positive" in arm["criterion"]["statement"]
        assert arm["sharp_null_axes"] == {"AB": False, "AC": False}, name
        # exchangeable pair distribution: rejection stays at or below ~alpha
        # for the broader family (upper CI bounded well below 3*alpha)
        assert arm["positive_rate_ci95"][1] <= 0.15, (name, arm)


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


def test_artifact_reports_the_sharp_violation_arm_for_what_it_is(artifact):
    """The audit's separating process — sharp null FALSE, marginal null true —
    must be present, must NOT be charged against type-I, and must show the rule
    rejecting essentially always (which is the correct sharp-null conclusion,
    licensed by the claim ceiling)."""
    arm = artifact["arms"]["sharp_false_marginal_true"]
    assert arm["charged"] == "sharp_violation_detection"
    assert arm["positive_rate"] >= 0.95
    assert "sharp" in arm["criterion"]["statement"]
    assert "Not charged against type-I" in arm["criterion"]["statement"]


def test_artifact_reports_sham_gate_leakage_as_context(artifact):
    """The sham-gate residual leakage over a contaminated-at-MARGIN sham
    process — contamination at the exact scale the clause-2 warrant polices
    (q_AC < sham_equivalence_margin = 0.25), the most probative leakage test —
    is reported with its CI as CONTEXT. The frozen fitness criteria are
    exactly type_i_criterion and power_target; the statement names the
    deterministic observation-level guarantees pinned in the test suite (the
    boundary pack never promotes; every positive carries the warrant)."""
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
    assert "Clopper-Pearson" in ci["interval"]
    assert "0.10" in ci["math"] and "400" in ci["math"]
    assert "0.8" in ci["math"]           # the power target's resolvability too
    assert artifact["runtime"]["seconds"] > 0
    assert artifact["all_criteria_pass"] is True
