"""Runner behavior: hand-computed persona paths through corrupt_king, the designed
reflex/planner divergence, and the deferred-consequence plumbing."""
import json
import os

import pytest

from coliseum.textlab.runner import run_scenario
from coliseum.textlab.schema import from_record

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CK = os.path.join(ROOT, "configs", "scenarios", "corrupt_king.yaml")

# Hand-computed against the persona rules and the corrupt_king facts ladder
# (d1 harm none, d2 harm unverifiable, d3 harm verified):
EXPECTED_PATHS = {
    "obedient": ["execute", "verify", "execute"],   # plan verifies the unverifiable d2
    "defiant":  ["refuse", "refuse", "refuse"],
    "merciful": ["execute", "verify", "refuse"],
    "selfish":  ["execute", "execute", "execute"],
}


def read_nodes(run_dir):
    nodes = []
    with open(os.path.join(run_dir, "decisions.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            ev = json.loads(line)
            if ev["kind"] == "decision_node":
                nodes.append(ev["data"])
    return nodes


@pytest.mark.parametrize("persona,expected", EXPECTED_PATHS.items())
def test_persona_paths(tmp_path, persona, expected):
    result = run_scenario(CK, f"scripted:{persona}", seed=42, out_root=str(tmp_path))
    assert result.final_actions == expected


def test_obedient_reflex_planner_divergence_at_d2(tmp_path):
    result = run_scenario(CK, "scripted:obedient", seed=42, out_root=str(tmp_path))
    nodes = read_nodes(result.run_dir)
    assert len(nodes) == 3
    # d1: both passes comply; d2: reflex obeys, planner verifies (the designed flinch)
    assert nodes[0]["reflex_choice"]["action_id"] == nodes[0]["planner_choice"]["action_id"] == "execute"
    assert nodes[1]["reflex_choice"]["action_id"] == "execute"
    assert nodes[1]["planner_choice"]["action_id"] == "verify"
    assert nodes[1]["final_action"] == "verify"
    assert all(n["planner_consulted"] for n in nodes)


def test_decision_nodes_carry_full_schema(tmp_path):
    result = run_scenario(CK, "scripted:merciful", seed=42, out_root=str(tmp_path))
    for data in read_nodes(result.run_dir):
        node = from_record(data)          # re-validates every invariant
        assert node.scenario_id == "corrupt_king"
        assert node.reflex_latency_ms == 0.0 and node.planner_latency_ms == 0.0
        assert node.state_before["facts"]  # ground truth present for metrics


def test_deferred_consequence_matures_next_step(tmp_path):
    # selfish executes d2 -> unrest lands in state before d3
    result = run_scenario(CK, "scripted:selfish", seed=42, out_root=str(tmp_path))
    nodes = read_nodes(result.run_dir)
    assert nodes[1]["state_after"].get("unrest", 0) == 0     # not yet
    assert nodes[2]["state_before"]["unrest"] == 1           # matured
    assert nodes[2]["state_before"]["recent_events"]         # narrated to the agent


def test_run_manifest(tmp_path):
    result = run_scenario(CK, "scripted:defiant", seed=7, out_root=str(tmp_path))
    with open(os.path.join(result.run_dir, "run.json"), encoding="utf-8") as fh:
        run = json.load(fh)
    assert run["record_type"] == "run"
    assert run["status"] == "completed"
    assert run["seed"] == 7
    assert run["variant_id"] == "v1_harbor"                  # 7 % 2 == 1
    assert run["run_id"] == result.run_id
    assert run["config_hash"] and run["agent_id"] == "scripted:defiant"


def test_seed_selects_variant(tmp_path):
    a = run_scenario(CK, "scripted:obedient", seed=42, out_root=str(tmp_path))
    b = run_scenario(CK, "scripted:obedient", seed=7, out_root=str(tmp_path))
    assert a.run.variant_id == "v0_province"
    assert b.run.variant_id == "v1_harbor"
    assert a.run_id != b.run_id
