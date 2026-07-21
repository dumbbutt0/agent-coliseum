#!/usr/bin/env python3
"""m8 Phase-2 — operating characteristics of the FROZEN decision rule (v6).

SCIENTIFIC RE-FREEZE (audit a-004) -> DISTRIBUTIONAL re-framing (owner a-005) ->
WITHIN-UNIT SWAP-INVARIANCE null (owner a-006, binding). This study is bound to
the ONE canonical null of this design, and a-006 fixed that null as within-unit
JOINT swap invariance under across-unit independence. The arithmetic is
unchanged — same within-pair paired permutation, same population-marginal
TV(A,B) statistic, same ordered decision rule, same verdict enum literals — so
the committed numbers of the shared arms are unchanged; the null vocabulary and
the arm taxonomy are what a-006 sharpened.

* ONE NULL EVERYWHERE. The operative confirmatory null of this design is the
  within-unit joint swap-invariance null, frozen in planned_design (null_form
  + null_statement), anchored in audited code (registry.M8_NULL_STATEMENT) and
  stated verbatim here:

      Operative confirmatory null (within-unit joint swap invariance): for every
      matched experimental unit i, the joint distribution of the paired terminal
      outcomes is invariant under exchanging presentation labels A and B —
      (Y_iA, Y_iB) =d (Y_iB, Y_iA) — subject to the preregistered across-unit
      independence / exchangeability-block assumptions. This implies equality of
      the population-marginal terminal-action distributions, but the within-pair
      permutation test is NOT claimed to be an exact test of bare
      population-marginal equality alone.

  Swap invariance IMPLIES equal population marginals but is strictly stronger
  than bare-marginal equality: an arm is a genuine null case only when BOTH its
  marginals AND its within-unit joint coupling are exchangeable. This study
  therefore keys every arm on BOTH — its `marginals` metadata AND its `coupling`
  metadata — so two arms that share a marginal-TV are never treated as
  equivalent when one is jointly exchangeable and the other is not.

* THE TWO-MODE NULL (a-006). Swap-invariance null arms come in two sub-modes,
  and both must be charged type-I:
    - null_mode "copy" — one draw per unit COPIED across A/B/C, so the realized
      pair is trivially exchangeable (byte-identical). The sharp_h0_iid_* and
      sharp_h0_shared_latent arms. Verified by the identical-realization proof:
      every matched unit is concordant (A_i == B_i == C_i).
    - null_mode "law_exchangeable" — A and B drawn iid from the SAME per-
      condition law (per["A"] == per["B"]), so their realizations DIFFER unit by
      unit while the pair (A_i, B_i) is exchangeable and independent across
      units. C COPIES A (per["C"] equals the same law, realized identically), so
      the sham axis holds the null exactly and the type-I characterization
      ISOLATES the A/B swap-invariance permutation test — the SAME clean-sham
      construction the power arms use. The iid_equal_marginals_* arms. Verified
      NOT by realization identity on A/B (which does not hold) but by LAW: the
      arm's declared per-condition distributions are equal
      (per["A"] == per["B"] == per["C"]) and A/B are generated iid-per-condition
      independently across units — the GENERATING LAW of the pair is swap-
      invariant. (Measuring the confirmatory AB decision under an INDEPENDENT C
      instead would confound this type-I rate with sham-gate behaviour, since an
      independent sham fails on a distribution-dependent fraction of trials.)
  Both sub-modes are genuine swap-invariance null cases; both are charged type-I
  and both must satisfy the frozen CP-95 UPPER-bound criterion. Verification is
  not weakened — each mode proves the property it actually holds.

* THE NON-EXCHANGEABLE ALTERNATIVES (a-006). An arm can hold the population
  marginals equal (TV(A,B) = 0) while VIOLATING swap invariance through a
  non-exchangeable within-unit joint (a deterministic relabeling / cancellation
  coupling). Because the marginal TV statistic is identically zero on such
  packs, the frozen rule cannot reject them (power ~ 0). This is NOT a type-I
  failure — the null is genuinely FALSE for these arms, and the design simply
  cannot detect that particular violation. It DOCUMENTS the design's
  outside-null sensitivity limitation: TV = 0 is never evidence that swap
  invariance holds. These arms are `alternative_nonexchangeable`, never charged
  type-I, and are expected to essentially never reject.

* FROZEN FITNESS CRITERIA, honest directions. The acceptance criteria are not
  script inventions; they are frozen in planned_design.thresholds and loaded
  from the registry bundle:
  - type_i_criterion: "CP-95 upper bound of the swap-invariance-null rejection
    rate <= alpha". The UPPER bound — the superseded lower-bound check tested
    only whether excess above alpha was demonstrated, the wrong direction. It is
    applied to EVERY charged type-I arm, copy-mode AND law-exchangeable-mode.
  - power_target: 0.8 — the CP-95 LOWER bound of measured power at
    min_detectable_effect must reach it. min_detectable_effect is frozen at the
    smallest grid effect whose measured power meets that bound; the artifact's
    mde_selection block recomputes the choice so it regenerates from the
    committed run alone. Power is DEMONSTRATED sensitivity under the specific
    marginal-shift families simulated here, not a universal guarantee.

The within-unit paired permutation supplies the REFERENCE distribution under
within-pair exchangeability, a valid level-alpha reference for the marginal
TV(A,B) statistic. A rejection evidences that presentation order changes the
paired terminal-outcome distribution at some unit; a non-rejection is "no order
effect detected at the threshold" and never establishes swap invariance,
per-unit invariance, or marginal equality (balanced cancelling couplings keep
the marginals equal while violating swap invariance — out of scope).

POWER IS CHARACTERISED UNDER A NULL SHAM AXIS, and that is the faithful model,
not a convenience: decoding is seeded per unit, so if the sham rewording truly
makes no difference to a unit's computation the realized terminal action is
IDENTICAL — C_i == A_i, so the sham axis holds the null exactly. The power arms
therefore copy C from A (verified).

The study drives `metrics.order_sensitivity_report` (ORDER_REPORT_VERSION 6)
end to end — synthetic run directories, real replay attestations over their
actual bytes, the real terminal-probe / matched-unit / surviving-count /
sham-adequacy gates — at the exact frozen threshold bundle, and writes the
committed artifact

    derived/textlab/m8-operating-characteristics.json

No model is contacted. Every draw comes from `random.Random` with a declared
per-trial seed (trial_seed = arm_seed + trial_index), so the study is
deterministic and independent of worker scheduling.

CI RESOLUTION. Copy-mode type-I arms are structural zeros (identical schedules),
resolved exactly at T = 400. Law-exchangeable type-I arms have a small non-zero
rejection rate whose exact CP-95 UPPER bound must fall at or below alpha, so they
run at T = TYPE_I_HIGH_TRIALS = 3000 (>= the 2000 floor) for a tight interval:
the most demanding arm (concentrated marginals) sits at a genuine, conservative
~0.039 discreteness level, and at T = 3000 its CP-95 upper bound is ~0.046 <
alpha = 0.05 with margin, whereas T = 2000 leaves only p-hat <= 0.040 headroom.
Power arms run at T = 400: at p-hat = 0.85 the CP-95 lower bound is ~0.812, so
the target 0.8 is resolvable against true power ~0.85+.

Runtime is measured and recorded in the artifact. Run:

    python3 scripts/m8_operating_characteristics.py [--workers N] [--out PATH]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import multiprocessing
import os
import random
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from coliseum.textlab.admissibility import DECISION_ADMISSIBILITY_VERSION  # noqa: E402
from coliseum.textlab.metrics import (METRICS_VERSION,  # noqa: E402
                                      ORDER_REPORT_VERSION,
                                      order_sensitivity_report)
from coliseum.textlab.registry import (M8_NULL_FORM,  # noqa: E402
                                       M8_NULL_STATEMENT,
                                       M8_POWER_TARGET,
                                       M8_TYPE_I_CRITERION)
from coliseum.textlab.schema import canonical_json, config_hash  # noqa: E402

# The characterisation is bound to the rule version it characterises: a bump
# of ORDER_REPORT_VERSION is a different decision rule, and this committed
# artifact must be regenerated under it, never inherited.
assert ORDER_REPORT_VERSION == "6", (
    f"ORDER_REPORT_VERSION is {ORDER_REPORT_VERSION!r}; this study "
    "characterises rule version '6' — regenerate deliberately")

# ------------------------------------------------------------ the ONE null
CANONICAL_NULL_STATEMENT = (
    "Operative confirmatory null (within-unit joint swap invariance): for every "
    "matched experimental unit i, the joint distribution of the paired terminal "
    "outcomes is invariant under exchanging presentation labels A and B — "
    "(Y_iA, Y_iB) =d (Y_iB, Y_iA) — subject to the preregistered across-unit "
    "independence / exchangeability-block assumptions. This implies equality of "
    "the population-marginal terminal-action distributions, but the within-pair "
    "permutation test is NOT claimed to be an exact test of bare population-"
    "marginal equality alone.")
assert CANONICAL_NULL_STATEMENT == M8_NULL_STATEMENT, (
    "the script's canonical null statement drifted from the audited "
    "registry.M8_NULL_STATEMENT anchor")

# ------------------------------------------------------------ frozen design
CONDITIONS = {"A": "scramble_dev_m8", "B": "scramble_perm_m8",
              "C": "scramble_sham_m8"}
TERMINAL_DP_ID = "d_partner"
MENU = ("share_resource", "verify_first", "decline_partnership",
        "defer_decision")
SAMPLER_SEEDS = tuple(range(2001, 2025))
S1, S2 = SAMPLER_SEEDS[:12], SAMPLER_SEEDS[12:]
VARIANTS = (("v0_caravan", 42), ("v1_workshop", 1))
UNITS = tuple((variant, scen_seed, samp)
              for variant, scen_seed in VARIANTS for samp in SAMPLER_SEEDS)
UNITS_PER_CONDITION = len(UNITS)                                   # 48

FROZEN_POLICY = {
    "policy_version": "1",
    "admissibility_version": DECISION_ADMISSIBILITY_VERSION,
    "max_non_decision_rate": 0.20,
    "max_non_decision_rate_delta": 0.05,
    "min_admissible_effective_n": 20,
    "on_violation": "refuse",
}
# the EXACT bundle registry.load_thresholds serves to the production path —
# the CI regression asserts echo equality against the registry-served bundle.
FROZEN_THRESHOLDS = {
    "bootstrap_iterations": 10000,
    "bootstrap_seed": 20260719,
    "confidence": 0.95,
    "noise_floor_split": {"S1": list(S1), "S2": list(S2)},
    "min_detectable_effect": 0.35,
    "permutation_iterations": 10000,
    "permutation_seed": 20260719,
    "alpha": 0.05,
    "sham_equivalence_margin": 0.25,
    "power_target": M8_POWER_TARGET,
    "type_i_criterion": M8_TYPE_I_CRITERION,
    "max_surviving_delta": 2,
}

ALPHA = FROZEN_THRESHOLDS["alpha"]
MDE = FROZEN_THRESHOLDS["min_detectable_effect"]
POWER_TARGET = FROZEN_THRESHOLDS["power_target"]

# ------------------------------------------------------------ trial counts
CHARGED_TRIALS = 400            # copy-mode type-I + power arms (frozen criteria)
TYPE_I_HIGH_TRIALS = 3000       # law-exchangeable type-I arms: tight CP-95 upper
CONTEXT_TRIALS = 200            # reported-with-CI context arms

# per-condition distributions (over MENU, in order)
UNIFORM = (0.25, 0.25, 0.25, 0.25)
GRADED = (0.40, 0.30, 0.20, 0.10)
CONCENTRATED = (0.85, 0.05, 0.05, 0.05)
# the power grid: TV(GRADED, .) equals the named effect EXACTLY
POWER_B = {
    0.25: (0.15, 0.30, 0.20, 0.35),
    0.35: (0.05, 0.30, 0.20, 0.45),
    0.50: (0.05, 0.15, 0.30, 0.50),
    0.75: (0.00, 0.00, 0.15, 0.85),
}
# TV = 1.0 is unreachable from GRADED over a shared 4-action support (max
# 0.9), so the grid endpoint uses disjoint two-action supports.
HALF_AB = (0.5, 0.5, 0.0, 0.0)
HALF_CD = (0.0, 0.0, 0.5, 0.5)
POWER_GRID = (0.25, 0.35, 0.50, 0.75, 1.0)
# The sham-gate leakage probe contaminates C by exactly the sham-equivalence
# MARGIN (0.25), NOT the MDE (0.35). The gate's clause-2 warrant is
# q_AC < sham_equivalence_margin, so the most stringent leakage test sits at
# the margin itself — where observed q_AC can occasionally fall just inside
# the warrant. Contaminating at the MDE (0.35 > margin) would let the gate
# refuse trivially and test far less. This decoupling mirrors the frozen
# threshold decoupling: the margin polices a finer scale than the MDE.
SHAM_MARGIN = FROZEN_THRESHOLDS["sham_equivalence_margin"]
SHAM_C_AT_MARGIN = POWER_B[SHAM_MARGIN]

# Non-exchangeable relabeling permutations over MENU indices: a deterministic
# coupling B_i = MENU[perm[base_i]] applied to a BALANCED base (each action
# exactly UNITS_PER_CONDITION / |MENU| = 12 times). A permutation of a balanced
# multiset is the same balanced multiset, so the population marginals of A, B
# and C are IDENTICALLY uniform (TV(A,B) = 0 exactly, every pack), yet the
# within-unit joint is NOT swap-symmetric — swap invariance is violated with a
# marginal statistic pinned to zero.
CYCLE4 = (1, 2, 3, 0)          # full 4-cycle 0->1->2->3->0 (order 4, derangement)
CYCLE3_FIXED = (1, 2, 0, 3)    # 3-cycle 0->1->2->0 with action 3 a fixed point

# Each arm declares, per comparison axis ("AB", "AC"), whether the swap-
# invariance null HOLDS on that axis, plus a `null_mode`:
#   "copy"             -> null holds; one draw copied across conditions
#                         (realizations byte-identical). Verified by concordance.
#   "law_exchangeable" -> null holds; A/B/C iid from the SAME per-condition law
#                         (realizations DIFFER). Verified by LAW (equal per-
#                         condition distributions + iid independent generation).
#   "nonexchangeable_alternative" -> the null is FALSE via a non-exchangeable
#                         equal-marginal coupling (TV=0, undetectable). AC held
#                         null by copy.
#   "marginal_shift"   -> the null is FALSE via a genuine marginal shift on AB;
#                         AC held null by copy (power arms) or contaminated
#                         (sham arm). Detectable.
# Every arm also carries `marginals` (the per-condition law) and `coupling`
# metadata, so two arms with equal marginal-TV are never conflated when one is
# jointly exchangeable and the other is not.
ARMS = {
    # ---- swap-invariance null, COPY mode (charged type_i): each unit's action
    # generated ONCE and copied across A/B/C exactly, so every matched pair is
    # byte-identical and trivially exchangeable. Different unit-action laws prove
    # the structural zero is not an artifact of one distribution.
    "sharp_h0_iid_uniform": {
        "kind": "sharp_iid", "per": {"unit": UNIFORM},
        "axes": {"AB": True, "AC": True}, "null_mode": "copy",
        "coupling": "copy_identical",
        "marginals": {"A": UNIFORM, "B": UNIFORM, "C": UNIFORM,
                      "equal_marginals": True},
        "trials": CHARGED_TRIALS, "seed": 101000, "charged": "type_i"},
    "sharp_h0_iid_graded": {
        "kind": "sharp_iid", "per": {"unit": GRADED},
        "axes": {"AB": True, "AC": True}, "null_mode": "copy",
        "coupling": "copy_identical",
        "marginals": {"A": GRADED, "B": GRADED, "C": GRADED,
                      "equal_marginals": True},
        "trials": CHARGED_TRIALS, "seed": 102000, "charged": "type_i"},
    "sharp_h0_iid_concentrated": {
        "kind": "sharp_iid", "per": {"unit": CONCENTRATED},
        "axes": {"AB": True, "AC": True}, "null_mode": "copy",
        "coupling": "copy_identical",
        "marginals": {"A": CONCENTRATED, "B": CONCENTRATED, "C": CONCENTRATED,
                      "equal_marginals": True},
        "trials": CHARGED_TRIALS, "seed": 103000, "charged": "type_i"},
    # dependent across units (pack-level latent mode) but still copied
    # identically across A/B/C — a DEPENDENCE-ROBUSTNESS arm: the across-unit
    # independence assumption is deliberately broken while swap invariance still
    # holds, and the rule must still control type-I (expected <= alpha).
    "sharp_h0_shared_latent": {
        "kind": "sharp_latent", "per": None,
        "axes": {"AB": True, "AC": True}, "null_mode": "copy",
        "coupling": "shared_latent_copy",
        "marginals": {"A": "pack-latent-mode law, identical across A/B/C",
                      "B": "identical to A", "C": "identical to A",
                      "equal_marginals": True,
                      "note": "dependence-robustness arm: dependent across "
                              "units, swap-invariant within unit"},
        "trials": CHARGED_TRIALS, "seed": 104000, "charged": "type_i"},
    # ---- swap-invariance null, LAW-EXCHANGEABLE mode (charged type_i, a-006):
    # A, B, C drawn iid from ONE per-condition law. The realizations DIFFER unit
    # by unit, but the pair (A_i, B_i) is exchangeable and independent across
    # units, so the GENERATING LAW is swap-invariant — a genuine null case,
    # charged type-I. High trial count for a tight CP-95 upper bound; the
    # permutation test is empirically conservative on this discrete design.
    "iid_equal_marginals_uniform": {
        "kind": "law_exch", "per": {"A": UNIFORM, "B": UNIFORM, "C": UNIFORM},
        "axes": {"AB": True, "AC": True}, "null_mode": "law_exchangeable",
        "coupling": "iid_same_law",
        "marginals": {"A": UNIFORM, "B": UNIFORM, "C": UNIFORM,
                      "equal_marginals": True},
        "trials": TYPE_I_HIGH_TRIALS, "seed": 105000, "charged": "type_i"},
    "iid_equal_marginals_graded": {
        "kind": "law_exch", "per": {"A": GRADED, "B": GRADED, "C": GRADED},
        "axes": {"AB": True, "AC": True}, "null_mode": "law_exchangeable",
        "coupling": "iid_same_law",
        "marginals": {"A": GRADED, "B": GRADED, "C": GRADED,
                      "equal_marginals": True},
        "trials": TYPE_I_HIGH_TRIALS, "seed": 106000, "charged": "type_i"},
    "iid_equal_marginals_concentrated": {
        "kind": "law_exch",
        "per": {"A": CONCENTRATED, "B": CONCENTRATED, "C": CONCENTRATED},
        "axes": {"AB": True, "AC": True}, "null_mode": "law_exchangeable",
        "coupling": "iid_same_law",
        "marginals": {"A": CONCENTRATED, "B": CONCENTRATED, "C": CONCENTRATED,
                      "equal_marginals": True},
        "trials": TYPE_I_HIGH_TRIALS, "seed": 107000, "charged": "type_i"},
    # ---- NON-EXCHANGEABLE equal-marginal ALTERNATIVES (a-006): equal marginals
    # (TV(A,B) = 0 exactly) but a non-exchangeable within-unit joint. Swap
    # invariance is FALSE, yet the marginal TV statistic is identically zero, so
    # the frozen rule cannot reject (power ~ 0). This DOCUMENTS the outside-null
    # sensitivity limitation; it is NOT a type-I failure and is never charged
    # type-I. Two mechanically distinct couplings, both undetectable.
    "alternative_nonexch_cycle4": {
        "kind": "nonexch", "per": {"perm": CYCLE4},
        "axes": {"AB": False, "AC": True},
        "null_mode": "nonexchangeable_alternative",
        "coupling": "nonexchangeable_cycle4",
        "marginals": {"A": UNIFORM, "B": UNIFORM, "C": UNIFORM,
                      "equal_marginals": True,
                      "note": "B_i = A_i shifted +1 (mod 4); balanced base -> "
                              "TV(A,B)=0; joint not swap-symmetric"},
        "trials": CHARGED_TRIALS, "seed": 111000,
        "charged": "alternative_nonexchangeable"},
    "alternative_nonexch_cycle3_fixed": {
        "kind": "nonexch", "per": {"perm": CYCLE3_FIXED},
        "axes": {"AB": False, "AC": True},
        "null_mode": "nonexchangeable_alternative",
        "coupling": "nonexchangeable_cycle3_fixed",
        "marginals": {"A": UNIFORM, "B": UNIFORM, "C": UNIFORM,
                      "equal_marginals": True,
                      "note": "B_i = 3-cycle(A_i) with one fixed point; balanced "
                              "base -> TV(A,B)=0; joint not swap-symmetric"},
        "trials": CHARGED_TRIALS, "seed": 112000,
        "charged": "alternative_nonexchangeable"},
    # ---- the sham-adequacy gate under contamination at the MARGIN scale (the
    # threshold the gate actually polices), with a decisive genuine A/B effect:
    # measures residual process-level leakage where it is most probative.
    "sham_contaminated_at_margin": {
        "kind": "iid",
        "per": {"A": GRADED, "B": POWER_B[0.75], "C": SHAM_C_AT_MARGIN},
        "axes": {"AB": False, "AC": False}, "null_mode": "marginal_shift",
        "coupling": "sham_margin_leak",
        "marginals": {"A": GRADED, "B": POWER_B[0.75], "C": SHAM_C_AT_MARGIN,
                      "equal_marginals": False},
        "trials": CONTEXT_TRIALS, "seed": 109000,
        "charged": "sham_gate_context"},
}
# ---- the power grid: A ~ GRADED (disjoint-support base at the 1.0 endpoint),
# B shifted by exactly the named effect (a genuine MARGINAL SHIFT — swap
# invariance violated on AB), C copied from A (the sham axis holds the null
# exactly, verified). The arm at the frozen min_detectable_effect is charged
# against power_target; the rest are curve context.
for _i, _eff in enumerate(POWER_GRID):
    if _eff == 1.0:
        _a, _b = HALF_AB, HALF_CD
    else:
        _a, _b = GRADED, POWER_B[_eff]
    ARMS[f"power_at_tv_{int(round(_eff * 100)):03d}"] = {
        "kind": "power", "per": {"A": _a, "B": _b}, "effect": _eff,
        "axes": {"AB": False, "AC": True}, "null_mode": "marginal_shift",
        "coupling": "marginal_shift",
        "marginals": {"A": _a, "B": _b, "C": _a, "equal_marginals": False},
        "trials": CHARGED_TRIALS, "seed": 110000 + _i * 1000,
        "charged": "power" if _eff == MDE else "power_curve"}


# ------------------------------------------------- schedule generation + proof

def build_schedule(kind: str, per, rng: random.Random) -> dict:
    """The complete potential-outcome schedule for one trial:
    {(cond, variant, scen_seed, samp): action}. Draw order is FIXED
    (condition-major, declared unit order), so a trial seed reproduces the
    same schedule regardless of scheduling."""
    sched = {}
    if kind == "sharp_iid":
        # COPY mode: ONE draw per unit, copied across conditions EXACTLY — swap
        # invariance holds by construction (byte-identical pair), no condition-
        # dependent noise.
        for unit in UNITS:
            action = _draw(rng, per["unit"])
            for cond in CONDITIONS:
                sched[(cond,) + unit] = action
    elif kind == "sharp_latent":
        # COPY mode with across-unit DEPENDENCE: a pack-level latent mode moves
        # every unit, identically in A/B/C. Swap invariance still holds (the
        # pair is byte-identical); only the independence assumption is broken.
        mode = rng.randrange(2)
        for unit in UNITS:
            variant, _scen, samp = unit
            i = (samp + (0 if variant.startswith("v0") else 7) + mode * 3) % 4
            for cond in CONDITIONS:
                sched[(cond,) + unit] = MENU[i]
    elif kind == "law_exch":
        # LAW-EXCHANGEABLE null: A and B drawn iid from the SAME per-condition
        # law (per["A"] == per["B"]), so their realizations differ unit by unit
        # while the pair (A_i, B_i) is exchangeable and independent across units
        # — the generating law is swap-invariant. C COPIES A (per["C"] equals the
        # same law, realized identically), so the sham axis holds the null
        # exactly and the type-I characterization isolates the A/B swap-
        # invariance permutation test — the SAME clean-sham construction the
        # power arms use. Measuring the confirmatory AB decision under an
        # independent C instead would confound the swap-invariance type-I rate
        # with sham-gate behaviour (an independent sham fails on a distribution-
        # dependent fraction of trials, suppressing or admitting positives
        # unevenly across the marginal families).
        for unit in UNITS:
            sched[("A",) + unit] = _draw(rng, per["A"])
        for unit in UNITS:
            sched[("B",) + unit] = _draw(rng, per["B"])
        for unit in UNITS:
            sched[("C",) + unit] = sched[("A",) + unit]
    elif kind == "iid":
        # A marginal-shift / contaminated process (the sham arm): each
        # (cond, unit) drawn INDEPENDENTLY from per[cond], including an
        # independent C — used only where an independent, possibly contaminated
        # sham axis is the point.
        for cond in ("A", "B", "C"):
            for unit in UNITS:
                sched[(cond,) + unit] = _draw(rng, per[cond])
    elif kind == "nonexch":
        # NON-EXCHANGEABLE equal-marginal coupling: a BALANCED base (each action
        # exactly UNITS_PER_CONDITION/|MENU| times) shuffled per trial; A_i is
        # the base action, B_i is a fixed non-symmetric relabeling perm(base_i),
        # C_i copies A_i. A permutation of a balanced multiset is balanced, so
        # TV(A,B) = 0 exactly every pack, yet the within-unit joint is not
        # swap-symmetric — swap invariance is FALSE and undetectable.
        perm = per["perm"]
        assert UNITS_PER_CONDITION % len(MENU) == 0
        base_idx = [a for a in range(len(MENU))
                    for _ in range(UNITS_PER_CONDITION // len(MENU))]
        rng.shuffle(base_idx)
        for unit, bi in zip(UNITS, base_idx):
            sched[("A",) + unit] = MENU[bi]
            sched[("B",) + unit] = MENU[perm[bi]]
            sched[("C",) + unit] = MENU[bi]
    elif kind == "power":
        # MARGINAL-SHIFT alternative: A from the base law, B independently from
        # the shifted law (swap invariance violated on A/B), C COPIED from A (the
        # null holds on A/C: seeded decoding makes 'the rewording changed
        # nothing' mean byte-identical outcomes).
        for unit in UNITS:
            sched[("A",) + unit] = _draw(rng, per["A"])
        for unit in UNITS:
            sched[("B",) + unit] = _draw(rng, per["B"])
        for unit in UNITS:
            sched[("C",) + unit] = sched[("A",) + unit]
    else:
        raise ValueError(kind)
    return sched


def verify_schedule(sched: dict, axes: dict, null_mode: str,
                    per=None, where: str = "") -> dict:
    """THE MECHANICAL ASSERTION (a-004 finding 0, sharpened at a-006): before any
    trial is analysed, the generated potential-outcome schedule is checked
    unit-by-unit against the arm's DECLARED null status and null_mode per axis.
    The proof is MODE-SPECIFIC — never weakened, always proving the property the
    mode actually holds:

    * a TRUE (null-holding) axis in null_mode "law_exchangeable" is verified by
      LAW — the declared per-condition distributions must be EQUAL (per["A"] ==
      per[other]); the realizations MAY differ (the A/B pair, drawn iid from the
      same law) or be identical (the copied A/C sham axis), and either is correct
      because it is the GENERATING LAW, not the realization, that is swap-
      invariant.
    * a TRUE axis in any other mode (copy / the copied AC axis of alternative
      and power arms) is verified by IDENTICAL REALIZATION — every matched unit
      must be concordant (one draw copied across conditions).
    * a FALSE (alternative) axis is verified by REALIZATION DISCORDANCE — at
      least one matched unit must differ, so the arm genuinely departs from a
      trivial copy on that axis.

    Returns {axis: discordant_unit_count}; raises on any mismatch."""
    counts = {}
    for axis, null_holds in axes.items():
        other = axis[1]                       # "AB" -> "B", "AC" -> "C"
        discordant = [u for u in UNITS
                      if sched[("A",) + u] != sched[(other,) + u]]
        counts[axis] = len(discordant)
        if null_holds:
            if null_mode == "law_exchangeable":
                # LAW proof — the generating law, not the realization, is
                # swap-invariant. Do NOT charge realization discordance.
                if per is None or per.get("A") is None \
                        or per.get(other) is None:
                    raise AssertionError(
                        f"{where}: axis {axis} declared null-holding in "
                        "law_exchangeable mode but the per-condition laws are "
                        "not both declared")
                if per["A"] != per[other]:
                    raise AssertionError(
                        f"{where}: axis {axis} declared a LAW-EXCHANGEABLE null "
                        f"but per['A'] != per['{other}'] — the generating law "
                        "is not swap-invariant and cannot be charged type-I by "
                        "law")
            else:
                if discordant:
                    raise AssertionError(
                        f"{where}: axis {axis} declared a COPY null ({null_mode}"
                        f") but {len(discordant)} of {len(UNITS)} matched units "
                        "are discordant — this schedule was not built by copying "
                        "one draw across conditions and may not be charged as a "
                        "copy-mode null arm")
        else:
            if not discordant:
                raise AssertionError(
                    f"{where}: axis {axis} declared an ALTERNATIVE but every "
                    "matched unit is concordant — this schedule holds the null "
                    "and cannot serve as a separating alternative")
    return counts


# ------------------------------------------------------------ pack builder

def _write_unit(root: str, cond: str, variant: str, scen_seed: int,
                samp: int, action: str) -> str:
    rid = f"{cond}_{variant}_{samp}"
    d = os.path.join(root, rid)
    os.mkdir(d)
    run = {"run_id": rid, "scenario_id": CONDITIONS[cond], "agent_id": "live",
           "variant_id": variant, "seed": scen_seed, "scenario_seed": scen_seed,
           "sampler_seed": samp, "reportable": True,
           "stochastic_reportable": True, "stochastic_exclusion_reasons": [],
           "agent_regime_id": "r" * 64,
           "agent_config": {"driver": "ollama_local", "temperature": 0.7},
           "sampling": {"mode": "stochastic", "temperature": 0.7},
           "arbitration": "planner_priority",
           "interaction_mode": "sequential_history"}
    with open(os.path.join(d, "run.json"), "w", encoding="utf-8") as fh:
        json.dump(run, fh)

    def node(dp_id, final, actions):
        return {"kind": "decision_node",
                "data": {"dp_id": dp_id, "final_action": final,
                         "available_actions": list(actions),
                         "arbitration_winner": "planner",
                         "reflex_choice": {"action_id": final,
                                           "meta": {"parse_status": "ok"}},
                         "planner_choice": {"action_id": final,
                                            "meta": {"parse_status": "ok"}},
                         "moral_tags": [], "state_before": {"facts": {}}}}

    lines = [node("e_event", "expose", ["expose"]),
             node(TERMINAL_DP_ID, action, MENU)]
    with open(os.path.join(d, "decisions.jsonl"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(json.dumps(x) for x in lines) + "\n")
    with open(os.path.join(d, "captures.jsonl"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"key": f"{TERMINAL_DP_ID}/plan",
                             "raw_text": action}) + "\n")
    return d


def _attest(dirs: list) -> dict:
    """The Director-defined replay attestation, generated over the packs'
    ACTUAL current bytes — the same contract the sweep-side generator emits,
    so the study exercises the real verification path."""
    runs = {}
    for d in dirs:
        with open(os.path.join(d, "run.json"), encoding="utf-8") as fh:
            run = json.load(fh)
        entry = {"replay_ok": True}
        for fname, key in (("run.json", "run_json_sha256"),
                           ("decisions.jsonl", "decisions_sha256"),
                           ("captures.jsonl", "captures_sha256")):
            h = hashlib.sha256()
            with open(os.path.join(d, fname), "rb") as fh:
                h.update(fh.read())
            entry[key] = h.hexdigest()
        runs[run["run_id"]] = entry
    return {"attestation_version": "1", "runs": runs}


def _draw(rng: random.Random, weights) -> str:
    u, acc = rng.random(), 0.0
    for action, w in zip(MENU, weights):
        acc += w
        if u <= acc:
            return action
    return MENU[-1]


def run_trial(spec: tuple) -> str:
    """One complete pack through the frozen path: generate the schedule, PROVE
    it matches the arm's declared null status and mode, then analyse. Returns
    the verdict."""
    kind, per, axes, null_mode, trial_seed, where = spec
    rng = random.Random(trial_seed)
    sched = build_schedule(kind, per, rng)
    verify_schedule(sched, axes, null_mode, per, where)   # raises before analysis
    root = tempfile.mkdtemp(prefix="m8oc_")
    try:
        dirs = []
        for cond in ("A", "B", "C"):
            for variant, scen_seed, samp in UNITS:
                dirs.append(_write_unit(
                    root, cond, variant, scen_seed, samp,
                    sched[(cond, variant, scen_seed, samp)]))
        rep = order_sensitivity_report(
            dirs, CONDITIONS,
            admissibility_policy=FROZEN_POLICY,
            thresholds=FROZEN_THRESHOLDS,
            replay_attestation=_attest(dirs),
            terminal_dp_id=TERMINAL_DP_ID,
            surviving_counts={"A": UNITS_PER_CONDITION,
                              "B": UNITS_PER_CONDITION,
                              "C": UNITS_PER_CONDITION})
        return rep["per_agent"]["live"]["verdict"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ------------------------------------------------------------ exact binomial CI

def _binom_sf(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Bin(n, p). Stdlib only, numerically stable.

    Each term is computed in log space via lgamma and exponentiated (every
    term is a probability <= 1, so nothing overflows). The earlier form used
    math.comb(n, i) * p**i directly, which overflows for the high-trial arms:
    math.comb(3000, 1500) ~ 1e901 exceeds float range before the tiny p**i
    factor can rein it in. This log form is exact to floating precision at
    every n the study uses."""
    if k <= 0:
        return 1.0
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    lp = math.log(p)
    lq = math.log1p(-p)
    lgn1 = math.lgamma(n + 1)
    total = 0.0
    for i in range(k, n + 1):
        log_term = (lgn1 - math.lgamma(i + 1) - math.lgamma(n - i + 1)
                    + i * lp + (n - i) * lq)
        total += math.exp(log_term)
    return total


