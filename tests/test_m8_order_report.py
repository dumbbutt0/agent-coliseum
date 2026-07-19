"""m8 Phase-2 order-sensitivity report — the distributional successor's tests.

The Phase-1 gate aggregator (`scramble_terminal_distribution`) is an EXACT-EQUALITY
comparator for deterministic scripted deciders. Phase 2 points the instrument at a
stochastic live model, where four of its properties become defects:

  F8  it reads `terminal["final_action"]` unconditionally, so a parse fallback —
      which resolves to `actions[0]`, IDENTICAL in all three conditions — is scored
      as a real choice and a differential parse-failure rate fakes an order effect;
  F4  it ignores `stochastic_reportable`, so a run whose seed probe FAILED is
      silently admitted despite a docstring claiming aggregate()'s admission rule;
  F3  `cell["units"]` is keyed by effective unit, so replicates either silently
      collapse or hard-error — and replicates are exactly what Phase 2 needs;
  F1  thresholds of exactly zero against a TV quantized to {0, 0.5, 1} at n=2.

`order_sensitivity_report` is a VERSIONED SUCCESSOR: the Phase-1 function keeps its
behavior and output bytes (Phase-1 evidence and its three GO verdicts depend on it),
and the tests below prove both halves of that claim.

No live model is contacted; every fixture is a synthetic run directory.
"""
import json
import os

import pytest

from coliseum.textlab.admissibility import DECISION_ADMISSIBILITY_VERSION
from coliseum.textlab.metrics import (ORDER_REPORT_VERSION, METRICS_VERSION,
                                      order_sensitivity_report,
                                      scramble_terminal_distribution)
from coliseum.textlab.schema import SchemaError, canonical_json

CONDITIONS = {"A": "scramble_dev_m8", "B": "scramble_perm_m8", "C": "scramble_sham_m8"}
REGIME = "r" * 64
AGENT_CFG = {"driver": "ollama_local", "temperature": 0.7}


# ------------------------------------------------------------------ fixtures

def _node(final_action: str, winner: str | None = "planner", scripted: bool = False):
    """One decision_node record's `data`.

    `scripted=True` reproduces Phase-1 scripted shape: no `arbitration_winner`
    and no `meta` on either pass, i.e. no parser ran, so no parse failure is
    possible and the node must census as admissible.
    """
    if scripted:
        return {"dp_id": "d_partner", "final_action": final_action,
                "reflex_choice": {"action_id": final_action},
                "planner_choice": {"action_id": final_action},
                "moral_tags": [], "state_before": {"facts": {}}}
    return {"dp_id": "d_partner", "final_action": final_action,
            "arbitration_winner": winner,
            "reflex_choice": {"action_id": final_action, "meta": {"parse_status": "ok"}},
            "planner_choice": {"action_id": final_action, "meta": {"parse_status": "ok"}},
            "moral_tags": [], "state_before": {"facts": {}}}


