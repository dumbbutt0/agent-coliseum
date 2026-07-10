"""Day-3b rulings: thinking-budget artifacts are format failures (never moral data),
and model digests pin lineage (no digest, not reportable)."""
import json
import os
import shutil

import pytest

import coliseum.textlab.agents as agents_mod
from coliseum.textlab.metrics import compute_run_metrics
from coliseum.textlab.runner import run_scenario

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CK = os.path.join(ROOT, "configs", "scenarios", "corrupt_king.yaml")


def read_nodes(run_dir):
    nodes = []
    with open(os.path.join(run_dir, "decisions.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            ev = json.loads(line)
            if ev["kind"] == "decision_node":
                nodes.append(ev["data"])
    return nodes


# ------------------------------------------------- ruling 1: thinking artifacts

def test_thinking_overflow_classified_as_artifact(tmp_path):
    r = run_scenario(CK, "llm:mock:thinking_overflow", 42, str(tmp_path))
    nodes = read_nodes(r.run_dir)
    d1_reflex = nodes[0]["reflex_choice"]["meta"]          # unclosed <think>, no JSON
    assert d1_reflex["parse_status"] == "parse_failure"
    assert d1_reflex["failure_kind"] == "thinking_budget_artifact"
    assert d1_reflex["reflex_valid"] is False
    d2_reflex = nodes[1]["reflex_choice"]["meta"]          # closed <think>, still no JSON
    assert d2_reflex["failure_kind"] == "thinking_budget_artifact"


def test_think_strip_lets_planner_parse(tmp_path):
    r = run_scenario(CK, "llm:mock:thinking_overflow", 42, str(tmp_path))
    d1_plan = read_nodes(r.run_dir)[0]["planner_choice"]
    assert d1_plan["meta"]["parse_status"] == "ok"         # <think>…</think> stripped, JSON kept
    assert d1_plan["action_id"] == "execute"
    assert r.final_actions == ["execute", "refuse", "refuse"]


def test_non_thinking_failures_keep_their_own_kinds(tmp_path):
    r = run_scenario(CK, "llm:mock:garbled", 42, str(tmp_path))
    nodes = read_nodes(r.run_dir)
    assert nodes[0]["reflex_choice"]["meta"]["failure_kind"] == "malformed_json"   # prose, no <think>
    assert nodes[0]["planner_choice"]["meta"]["failure_kind"] == "invalid_action"
    assert nodes[2]["planner_choice"]["meta"]["failure_kind"] is None              # ok


def test_artifacts_never_score_as_moral_behavior(tmp_path):
    """garbled: winners at d1+d2 are fallbacks -> excluded from moral rates entirely."""
    r = run_scenario(CK, "llm:mock:garbled", 42, str(tmp_path))
    m = compute_run_metrics(r.run_dir)["metrics"]
    assert m["valid_decision_rate"]["value"] == pytest.approx(1 / 3)
    assert m["compliance_rate"]["n"] == 1                  # only d3 counts
    assert m["compliance_rate"]["value"] == 1.0
    assert m["format_compliance_under_pressure"]["value"] == pytest.approx(2 / 3)
    # divergence only over both-valid nodes (d3): no fabricated flinch from fallbacks
    assert m["reflex_planner_divergence_rate"]["n"] == 1
    assert m["reflex_planner_divergence_rate"]["value"] == 0.0


def test_format_compliance_fingerprint(tmp_path):
    r = run_scenario(CK, "llm:mock:thinking_overflow", 42, str(tmp_path))
    m = compute_run_metrics(r.run_dir)["metrics"]
    assert m["format_compliance_under_pressure"]["value"] == pytest.approx(1 / 3)
    assert m["valid_decision_rate"]["value"] == 1.0        # planner rescued every decision
    assert m["refusal_rate"]["value"] == pytest.approx(2 / 3)


def test_scripted_format_compliance_is_perfect(tmp_path):
    r = run_scenario(CK, "scripted:obedient", 42, str(tmp_path))
    m = compute_run_metrics(r.run_dir)["metrics"]
    assert m["format_compliance_under_pressure"]["value"] == 1.0
    assert m["valid_decision_rate"]["value"] == 1.0
    assert m["reflex_planner_divergence_rate"]["value"] == pytest.approx(1 / 3)  # unchanged


# ------------------------------------------------- ruling 2: digest pinning

def test_mock_digest_pinned_and_reportable(tmp_path):
    r = run_scenario(CK, "llm:mock:steward_obedient", 42, str(tmp_path))
    run = json.load(open(os.path.join(r.run_dir, "run.json"), encoding="utf-8"))
    assert run["digest_status"] == "ok"
    assert run["reportable"] is True
    info = run["llm_info"]
    assert info["model_digest"].startswith("sha256:")
    assert info["model_family"] == "mock"
    assert info["capture_hash"].startswith("sha256:")
    assert info["reflex_budget"] < info["planner_budget"]
    assert info["temperature"] == 0


def test_digest_change_alters_lineage(tmp_path, monkeypatch):
    """Editing the fixture (= repulling a model to a new digest) => NEW run lineage."""
    fixdir = tmp_path / "fixtures"
    fixdir.mkdir()
    src = os.path.join(ROOT, "tests", "fixtures", "llm", "steward_obedient.json")
    shutil.copy(src, fixdir / "steward_obedient.json")
    monkeypatch.setattr(agents_mod, "_fixtures_root", lambda: str(fixdir))

    a = run_scenario(CK, "llm:mock:steward_obedient", 42, str(tmp_path / "a"))
    fix = json.load(open(fixdir / "steward_obedient.json", encoding="utf-8"))
    fix["responses"]["d3_expulsion/plan"] = fix["responses"]["d3_expulsion/plan"].replace("0.85", "0.86")
    (fixdir / "steward_obedient.json").write_text(json.dumps(fix), encoding="utf-8")
    b = run_scenario(CK, "llm:mock:steward_obedient", 42, str(tmp_path / "b"))
    assert a.run_id != b.run_id                            # digest is in the lineage hash


def test_missing_digest_marks_non_reportable(tmp_path, monkeypatch):
    monkeypatch.setattr(agents_mod.MockLLMAgent, "__init__", _init_without_digest)
    r = run_scenario(CK, "llm:mock:steward_obedient", 42, str(tmp_path))
    run = json.load(open(os.path.join(r.run_dir, "run.json"), encoding="utf-8"))
    assert run["digest_status"] == "missing"
    assert run["reportable"] is False
    rep = compute_run_metrics(r.run_dir)
    assert rep["reportable"] is False


def _init_without_digest(self, fixture):
    agents_mod.LLMAgent.__init__(self, fixture)
    path = os.path.join(ROOT, "tests", "fixtures", "llm", f"{fixture}.json")
    with open(path, encoding="utf-8") as fh:
        self._responses = json.load(fh)["responses"]
    # digest lookup "failed": stays digest_status="missing" from the base class


def test_scripted_runs_reportable_by_definition(tmp_path):
    r = run_scenario(CK, "scripted:defiant", 42, str(tmp_path))
    run = json.load(open(os.path.join(r.run_dir, "run.json"), encoding="utf-8"))
    assert run["digest_status"] == "n/a"
    assert run["reportable"] is True
    assert run["llm_info"] == {}