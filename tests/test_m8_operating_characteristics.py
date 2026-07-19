"""m8 Phase-2 — frozen operating characteristics of the finite-sample decision rule.

RESTRUCTURED AT ORDER_REPORT_VERSION 4 (audit 001814 finding 2). The audit
blocked the previous shape of this module: it substituted 300 for the frozen
10 000 permutation/bootstrap iterations and used 40 outer trials per arm — too
few to distinguish a 0.05 false-positive rate from ~0.10 — so it did not
characterise the procedure it claimed to characterise.

The characterisation now lives in TWO places with a clean division of labour:

* `scripts/m8_operating_characteristics.py` runs the SLOW study — the exact
  frozen decision parameters (permutation_iterations = 10 000,
  bootstrap_iterations = 10 000), 400 outer trials per H0 arm (enough for the
  exact Clopper-Pearson 95% interval to resolve alpha from 2*alpha — the math
  is stated in the script and echoed in the artifact), null families that
  include the dependent shared-latent processes from audit 001814 finding 0,
  power at the min_detectable_effect boundary, and the sham-adequacy gate —
  and writes the COMMITTED artifact
  `derived/textlab/m8-operating-characteristics.json`.

* THIS module is fast: structural regressions that pin the decision rule's
  branch behaviour directly (single reports, simulation-harness iteration
  counts, clearly labelled as NOT the characterisation), plus the CI
  regression on the committed artifact — asserting it was produced under the
  EXACT frozen bundle the production path loads from the registry (echo
  equality and hash equality), that its intervals recompute, and that its
  rates satisfy the frozen fitness criteria. The slow study itself is invoked
  by the script, never by CI.
"""
import importlib.util
import json
import os
import random

import pytest

from coliseum.textlab.metrics import order_sensitivity_report
from coliseum.textlab.registry import (load_admissibility_policy,
                                       load_thresholds)
from coliseum.textlab.schema import config_hash

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "configs", "registry", "experiments.yaml")
EID = "m8-phase2-live-order-sensitivity"
ARTIFACT = os.path.join(ROOT, "derived", "textlab",
                        "m8-operating-characteristics.json")
SCRIPT = os.path.join(ROOT, "scripts", "m8_operating_characteristics.py")

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


# ---------------------------------------- 1. branch-structure regressions
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
    assert di["q_ab"] == 0.291667 > MDE                      # irrelevant to a rejection
    assert agent["verdict"] != "no_order_effect_observed"    # THE INVARIANT
    assert agent["verdict"] == "order_effect_observed"
    # the split-half floor is still REPORTED at its maximum — and gates nothing
    assert agent["diagnostics"]["tv_null"] == 1.0
    assert "tv_null" not in di


def test_sensitivity_does_not_gate_the_positive_branch(tmp_path):
    """THE ASYMMETRY: q_AB > min_detectable_effect must not suppress a genuine
    rejection — sensitivity constrains only what a NON-rejection may assert."""
    def choose(cond, variant, samp):
        if cond == "B":
            return "decline_partnership"
        if samp in S1:
            return "share_resource"
        return "share_resource" if samp % 2 else "verify_first"     # A and C alike

    agent = _run_pack(tmp_path, choose)
    di = agent["decision_inputs"]
    assert agent["tv_distances"]["A|B"] == 1.0
    assert di["q_ab"] > MDE                     # the ceiling is genuinely exceeded
    assert di["tv_ab"] > di["q_ab"]                         # clause 3 FIRES
    assert di["tv_ac"] <= di["q_ac"]                        # clause 2 passes
    assert di["q_ac"] < di["sham_equivalence_margin"]       # v4 warrant holds
    assert agent["verdict"] == "order_effect_observed"
    assert "does not bear on a rejection" in agent["verdict_reason"]


def test_total_separation_is_reported_as_a_sharp_unit_level_rejection(tmp_path):
    """A and C entirely `share_resource`, B entirely `decline_partnership` — the
    cleanest possible instrument and the most decisive possible effect. This is
    ALSO the audit 001814 finding-0 separating process at a fixed latent mode:
    the marginal distributions of the PROCESS are equal across modes, but every
    unit is order-dependent — the sharp null is genuinely FALSE. The frozen rule
    rejects, and at v4 the claim is stated at the unit level with the marginal
    limitation, which is exactly what makes the rejection honest."""
    agent = _run_pack(tmp_path, lambda c, v, s: ("decline_partnership" if c == "B"
                                                 else "share_resource"))
    di = agent["decision_inputs"]
    assert agent["tv_distances"]["A|B"] == 1.0
    assert agent["diagnostics"]["tv_null"] == 0.0      # a perfectly stable instrument
    assert di["q_ab"] == 0.291667 > MDE
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
    rng = random.Random(4)
    choose = m8oc._choose_fn("latent_true", None, rng)
    agent = _run_pack(tmp_path, choose)
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


# --------------------------------- 2. the study harness itself is deterministic

def test_study_trial_is_deterministic_at_the_frozen_parameters():
    """Same trial seed, same verdict — `random.Random` only, no global RNG, so
    the committed characterisation regenerates. One trial at the FROZEN 10 000
    iterations (this is the only slow item in CI, by design ~4 s)."""
    spec = ("iid", {"A": m8oc.GRADED, "B": m8oc.POWER_B_MDE, "C": m8oc.GRADED},
            m8oc.ARMS["power_at_mde"]["seed"])
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
    lo1, hi1 = m8oc.clopper_pearson(400, 400)
    assert lo1 == pytest.approx(0.9908, abs=2e-3) and hi1 == 1.0


# ------------------------------------- 3. THE COMMITTED ARTIFACT (regression)

