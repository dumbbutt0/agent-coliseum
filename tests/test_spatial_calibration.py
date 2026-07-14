"""Spatial Butterfly calibration MVP (design rev 4, integrated 001214) — the
scripted measurement baseline: six preregistered interventions (one per golden
scenario + the R3 scenario), witnessed treatment runs, matched pairs, and
deterministic divergence reports with PINNED ids. Refusal coverage for the
replay-gate authentication prerequisite, binding cross-checks, the fixed
attempt index, the claim ceiling, and the 0.3 projector dispatch."""
from __future__ import annotations

import json
import os

import pytest

from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.cli import main as cli_main
from coliseum.textlab.spatial.calibration import (CLAIM_CEILING, INTERVENTIONS,
                                                  SpatialDivergenceReport,
                                                  build_divergence_report,
                                                  build_matched_pair,
                                                  build_treatment_scenario,
                                                  derive_execution_instance_id,
                                                  intervention_record)
from coliseum.textlab.spatial.registry import SpatialSpecRegistry
from coliseum.textlab.spatial.run import execute_spatial_run

#: the pinned scripted-baseline identities (seed 42): any drift anywhere in the
#: substrate, runner, fork machinery, normalization, or record identity fails.
BASELINE_PINS = {
    "iv_private_object_relinquish_v1": {
        "pair": "660f479a18f80336379c43acdd01b2d2cbf842ca9e67f91f5032bc9391ff91d4",
        "report": "a6d3a9dc498db8f3457e90d851a8727bf2fba84d700f3d71807b2dfb241886a0",
    },
    "iv_nav_linger_far_v1": {
        "pair": "65b2c6a9601ae109acbea27b70aa38ff339aad99c5c646486bcd013d44db6065",
        "report": "17bbb69bfdb70453c1f26351fa77add9b5d894a4b99bcaf1497ef8272326a568",
    },
    "iv_pipeline_keep_boxed_v1": {
        "pair": "274a713ee5600c4bc89661535d259c9b4807f507975b478fbddb45f3a14b5838",
        "report": "cc194329271defca524658c0d902ebb221fbe195a5a7fc02880b19b9081d74fe",
    },
    "iv_asymmetry_retreat_v1": {
        "pair": "3f8fc318e55179e14e97e2c7dc8bd9fa200d9538356fa6d152b599bc4e9371d7",
        "report": "9971979507003df9ae3cd856f865db7916303c0616bb4f6acae820ad37b831a3",
    },
    "iv_scarce_abandon_race_v1": {
        "pair": "fc5183b937d570060c78621ccaacd0045de1b4839625a99f36cca1156427182e",
        "report": "55c9d84d3a89c6568a2fef3bb3d63e333bcc806dd204df743bf2e6cd57b43e65",
    },
    "iv_long_march_halt_v1": {
        "pair": "c532a115e584a21157d7f69b6f3d0b06c88f15a680cb682f552c5d7b11f368fb",
        "report": "1400eae2d40ff9dba91f7d38f6d349762b92fb42934aa145edd708a3ccc45999",
    },
}


@pytest.fixture(scope="module")
def baseline(tmp_path_factory):
    """Execute the FULL scripted baseline once: control + treatment + pair +
    report for every preregistered intervention (each construction step runs its
    replay-gate authentication internally)."""
    root = str(tmp_path_factory.mktemp("calibration"))
    out = {}
    for name, spec in INTERVENTIONS.items():
        c = execute_spatial_run(spec["scenario"], spec["seed"], out_root=root)
        cdir = os.path.join(root, c["run_id"])
        t = execute_spatial_run(spec["scenario"], spec["seed"], out_root=root,
                                intervention=name, control_run_dir=cdir)
        tdir = os.path.join(root, t["run_id"])
        pair = build_matched_pair(name, cdir, tdir)
        report = build_divergence_report(pair, cdir, tdir)
        out[name] = {"root": root, "control": c, "treatment": t,
                     "control_dir": cdir, "treatment_dir": tdir,
                     "pair": pair, "report": report}
    return out


def test_baseline_pinned_pairs_and_reports(baseline):
    for name, pins in BASELINE_PINS.items():
        assert baseline[name]["pair"].id == pins["pair"], name
        assert baseline[name]["report"].id == pins["report"], name


def test_divergence_semantics(baseline):
    """Scripted determinism: divergence lands EXACTLY one coordinate after the
    fork; the claim ceiling is the fixed string; pathway measures are
    not_applicable; treatment evidence carries schema 0.3 while every control
    remains byte-level schema 0.2."""
    for name, b in baseline.items():
        rc = b["report"].content
        assert rc["first_divergent_coordinate"] == rc["fork_position"] + 1, name
        assert rc["claim_ceiling"] == CLAIM_CEILING
        assert rc["pathway_note"] == "not_applicable"
        assert b["treatment"]["spatial_run_schema_version"] == "0.3"
        assert b["control"]["spatial_run_schema_version"] == "0.2"
        # every agent's terminal placements differ (all six interventions move
        # world outcomes, not just private state).
        for key, pa in rc["per_agent"].items():
            assert pa["terminal_placement_delta"], (name, key)