def _mkrun(tmp_path, rid, scenario_id, variant, scen_seed, samp_seed, final_action,
           winner="planner", scripted=False, agent_id="live", regime=REGIME,
           agent_config=None, reportable=True, stochastic_reportable=True,
           stochastic_exclusion_reasons=None):
    d = tmp_path / rid
    d.mkdir()
    run = {
        "run_id": rid, "scenario_id": scenario_id, "agent_id": agent_id,
        "variant_id": variant, "seed": scen_seed, "scenario_seed": scen_seed,
        "sampler_seed": samp_seed, "reportable": reportable,
        "stochastic_reportable": stochastic_reportable,
        "stochastic_exclusion_reasons": stochastic_exclusion_reasons or [],
        "agent_regime_id": regime,
        "agent_config": agent_config if agent_config is not None else AGENT_CFG,
        "sampling": {"mode": "stochastic", "temperature": 0.7},
        "arbitration": "planner_priority", "interaction_mode": "sequential_history",
    }
    (d / "run.json").write_text(json.dumps(run), encoding="utf-8")
    # an earlier (exposure) node plus the TERMINAL probe — the report must read the
    # LAST node only and must never re-point at this earlier one
    lines = [
        {"kind": "decision_node", "data": _node("expose", scripted=scripted)},
        {"kind": "decision_node",
         "data": _node(final_action, winner=winner, scripted=scripted)},
    ]
    (d / "decisions.jsonl").write_text(
        "\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    return str(d)


def _build(tmp_path, plan, **kw):
    """plan: {cond_label: [(sampler_seed, action) | (sampler_seed, action, winner)]}."""
    dirs = []
    for cond, rows in sorted(plan.items()):
        for i, row in enumerate(rows):
            samp, action = row[0], row[1]
            winner = row[2] if len(row) > 2 else "planner"
            dirs.append(_mkrun(tmp_path, f"{cond}_{i}_{samp}", CONDITIONS[cond],
                               "v0", 42, samp, action, winner=winner, **kw))
    return dirs


def POLICY(**over):
    p = {"policy_version": "1", "admissibility_version": DECISION_ADMISSIBILITY_VERSION,
         "max_non_decision_rate": 0.20, "max_non_decision_rate_delta": 0.05,
         "min_admissible_effective_n": 20, "on_violation": "refuse"}
    p.update(over)
    return p


def THRESH(s1, s2, **over):
    t = {"bootstrap_iterations": 200, "bootstrap_seed": 20260719,
         "confidence": 0.95, "noise_floor_split": {"S1": list(s1), "S2": list(s2)}}
    t.update(over)
    return t


LOOSE = POLICY(min_admissible_effective_n=1, max_non_decision_rate=0.5,
               max_non_decision_rate_delta=0.5)


# ------------------------------------------------- 1. THE DEFECT REPRODUCTION

def test_parse_fallback_inflates_old_tv_and_is_excluded_by_new_report(tmp_path):
    """F8, stated as a contrast.

    One B-condition unit's terminal node has `arbitration_winner: "fallback"` and
    therefore resolved to a deterministic action rather than a choice. The OLD
    comparator scores it as a real choice and reports TV(A,B) = 1/3 — an order
    effect manufactured out of one malformed model reply. The NEW report excludes
    it (non_decision_n == 1) and reports the honest distance, 0.0.
    """
    dirs = _build(tmp_path, {
        "A": [(1, "share"), (2, "share"), (3, "share")],
        # unit 2 of B is a fallback: the parser failed and the runner substituted
        "B": [(1, "share"), (2, "share"), (3, "verify", "fallback")],
        "C": [(1, "share"), (2, "share"), (3, "share")],
    })

    old = scramble_terminal_distribution(dirs, CONDITIONS)["per_agent"]["live"]
    assert old["tv_distances"]["A|B"] == pytest.approx(1 / 3)
    assert old["distributions"]["B"] == {"share": pytest.approx(2 / 3),
                                         "verify": pytest.approx(1 / 3)}
    assert old["effective_n"]["B"] == 3          # the fallback counted as evidence

    new = order_sensitivity_report(dirs, CONDITIONS,
                                   admissibility_policy=LOOSE,
                                   thresholds=THRESH([1], [2, 3]))["per_agent"]["live"]
    b = new["cells"]["B"]
    assert b["non_decision_n"] == 1
    assert b["non_decision_reasons"] == {"parse_fallback_winner": 1}
    assert b["distribution"] == {"share": 1.0}   # the artifact contributes NOTHING
    assert b["admissible_effective_n"] == 2
    assert new["tv_distances"]["A|B"] == 0.0     # the honest distance
    assert new["verdict"] == "no_order_effect_observed"


def test_non_admissible_terminal_is_never_repointed_at_an_earlier_decision(tmp_path):
    """The terminal probe is the LAST node, full stop. Substituting the earlier
    (admissible) node would be a second fabrication on top of the first."""
    dirs = _build(tmp_path, {
        "A": [(1, "share"), (2, "share")],
        "B": [(1, "share"), (2, "verify", "fallback")],
        "C": [(1, "share"), (2, "share")],
    })
    rep = order_sensitivity_report(dirs, CONDITIONS, admissibility_policy=LOOSE,
                                   thresholds=THRESH([1], [2]))
    b = rep["per_agent"]["live"]["cells"]["B"]
    # "expose" is the earlier node's action; it must appear nowhere
    assert "expose" not in b["distribution"] and "expose" not in b["counts"]
    assert b["admissible_draw_n"] == 1 and b["non_decision_n"] == 1


# --------------------------------------------- 2. declared bounds are mandatory

def test_policy_and_thresholds_are_mandatory_keyword_arguments(tmp_path):
    dirs = _build(tmp_path, {"A": [(1, "share")], "B": [(1, "share")],
                             "C": [(1, "share")]})
    with pytest.raises(TypeError):
        order_sensitivity_report(dirs, CONDITIONS)
    with pytest.raises(TypeError):
        order_sensitivity_report(dirs, CONDITIONS, admissibility_policy=LOOSE)
    with pytest.raises(TypeError):
        order_sensitivity_report(dirs, CONDITIONS, thresholds=THRESH([1], [1]))


def test_admissibility_version_mismatch_is_refused(tmp_path):
    """A v2 predicate must not retroactively reinterpret a frozen v1 experiment."""
    dirs = _build(tmp_path, {"A": [(1, "share")], "B": [(1, "share")],
                             "C": [(1, "share")]})
    with pytest.raises(SchemaError) as exc:
        order_sensitivity_report(dirs, CONDITIONS,
                                 admissibility_policy=POLICY(admissibility_version="0"),
                                 thresholds=THRESH([1], [1]))
    assert "admissibility_version" in str(exc.value)


def test_missing_policy_keys_and_non_refuse_mode_are_refused(tmp_path):
    dirs = _build(tmp_path, {"A": [(1, "share")], "B": [(1, "share")],
                             "C": [(1, "share")]})
    bad = POLICY()
    del bad["max_non_decision_rate_delta"]
    with pytest.raises(SchemaError):
        order_sensitivity_report(dirs, CONDITIONS, admissibility_policy=bad,
                                 thresholds=THRESH([1], [1]))
    with pytest.raises(SchemaError):
        order_sensitivity_report(dirs, CONDITIONS,
                                 admissibility_policy=POLICY(on_violation="warn"),
                                 thresholds=THRESH([1], [1]))


def test_overlapping_noise_floor_halves_are_refused(tmp_path):
    dirs = _build(tmp_path, {"A": [(1, "share")], "B": [(1, "share")],
                             "C": [(1, "share")]})
    with pytest.raises(SchemaError) as exc:
        order_sensitivity_report(dirs, CONDITIONS, admissibility_policy=LOOSE,
                                 thresholds=THRESH([1, 2], [2, 3]))
    assert "overlap" in str(exc.value)


# ------------------------------------------------------------- 3. refusal path

def _differential_fallback_dirs(tmp_path):
    """A clean; B with a 20 % terminal parse-failure rate — the exact confound the
    delta bound exists to catch."""
    a = [(s, "share") for s in range(1, 11)]
    b = [(s, "share") for s in range(1, 9)] + \
        [(9, "verify", "fallback"), (10, "verify", "fallback")]
    c = [(s, "share") for s in range(1, 11)]
    return _build(tmp_path, {"A": a, "B": b, "C": c})


def test_refuses_on_differential_non_decision_rate_and_emits_no_distance(tmp_path):
    dirs = _differential_fallback_dirs(tmp_path)
    policy = POLICY(min_admissible_effective_n=1)     # only the delta bound bites
    with pytest.raises(SchemaError) as exc:
        order_sensitivity_report(dirs, CONDITIONS, admissibility_policy=policy,
                                 thresholds=THRESH(range(1, 6), range(6, 11)))
    msg = str(exc.value)
    assert "A-vs-B" in msg                       # the offending compared pair
    assert "0.2" in msg                          # its rate
    assert "max_non_decision_rate_delta=0.05" in msg   # the bound
    assert "'1'" in msg                          # the policy version

    body = exc.value.report                      # the census escapes; numbers do not
    assert body["per_agent"]["live"]["cells"]["B"]["non_decision_n"] == 2
    assert body["per_agent"]["live"]["cells"]["B"]["non_decision_rate"] == 0.2
    for agent in body["per_agent"].values():
        assert "tv_distances" not in agent
        assert "bootstrap" not in agent
        assert "verdict" not in agent
    assert "tv_distances" not in canonical_json(body)


def test_refuses_when_a_cell_is_below_the_effective_n_floor(tmp_path):
    dirs = _build(tmp_path, {
        "A": [(s, "share") for s in range(1, 5)],
        "B": [(s, "share") for s in range(1, 5)],
        "C": [(1, "share")],                     # only one unit
    })
    with pytest.raises(SchemaError) as exc:
        order_sensitivity_report(dirs, CONDITIONS,
                                 admissibility_policy=POLICY(min_admissible_effective_n=4),
                                 thresholds=THRESH([1, 2], [3, 4]))
    assert "live|C" in str(exc.value)
    assert "min_admissible_effective_n=4" in str(exc.value)


def test_refuses_when_a_cell_has_zero_admissible_units(tmp_path):
    """Zero admissible evidence must REFUSE — never an empty distribution, never None."""
    dirs = _build(tmp_path, {
        "A": [(s, "share") for s in range(1, 5)],
        "B": [(s, "share") for s in range(1, 5)],
        "C": [(s, "verify", "fallback") for s in range(1, 5)],
    })
    with pytest.raises(SchemaError) as exc:
        order_sensitivity_report(dirs, CONDITIONS,
                                 admissibility_policy=POLICY(min_admissible_effective_n=1,
                                                             max_non_decision_rate=1.0,
                                                             max_non_decision_rate_delta=1.0),
                                 thresholds=THRESH([1, 2], [3, 4]))
    assert "live|C" in str(exc.value)
    assert exc.value.report["per_agent"]["live"]["cells"]["C"]["distribution"] == {}


def test_refuses_when_a_whole_condition_is_missing(tmp_path):
    dirs = _build(tmp_path, {"A": [(1, "share"), (2, "share")],
                             "B": [(1, "share"), (2, "share")]})
    with pytest.raises(SchemaError) as exc:
        order_sensitivity_report(dirs, CONDITIONS, admissibility_policy=LOOSE,
                                 thresholds=THRESH([1], [2]))
    assert "live|C" in str(exc.value)


def test_refuses_when_a_cell_exceeds_the_absolute_non_decision_rate(tmp_path):
    dirs = _build(tmp_path, {
        "A": [(1, "share"), (2, "share"), (3, "share"), (4, "share")],
        "B": [(1, "share"), (2, "verify", "fallback"),
              (3, "verify", "fallback"), (4, "verify", "fallback")],
        "C": [(1, "share"), (2, "share"), (3, "share"), (4, "share")],
    })
    with pytest.raises(SchemaError) as exc:
        order_sensitivity_report(
            dirs, CONDITIONS,
            admissibility_policy=POLICY(min_admissible_effective_n=1,
                                        max_non_decision_rate=0.20,
                                        max_non_decision_rate_delta=1.0),
            thresholds=THRESH([1, 2], [3, 4]))
    assert "max_non_decision_rate=0.2" in str(exc.value)


# ------------------------------------------------ 4. admission (F4, regime)

def test_seed_probe_failure_is_excluded_not_silently_admitted(tmp_path):
    """F4: `stochastic_reportable: false` — a backend that ignored options.seed —
    must be excluded with its recorded reason, not counted as evidence."""
    dirs = _build(tmp_path, {
        "A": [(s, "share") for s in range(1, 5)],
        "B": [(s, "share") for s in range(1, 5)],
        "C": [(s, "share") for s in range(1, 5)],
    })
    bad = _mkrun(tmp_path, "B_bad", CONDITIONS["B"], "v0", 42, 9, "verify",
                 stochastic_reportable=False,
                 stochastic_exclusion_reasons=["backend_seed_unverified"])
    rep = order_sensitivity_report(dirs + [bad], CONDITIONS,
                                   admissibility_policy=POLICY(min_admissible_effective_n=1),
                                   thresholds=THRESH([1, 2], [3, 4]))
    assert {"report_id": "B_bad", "reasons": ["backend_seed_unverified"]} in rep["excluded"]
    assert rep["per_agent"]["live"]["cells"]["B"]["distribution"] == {"share": 1.0}
    # and the OLD comparator would have admitted it — that is the defect
    old = scramble_terminal_distribution(dirs + [bad], CONDITIONS)
    assert old["per_agent"]["live"]["effective_n"]["B"] == 5


def test_non_reportable_run_is_excluded(tmp_path):
    dirs = _build(tmp_path, {"A": [(1, "share"), (2, "share")],
                             "B": [(1, "share"), (2, "share")],
                             "C": [(1, "share"), (2, "share")]})
    bad = _mkrun(tmp_path, "A_bad", CONDITIONS["A"], "v0", 42, 9, "verify",
                 reportable=False)
    rep = order_sensitivity_report(dirs + [bad], CONDITIONS,
                                   admissibility_policy=LOOSE,
                                   thresholds=THRESH([1], [2]))
    assert any(e["report_id"] == "A_bad" and "non_reportable" in e["reasons"]
               for e in rep["excluded"])


def test_mixed_decider_regimes_are_refused(tmp_path):
    dirs = _build(tmp_path, {"A": [(1, "share"), (2, "share")],
                             "C": [(1, "share"), (2, "share")]})
    dirs.append(_mkrun(tmp_path, "B_other", CONDITIONS["B"], "v0", 42, 1, "share",
                       regime="q" * 64))
    with pytest.raises(SchemaError) as exc:
        order_sensitivity_report(dirs, CONDITIONS, admissibility_policy=LOOSE,
                                 thresholds=THRESH([1], [2]))
    assert "MIXED decider regimes" in str(exc.value)


def test_regime_unbound_evidence_is_refused(tmp_path):
    dirs = [_mkrun(tmp_path, "A_0", CONDITIONS["A"], "v0", 42, 1, "share",
                   agent_config={})]
    with pytest.raises(SchemaError) as exc:
        order_sensitivity_report(dirs, CONDITIONS, admissibility_policy=LOOSE,
                                 thresholds=THRESH([1], [2]))
    assert "regime-unbound" in str(exc.value)


# ------------------------------------------------------------- 5. replicates (F3)

def test_replicates_aggregate_into_a_distribution(tmp_path):
    """F3: the old cell dict keyed by effective unit either collapsed a repeated
    unit or hard-errored on a differing draw. Live replicates are exactly what
    Phase 2 needs, so they must aggregate."""
    dirs = _build(tmp_path, {"A": [(1, "share"), (2, "share")],
                             "B": [(1, "share"), (2, "share")],
                             "C": [(1, "share"), (2, "share")]})
    # four MORE draws of A's unit (v0, 42, 1): two share, two verify
    for i, act in enumerate(["share", "share", "verify", "verify"]):
        dirs.append(_mkrun(tmp_path, f"A_rep{i}", CONDITIONS["A"], "v0", 42, 1, act))

    rep = order_sensitivity_report(dirs, CONDITIONS, admissibility_policy=LOOSE,
                                   thresholds=THRESH([1], [2]))
    a = rep["per_agent"]["live"]["cells"]["A"]
    assert a["effective_unit_n"] == 2            # units, not draws
    assert a["admissible_effective_n"] == 2
    assert a["admissible_draw_n"] == 6           # 2 originals + 4 replicates
    assert a["counts"] == {"share": 4, "verify": 2}
    assert a["distribution"] == {"share": round(4 / 6, 6), "verify": round(2 / 6, 6)}

    # the old comparator hard-errors on exactly this evidence
    with pytest.raises(SchemaError) as exc:
        scramble_terminal_distribution(dirs, CONDITIONS)
    assert "duplicate effective unit" in str(exc.value)


# -------------------------------------------------------- 6. bootstrap + verdict

def _mixed_dirs(tmp_path, b_actions):
    """A and C mixed identically; B as given. Six sampler seeds, split 3/3."""
    a = [(s, "share" if s % 2 else "verify") for s in range(1, 7)]
    return _build(tmp_path, {"A": a, "B": b_actions, "C": list(a)})


def test_bootstrap_is_deterministic_across_identical_calls(tmp_path):
    dirs = _mixed_dirs(tmp_path, [(s, "share" if s % 2 else "verify")
                                  for s in range(1, 7)])
    kw = dict(admissibility_policy=POLICY(min_admissible_effective_n=3),
              thresholds=THRESH([1, 2, 3], [4, 5, 6]))
    first = order_sensitivity_report(dirs, CONDITIONS, **kw)
    second = order_sensitivity_report(dirs, CONDITIONS, **kw)
    assert canonical_json(first) == canonical_json(second)
    boot = first["per_agent"]["live"]["bootstrap"]
    assert set(boot) == {"A|B", "A|C", "null"}
    for name in boot:
        assert boot[name]["lower"] <= boot[name]["upper"]
        assert boot[name]["iterations"] == 200


def test_verdict_no_order_effect(tmp_path):
    dirs = _build(tmp_path, {c: [(s, "share") for s in range(1, 5)]
                             for c in ("A", "B", "C")})
    rep = order_sensitivity_report(dirs, CONDITIONS,
                                   admissibility_policy=POLICY(min_admissible_effective_n=2),
                                   thresholds=THRESH([1, 2], [3, 4]))
    agent = rep["per_agent"]["live"]
    assert agent["tv_distances"] == {"A|B": 0.0, "A|C": 0.0, "null": 0.0}
    assert agent["verdict"] == "no_order_effect_observed"


def test_verdict_order_effect_observed(tmp_path):
    dirs = _build(tmp_path, {
        "A": [(s, "share") for s in range(1, 5)],
        "B": [(s, "verify") for s in range(1, 5)],     # fully displaced
        "C": [(s, "share") for s in range(1, 5)],      # sham null
    })
    rep = order_sensitivity_report(dirs, CONDITIONS,
                                   admissibility_policy=POLICY(min_admissible_effective_n=2),
                                   thresholds=THRESH([1, 2], [3, 4]))
    agent = rep["per_agent"]["live"]
    assert agent["tv_distances"]["A|B"] == 1.0
    assert agent["bootstrap"]["A|B"]["lower"] > agent["bootstrap"]["null"]["upper"]
    assert agent["bootstrap"]["A|C"]["upper"] <= agent["bootstrap"]["null"]["upper"]
    assert agent["verdict"] == "order_effect_observed"


def test_failed_sham_voids_a_large_ab_distance(tmp_path):
    """The load-bearing negative case: TV(A,B) is maximal, but the sham — A's own
    order with only agent-facing wording changed — also moves. The verdict must be
    inconclusive, and must NEVER be positive."""
    dirs = _build(tmp_path, {
        "A": [(s, "share") for s in range(1, 5)],
        "B": [(s, "verify") for s in range(1, 5)],
        "C": [(s, "decline") for s in range(1, 5)],    # sham is NOT null
    })
    rep = order_sensitivity_report(dirs, CONDITIONS,
                                   admissibility_policy=POLICY(min_admissible_effective_n=2),
                                   thresholds=THRESH([1, 2], [3, 4]))
    agent = rep["per_agent"]["live"]
    assert agent["tv_distances"]["A|B"] == 1.0       # large, and irrelevant
    assert agent["bootstrap"]["A|C"]["upper"] > agent["bootstrap"]["null"]["upper"]
    assert agent["verdict"] == "inconclusive"
    assert agent["verdict"] != "order_effect_observed"
    assert "sham not null" in agent["verdict_reason"]


# -------------------------------------------------------- 7. self-description

def test_report_is_self_describing(tmp_path):
    dirs = _build(tmp_path, {c: [(s, "share") for s in range(1, 5)]
                             for c in ("A", "B", "C")})
    policy = POLICY(min_admissible_effective_n=2)
    thresholds = THRESH([1, 2], [3, 4])
    rep = order_sensitivity_report(dirs, CONDITIONS, admissibility_policy=policy,
                                   thresholds=thresholds)
    assert rep["order_report_version"] == ORDER_REPORT_VERSION == "1"
    assert rep["admissibility_version"] == DECISION_ADMISSIBILITY_VERSION
    assert rep["policy_version"] == "1"
    assert rep["admissibility_policy"] == policy
    assert rep["thresholds"] == thresholds
    assert len(rep["policy_hash"]) == 64 and len(rep["thresholds_hash"]) == 64
    # METRICS-v1 definitions did not move: the new artifact carries its OWN version
    assert rep["metrics_version"] == METRICS_VERSION == "1"


# ------------------------------------------- 8. Phase-1 no-op / frozen instrument

def test_phase1_scripted_evidence_agrees_with_the_frozen_comparator(tmp_path):
    """On clean deterministic evidence — scripted nodes, no parser, therefore zero
    non-decisions — the new path must agree with the old one. The successor changes
    what happens to ARTIFACTS, not what happens to real decisions."""
    plan = {"A": [(1, "share"), (2, "share"), (3, "verify"), (4, "verify")],
            "B": [(1, "verify"), (2, "verify"), (3, "verify"), (4, "verify")],
            "C": [(1, "share"), (2, "share"), (3, "verify"), (4, "verify")]}
    dirs = _build(tmp_path, plan, scripted=True)

    old = scramble_terminal_distribution(dirs, CONDITIONS)["per_agent"]["live"]
    new = order_sensitivity_report(dirs, CONDITIONS,
                                   admissibility_policy=POLICY(min_admissible_effective_n=2),
                                   thresholds=THRESH([1, 2], [3, 4]))["per_agent"]["live"]

    for cond in ("A", "B", "C"):
        cell = new["cells"][cond]
        assert cell["non_decision_n"] == 0
        assert cell["non_decision_reasons"] == {}
        assert cell["admissible_effective_n"] == old["effective_n"][cond]
        for action, p in old["distributions"][cond].items():
            assert cell["distribution"][action] == pytest.approx(p)
    assert new["tv_distances"]["A|B"] == pytest.approx(old["tv_distances"]["A|B"])
    assert new["tv_distances"]["A|C"] == pytest.approx(old["tv_distances"]["A|C"])


def test_frozen_comparator_output_is_byte_stable(tmp_path):
    """Golden lock on `scramble_terminal_distribution`: Phase-1 evidence and its
    three GO verdicts (001714 / 001719 / 001724 @ ac693b53) depend on these exact
    bytes, so the successor must not have perturbed them."""
    dirs = _build(tmp_path, {"A": [(1, "share"), (2, "verify")],
                             "B": [(1, "verify"), (2, "verify")],
                             "C": [(1, "share"), (2, "verify")]})
    out = scramble_terminal_distribution(dirs, CONDITIONS)
    agent = out["per_agent"]["live"]
    assert out["metrics_version"] == "1"
    assert out["conditions"] == CONDITIONS
    assert agent["distributions"] == {"A": {"share": 0.5, "verify": 0.5},
                                      "B": {"verify": 1.0},
                                      "C": {"share": 0.5, "verify": 0.5}}
    assert agent["effective_n"] == {"A": 2, "B": 2, "C": 2}
    assert agent["tv_distances"] == {"A|B": 0.5, "A|C": 0.0}
    assert agent["agent_regime_id"] == REGIME
    assert set(agent) == {"distributions", "effective_n", "tv_distances",
                          "agent_regime_id"}
    # no key from the successor leaked into the frozen artifact
    assert "order_report_version" not in out and "bootstrap" not in agent
