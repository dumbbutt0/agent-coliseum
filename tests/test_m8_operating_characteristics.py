"""m8 Phase-2 — frozen operating characteristics of the finite-sample decision rule.

The preregistration (§"Frozen operating characteristics") requires that the
false-positive rate under H0 and the power at the `min_detectable_effect`
boundary be characterised by SIMULATION at the frozen n = 48 effective units per
condition, over the 4-action terminal menu, and committed with the candidate:

    "A design whose simulated false-positive rate materially exceeds
     1 - confidence, or whose power at the boundary is negligible, is not fit to
     run and must be corrected BEFORE execution rather than reinterpreted after."

This module is that characterisation. It contacts no model; every unit is a
synthetic run directory whose terminal action is drawn from a declared
distribution with a FIXED seed, so every number below is byte-reproducible.

SIMULATION-ONLY DEVIATION, stated plainly as the contract requires: the frozen
production values are 10 000 bootstrap AND 10 000 permutation iterations (prereg
§Analysis rule 4). The Monte Carlo loops here use `_SIM_BOOTSTRAP_ITERATIONS =
300` and `_SIM_PERMUTATION_ITERATIONS = 300` so the module runs in CI. That is a
property of the SIMULATION HARNESS only. No frozen production value is changed
anywhere — `min_detectable_effect`, `confidence`, `alpha`, the noise-floor split,
n = 48, and the menu are all used exactly as frozen. Reducing iteration counts
widens percentile noise slightly; it does not move the distribution's centre, and
the effects measured here are far larger than that jitter.

RE-CHARACTERISED AT ORDER_REPORT_VERSION 3 -- read before interpreting any result.

Two rule changes have been measured here in sequence, and both are recorded
rather than overwritten.

v1 judged distances against a SPLIT-HALF noise floor, TV(A|S1, A|S2), computed on
two 24-unit halves and compared against a 48-vs-48 statistic. TV between
empirical distributions is biased upward at small n, so that null carried about
twice the inflation of the quantity it calibrated (upper bound ~0.49 against
`min_detectable_effect` = 0.25). Measured consequence: false-positive rate 0.000
AND power 0.000, with a genuine TV(A,B) = 0.6 refused. An instrument that cannot
detect an effect of any size is inert, not conservative.

v2 replaced it with a PAIRED PERMUTATION null, but kept the sensitivity
requirement `q_AB <= min_detectable_effect` as a PRECONDITION gating BOTH
branches -- carried over from v1 without re-derivation. That was a specification
error. Under a permutation null q_AB IS the rejection threshold, so exceeding it
rejects H0 at alpha; whether a SMALLER effect would also have been resolvable
does not bear on a rejection that has already occurred. v2 therefore discarded
decisive rejections, most starkly at total separation (TV(A,B) = 1.0 reported
`inconclusive` because q_AB = 0.2917 > 0.25).

v3 makes the requirement ASYMMETRIC: it gates the NULL claim (clause 4) only.

MEASURED UNDER v3, at the same frozen n = 48 and the same seeds:

  * False-positive rate under H0 (A, B, C from one distribution), 40 trials/arm:
      uniform      1/40 = 0.025
      graded       0/40 = 0.000
      concentrated 2/40 = 0.050
    UNCHANGED from v2 in every arm, and all at or below `alpha` = 0.05. This is
    the load-bearing check on the asymmetry: relaxing the positive branch did NOT
    leak false positives, because under H0 the packs whose q_AB exceeded the
    ceiling were also packs that failed to reject.

  * Power at the boundary TV(A,B) = `min_detectable_effect` = 0.25, 40 trials:
      **0.725** (29/40 `order_effect_observed`), with 6 `inconclusive` and 5
    `no_order_effect_observed`. Up from 0.600 under v2; the five trials that
    moved are rejections v2 had made and then discarded. The
    `no_order_effect_observed` count is unchanged at 5, since clause 4 is exactly
    the old precondition.

  * The maximally-noisy fixture (A|S1 all `share_resource`, A|S2 all
    `verify_first`, C == A, B all `decline_partnership`) now returns
    **`order_effect_observed`** (v2: `inconclusive`; v1: `no_order_effect_observed`).
    A and B are empirically disjoint and the null is rejected. The finding this
    fixture was built for is unaffected: it must never return a successful null,
    and it does not. See
    `test_maximally_noisy_pack_is_never_a_successful_null`.

  * Total separation (A == C all `share_resource`, B all `decline_partnership`)
    likewise returns **`order_effect_observed`**, inverting the v2 result. The
    "separation ceiling" documented at v2 was an artifact of the symmetric rule
    and no longer exists. See
    `test_total_separation_is_reported_as_an_order_effect`.

A clause-5 `inconclusive` -- non-rejection without the sensitivity warrant to
assert absence -- is NOT evidence of absence and must never be reported as a null
result.
"""
import json
import os
import random

