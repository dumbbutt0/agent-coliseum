"""Schema round-trips, DecisionNode invariants, delta ops, and config_hash stability."""
import pytest

from coliseum.textlab.schema import (AgentSpec, DecisionNode, EventDelta,
                                     MemoryUpdate, MetricReport, Outcome, Run,
                                     SchemaError, apply_delta, canonical_json,
                                     config_hash, from_record)


def make_node(**over):
    base = dict(
        run_id="r1", agent_id="scripted:obedient", scenario_id="corrupt_king",
        timestep=0, state_before={"standing": 5}, available_actions=["execute", "refuse"],
        reflex_choice={"action_id": "execute", "confidence": 0.9,
                       "reasoning_summary": "x", "reward_expected": 2.0},
        planner_choice={"action_id": "refuse", "confidence": 0.8,
                        "reasoning_summary": "y", "reward_expected": 0.0},
        final_action="refuse", confidence=0.8, reasoning_summary="y",
        moral_tags=["refusal"], authority_pressure=2, risk_level=1,
        reward_expected=0.0, outcome={"narrative": "n", "state_delta": []},
        state_after={"standing": 3}, memory_update="[t0] n",
        reflex_latency_ms=0.0, planner_latency_ms=0.0, planner_consulted=True,
        arbitration_rule="planner_priority")
    base.update(over)
    return DecisionNode(**base)


def test_round_trip_all_record_types():
    records = [
        AgentSpec("a1", "scripted", persona_id="obedient"),
        Run("r1", None, 42, "corrupt_king", "v0_province", "a1", "deadbeef"),
        make_node(),
        Outcome("r1", 0, "refuse", [{"field": "standing", "op": "add", "value": -2}], "declined"),
        EventDelta("r1", 1, "world", [{"field": "unrest", "op": "add", "value": 1}], "word spreads"),
        MemoryUpdate("r1", 0, "declined the order"),
        MetricReport("rep1", ["r1"], "corrupt_king", {"obedience_to_harm": {"value": 0.0, "n": 1}}, [42]),
    ]
    for original in records:
        rec = original.to_record()
        assert "record_type" in rec
        assert from_record(rec) == original


def test_decision_node_invariants():
    with pytest.raises(SchemaError):
        make_node(confidence=1.5)
    with pytest.raises(SchemaError):
        make_node(authority_pressure=7)
    with pytest.raises(SchemaError):
        make_node(final_action="not_offered")


def test_agent_and_memory_enums():
    with pytest.raises(SchemaError):
        AgentSpec("a1", "wizard")
    with pytest.raises(SchemaError):
        MemoryUpdate("r1", 0, "s", author="narrator")


def test_apply_delta_set_and_add():
    state = {"standing": 5, "refusals": 0}
    ops = [{"field": "standing", "op": "add", "value": -2},
           {"field": "refusals", "op": "add", "value": 1},
           {"field": "status", "op": "set", "value": "reprimanded"}]
    out = apply_delta(state, ops)
    assert out == {"standing": 3, "refusals": 1, "status": "reprimanded"}
    assert state == {"standing": 5, "refusals": 0}          # input untouched


def test_apply_delta_rejects_bad_ops():
    with pytest.raises(SchemaError):
        apply_delta({}, [{"field": "x", "op": "multiply", "value": 2}])
    with pytest.raises(SchemaError):
        apply_delta({}, [{"field": "x", "op": "add", "value": "three"}])
    with pytest.raises(SchemaError):
        apply_delta({"x": "text"}, [{"field": "x", "op": "add", "value": 1}])
    with pytest.raises(SchemaError):
        Outcome("r1", 0, "a", {"standing": 3}, "dict not ops")   # old format rejected


def test_config_hash_stability_and_sensitivity():
    a = {"scenario": {"x": 1, "y": [1, 2]}, "agent": {"persona": "obedient"}}
    b = {"agent": {"persona": "obedient"}, "scenario": {"y": [1, 2], "x": 1}}  # same, reordered
    assert config_hash(a) == config_hash(b)
    assert config_hash(a) != config_hash({**a, "agent": {"persona": "defiant"}})
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'
