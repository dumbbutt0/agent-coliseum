"""m8 Phase-2 triplet — the history is IMPOSED, not authored.

Phase 1 (`scramble_dev/perm/sham`) let each event decision point offer two
actions. Both write the identical state_delta, narrative, and successor, so the
WORLD effect is choice-independent — but the runner appends the chosen
`action_id` and `action_label` to the agent-visible history. Under the scripted
deterministic deciders Phase 1 calibrated with, the realized path is a function
of the events, so A and B histories differ only by order. Under a LIVE model it
may acknowledge the betrayal in A and reflect on it in B, and the terminal
prompts then differ in CONTENT — which silently voids "matched except order".

The Phase-2 triplet closes that by making every event point a `kind: exposure`
carrying exactly one action, leaving the terminal probe as the only free choice
(which is also the only measured outcome). See
docs/first-gladiator/preregistrations/m8-phase2-live-order-sensitivity.md,
"Design decision: the history is imposed, not authored".

These tests pin BOTH directions: the new check accepts the m8 triplet, and it
REJECTS the Phase-1 triplet — a check that cannot fail on the known-defective
input proves nothing. Phase 1 must simultaneously keep passing in the default
mode, since its two-action event points are legitimate for scripted deciders.
"""
import os

import pytest

from coliseum.textlab.scenario import (experience_multiset, experience_sequence,
                                       imposed_history_issues, lint_registry,
                                       lint_scramble_triplet, load_scenario,
                                       load_registry)
from coliseum.textlab.schema import SchemaError

SCEN_DIR = os.path.join(os.path.dirname(__file__), "..", "configs", "scenarios")
REGISTRY = os.path.join(SCEN_DIR, "..", "registry", "scenarios.yaml")

M8_PATHS = {
    "A": os.path.join(SCEN_DIR, "scramble_dev_m8.yaml"),
    "B": os.path.join(SCEN_DIR, "scramble_perm_m8.yaml"),
    "C": os.path.join(SCEN_DIR, "scramble_sham_m8.yaml"),
}
P1_PATHS = {
    "A": os.path.join(SCEN_DIR, "scramble_dev.yaml"),
    "B": os.path.join(SCEN_DIR, "scramble_perm.yaml"),
    "C": os.path.join(SCEN_DIR, "scramble_sham.yaml"),
}
M8_IDS = {"A": "scramble_dev_m8", "B": "scramble_perm_m8", "C": "scramble_sham_m8"}
EVENT_DPS = ("e_trust", "e_betrayal", "e_warning")
PROBE = "d_partner"


@pytest.fixture(scope="module")
def m8():
    return {k: load_scenario(p) for k, p in M8_PATHS.items()}


@pytest.fixture(scope="module")
def phase1():
    return {k: load_scenario(p) for k, p in P1_PATHS.items()}


# ------------------------------------------------------- the triplet itself

def test_m8_triplet_loads_with_expected_ids(m8):
    for key, sid in M8_IDS.items():
        assert m8[key].scenario_id == sid


def test_m8_triplet_passes_lint_with_imposed_history_enabled(m8):
    issues = lint_scramble_triplet(m8["A"], m8["B"], m8["C"], REGISTRY,
                                   imposed_history=True)
    assert issues == [], issues


def test_m8_event_points_are_single_action_exposures(m8):
    for key, s in m8.items():
        by_id = {dp.dp_id: dp for dp in s.decision_points}
        for dp_id in EVENT_DPS:
            dp = by_id[dp_id]
            assert dp.kind == "exposure", f"{key}.{dp_id} kind={dp.kind!r}"
            assert dp.is_exposure()
            assert len(dp.available_actions) == 1, \
                f"{key}.{dp_id} has {dp.available_actions}"


