"""Tests for the decision-admissibility predicate.

The load-bearing test is `test_real_scripted_run_censuses_clean`: it runs the census
over actual committed Phase-1 evidence and requires zero non-decisions. If a change to
the predicate ever starts charging non-decisions against scripted runs, Phase-1 results
stop regenerating and that test is the tripwire.
"""
from __future__ import annotations

import os

import pytest

from coliseum.textlab.admissibility import (DECISION_ADMISSIBILITY_VERSION,
                                            decision_admissibility,
                                            is_admissible_decision,
                                            load_decision_nodes,
                                            run_decision_census,
                                            strictly_admissible)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A real, committed scripted Phase-1 run. Legacy shape: no `arbitration_winner`,
# no `meta` on either pass — exactly the shape that must census clean.
SCRIPTED_RUN = os.path.join(
    REPO, "reports", "session-2026-07-10-1", "run_logs",
    "corrupt_king.v0_province.scripted-obedient.s42.1967cfa3")

# A real, committed live-LLM run: legacy shape, but WITH parse metadata.
LLM_RUN = os.path.join(
    REPO, "reports", "session-2026-07-10-3", "run_logs",
    "corrupt_king.v0_province.llm-ollama-llama3.1-latest.s42.75383fed")


def _choice(action_id, *, meta=None):
    c = {"action_id": action_id, "confidence": 0.9,
         "reasoning_summary": "because", "reward_expected": 1.0}
    if meta is not None:
        c["meta"] = meta
    return c


def _ok_meta(**kw):
    m = {"parse_status": "ok", "fallback": False, "backend": "ollama"}
    m.update(kw)
    return m


def _fallback_meta():
    return {"parse_status": "invalid_json", "fallback": False,
            "valid": False, "failure_kind": "invalid_json"}


# --- primary path ---------------------------------------------------------

def test_recorded_fallback_winner_is_non_admissible_on_first_class_evidence():
    node = {"arbitration_winner": "fallback", "final_action": "execute",
            "reflex_choice": _choice("execute", meta={"fallback": True,
                                                      "parse_status": "invalid_json"}),
            "planner_choice": _choice("execute", meta={"fallback": True,
                                                       "parse_status": "invalid_json"})}
    v = decision_admissibility(node)
    assert v["admissible"] is False
    assert v["evidence"] == "arbitration_winner"
    assert v["reason"] == "parse_fallback_winner"


@pytest.mark.parametrize("winner", ["reflex", "planner"])
def test_recorded_pass_winner_is_admissible(winner):
    node = {"arbitration_winner": winner, "final_action": "execute",
            "reflex_choice": _choice("execute", meta=_ok_meta()),
            "planner_choice": _choice("execute", meta=_ok_meta())}
    v = decision_admissibility(node)
    assert v == {"admissible": True, "reason": "ok", "evidence": "arbitration_winner"}


# --- legacy read-compat ---------------------------------------------------

def test_legacy_node_with_fallback_meta_is_distinguishable_from_first_class():
    """No `arbitration_winner`; the winning pass carries fallback: True. Must be
    non-admissible AND tagged as inferred, never claimed as recorded evidence."""
    node = {"final_action": "execute",
            "reflex_choice": _choice("execute", meta={"fallback": True,
                                                      "parse_status": "invalid_json"}),
            "planner_choice": _choice("refuse", meta=_ok_meta())}
    v = decision_admissibility(node)
    assert v["admissible"] is False
    assert v["evidence"] == "legacy_pass_inference"
    assert v["reason"] == "legacy_inferred_fallback"


def test_legacy_clean_node_is_admissible_but_still_tagged_as_inferred():
    node = {"final_action": "refuse",
            "reflex_choice": _choice("execute", meta=_ok_meta()),
            "planner_choice": _choice("refuse", meta=_ok_meta())}
    v = decision_admissibility(node)
    assert v == {"admissible": True, "reason": "ok",
                 "evidence": "legacy_pass_inference"}


def test_legacy_inference_matches_metrics_node_valid():
    """Conformance, not reinvention: agree with the already-audited private helper."""
    from coliseum.textlab import metrics
    for run in (SCRIPTED_RUN, LLM_RUN):
        for node in load_decision_nodes(run):
            assert is_admissible_decision(node) is metrics._node_valid(node)


# --- scripted runs --------------------------------------------------------

def test_scripted_node_without_parse_metadata_is_admissible():
    """No parser ran, so no parse failure is possible. A missing key must never
    default to failure."""
    node = {"final_action": "execute",
            "reflex_choice": _choice("execute"),
            "planner_choice": _choice("execute")}
    v = decision_admissibility(node)
    assert v["admissible"] is True
    assert v["reason"] == "ok"
    assert v["evidence"] == "no_parse_metadata"


def test_real_scripted_run_censuses_clean():
    """Phase-1 evidence must regenerate unchanged: zero non-decisions, no reasons."""
    nodes = load_decision_nodes(SCRIPTED_RUN)
    assert nodes, "expected committed scripted evidence at %s" % SCRIPTED_RUN
    census = run_decision_census(nodes)
    assert census["n_non_decision"] == 0
    assert census["reasons"] == {}
    assert census["n_admissible"] == census["n_total"] == len(nodes)
    assert census["non_decision_rate"] == 0.0
    assert census["admissibility_version"] == DECISION_ADMISSIBILITY_VERSION


