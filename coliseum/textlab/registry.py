"""Experiment registry (First Gladiator M4) — binds every experiment's
design → regimes → approvals → artifacts → replay → reports → verdicts.

The registry is the citability gate: an experiment that is not registered
(or whose registry row disagrees with its evidence) cannot be cited. Two
validation tiers reflect historical reality honestly:

- ``full``   — the manifest passes ``sweep_models.manifest_load`` full-row
  validation against the run evidence (required for every citable entry);
- ``legacy`` — DEMOTED datasets (the pilot sweep and sweep-v2) whose
  manifests predate the current row schema and are preserved AS-IS; they
  parse and count but are never citable, and their status says so.

Post-freeze mutation refusal: every frozen entry carries an ``entry_hash``
(sha256 of the canonical entry minus the hash field). Lint recomputes it —
editing a frozen entry without re-hashing (i.e. without an audited,
deliberate change) fails loudly. Held-out declarations live here too: a
held-out scenario may never appear in ANY registered manifest before the
M14 evaluation (SPEC E6); the lint enforces it mechanically.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

import yaml

from .schema import SchemaError, canonical_json

EXPERIMENTS_REGISTRY_VERSION = "1"
EXPERIMENT_STATUSES = ("exploratory", "pilot-demoted", "legacy-demoted",
                       "pre-registered", "complete")
VALIDATION_TIERS = ("full", "legacy")
GENERALIZATION_LEVELS = ("L1", "L2", "L3", "L4")

# Research claim lifecycle (SPEC §5, owner-ratified SC-3): the ladder every
# empirical claim climbs. `demoted`/`refuted` are first-class (the sweep-v2
# and full-audit withdrawals are the precedent); `accepted` REQUIRES an
# independent finding audit; paper drafts may cite `accepted` only.
CLAIMS_REGISTRY_VERSION = "1"
CLAIM_STATES = ("speculation", "observation", "replicated", "generalized",
                "accepted", "refuted", "demoted")


def entry_hash(entry: dict) -> str:
    """sha256 over the canonical entry with entry_hash itself excluded."""
    body = {k: v for k, v in entry.items() if k != "entry_hash"}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def design_hash(planned_design: dict) -> str:
    """sha256 over a pre-registered experiment's planned_design — the frozen
    hypothesis. The eventual runs' autonomy-block experiment_config_hash must
    match this, binding evidence to the pre-registration."""
    return hashlib.sha256(
        canonical_json(planned_design).encode("utf-8")).hexdigest()


# --------------------------------------------------- frozen-policy accessors
#
# Admissibility bounds and analysis thresholds live INSIDE planned_design, so
# they are covered by design_hash and cannot be moved after outcomes are seen
# without breaking the pre-registration lint. These loaders are the ONLY
# supported read path; nothing may re-derive a bound from run evidence.

ADMISSIBILITY_POLICY_KEYS = (
    "policy_version", "admissibility_version", "max_non_decision_rate",
    "max_non_decision_rate_delta", "min_admissible_effective_n",
    "on_violation")
THRESHOLD_KEYS = ("bootstrap_iterations", "bootstrap_seed", "confidence",
                  "min_detectable_effect", "sham_equivalence_margin")
# M8 audit repair R4: the null model is a PAIRED PERMUTATION null, so its
# parameters must be frozen inside planned_design exactly like the bootstrap
# parameters were. A design that omits them cannot state a decision quantile at
# all, so absence is a lint failure rather than a runtime default.
PERMUTATION_THRESHOLD_KEYS = ("permutation_iterations", "permutation_seed",
                              "alpha")
_RATE_KEYS = ("max_non_decision_rate", "max_non_decision_rate_delta")

# experiments whose frozen design MUST carry a policy + thresholds + a
# noise-floor split (a stochastic live design cannot be analysed without them)
POLICY_REQUIRED_EXPERIMENTS = ("m8-phase2-live-order-sensitivity",)

# --------------------------------------------------- frozen ANALYSIS IDENTITY
#
# A design_hash that does not cover *which analysis runs* freezes nothing that
# matters: the same run set yields different verdicts under different callables.
# The Phase-2 successor is `metrics.order_sensitivity_report`; the Phase-1
# comparator `metrics.scramble_terminal_distribution` admits parse fallbacks as
# decisions and can return a clean null from wholly unparseable output, so a
# design naming it must FAIL rather than load quietly.
#
# The ban is a literal symbol ban on primary_event, not an attempt to read an
# English negation ("computed by X" vs "X is not the path" are the same
# substring). The prose exclusion therefore lives in planned_design.notes —
# equally covered by design_hash — and primary_event names only the successor.
#
# Why amending a frozen-looking design is legitimate here: at the time of this
# repair no outcome exists, no live run has occurred and no model has been
# contacted. The anti-rigging prohibition is on moving thresholds AFTER seeing
# outcomes; this is the audit repair loop operating on an unfrozen candidate.
# Nothing is weakened — two bounds are ADDED and the analysis path is narrowed
# to the safer one.
#
# SECOND repair (R4), also pre-execution: the split-half noise floor that the
# original decision rule compared against was found INERT by the design's own
# required characterisation — TV_null between two 24-unit halves carries about
# twice the small-sample inflation of TV(A,B) on 48-vs-48, putting the floor
# near 0.49 against a 0.25 ceiling, so the simulated false-positive rate AND the
# power were both 0.000. The null is now a PAIRED PERMUTATION null and the
# decision rule compares observed distances against its 1-alpha quantile. Since
# a superseded rule left in place would still hash and still load, the lint bans
# the old bootstrap-bound-comparison phrasing outright.
ANALYSIS_CALLABLE_REQUIRED = "order_sensitivity_report"
ANALYSIS_CALLABLE_FORBIDDEN = "scramble_terminal_distribution"

# literal markers of the SUPERSEDED bootstrap-bound-comparison rule (matched
# case-insensitively against primary_event). Prose, like the symbol ban above,
# rather than an attempt to parse an English negation.
SUPERSEDED_RULE_MARKERS = ("lower bound of tv(a,b)", "upper bound of tv_null")
# literal markers the PERMUTATION rule must carry
PERMUTATION_RULE_MARKERS = ("permutation", "q_AB")

# THIRD repair (R6), also pre-execution: the sensitivity requirement
# `q_AB <= min_detectable_effect` was specified as a precondition gating BOTH
# branches of the decision rule — carried over from the superseded split-half
# null without re-derivation. Under a paired permutation null that is wrong:
# `q_AB` IS the rejection threshold, so an observed distance exceeding it has
# rejected H0 at `alpha`, and that is a valid positive whether or not a smaller
# effect would also have been resolvable. Sensitivity constrains only what may
# be concluded from a NON-rejection. Implemented symmetrically the rule was
# perverse — total separation at TV(A,B)=1.0 against q_AB=0.2917 reported
# `inconclusive` solely because 0.2917 > 0.25, discarding a decisive rejection.
#
# The analysis callable version is pinned literally in primary_event so a
# report emitted by an older callable cannot be passed off as conforming to
# this design. FOURTH repair (audit 001834 / 001832, still pre-execution):
# ORDER_REPORT_VERSION bumps 3 -> 4 — the rule gains a mandatory clause-0
# evidence-admission block (provider-free replay attestation, frozen terminal
# probe identity d_partner, the full 48-unit matched grid, and a REQUIRED
# registry-loaded max_surviving_delta enforced before any statistic) and the
# clause-2 sham-adequacy warrant (q_AC < sham_equivalence_margin, strict): a
# sham NON-rejection needs a warrant exactly as a null claim does.
ANALYSIS_CALLABLE_VERSION_MARKER = "ORDER_REPORT_VERSION 4"

# literal markers the clause-0 EVIDENCE-ADMISSION block must carry (matched
# case-sensitively, like the callable name). A primary_event that drops any of
# them can be read as permitting the exact escapes audits 001832/001834 pinned:
# attestation-free runs, a positionally-inferred terminal, an unmatched grid,
# or an optional dropout bound.
ADMISSION_RULE_MARKERS = (
    "provider-free replay", "d_partner", "missing_terminal_probe",
    "matched_units == 48", "before any statistic")
# literal markers the clause-2 SHAM-ADEQUACY warrant must carry: the strict
# margin comparison is the warrant itself.
SHAM_ADEQUACY_MARKERS = ("q_AC < sham_equivalence_margin",)

# literal markers of the SUPERSEDED SYMMETRIC sensitivity precondition (matched
# case-insensitively against primary_event). Each phrase asserts the requirement
# gates the whole rule or the POSITIVE branch, which is exactly the defect.
SYMMETRIC_SENSITIVITY_MARKERS = (
    "sensitivity precondition (evaluated first)",
    "inconclusive whatever else holds",
    "order effect observed iff the sensitivity precondition holds",
    "the sensitivity precondition holds and",
)
# literal markers the CORRECTED asymmetric rule must carry: the requirement must
# be stated as attaching to the null branch alone and as never overturning a
# rejection. Matched case-sensitively, like the callable name.
ASYMMETRIC_SENSITIVITY_MARKERS = (
    "attaches ONLY to the null branch",
    "never invalidates a rejection",
)

# ------------------------------------------- frozen NUMERIC PROFILE authority
#
# Audit b-001 finding 3 (the rehash attack): design_hash is SELF-derived from
# planned_design, so an attacker who weakens a numeric bound, recomputes
# design_hash and mirrors the config defeats hash reconstruction entirely —
# and the semantic lint above only checks broad domains (rate in [0,1],
# positive int), so a weaker-but-type-valid bound loaded cleanly. The frozen
# numeric profile below is the INDEPENDENT authority: it lives in audited
# code, not in the artifact being checked, so a mutate+rehash+mirror attack
# now fails against constants no registry or config edit can move. Both lints
# (registry AND config) compare against it, so neither artifact can be
# weakened alone or in concert.
#
# Changing a value here is a deliberate, audited code change — exactly the
# property the design_hash alone could not provide.
M8_FROZEN_PROFILE = {
    "admissibility_policy": {
        "max_non_decision_rate": 0.20,
        "max_non_decision_rate_delta": 0.05,
        "min_admissible_effective_n": 20,
        "on_violation": "refuse",
    },
    "thresholds": {
        "bootstrap_iterations": 10000,
        "bootstrap_seed": 20260719,
        "confidence": 0.95,
        "min_detectable_effect": 0.25,
        "sham_equivalence_margin": 0.25,
        "permutation_iterations": 10000,
        "permutation_seed": 20260719,
        "alpha": 0.05,
    },
    "max_surviving_delta": 2,
    "sampler_seeds": list(range(2001, 2025)),
    "noise_floor_split": {"S1": list(range(2001, 2013)),
                          "S2": list(range(2013, 2025))},
    "scenario_seeds": [42, 1],
    "temperature": 0.7,
    "arbitration": "planner_priority",
    "model_digests": {
        "huihui_ai/qwen2.5-abliterate:7b-instruct":
            "103482475c9b4d4032999dd5d7383478cad8b966ae6ae984d525"
            "daf7352c2219",
    },
}

# experiment id -> audited frozen numeric profile
FROZEN_NUMERIC_PROFILES = {
    "m8-phase2-live-order-sensitivity": M8_FROZEN_PROFILE,
}

_FULL_DIGEST_RE = re.compile(r"[0-9a-f]{64}")


def _is_full_digest(value) -> bool:
    """A full immutable 64-hex model digest (an optional sha256: prefix is
    tolerated and stripped, matching sweep.norm_digest)."""
    return isinstance(value, str) and bool(
        _FULL_DIGEST_RE.fullmatch(value.replace("sha256:", "")))


def _profile_issues(eid: str, where: str, view: dict) -> list:
    """Compare a planned_design (or a config projected into planned_design
    shape) against the audited frozen numeric profile. Returns issue strings.

    The comparison is EXACT: every profile value must be present and equal
    (bools never impersonate ints), and the model_digests mapping must match
    key-for-key and digest-for-digest — no missing, extra, or substituted
    entries. Deviations are refused INDEPENDENTLY of design_hash, so they are
    caught even after a rehash."""
    prof = FROZEN_NUMERIC_PROFILES.get(eid)
    if prof is None:
        return []

    def _mismatch(got, want):
        return got != want or (isinstance(got, bool) is not
                               isinstance(want, bool))

    issues = []
    for key, want in prof.items():
        if key in ("admissibility_policy", "thresholds"):
            block = view.get(key)
            if not isinstance(block, dict):
                issues.append(
                    f"{where}: {key} is missing — the audited frozen profile "
                    f"for {eid} requires it (profile authority is code, not "
                    "the self-derived hash)")
                continue
            for k, w in want.items():
                if k not in block:
                    issues.append(
                        f"{where}: {key}.{k} is missing — the audited frozen "
                        f"profile pins it at {w!r}")
                elif _mismatch(block[k], w):
                    issues.append(
                        f"{where}: {key}.{k} {block[k]!r} != audited frozen "
                        f"profile value {w!r} — the M8 numeric profile is "
                        "anchored in audited code, independent of the "
                        "self-derived hash")
            continue
        if key == "model_digests":
            got = view.get(key)
            if got != want:
                issues.append(
                    f"{where}: model_digests {got!r} != audited frozen "
                    f"profile digests {want!r} — a substituted, missing, or "
                    "extra digest is a NEW regime and is refused "
                    "independently of the self-derived hash")
            continue
        if key not in view:
            issues.append(f"{where}: {key} is missing — the audited frozen "
                          f"profile pins it at {want!r}")
        elif _mismatch(view[key], want):
            issues.append(
                f"{where}: {key} {view[key]!r} != audited frozen profile "
                f"value {want!r} — anchored in audited code, independent of "
                "the self-derived hash")
    return issues


def _config_profile_view(cfg: dict) -> dict:
    """Project a run config into planned_design shape so the SAME profile
    comparison applies to both artifacts (config 'seeds' realizes the design's
    'scenario_seeds')."""
    view = {k: cfg[k] for k in (
        "admissibility_policy", "thresholds", "max_surviving_delta",
        "sampler_seeds", "noise_floor_split", "temperature", "arbitration",
        "model_digests") if k in cfg}
    if "seeds" in cfg:
        view["scenario_seeds"] = cfg["seeds"]
    return view


def _find_entry(registry_path: str, experiment_id: str) -> dict:
    raw = load_experiments_registry(registry_path)
    entry = next((e for e in raw["experiments"]
                  if e.get("experiment_id") == experiment_id), None)
    if entry is None:
        raise SchemaError(f"experiment {experiment_id!r} is not registered")
    return entry


def _frozen_design(registry_path: str, experiment_id: str) -> dict:
    """planned_design, refusing to serve it if the entry's design_hash does
    not reconstruct — a tampered pre-registration must not load quietly."""
    entry = _find_entry(registry_path, experiment_id)
    pd = entry.get("planned_design")
    if not isinstance(pd, dict):
        raise SchemaError(f"{experiment_id}: no planned_design mapping")
    want = design_hash(pd)
    if entry.get("design_hash") != want:
        raise SchemaError(
            f"{experiment_id}: design_hash {str(entry.get('design_hash'))[:16]}"
            f"… != recomputed {want[:16]}… — the frozen design was mutated")
    return pd


def load_admissibility_policy(registry_path: str, experiment_id: str) -> dict:
    """The frozen admissibility bounds from planned_design.admissibility_policy."""
    pd = _frozen_design(registry_path, experiment_id)
    pol = pd.get("admissibility_policy")
    if not isinstance(pol, dict):
        raise SchemaError(f"{experiment_id}: planned_design has no "
                          "admissibility_policy mapping")
    return dict(pol)


def load_thresholds(registry_path: str, experiment_id: str) -> dict:
    """The frozen analysis thresholds, as ONE bundle the analysis can consume.

    Composition note (Director assembly, M8): the bundle is assembled from two
    places in planned_design, deliberately. `thresholds` holds the inferential
    parameters — the paired-permutation null that DECIDES
    (`permutation_iterations`, `permutation_seed`, `alpha`), the bootstrap that
    only REPORTS intervals (`bootstrap_iterations`, `bootstrap_seed`,
    `confidence`), and the resolving power `min_detectable_effect`;
    `noise_floor_split` sits at planned_design top
    level because it is a property of the SAMPLING design — it partitions the
    declared sampler_seeds — and belongs beside them rather than inside a block
    about bootstrapping. It is RETAINED and still frozen after the R4 repair,
    but purely as a reported DIAGNOSTIC of within-condition stability: it gates
    no verdict. `max_surviving_delta` likewise sits at top level: it
    bounds differential provider DROPOUT across conditions, which is a property
    of execution, not of the bootstrap. The analysis needs all of them to
    evaluate the decision rule, so the loader returns them joined. All live
    under planned_design and are therefore equally covered by design_hash, so
    none can be moved after seeing outcomes; the split across sections is a
    presentation choice, never a difference in what is frozen.

    Every bound the execution and report path needs comes out of THIS one call
    (M8 audit repair R1c). `sweep.run_sweep` defaults `max_surviving_delta` to
    None and SKIPS the balance gate when it is None, so a bound that is merely
    documented is a guard nobody is obliged to call; carrying it in the same
    bundle removes the caller's opportunity to omit it.
    """
    pd = _frozen_design(registry_path, experiment_id)
    th = pd.get("thresholds")
    if not isinstance(th, dict):
        raise SchemaError(f"{experiment_id}: planned_design has no "
                          "thresholds mapping")
    bundle = dict(th)
    split = pd.get("noise_floor_split")
    if split is not None:
        bundle["noise_floor_split"] = split
    delta = pd.get("max_surviving_delta")
    if delta is not None:
        bundle["max_surviving_delta"] = delta
    return bundle


def _lint_frozen_policy(eid: str, pd: dict) -> list:
    """Policy/threshold/noise-floor checks for a stochastic pre-registration.
    Returns issue strings. Self-contradiction must fail, not load quietly."""
    issues = []

    pol = pd.get("admissibility_policy")
    if not isinstance(pol, dict):
        issues.append(f"{eid}: planned_design missing 'admissibility_policy' "
                      "(a stochastic live design must freeze its bounds)")
    else:
        for k in ADMISSIBILITY_POLICY_KEYS:
            if k not in pol:
                issues.append(f"{eid}: admissibility_policy missing {k!r}")
        if "on_violation" in pol and pol["on_violation"] != "refuse":
            issues.append(f"{eid}: admissibility_policy on_violation "
                          f"{pol['on_violation']!r} != 'refuse' — a violated "
                          "bound refuses, it never degrades to a number")
        for k in _RATE_KEYS:
            if k in pol:
                v = pol[k]
                if isinstance(v, bool) or not isinstance(v, (int, float)) \
                        or not (0 <= v <= 1):
                    issues.append(f"{eid}: admissibility_policy {k} {v!r} is "
                                  "not a rate in [0, 1]")
        n = pol.get("min_admissible_effective_n")
        if "min_admissible_effective_n" in pol and (
                isinstance(n, bool) or not isinstance(n, int) or n <= 0):
            issues.append(f"{eid}: admissibility_policy "
                          f"min_admissible_effective_n {n!r} must be a "
                          "positive int")

    th = pd.get("thresholds")
    if not isinstance(th, dict):
        issues.append(f"{eid}: planned_design missing 'thresholds' (bootstrap "
                      "parameters must be frozen before any outcome is seen)")
    else:
        for k in THRESHOLD_KEYS:
            if k not in th:
                issues.append(f"{eid}: thresholds missing {k!r}")
        it = th.get("bootstrap_iterations")
        if "bootstrap_iterations" in th and (
                isinstance(it, bool) or not isinstance(it, int) or it <= 0):
            issues.append(f"{eid}: thresholds bootstrap_iterations {it!r} "
                          "must be a positive int")
        bs = th.get("bootstrap_seed")
        if "bootstrap_seed" in th and (
                isinstance(bs, bool) or not isinstance(bs, int)):
            issues.append(f"{eid}: thresholds bootstrap_seed {bs!r} must be "
                          "an int")
        cf = th.get("confidence")
        if "confidence" in th and (
                isinstance(cf, bool) or not isinstance(cf, (int, float))
                or not (0 < cf < 1)):
            issues.append(f"{eid}: thresholds confidence {cf!r} must be in "
                          "(0, 1)")
        # resolving power: the smallest effect the design claims to detect, and
        # equally the tightest null it is entitled to assert. It gates BOTH
        # branches of the decision rule (a noise floor at or above it makes the
        # pack inconclusive), so a design without it has no sensitivity gate.
        mde = th.get("min_detectable_effect")
        if "min_detectable_effect" in th and (
                isinstance(mde, bool) or not isinstance(mde, (int, float))
                or not (0 < mde <= 1)):
            issues.append(f"{eid}: thresholds min_detectable_effect {mde!r} "
                          "must be a float in (0, 1] — a total-variation "
                          "distance is bounded by 1 and a zero floor claims "
                          "infinite resolving power")
        # R7: the sham-adequacy warrant's margin. A sham non-rejection needs a
        # warrant exactly as a null claim does: q_AC must be STRICTLY below
        # this margin or a positive verdict is unreachable. Same domain as
        # min_detectable_effect (a TV distance bound).
        sem = th.get("sham_equivalence_margin")
        if "sham_equivalence_margin" in th and (
                isinstance(sem, bool) or not isinstance(sem, (int, float))
                or not (0 < sem <= 1)):
            issues.append(f"{eid}: thresholds sham_equivalence_margin {sem!r} "
                          "must be a float in (0, 1] — it bounds a "
                          "total-variation quantile and a zero margin makes "
                          "the sham warrant unsatisfiable")

        # R4: paired-permutation null parameters. The decision quantile is the
        # 1-alpha percentile of a permutation null drawn under a declared seed
        # for a declared number of iterations; a design missing any of the three
        # cannot state its own rejection threshold and must not load quietly.
        for k in PERMUTATION_THRESHOLD_KEYS:
            if k not in th:
                issues.append(f"{eid}: thresholds missing {k!r} (the paired "
                              "permutation null replaced the split-half noise "
                              "floor; its parameters must be frozen before any "
                              "outcome is seen)")
        pit = th.get("permutation_iterations")
        if "permutation_iterations" in th and (
                isinstance(pit, bool) or not isinstance(pit, int) or pit <= 0):
            issues.append(f"{eid}: thresholds permutation_iterations {pit!r} "
                          "must be a positive int")
        ps = th.get("permutation_seed")
        if "permutation_seed" in th and (
                isinstance(ps, bool) or not isinstance(ps, int)):
            issues.append(f"{eid}: thresholds permutation_seed {ps!r} must be "
                          "an int")
        al = th.get("alpha")
        if "alpha" in th and (
                isinstance(al, bool) or not isinstance(al, (int, float))
                or not (0 < al < 0.5)):
            issues.append(f"{eid}: thresholds alpha {al!r} must be a float in "
                          "(0, 0.5) — a decision quantile at or above the "
                          "median is not a test")

    # differential provider dropout is observationally identical to an order
    # effect (the survivors in the affected condition are a biased subsample),
    # and sweep.run_sweep SKIPS the balance gate when this bound is absent. An
    # unbounded design could therefore complete a condition-imbalanced pack
    # without the guard ever running, so absence is a lint failure, not a
    # default.
    if "max_surviving_delta" not in pd:
        issues.append(f"{eid}: planned_design missing 'max_surviving_delta' "
                      "(differential dropout must be bounded before execution; "
                      "sweep.run_sweep skips the balance gate when the bound "
                      "is absent, so an unfrozen bound is no bound at all)")
    else:
        msd = pd["max_surviving_delta"]
        if isinstance(msd, bool) or not isinstance(msd, int) or msd < 0:
            issues.append(f"{eid}: max_surviving_delta {msd!r} must be a "
                          "non-negative int (an absolute spread between "
                          "per-condition surviving counts)")

    # b-001 finding 2: the frozen ARBITRATION regime must be declared in the
    # design so the config gate can bind to it — an undeclared arbitration is
    # an unpinned regime dimension the live driver would fill from a default.
    if not pd.get("arbitration"):
        issues.append(f"{eid}: planned_design missing 'arbitration' (the "
                      "arbitration rule is part of the frozen regime and the "
                      "config gate binds to it exactly)")

    # b-001 finding 1: the FULL immutable model digest must be frozen in the
    # design, per model, in full 64-hex shape — the config gate requires exact
    # equality against this mapping, so a partial or malformed pin here would
    # weaken the whole boundary.
    md = pd.get("model_digests")
    if not isinstance(md, dict) or not md:
        issues.append(f"{eid}: planned_design missing 'model_digests' (a live "
                      "design must freeze every model's FULL digest; a tag "
                      "alone pins nothing immutable)")
    else:
        for m in pd.get("models") or []:
            if m not in md:
                issues.append(f"{eid}: planned model {m!r} has no frozen "
                              "digest in planned_design.model_digests")
        for m, dg in md.items():
            if not _is_full_digest(dg):
                issues.append(f"{eid}: model_digests[{m!r}] {str(dg)[:20]!r} "
                              "is not a full immutable 64-hex digest")

    # frozen analysis identity: design_hash must cover WHICH analysis runs.
    pe = pd.get("primary_event")
    if not isinstance(pe, str) or not pe.strip():
        issues.append(f"{eid}: planned_design missing a 'primary_event' "
                      "string (the decision rule and the analysis identity)")
    else:
        if ANALYSIS_CALLABLE_REQUIRED not in pe:
            issues.append(
                f"{eid}: primary_event does not name the frozen analysis "
                f"callable {ANALYSIS_CALLABLE_REQUIRED!r} — a design_hash that "
                "does not cover which analysis runs freezes nothing that "
                "matters")
        if ANALYSIS_CALLABLE_FORBIDDEN in pe:
            issues.append(
                f"{eid}: primary_event names the Phase-1 comparator "
                f"{ANALYSIS_CALLABLE_FORBIDDEN!r} — that path admits parse "
                "fallbacks as decisions and can return a clean null from "
                "wholly unparseable output; it may not be the frozen Phase-2 "
                "analysis path (state the exclusion in notes instead)")
        # R4: the superseded bootstrap-bound-comparison rule must not survive.
        # It hashes and loads exactly as well as the correct one, so leaving it
        # in place would freeze an inert decision rule (measured false-positive
        # rate 0.000 and power 0.000) behind a valid design_hash.
        low = pe.lower()
        for marker in SUPERSEDED_RULE_MARKERS:
            if marker in low:
                issues.append(
                    f"{eid}: primary_event still expresses the SUPERSEDED "
                    f"bootstrap-bound-comparison rule ({marker!r}) — that rule "
                    "compared a 48-vs-48 distance against a split-half null "
                    "carrying about twice its small-sample inflation and was "
                    "measured inert; the frozen rule is the paired permutation "
                    "rule")
        for marker in PERMUTATION_RULE_MARKERS:
            if marker not in pe:
                issues.append(
                    f"{eid}: primary_event does not express the frozen paired "
                    f"permutation decision rule (missing {marker!r})")
        # R6: the analysis callable's version must be pinned, and pinned to the
        # CURRENT rule. A verdict emitted by an older callable implements a
        # different decision rule and must not be able to claim this design.
        if ANALYSIS_CALLABLE_VERSION_MARKER not in pe:
            issues.append(
                f"{eid}: primary_event does not pin the frozen analysis "
                f"callable version {ANALYSIS_CALLABLE_VERSION_MARKER!r} — the "
                "decision rule changed with the version, so a verdict must "
                "stay traceable to the rule that produced it")
        # R6: the SYMMETRIC sensitivity precondition must not survive. It gated
        # the POSITIVE branch on min_detectable_effect, which under a
        # permutation null discards decisive rejections (TV(A,B)=1.0 against
        # q_AB=0.2917 was reported inconclusive because 0.2917 > 0.25).
        for marker in SYMMETRIC_SENSITIVITY_MARKERS:
            if marker in low:
                issues.append(
                    f"{eid}: primary_event still expresses the SUPERSEDED "
                    f"SYMMETRIC sensitivity precondition ({marker!r}) — q_AB "
                    "IS the rejection threshold, so exceeding it rejects H0 at "
                    "alpha and the sensitivity requirement may gate ONLY the "
                    "null branch, never a rejection")
        for marker in ASYMMETRIC_SENSITIVITY_MARKERS:
            if marker not in pe:
                issues.append(
                    f"{eid}: primary_event does not state the CORRECTED "
                    "asymmetric sensitivity requirement (missing "
                    f"{marker!r}) — a design that leaves the requirement's "
                    "scope unstated can be read as gating both branches")
        # R7: the clause-0 evidence-admission block is mandatory. A rule that
        # drops any of its markers can be read as re-admitting the audited
        # escapes: attestation-free runs, a positionally-inferred terminal, an
        # unmatched grid, or an optional dropout bound.
        for marker in ADMISSION_RULE_MARKERS:
            if marker not in pe:
                issues.append(
                    f"{eid}: primary_event does not state the mandatory "
                    f"clause-0 evidence-admission requirement (missing "
                    f"{marker!r}) — every admission clause must refuse "
                    "before any distance, quantile, or verdict exists")
        # R7: the sham-adequacy warrant. A sham NON-rejection needs a warrant
        # exactly as a null claim does: q_AC strictly below the frozen margin.
        for marker in SHAM_ADEQUACY_MARKERS:
            if marker not in pe:
                issues.append(
                    f"{eid}: primary_event does not state the sham-adequacy "
                    f"warrant (missing {marker!r}) — without the strict "
                    "margin requirement a vacuous sham comparison could "
                    "warrant an order claim")

    # noise-floor split: TV_null = TV(A|S1, A|S2), so the split must partition
    # the DECLARED sampler seeds exactly — declared before execution and never
    # re-drawn after seeing outcomes.
    split = pd.get("noise_floor_split")
    if not isinstance(split, dict):
        issues.append(f"{eid}: planned_design missing 'noise_floor_split' "
                      "(the within-condition null must be frozen, not chosen "
                      "after the fact)")
    else:
        declared = pd.get("sampler_seeds") or []
        halves = {}
        for half in ("S1", "S2"):
            vals = split.get(half)
            if not isinstance(vals, list) or not vals:
                issues.append(f"{eid}: noise_floor_split {half} must be a "
                              "non-empty list of sampler seeds")
                halves[half] = None
                continue
            if len(vals) != len(set(vals)):
                issues.append(f"{eid}: noise_floor_split {half} contains "
                              "duplicate seeds")
            halves[half] = set(vals)
        if halves.get("S1") is not None and halves.get("S2") is not None:
            s1, s2 = halves["S1"], halves["S2"]
            overlap = sorted(s1 & s2)
            if overlap:
                issues.append(f"{eid}: noise_floor_split halves overlap on "
                              f"{overlap} — S1 and S2 must be disjoint")
            union, full = s1 | s2, set(declared)
            if union != full:
                missing = sorted(full - union)
                extra = sorted(union - full)
                issues.append(
                    f"{eid}: noise_floor_split does not partition the declared "
                    f"sampler_seeds (missing {missing}, unknown {extra})")
    return issues


def load_experiments_registry(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict) or "experiments" not in raw:
        raise SchemaError(f"{os.path.basename(path)}: registry must be a "
                          "mapping with an 'experiments' list")
    if raw.get("registry_version") != EXPERIMENTS_REGISTRY_VERSION:
        raise SchemaError(f"unsupported experiments registry_version "
                          f"{raw.get('registry_version')!r}")
    return raw


def _manifest_rows_raw(path: str) -> list:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def lint_experiments_registry(registry_path: str, repo_root: str) -> list:
    """Machine-check the experiment registry. Returns issue strings
    (empty = clean)."""
    issues = []
    try:
        raw = load_experiments_registry(registry_path)
    except (SchemaError, OSError, yaml.YAMLError) as exc:
        return [f"registry unreadable: {exc}"]

    held_out = raw.get("held_out", {}) or {}
    held_ids = set(held_out.get("scenarios") or [])
    held_hashes = set(held_out.get("scenario_hashes") or [])

    entries = raw["experiments"]
    ids = [e.get("experiment_id") for e in entries]
    for eid in {i for i in ids if ids.count(i) > 1}:
        issues.append(f"duplicate experiment entry {eid!r}")

    # a scenario registry (M3) is consulted so pre-registered designs can
    # only name real, non-held-out scenarios
    try:
        from .scenario import load_registry as _load_scen_registry
        scen_reg = _load_scen_registry(os.path.join(
            repo_root, "configs", "registry", "scenarios.yaml"))
        registered_scen = {s["scenario_id"] for s in scen_reg["scenarios"]}
    except Exception:
        registered_scen = None

    for e in entries:
        eid = e.get("experiment_id", "?")
        status = e.get("status")
        if e.get("generalization_level") not in GENERALIZATION_LEVELS:
            issues.append(f"{eid}: generalization_level "
                          f"{e.get('generalization_level')!r} not in "
                          f"{GENERALIZATION_LEVELS}")
        if status not in EXPERIMENT_STATUSES:
            issues.append(f"{eid}: status {status!r} not in "
                          f"{EXPERIMENT_STATUSES}")
            continue

        # --- pre-registered: DESIGN frozen, NOT yet run (M6). No manifest;
        # a design_hash pins the planned design so the eventual runs' autonomy
        # block must match it. Not citable evidence until it becomes complete.
        if status == "pre-registered":
            # LITERAL null only — an empty string or the string "null" is a
            # non-null manifest field and must not bypass the no-runs guard
            if "manifest" in e and e["manifest"] is not None:
                issues.append(f"{eid}: pre-registered entry must have "
                              "manifest: null (got "
                              f"{e['manifest']!r}); no runs yet")
            pd = e.get("planned_design")
            if not isinstance(pd, dict):
                issues.append(f"{eid}: pre-registered entry needs a "
                              "planned_design mapping")
                continue
            want = design_hash(pd)
            if e.get("design_hash") != want:
                issues.append(f"{eid}: design_hash "
                              f"{str(e.get('design_hash'))[:16]}… != "
                              f"recomputed {want[:16]}… (pre-registration "
                              "is frozen by its design_hash)")
            for req in ("hypothesis", "models", "interaction_mode",
                        "scenarios", "sampler_seeds", "primary_event",
                        "prereg_doc"):
                if not pd.get(req):
                    issues.append(f"{eid}: planned_design missing {req!r}")
            if eid in POLICY_REQUIRED_EXPERIMENTS:
                issues.extend(_lint_frozen_policy(eid, pd))
                # b-001 finding 3: the audited code-level profile is checked
                # INDEPENDENTLY of design_hash, so a mutate+rehash attack on
                # the load-bearing numeric bounds still refuses here.
                issues.extend(_profile_issues(eid, eid, pd))
            if pd.get("interaction_mode") and pd["interaction_mode"] not in \
                    ("independent_vignettes", "sequential_history"):
                issues.append(f"{eid}: planned interaction_mode "
                              f"{pd['interaction_mode']!r} invalid")
            for sid in pd.get("scenarios", []):
                if registered_scen is not None and sid not in registered_scen:
                    issues.append(f"{eid}: planned scenario {sid!r} is not "
                                  "in the scenario registry")
                if sid in held_ids:
                    issues.append(f"{eid}: planned scenario {sid!r} is "
                                  "HELD-OUT (SPEC E6)")
            doc = os.path.join(repo_root, pd.get("prereg_doc", ""))
            if pd.get("prereg_doc") and not os.path.exists(doc):
                issues.append(f"{eid}: prereg_doc {pd['prereg_doc']!r} "
                              "missing")
            continue

        # --- everything else is evidence-bearing: needs a validation tier
        if e.get("validation") not in VALIDATION_TIERS:
            issues.append(f"{eid}: validation {e.get('validation')!r} not in "
                          f"{VALIDATION_TIERS}")
            continue
        # only `complete` is citable, and it requires full validation
        if status == "complete" and e.get("validation") != "full":
            issues.append(f"{eid}: citable status 'complete' requires "
                          "validation: full")
        mpath = os.path.join(repo_root, e.get("manifest", ""))
        if not os.path.exists(mpath):
            issues.append(f"{eid}: manifest {e.get('manifest')!r} missing")
            continue
        # per-experiment evidence root: the ollama_local driver isolates each
        # run set under logs/runs/<experiment>/ (needed for a clean, per-
        # experiment evidence-manifest hash), so a complete entry declares
        # WHERE its run.json evidence lives. Legacy back-filled entries
        # (exp1/exp2) default to the shared logs/runs.
        entry_out_root = os.path.join(
            repo_root, e.get("evidence_root", os.path.join("logs", "runs")))
        try:
            if e["validation"] == "full":
                import sys
                scripts = os.path.join(repo_root, "scripts")
                if scripts not in sys.path:
                    sys.path.insert(0, scripts)
                from sweep_models import manifest_load
                rows = list(manifest_load(mpath, entry_out_root).values())
                declared = e.get("interaction_mode")
                modes = {r["interaction_mode"] for r in rows}
                if modes != {declared}:
                    issues.append(f"{eid}: manifest interaction modes "
                                  f"{sorted(modes)} != declared "
                                  f"{declared!r}")
                if held_ids or held_hashes:
                    for r in rows:
                        if r["scenario"] in held_ids or \
                                r["scenario_hash"] in held_hashes:
                            issues.append(
                                f"{eid}: HELD-OUT scenario "
                                f"{r['scenario']!r} appears in the manifest "
                                "— held-out content may never be used "
                                "before the M14 evaluation (SPEC E6)")
                            break
            else:
                rows = _manifest_rows_raw(mpath)
                for r in rows:
                    sid = r.get("scenario", "")
                    if sid in held_ids or r.get("scenario_hash", "") in \
                            held_hashes:
                        issues.append(f"{eid}: HELD-OUT scenario {sid!r} "
                                      "appears in the legacy manifest")
                        break
        except (SchemaError, json.JSONDecodeError, OSError) as exc:
            issues.append(f"{eid}: manifest validation failed: "
                          f"{str(exc)[:160]}")
            continue
        if e.get("rows") != len(rows):
            issues.append(f"{eid}: declared rows {e.get('rows')} != manifest "
                          f"rows {len(rows)}")
        if e.get("frozen"):
            want = entry_hash(e)
            if e.get("entry_hash") != want:
                issues.append(f"{eid}: FROZEN entry mutated — entry_hash "
                              f"{str(e.get('entry_hash'))[:16]}… != "
                              f"recomputed {want[:16]}… (a frozen entry "
                              "changes only via an audited re-hash)")
    return issues


# ---------------------------------------------- experiment run configs (M6)

EXPERIMENT_CONFIG_REQUIRED = (
    "experiment_id", "design_hash", "task_id", "driver", "models",
    "model_digests", "scenarios", "seeds", "sampler_seeds", "temperature",
    "arbitration", "interaction", "out_root", "manifest", "scenario_count",
    "retries_per_unit", "expected_run_count")


def lint_experiment_config(config_path: str, registry_path: str,
                           repo_root: str) -> list:
    """Bind a committed ollama_local run config to its FROZEN pre-registration
    (the provenance gate the result audit runs). Returns issue strings; empty
    means the config faithfully realizes exactly one pre-registered design and
    nothing about the frozen hypothesis was weakened. This is the check that a
    live run cannot execute a design the owner never froze."""
    issues = []
    try:
        with open(config_path, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"config unreadable: {exc}"]
    where = os.path.basename(config_path)
    missing = [f for f in EXPERIMENT_CONFIG_REQUIRED if f not in cfg]
    if missing:
        issues.append(f"{where}: missing required fields {missing}")
        return issues

    if cfg["driver"] != "ollama_local":
        issues.append(f"{where}: driver {cfg['driver']!r} — only "
                      "'ollama_local' configs are linted here")

    try:
        raw = load_experiments_registry(registry_path)
    except (SchemaError, OSError, yaml.YAMLError) as exc:
        return issues + [f"{where}: registry unreadable: {exc}"]
    entry = next((e for e in raw["experiments"]
                  if e.get("experiment_id") == cfg["experiment_id"]), None)
    if entry is None:
        return issues + [f"{where}: experiment_id {cfg['experiment_id']!r} "
                         "is not in the experiments registry"]
    if entry.get("status") != "pre-registered":
        issues.append(f"{where}: {cfg['experiment_id']!r} status is "
                      f"{entry.get('status')!r}, expected 'pre-registered' "
                      "(a run config binds a frozen design, not a demoted or "
                      "already-complete one)")
    design = entry.get("planned_design", {}) or {}
    dh = design_hash(design)
    if entry.get("design_hash") != dh:
        issues.append(f"{where}: registry entry design_hash disagrees with "
                      "its planned_design (registry tampered)")
    if cfg["design_hash"] != dh:
        issues.append(f"{where}: config design_hash {cfg['design_hash'][:16]}… "
                      f"!= frozen design_hash {dh[:16]}… — the config does not "
                      "bind the pre-registered design")

    # held-out contamination: a run config may never touch reserved eval content
    held = set((raw.get("held_out", {}) or {}).get("scenarios") or [])
    for s in cfg["scenarios"]:
        if s in held:
            issues.append(f"{where}: scenario {s!r} is HELD-OUT — a run config "
                          "may not touch reserved evaluation content")

    # the manipulated design must be realized EXACTLY, never weakened
    if cfg["interaction"] != design.get("interaction_mode"):
        issues.append(f"{where}: interaction {cfg['interaction']!r} != frozen "
                      f"interaction_mode {design.get('interaction_mode')!r}")
    if set(cfg["scenarios"]) != set(design.get("scenarios") or []):
        issues.append(f"{where}: scenarios {sorted(cfg['scenarios'])} != frozen "
                      f"{sorted(design.get('scenarios') or [])}")
    if cfg["sampler_seeds"] != (design.get("sampler_seeds") or []):
        issues.append(f"{where}: sampler_seeds {cfg['sampler_seeds']} != frozen "
                      f"{design.get('sampler_seeds')}")
    if cfg["temperature"] != design.get("temperature"):
        issues.append(f"{where}: temperature {cfg['temperature']} != frozen "
                      f"{design.get('temperature')}")
    # b-001 finding 2: the arbitration rule is part of the frozen regime. When
    # the design declares it (every live pre-registration from M8 on does —
    # _lint_frozen_policy requires it), the config must realize it EXACTLY: a
    # valid alternate rule is a different regime, not a variation.
    if "arbitration" in design and cfg["arbitration"] != design["arbitration"]:
        issues.append(f"{where}: arbitration {cfg['arbitration']!r} != frozen "
                      f"arbitration {design['arbitration']!r} — a different "
                      "arbitration rule is a NEW regime, never a variation "
                      "of the pre-registered one")
    # b1 froze explicit scenario_seeds; b2/b3 leave variant-covering seeds to
    # the operational config, so we only pin them when the design did
    if "scenario_seeds" in design and cfg["seeds"] != design["scenario_seeds"]:
        issues.append(f"{where}: seeds {cfg['seeds']} != frozen scenario_seeds "
                      f"{design['scenario_seeds']}")
    if not cfg["seeds"]:
        issues.append(f"{where}: seeds is empty — no variant would be selected")

    # variant coverage: run_sweep selects scenario.variants[seed % n_variants],
    # so the config's seeds must cover EVERY variant of each scenario. The
    # run-count check alone cannot catch a config that (e.g.) uses same-parity
    # seeds and silently drops variant A — for a wording contrast that would
    # answer the pre-registered question with no variant-A observations at all.
    try:
        from .scenario import load_scenario
        cfg_scen_dir = os.path.join(
            repo_root, cfg.get("config_dir", "configs/scenarios"))
        for sid in cfg["scenarios"]:
            spath = os.path.join(cfg_scen_dir, f"{sid}.yaml")
            if not os.path.exists(spath):
                continue   # unregistered-scenario check above already flags it
            nv = len(load_scenario(spath).variants)
            covered = {s % nv for s in cfg["seeds"]}
            if covered != set(range(nv)):
                miss = sorted(set(range(nv)) - covered)
                issues.append(
                    f"{where}: seeds {cfg['seeds']} cover variant indices "
                    f"{sorted(covered)} for {sid!r} ({nv} variants) — miss "
                    f"{miss}; every variant must be selected (seed % n_variants)")
    except (SchemaError, OSError) as exc:
        issues.append(f"{where}: variant-coverage check failed: {str(exc)[:120]}")

    # models: every frozen 'tag@digest-prefix' must map to exactly one config
    # model whose pinned digest carries that prefix; no unfrozen extras
    planned = design.get("models") or []
    matched = set()
    for spec in planned:
        base, _, prefix = spec.partition("@")
        cands = [m for m in cfg["models"] if m == base or m.startswith(base + ":")]
        if len(cands) != 1:
            issues.append(f"{where}: frozen model {spec!r} matches "
                          f"{cands} config models (want exactly 1)")
            continue
        cm = cands[0]
        matched.add(cm)
        dg = cfg["model_digests"].get(cm, "")
        if not dg:
            issues.append(f"{where}: model {cm!r} has no pinned digest")
        elif prefix and not dg.replace("sha256:", "").startswith(prefix):
            issues.append(f"{where}: model {cm!r} digest {dg[:16]}… does not "
                          f"carry the frozen prefix {prefix!r} (new regime)")
    extra = [m for m in cfg["models"] if m not in matched]
    if extra:
        issues.append(f"{where}: config adds models {extra} absent from the "
                      "frozen design")
    for m in cfg["models"]:
        if m not in cfg["model_digests"]:
            issues.append(f"{where}: model {m!r} missing from model_digests")

    # b-001 finding 1: when the frozen design pins full digests, the config's
    # model_digests mapping must equal it EXACTLY — every planned model
    # present, every digest a full immutable 64-hex value, byte-identical to
    # the frozen pin, and no extra mappings. The @prefix check above only
    # constrains models frozen as 'tag@prefix'; a design that freezes the
    # full digest separately (planned_design.model_digests) is bound here, so
    # a same-tag full-digest substitution refuses BEFORE the driver runs.
    frozen_digests = design.get("model_digests")
    if isinstance(frozen_digests, dict) and frozen_digests:
        cfg_digests = cfg["model_digests"]
        missing_d = sorted(set(frozen_digests) - set(cfg_digests))
        extra_d = sorted(set(cfg_digests) - set(frozen_digests))
        if missing_d:
            issues.append(f"{where}: model_digests missing frozen models "
                          f"{missing_d} — every planned model's digest must "
                          "be realized")
        if extra_d:
            issues.append(f"{where}: model_digests carries extra models "
                          f"{extra_d} absent from the frozen design")
        for m, want in frozen_digests.items():
            got = cfg_digests.get(m)
            if got is None:
                continue     # missing_d already refused it
            if not _is_full_digest(got):
                issues.append(f"{where}: model_digests[{m!r}] "
                              f"{str(got)[:20]!r} is not a full immutable "
                              "64-hex digest")
            if str(got).replace("sha256:", "") != \
                    str(want).replace("sha256:", ""):
                issues.append(f"{where}: model_digests[{m!r}] "
                              f"{str(got)[:20]}… != frozen digest "
                              f"{str(want)[:20]}… — a same-tag digest "
                              "substitution is a NEW regime and is refused "
                              "before the driver runs")

    # b-001 finding 3: the config side of the audited frozen numeric profile.
    # A config that mirrors a mutated+rehashed registry passes every pairwise
    # equality above, so the profile anchored in audited code must refuse it
    # here independently of any hash comparison.
    issues.extend(_profile_issues(cfg["experiment_id"], where,
                                  _config_profile_view(cfg)))
    if cfg["experiment_id"] in FROZEN_NUMERIC_PROFILES:
        issues.extend(_profile_issues(cfg["experiment_id"],
                                      f"{where} (registry)", design))
        # the prereg requires interleaved execution; the driver refuses a
        # config that leaves execution_order unset, and the gate refuses one
        # that sets it to anything the frozen design forbids.
        if cfg.get("execution_order") != "interleaved":
            issues.append(f"{where}: execution_order "
                          f"{cfg.get('execution_order')!r} != 'interleaved' "
                          "— blocked execution perfectly confounds condition "
                          "with backend state drift across the pack")

    # no duplicated grid dimension: run_sweep iterates the RAW lists, so a
    # duplicate would launch unplanned cells the declared count never counted
    # (and collide on the resume key). Every dimension must be unique.
    for dim in ("models", "scenarios", "seeds", "sampler_seeds"):
        vals = cfg.get(dim) or []
        if len(vals) != len(set(vals)):
            dupes = sorted({str(v) for v in vals if vals.count(v) > 1})
            issues.append(f"{where}: {dim} contains duplicates {dupes} — every "
                          "grid dimension must be unique (run_sweep iterates "
                          "the raw list; a duplicate launches unplanned cells)")

    # cardinality sanity: expected_run_count must equal the grid run_sweep
    # actually iterates — the RAW list lengths (== set lengths once unique)
    grid = (len(cfg["models"]) * len(cfg["scenarios"]) *
            len(cfg["seeds"]) * len(cfg["sampler_seeds"]))
    if cfg["expected_run_count"] != grid:
        issues.append(f"{where}: expected_run_count {cfg['expected_run_count']} "
                      f"!= models*scenarios*seeds*sampler_seeds = {grid}")
    return issues


# ------------------------------------------------------------- claims (M5)

def load_claims_registry(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict) or "claims" not in raw:
        raise SchemaError(f"{os.path.basename(path)}: registry must be a "
                          "mapping with a 'claims' list")
    if raw.get("registry_version") != CLAIMS_REGISTRY_VERSION:
        raise SchemaError(f"unsupported claims registry_version "
                          f"{raw.get('registry_version')!r}")
    return raw


def lint_claims_registry(claims_path: str, experiments_path: str,
                         repo_root: str) -> list:
    """Machine-check the claim ladder (SPEC §5). Returns issue strings.

    - state in CLAIM_STATES; claim_ids unique;
    - every evidence experiment_id resolves in the experiment registry, and
      a claim may cite a DEMOTED dataset only while at
      speculation/observation/demoted/refuted (demoted evidence can never
      carry a claim up the ladder);
    - `replicated`+ requires >=2 distinct evidence experiments (or an
      explicit preregistered_replication_of link);
    - `accepted` requires a finding_audit reference (the independent Codex
      audit of the CLAIM);
    - `demoted`/`refuted` require a reason and the former state;
    - statement text present and non-empty for every claim.
    """
    issues = []
    try:
        raw = load_claims_registry(claims_path)
        exp_raw = load_experiments_registry(experiments_path)
    except (SchemaError, OSError, yaml.YAMLError) as exc:
        return [f"registry unreadable: {exc}"]
    exp_by_id = {e["experiment_id"]: e for e in exp_raw["experiments"]}
    # ONLY `complete` experiments are citable evidence — a pre-registered
    # design has no runs yet; demoted datasets are never citable.
    citable_exp = {eid for eid, e in exp_by_id.items()
                   if e.get("status") == "complete"}

    ids = [c.get("claim_id") for c in raw["claims"]]
    for cid in {i for i in ids if ids.count(i) > 1}:
        issues.append(f"duplicate claim entry {cid!r}")

    for c in raw["claims"]:
        cid = c.get("claim_id", "?")
        state = c.get("state")
        if state not in CLAIM_STATES:
            issues.append(f"{cid}: state {state!r} not in {CLAIM_STATES}")
            continue
        if not (c.get("statement") or "").strip():
            issues.append(f"{cid}: empty statement")
        evidence = c.get("evidence") or []
        for eid in evidence:
            if eid not in exp_by_id:
                issues.append(f"{cid}: evidence experiment {eid!r} is not "
                              "registered")
            elif eid not in citable_exp and state in (
                    "replicated", "generalized", "accepted"):
                issues.append(f"{cid}: state {state!r} cites non-citable "
                              f"(demoted) evidence {eid!r} — demoted "
                              "evidence can never carry a claim up the "
                              "ladder")
        prereg = c.get("preregistered_replication_of")
        if prereg is not None and prereg not in citable_exp:
            issues.append(f"{cid}: preregistered_replication_of {prereg!r} "
                          "does not resolve to a citable experiment")
        if state in ("replicated", "generalized", "accepted"):
            # replication inherently needs the original + its reproduction:
            # >=2 CITABLE evidence experiments, full stop. A pre-registration
            # link is extra provenance, never a substitute for the evidence.
            if len(set(evidence) & citable_exp) < 2:
                issues.append(f"{cid}: {state!r} requires >=2 citable "
                              "evidence experiments (a pre-registration "
                              "link does not substitute for evidence)")
        if state == "accepted" and not c.get("finding_audit"):
            issues.append(f"{cid}: 'accepted' requires a finding_audit "
                          "reference (the independent audit of the claim)")
        if state in ("demoted", "refuted"):
            if not c.get("reason"):
                issues.append(f"{cid}: {state!r} requires a reason")
            if not c.get("former_state"):
                issues.append(f"{cid}: {state!r} requires former_state")
    return issues