def test_execution_instance_binding(baseline):
    """The recorded execution instance re-derives exactly from the pair bindings
    (seed-bound; attempt fixed at 0), and a non-zero attempt refuses."""
    for name, b in baseline.items():
        iv = intervention_record(name)
        spec = iv.canonical_spec
        pc = b["pair"].content
        expected = derive_execution_instance_id(
            iv.intervention_id, spec["scenario"], spec["seed"],
            spec["agent_key"], b["control"]["world_line_id"],
            pc["control"]["source_evidence_id"], spec["fork_position"],
            spec["fork_state_hash"])
        assert b["treatment"]["execution_instance_id"] == expected
        assert pc["execution_instance_id"] == expected
    with pytest.raises(ContentRecordError, match="attempt_index"):
        derive_execution_instance_id("iv", "s", 42, "a", "w" * 64, "e" * 64,
                                     1, "f" * 64, attempt_index=1)


def test_treatment_replay_and_projection(baseline):
    """A treatment run replays byte-identically through the CLI gate and projects
    through the trajectory corpus under strict 0.3 dispatch; stripping a
    treatment field refuses."""
    from coliseum.textlab.training.spatial_trajectory_projection import (
        project_spatial_trajectory)
    b = baseline["iv_private_object_relinquish_v1"]
    cli_main(["spatial-replay", b["treatment"]["run_id"],
              "--spatial-root", b["root"]])
    p = project_spatial_trajectory(b["treatment_dir"])
    assert p["manifests"]                              # per-agent trajectories
    import shutil
    stale = os.path.join(b["root"], "stripped-treatment")
    shutil.copytree(b["treatment_dir"], stale)
    rj = json.load(open(os.path.join(stale, "run.json")))
    del rj["execution_instance_id"]
    with open(os.path.join(stale, "run.json"), "w") as fh:
        json.dump(rj, fh)
    with pytest.raises(ContentRecordError, match="missing"):
        project_spatial_trajectory(stale)


def test_tampered_control_refused_by_replay_gate(baseline, tmp_path):
    """The replay gate is the authentication prerequisite: a control directory
    with ONE altered evidence byte cannot enter treatment construction — hashing
    would happily rebind it; the gate refuses it."""
    import shutil
    b = baseline["iv_nav_linger_far_v1"]
    bad_root = tmp_path / "bad"
    bad_root.mkdir()
    bad = bad_root / os.path.basename(b["control_dir"])
    shutil.copytree(b["control_dir"], bad)
    obs = bad / "observations.jsonl"
    data = obs.read_bytes()
    obs.write_bytes(data[:-2] + b"X\n")
    with pytest.raises(ContentRecordError, match="replay gate"):
        build_treatment_scenario("iv_nav_linger_far_v1", SpatialSpecRegistry(),
                                 str(bad))


def test_pair_binding_cross_checks(baseline):
    """A treatment paired against the WRONG control refuses (bindings do not
    match), and a pair cannot cite an intervention for a different scenario."""
    t = baseline["iv_private_object_relinquish_v1"]
    wrong_control = baseline["iv_nav_linger_far_v1"]["control_dir"]
    with pytest.raises(ContentRecordError):
        build_matched_pair("iv_private_object_relinquish_v1", wrong_control,
                           t["treatment_dir"])
    with pytest.raises(ContentRecordError):
        build_matched_pair("iv_nav_linger_far_v1", t["control_dir"],
                           t["treatment_dir"])


def test_runner_keyword_pairing_and_unknown_intervention(tmp_path):
    with pytest.raises(ContentRecordError, match="together"):
        execute_spatial_run("spatial_nav_exploration_v1", 42,
                            out_root=str(tmp_path), intervention="iv_x")
    with pytest.raises(ContentRecordError, match="unknown intervention"):
        intervention_record("iv_nonexistent_v9")


def test_report_record_refusals():
    """Record-level rules: divergence at/before the fork refuses; a wrong claim
    ceiling refuses; a fabricated pathway note refuses."""
    kw = dict(matched_pair_id="p" * 64, fork_position=3, per_agent={},
              lengths={"control_chain": 5, "treatment_chain": 4,
                       "combined_coordinates_compared": 1})
    SpatialDivergenceReport(first_divergent_coordinate=4,
                            claim_ceiling=CLAIM_CEILING, **kw)
    SpatialDivergenceReport(first_divergent_coordinate=None,
                            claim_ceiling=CLAIM_CEILING, **kw)
    with pytest.raises(ContentRecordError, match="fork anchor"):
        SpatialDivergenceReport(first_divergent_coordinate=3,
                                claim_ceiling=CLAIM_CEILING, **kw)
    with pytest.raises(ContentRecordError, match="claim_ceiling"):
        SpatialDivergenceReport(first_divergent_coordinate=4,
                                claim_ceiling="this model is aligned", **kw)
    with pytest.raises(ContentRecordError, match="fabricated"):
        SpatialDivergenceReport(first_divergent_coordinate=4,
                                claim_ceiling=CLAIM_CEILING,
                                pathway_note="planner_beats_reflex", **kw)


def test_intervention_records_registry_admitted():
    """The preregistered definitions admit into the integrated slice-1
    InterventionRegistry (content-addressed, construction-frozen) and their
    canonical specs carry the exhaustive fork bindings."""
    from coliseum.textlab.intervention import InterventionRegistry
    reg = InterventionRegistry()
    for name in INTERVENTIONS:
        iv = intervention_record(name)
        reg.register(iv)
        spec = iv.canonical_spec
        assert spec["fork_position"] is not None and spec["fork_state_hash"]
        assert spec["substituted_intents"]
        assert iv.cls == "policy" and iv.kind == "spatial_intent_substitution_v1"