def clopper_pearson(k: int, n: int, confidence: float = 0.95) -> tuple:
    """Exact two-sided Clopper-Pearson interval for a binomial proportion.

    Solved by bisection on the exact binomial tail — no scipy, deterministic,
    and the same implementation the CI regression recomputes against."""
    tail = (1.0 - confidence) / 2.0

    def solve(f, lo, hi, rising):
        for _ in range(200):
            mid = (lo + hi) / 2.0
            if (f(mid) < tail) == rising:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2.0

    lower = 0.0 if k == 0 else solve(lambda p: _binom_sf(k, n, p), 0.0, 1.0,
                                     True)
    upper = 1.0 if k == n else solve(
        lambda p: 1.0 - _binom_sf(k + 1, n, p), 0.0, 1.0, False)
    return round(lower, 6), round(upper, 6)


# ------------------------------------------------------------ the study

def _criterion(arm: dict, lo: float, hi: float) -> dict:
    charged = arm["charged"]
    if charged == "type_i":
        mode = arm.get("null_mode")
        if mode == "law_exchangeable":
            detail = ("swap-invariance null, LAW-EXCHANGEABLE mode (a-006): "
                      "A/B/C are drawn iid from the SAME per-condition law, so "
                      "the realizations differ unit by unit while the pair "
                      "(A_i, B_i) is exchangeable and independent across units "
                      "— a genuine swap-invariance null case, verified by law "
                      "pre-analysis (equal per-condition distributions + iid "
                      "independent generation). The within-pair permutation "
                      "reference is valid, and on this discrete 4-action / n=48 "
                      "design the test is empirically CONSERVATIVE; the exact "
                      "CP-95 UPPER bound must still fall at or below alpha, "
                      "resolved at the frozen high trial count reported in "
                      "ci_method.type_i_high_trials.")
        else:
            detail = ("swap-invariance null, COPY mode (a-006): one draw per "
                      "unit is copied across A/B/C exactly (verified concordant "
                      "unit-by-unit pre-analysis), so every matched pair is "
                      "byte-identical and the structural rejection rate is "
                      "ZERO; the CP-95 upper bound holds mechanically. "
                      "sharp_h0_shared_latent additionally breaks across-unit "
                      "independence (dependence-robustness) and must still "
                      "control type-I.")
        return {
            "statement": FROZEN_THRESHOLDS["type_i_criterion"],
            "null_mode": mode, "detail": detail,
            "alpha": ALPHA, "pass": hi <= ALPHA}
    if charged == "power":
        return {
            "statement": ("Clopper-Pearson 95% LOWER bound of measured power "
                          "at min_detectable_effect must reach the frozen "
                          "power_target"),
            "power_target": POWER_TARGET, "pass": lo >= POWER_TARGET}
    if charged == "power_curve":
        return {"statement": ("power-curve context: informs the frozen "
                              "min_detectable_effect selection (see "
                              "mde_selection); not itself a pass/fail "
                              "criterion"), "pass": True}
    if charged == "alternative_nonexchangeable":
        return {
            "statement": ("NON-EXCHANGEABLE equal-marginal alternative (a-006): "
                          "the population marginals are equal (TV(A,B) = 0 "
                          "exactly) but the within-unit joint is a "
                          "non-exchangeable deterministic relabeling coupling, "
                          "so swap invariance is FALSE. Because the marginal TV "
                          "statistic is identically zero, the frozen rule "
                          "cannot reject (power ~ 0). This DOCUMENTS the "
                          "design's outside-null sensitivity limitation — TV=0 "
                          "is never evidence that swap invariance holds — and "
                          "is NEVER charged against type-I."),
            "pass": True}
    if charged == "sham_gate_context":
        return {
            "statement": ("sham-gate residual LEAKAGE context (reported with "
                          "CI, not a frozen fitness criterion): the clause-2 "
                          "warrant is granted on the OBSERVED pack, so no "
                          "finite-sample rule can bound the unobserved "
                          "generating process — in a small fraction of "
                          "trials a contaminated-at-margin sham looks null with "
                          "its warrant intact and a decisive A/B rejection "
                          "promotes as the frozen rule directs. The frozen "
                          "fitness criteria of this design are exactly "
                          "type_i_criterion and power_target; the ABSOLUTE "
                          "observation-level guarantees are pinned "
                          "deterministically in the test suite (the "
                          "reproduced boundary pack TV(A,C) = q_AC = margin "
                          "is inconclusive, never positive; every emitted "
                          "positive carries the sham warrant)."),
            "pass": True}
    return {"statement": "context only", "pass": True}


