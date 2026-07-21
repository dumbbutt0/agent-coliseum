"""PERMANENT cancellation guardrail (owner a-005 requirement; a-006 framing).

The confirmatory null is within-unit JOINT swap invariance, tested by a paired
permutation whose statistic is the aggregate TV(A,B) — which is blind to
balanced unit-level effects (a non-exchangeable coupling can hold TV=0 while
violating swap invariance). This fixture pins that exact adversarial case
forever and enforces the claim boundary:

  - unit 1..24: share_resource under A, decline_partnership under B
  - unit 25..48: decline_partnership under A, share_resource under B
  - C is sharply identical to A
  => the marginal terminal-action distributions of A and B are EQUAL (TV=0),
     yet EVERY unit's action changed with order (the sharp null is false).

The system MUST:
  * PERMIT "no distributional effect observed" (a correct distributional
    non-rejection under the frozen threshold);
  * make the forbidden claims UNREPRESENTABLE — never "no order effect", never
    "no individual unit was affected", never "the sharp null was preserved".

This protects the scientific claim boundary in the analysis AND (via the enum it
emits) in the result package that binds that verdict.
"""
import pytest

from coliseum.textlab.metrics import order_sensitivity_report

oc = pytest.importorskip("scripts.m8_operating_characteristics")

# AFFIRMATIVE over-claims the report may never make on a non-rejection. NOTE:
# the correct reason legitimately DISCLAIMS the removed claims (it says "does
# NOT establish swap invariance, per-unit invariance, or marginal equality"),
# so the negated phrases "swap invariance" / "per-unit invariance" are NOT
# forbidden — only affirmative sharp/per-unit assertions are. The swap-
# invariance report never invokes "sharp" at all, so its presence is a
# regression signal. The owner's forbidden phrase "no order effect" is handled
# separately (see the qualified-form check below): under the a-006 framing the
# ONLY permitted appearance is the qualified honest non-detection ("no order
# effect DETECTED at the threshold"); a bare/unqualified "no order effect"
# affirmation stays unrepresentable.
_FORBIDDEN_AFFIRMATIONS = (
    "sharp",                    # a swap-invariance verdict never says "sharp"
    "no individual unit",
    "null was preserved",
    "null preserved",
    "every unit unchanged",
)


def _cancelling_pack(root):
    """24 A/B pairs move share->decline and 24 move decline->share, so the A and
    B marginals cancel exactly; C is byte-identical to A."""
    dirs = []
    for cond in ("A", "B", "C"):
        for variant, scenario_seed in oc.VARIANTS:
            for index, sampler_seed in enumerate(oc.SAMPLER_SEEDS):
                side = (index + (0 if variant == "v0_caravan" else 12)) % 24
                a_action = ("share_resource" if side < 12
                            else "decline_partnership")
                action = a_action
                if cond == "B":
                    action = ("decline_partnership"
                              if a_action == "share_resource"
                              else "share_resource")
                dirs.append(oc._write_unit(root, cond, variant, scenario_seed,
                                           sampler_seed, action))
    return dirs


def _run(tmp_path):
    root = str(tmp_path / "pack")
    import os
    os.makedirs(root, exist_ok=True)
    dirs = _cancelling_pack(root)
    return order_sensitivity_report(
        dirs, oc.CONDITIONS, admissibility_policy=oc.FROZEN_POLICY,
        thresholds=oc.FROZEN_THRESHOLDS, replay_attestation=oc._attest(dirs),
        terminal_dp_id=oc.TERMINAL_DP_ID,
        surviving_counts={"A": 48, "B": 48, "C": 48}, retries_per_unit=0)


def test_marginals_cancel_to_zero_tv():
    """Sanity: the construction really does leave TV(A,B) at 0 while every unit
    changed — the exact blind spot the distributional claim is scoped around."""
    import tempfile
    import shutil
    root = tempfile.mkdtemp(prefix="m8-cancel-")
    try:
        dirs = _cancelling_pack(root)
        report = order_sensitivity_report(
            dirs, oc.CONDITIONS, admissibility_policy=oc.FROZEN_POLICY,
            thresholds=oc.FROZEN_THRESHOLDS,
            replay_attestation=oc._attest(dirs),
            terminal_dp_id=oc.TERMINAL_DP_ID,
            surviving_counts={"A": 48, "B": 48, "C": 48}, retries_per_unit=0)
        agent = report["per_agent"]["live"]
        assert agent["tv_distances"]["A|B"] == 0.0
    finally:
        shutil.rmtree(root)


def test_permits_the_distributional_non_rejection(tmp_path):
    """The PERMITTED outcome: with equal marginals the distributional null is
    not rejected, and the verdict says exactly that — no more."""
    agent = _run(tmp_path)["per_agent"]["live"]
    assert agent["verdict"] == "no_distributional_order_effect_observed"


def test_forbids_the_over_claim_vocabulary(tmp_path):
    """The verdict text may never AFFIRM the per-unit / sharp / swap-invariance
    claims — those claims are FALSE on this pack (every unit changed) and must be
    unrepresentable, not merely discouraged. The report MUST instead carry the
    disclaimer that a non-rejection establishes neither swap invariance nor
    per-unit invariance nor marginal equality (a-006 three-layer scope)."""
    import re
    agent = _run(tmp_path)["per_agent"]["live"]
    reason = agent["verdict_reason"].lower()
    for bad in _FORBIDDEN_AFFIRMATIONS:
        assert bad not in reason, f"forbidden affirmation {bad!r} in: {reason}"
    # "no order effect" may appear ONLY as the qualified honest non-detection
    # ("... DETECTED at the threshold"); a bare affirmation is forbidden.
    for m in re.finditer(r"no order effect", reason):
        assert reason[m.end():].lstrip().startswith("detected"), (
            f"unqualified 'no order effect' over-claim in: {reason}")
    # the emitted verdict enum itself carries no "no_order_effect" literal
    assert agent["verdict"] == "no_distributional_order_effect_observed"
    assert "distributional" in agent["verdict"]
    # the honest disclaimer IS required (the whole point of the scope): the
    # non-rejection explicitly establishes none of the removed claims, and TV=0
    # is called out as outside the confirmatory null.
    assert "does not establish" in reason
    assert "per-unit invariance" in reason
    assert "outside the confirmatory null" in reason


def test_report_declares_the_swap_invariance_null_and_scope(tmp_path):
    """The report self-documents the operative null as within-unit swap
    invariance and carries the three-layer claim limitation (inferential null
    vs marginal-TV estimand vs demonstrated-sensitivity MDE; a non-rejection
    establishes neither swap invariance nor per-unit invariance nor marginal
    equality; a TV=0 cancellation coupling is OUTSIDE the confirmatory null).
    These fields are at the report top level."""
    report = _run(tmp_path)
    assert report["null_form"] == "swap_invariance"
    limitation = report.get("claim_limitation", "").lower()
    assert "per-unit" in limitation
    # the cancellation blind spot is named as outside the null, and TV=0 is
    # explicitly disclaimed as not-evidence-the-null-is-true (the teeth).
    assert "outside the confirmatory null" in limitation
    assert "tv=0 is not evidence the null is true" in limitation