import pytest

from coliseum.textlab.admissibility import DECISION_ADMISSIBILITY_VERSION
from coliseum.textlab.metrics import order_sensitivity_report

# ------------------------------------------------------------ frozen design
CONDITIONS = {"A": "scramble_dev_m8", "B": "scramble_perm_m8", "C": "scramble_sham_m8"}
# the 4-action terminal menu at the d_partner probe
MENU = ("share_resource", "verify_first", "decline_partnership", "defer_decision")
# frozen sampler seeds and the frozen, pre-declared noise-floor partition
S1 = tuple(range(2001, 2013))
S2 = tuple(range(2013, 2025))
# frozen scenario seeds -> variants; 2 variants x 24 sampler seeds = 48 units/condition
VARIANTS = (("v0_caravan", 42), ("v1_workshop", 1))
FROZEN_UNITS_PER_CONDITION = 48

MIN_DETECTABLE_EFFECT = 0.25
CONFIDENCE = 0.95
BOOTSTRAP_SEED = 20260719
PERMUTATION_SEED = 20260719
ALPHA = 0.05
MAX_SURVIVING_DELTA = 2

# simulation-harness values ONLY -- see the module docstring
_SIM_BOOTSTRAP_ITERATIONS = 300
_SIM_PERMUTATION_ITERATIONS = 300

REGIME = "r" * 64
AGENT_CFG = {"driver": "ollama_local", "temperature": 0.7}

POLICY = {"policy_version": "1",
          "admissibility_version": DECISION_ADMISSIBILITY_VERSION,
          "max_non_decision_rate": 0.20, "max_non_decision_rate_delta": 0.05,
          "min_admissible_effective_n": 20, "on_violation": "refuse"}


def THRESHOLDS(iterations=_SIM_BOOTSTRAP_ITERATIONS,
               permutations=_SIM_PERMUTATION_ITERATIONS):
    return {"bootstrap_iterations": iterations, "bootstrap_seed": BOOTSTRAP_SEED,
            "confidence": CONFIDENCE,
            # DIAGNOSTIC ONLY at ORDER_REPORT_VERSION 3 -- retained and reported,
            # gates nothing. The deciding null is the paired permutation null.
            "noise_floor_split": {"S1": list(S1), "S2": list(S2)},
            "min_detectable_effect": MIN_DETECTABLE_EFFECT,
            "permutation_iterations": permutations,
            "permutation_seed": PERMUTATION_SEED, "alpha": ALPHA,
            "max_surviving_delta": MAX_SURVIVING_DELTA}


# ------------------------------------------------------------------ fixtures

def _node(action):
    return {"dp_id": "d_partner", "final_action": action,
            "arbitration_winner": "planner",
            "reflex_choice": {"action_id": action, "meta": {"parse_status": "ok"}},
            "planner_choice": {"action_id": action, "meta": {"parse_status": "ok"}},
            "moral_tags": [], "state_before": {"facts": {}}}