def _jsonify_marginals(marginals: dict) -> dict:
    out = {}
    for k, v in marginals.items():
        out[k] = list(v) if isinstance(v, (list, tuple)) else v
    return out


def run_arm(name: str, arm: dict, workers: int) -> dict:
    specs = [(arm["kind"], arm.get("per"), arm["axes"], arm["null_mode"],
              arm["seed"] + i, f"{name}[trial {i}]")
             for i in range(arm["trials"])]
    if workers > 1:
        with multiprocessing.Pool(workers) as pool:
            verdicts = pool.map(run_trial, specs)
    else:
        verdicts = [run_trial(s) for s in specs]
    tally: dict = {}
    for v in verdicts:
        tally[v] = tally.get(v, 0) + 1
    positives = tally.get("distributional_order_effect_observed", 0)
    n = arm["trials"]
    lo, hi = clopper_pearson(positives, n)
    out = {"kind": arm["kind"], "charged": arm["charged"],
           "null_mode": arm["null_mode"], "coupling": arm["coupling"],
           "trials": n, "seed": arm["seed"],
           "null_axes": dict(arm["axes"]),
           "marginals": _jsonify_marginals(arm["marginals"]),
           "tally": {k: tally[k] for k in sorted(tally)},
           "positive_rate": round(positives / n, 6),
           "positive_rate_ci95": [lo, hi]}
    if arm.get("effect") is not None:
        out["effect_tv"] = arm["effect"]
    if arm.get("per") and arm["kind"] != "nonexch":
        out["per_condition"] = {c: list(p)
                                for c, p in sorted(arm["per"].items())}
    elif arm["kind"] == "nonexch":
        out["per_condition"] = {"perm": list(arm["per"]["perm"])}
    out["criterion"] = _criterion(arm, lo, hi)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int,
                    default=max(1, multiprocessing.cpu_count() - 1))
    ap.add_argument("--out", default=os.path.join(
        ROOT, "derived", "textlab", "m8-operating-characteristics.json"))
    ap.add_argument("--trials-scale", type=float, default=1.0,
                    help="scale all trial counts (smoke runs only; the "
                         "committed artifact must use 1.0)")
    args = ap.parse_args(argv)

    arms = {}
    t0 = time.monotonic()
    for name, arm in ARMS.items():
        spec = dict(arm)
        spec["trials"] = max(1, int(round(arm["trials"] * args.trials_scale)))
        a0 = time.monotonic()
        arms[name] = run_arm(name, spec, args.workers)
        arms[name]["arm_runtime_seconds"] = round(time.monotonic() - a0, 1)
        print(f"[{name}] {arms[name]['tally']} "
              f"rate={arms[name]['positive_rate']} "
              f"ci95={arms[name]['positive_rate_ci95']} "
              f"pass={arms[name]['criterion']['pass']} "
              f"({arms[name]['arm_runtime_seconds']}s)", flush=True)
    runtime = round(time.monotonic() - t0, 1)

    # ------------------------------------------------ frozen MDE selection
    # min_detectable_effect must be the SMALLEST grid effect whose measured
    # power CP-95 LOWER bound reaches the frozen power_target — recomputed
    # here from the arms so the committed choice regenerates from the run.
    curve = []
    for name, a in arms.items():
        if a["charged"] in ("power", "power_curve"):
            curve.append({"effect_tv": a["effect_tv"],
                          "arm": name,
                          "positive_rate": a["positive_rate"],
                          "positive_rate_ci95": a["positive_rate_ci95"]})
    curve.sort(key=lambda r: r["effect_tv"])
    eligible = [r["effect_tv"] for r in curve
                if r["positive_rate_ci95"][0] >= POWER_TARGET]
    selected = min(eligible) if eligible else None
    mde_selection = {
        "method": ("smallest grid effect whose measured power CP-95 LOWER "
                   "bound >= power_target, at the exact frozen procedure "
                   "(n = 48 units per condition, 10000-iteration within-pair "
                   "permutation null, sham axis holding the null)"),
        "grid": list(POWER_GRID),
        "power_target": POWER_TARGET,
        "power_curve": curve,
        "selected_effect": selected,
        "frozen_min_detectable_effect": MDE,
        "consistent": selected == MDE,
    }

    # the charged type-I arms (both null modes) gate the study: every one must
    # have its exact CP-95 UPPER bound at or below alpha.
    type_i_pass = all(
        a["criterion"]["pass"]
        for a in arms.values() if a["charged"] == "type_i")

    artifact = {
        "artifact": "m8-operating-characteristics",
        "order_report_version": ORDER_REPORT_VERSION,
        "metrics_version": METRICS_VERSION,
        "admissibility_version": DECISION_ADMISSIBILITY_VERSION,
        "generated_by": "scripts/m8_operating_characteristics.py",
        "trials_scale": args.trials_scale,
        # a-006: the ONE canonical null, echoed verbatim
        "null_form": M8_NULL_FORM,
        "null_statement": CANONICAL_NULL_STATEMENT,
        "schedule_verification": (
            "every trial's generated potential-outcome schedule is verified "
            "unit-by-unit against its arm's declared null status AND null_mode "
            "BEFORE analysis, with a mode-specific proof that is never "
            "weakened: a copy-mode null axis is proven by IDENTICAL REALIZATION "
            "(A_i == B_i == C_i at every matched unit, so the pair is "
            "byte-identical); a law-exchangeable null axis is proven by LAW "
            "(equal per-condition distributions + iid independent generation, "
            "the generating law is swap-invariant though realizations differ); "
            "an alternative axis is proven by REALIZATION DISCORDANCE. A "
            "completed arm is itself the proof — verification raises before any "
            "statistic otherwise."),
        # the EXACT frozen bundle the production path loads; the CI regression
        # asserts echo equality and hash equality against the registry
        "frozen_bundle": {
            "admissibility_policy": dict(FROZEN_POLICY),
            "thresholds": {k: (dict(v) if isinstance(v, dict) else v)
                           for k, v in FROZEN_THRESHOLDS.items()},
            "terminal_dp_id": TERMINAL_DP_ID,
            "conditions": dict(CONDITIONS),
        },
        "frozen_bundle_hashes": {
            "policy_hash": config_hash(FROZEN_POLICY),
            "thresholds_hash": config_hash(FROZEN_THRESHOLDS),
        },
        "arm_taxonomy": {
            "type_i": ("swap-invariance null arms, charged type-I; two null "
                       "modes: 'copy' (identical realizations) and "
                       "'law_exchangeable' (iid from one per-condition law, "
                       "realizations differ but the pair is exchangeable and "
                       "independent across units). Both must satisfy the CP-95 "
                       "upper-bound criterion."),
            "alternative_nonexchangeable": (
                "equal-marginal (TV(A,B)=0) but non-exchangeable within-unit "
                "joint; swap invariance is FALSE yet undetectable by the "
                "marginal statistic — the documented outside-null sensitivity "
                "limitation, never charged type-I."),
            "power": ("genuine marginal-shift alternatives; demonstrate MDE "
                      "0.35 detection under their specific families."),
        },
        "design": {
            "units_per_condition": UNITS_PER_CONDITION,
            "menu": list(MENU),
            "variants": [list(v) for v in VARIANTS],
            "sampler_seeds": list(SAMPLER_SEEDS),
        },
        "ci_method": {
            "interval": "exact two-sided Clopper-Pearson at 95%",
            "outer_trials_per_charged_arm": CHARGED_TRIALS,
            "type_i_high_trials": TYPE_I_HIGH_TRIALS,
            "math": ("copy-mode type-I arms are structural zeros, resolved "
                     "exactly at T=400 (CP-95 upper ~0.0092 at k=0). "
                     "Law-exchangeable type-I arms carry a small non-zero rate "
                     "and run at T=3000 (>= the 2000 floor) for a tight bound: "
                     "the concentrated arm sits at a genuine, conservative "
                     "~0.039 discreteness level, and at T=3000 its CP-95 upper "
                     "bound is ~0.046 < alpha=0.05 with margin, whereas T=2000 "
                     "leaves only p-hat<=0.040 headroom. For power, at T=400 and "
                     "p-hat=0.85 the CP lower bound is ~0.812, so the frozen "
                     "target 0.8 is resolvable against true power ~0.85 or "
                     "better."),
        },
        "arms": arms,
        "mde_selection": mde_selection,
        "runtime": {"seconds": runtime, "workers": args.workers,
                    "python": sys.version.split()[0]},
        "all_criteria_pass": (
            type_i_pass
            and all(a["criterion"]["pass"] for a in arms.values())
            and mde_selection["consistent"]),
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(canonical_json(artifact) + "\n")
    print(f"wrote {args.out} ({runtime}s, all_criteria_pass="
          f"{artifact['all_criteria_pass']}, mde_selection="
          f"{mde_selection['selected_effect']})")
    return 0 if artifact["all_criteria_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
