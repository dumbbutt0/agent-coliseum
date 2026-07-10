"""Day 3: LLM agent path — mock fixtures, parse failures, confidence, latency
semantics, and the capture-and-replay determinism tier."""
import json
import os

import pytest

from coliseum.textlab.agents import MockLLMAgent, build_prompt, make_agent, parse_llm_response
from coliseum.textlab.metrics import compute_run_metrics
from coliseum.textlab.runner import run_scenario
from coliseum.textlab.schema import SchemaError

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


# ---------------------------------------------------------------- parse pipeline

def test_mock_reflex_and_planner_parse(tmp_path):
    r = run_scenario(CK, "llm:mock:steward_obedient", 42, str(tmp_path))
    assert r.final_actions == ["execute", "verify", "refuse"]     # the fixture's moral profile
    nodes = read_nodes(r.run_dir)
    for n in nodes:
        assert n["reflex_choice"]["meta"]["parse_status"] == "ok"
        assert n["planner_choice"]["meta"]["parse_status"] == "ok"
        assert n["reflex_choice"]["meta"]["backend"] == "mock"
    # divergence at d2 (verify vs execute) AND d3 (refuse vs execute)
    assert [n["reflex_choice"]["action_id"] != n["planner_choice"]["action_id"]
            for n in nodes] == [False, True, True]


def test_json_extraction_from_prose():
    class A:  # minimal action stub
        def __init__(self, aid): self.action_id = aid
    choice, status = parse_llm_response(
        'Sure! Here you go: {"action": "refuse", "confidence": 0.7, "reason": "no", '
        '"expected_reward": 0} Hope that helps!', [A("refuse"), A("execute")])
    assert status == "ok" and choice.action_id == "refuse"
    assert choice.model_stated_confidence == 0.7


def test_bad_json_logs_parse_failure_with_deterministic_fallback(tmp_path):
    r = run_scenario(CK, "llm:mock:garbled", 42, str(tmp_path))
    nodes = read_nodes(r.run_dir)
    d1_reflex = nodes[0]["reflex_choice"]
    assert d1_reflex["meta"]["parse_status"] == "parse_failure"   # prose, no JSON
    assert d1_reflex["meta"]["fallback"] is True
    assert d1_reflex["confidence"] == 0.0
    assert d1_reflex["model_stated_confidence"] is None
    assert d1_reflex["action_id"] == "execute"                    # first available = deterministic
    assert nodes[0]["planner_choice"]["meta"]["parse_status"] == "invalid_action"
    assert nodes[1]["planner_choice"]["meta"]["parse_status"] == "parse_failure"  # broken JSON
    assert r.final_actions == ["execute", "execute", "execute"]   # all fallbacks land on execute


# ---------------------------------------------------------------- rulings

def test_confidence_recorded_on_node_and_recommendations(tmp_path):
    r = run_scenario(CK, "llm:mock:steward_obedient", 42, str(tmp_path))
    n = read_nodes(r.run_dir)[2]                                  # d3: plan refuse @ 0.85
    assert n["planner_choice"]["model_stated_confidence"] == 0.85
    assert n["confidence"] == 0.85                                # node confidence = winner's stated
    assert n["reflex_choice"]["model_stated_confidence"] == 0.7


def test_latency_logged_but_excluded_from_lineage(tmp_path, monkeypatch):
    """Two live runs with different wall-clock latencies -> same run_id, same
    everything EXCEPT the latency evidence fields (ruling 2)."""
    latencies = iter([111.0, 222.0, 333.0, 444.0, 555.0, 666.0,
                      911.0, 922.0, 933.0, 944.0, 955.0, 966.0])
    orig = MockLLMAgent._generate
    monkeypatch.setattr(MockLLMAgent, "_generate",
                        lambda self, p, b: (orig(self, p, b)[0], next(latencies)))
    a = run_scenario(CK, "llm:mock:steward_obedient", 42, str(tmp_path / "a"))
    b = run_scenario(CK, "llm:mock:steward_obedient", 42, str(tmp_path / "b"))
    assert a.run_id == b.run_id                                   # latency not in the hash
    na, nb = read_nodes(a.run_dir), read_nodes(b.run_dir)
    assert na[0]["reflex_latency_ms"] == 111.0
    assert nb[0]["reflex_latency_ms"] == 911.0                    # logged, differing
    assert [n["final_action"] for n in na] == [n["final_action"] for n in nb]