def test_m8_terminal_probe_keeps_four_actions_and_stays_a_decision(m8):
    for key, s in m8.items():
        by_id = {dp.dp_id: dp for dp in s.decision_points}
        probe = by_id[PROBE]
        assert probe.kind == "decision"
        assert len(probe.available_actions) == 4, \
            f"{key}.{PROBE} has {probe.available_actions}"


def test_m8_outcome_rules_have_no_orphans_and_no_gaps(m8):
    """Every (dp, available action) pair has a rule and every rule is
    reachable — pruning the second event action must not leave either a
    dangling `e_*/reflect` rule or a missing one."""
    for key, s in m8.items():
        want = {f"{dp.dp_id}/{aid}" for dp in s.decision_points
                for aid in dp.available_actions}
        assert set(s.outcome_rules) == want, \
            f"{key}: {set(s.outcome_rules) ^ want}"


def test_m8_no_action_is_defined_but_unreachable(m8):
    """The pruned `reflect` action is gone from the action table too — a
    defined-but-unofferable action is dead surface an auditor must reason
    about."""
    for key, s in m8.items():
        offered = {aid for dp in s.decision_points for aid in dp.available_actions}
        assert set(s.actions) == offered, f"{key}: {set(s.actions) ^ offered}"


# --------------------------------------------- matched-except-order content

def test_m8_experience_multiset_identical_across_conditions(m8):
    ms = {k: experience_multiset(s) for k, s in m8.items()}
    assert ms["A"] == ms["B"] == ms["C"], ms
    assert ms["A"] == {("trust", 2): 1, ("betrayal", -3): 1, ("warning", -1): 1}


def test_m8_b_is_genuinely_permuted_not_reordered_content(m8):
    seq_a, seq_b = experience_sequence(m8["A"]), experience_sequence(m8["B"])
    assert seq_a != seq_b, "B delivers A's order — not a permutation"
    assert sorted(seq_a) == sorted(seq_b)
    assert seq_a == [("trust", 2), ("betrayal", -3), ("warning", -1)]
    assert seq_b == [("betrayal", -3), ("warning", -1), ("trust", 2)]


def test_m8_c_is_behaviorally_identical_to_a_but_worded_differently(m8):
    a, c = m8["A"], m8["C"]
    assert experience_sequence(a) == experience_sequence(c)
    for key in ("initial_state", "actions", "decision_points", "outcome_rules"):
        assert a.raw.get(key) == c.raw.get(key), f"C differs in {key!r}"
    a_text = [(v.get("intro", ""), v.get("decision_texts")) for v in a.variants]
    c_text = [(v.get("intro", ""), v.get("decision_texts")) for v in c.variants]
    assert a_text != c_text, "sham must actually change the surface form"


def test_m8_twin_links_point_at_the_m8_primary(m8):
    assert m8["A"].control_of == ""
    assert m8["B"].control_of == "scramble_dev_m8"
    assert m8["C"].control_of == "scramble_dev_m8"


# ------------------------------------------- the check detects the defect

def test_phase1_triplet_fails_the_imposed_history_check_when_enabled(phase1):
    """The load-bearing negative. Phase 1's two-action event points are the
    exact defect the m8 design removes, so enabling the check MUST flag them
    — otherwise the check is decorative and the m8 pass above is vacuous."""
    issues = lint_scramble_triplet(phase1["A"], phase1["B"], phase1["C"],
                                   REGISTRY, imposed_history=True)
    assert issues, "imposed-history check did not detect Phase-1's authored history"
    for sid in ("scramble_dev", "scramble_perm", "scramble_sham"):
        for dp_id in EVENT_DPS:
            assert any(f"{sid}.{dp_id}" in i for i in issues), \
                f"no issue raised for {sid}.{dp_id}"


def test_phase1_event_points_are_flagged_per_scenario(phase1):
    for key, s in phase1.items():
        issues = imposed_history_issues(s)
        # three event points, each flagged for kind AND for cardinality
        assert len(issues) == 6, f"{key}: {issues}"
        assert all("d_partner" not in i for i in issues), \
            "the terminal probe is a legitimate decision and must not be flagged"


