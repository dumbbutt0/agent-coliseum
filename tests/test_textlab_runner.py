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


def test_arbitration_recorded_and_lineage_sensitive(tmp_path):
    a = run_scenario(CK, "scripted:obedient", seed=42, out_root=str(tmp_path / "a"))
    for n in read_nodes(a.run_dir):
        assert n["arbitration_rule"] == "planner_priority"
    assert a.run.arbitration == "planner_priority"
    b = run_scenario(CK, "scripted:obedient", seed=42, out_root=str(tmp_path / "b"),
                     arbitration="reflex_under_time_pressure")
    assert b.run_id != a.run_id            # different arbitration = different lineage
    # corrupt_king has no time_pressure-3 dp, so behavior matches planner_priority here
    assert b.final_actions == a.final_actions
    assert read_nodes(b.run_dir)[0]["arbitration_rule"] == "reflex_under_time_pressure"


def test_reflex_wins_under_max_time_pressure(tmp_path):
    import yaml
    with open(CK, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    raw["decision_points"][1]["time_pressure"] = 3      # d2 becomes a snap decision
    p = tmp_path / "ck_pressure.yaml"
    p.write_text(yaml.safe_dump(raw), encoding="utf-8")
    r = run_scenario(str(p), "scripted:obedient", seed=42, out_root=str(tmp_path / "runs"),
                     arbitration="reflex_under_time_pressure")
    nodes = read_nodes(r.run_dir)
    # obedient reflex executes, planner wants verify — under pressure the reflex acts
    assert nodes[1]["reflex_choice"]["action_id"] == "execute"
    assert nodes[1]["planner_choice"]["action_id"] == "verify"
    assert nodes[1]["final_action"] == "execute"
    assert r.final_actions == ["execute", "execute", "execute"]


def test_event_delta_logged_for_matured_consequence(tmp_path):
    result = run_scenario(CK, "scripted:selfish", seed=42, out_root=str(tmp_path))
    events = []
    with open(f"{result.run_dir}/decisions.jsonl", encoding="utf-8") as fh:
        for line in fh:
            ev = json.loads(line)
            if ev["kind"] == "event_delta":
                events.append(ev["data"])
    assert len(events) == 1
    assert events[0]["source"] == "world"
    assert events[0]["state_delta"] == [{"field": "unrest", "op": "add", "value": 1}]


def test_state_reconstructs_from_deltas(tmp_path):
    """Ruling 2 end-to-end: folding initial_state through every logged op reproduces
    the final state_after snapshot — absolute state is derivable, not primary."""
    from coliseum.textlab.scenario import load_scenario
    from coliseum.textlab.schema import apply_delta
    result = run_scenario(CK, "scripted:obedient", seed=42, out_root=str(tmp_path))
    state = dict(load_scenario(CK).initial_state)
    with open(f"{result.run_dir}/decisions.jsonl", encoding="utf-8") as fh:
        for line in fh:
            ev = json.loads(line)
            if ev["kind"] in ("event_delta", "outcome"):
                state = apply_delta(state, ev["data"]["state_delta"])
    assert state == read_nodes(result.run_dir)[-1]["state_after"]


def test_seed_selects_variant(tmp_path):
    a = run_scenario(CK, "scripted:obedient", seed=42, out_root=str(tmp_path))
    b = run_scenario(CK, "scripted:obedient", seed=7, out_root=str(tmp_path))
    assert a.run.variant_id == "v0_province"
    assert b.run.variant_id == "v1_harbor"
    assert a.run_id != b.run_id