def test_reflex_and_planner_budgets_differ_same_model():
    """Ruling 1: same model, different pressure — the reflex prompt forbids
    deliberation and the budgets differ; both are in the lineage config."""
    agent = make_agent("llm:mock:steward_obedient")
    spec = agent.spec_dict()
    assert spec["model"] == "steward_obedient"
    assert spec["reflex_budget"]["num_predict"] < spec["planner_budget"]["num_predict"]
    assert "latency" not in json.dumps(spec)

    class A:
        def __init__(self, aid): self.action_id, self.label = aid, aid
    state = {"narrative": "x", "dp_id": "d"}
    fast = build_prompt(state, [A("go")], deliberate=False)
    slow = build_prompt(state, [A("go")], deliberate=True)
    assert "IMMEDIATELY" in fast and "IMMEDIATELY" not in slow


# ---------------------------------------------------------------- replay tier

def test_llm_replay_from_captures_is_byte_identical(tmp_path, monkeypatch):
    latencies = iter([101.5, 202.5, 303.5, 404.5, 505.5, 606.5])
    orig = MockLLMAgent._generate
    monkeypatch.setattr(MockLLMAgent, "_generate",
                        lambda self, p, b: (orig(self, p, b)[0], next(latencies)))
    live = run_scenario(CK, "llm:mock:steward_obedient", 42, str(tmp_path / "live"))
    assert os.path.exists(os.path.join(live.run_dir, "captures.jsonl"))
    monkeypatch.setattr(MockLLMAgent, "_generate",
                        lambda self, p, b: (_ for _ in ()).throw(AssertionError("backend called during replay")))
    replayed = run_scenario(CK, "llm:mock:steward_obedient", 42, str(tmp_path / "replay"),
                            replay_from=live.run_dir)
    assert replayed.run_id == live.run_id
    with open(os.path.join(live.run_dir, "decisions.jsonl"), "rb") as f1, \
         open(os.path.join(replayed.run_dir, "decisions.jsonl"), "rb") as f2:
        assert f1.read() == f2.read()                             # incl. the odd latencies


def test_replay_requires_captures_and_llm_agent(tmp_path):
    scripted = run_scenario(CK, "scripted:obedient", 42, str(tmp_path / "s"))
    with pytest.raises(SchemaError, match="only applies to llm"):
        run_scenario(CK, "scripted:obedient", 42, str(tmp_path / "x"),
                     replay_from=scripted.run_dir)
    with pytest.raises(SchemaError, match="no captures"):
        run_scenario(CK, "llm:mock:steward_obedient", 42, str(tmp_path / "y"),
                     replay_from=str(tmp_path / "nowhere"))


# ---------------------------------------------------------------- integration

def test_metrics_engine_reads_llm_runs(tmp_path):
    r = run_scenario(CK, "llm:mock:steward_obedient", 42, str(tmp_path))
    rep = compute_run_metrics(r.run_dir)
    assert rep["metrics"]["reflex_planner_divergence_rate"]["value"] == pytest.approx(2 / 3)
    assert rep["metrics"]["refusal_rate"]["value"] == pytest.approx(1 / 3)
    assert rep["agent_id"] == "llm:mock:steward_obedient"


def test_scripted_agents_unaffected(tmp_path):
    """The gold deterministic baseline is untouched by the LLM path."""
    r = run_scenario(CK, "scripted:obedient", 42, str(tmp_path))
    assert r.final_actions == ["execute", "verify", "execute"]
    nodes = read_nodes(r.run_dir)
    assert not os.path.exists(os.path.join(r.run_dir, "captures.jsonl"))
    assert nodes[0]["reflex_choice"]["meta"] == {}
    assert nodes[0]["reflex_latency_ms"] == 0.0