def test_real_llm_run_is_analyzable_without_re_running():
    """The whole point of the derivability constraint: historical live evidence
    censuses off already-recorded fields alone."""
    census = run_decision_census(load_decision_nodes(LLM_RUN))
    assert census["n_total"] > 0
    assert census["n_admissible"] + census["n_non_decision"] == census["n_total"]


# --- strictness -----------------------------------------------------------

def test_strictly_admissible_is_stricter_than_admissible():
    """Reflex garbled, planner clean, planner won: a genuine decision (admissible)
    but not a clean two-pass observation (not strictly admissible)."""
    node = {"arbitration_winner": "planner", "final_action": "refuse",
            "reflex_choice": _choice("execute", meta=_fallback_meta()),
            "planner_choice": _choice("refuse", meta=_ok_meta())}
    assert is_admissible_decision(node) is True
    assert strictly_admissible(node) is False


def test_strictly_admissible_true_when_both_passes_parse():
    node = {"arbitration_winner": "planner", "final_action": "refuse",
            "reflex_choice": _choice("execute", meta=_ok_meta()),
            "planner_choice": _choice("refuse", meta=_ok_meta())}
    assert strictly_admissible(node) is True


def test_strictly_admissible_never_admits_a_non_decision():
    node = {"arbitration_winner": "fallback", "final_action": "execute",
            "reflex_choice": _choice("execute", meta=_ok_meta()),
            "planner_choice": _choice("execute", meta=_ok_meta())}
    assert strictly_admissible(node) is False


def test_scripted_nodes_are_strictly_admissible():
    for node in load_decision_nodes(SCRIPTED_RUN):
        assert strictly_admissible(node) is True


# --- heuristics that must NOT be used -------------------------------------

def test_zero_confidence_alone_does_not_make_a_node_inadmissible():
    """confidence 0.0 correlates with the fallback path but is not a fact about
    it — a model may genuinely answer with zero confidence."""
    node = {"arbitration_winner": "reflex", "final_action": "execute",
            "reflex_choice": {"action_id": "execute", "confidence": 0.0,
                              "reasoning_summary": "parse failure fallback",
                              "reward_expected": 0.0, "meta": _ok_meta()},
            "planner_choice": _choice("execute", meta=_ok_meta())}
    assert is_admissible_decision(node) is True


# --- replay parity --------------------------------------------------------

def test_replay_needs_no_special_case():
    """Replay drives the same LLMAgent._pass and re-derives identical meta and
    arbitration_winner, so an identically-shaped node must classify identically.
    A divergence here would mean a replay-specific branch had crept in."""
    live = {"arbitration_winner": "fallback", "final_action": "execute",
            "reflex_choice": _choice("execute", meta=_fallback_meta()),
            "planner_choice": _choice("execute", meta=_fallback_meta())}
    replay = dict(live)  # replay adds no admissibility-relevant field
    assert decision_admissibility(replay) == decision_admissibility(live)


# --- totality -------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    {},                                        # empty
    None,                                      # not a dict
    [],                                        # not a dict
    "decision",                                # not a dict
    {"final_action": "execute"},               # no passes
    {"final_action": "execute", "reflex_choice": _choice("execute")},  # one pass
    {"final_action": None, "reflex_choice": _choice("x"),
     "planner_choice": _choice("x")},          # unusable final_action
    {"reflex_choice": "garbled", "planner_choice": "garbled",
     "final_action": "execute"},               # passes not dicts
    {"arbitration_winner": 7},                 # field present, unreadable
])
def test_malformed_nodes_are_non_admissible_and_never_raise(bad):
    v = decision_admissibility(bad)
    assert v["admissible"] is False
    assert v["reason"] == "unreadable_node"
    assert strictly_admissible(bad) is False
    assert is_admissible_decision(bad) is False


# --- census arithmetic ----------------------------------------------------

def test_census_counts_are_closed():
    nodes = [
        {"arbitration_winner": "reflex", "final_action": "execute",
         "reflex_choice": _choice("execute", meta=_ok_meta()),
         "planner_choice": _choice("execute", meta=_ok_meta())},
        {"arbitration_winner": "fallback", "final_action": "execute",
         "reflex_choice": _choice("execute", meta=_fallback_meta()),
         "planner_choice": _choice("execute", meta=_fallback_meta())},
        {"final_action": "execute",
         "reflex_choice": _choice("execute", meta={"fallback": True}),
         "planner_choice": _choice("refuse", meta=_ok_meta())},
        {},
        {"final_action": "execute", "reflex_choice": _choice("execute"),
         "planner_choice": _choice("execute")},
    ]
    c = run_decision_census(nodes)
    assert c["n_total"] == 5
    assert c["n_admissible"] + c["n_non_decision"] == c["n_total"]
    assert sum(c["reasons"].values()) == c["n_non_decision"] == 3
    assert c["reasons"] == {"parse_fallback_winner": 1,
                            "legacy_inferred_fallback": 1,
                            "unreadable_node": 1}
    assert c["n_admissible"] == 2
    assert c["non_decision_rate"] == 0.6


def test_empty_census_reports_no_rate_rather_than_a_clean_one():
    c = run_decision_census([])
    assert c["n_total"] == 0
    assert c["non_decision_rate"] is None
    assert c["reasons"] == {}
