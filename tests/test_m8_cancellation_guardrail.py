"""PERMANENT cancellation guardrail (owner a-005 requirement).

The distributional narrowing exists BECAUSE the aggregate TV(A,B) statistic is
blind to balanced unit-level effects. This fixture pins that exact adversarial
case forever and enforces the claim boundary:

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
# the correct reason legitimately DISCLAIMS per-unit invariance ("does NOT
# establish per-unit invariance"), so the bare phrase "per-unit invariance" is
# NOT forbidden — only affirmative sharp/per-unit assertions are. The
# distributional report never invokes "sharp" at all, so its presence is a
# regression signal.
_FORBIDDEN_SUBSTRINGS = (
    "no order effect",          # owner's exact forbidden phrase
    "sharp",                    # a distributional verdict never says "sharp"
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
    """The verdict text may never AFFIRM the per-unit / sharp claims the
    narrowing removed — those claims are FALSE on this pack (every unit changed)
    and must be unrepresentable, not merely discouraged. The report MUST instead
    carry the disclaimer that per-unit invariance is not established."""
    agent = _run(tmp_path)["per_agent"]["live"]
    reason = agent["verdict_reason"].lower()
    for bad in _FORBIDDEN_SUBSTRINGS:
        assert bad not in reason, f"forbidden claim {bad!r} in: {reason}"
    # the emitted verdict enum itself carries no "no_order_effect" literal
    assert agent["verdict"] == "no_distributional_order_effect_observed"
    assert "distributional" in agent["verdict"]
    # the honest disclaimer IS required (this is the whole point of the scope)
    assert ("does not establish per-unit invariance" in reason
            or "out of scope" in reason)


def test_report_declares_the_distributional_null_and_scope(tmp_path):
    """The report self-documents the operative null as distributional and
    carries the per-unit claim limitation (marginals only; cancelling effects
    out of scope; a non-rejection is not per-unit invariance). These fields are
    at the report top level."""
    report = _run(tmp_path)
    assert report["null_form"] == "distributional"
    limitation = report.get("per_unit_claim_limitation", "").lower()
    assert "per-unit" in limitation
    assert "out of scope" in limitation
