"""M8 Phase 2 — exposure points: a world event with no agent choice.

The Phase-2 invariant is that the agent-visible A/B histories are identical
EXCEPT for order. That can only hold by construction if the event points carry no
choice at all; otherwise a live model choosing differently in A than in B makes
the histories differ in CONTENT (runner.py records action_id/action_label).

The resolution narrows the domain of the ">= 2 actions" invariant instead of
weakening it: a point is either a `decision` (>= 2 actions, audit 000886
untouched) or an `exposure` (exactly 1 action, and therefore not a decision).
These tests pin both halves and the mutual exclusion between them.
"""
from __future__ import annotations

import pytest

from coliseum.textlab.schema import (POINT_KINDS, BEHAVIORAL_CONFIG_SCHEMA_VERSION,
                                     DecisionPoint, SchemaError,
                                     build_behavioral_config, config_hash)
from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.training.actions import (LegalActionSet,
                                               legal_action_set_for_point)


# ------------------------------------------------------------------ the kinds
def test_point_kinds_are_exactly_decision_and_exposure():
    assert POINT_KINDS == ("decision", "exposure")


def test_default_kind_is_decision_and_two_action_point_is_unchanged():
    dp = DecisionPoint(dp_id="dp1", available_actions=["execute", "refuse"])
    assert dp.kind == "decision"
    assert not dp.is_exposure()
    # an explicit "decision" must be indistinguishable from the default
    explicit = DecisionPoint(dp_id="dp1", available_actions=["execute", "refuse"],
                             kind="decision")
    assert dp == explicit


def test_decision_point_with_one_action_is_still_rejected():
    # audit 000886, undiminished: a decision needs a real choice.
    with pytest.raises(SchemaError, match="a decision needs >=2 actions"):
        DecisionPoint(dp_id="dp1", available_actions=["only"])
    with pytest.raises(SchemaError, match="a decision needs >=2 actions"):
        DecisionPoint(dp_id="dp1", available_actions=[])
    with pytest.raises(SchemaError, match="a decision needs >=2 actions"):
        DecisionPoint(dp_id="dp1", available_actions=["only"], kind="decision")


def test_exposure_point_with_exactly_one_action_is_accepted():
    dp = DecisionPoint(dp_id="ev1", available_actions=["acknowledge"], kind="exposure")
    assert dp.is_exposure()
    assert dp.available_actions == ["acknowledge"]


@pytest.mark.parametrize("actions", [
    ["acknowledge", "reflect"], ["a", "b", "c"], [],
])
def test_exposure_point_must_have_exactly_one_action(actions):
    # not a loophole: a point offering a choice IS a decision, and an empty point
    # is neither. The two kinds partition; they do not overlap.
    with pytest.raises(SchemaError, match="exactly 1 action"):
        DecisionPoint(dp_id="ev1", available_actions=actions, kind="exposure")


def test_unknown_kind_fails_closed():
    for bad in ("event", "", None, "Decision"):
        with pytest.raises(SchemaError, match="unknown point kind"):
            DecisionPoint(dp_id="dp1", available_actions=["a", "b"], kind=bad)


def test_pressure_validation_still_applies_to_exposure_points():
    with pytest.raises(SchemaError):
        DecisionPoint(dp_id="ev1", available_actions=["ack"], kind="exposure",
                      risk_level=9)


# --------------------------------------------------- LegalActionSet export seam
def test_exposure_points_are_excluded_from_legal_action_set_export():
    assert legal_action_set_for_point(["acknowledge"], kind="exposure") is None


def test_decision_export_still_builds_a_legal_action_set():
    las = legal_action_set_for_point(["execute", "refuse", "stall"])
    assert isinstance(las, LegalActionSet)
    # identical to the direct construction — the seam adds no new identity
    assert las.id == LegalActionSet(["execute", "refuse", "stall"]).id
    masked = legal_action_set_for_point(["execute", "refuse"], mask=[True, False])
    assert masked.is_legal("execute") and not masked.is_legal("refuse")


def test_decision_singleton_universe_is_still_rejected_by_the_export_seam():
    # audit 000886 through the seam: the escape hatch is exclusion, never a
    # degenerate one-action universe.
    with pytest.raises(ContentRecordError):
        legal_action_set_for_point(["only_action"])
    with pytest.raises(ContentRecordError):
        legal_action_set_for_point(["only_action"], kind="decision")


def test_legal_action_set_itself_still_rejects_singletons():
    with pytest.raises(ContentRecordError):
        LegalActionSet(["only_action"])


def test_export_seam_rejects_an_exposure_point_that_offers_a_choice():
    with pytest.raises(ContentRecordError, match="exactly 1 action"):
        legal_action_set_for_point(["acknowledge", "reflect"], kind="exposure")
    with pytest.raises(ContentRecordError, match="unknown point kind"):
        legal_action_set_for_point(["a", "b"], kind="event")


# ------------------------------------------------------------------- lineage
def test_behavioral_config_output_unchanged_for_an_existing_config():
    """Regression: nothing this slice added may move a run's lineage hash.

    The expected dict + hash below are literals, so a future change to
    build_behavioral_config's shape fails here rather than silently re-keying
    every existing regime.
    """
    agent_spec = {"agent_id": "scripted:obedient", "kind": "scripted",
                  "model": "", "persona_id": "obedient"}
    cfg = build_behavioral_config(
        scenario_id="scramble_dev", scenario_hash="a" * 64, agent_spec=agent_spec,
        arbitration="planner_priority", arbitration_version="1",
        sampling={"mode": "deterministic", "temperature": 0})
    assert cfg == {
        "regime_schema_version": "1",
        "behavioral_config_schema_version": "2",
        "interaction": {"mode": "independent_vignettes"},
        "runner": {"behavioral_version": "1"},
        "scenario": {"scenario_id": "scramble_dev", "scenario_hash": "a" * 64},
        "agent": agent_spec,
        "decoding": {"sampling_mode": "deterministic", "temperature": 0},
        "arbitration": {"rule": "planner_priority", "version": "1"},
    }
    assert config_hash(cfg) == (
        "8638e76c4bcd76fe3acca2b634a9d9437371d98baa432bec7869fae794578c59")


def test_behavioral_config_schema_version_did_not_move():
    assert BEHAVIORAL_CONFIG_SCHEMA_VERSION == "2"
