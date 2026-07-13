"""P1-S2 — core training-readiness record contracts.

BehaviorPolicySpec, ObservationArtifact (actor/privileged), LegalActionSet,
DecisionRecord, the termination taxonomy, and the explicit-availability
discipline — each content-addressed, immutable, self-excluding, with unavailable
values explicit and strict-DAG references.
"""
from __future__ import annotations

import pytest

from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.training.actions import LegalActionSet
from coliseum.textlab.training.availability import (available, unavailable,
                                                    validate_availability)
from coliseum.textlab.training.decision_record import DecisionRecord
from coliseum.textlab.training.observation import (VIEW_KINDS,
                                                   observation_artifact,
                                                   project_by_allowlist)
from coliseum.textlab.training.policy import BehaviorPolicySpec
from coliseum.textlab.training.termination import (TERMINATION_KINDS,
                                                   validate_termination_kind)


# ------------------------------------------------------------- availability
def test_availability_wrappers():
    assert validate_availability(available(5)) == {"status": "available", "value": 5}
    assert validate_availability(unavailable()) == {"status": "unavailable"}


@pytest.mark.parametrize("bad", [
    5, "x", {}, {"status": "maybe"}, {"status": "available"},
    {"status": "unavailable", "value": 1}, {"status": "available", "value": 1, "x": 2},
])
def test_availability_rejects_malformed(bad):
    with pytest.raises(ContentRecordError):
        validate_availability(bad)


# ------------------------------------------------------------- BehaviorPolicySpec
def _bps(**kw):
    base = dict(behavioral_config={"model": "scripted:obedient"},
                comparison_regime_id="cmp1", agent_regime_id="agt1",
                exploration_mechanism="deterministic_scripted")
    base.update(kw)
    return BehaviorPolicySpec(**base)


def test_policy_spec_defaults_unavailable_and_self_excludes():
    p = _bps()
    c = p.content
    assert c["tokenizer_identity"] == {"status": "unavailable"}
    assert c["action_score"] == {"status": "unavailable"}
    assert c["memory_state_ref"] == {"status": "unavailable"}
    assert "behavior_policy_spec_id" not in c
    assert p.domain == "trs.behavior_policy_spec.v1"


def test_policy_spec_available_field_and_identity_changes():
    a = _bps()
    b = _bps(tokenizer_identity=available("tok@abc"))
    assert a.id != b.id
    assert _bps(behavioral_config={"model": "other"}).id != a.id


def test_policy_spec_rejects_bare_unavailable_and_empty_regime():
    with pytest.raises(ContentRecordError):
        _bps(tokenizer_identity="")            # bare empty string, not a wrapper
    with pytest.raises(ContentRecordError):
        _bps(comparison_regime_id="")


# ------------------------------------------------------------- LegalActionSet
def test_legal_action_set_order_and_mask():
    las = LegalActionSet(["execute", "refuse", "stall"])
    assert las.is_legal("execute") and las.is_legal("stall")
    assert not las.is_legal("nope")
    # reordering changes identity
    assert LegalActionSet(["refuse", "execute", "stall"]).id != las.id
    # a masked-out action is not legal
    masked = LegalActionSet(["execute", "refuse"], mask=[True, False])
    assert masked.is_legal("execute") and not masked.is_legal("refuse")


@pytest.mark.parametrize("args", [
    ([],), (["a", "a"],), ([""],), (["a"], [True, True]), (["a"], ["yes"]),
])
def test_legal_action_set_rejects_bad(args):
    with pytest.raises(ContentRecordError):
        LegalActionSet(*args)


# ------------------------------------------------------------- ObservationArtifact
def test_observation_actor_privileged_distinct_and_view_in_domain():
    content = {"narrative": "a dispatch arrives"}
    actor = observation_artifact("actor", content)
    priv = observation_artifact("privileged", content)
    assert actor.domain == "trs.observation.actor.v1"
    assert priv.domain == "trs.observation.privileged.v1"
    assert actor.id != priv.id                 # same content, different view-domain
    assert actor.content["view_kind"] == "actor"


def test_observation_unknown_view_fails_closed():
    for bad in ("god", "", None):
        with pytest.raises(ContentRecordError):
            observation_artifact(bad, {"x": 1})
    assert set(VIEW_KINDS) == {"actor", "privileged"}


def test_project_by_allowlist_selects_only_allowed_keys():
    privileged = {"narrative": "n", "facts": {"harm": "none"}, "standing": 5}
    actor = project_by_allowlist(privileged, ["narrative", "available_actions"])
    assert actor == {"narrative": "n"}         # facts + standing NEVER copied
    assert "facts" not in actor and "standing" not in actor


# ------------------------------------------------------------- termination
def test_termination_taxonomy():
    for k in TERMINATION_KINDS:
        assert validate_termination_kind(k) == k
    assert "time_limit_truncation" in TERMINATION_KINDS
    assert "success_terminal" != "time_limit_truncation"      # distinct
    with pytest.raises(ContentRecordError):
        validate_termination_kind("done")


# ------------------------------------------------------------- DecisionRecord
def _decision(term="natural_terminal", sym="execute", las=None):
    las = las or LegalActionSet(["execute", "refuse", "stall"])
    return DecisionRecord(
        sequence_position=0, prev_decision_hash=None, termination_kind=term,
        action_split={"high_level_intent": None, "symbolic_action": sym,
                      "controller_actions": None, "execution_result": {"narrative": "done"}},
        actor_observation_hash="a" * 64, privileged_observation_hash="p" * 64,
        legal_action_set=las, behavior_policy_spec_hash="b" * 64)


def test_decision_record_binds_and_self_excludes():
    d = _decision()
    c = d.content
    assert c["legal_action_set_hash"] == LegalActionSet(["execute", "refuse", "stall"]).id
    assert c["world_instance_hash"] is None
    assert c["prev_decision_hash"] is None
    assert "decision_record_id" not in c
    assert d.domain == "trs.decision_record.v1"


def test_decision_record_selected_action_must_be_legal():
    with pytest.raises(ContentRecordError):
        _decision(sym="bribe")                 # not in the legal set
    # ...unless it is explicitly an invalid-action attempt
    ok = _decision(term="invalid_action_termination", sym="bribe")
    assert ok.content["action_split"]["symbolic_action"] == "bribe"


def test_decision_record_rejects_bad_shape():
    las = LegalActionSet(["execute"])
    with pytest.raises(ContentRecordError):
        DecisionRecord(0, None, "unknown_kind",
                       {"high_level_intent": None, "symbolic_action": "execute",
                        "controller_actions": None, "execution_result": None},
                       "a" * 64, "p" * 64, las, "b" * 64)
    with pytest.raises(ContentRecordError):
        DecisionRecord(0, None, "natural_terminal", {"symbolic_action": "execute"},
                       "a" * 64, "p" * 64, las, "b" * 64)   # incomplete action_split
