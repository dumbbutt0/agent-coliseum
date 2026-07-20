#!/usr/bin/env python3
"""m8 Phase-2 — operating characteristics of the FROZEN decision rule (v4).

SCIENTIFIC RE-FREEZE (audit a-004, findings 0 and 1). The previous shape of
this study was blocked for two reasons, both repaired here:

* Finding 0 — ONE NULL EVERYWHERE. The operative null of this design is the
  canonical sharp unit-level null, frozen in planned_design (null_form +
  null_statement), anchored in audited code (registry.M8_NULL_STATEMENT) and
  stated verbatim here:

      Sharp (unit-level) null: for every matched effective unit (variant_id,
      scenario_seed, sampler_seed), presentation order made no difference to
      the terminal action chosen at that unit.

  A sharp-null H0 arm must MECHANICALLY satisfy that statement: each unit's
  terminal action is generated ONCE and copied across A/B/C, exactly — the
  design declares no condition-independent noise, so none is applied. Every
  type-I trial's generated schedule is verified unit-by-unit (A_i == B_i ==
  C_i for all 48 units) BEFORE analysis, and every named alternative arm is
  verified to VIOLATE the null on its declared axis. The former iid
  equal-marginal "H0" arms — whose every generated pack violated the sharp
  null (the audit measured 27-44 discordant units per pack) — are RELABELED
  as exchangeability-robustness context and are never charged as sharp-null
  type-I.

* Finding 1 — FROZEN FITNESS CRITERIA, honest directions. The acceptance
  criteria are no longer script inventions; they are frozen in
  planned_design.thresholds and loaded from the registry bundle:
  - type_i_criterion: "CP-95 upper bound of sharp-null rejection rate <=
    alpha". The UPPER bound — the superseded lower-bound check tested only
    whether excess above alpha was demonstrated, the wrong direction.
  - power_target: 0.8 — the CP-95 LOWER bound of measured power at
    min_detectable_effect must reach it. min_detectable_effect is frozen at
    the smallest grid effect (0.25 / 0.35 / 0.5 / 0.75 / 1.0) whose measured
    power meets that bound under the exact frozen procedure; the artifact's
    mde_selection block recomputes the choice so it regenerates from the
    committed run alone. Effects below the frozen boundary are real
    possibilities this design cannot reliably detect.

POWER IS CHARACTERISED UNDER A SHARPLY-NULL SHAM AXIS, and that is the
faithful model, not a convenience: decoding is seeded per unit, so if the
sham rewording truly makes no difference to a unit's computation the realized
terminal action is IDENTICAL — the sharp surface-form null literally predicts
C_i == A_i. The power arms therefore copy C from A (verified), and the
exchangeability-context arms show honestly what happens when the sham axis is
null only in distribution: the warrant frequently refuses and the design goes
inconclusive — conservative, never anti-conservative.

The study drives `metrics.order_sensitivity_report` (ORDER_REPORT_VERSION 4)
end to end — synthetic run directories, real replay attestations over their
actual bytes, the real terminal-probe / matched-unit / surviving-count /
sham-adequacy gates — at the exact frozen threshold bundle, and writes the
committed artifact

    derived/textlab/m8-operating-characteristics.json

No model is contacted. Every draw comes from `random.Random` with a declared
per-trial seed (trial_seed = arm_seed + trial_index), so the study is
deterministic and independent of worker scheduling.

CI RESOLUTION (unchanged from the 001814 repair, restated): T = 400 outer
trials per charged arm. At T = 400 and p-hat = alpha = 0.05 the exact
Clopper-Pearson 95% interval is ~[0.031, 0.076] (half-width ~0.023 < alpha),
so 2*alpha = 0.10 is resolvable. For the power criterion, at T = 400 and
p-hat = 0.85 the CP-95 lower bound is ~0.812 — the target 0.8 is resolvable
against true power ~0.85 or better.

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
assert ORDER_REPORT_VERSION == "4", (
    f"ORDER_REPORT_VERSION is {ORDER_REPORT_VERSION!r}; this study "
    "characterises rule version '4' — regenerate deliberately")

# ------------------------------------------------------------ the ONE null
CANONICAL_NULL_STATEMENT = (
    "Sharp (unit-level) null: for every matched effective unit (variant_id, "
    "scenario_seed, sampler_seed), presentation order made no difference to "
    "the terminal action chosen at that unit.")
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
CHARGED_TRIALS = 400            # every arm a frozen criterion is judged on
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

# Each arm declares its null status per comparison axis ("AB", "AC"):
#   True  -> the sharp null HOLDS on that axis; verified unit-by-unit equal.
#   False -> the sharp null is VIOLATED on that axis; verified >=1 unit differs.
ARMS = {
    # ---- sharp-null H0 arms (charged type_i): each unit's action generated
    # ONCE and copied across A/B/C exactly. Different unit-action laws prove
    # the zero is structural, not an artifact of one distribution.
    "sharp_h0_iid_uniform": {"kind": "sharp_iid", "per": {"unit": UNIFORM},
                             "axes": {"AB": True, "AC": True},
                             "trials": CHARGED_TRIALS, "seed": 101000,
                             "charged": "type_i"},
    "sharp_h0_iid_graded": {"kind": "sharp_iid", "per": {"unit": GRADED},
                            "axes": {"AB": True, "AC": True},
                            "trials": CHARGED_TRIALS, "seed": 102000,
                            "charged": "type_i"},
    "sharp_h0_iid_concentrated": {"kind": "sharp_iid",
                                  "per": {"unit": CONCENTRATED},
                                  "axes": {"AB": True, "AC": True},
                                  "trials": CHARGED_TRIALS, "seed": 103000,
                                  "charged": "type_i"},
    # dependent across units (pack-level latent mode), still sharp-null true
    "sharp_h0_shared_latent": {"kind": "sharp_latent", "per": None,
                               "axes": {"AB": True, "AC": True},
                               "trials": CHARGED_TRIALS, "seed": 104000,
                               "charged": "type_i"},
    # ---- RELABELED context (audit a-004 finding 0): A, B, C drawn iid from
    # ONE distribution. The PAIR distribution is exchangeable, so rejection
    # stays near alpha for the broader exchangeable family — but every
    # generated pack VIOLATES the sharp null (units disagree), so these are
    # never charged as sharp-null type-I.
    "iid_equal_marginals_uniform": {"kind": "iid",
                                    "per": {"A": UNIFORM, "B": UNIFORM,
                                            "C": UNIFORM},
                                    "axes": {"AB": False, "AC": False},
                                    "trials": CONTEXT_TRIALS, "seed": 105000,
                                    "charged": "exchangeable_context"},
    "iid_equal_marginals_graded": {"kind": "iid",
                                   "per": {"A": GRADED, "B": GRADED,
                                           "C": GRADED},
                                   "axes": {"AB": False, "AC": False},
                                   "trials": CONTEXT_TRIALS, "seed": 106000,
                                   "charged": "exchangeable_context"},
    "iid_equal_marginals_concentrated": {"kind": "iid",
                                         "per": {"A": CONCENTRATED,
                                                 "B": CONCENTRATED,
                                                 "C": CONCENTRATED},
                                         "axes": {"AB": False, "AC": False},
                                         "trials": CONTEXT_TRIALS,
                                         "seed": 107000,
                                         "charged": "exchangeable_context"},
    # ---- the audit's separating case: sharp null FALSE on A/B for every
    # unit, marginal null true across the process. A rejection is the correct
    # sharp unit-level conclusion; never charged against type-I.
    "sharp_false_marginal_true": {"kind": "latent_false", "per": None,
                                  "axes": {"AB": False, "AC": True},
                                  "trials": CONTEXT_TRIALS, "seed": 108000,
                                  "charged": "sharp_violation_detection"},
    # ---- the sham-adequacy gate under contamination at the MARGIN scale
    # (the threshold the gate actually polices), with a decisive genuine A/B
    # effect: measures residual process-level leakage where it is most
    # probative.
    "sham_contaminated_at_margin": {"kind": "iid",
                                    "per": {"A": GRADED, "B": POWER_B[0.75],
                                            "C": SHAM_C_AT_MARGIN},
                                    "axes": {"AB": False, "AC": False},
                                    "trials": CONTEXT_TRIALS, "seed": 109000,
                                    "charged": "sham_gate_context"},
}
# ---- the power grid: A ~ GRADED (disjoint-support base at the 1.0
# endpoint), B shifted by exactly the named effect, C copied from A (the
# sham axis sharply null, verified). The arm at the frozen
# min_detectable_effect is charged against power_target; the rest are curve
# context.
for _i, _eff in enumerate(POWER_GRID):
    if _eff == 1.0:
        _a, _b = HALF_AB, HALF_CD
    else:
        _a, _b = GRADED, POWER_B[_eff]
    ARMS[f"power_at_tv_{int(round(_eff * 100)):03d}"] = {
        "kind": "power", "per": {"A": _a, "B": _b}, "effect": _eff,
        "axes": {"AB": False, "AC": True},
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
        # ONE draw per unit, copied across conditions EXACTLY — the sharp
        # null holds by construction, with no condition-dependent noise.
        for unit in UNITS:
            action = _draw(rng, per["unit"])
            for cond in CONDITIONS:
                sched[(cond,) + unit] = action
    elif kind == "sharp_latent":
        # pack-level latent mode moves every unit, identically in A/B/C:
        # dependent across units, sharp null still true.
        mode = rng.randrange(2)
        for unit in UNITS:
            variant, _scen, samp = unit
            i = (samp + (0 if variant.startswith("v0") else 7) + mode * 3) % 4
            for cond in CONDITIONS:
                sched[(cond,) + unit] = MENU[i]
    elif kind == "iid":
        for cond in ("A", "B", "C"):
            for unit in UNITS:
                sched[(cond,) + unit] = _draw(rng, per[cond])
    elif kind == "latent_false":
        # the audit's separating case: A/C one action, B another; mode flips.
        mode = rng.randrange(2)
        pair = (("share_resource", "decline_partnership")
                if mode == 0 else ("decline_partnership", "share_resource"))
        for cond in ("A", "B", "C"):
            for unit in UNITS:
                sched[(cond,) + unit] = pair[1] if cond == "B" else pair[0]
    elif kind == "power":
        # A drawn from the base law, B independently from the shifted law
        # (sharp null violated on A/B), C COPIED from A (sharp null true on
        # A/C: seeded decoding makes 'the rewording changed nothing' mean
        # byte-identical outcomes).
        for unit in UNITS:
            sched[("A",) + unit] = _draw(rng, per["A"])
        for unit in UNITS:
            sched[("B",) + unit] = _draw(rng, per["B"])
        for unit in UNITS:
            sched[("C",) + unit] = sched[("A",) + unit]
    else:
        raise ValueError(kind)
    return sched


def verify_schedule(sched: dict, axes: dict, where: str = "") -> dict:
    """THE MECHANICAL ASSERTION (audit a-004 finding 0, minimum_regression):
    before any trial is analysed, the generated potential-outcome schedule is
    checked unit-by-unit against the arm's DECLARED null status per axis —
    a sharp-null axis must satisfy the canonical statement at every matched
    unit; an alternative axis must violate it at one or more units. Returns
    {axis: discordant_unit_count}; raises on any mismatch."""
    counts = {}
    for axis, null_holds in axes.items():
        other = axis[1]                       # "AB" -> "B", "AC" -> "C"
        discordant = [u for u in UNITS
                      if sched[("A",) + u] != sched[(other,) + u]]
        counts[axis] = len(discordant)
        if null_holds and discordant:
            raise AssertionError(
                f"{where}: axis {axis} declared SHARP-NULL TRUE but "
                f"{len(discordant)} of {len(UNITS)} matched units are "
                "discordant — this schedule does not satisfy the canonical "
                "sharp null and may not be charged as a null arm")
        if not null_holds and not discordant:
            raise AssertionError(
                f"{where}: axis {axis} declared an ALTERNATIVE but every "
                "matched unit is concordant — this schedule satisfies the "
                "sharp null and cannot serve as a separating alternative")
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
    """One complete pack through the frozen path: generate the schedule,
    PROVE it matches the arm's declared null status, then analyse. Returns
    the verdict."""
    kind, per, axes, trial_seed, where = spec
    rng = random.Random(trial_seed)
    sched = build_schedule(kind, per, rng)
    verify_schedule(sched, axes, where)          # raises before any analysis
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
    """P(X >= k) for X ~ Bin(n, p). Exact, stdlib only."""
    if k <= 0:
        return 1.0
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    return sum(math.comb(n, i) * (p ** i) * ((1.0 - p) ** (n - i))
               for i in range(k, n + 1))


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
        return {
            "statement": FROZEN_THRESHOLDS["type_i_criterion"],
            "detail": ("frozen in planned_design.thresholds (audit a-004 "
                       "finding 1): only an UPPER confidence bound at or "
                       "below alpha supports an at-or-below-alpha type-I "
                       "claim. Under the canonical sharp null with seeded "
                       "per-unit decoding the three conditions' schedules "
                       "are identical by the null itself (verified "
                       "unit-by-unit pre-analysis), so the structural "
                       "rejection rate is zero and the bound holds "
                       "mechanically."),
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
    if charged == "exchangeable_context":
        return {
            "statement": ("RELABELED context, never sharp-null type-I (audit "
                          "a-004 finding 0): A/B/C drawn iid from one "
                          "distribution — the PAIR distribution is "
                          "exchangeable, so the paired permutation test "
                          "still rejects near or below alpha for this "
                          "broader family, but every generated pack "
                          "VIOLATES the canonical sharp null (verified "
                          "discordant pre-analysis), so these rates are "
                          "robustness context for distribution-level "
                          "nullness, not sharp-null false-positive rates."),
            "pass": True}
    if charged == "sharp_violation_detection":
        return {
            "statement": ("reported for what it is: the sharp null is "
                          "genuinely FALSE for every unit while the marginal "
                          "null is true; a rejection is the correct sharp "
                          "unit-level conclusion and the report's claim "
                          "ceiling (null_form: sharp) matches it. Not "
                          "charged against type-I."),
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


def run_arm(name: str, arm: dict, workers: int) -> dict:
    specs = [(arm["kind"], arm.get("per"), arm["axes"], arm["seed"] + i,
              f"{name}[trial {i}]")
             for i in range(arm["trials"])]
    if workers > 1:
        with multiprocessing.Pool(workers) as pool:
            verdicts = pool.map(run_trial, specs)
    else:
        verdicts = [run_trial(s) for s in specs]
    tally: dict = {}
    for v in verdicts:
        tally[v] = tally.get(v, 0) + 1
    positives = tally.get("order_effect_observed", 0)
    n = arm["trials"]
    lo, hi = clopper_pearson(positives, n)
    out = {"kind": arm["kind"], "charged": arm["charged"], "trials": n,
           "seed": arm["seed"],
           "sharp_null_axes": dict(arm["axes"]),
           "tally": {k: tally[k] for k in sorted(tally)},
           "positive_rate": round(positives / n, 6),
           "positive_rate_ci95": [lo, hi]}
    if arm.get("effect") is not None:
        out["effect_tv"] = arm["effect"]
    if arm.get("per"):
        out["per_condition"] = {c: list(p)
                                for c, p in sorted(arm["per"].items())}
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
                   "(n = 48 units per condition, 10000-iteration paired "
                   "permutation null, sham axis sharply null)"),
        "grid": list(POWER_GRID),
        "power_target": POWER_TARGET,
        "power_curve": curve,
        "selected_effect": selected,
        "frozen_min_detectable_effect": MDE,
        "consistent": selected == MDE,
    }

    artifact = {
        "artifact": "m8-operating-characteristics",
        "order_report_version": ORDER_REPORT_VERSION,
        "metrics_version": METRICS_VERSION,
        "admissibility_version": DECISION_ADMISSIBILITY_VERSION,
        "generated_by": "scripts/m8_operating_characteristics.py",
        "trials_scale": args.trials_scale,
        # a-004 finding 0: the ONE canonical null, echoed verbatim
        "null_form": M8_NULL_FORM,
        "null_statement": CANONICAL_NULL_STATEMENT,
        "schedule_verification": (
            "every trial's generated potential-outcome schedule is verified "
            "unit-by-unit against its arm's declared null status BEFORE "
            "analysis: sharp-null axes must satisfy the canonical statement "
            "at every matched unit (A_i == B_i == C_i, exact, no "
            "condition-dependent noise); alternative axes must violate it. "
            "A completed arm is itself the proof — verification raises "
            "before any statistic otherwise."),
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
        "design": {
            "units_per_condition": UNITS_PER_CONDITION,
            "menu": list(MENU),
            "variants": [list(v) for v in VARIANTS],
            "sampler_seeds": list(SAMPLER_SEEDS),
        },
        "ci_method": {
            "interval": "exact two-sided Clopper-Pearson at 95%",
            "outer_trials_per_charged_arm": CHARGED_TRIALS,
            "math": ("at T=400 and p-hat=alpha=0.05 the CP interval is "
                     "~[0.031, 0.076] (half-width ~0.023 < alpha), so "
                     "2*alpha=0.10 is resolvable: if the true rate were 0.10, "
                     "P[95% lower bound <= alpha] = P[Bin(400,0.10) <= 29] "
                     "~= 0.03. For power, at T=400 and p-hat=0.85 the CP "
                     "lower bound is ~0.812, so the frozen target 0.8 is "
                     "resolvable against true power ~0.85 or better."),
        },
        "arms": arms,
        "mde_selection": mde_selection,
        "runtime": {"seconds": runtime, "workers": args.workers,
                    "python": sys.version.split()[0]},
        "all_criteria_pass": (
            all(a["criterion"]["pass"] for a in arms.values())
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