@pytest.fixture(scope="module")
def artifact():
    assert os.path.exists(ARTIFACT), (
        "the committed operating-characteristics artifact is missing — run "
        "scripts/m8_operating_characteristics.py and commit its output")
    with open(ARTIFACT, encoding="utf-8") as fh:
        return json.load(fh)


def test_artifact_was_produced_under_the_exact_frozen_bundle(artifact):
    """THE AUDIT'S BINDING (001814 finding 2 minimum_regression): the
    characterisation loads the same frozen threshold bundle as production —
    including permutation_iterations = 10000 — asserted by ECHO EQUALITY
    against the registry-served bundle and by content-address equality."""
    registry_thresholds = load_thresholds(REGISTRY, EID)
    registry_policy = load_admissibility_policy(REGISTRY, EID)
    echo = artifact["frozen_bundle"]
    assert echo["thresholds"] == registry_thresholds
    assert echo["admissibility_policy"] == registry_policy
    assert echo["thresholds"]["permutation_iterations"] == 10000
    assert echo["thresholds"]["bootstrap_iterations"] == 10000
    assert echo["thresholds"]["sham_equivalence_margin"] == 0.25
    assert echo["thresholds"]["max_surviving_delta"] == 2
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


def test_artifact_arms_are_structurally_sound(artifact):
    arms = artifact["arms"]
    assert set(arms) == set(m8oc.ARMS)
    for name, arm in arms.items():
        declared = m8oc.ARMS[name]
        assert arm["trials"] == declared["trials"], name
        assert arm["seed"] == declared["seed"], name
        assert sum(arm["tally"].values()) == arm["trials"], name
        k = arm["tally"].get("order_effect_observed", 0)
        assert arm["positive_rate"] == round(k / arm["trials"], 6), name
        # the interval recomputes exactly from the tally
        assert tuple(arm["positive_rate_ci95"]) == \
            m8oc.clopper_pearson(k, arm["trials"]), name


def test_artifact_type_i_rates_satisfy_the_frozen_criterion(artifact):
    """False-positive rate not materially above alpha, with CI evidence: for
    every H0-family arm — the iid families AND the dependent shared-latent
    sharp-null-true process — the exact 95% lower bound must not exceed
    alpha = 0.05."""
    charged = {n: a for n, a in artifact["arms"].items()
               if a["charged"] == "type_i"}
    assert set(charged) == {"h0_iid_uniform", "h0_iid_graded",
                            "h0_iid_concentrated",
                            "h0_shared_latent_sharp_true"}
    for name, arm in charged.items():
        lo, hi = arm["positive_rate_ci95"]
        assert lo <= 0.05, (name, arm)
        assert arm["criterion"]["pass"] is True, name
        # 400 trials: the audit's resolution demand — the interval itself can
        # distinguish alpha from 2*alpha
        assert arm["trials"] == 400, name


def test_artifact_power_at_the_boundary_is_non_negligible(artifact):
    arm = artifact["arms"]["power_at_mde"]
    lo, hi = arm["positive_rate_ci95"]
    assert lo > 0.05, arm                     # distinguishable from the FP floor
    assert arm["criterion"]["pass"] is True
    assert arm["trials"] == 400
    # power grows with effect size — the 2x-MDE context arm must dominate
    assert artifact["arms"]["power_at_2x_mde"]["positive_rate"] >= \
        arm["positive_rate"]


def test_artifact_sham_gate_leakage_is_bounded(artifact):
    """The sham gate's residual leakage over a contaminated-at-MDE sham
    PROCESS is bounded like type-I: CP 95% lower bound at or below alpha
    (audit 001814 finding 1). The gate's ABSOLUTE guarantees are
    observation-level and pinned deterministically elsewhere:
    `test_sham_warrant_missing_boundary_is_inconclusive_never_positive` (the
    reproduced TV(A,C)=q_AC=margin pack, at the frozen 10 000 iterations,
    never promotes) and `test_positive_verdict_always_carries_the_sham_warrant`
    in tests/test_m8_order_report.py. A finite-sample rule grants the warrant
    on the observed pack; it cannot bound the unobserved process, and the
    artifact reports that residual for what it is rather than hiding it."""
    arm = artifact["arms"]["sham_contaminated_at_mde"]
    lo, hi = arm["positive_rate_ci95"]
    assert lo <= 0.05, arm
    assert arm["criterion"]["pass"] is True
    # small in absolute terms as well — an order of magnitude below the power
    # the same rule delivers at the same effect size on the A/B axis
    assert arm["positive_rate"] <= 0.05
    assert "leakage" in arm["criterion"]["statement"]


def test_artifact_reports_the_sharp_violation_arm_for_what_it_is(artifact):
    """The audit's separating process — sharp null FALSE, marginal null true —
    must be present, must NOT be charged against type-I, and must show the rule
    rejecting essentially always (which is the correct sharp-null conclusion,
    licensed by the v4 claim ceiling)."""
    arm = artifact["arms"]["sharp_false_marginal_true"]
    assert arm["charged"] == "sharp_violation_detection"
    assert arm["positive_rate"] >= 0.95
    assert "sharp" in arm["criterion"]["statement"]
    assert "Not charged against type-I" in arm["criterion"]["statement"]


def test_artifact_states_the_ci_math_and_measured_runtime(artifact):
    """The prereg requires the trial-count math stated and this build requires
    runtime measured — both live in the artifact, not in a docstring."""
    ci = artifact["ci_method"]
    assert ci["outer_trials_per_h0_arm"] == 400
    assert "Clopper-Pearson" in ci["interval"]
    assert "0.10" in ci["math"] and "400" in ci["math"]
    assert artifact["runtime"]["seconds"] > 0
    assert artifact["all_criteria_pass"] is True
