"""P1-S3 — ActorDecisionRecord + actor/privileged non-interference proof.

The central invariant: a privileged-only change never moves an actor identity or
byte, while an actor-visible change does; and no privileged reference is present
(directly or transitively) in the actor projection.
"""
from __future__ import annotations

import pytest

from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.training.actions import LegalActionSet
from coliseum.textlab.training.actor_decision import (REMOVED_REFERENCES,
                                                      ActorDecisionRecord,
                                                      project_actor_decision)
from coliseum.textlab.training.availability import unavailable
from coliseum.textlab.training.decision_record import DecisionRecord

_LAS = LegalActionSet(["execute", "refuse", "stall"])


def _decision(actor_obs="a" * 64, priv_obs="p" * 64, world=None,
              sym="execute", term="natural_terminal"):
    return DecisionRecord(
        sequence_position=0, prev_decision_hash=None, termination_kind=term,
        action_split={"high_level_intent": None, "symbolic_action": sym,
                      "controller_actions": None,
                      "execution_result": {"narrative": "done"}},
        actor_observation_hash=actor_obs, privileged_observation_hash=priv_obs,
        legal_action_set=_LAS, behavior_policy_spec_hash="b" * 64,
        world_instance_hash=world)


def _actor(dr):
    return project_actor_decision(dr, memory_state_ref=unavailable())


# ------------------------------------------------------- structural omission
def test_actor_projection_omits_privileged_references():
    a = _actor(_decision(world="w" * 64))
    c = a.content
    assert "privileged_observation_hash" not in c
    assert "world_instance_hash" not in c
    assert set(c["removed_references"]) == set(REMOVED_REFERENCES)
    assert c["actor_observation_hash"] == "a" * 64
    assert a.domain == "trs.actor_decision.v1"
    assert "actor_decision_id" not in c


# --------------------------------------------- non-interference (THE invariant)
def test_privileged_only_change_leaves_actor_identity_byte_identical():
    base = _actor(_decision(priv_obs="p" * 64, world="w1" + "0" * 62))
    # change ONLY privileged fields (privileged observation + world instance)
    changed = _actor(_decision(priv_obs="Q" * 64, world="w2" + "0" * 62))
    assert base.id == changed.id
    assert base.canonical() == changed.canonical()      # byte-identical


def test_actor_visible_change_moves_actor_identity():
    base = _actor(_decision(actor_obs="a" * 64))
    assert _actor(_decision(actor_obs="Z" * 64)).id != base.id      # observation
    assert _actor(_decision(sym="refuse")).id != base.id            # action
    # a different legal-action set (order) changes the bound hash -> actor id
    other_las = LegalActionSet(["refuse", "execute", "stall"])
    dr = DecisionRecord(0, None, "natural_terminal",
                        {"high_level_intent": None, "symbolic_action": "execute",
                         "controller_actions": None, "execution_result": None},
                        "a" * 64, "p" * 64, other_las, "b" * 64)
    assert _actor(dr).id != base.id


def test_actor_only_reconstruction_needs_no_privileged_data():
    a = _actor(_decision())
    # recompute the id from actor content alone (privileged data physically absent)
    from coliseum.textlab._content_record import content_id
    assert content_id(a.domain, a.content, "actor_decision_id") == a.id


# ------------------------------------------------------- leak fail-closed
def _valid_actor_preimage(**over):
    p = {
        "schema_version": "1", "sequence_position": 0,
        "prev_actor_decision_hash": None, "termination_kind": "natural_terminal",
        "action_split": {"high_level_intent": None, "symbolic_action": "execute",
                         "controller_actions": None,
                         "execution_result": {"narrative": "done"}},
        "actor_observation_hash": "a" * 64, "legal_action_set_hash": "l" * 64,
        "behavior_policy_spec_hash": "b" * 64,
        "memory_state_ref": {"status": "unavailable"},
        "removed_references": list(REMOVED_REFERENCES),
    }
    p.update(over)
    return p


def test_valid_actor_preimage_constructs():
    assert ActorDecisionRecord(_valid_actor_preimage()).domain == "trs.actor_decision.v1"


def test_actor_decision_rejects_nested_privileged_reference():
    # audit 000899: a privileged/world reference nested at ANY depth is refused.
    for k in REMOVED_REFERENCES:
        nested = _valid_actor_preimage(
            action_split={"high_level_intent": None, "symbolic_action": "execute",
                          "controller_actions": None,
                          "execution_result": {"narrative": "done", k: "x" * 64}})
        with pytest.raises(ContentRecordError):
            ActorDecisionRecord(nested)


def test_actor_projection_rejects_nested_privileged_reference_in_action_split():
    leaky = DecisionRecord(
        0, None, "natural_terminal",
        {"high_level_intent": None, "symbolic_action": "execute",
         "controller_actions": None,
         "execution_result": {"world_instance_hash": "w" * 64}},   # nested priv ref
        "a" * 64, "p" * 64, _LAS, "b" * 64)
    with pytest.raises(ContentRecordError):
        _actor(leaky)


def test_actor_projection_rejects_privileged_field_in_action_split():
    leaky = DecisionRecord(
        0, None, "natural_terminal",
        {"high_level_intent": None, "symbolic_action": "execute",
         "controller_actions": None,
         "execution_result": {"facts": {"harm": "none"}}},   # privileged field
        "a" * 64, "p" * 64, _LAS, "b" * 64)
    with pytest.raises(ContentRecordError):
        _actor(leaky)


def test_actor_decision_enforces_exact_appendix_a_key_set():
    # audit 000899: missing / extra keys and wrong schema version are refused.
    incomplete = _valid_actor_preimage()
    del incomplete["memory_state_ref"]
    with pytest.raises(ContentRecordError):
        ActorDecisionRecord(incomplete)
    with pytest.raises(ContentRecordError):
        ActorDecisionRecord(_valid_actor_preimage(unexpected="x"))
    with pytest.raises(ContentRecordError):
        ActorDecisionRecord(_valid_actor_preimage(schema_version="9"))
    with pytest.raises(ContentRecordError):
        ActorDecisionRecord(_valid_actor_preimage(removed_references=["only_one"]))


def test_project_actor_decision_validates_inputs():
    with pytest.raises(ContentRecordError):
        project_actor_decision({"not": "a decision"}, unavailable())
    with pytest.raises(ContentRecordError):
        project_actor_decision(_decision(), memory_state_ref="")      # bad wrapper
    with pytest.raises(ContentRecordError):
        project_actor_decision(_decision(), unavailable(), prev_actor_decision_hash="")
