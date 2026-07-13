"""P1-S4 prerequisite — run.json -> BehaviorPolicySpec with canonical id cross-check.

Adversarial: forged ids, swapped ids, configuration drift, and legacy (pre-regime)
runs are all refused; a genuine modern run projects to a BehaviorPolicySpec whose
regime ids match. Regime ids are re-derived from behavioral_config via the pure
canonical builder (schema.regime_hashes), never fabricated or config_hash-substituted.
"""
from __future__ import annotations

import copy

import pytest

from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.schema import build_behavioral_config, regime_hashes
from coliseum.textlab.training.run_projection import (is_modern_run,
                                                      project_behavior_policy_spec)

_AGENT_SPEC = {"kind": "scripted", "agent_id": "scripted:merciful",
               "constitution": "", "persona": "merciful",
               "persona_role": "deference"}


def _modern_run(**over):
    bc = build_behavioral_config(
        "corrupt_king", "s" * 64, _AGENT_SPEC, "planner_priority", "2",
        {"mode": "deterministic", "temperature": 0})
    cmp_id, agt_id = regime_hashes(bc)
    run = {"schema_version": "0.1", "run_id": "corrupt_king.v0.scripted-merciful.s2",
           "behavioral_config": bc, "comparison_regime_id": cmp_id,
           "agent_regime_id": agt_id}
    run.update(over)
    return run


# --------------------------------------------------------------- happy path
def test_modern_run_projects_with_matching_ids():
    run = _modern_run()
    bps = project_behavior_policy_spec(run)
    c = bps.content
    assert c["comparison_regime_id"] == run["comparison_regime_id"]
    assert c["agent_regime_id"] == run["agent_regime_id"]
    assert c["behavioral_config"] == run["behavioral_config"]
    # absent policy info stays explicit-unavailable (no fabrication)
    assert c["tokenizer_identity"] == {"status": "unavailable"}
    assert c["action_score"] == {"status": "unavailable"}
    assert c["memory_state_ref"] == {"status": "unavailable"}
    assert c["exploration_mechanism"] == "deterministic"
    assert is_modern_run(run)


# --------------------------------------------------------------- adversarial
def test_forged_comparison_id_rejected():
    with pytest.raises(ContentRecordError):
        project_behavior_policy_spec(_modern_run(comparison_regime_id="0" * 64))


def test_swapped_ids_rejected():
    run = _modern_run()
    run["comparison_regime_id"], run["agent_regime_id"] = (
        run["agent_regime_id"], run["comparison_regime_id"])
    with pytest.raises(ContentRecordError):
        project_behavior_policy_spec(run)


def test_configuration_drift_rejected():
    # mutate behavioral_config AFTER the ids were computed -> re-derivation mismatch
    run = _modern_run()
    drifted = copy.deepcopy(run)
    drifted["behavioral_config"]["arbitration"]["rule"] = "reflex_priority"
    with pytest.raises(ContentRecordError):
        project_behavior_policy_spec(drifted)


def test_legacy_run_refused_never_fabricated():
    legacy = {"schema_version": "0.1", "run_id": "old.scripted.s2",
              "agent_id": "scripted:obedient", "config_hash": "c" * 64,
              "arbitration": "planner_priority", "status": "completed"}
    assert not is_modern_run(legacy)
    with pytest.raises(ContentRecordError):
        project_behavior_policy_spec(legacy)


def test_partial_modern_run_refused():
    # behavioral_config present but a regime id missing -> not modern, refused
    run = _modern_run()
    del run["agent_regime_id"]
    assert not is_modern_run(run)
    with pytest.raises(ContentRecordError):
        project_behavior_policy_spec(run)
    with pytest.raises(ContentRecordError):
        project_behavior_policy_spec("not a dict")
