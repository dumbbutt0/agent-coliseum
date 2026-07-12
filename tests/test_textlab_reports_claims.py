"""M5 report generators + claim lifecycle + dashboard: reports derive
idempotently from artifacts (same inputs -> byte-identical); the claim
ladder lints clean and refuses every defect class; the dashboard is a pure
function of its inputs and shows accepted-only paper candidates."""
import copy
import os

import yaml

from coliseum.textlab import reports
from coliseum.textlab.registry import (entry_hash,
                                       lint_claims_registry,
                                       load_claims_registry)
from coliseum.textlab.runner import run_scenario

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLAIMS = os.path.join(ROOT, "configs", "registry", "claims.yaml")
EXPERIMENTS = os.path.join(ROOT, "configs", "registry", "experiments.yaml")
SCEN = os.path.join(ROOT, "configs", "scenarios", "corrupt_king.yaml")


# ------------------------------------------------------------- reports

def test_run_report_idempotent(tmp_path):
    r = run_scenario(SCEN, "scripted:obedient", 42, str(tmp_path))
    a = reports.run_report(r.run_dir)
    b = reports.run_report(r.run_dir)
    assert a == b
    assert "corrupt_king" in a and "metrics_version" in a


def test_experiment_and_milestone_reports_derive_from_registries():
    exp = reports.experiment_report("exp2-v1cistern-replication", ROOT)
    assert "exp2-v1cistern-replication" in exp
    # the claim resting on exp2 shows with its ladder state
    assert "deliberation-layer-wording-sensitivity" in exp
    assert "**replicated**" in exp
    mile = reports.milestone_report(ROOT)
    assert "## paper-citable findings (ACCEPTED only)" in mile
    assert "no claim has passed an independent finding audit" in mile
    # idempotent
    assert reports.milestone_report(ROOT) == mile


def test_milestone_report_family_census():
    mile = reports.milestone_report(ROOT)
    for fam in ("authority", "moral_conflict", "deception"):
        assert fam in mile


# ------------------------------------------------------------- claims

def test_real_claims_registry_clean():
    assert lint_claims_registry(CLAIMS, EXPERIMENTS, ROOT) == []


def test_backfilled_claims_shape():
    raw = load_claims_registry(CLAIMS)
    by_id = {c["claim_id"]: c for c in raw["claims"]}
    assert by_id["deliberation-layer-wording-sensitivity"]["state"] == \
        "replicated"
    # the full-audit withdrawals are preserved as first-class demotions
    for cid in ("cover-story-maintenance", "remembered-confession",
                "temporal-dissociation-cognitive-layers"):
        assert by_id[cid]["state"] == "demoted"
        assert by_id[cid]["reason"] and by_id[cid]["former_state"]


def _claims_mutated(tmp_path, mutate):
    raw = load_claims_registry(CLAIMS)
    mutate(raw)
    p = tmp_path / "claims.yaml"
    p.write_text(yaml.safe_dump(raw, sort_keys=False))
    return lint_claims_registry(str(p), EXPERIMENTS, ROOT)


def test_accepted_requires_finding_audit(tmp_path):
    def mutate(raw):
        c = next(x for x in raw["claims"]
                 if x["claim_id"] == "deliberation-layer-wording-sensitivity")
        c["state"] = "accepted"   # no finding_audit
    issues = _claims_mutated(tmp_path, mutate)
    assert any("'accepted' requires a finding_audit" in i for i in issues)


def test_replicated_needs_two_citable_or_prereg_link(tmp_path):
    def mutate(raw):
        c = next(x for x in raw["claims"]
                 if x["claim_id"] == "deliberation-layer-wording-sensitivity")
        c["evidence"] = ["exp2-v1cistern-replication"]   # one only
        c.pop("preregistered_replication_of", None)
    issues = _claims_mutated(tmp_path, mutate)
    assert any(">=2 citable evidence experiments" in i for i in issues)


def test_demoted_evidence_cannot_carry_claim_up(tmp_path):
    def mutate(raw):
        c = next(x for x in raw["claims"]
                 if x["claim_id"] == "universal-harm-refusal-temp0")
        c["state"] = "generalized"   # cites demoted pilot + sweep-v2
    issues = _claims_mutated(tmp_path, mutate)
    assert any("demoted) evidence" in i for i in issues)


def test_demotion_requires_reason_and_former_state(tmp_path):
    def mutate(raw):
        c = next(x for x in raw["claims"]
                 if x["claim_id"] == "cover-story-maintenance")
        c.pop("reason")
        c.pop("former_state")
    issues = _claims_mutated(tmp_path, mutate)
    assert any("requires a reason" in i for i in issues)
    assert any("requires former_state" in i for i in issues)


def test_unregistered_evidence_refused(tmp_path):
    def mutate(raw):
        raw["claims"][0]["evidence"] = ["no-such-experiment"]
    issues = _claims_mutated(tmp_path, mutate)
    assert any("is not registered" in i for i in issues)


# ------------------------------------------------------------- dashboard

def _load_dashboard():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "dashboard", os.path.join(ROOT, "scripts", "dashboard.py"))
    dash = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dash)
    return dash


def test_dashboard_render_is_pure_over_snapshot():
    """render() must be a PURE function of an explicit snapshot — the same
    snapshot yields byte-identical output; gather() is the impure step."""
    dash = _load_dashboard()
    snap = {
        "roadmap": {"milestone": "first-gladiator",
                    "tasks": [{"task_id": f"m{i}-x", "status": "pending"}
                              for i in range(1, 16)]},
        "scenarios": [{"scenario_id": "s", "family": "authority"}],
        "experiments": [], "claims": [
            {"claim_id": "c", "state": "accepted"}],
        "council": {"chain_len": 100, "verify": True, "active": [],
                    "blocked": [], "integrated_milestones":
                    ["first-gladiator-m1", "first-gladiator-m2"]},
        "test_count": 999}
    a = dash.render(snap)
    b = dash.render(copy.deepcopy(snap))
    assert a == b                                   # pure over the snapshot
    assert "Program Dashboard" in a
    assert "/8 present" in a
    # accepted claim surfaces as a paper candidate
    assert "`c`" in a.split("Paper candidates")[1]
    # milestone completion derived from the chain snapshot, not statuses
    assert "2/15 integrated" in a


def test_dashboard_gather_render_end_to_end():
    dash = _load_dashboard()
    text = dash.render(dash.gather(test_count=777))
    assert "Program Dashboard" in text and "777" in text