def test_phase1_still_passes_lint_in_default_mode(phase1):
    """No regression: the default call is byte-for-byte the Phase-1 contract,
    whose audited GO verdicts are bound to it."""
    assert lint_scramble_triplet(phase1["A"], phase1["B"], phase1["C"],
                                 REGISTRY) == []


def test_imposed_history_defaults_to_off(phase1):
    """The gate is opt-in — an explicit False and the default must agree."""
    assert lint_scramble_triplet(phase1["A"], phase1["B"], phase1["C"],
                                 REGISTRY, imposed_history=False) == \
        lint_scramble_triplet(phase1["A"], phase1["B"], phase1["C"], REGISTRY)


def test_imposed_history_only_adds_issues_never_removes(m8, phase1):
    """Enabling the flag must never mask an existing failure."""
    for trip in (m8, phase1):
        base = lint_scramble_triplet(trip["A"], trip["B"], trip["C"], REGISTRY)
        strict = lint_scramble_triplet(trip["A"], trip["B"], trip["C"],
                                       REGISTRY, imposed_history=True)
        assert set(base).issubset(set(strict))


def test_imposed_history_rejects_an_imposed_terminal_probe(m8):
    """An imposed terminal probe measures nothing. Guard against a naive
    reading of the rule ("all points single-action") that would accept it."""
    raw = dict(m8["A"].raw)
    dps = [dict(dp) for dp in raw["decision_points"]]
    for dp in dps:
        if dp["dp_id"] == PROBE:
            dp["available_actions"] = ["share_resource"]
            dp["kind"] = "exposure"
    raw = {**raw, "decision_points": dps}
    from coliseum.textlab.scenario import build_scenario
    s = build_scenario(raw, "all_exposure")
    issues = imposed_history_issues(s)
    assert any("must remain a free choice" in i and PROBE in i
               for i in issues), issues
    # and the event points on their own are still clean, so the probe is the
    # sole reason this scenario is rejected
    assert all(PROBE in i for i in issues), issues


# ------------------------------------------------------------ registry

def test_m8_entries_are_registered_with_correct_behavioral_hashes(m8):
    registered = {e["scenario_id"]: e
                  for e in load_registry(REGISTRY)["scenarios"]}
    for key, sid in M8_IDS.items():
        assert sid in registered, f"{sid} not registered"
        entry = registered[sid]
        assert entry["behavioral_hash"] == m8[key].behavioral_hash(), \
            f"{sid}: registry hash != loaded scenario hash"
        assert entry["family"] == "memory_persistence"
        assert entry["status"] == "draft"
        assert entry["variants"] == [v["variant_id"] for v in m8[key].variants]


def test_m8_registry_twin_links_mirror_the_phase1_shape():
    registered = {e["scenario_id"]: e
                  for e in load_registry(REGISTRY)["scenarios"]}
    assert registered["scramble_dev_m8"]["control_of"] is None
    assert registered["scramble_dev_m8"]["controls"] == \
        ["scramble_perm_m8", "scramble_sham_m8"]
    for sid in ("scramble_perm_m8", "scramble_sham_m8"):
        assert registered[sid]["control_of"] == "scramble_dev_m8"
        assert registered[sid]["controls"] == []


def test_m8_behavioral_hashes_differ_from_phase1(m8, phase1):
    """Separate identities: Phase-1 evidence must keep regenerating against
    unchanged artifacts."""
    m8_hashes = {s.behavioral_hash() for s in m8.values()}
    p1_hashes = {s.behavioral_hash() for s in phase1.values()}
    assert len(m8_hashes) == 3
    assert not (m8_hashes & p1_hashes)


def test_registry_completeness_still_clean():
    """Adding three scenario files must not leave any file unregistered."""
    assert lint_registry(REGISTRY, SCEN_DIR) == []