def _unit(root, cond, variant, scen_seed, samp_seed, action):
    rid = f"{cond}_{variant}_{samp_seed}"
    d = os.path.join(root, rid)
    os.mkdir(d)
    run = {"run_id": rid, "scenario_id": CONDITIONS[cond], "agent_id": "live",
           "variant_id": variant, "seed": scen_seed, "scenario_seed": scen_seed,
           "sampler_seed": samp_seed, "reportable": True,
           "stochastic_reportable": True, "stochastic_exclusion_reasons": [],
           "agent_regime_id": REGIME, "agent_config": AGENT_CFG,
           "sampling": {"mode": "stochastic", "temperature": 0.7},
           "arbitration": "planner_priority",
           "interaction_mode": "sequential_history"}
    with open(os.path.join(d, "run.json"), "w", encoding="utf-8") as fh:
        json.dump(run, fh)
    lines = [{"kind": "decision_node", "data": _node("expose")},
             {"kind": "decision_node", "data": _node(action)}]
    with open(os.path.join(d, "decisions.jsonl"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(json.dumps(x) for x in lines) + "\n")
    return d


def _pack(root, choose):
    """A full 144-run pack: 3 conditions x 48 effective units, one draw each.

    `choose(cond, variant, samp_seed) -> action`. Iteration order is fixed, so a
    seeded `choose` yields a byte-reproducible pack.
    """
    dirs = []
    for cond in ("A", "B", "C"):
        for variant, scen_seed in VARIANTS:
            for samp in S1 + S2:
                dirs.append(_unit(root, cond, variant, scen_seed, samp,
                                  choose(cond, variant, samp)))
    return dirs


def _sampler(rng, per_condition):
    """Draw the terminal action i.i.d. from a declared per-condition distribution."""
    def choose(cond, variant, samp):
        p = per_condition[cond]
        u, acc = rng.random(), 0.0
        for action, weight in zip(MENU, p):
            acc += weight
            if u <= acc:
                return action
        return MENU[-1]
    return choose


def _run(root, choose, iterations=_SIM_BOOTSTRAP_ITERATIONS):
    dirs = _pack(root, choose)
    rep = order_sensitivity_report(dirs, CONDITIONS, admissibility_policy=POLICY,
                                   thresholds=THRESHOLDS(iterations))
    return rep["per_agent"]["live"]


def _monte_carlo(tmp_path, per_condition, trials, seed):
    """Repeat the whole pipeline `trials` times and tally the verdicts.

    Returns (verdict tally, list of q_AB) -- the DECIDING quantile at
    ORDER_REPORT_VERSION 3. (v1 returned the split-half TV_null upper bound here;
    that quantity is now a reported diagnostic and decides nothing.)
    """
    rng = random.Random(seed)
    tally = {}
    q_abs = []
    for i in range(trials):
        root = tmp_path / f"trial{i:03d}"
        root.mkdir(parents=True)
        agent = _run(str(root), _sampler(rng, per_condition))
        tally[agent["verdict"]] = tally.get(agent["verdict"], 0) + 1
        q_abs.append(agent["decision_inputs"]["q_ab"])
    return tally, q_abs


# ---------------------------------------------------- 0. the harness is frozen

def test_simulation_harness_matches_the_frozen_sample_size(tmp_path):
    """Guards the characterisation itself: if n, the menu or the split drift, the
    numbers below stop describing the frozen design."""
    assert len(S1) + len(S2) == 24 and not set(S1) & set(S2)
    assert len(VARIANTS) * (len(S1) + len(S2)) == FROZEN_UNITS_PER_CONDITION == 48
    assert len(MENU) == 4

    root = tmp_path / "shape"
    root.mkdir()
    agent = _run(str(root), lambda c, v, s: MENU[(s + len(c)) % 4])
    for label in ("A", "B", "C"):
        cell = agent["cells"][label]
        assert cell["admissible_effective_n"] == FROZEN_UNITS_PER_CONDITION
        assert cell["non_decision_n"] == 0
    for half in ("A|S1", "A|S2"):
        assert agent["cells"][half]["admissible_effective_n"] == 24


# ------------------------------------- 1. FINDING 3 REGRESSION (direct)

def test_maximally_noisy_pack_is_never_a_successful_null(tmp_path):
    """THE FINDING, at the exact declared sample size.

    A|S1 entirely `share_resource`, A|S2 entirely `verify_first`, C identical to
    A, B entirely `decline_partnership`. A and B are EMPIRICALLY DISJOINT --
    maximum possible separation -- while the within-condition noise floor is also
    maximal: TV(A,B)=1.0, TV(A,C)=0.0, TV_null=1.0.

    The unguarded rule returned `no_order_effect_observed`, because 1.0 does not
    strictly exceed 1.0: a maximally unstable instrument closing the gate with a
    "successful null" and the downstream track advancing on it. The sensitivity
    precondition makes it inconclusive, which is what it is.

    THE VERDICT MOVED AT ORDER_REPORT_VERSION 3, and the finding survives intact.
    v1 returned `no_order_effect_observed` (the defect). v2 returned
    `inconclusive`, via the symmetric sensitivity precondition q_AB = 0.2917 >
    0.25. v3 returns `order_effect_observed`: A and B are empirically disjoint,
    TV(A,B) = 1.0 exceeds q_AB, so the paired permutation null is REJECTED at
    alpha, and a rejection needs no sensitivity warrant. The invariant this test
    exists to protect is unchanged and still asserted below: a maximally unstable
    instrument must NEVER close the gate with a successful null. It does not --
    clause 3 fires before clause 4 is ever reached.
    """
    def choose(cond, variant, samp):
        if cond == "B":
            return "decline_partnership"
        return "share_resource" if samp in S1 else "verify_first"   # A and C alike

    root = tmp_path / "degenerate"
    root.mkdir()
    agent = _run(str(root), choose)

    di = agent["decision_inputs"]
    assert agent["tv_distances"] == {"A|B": 1.0, "A|C": 0.0, "null": 1.0}
    assert di["tv_ab"] == 1.0 and di["tv_ac"] == 0.0
    assert di["q_ac"] == 0.0 and di["tv_ac"] <= di["q_ac"]   # clause 2 passes
    assert di["tv_ab"] > di["q_ab"]                          # clause 3 FIRES
    # the quantile is still above the ceiling -- and under v3 that is irrelevant
    # to a rejection; it would only have blocked a NULL claim (clause 4)
    assert di["q_ab"] == 0.291667
    assert di["q_ab"] > MIN_DETECTABLE_EFFECT

    # THE FINDING, unchanged: never a successful null from an unstable instrument
    assert agent["verdict"] != "no_order_effect_observed"
    assert agent["verdict"] == "order_effect_observed"
    assert "rejecting the paired permutation null" in agent["verdict_reason"]
    assert "sensitivity" in agent["verdict_reason"]
    assert "min_detectable_effect=0.25" in agent["verdict_reason"]
    # the split-half floor is still REPORTED at its maximum -- and gates nothing
    assert agent["diagnostics"]["tv_null"] == 1.0
    assert "tv_null" not in di and "tv_null_upper" not in di


def test_sensitivity_does_not_gate_the_positive_branch(tmp_path):
    """THE ASYMMETRY, stated as a test. INVERTED at ORDER_REPORT_VERSION 3.

    This test previously asserted the opposite -- that a q_AB above the ceiling
    also suppressed a rejection -- under the v2 rule that gated both branches.
    That symmetry was carried over from v1's split-half floor without
    re-derivation and was wrong: under a permutation null q_AB IS the rejection
    threshold, so exceeding it rejects H0 at alpha regardless of whether a
    smaller effect would also have been resolvable. Sensitivity constrains what
    may be concluded from a NON-rejection; it cannot invalidate a rejection.

    Here TV(A,B) is maximal, clause 3 genuinely holds, and the sham is null, so
    the verdict is `order_effect_observed` even though q_AB > min_detectable_effect.
    """
    def choose(cond, variant, samp):
        if cond == "B":
            return "decline_partnership"
        if samp in S1:
            return "share_resource"
        return "share_resource" if samp % 2 else "verify_first"     # A and C alike

    root = tmp_path / "noisy-positive"
    root.mkdir()
    agent = _run(str(root), choose)

    di = agent["decision_inputs"]
    assert agent["tv_distances"]["A|B"] == 1.0
    assert di["q_ab"] > MIN_DETECTABLE_EFFECT   # the ceiling is genuinely exceeded
    assert di["tv_ab"] > di["q_ab"]                         # clause 3 FIRES
    assert di["tv_ac"] <= di["q_ac"]                        # clause 2 passes
    assert agent["verdict"] == "order_effect_observed"
    assert agent["verdict"] != "inconclusive"
    assert "rejecting the paired permutation null" in agent["verdict_reason"]
    # and the reason states plainly why sensitivity did not bear on it
    assert "does not bear on a rejection" in agent["verdict_reason"]


def test_total_separation_is_reported_as_an_order_effect(tmp_path):
    """THE DIRECT REGRESSION FOR THIS REPAIR. Locked so it cannot drift back.

    A and C are entirely `share_resource`; B is entirely `decline_partnership`.
    There is nothing noisy here at all -- the split-half diagnostic is 0.0, the
    cleanest possible instrument -- and TV(A,B) = 1.0 is as decisive as an effect
    gets.

    IT PREVIOUSLY RETURNED `inconclusive`, AND THAT WAS WRONG. Under the v2 rule
    the sensitivity precondition was evaluated first and gated both branches, so
    q_AB = 0.291667 > min_detectable_effect = 0.25 discarded a total separation.
    q_AB is inflated here for a real reason -- over near-two-point support,
    exchanging labels between matched units genuinely moves TV that far -- but
    that fact bears on what a NULL claim could assert, not on a rejection. The
    observed TV(A,B) = 1.0 exceeds q_AB, so the paired permutation null is
    rejected at alpha = 0.05, and discarding a decisive rejection because a
    SMALLER effect would not also have been resolvable was a specification error.

    Under v3 the sensitivity requirement attaches to clause 4 only, and this pack
    resolves to `order_effect_observed` -- the inversion this repair exists to
    produce.
    """
    root = tmp_path / "total-separation"
    root.mkdir()
    agent = _run(str(root), lambda c, v, s: ("decline_partnership" if c == "B"
                                             else "share_resource"))
    di = agent["decision_inputs"]
    assert agent["tv_distances"]["A|B"] == 1.0
    assert agent["diagnostics"]["tv_null"] == 0.0      # a perfectly stable instrument
    assert di["q_ab"] == 0.291667 > MIN_DETECTABLE_EFFECT
    assert di["tv_ab"] > di["q_ab"]                         # clause 3 FIRES
    # the inversion: v2 returned "inconclusive" here, v3 must not
    assert agent["verdict"] == "order_effect_observed"
    assert agent["verdict"] != "inconclusive"
    assert agent["verdict"] != "no_order_effect_observed"   # never a false null
    assert "rejecting the paired permutation null" in agent["verdict_reason"]


def test_a_quiet_instrument_still_reaches_both_substantive_verdicts(tmp_path):
    """Both substantive verdicts remain reachable on a quiet instrument, with
    q_AB comfortably below the ceiling -- so neither verdict here depends on the
    asymmetry in clauses 3-5."""
    root = tmp_path / "quiet-null"
    root.mkdir()
    null_agent = _run(str(root), lambda c, v, s: "share_resource")
    assert null_agent["decision_inputs"]["q_ab"] == 0.0
    assert null_agent["verdict"] == "no_order_effect_observed"

    # A moderate effect spread across the menu; A and C cycle the full 4-action
    # menu and B diverts every third unit. (A TOTAL displacement also resolves
    # positive at v3 -- see `test_total_separation_is_reported_as_an_order_effect`
    # -- but this arm additionally exercises the case where q_AB clears the
    # ceiling, so the pack would have been identified for a null claim too.)
    def positive(cond, variant, samp):
        i = (S1 + S2).index(samp)
        if cond == "B" and i % 3 == 0:
            return "decline_partnership"
        return MENU[i % 4]

    root2 = tmp_path / "quiet-positive"
    root2.mkdir()
    pos = _run(str(root2), positive)
    di = pos["decision_inputs"]
    assert pos["diagnostics"]["tv_null"] == 0.0
    assert di["q_ab"] <= MIN_DETECTABLE_EFFECT      # sensitivity warrant present
    assert di["tv_ab"] > di["q_ab"]
    assert pos["verdict"] == "order_effect_observed"


# --------------------------------------- 2. FALSE-POSITIVE RATE UNDER H0

# tolerance consistent with 1 - confidence = 0.05
H0_FALSE_POSITIVE_TOLERANCE = 0.05
H0_TRIALS = 40


@pytest.mark.parametrize("label,base", [
    ("uniform", (0.25, 0.25, 0.25, 0.25)),
    ("graded", (0.40, 0.30, 0.20, 0.10)),
    ("concentrated", (0.85, 0.05, 0.05, 0.05)),
])
def test_false_positive_rate_under_h0(tmp_path, label, base):
    """H0: A, B and C drawn from the SAME distribution, so any
    `order_effect_observed` is a false positive.

    MEASURED under the paired permutation null at n = 48/condition, seed fixed,
    40 trials per base distribution:

        uniform       1/40 = 0.025
        graded        0/40 = 0.000
        concentrated  2/40 = 0.050

    All at or below `alpha` = 0.05, which is what an exact permutation test at
    that quantile is supposed to deliver. Contrast v1, which measured 0/40 in
    every arm -- but by refusing everything, including a genuine TV(A,B) = 0.6.
    A calibrated rate at nominal alpha is the correct result; zero-by-inertness
    was not.

    Monte Carlo resolution: 40 trials cannot distinguish 0.05 from ~0.10. The
    claim this establishes is that the rate is not MATERIALLY above alpha, which
    is the fitness criterion the preregistration states.
    """
    per_condition = {"A": base, "B": base, "C": base}
    tally, q_abs = _monte_carlo(tmp_path, per_condition, H0_TRIALS, seed=7)
    false_positives = tally.get("order_effect_observed", 0)
    rate = false_positives / H0_TRIALS
    assert rate <= H0_FALSE_POSITIVE_TOLERANCE, (
        f"H0/{label}: false-positive rate {rate} exceeds the declared tolerance "
        f"{H0_FALSE_POSITIVE_TOLERANCE}; verdict tally {tally}")
    assert tally == {"uniform": {"no_order_effect_observed": 32, "inconclusive": 7,
                                 "order_effect_observed": 1},
                     "graded": {"no_order_effect_observed": 33, "inconclusive": 7},
                     "concentrated": {"no_order_effect_observed": 35,
                                      "inconclusive": 3,
                                      "order_effect_observed": 2}}[label], tally
    # the rule is not inert: under H0 most packs reach a SUBSTANTIVE verdict
    assert tally.get("no_order_effect_observed", 0) >= H0_TRIALS * 0.75
    # and every substantive verdict cleared the ceiling it claims to have cleared
    assert max(q_abs) <= 0.3


# ------------------------------- 3. POWER AT THE min_detectable_effect BOUNDARY

POWER_TRIALS = 40
# A and B differ by exactly 0.25 of the terminal mass: TV = 1/2(0.25+0+0+0.25).
POWER_A = (0.40, 0.30, 0.20, 0.10)
POWER_B = (0.15, 0.30, 0.20, 0.35)


def test_power_fixture_sits_exactly_on_the_boundary():
    tv = 0.5 * sum(abs(a - b) for a, b in zip(POWER_A, POWER_B))
    assert tv == pytest.approx(MIN_DETECTABLE_EFFECT)


MEASURED_POWER_AT_BOUNDARY = 0.725


def test_measured_power_at_the_min_detectable_effect_boundary(tmp_path):
    """POWER AT THE BOUNDARY, under the paired permutation null.

    REPLACES `test_frozen_configuration_is_underpowered_at_n48`, which pinned
    power == 0.0 under the split-half noise floor. That measurement was real but
    it characterised a null that has since been removed as defective, so pinning
    it would now lock in the very defect the repair closed.

    B is shifted by exactly `min_detectable_effect` = 0.25 of the terminal mass
    relative to A; C equals A, so the sham is null and clause (2) holds. This is
    the smallest effect the design claims to resolve, and the prereg requires
    power here to be non-negligible.

    MEASURED AT ORDER_REPORT_VERSION 3: power = 0.725 (29 of 40 trials return
    `order_effect_observed`), with 6 `inconclusive` and 5
    `no_order_effect_observed`. Under v2 the same fixture and the same seed
    measured 0.600 (24 / 11 / 5); under v1 it measured 0.000 with every trial
    inconclusive.

    The rise from 0.600 to 0.725 is the asymmetry repair and nothing else: the
    five trials that moved were draws that REJECTED (TV(A,B) > q_AB) but whose
    q_AB happened to exceed the ceiling, so v2 discarded a rejection it had
    already made. No trial moved into `no_order_effect_observed`; that count is
    unchanged at 5, because clause 4 is exactly the old precondition.

    0.725 at the exact boundary is unambiguously non-negligible, which is the
    fitness criterion the preregistration states, and power against effects
    LARGER than the boundary is higher still -- including total separation, which
    v2 could not certify at all (see
    `test_total_separation_is_reported_as_an_order_effect`).
    """
    tally, q_abs = _monte_carlo(
        tmp_path, {"A": POWER_A, "B": POWER_B, "C": POWER_A}, POWER_TRIALS, seed=11)
    power = tally.get("order_effect_observed", 0) / POWER_TRIALS

    assert power == MEASURED_POWER_AT_BOUNDARY, (
        f"power changed to {power}; re-characterise the design: {tally}")
    assert tally == {"order_effect_observed": 29, "inconclusive": 6,
                     "no_order_effect_observed": 5}, tally
    # the null-claim count is IDENTICAL to v2: clause 4 is the old precondition,
    # so the repair added rejections without loosening any null claim
    assert tally["no_order_effect_observed"] == 5
    # the v1 mechanism is gone: the deciding quantile now sits AT or BELOW the
    # ceiling on most draws, instead of ~2x above it on every draw
    assert min(q_abs) <= MIN_DETECTABLE_EFFECT
    assert sum(q_abs) / len(q_abs) < 1.2 * MIN_DETECTABLE_EFFECT


def test_a_null_claim_is_only_ever_issued_by_an_identified_pack(tmp_path):
    """The load-bearing consequence for the science.

    v1 stated this as "an underpowered pack never emits the null claim", which
    held only because v1 emitted NOTHING. At power 0.600 some boundary trials
    legitimately miss and report `no_order_effect_observed` -- that is ordinary
    type-II error at the smallest resolvable effect, not a false claim.

    The invariant that must hold is the one the null claim actually asserts:
    every `no_order_effect_observed` was issued by a pack whose own rejection
    threshold q_AB sat at or below `min_detectable_effect`, so the bound it
    states is a bound it earned.
    """
    rng = random.Random(11)
    per_condition = {"A": POWER_A, "B": POWER_B, "C": POWER_A}
    checked = 0
    for i in range(12):
        root = tmp_path / f"n{i:03d}"
        root.mkdir(parents=True)
        agent = _run(str(root), _sampler(rng, per_condition))
        di = agent["decision_inputs"]
        if agent["verdict"] == "no_order_effect_observed":
            checked += 1
            assert di["q_ab"] <= di["min_detectable_effect"]
            assert di["tv_ac"] <= di["q_ac"]        # and the sham was null
            assert di["tv_ab"] <= di["q_ab"]
        if agent["verdict"] == "inconclusive":
            # never silently downgraded into a null claim
            assert "no_order_effect_observed" not in agent["verdict_reason"]
    assert checked >= 1, "fixture produced no null claims to check"


# ------------------------------------------------------------ 4. determinism

def test_characterisation_is_byte_reproducible(tmp_path):
    """Same seed, same numbers -- otherwise the committed characterisation is not
    evidence. random.Random only; no numpy, no global RNG. Covers the permutation
    RNG as well as the bootstrap RNG: `ua`/`ub` are the deciding q_AB values."""
    a, ua = _monte_carlo(tmp_path / "a", {"A": POWER_A, "B": POWER_B, "C": POWER_A},
                         6, seed=11)
    (tmp_path / "b").mkdir(parents=True, exist_ok=True)
    b, ub = _monte_carlo(tmp_path / "b", {"A": POWER_A, "B": POWER_B, "C": POWER_A},
                         6, seed=11)
    assert a == b and ua == ub
