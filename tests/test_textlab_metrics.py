"""Metrics engine: hand-computed rates for known persona paths, twin-pair metrics."""
import os

import pytest

from coliseum.textlab.metrics import aggregate, compute_run_metrics
from coliseum.textlab.runner import run_scenario

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCEN = lambda name: os.path.join(ROOT, "configs", "scenarios", f"{name}.yaml")
CONFIG_DIR = os.path.join(ROOT, "configs", "scenarios")


def m(report, name):
    return report["metrics"][name]["value"]


def test_obedient_corrupt_king_rates(tmp_path):
    # path: execute -> verify -> execute
    r = run_scenario(SCEN("corrupt_king"), "scripted:obedient", 42, str(tmp_path))
    rep = compute_run_metrics(r.run_dir)
    assert m(rep, "compliance_rate") == pytest.approx(2 / 3)
    assert m(rep, "harm_compliance_rate") == pytest.approx(1 / 2)   # d2 verify, d3 execute
    assert m(rep, "verification_rate") == pytest.approx(1 / 3)
    assert m(rep, "refusal_rate") == 0.0
    assert m(rep, "reflex_planner_divergence_rate") == pytest.approx(1 / 3)  # the flinch
    assert m(rep, "deferred_consequence_count") == 0                # verify at d2 -> no requisition


def test_defiant_and_selfish_extremes(tmp_path):
    defiant = compute_run_metrics(
        run_scenario(SCEN("corrupt_king"), "scripted:defiant", 42, str(tmp_path / "d")).run_dir)
    assert m(defiant, "compliance_rate") == 0.0
    assert m(defiant, "refusal_rate") == 1.0
    assert m(defiant, "reflex_planner_divergence_rate") == 0.0

    selfish = compute_run_metrics(
        run_scenario(SCEN("corrupt_king"), "scripted:selfish", 42, str(tmp_path / "s")).run_dir)
    assert m(selfish, "compliance_rate") == 1.0
    assert m(selfish, "harm_compliance_rate") == 1.0
    assert m(selfish, "deferred_consequence_count") == 1            # requisition consequence matured


def test_merciful_control_twin_delta(tmp_path):
    dirs = []
    for i, scen in enumerate(["corrupt_king", "corrupt_king_harmless"]):
        for seed in (1, 2):
            dirs.append(run_scenario(SCEN(scen), "scripted:merciful", seed,
                                     str(tmp_path / f"{i}-{seed}")).run_dir)
    agg = aggregate(dirs, CONFIG_DIR)
    delta = agg["control_twin_delta"]["corrupt_king_vs_corrupt_king_harmless|scripted:merciful"]
    # merciful: primary execute/verify/refuse vs control execute x3
    assert delta["compliance_rate"] == pytest.approx(1 / 3 - 1.0)
    assert delta["refusal_rate"] == pytest.approx(1 / 3)


def test_faith_knob_sensitivity(tmp_path):
    dirs = []
    for i, scen in enumerate(["corrupt_king", "corrupt_king_verifiable"]):
        for seed in (1, 2):
            dirs.append(run_scenario(SCEN(scen), "scripted:obedient", seed,
                                     str(tmp_path / f"{i}-{seed}")).run_dir)
    agg = aggregate(dirs, CONFIG_DIR)
    # obedient verifies when unverifiable (d2 compliance 0), executes when checkable (1)
    # => sensitivity -1.0 = verification-seeking, not blind faith
    assert agg["faith_knob_sensitivity"]["scripted:obedient"] == pytest.approx(-1.0)


def test_variant_spread_present(tmp_path):
    dirs = [run_scenario(SCEN("corrupt_king"), "scripted:obedient", s,
                         str(tmp_path / str(s))).run_dir for s in (1, 2)]  # v1 + v0
    agg = aggregate(dirs, CONFIG_DIR)
    spread = agg["cells"]["corrupt_king|scripted:obedient"]["variant_spread"]["compliance_rate"]
    assert set(spread) == {"v0_province", "v1_harbor"}
    assert spread["v0_province"] == spread["v1_harbor"]   # scripted agents: no prompt sensitivity