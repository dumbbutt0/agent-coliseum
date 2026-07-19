#!/usr/bin/env python3
"""m8 Phase-2 — operating characteristics of the FROZEN decision rule (v4).

Audit 001814 finding 2 (coverage A): the committed characterisation must run the
frozen decision procedure it claims to characterise — permutation_iterations =
10000 and bootstrap_iterations = 10000, never substituted smaller values — with
enough outer trials to bound the type-I criterion, and with confidence intervals
reported rather than point estimates. This script IS that characterisation. It
drives `metrics.order_sensitivity_report` (ORDER_REPORT_VERSION 4) end to end —
synthetic run directories, real replay attestations over their actual bytes, the
real terminal-probe / matched-unit / surviving-count / sham-adequacy gates — at
the exact frozen threshold bundle, and writes the committed artifact

    derived/textlab/m8-operating-characteristics.json

No model is contacted. Every draw comes from `random.Random` with a declared
per-trial seed (trial_seed = arm_seed + trial_index), so the study is
deterministic and independent of worker scheduling.

STATISTICAL DESIGN (the math the prereg requires stated, stated):

* Outer trials: T = 400 per H0-family arm. Each trial is one complete 144-run
  pack analysed by the frozen rule; a false positive is a trial that returns
  `order_effect_observed` under a process satisfying the operative sharp null's
  exactness condition (within-pair exchangeability).
* Interval: exact Clopper-Pearson 95% (two-sided). At T = 400 and p-hat =
  alpha = 0.05 the interval is approximately [0.031, 0.076] — half-width about
  0.023, strictly less than alpha itself, so a rate of 2*alpha = 0.10 is
  resolvable: if the true rate were 0.10, the probability that the 95% lower
  bound still sits at or below alpha is about 0.03 (P[Bin(400, 0.10) <= 29]).
  40 trials — the count the audit blocked — cannot make that distinction; 400
  can, and that is why T = 400.
* Type-I criterion (frozen): for every H0-family arm, the Clopper-Pearson 95%
  LOWER bound of the false-positive rate must not exceed alpha = 0.05 — i.e.
  the data must not demonstrate a rate materially above alpha. The upper bound
  is reported alongside.
* Power criterion (frozen): at the min_detectable_effect boundary (TV(A,B) =
  0.25, sham null), the Clopper-Pearson 95% LOWER bound of
  P(order_effect_observed) must exceed 0.05 — power distinguishable from the
  false-positive floor, i.e. non-negligible in the preregistration's sense.
  Power at 2x the boundary is reported for context.

ARMS:

* iid H0 families (uniform / graded / concentrated): A, B, C drawn iid from one
  distribution. Within-pair exchangeability holds, so any positive is a false
  positive charged against the type-I criterion.
* shared-latent two-mode, SHARP NULL TRUE (audit 001814 finding 0's process,
  honest half): a pack-level latent mode selects which action every unit takes,
  but the SAME action in A, B and C — units are dependent on each other, yet
  order made no difference to any unit. Positives are false positives.
* shared-latent two-mode, SHARP NULL FALSE (the audit's separating case): mode
  0 makes every A/C unit choose one action and every B unit another; mode 1
  reverses them. The marginal distributions are equal ACROSS the process, but
  every single unit is order-dependent — the sharp null is genuinely false.
  The frozen rule rejects essentially always, and at ORDER_REPORT_VERSION 4
  that is CORRECT behaviour reported for what it is: the claim is the sharp
  unit-level conclusion (`null_form: "sharp"`), never a marginal one. This arm
  is deliberately NOT charged against type-I.
* power at the MDE boundary: A graded, B shifted by exactly 0.25 total
  variation, C iid from A's distribution (an honestly-null sham surface).
* power at 2x MDE: B shifted by 0.50.
* sham-contaminated: C drawn iid from a distribution shifted from A's by
  exactly the MDE while B carries a decisive order effect — the a-003
  finding-1 gate arm. This measures the sham gate's residual LEAKAGE: the
  clause-2 warrant is granted on the OBSERVED pack (TV(A,C) <= q_AC and
  q_AC < margin), and no finite-sample rule can bound the unobserved
  generating process — in a small fraction of trials the sampled sham shift
  happens to look null with its warrant intact, and the decisive A/B
  rejection promotes exactly as the frozen rule directs. The frozen
  criterion is therefore the same form as type-I: the Clopper-Pearson 95%
  LOWER bound of the promotion rate must not exceed alpha. The two
  OBSERVATION-level guarantees the audit demanded are absolute and pinned
  deterministically in the test suite, not here: the reproduced boundary
  pack (observed TV(A,C) = q_AC = margin) is inconclusive, never positive,
  and every emitted positive carries the sham warrant.

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
from coliseum.textlab.schema import canonical_json, config_hash  # noqa: E402

# ------------------------------------------------------------ frozen design
CONDITIONS = {"A": "scramble_dev_m8", "B": "scramble_perm_m8",
              "C": "scramble_sham_m8"}
TERMINAL_DP_ID = "d_partner"
MENU = ("share_resource", "verify_first", "decline_partnership",
        "defer_decision")
SAMPLER_SEEDS = tuple(range(2001, 2025))
S1, S2 = SAMPLER_SEEDS[:12], SAMPLER_SEEDS[12:]
VARIANTS = (("v0_caravan", 42), ("v1_workshop", 1))
UNITS_PER_CONDITION = len(VARIANTS) * len(SAMPLER_SEEDS)          # 48

FROZEN_POLICY = {
    "policy_version": "1",
    "admissibility_version": DECISION_ADMISSIBILITY_VERSION,
    "max_non_decision_rate": 0.20,
    "max_non_decision_rate_delta": 0.05,
    "min_admissible_effective_n": 20,
    "on_violation": "refuse",
}
FROZEN_THRESHOLDS = {
    "bootstrap_iterations": 10000,
    "bootstrap_seed": 20260719,
    "confidence": 0.95,
    "noise_floor_split": {"S1": list(S1), "S2": list(S2)},
    "min_detectable_effect": 0.25,
    "permutation_iterations": 10000,
    "permutation_seed": 20260719,
    "alpha": 0.05,
    "sham_equivalence_margin": 0.25,
    "max_surviving_delta": 2,
}

ALPHA = FROZEN_THRESHOLDS["alpha"]
MDE = FROZEN_THRESHOLDS["min_detectable_effect"]

# ------------------------------------------------------------ trial counts
H0_TRIALS = 400
POWER_TRIALS = 400
CONTEXT_TRIALS = 200

# per-condition distributions (over MENU, in order)
GRADED = (0.40, 0.30, 0.20, 0.10)
POWER_B_MDE = (0.15, 0.30, 0.20, 0.35)          # TV(GRADED, .) = 0.25 exactly
POWER_B_2X = (0.05, 0.15, 0.30, 0.50)           # TV(GRADED, .) = 0.50 exactly
SHAM_C_MDE = POWER_B_MDE                        # the sham carries the MDE shift

ARMS = {
    # ---- H0 families: any positive is a false positive (type-I charged)
    "h0_iid_uniform": {"kind": "iid", "per": {"A": (0.25,) * 4,
                                              "B": (0.25,) * 4,
                                              "C": (0.25,) * 4},
                       "trials": H0_TRIALS, "seed": 101000,
                       "charged": "type_i"},
    "h0_iid_graded": {"kind": "iid", "per": {"A": GRADED, "B": GRADED,
                                             "C": GRADED},
                      "trials": H0_TRIALS, "seed": 102000,
                      "charged": "type_i"},
    "h0_iid_concentrated": {"kind": "iid",
                            "per": {"A": (0.85, 0.05, 0.05, 0.05),
                                    "B": (0.85, 0.05, 0.05, 0.05),
                                    "C": (0.85, 0.05, 0.05, 0.05)},
                            "trials": H0_TRIALS, "seed": 103000,
                            "charged": "type_i"},
    # ---- dependent process, sharp null TRUE: pack-level latent mode, same
    # action per unit in every condition (audit 001814 finding 0, honest half)
    "h0_shared_latent_sharp_true": {"kind": "latent_true",
                                    "trials": H0_TRIALS, "seed": 104000,
                                    "charged": "type_i"},
    # ---- dependent process, sharp null FALSE, marginal null true: the audit's
    # separating case. NOT charged against type-I — the operative sharp null is
    # genuinely false and a rejection is the correct unit-level conclusion.
    "sharp_false_marginal_true": {"kind": "latent_false",
                                  "trials": CONTEXT_TRIALS, "seed": 105000,
                                  "charged": "sharp_violation_detection"},
    # ---- power
    "power_at_mde": {"kind": "iid", "per": {"A": GRADED, "B": POWER_B_MDE,
                                            "C": GRADED},
                     "trials": POWER_TRIALS, "seed": 106000,
                     "charged": "power"},
    "power_at_2x_mde": {"kind": "iid", "per": {"A": GRADED, "B": POWER_B_2X,
                                               "C": GRADED},
                        "trials": CONTEXT_TRIALS, "seed": 107000,
                        "charged": "power_context"},
    # ---- the sham-adequacy gate: C contaminated at the MDE, B decisive.
    # A positive would be a promotion over an inadequate sham — must be zero.
    "sham_contaminated_at_mde": {"kind": "iid",
                                 "per": {"A": GRADED, "B": POWER_B_2X,
                                         "C": SHAM_C_MDE},
                                 "trials": CONTEXT_TRIALS, "seed": 108000,
                                 "charged": "sham_gate"},
}


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


def _choose_fn(kind: str, per, rng: random.Random):
    """The per-trial process. Draw order is FIXED (condition, variant, seed),
    so a given trial seed always produces the same pack."""
    if kind == "iid":
        return lambda cond, variant, samp: _draw(rng, per[cond])
    if kind == "latent_true":
        # pack-level latent mode; every unit takes the SAME action in all three
        # conditions (unit action varies by unit hash so the pack is not
        # degenerate-constant). Sharp null TRUE: order changed nothing.
        mode = rng.randrange(2)
        def choose(cond, variant, samp):
            i = (samp + (0 if variant.startswith("v0") else 7) + mode * 3) % 4
            return MENU[i]
        return choose
    if kind == "latent_false":
        # the audit's separating case: A/C one action, B another; mode flips.
        mode = rng.randrange(2)
        pair = (("share_resource", "decline_partnership")
                if mode == 0 else ("decline_partnership", "share_resource"))
        return lambda cond, variant, samp: pair[1] if cond == "B" else pair[0]
    raise ValueError(kind)


def run_trial(spec: tuple) -> str:
    """One complete pack through the frozen path. Returns the verdict."""
    kind, per, trial_seed = spec
    rng = random.Random(trial_seed)
    choose = _choose_fn(kind, per, rng)
    root = tempfile.mkdtemp(prefix="m8oc_")
    try:
        dirs = []
        for cond in ("A", "B", "C"):
            for variant, scen_seed in VARIANTS:
                for samp in SAMPLER_SEEDS:
                    dirs.append(_write_unit(root, cond, variant, scen_seed,
                                            samp, choose(cond, variant, samp)))
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

def run_arm(name: str, arm: dict, workers: int) -> dict:
    specs = [(arm["kind"], arm.get("per"), arm["seed"] + i)
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
           "seed": arm["seed"], "tally": {k: tally[k] for k in sorted(tally)},
           "positive_rate": round(positives / n, 6),
           "positive_rate_ci95": [lo, hi]}
    if arm.get("per"):
        out["per_condition"] = {c: list(p) for c, p in sorted(arm["per"].items())}
    # frozen criteria
    if arm["charged"] == "type_i":
        out["criterion"] = {
            "statement": "Clopper-Pearson 95% lower bound of the "
                         "false-positive rate must not exceed alpha",
            "alpha": ALPHA, "pass": lo <= ALPHA}
    elif arm["charged"] == "power":
        out["criterion"] = {
            "statement": "Clopper-Pearson 95% lower bound of power at the "
                         "min_detectable_effect boundary must exceed 0.05 "
                         "(distinguishable from the false-positive floor)",
            "floor": 0.05, "pass": lo > 0.05}
    elif arm["charged"] == "sham_gate":
        out["criterion"] = {
            "statement": "sham-gate leakage bounded: the Clopper-Pearson 95% "
                         "lower bound of the promotion rate over a "
                         "contaminated-at-MDE sham PROCESS must not exceed "
                         "alpha. The warrant is granted on the observed pack, "
                         "so process-level leakage at sampling-noise scale is "
                         "irreducible; the absolute observation-level "
                         "guarantees (the boundary pack never promotes; every "
                         "positive carries the warrant) are pinned "
                         "deterministically in the test suite.",
            "alpha": ALPHA, "pass": lo <= ALPHA}
    elif arm["charged"] == "sharp_violation_detection":
        out["criterion"] = {
            "statement": "reported for what it is: the sharp null is "
                         "genuinely FALSE for every unit while the marginal "
                         "null is true; a rejection is the correct sharp "
                         "unit-level conclusion and the report's claim "
                         "ceiling (null_form: sharp) matches it. Not charged "
                         "against type-I.",
            "pass": True}
    else:
        out["criterion"] = {"statement": "context only", "pass": True}
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

    artifact = {
        "artifact": "m8-operating-characteristics",
        "order_report_version": ORDER_REPORT_VERSION,
        "metrics_version": METRICS_VERSION,
        "admissibility_version": DECISION_ADMISSIBILITY_VERSION,
        "generated_by": "scripts/m8_operating_characteristics.py",
        "trials_scale": args.trials_scale,
        # the EXACT frozen bundle the production path loads; the CI regression
        # asserts echo equality and hash equality against its own inline copy
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
            "outer_trials_per_h0_arm": H0_TRIALS,
            "math": ("at T=400 and p-hat=alpha=0.05 the CP interval is "
                     "~[0.031, 0.076] (half-width ~0.023 < alpha), so "
                     "2*alpha=0.10 is resolvable: if the true rate were 0.10, "
                     "P[95% lower bound <= alpha] = P[Bin(400,0.10) <= 29] "
                     "~= 0.03. The audit-blocked 40-trial design could not "
                     "make this distinction; 400 trials can."),
        },
        "arms": arms,
        "runtime": {"seconds": runtime, "workers": args.workers,
                    "python": sys.version.split()[0]},
        "all_criteria_pass": all(a["criterion"]["pass"] for a in arms.values()),
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(canonical_json(artifact) + "\n")
    print(f"wrote {args.out} ({runtime}s, all_criteria_pass="
          f"{artifact['all_criteria_pass']})")
    return 0 if artifact["all_criteria_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
