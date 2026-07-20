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

AT ORDER_REPORT_VERSION 5 the successor enforces the audit repairs and the
a-005 distributional re-framing (001814 / 001820 / 001823 / a-005):

  a-005     distributional-null claim discipline: `null_form: "distributional"`,
            the per-unit-claim limitation, and verdict language that states the
            population-marginal conclusion — a rejection evidences a
            marginal-distribution difference only, never a per-unit claim;
  a-003[1]  sham adequacy: a positive needs TV(A,C) <= q_AC AND
            q_AC < sham_equivalence_margin (STRICT);
  d-001[0]  `max_surviving_delta` REQUIRED and enforced pre-statistics, with the
            execution census (`surviving_counts`) consumed when declared;
  d-001[1]  the matched-unit grid: identical unit identities in every condition,
            fully realizing the frozen sampler-seed set;
  d-001[2]  the frozen terminal probe (`terminal_dp_id`), never `nodes[-1]`;
  c-001[0]  the provider-free replay gate (`replay_attestation`, MANDATORY).

No live model is contacted; every fixture is a synthetic run directory.
"""
import hashlib
import json
import os
import socket

import pytest

from coliseum.textlab.admissibility import DECISION_ADMISSIBILITY_VERSION
from coliseum.textlab.metrics import (ORDER_REPORT_VERSION, METRICS_VERSION,
                                      order_sensitivity_report,
                                      scramble_terminal_distribution)
from coliseum.textlab.schema import SchemaError, canonical_json

CONDITIONS = {"A": "scramble_dev_m8", "B": "scramble_perm_m8", "C": "scramble_sham_m8"}
REGIME = "r" * 64
AGENT_CFG = {"driver": "ollama_local", "temperature": 0.7}
TERMINAL = "d_partner"
# the terminal probe's action menu (a DECISION: >= 2 actions); the exposure
# points offer exactly one
MENU = ["share", "verify", "decline", "defer"]


# ------------------------------------------------------------------ fixtures

def _node(final_action: str, winner: str | None = "planner", scripted: bool = False,
          dp_id: str = TERMINAL, available_actions: list | None = None):
    """One decision_node record's `data`.

    `scripted=True` reproduces Phase-1 scripted shape: no `arbitration_winner`
    and no `meta` on either pass, i.e. no parser ran, so no parse failure is
    possible and the node must census as admissible.
    """
    aa = list(MENU) if available_actions is None else list(available_actions)
    if scripted:
        return {"dp_id": dp_id, "final_action": final_action,
                "available_actions": aa,
                "reflex_choice": {"action_id": final_action},
                "planner_choice": {"action_id": final_action},
                "moral_tags": [], "state_before": {"facts": {}}}
    return {"dp_id": dp_id, "final_action": final_action,
            "available_actions": aa,
            "arbitration_winner": winner,
            "reflex_choice": {"action_id": final_action, "meta": {"parse_status": "ok"}},
            "planner_choice": {"action_id": final_action, "meta": {"parse_status": "ok"}},
            "moral_tags": [], "state_before": {"facts": {}}}


def _exposure(scripted: bool = False):
    """An exposure point: exactly ONE legal action, and NOT the terminal dp_id.
    The report must never let it stand in for the measured probe."""
    return _node("expose", scripted=scripted, dp_id="e_event",
                 available_actions=["expose"])


def _mkrun(tmp_path, rid, scenario_id, variant, scen_seed, samp_seed, final_action,
           winner="planner", scripted=False, agent_id="live", regime=REGIME,
           agent_config=None, reportable=True, stochastic_reportable=True,
           stochastic_exclusion_reasons=None, nodes=None):
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
    # an earlier (exposure) node plus the TERMINAL probe — the report must
    # measure the frozen probe and must never re-point at the earlier one
    if nodes is None:
        lines = [
            {"kind": "decision_node", "data": _exposure(scripted=scripted)},
            {"kind": "decision_node",
             "data": _node(final_action, winner=winner, scripted=scripted)},
        ]
    else:
        lines = [{"kind": "decision_node", "data": n} for n in nodes]
    (d / "decisions.jsonl").write_text(
        "\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    # the replay substrate the attestation binds; synthetic but hashed for real
    (d / "captures.jsonl").write_text(
        json.dumps({"key": f"{TERMINAL}/plan", "raw_text": final_action}) + "\n",
        encoding="utf-8")
    return str(d)


def _attest(dirs, replay_ok=True):
    """Generate the Director-defined replay attestation from the CURRENT bytes
    of each run directory — the same contract the sweep-side generator emits."""
    runs = {}
    for d in dirs:
        with open(os.path.join(d, "run.json"), encoding="utf-8") as fh:
            run = json.load(fh)
        entry = {"replay_ok": replay_ok}
        for fname, key in (("run.json", "run_json_sha256"),
                           ("decisions.jsonl", "decisions_sha256"),
                           ("captures.jsonl", "captures_sha256")):
            with open(os.path.join(d, fname), "rb") as fh:
                entry[key] = hashlib.sha256(fh.read()).hexdigest()
        runs[run["run_id"]] = entry
    return {"attestation_version": "1", "runs": runs}


def _report(dirs, policy, thresholds, attestation=None, terminal=TERMINAL,
            surviving=None, conditions=CONDITIONS):
    return order_sensitivity_report(
        dirs, conditions, admissibility_policy=policy, thresholds=thresholds,
        replay_attestation=_attest(dirs) if attestation is None else attestation,
        terminal_dp_id=terminal, surviving_counts=surviving)


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
         "confidence": 0.95,
         # DIAGNOSTIC ONLY — retained and reported as a within-condition
         # stability measure, but it gates no verdict. It ALSO declares the
         # frozen sampler-seed set (S1 ∪ S2) the matched-unit grid must realize.
         "noise_floor_split": {"S1": list(s1), "S2": list(s2)},
         # the frozen sensitivity ceiling; mandatory, see _THRESHOLD_KEYS
         "min_detectable_effect": 0.25,
         # the paired permutation null that REPLACED the split-half noise floor
         # as the calibrating null; these three are mandatory at v2
         "permutation_iterations": 200, "permutation_seed": 20260719,
         "alpha": 0.05,
         # v4 REQUIRED: the sham non-rejection's equivalence warrant and the
         # differential-dropout bound
         "sham_equivalence_margin": 0.25,
         "max_surviving_delta": 2}
    t.update(over)
    return t


LOOSE = POLICY(min_admissible_effective_n=1, max_non_decision_rate=0.5,
               max_non_decision_rate_delta=0.5)


# ------------------------------------------------- 1. THE DEFECT REPRODUCTION

def test_parse_fallback_inflates_old_tv_and_new_report_refuses_the_pair(tmp_path):
    """F8, stated as a contrast, AT v4 (audit d-002 finding 0).

    One B-condition unit's terminal node has `arbitration_winner: "fallback"` and
    therefore resolved to a deterministic action rather than a choice. The OLD
    comparator scores it as a real choice and reports TV(A,B) = 1/3 — an order
    effect manufactured out of one malformed model reply. The NEW report does not
    merely exclude the draw and press on with an unbalanced pair: a non-decision
    on one side makes that matched pair INADMISSIBLE, so the report REFUSES
    pre-statistics with a typed census — the fallback appears as a non-decision,
    never in any distribution, and no distance/quantile/verdict is emitted.
    """
    dirs = _build(tmp_path, {
        "A": [(1, "share"), (2, "share"), (3, "share")],
        # unit 3 of B is a fallback: the parser failed and the runner substituted
        "B": [(1, "share"), (2, "share"), (3, "verify", "fallback")],
        "C": [(1, "share"), (2, "share"), (3, "share")],
    })

    old = scramble_terminal_distribution(dirs, CONDITIONS)["per_agent"]["live"]
    assert old["tv_distances"]["A|B"] == pytest.approx(1 / 3)   # manufactured
    assert old["distributions"]["B"] == {"share": pytest.approx(2 / 3),
                                         "verify": pytest.approx(1 / 3)}
    assert old["effective_n"]["B"] == 3          # the fallback counted as evidence

    with pytest.raises(SchemaError) as exc:
        _report(dirs, LOOSE, THRESH([1], [2, 3]))
    msg = str(exc.value)
    assert "matched_unit_grid" in msg
    assert "live|A|B pairs 2 admissible matched units, not the 3" in msg
    assert "never silently held fixed" in msg
    body = exc.value.report
    b = body["per_agent"]["live"]["cells"]["B"]
    # the fallback is a NON-DECISION in the census, never a real choice
    assert b["non_decision_n"] == 1
    assert b["non_decision_reasons"] == {"parse_fallback_winner": 1}
    assert b["distribution"] == {"share": 1.0}   # the artifact contributes NOTHING
    assert b["admissible_effective_n"] == 2
    # numbers never escape the refusal
    for agent in body["per_agent"].values():
        for key in ("tv_distances", "bootstrap", "permutation_null", "verdict"):
            assert key not in agent
    for leaked in ("tv_distances", "permutation_null", "q_ab", "verdict"):
        assert leaked not in canonical_json(body)


def test_non_admissible_terminal_is_never_repointed_at_an_earlier_decision(tmp_path):
    """The terminal probe is the FROZEN probe, full stop. Substituting the earlier
    (admissible) node would be a second fabrication on top of the first. With one
    B unit non-admissible the v4 report REFUSES (audit d-002 finding 0), and the
    census it attaches proves 'expose' entered no distribution."""
    dirs = _build(tmp_path, {
        "A": [(1, "share"), (2, "share")],
        "B": [(1, "share"), (2, "verify", "fallback")],
        "C": [(1, "share"), (2, "share")],
    })
    with pytest.raises(SchemaError) as exc:
        _report(dirs, LOOSE, THRESH([1], [2]))
    assert "matched_unit_grid" in str(exc.value)
    b = exc.value.report["per_agent"]["live"]["cells"]["B"]
    # "expose" is the earlier node's action; it must appear nowhere
    assert "expose" not in b["distribution"] and "expose" not in b["counts"]
    assert b["admissible_draw_n"] == 1 and b["non_decision_n"] == 1


# --------------------------------------------- 2. declared bounds are mandatory

def test_policy_thresholds_attestation_and_probe_are_mandatory_keywords(tmp_path):
    dirs = _build(tmp_path, {"A": [(1, "share")], "B": [(1, "share")],
                             "C": [(1, "share")]})
    att = _attest(dirs)
    with pytest.raises(TypeError):
        order_sensitivity_report(dirs, CONDITIONS)
    with pytest.raises(TypeError):
        order_sensitivity_report(dirs, CONDITIONS, admissibility_policy=LOOSE)
    with pytest.raises(TypeError):
        order_sensitivity_report(dirs, CONDITIONS, thresholds=THRESH([1], [2]))
    # v4: the replay attestation and the frozen probe identity are equally
    # non-defaultable — a report without them is the artifact this module
    # exists to prevent
    with pytest.raises(TypeError):
        order_sensitivity_report(dirs, CONDITIONS, admissibility_policy=LOOSE,
                                 thresholds=THRESH([1], [2]),
                                 terminal_dp_id=TERMINAL)
    with pytest.raises(TypeError):
        order_sensitivity_report(dirs, CONDITIONS, admissibility_policy=LOOSE,
                                 thresholds=THRESH([1], [2]),
                                 replay_attestation=att)


def test_admissibility_version_mismatch_is_refused(tmp_path):
    """A v2 predicate must not retroactively reinterpret a frozen v1 experiment."""
    dirs = _build(tmp_path, {"A": [(1, "share")], "B": [(1, "share")],
                             "C": [(1, "share")]})
    with pytest.raises(SchemaError) as exc:
        _report(dirs, POLICY(admissibility_version="0"), THRESH([1], [2]))
    assert "admissibility_version" in str(exc.value)


def test_missing_policy_keys_and_non_refuse_mode_are_refused(tmp_path):
    dirs = _build(tmp_path, {"A": [(1, "share")], "B": [(1, "share")],
                             "C": [(1, "share")]})
    bad = POLICY()
    del bad["max_non_decision_rate_delta"]
    with pytest.raises(SchemaError):
        _report(dirs, bad, THRESH([1], [2]))
    with pytest.raises(SchemaError):
        _report(dirs, POLICY(on_violation="warn"), THRESH([1], [2]))


def test_min_detectable_effect_is_a_mandatory_threshold(tmp_path):
    """The sensitivity ceiling is part of the claim. A report computed without it
    would be able to state a null it has no entitlement to state."""
    dirs = _build(tmp_path, {"A": [(1, "share")], "B": [(1, "share")],
                             "C": [(1, "share")]})
    bad = THRESH([1], [2])
    del bad["min_detectable_effect"]
    with pytest.raises(SchemaError) as exc:
        _report(dirs, LOOSE, bad)
    assert "min_detectable_effect" in str(exc.value)
    for value in (0.0, -0.1, 1.5, "0.25", True):
        with pytest.raises(SchemaError):
            _report(dirs, LOOSE, THRESH([1], [2], min_detectable_effect=value))


def test_sham_equivalence_margin_is_a_mandatory_threshold(tmp_path):
    """v4 (audit 001814 finding 1): the sham non-rejection's warrant is part of
    the frozen bundle. Deleting it must refuse; malformed values must refuse."""
    dirs = _build(tmp_path, {"A": [(1, "share")], "B": [(1, "share")],
                             "C": [(1, "share")]})
    bad = THRESH([1], [2])
    del bad["sham_equivalence_margin"]
    with pytest.raises(SchemaError) as exc:
        _report(dirs, LOOSE, bad)
    assert "sham_equivalence_margin" in str(exc.value)
    for value in (0.0, -0.1, 1.5, "0.25", True):
        with pytest.raises(SchemaError):
            _report(dirs, LOOSE, THRESH([1], [2], sham_equivalence_margin=value))


def test_max_surviving_delta_is_a_mandatory_threshold_and_echoed(tmp_path):
    """v4 (audit 001823 finding 0): the dropout bound was optional and never
    enforced — a guard nobody is obliged to call. It is now REQUIRED: deleting
    it from the frozen bundle refuses pre-statistics, and the declared value
    survives into the artifact."""
    dirs = _build(tmp_path, {c: [(s, "share") for s in range(1, 5)]
                             for c in ("A", "B", "C")})
    bad = THRESH([1, 2], [3, 4])
    del bad["max_surviving_delta"]
    with pytest.raises(SchemaError) as exc:
        _report(dirs, POLICY(min_admissible_effective_n=2), bad)
    assert "max_surviving_delta" in str(exc.value)
    for value in (-1, 0.5, "2", True):
        with pytest.raises(SchemaError):
            _report(dirs, LOOSE, THRESH([1, 2], [3, 4],
                                        max_surviving_delta=value))
    thresholds = THRESH([1, 2], [3, 4])
    rep = _report(dirs, POLICY(min_admissible_effective_n=2), thresholds)
    assert rep["thresholds"]["max_surviving_delta"] == 2
    assert rep["thresholds"] == thresholds


def test_overlapping_noise_floor_halves_are_refused(tmp_path):
    dirs = _build(tmp_path, {"A": [(1, "share")], "B": [(1, "share")],
                             "C": [(1, "share")]})
    with pytest.raises(SchemaError) as exc:
        _report(dirs, LOOSE, THRESH([1, 2], [2, 3]))
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
        _report(dirs, policy, THRESH(range(1, 6), range(6, 11)))
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
        # v2 additions are on the same fail-closed side of the gate: no quantile
        # and no diagnostic escapes a refusal either
        assert "permutation_null" not in agent
        assert "diagnostics" not in agent
        assert "decision_inputs" not in agent
    for leaked in ("tv_distances", "permutation_null", "q_ab", "verdict"):
        assert leaked not in canonical_json(body)


def test_refuses_when_every_cell_is_below_the_effective_n_floor(tmp_path):
    """The n floor refusal, on a pack whose grid and counts are otherwise clean
    (equal 4-unit conditions against a floor of 8) — so the refusal is
    attributable to the floor and nothing upstream."""
    dirs = _build(tmp_path, {c: [(s, "share") for s in range(1, 5)]
                             for c in ("A", "B", "C")})
    with pytest.raises(SchemaError) as exc:
        _report(dirs, POLICY(min_admissible_effective_n=8),
                THRESH([1, 2], [3, 4]))
    assert "live|C" in str(exc.value)
    assert "min_admissible_effective_n=8" in str(exc.value)


def test_refuses_when_a_cell_has_zero_admissible_units(tmp_path):
    """Zero admissible evidence must REFUSE — never an empty distribution, never None."""
    dirs = _build(tmp_path, {
        "A": [(s, "share") for s in range(1, 5)],
        "B": [(s, "share") for s in range(1, 5)],
        "C": [(s, "verify", "fallback") for s in range(1, 5)],
    })
    with pytest.raises(SchemaError) as exc:
        _report(dirs, POLICY(min_admissible_effective_n=1,
                             max_non_decision_rate=1.0,
                             max_non_decision_rate_delta=1.0),
                THRESH([1, 2], [3, 4]))
    assert "live|C" in str(exc.value)
    assert exc.value.report["per_agent"]["live"]["cells"]["C"]["distribution"] == {}


def test_refuses_when_a_whole_condition_is_missing(tmp_path):
    """A missing condition is a matched-unit grid violation (v4): C realizes
    none of the identities the other conditions carry."""
    dirs = _build(tmp_path, {"A": [(1, "share"), (2, "share")],
                             "B": [(1, "share"), (2, "share")]})
    with pytest.raises(SchemaError) as exc:
        _report(dirs, LOOSE, THRESH([1], [2]))
    assert "live|C" in str(exc.value)
    assert "matched_unit_grid" in str(exc.value)


def test_refuses_when_a_cell_exceeds_the_absolute_non_decision_rate(tmp_path):
    dirs = _build(tmp_path, {
        "A": [(1, "share"), (2, "share"), (3, "share"), (4, "share")],
        "B": [(1, "share"), (2, "verify", "fallback"),
              (3, "verify", "fallback"), (4, "verify", "fallback")],
        "C": [(1, "share"), (2, "share"), (3, "share"), (4, "share")],
    })
    with pytest.raises(SchemaError) as exc:
        _report(dirs, POLICY(min_admissible_effective_n=1,
                             max_non_decision_rate=0.20,
                             max_non_decision_rate_delta=1.0),
                THRESH([1, 2], [3, 4]))
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
    rep = _report(dirs + [bad], POLICY(min_admissible_effective_n=1),
                  THRESH([1, 2], [3, 4]))
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
    rep = _report(dirs + [bad], LOOSE, THRESH([1], [2]))
    assert any(e["report_id"] == "A_bad" and "non_reportable" in e["reasons"]
               for e in rep["excluded"])


def test_mixed_decider_regimes_are_refused(tmp_path):
    dirs = _build(tmp_path, {"A": [(1, "share"), (2, "share")],
                             "C": [(1, "share"), (2, "share")]})
    dirs.append(_mkrun(tmp_path, "B_other", CONDITIONS["B"], "v0", 42, 1, "share",
                       regime="q" * 64))
    with pytest.raises(SchemaError) as exc:
        _report(dirs, LOOSE, THRESH([1], [2]))
    assert "MIXED decider regimes" in str(exc.value)


def test_regime_unbound_evidence_is_refused(tmp_path):
    dirs = [_mkrun(tmp_path, "A_0", CONDITIONS["A"], "v0", 42, 1, "share",
                   agent_config={})]
    with pytest.raises(SchemaError) as exc:
        _report(dirs, LOOSE, THRESH([1], [2]))
    assert "regime-unbound" in str(exc.value)


# ------------------------------------- 5. v4 replay gate (audit c-001 finding 0)

def _full_grid(tmp_path, choose, conditions=("A", "B", "C"), skip=()):
    """A production-shaped pack: 2 (variant, scenario_seed) groups x 24 frozen
    sampler seeds x 3 conditions = 144 run dirs. `choose(cond, variant, samp)`.
    `skip` removes (cond, variant, samp) triples to model dropout."""
    s_all = list(range(2001, 2025))
    dirs = []
    for cond in conditions:
        for variant, scen_seed in (("v0", 42), ("v1", 1)):
            for samp in s_all:
                if (cond, variant, samp) in skip:
                    continue
                dirs.append(_mkrun(tmp_path, f"{cond}_{variant}_{samp}",
                                   CONDITIONS[cond], variant, scen_seed, samp,
                                   choose(cond, variant, samp)))
    return dirs


_GRID_S1 = list(range(2001, 2013))
_GRID_S2 = list(range(2013, 2025))
_GRID_POLICY = POLICY(min_admissible_effective_n=20)


def _grid_thresh(**over):
    return THRESH(_GRID_S1, _GRID_S2, **over)


def test_replay_attestation_is_mandatory_and_shape_checked(tmp_path):
    dirs = _build(tmp_path, {"A": [(1, "share")], "B": [(1, "share")],
                             "C": [(1, "share")]})
    for bad in (None, [], "yes", {"runs": {}},
                {"attestation_version": "2", "runs": {}},
                {"attestation_version": "1", "runs": []}):
        with pytest.raises((SchemaError, TypeError)):
            _report(dirs, LOOSE, THRESH([1], [2]), attestation=bad)


def test_missing_attestation_entry_refuses_before_any_distance(tmp_path):
    dirs = _build(tmp_path, {"A": [(1, "share")], "B": [(1, "share")],
                             "C": [(1, "share")]})
    att = _attest(dirs)
    del att["runs"]["B_0_1"]
    with pytest.raises(SchemaError) as exc:
        _report(dirs, LOOSE, THRESH([1], [2]), attestation=att)
    assert "replay_attestation_missing" in str(exc.value)


def test_failed_replay_refuses(tmp_path):
    dirs = _build(tmp_path, {"A": [(1, "share")], "B": [(1, "share")],
                             "C": [(1, "share")]})
    att = _attest(dirs)
    att["runs"]["A_0_1"]["replay_ok"] = False
    with pytest.raises(SchemaError) as exc:
        _report(dirs, LOOSE, THRESH([1], [2]), attestation=att)
    assert "replay_attestation_failed" in str(exc.value)


def test_144_run_pack_with_missing_corrupted_or_stale_captures_refuses(tmp_path):
    """THE c-001 FINDING-0 REGRESSION at the frozen pack shape: a 144-run grid
    whose captures are missing, corrupted, or stale refuses BEFORE any distance,
    quantile or verdict exists."""
    dirs = _full_grid(tmp_path, lambda c, v, s: "share")
    att = _attest(dirs)

    # (a) missing: delete one run's captures after attestation
    victim = os.path.join(dirs[7], "captures.jsonl")
    os.rename(victim, victim + ".bak")
    with pytest.raises(SchemaError) as exc:
        _report(dirs, _GRID_POLICY, _grid_thresh(), attestation=att)
    assert "replay_attestation_stale" in str(exc.value)
    assert not hasattr(exc.value, "report") or \
        "tv_distances" not in canonical_json(getattr(exc.value, "report", {}))
    os.rename(victim + ".bak", victim)

    # (b) corrupted: tamper the bytes
    with open(victim, "a", encoding="utf-8") as fh:
        fh.write('{"key": "forged", "raw_text": "tampered"}\n')
    with pytest.raises(SchemaError) as exc:
        _report(dirs, _GRID_POLICY, _grid_thresh(), attestation=att)
    assert "replay_attestation_stale" in str(exc.value)

    # (c) stale: the run evidence moved after attestation
    att2 = _attest(dirs)          # fresh attestation over the tampered captures
    dec = os.path.join(dirs[3], "decisions.jsonl")
    with open(dec, "a", encoding="utf-8") as fh:
        pass                       # touch is not enough — rewrite content
    with open(dec, "r+", encoding="utf-8") as fh:
        content = fh.read()
        fh.seek(0)
        fh.write(content.replace("share", "adopt"))
        fh.truncate()
    with pytest.raises(SchemaError) as exc:
        _report(dirs, _GRID_POLICY, _grid_thresh(), attestation=att2)
    assert "replay_attestation_stale" in str(exc.value)


def test_valid_attested_pack_passes_with_a_provider_call_trap(tmp_path, monkeypatch):
    """THE POSITIVE HALF of the c-001 regression: a fully attested pack reaches a
    verdict deterministically, and a socket trap proves the whole analysis is
    provider-free — no network object is ever constructed."""
    def trap(*a, **kw):
        raise AssertionError("provider contact attempted during a frozen analysis")
    monkeypatch.setattr(socket, "socket", trap)
    monkeypatch.setattr(socket, "create_connection", trap)

    dirs = _full_grid(tmp_path,
                      lambda c, v, s: "share" if (c != "B" or s % 2) else "verify")
    first = _report(dirs, _GRID_POLICY, _grid_thresh(),
                    surviving={"A": 48, "B": 48, "C": 48})
    second = _report(dirs, _GRID_POLICY, _grid_thresh(),
                     surviving={"A": 48, "B": 48, "C": 48})
    assert canonical_json(first) == canonical_json(second)
    agent = first["per_agent"]["live"]
    assert agent["verdict"] in ("distributional_order_effect_observed",
                                "no_distributional_order_effect_observed",
                                "inconclusive")
    assert first["replay_verification"] == {"attestation_version": "1",
                                            "verified_run_n": 144}


# --------------------------------- 6. v4 terminal probe (audit d-001 finding 2)

def test_missing_terminal_probe_refuses_and_never_falls_back_to_last_node(tmp_path):
    """THE d-001 FINDING-2 REGRESSION: a completed run whose last node is an
    admissible EXPOSURE but whose frozen terminal probe is absent must refuse
    with the typed reason — the exposure must never enter any distribution."""
    dirs = _build(tmp_path, {"A": [(1, "share"), (2, "share")],
                             "C": [(1, "share"), (2, "share")]})
    dirs.append(_mkrun(tmp_path, "B_1", CONDITIONS["B"], "v0", 42, 1, "share"))
    # B unit 2: only exposure nodes — no d_partner record at all
    dirs.append(_mkrun(tmp_path, "B_2", CONDITIONS["B"], "v0", 42, 2, "share",
                       nodes=[_exposure(), _exposure()]))
    with pytest.raises(SchemaError) as exc:
        _report(dirs, LOOSE, THRESH([1], [2]))
    assert "missing_terminal_probe" in str(exc.value)
    assert "B_2" in str(exc.value)


def test_wrong_terminal_id_refuses(tmp_path):
    dirs = _build(tmp_path, {"A": [(1, "share")], "C": [(1, "share")]})
    dirs.append(_mkrun(tmp_path, "B_0", CONDITIONS["B"], "v0", 42, 1, "share",
                       nodes=[_exposure(), _node("share", dp_id="d_other")]))
    with pytest.raises(SchemaError) as exc:
        _report(dirs, LOOSE, THRESH([1], [2]))
    assert "missing_terminal_probe" in str(exc.value)


def test_duplicate_terminal_probe_refuses(tmp_path):
    dirs = _build(tmp_path, {"A": [(1, "share")], "C": [(1, "share")]})
    dirs.append(_mkrun(tmp_path, "B_0", CONDITIONS["B"], "v0", 42, 1, "share",
                       nodes=[_node("share"), _node("verify")]))
    with pytest.raises(SchemaError) as exc:
        _report(dirs, LOOSE, THRESH([1], [2]))
    assert "missing_terminal_probe" in str(exc.value)
    assert "2 decision_node" in str(exc.value)


def test_out_of_order_terminal_refuses(tmp_path):
    """A record after the measured probe means the probe was not terminal."""
    dirs = _build(tmp_path, {"A": [(1, "share")], "C": [(1, "share")]})
    dirs.append(_mkrun(tmp_path, "B_0", CONDITIONS["B"], "v0", 42, 1, "share",
                       nodes=[_node("share"), _exposure()]))
    with pytest.raises(SchemaError) as exc:
        _report(dirs, LOOSE, THRESH([1], [2]))
    assert "missing_terminal_probe" in str(exc.value)
    assert "out-of-order" in str(exc.value)


def test_exposure_kind_terminal_refuses(tmp_path):
    """A node carrying the terminal dp_id but offering a single action is an
    exposure wearing the probe's name — refused, never measured."""
    dirs = _build(tmp_path, {"A": [(1, "share")], "C": [(1, "share")]})
    dirs.append(_mkrun(
        tmp_path, "B_0", CONDITIONS["B"], "v0", 42, 1, "share",
        nodes=[_exposure(),
               _node("share", dp_id=TERMINAL, available_actions=["share"])]))
    with pytest.raises(SchemaError) as exc:
        _report(dirs, LOOSE, THRESH([1], [2]))
    assert "missing_terminal_probe" in str(exc.value)
    assert "exposure" in str(exc.value)


def test_terminal_dp_id_must_be_a_nonempty_string(tmp_path):
    dirs = _build(tmp_path, {"A": [(1, "share")], "B": [(1, "share")],
                             "C": [(1, "share")]})
    for bad in ("", None, 42):
        with pytest.raises(SchemaError):
            _report(dirs, LOOSE, THRESH([1], [2]), terminal=bad)


# ------------------------------ 7. v4 surviving counts (audit d-001 finding 0)

def test_48_45_48_pack_refuses_pre_statistics_naming_counts_delta_and_bound(tmp_path):
    """THE d-001 FINDING-0 REGRESSION: a clean pack whose B condition lost 3
    units refuses BEFORE any statistic, naming every count, the delta and the
    bound — with no caller-declared census needed (the report charges its own
    observed counts)."""
    skip = {("B", "v0", s) for s in (2001, 2002, 2003)}
    dirs = _full_grid(tmp_path, lambda c, v, s: "share", skip=skip)
    with pytest.raises(SchemaError) as exc:
        _report(dirs, _GRID_POLICY, _grid_thresh())
    msg = str(exc.value)
    assert "surviving_count_spread" in msg
    assert "A=48" in msg and "B=45" in msg and "C=48" in msg
    assert "delta=3" in msg and "max_surviving_delta=2" in msg
    body = exc.value.report
    for agent in body["per_agent"].values():
        for key in ("tv_distances", "bootstrap", "permutation_null", "verdict",
                    "decision_inputs"):
            assert key not in agent
    for leaked in ("tv_distances", "permutation_null", "q_ab", "verdict"):
        assert leaked not in canonical_json(body)


def test_declared_execution_census_is_charged_against_the_bound(tmp_path):
    """The execution layer's own census refuses at spread 3 and passes at the
    boundary spread 2 — production entrypoints MUST declare it, because a
    dropped run is invisible in run_dirs."""
    dirs = _full_grid(tmp_path, lambda c, v, s: "share")
    with pytest.raises(SchemaError) as exc:
        _report(dirs, _GRID_POLICY, _grid_thresh(),
                surviving={"A": 48, "B": 45, "C": 48})
    msg = str(exc.value)
    assert "surviving_count_spread" in msg and "declared" in msg
    assert "B=45" in msg and "delta=3" in msg and "max_surviving_delta=2" in msg

    # boundary: spread exactly max_surviving_delta passes the dropout gate
    rep = _report(dirs, _GRID_POLICY, _grid_thresh(),
                  surviving={"A": 48, "B": 46, "C": 48})
    assert rep["per_agent"]["live"]["verdict"] == "no_distributional_order_effect_observed"
    assert rep["surviving_counts"] == {"A": 48, "B": 46, "C": 48}


def test_malformed_surviving_counts_are_refused(tmp_path):
    dirs = _build(tmp_path, {"A": [(1, "share")], "B": [(1, "share")],
                             "C": [(1, "share")]})
    for bad in ([1, 2, 3], {"A": 1, "B": 1},          # missing C
                {"A": 1, "B": 1, "C": -1},
                {"A": 1, "B": 1, "C": "1"},
                {"A": 1, "B": 1, "C": True}):
        with pytest.raises(SchemaError):
            _report(dirs, LOOSE, THRESH([1], [2]), surviving=bad)


# ------------------------------ 8. v4 matched-unit grid (audit d-001 finding 1)

def test_disjoint_unit_identities_refuse_despite_equal_counts(tmp_path):
    """THE d-001 FINDING-1 REGRESSION: equal effective-n with DISJOINT B unit
    identities must refuse before distances — the paired permutation null has
    nothing to pair and must never decide."""
    dirs = []
    for cond, seeds in (("A", range(1, 5)), ("C", range(1, 5)),
                        ("B", range(11, 15))):        # disjoint sampler seeds
        for s in seeds:
            dirs.append(_mkrun(tmp_path, f"{cond}_{s}", CONDITIONS[cond],
                               "v0", 42, s, "share"))
    with pytest.raises(SchemaError) as exc:
        _report(dirs, POLICY(min_admissible_effective_n=2),
                THRESH([1, 2], [3, 4]))
    assert "matched_unit_grid" in str(exc.value)
    body = exc.value.report
    for agent in body["per_agent"].values():
        assert "tv_distances" not in agent and "verdict" not in agent


def test_single_unit_dropout_refuses_never_held_fixed_silently(tmp_path):
    """One B unit missing: spread 1 passes the dropout bound, but the identity
    gate still refuses — an unmatched unit is never silently held fixed."""
    skip = {("B", "v1", 2024)}
    dirs = _full_grid(tmp_path, lambda c, v, s: "share", skip=skip)
    with pytest.raises(SchemaError) as exc:
        _report(dirs, _GRID_POLICY, _grid_thresh())
    msg = str(exc.value)
    assert "matched_unit_grid" in msg and "live|B" in msg
    assert "never silently held fixed" in msg


def test_partial_identity_replacement_refuses(tmp_path):
    """B keeps the right COUNT by replacing one frozen unit with an alien one —
    counts balance, identities do not, and the gate refuses."""
    skip = {("B", "v1", 2024)}
    dirs = _full_grid(tmp_path, lambda c, v, s: "share", skip=skip)
    dirs.append(_mkrun(tmp_path, "B_alien", CONDITIONS["B"], "v1", 1, 3001,
                       "share"))
    with pytest.raises(SchemaError) as exc:
        _report(dirs, _GRID_POLICY, _grid_thresh())
    assert "matched_unit_grid" in str(exc.value)


def test_fully_matched_grid_reports_48_matched_units_for_both_comparisons(tmp_path):
    """The positive pin: the full frozen grid reports matched_units == 48 for
    A|B and A|C — derived as |S1 ∪ S2| x #(variant, scenario_seed) groups
    = 24 x 2 — and the permutation null pairs all 48."""
    dirs = _full_grid(tmp_path,
                      lambda c, v, s: "share" if s % 2 else "verify")
    rep = _report(dirs, _GRID_POLICY, _grid_thresh(),
                  surviving={"A": 48, "B": 48, "C": 48})
    agent = rep["per_agent"]["live"]
    grid = agent["matched_unit_grid"]
    assert grid["required_matched_units"] == 48
    assert grid["matched_units"] == {"A|B": 48, "A|C": 48}
    assert agent["permutation_null"]["A|B"]["matched_units"] == 48
    assert agent["permutation_null"]["A|C"]["matched_units"] == 48


def test_144_grid_with_one_fallback_refuses_and_emits_no_numbers(tmp_path):
    """THE d-002 FINDING-0 REGRESSION: a full frozen 144-run grid with EXACTLY
    one B terminal marked a parse fallback — non-decision rate 1/48 = 0.020833
    (below max_non_decision_rate and its delta) and B admissible n = 47 (above
    the floor), so it passes every rate/dropout/effective-n gate — must still
    REFUSE pre-statistics: only 47 of the 48 matched A|B pairs are admissible.
    Previously the report emitted a verdict while the permutation null silently
    paired 47 and held the unmatched A action fixed. No tv_distances, bootstrap,
    permutation_null, decision_inputs or verdict may be emitted, and the report
    must NEVER claim a 48-unit grid it did not realize admissibly."""
    dirs = _full_grid(tmp_path, lambda c, v, s: "share")
    # mark exactly one B unit's terminal as a parse fallback (a non-decision)
    dec = os.path.join(tmp_path, "B_v0_2001", "decisions.jsonl")
    lines = [json.loads(l) for l in open(dec, encoding="utf-8") if l.strip()]
    lines[-1]["data"]["arbitration_winner"] = "fallback"
    with open(dec, "w", encoding="utf-8") as fh:
        fh.write("\n".join(json.dumps(x) for x in lines) + "\n")
    att = _attest(dirs)          # re-attest over the mutated bytes

    with pytest.raises(SchemaError) as exc:
        order_sensitivity_report(
            dirs, CONDITIONS, admissibility_policy=_GRID_POLICY,
            thresholds=_grid_thresh(), replay_attestation=att,
            terminal_dp_id=TERMINAL, surviving_counts={"A": 48, "B": 48, "C": 48})
    msg = str(exc.value)
    assert "matched_unit_grid" in msg
    assert "live|A|B pairs 47 admissible matched units, not the 48" in msg
    assert "never silently held fixed" in msg
    body = exc.value.report
    b = body["per_agent"]["live"]["cells"]["B"]
    assert b["non_decision_n"] == 1 and b["admissible_effective_n"] == 47
    assert b["non_decision_rate"] == round(1 / 48, 6)
    for agent in body["per_agent"].values():
        for key in ("tv_distances", "bootstrap", "permutation_null",
                    "decision_inputs", "verdict"):
            assert key not in agent
    for leaked in ("tv_distances", "permutation_null", "q_ab", "verdict"):
        assert leaked not in canonical_json(body)


def test_retries_per_unit_zero_dedups_identical_and_refuses_conflicting(tmp_path):
    """THE b-002 FINDING-1 (analysis side) REGRESSION: under the frozen
    retries_per_unit=0 contract the report admits exactly ONE canonical
    observation per effective unit. A single-attempt pack and the same pack with
    an IDENTICAL duplicate run dir for one unit produce BYTE-IDENTICAL statistics
    (the resume re-roll is discarded, never pooled); a CONFLICTING duplicate
    REFUSES pre-statistics rather than reweighting the distribution. The general
    (default) contract still aggregates replicates — the dedup is opt-in."""
    base = {c: [(s, "share") for s in range(1, 5)] for c in ("A", "B", "C")}
    dirs = _build(tmp_path, base)
    policy = POLICY(min_admissible_effective_n=2)
    th = THRESH([1, 2], [3, 4])

    def _run(ds, **kw):
        return order_sensitivity_report(
            ds, CONDITIONS, admissibility_policy=policy, thresholds=th,
            replay_attestation=_attest(ds), terminal_dp_id=TERMINAL, **kw)

    single = _run(dirs, retries_per_unit=0)

    # an IDENTICAL duplicate run dir for A's unit (v0, 42, 1)
    dup = _mkrun(tmp_path, "A_dup", CONDITIONS["A"], "v0", 42, 1, "share")
    dirs_dup = dirs + [dup]
    deduped = _run(dirs_dup, retries_per_unit=0)
    assert canonical_json(deduped) == canonical_json(single)    # byte-identical
    assert deduped["replay_verification"]["verified_run_n"] == 12

    # under the DEFAULT (general replicate) contract the duplicate instead POOLS
    default = _run(dirs_dup)
    assert default["per_agent"]["live"]["cells"]["A"]["admissible_draw_n"] == 5

    # a CONFLICTING duplicate (same unit, different terminal action) refuses
    conflict = _mkrun(tmp_path, "A_conflict", CONDITIONS["A"], "v0", 42, 1, "verify")
    with pytest.raises(SchemaError) as exc:
        _run(dirs + [conflict], retries_per_unit=0)
    assert "duplicate_effective_unit" in str(exc.value)
    for leaked in ("tv_distances", "permutation_null", "verdict"):
        assert leaked not in str(exc.value)

    # unsupported retry counts are refused (only 0 or None are contract-legal)
    for bad in (1, 2, True):
        with pytest.raises(SchemaError) as exc2:
            _run(dirs, retries_per_unit=bad)
        assert "retries_per_unit" in str(exc2.value)


def test_diagnostics_note_and_report_version_are_v5(tmp_path):
    """d-002 finding 1 (LOW): the emitted report identifies ORDER_REPORT_VERSION
    5 consistently — the top-level version, the constant, and the diagnostics
    note that previously read 'order_report_version 4'."""
    dirs = _build(tmp_path, {"A": _mixed(0), "B": _mixed(16), "C": _mixed(0)})
    rep = _report(dirs, _BIG_POLICY, THRESH(_HALF1, _HALF2))
    assert ORDER_REPORT_VERSION == "5"
    assert rep["order_report_version"] == "5"
    note = rep["per_agent"]["live"]["diagnostics"]["note"]
    assert "order_report_version 5" in note
    assert "order_report_version 4" not in note


# ------------------------------------------------------------- 9. replicates (F3)

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

    rep = _report(dirs, LOOSE, THRESH([1], [2]))
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


# -------------------------------------------------------- 10. bootstrap + verdict

def _mixed_dirs(tmp_path, b_actions):
    """A and C mixed identically; B as given. Six sampler seeds, split 3/3."""
    a = [(s, "share" if s % 2 else "verify") for s in range(1, 7)]
    return _build(tmp_path, {"A": a, "B": b_actions, "C": list(a)})


def test_bootstrap_is_deterministic_across_identical_calls(tmp_path):
    dirs = _mixed_dirs(tmp_path, [(s, "share" if s % 2 else "verify")
                                  for s in range(1, 7)])
    kw = dict(policy=POLICY(min_admissible_effective_n=3),
              thresholds=THRESH([1, 2, 3], [4, 5, 6]))
    first = _report(dirs, kw["policy"], kw["thresholds"])
    second = _report(dirs, kw["policy"], kw["thresholds"])
    assert canonical_json(first) == canonical_json(second)
    boot = first["per_agent"]["live"]["bootstrap"]
    assert set(boot) == {"A|B", "A|C", "null"}
    for name in boot:
        assert boot[name]["lower"] <= boot[name]["upper"]
        assert boot[name]["iterations"] == 200


def test_verdict_no_order_effect(tmp_path):
    dirs = _build(tmp_path, {c: [(s, "share") for s in range(1, 5)]
                             for c in ("A", "B", "C")})
    rep = _report(dirs, POLICY(min_admissible_effective_n=2),
                  THRESH([1, 2], [3, 4]))
    agent = rep["per_agent"]["live"]
    assert agent["tv_distances"] == {"A|B": 0.0, "A|C": 0.0, "null": 0.0}
    assert agent["verdict"] == "no_distributional_order_effect_observed"


# Realistic-n verdict fixtures. The decision quantile is the paired permutation
# null, which is a function of the ACTUAL sample size — so a 4-unit fixture has
# q_AB = 1.0 and correctly resolves to `inconclusive` whatever the distances
# show. Exercising the substantive branches therefore requires the frozen order
# of magnitude (48 matched units per condition), not a toy pack.
_N = 48
_SEEDS = list(range(1, _N + 1))
_HALF1, _HALF2 = _SEEDS[:24], _SEEDS[24:]
_BIG_POLICY = POLICY(min_admissible_effective_n=20)


def _mixed(shift=0):
    """24 `share` / 24 `verify` over the 48 sampler seeds, displaced by `shift`
    units toward `verify`. TV against `_mixed(0)` is exactly shift/48."""
    return [(s, "share" if i < 24 - shift else "verify")
            for i, s in enumerate(_SEEDS)]


def test_verdict_distributional_order_effect_states_the_marginal_claim(tmp_path):
    dirs = _build(tmp_path, {
        "A": _mixed(0),
        "B": _mixed(16),      # TV(A,B) = 1/3, well above its permutation quantile
        "C": _mixed(0),       # sham null, unit-identical to A -> q_AC = 0
    })
    rep = _report(dirs, _BIG_POLICY, THRESH(_HALF1, _HALF2))
    agent = rep["per_agent"]["live"]
    di = agent["decision_inputs"]
    assert agent["tv_distances"]["A|B"] == pytest.approx(1 / 3, abs=1e-6)
    assert di["q_ab"] <= di["min_detectable_effect"]
    assert di["tv_ab"] > di["q_ab"]                  # clause 3
    assert di["tv_ac"] <= di["q_ac"]                 # clause 2, first part
    # v4: the sham warrant — q_AC strictly below the frozen equivalence margin
    assert di["q_ac"] < di["sham_equivalence_margin"] == 0.25
    assert agent["verdict"] == "distributional_order_effect_observed"
    # the permutation null is what decided it, and it used the real matched n
    assert agent["permutation_null"]["A|B"]["matched_units"] == _N
    assert agent["permutation_null"]["A|B"]["iterations"] == 200
    # a-005: the claim is the DISTRIBUTIONAL (population-marginal) conclusion,
    # capped there — a marginal-distribution difference, never a per-unit claim
    reason = agent["verdict_reason"]
    assert "marginal" in reason and "population-level" in reason
    assert "does not identify which units changed" in reason
    assert rep["null_form"] == "distributional"
    assert "marginal" in rep["per_unit_claim_limitation"]


def test_failed_sham_voids_a_large_ab_distance(tmp_path):
    """The load-bearing negative case: TV(A,B) clears its own null, but the sham —
    A's own order with only agent-facing wording changed — also moves. The verdict
    must be inconclusive, and must NEVER be positive."""
    dirs = _build(tmp_path, {
        "A": _mixed(0),
        "B": _mixed(16),
        "C": _mixed(8),       # sham is NOT null
    })
    rep = _report(dirs, _BIG_POLICY, THRESH(_HALF1, _HALF2))
    agent = rep["per_agent"]["live"]
    di = agent["decision_inputs"]
    assert di["q_ab"] <= di["min_detectable_effect"]  # warrant present, irrelevant
    assert di["tv_ab"] > di["q_ab"]                   # clause 3 WOULD hold, and is void
    assert di["tv_ac"] > di["q_ac"]                   # clause 2 FAILS FIRST
    assert agent["verdict"] == "inconclusive"
    assert agent["verdict"] != "distributional_order_effect_observed"
    assert "sham not null" in agent["verdict_reason"]


def test_sham_warrant_missing_boundary_is_inconclusive_never_positive(tmp_path):
    """THE a-003 FINDING-1 PINNED REGRESSION, at the frozen production
    parameters (10 000 bootstrap / 10 000 permutation iterations).

    The audit's boundary pack: A is 0.5 share / 0.5 verify; C is 0.25 / 0.75
    with every pair discordant where they differ, so TV(A,C) = 0.25 =
    min_detectable_effect and the paired permutation quantile q_AC lands AT or
    ABOVE the frozen sham_equivalence_margin = 0.25; B is decisively separated
    (all decline). Under v3 this promoted (a positive) while an
    observed sham shift equalled the design's own declared minimum detectable
    effect. Under v4 the strict warrant `q_AC < sham_equivalence_margin` fails
    and the verdict is `inconclusive` with the sham-warrant-missing reason —
    NEVER a positive.
    """
    def choose(cond, variant, samp):
        i = (_GRID_S1 + _GRID_S2).index(samp)
        if cond == "B":
            return "decline"
        if cond == "A":
            return "share" if i < 12 else "verify"
        # C: A's share half flips to verify; 12 of A's verify half flip to share
        # -> C is 0.25 share / 0.75 verify with 36 discordant pairs per variant
        return "share" if 12 <= i < 18 else "verify"

    dirs = _full_grid(tmp_path, choose)
    rep = _report(dirs, _GRID_POLICY,
                  _grid_thresh(bootstrap_iterations=10000,
                               permutation_iterations=10000),
                  surviving={"A": 48, "B": 48, "C": 48})
    agent = rep["per_agent"]["live"]
    di = agent["decision_inputs"]
    assert di["tv_ac"] == pytest.approx(0.25, abs=1e-6)   # the sham shift AT the MDE
    assert di["tv_ab"] > di["q_ab"]                       # decisive A/B separation
    assert di["tv_ac"] <= di["q_ac"]                      # no A/C rejection...
    assert di["q_ac"] >= di["sham_equivalence_margin"]    # ...and no warrant either
    assert agent["verdict"] == "inconclusive"
    assert agent["verdict"] != "distributional_order_effect_observed"
    assert "sham warrant missing" in agent["verdict_reason"]


def test_positive_verdict_always_carries_the_sham_warrant(tmp_path):
    """Just BELOW the margin: a small unit-level sham perturbation keeps q_AC
    strictly under the frozen margin, the warrant holds, and the decisive A/B
    rejection promotes — with the warrant stated in the reason."""
    def choose(cond, variant, samp):
        i = (_GRID_S1 + _GRID_S2).index(samp)
        if cond == "B":
            return "decline"
        if cond == "A":
            return "share" if i < 12 else "verify"
        # C: two discordant pairs only -> q_AC far below the margin
        return "share" if i < 10 or i in (12, 13) else "verify"

    dirs = _full_grid(tmp_path, choose)
    rep = _report(dirs, _GRID_POLICY, _grid_thresh(),
                  surviving={"A": 48, "B": 48, "C": 48})
    agent = rep["per_agent"]["live"]
    di = agent["decision_inputs"]
    assert di["q_ac"] < di["sham_equivalence_margin"]
    assert di["tv_ac"] <= di["q_ac"]
    assert agent["verdict"] == "distributional_order_effect_observed"
    assert "sham warrant holds" in agent["verdict_reason"].lower() or \
        "q_AC < sham_equivalence_margin" in agent["verdict_reason"]


def test_split_half_noise_floor_no_longer_gates_any_verdict(tmp_path):
    """v1 -> v2 regression in the OTHER direction (still holds at v5).

    A|S1 is entirely `share` and A|S2 entirely `verify`, so the retained
    diagnostic TV_null is 1.0 — its maximum. Under the v1 rule that alone forced
    `inconclusive` on every pack. It must now decide nothing: the diagnostic is
    reported, and the verdict comes from the paired permutation null.
    """
    dirs = _build(tmp_path, {
        "A": _mixed(0),       # share on _HALF1, verify on _HALF2 -> TV_null = 1.0
        "B": _mixed(16),
        "C": _mixed(0),
    })
    rep = _report(dirs, _BIG_POLICY, THRESH(_HALF1, _HALF2))
    agent = rep["per_agent"]["live"]
    assert agent["tv_distances"]["null"] == 1.0
    assert agent["diagnostics"]["tv_null"] == 1.0
    assert agent["diagnostics"]["tv_null_upper"] == 1.0
    # ...and it appears in NO decision input and gates nothing
    assert "tv_null" not in agent["decision_inputs"]
    assert "tv_null_upper" not in agent["decision_inputs"]
    assert agent["verdict"] == "distributional_order_effect_observed"
    assert "TV_null" not in agent["verdict_reason"]


def test_permutation_parameters_are_mandatory_and_validated(tmp_path):
    """The decision quantile is parameterised by these three. A report computed
    without them would be judging distances against an undeclared null."""
    dirs = _build(tmp_path, {c: [(s, "share") for s in range(1, 5)]
                             for c in ("A", "B", "C")})
    for key in ("permutation_iterations", "permutation_seed", "alpha"):
        bad = THRESH([1, 2], [3, 4])
        del bad[key]
        with pytest.raises(SchemaError) as exc:
            _report(dirs, LOOSE, bad)
        assert key in str(exc.value)
    for value in (0.0, 1.0, -0.1, "0.05", True):
        with pytest.raises(SchemaError):
            _report(dirs, LOOSE, THRESH([1, 2], [3, 4], alpha=value))
    for value in (0, -1, 2.5, True):
        with pytest.raises(SchemaError):
            _report(dirs, LOOSE, THRESH([1, 2], [3, 4],
                                        permutation_iterations=value))


def test_permutation_null_is_deterministic_under_the_frozen_seed(tmp_path):
    """`random.Random(permutation_seed)` only — no global RNG, no numpy — so the
    quantile that decided a verdict regenerates byte-identically."""
    dirs = _build(tmp_path, {"A": _mixed(0), "B": _mixed(16), "C": _mixed(0)})
    first = _report(dirs, _BIG_POLICY, THRESH(_HALF1, _HALF2))
    second = _report(dirs, _BIG_POLICY, THRESH(_HALF1, _HALF2))
    assert canonical_json(first) == canonical_json(second)
    assert (first["per_agent"]["live"]["permutation_null"]
            == second["per_agent"]["live"]["permutation_null"])


# -------------------------------------------------------- 11. self-description

def test_report_is_self_describing(tmp_path):
    dirs = _build(tmp_path, {c: [(s, "share") for s in range(1, 5)]
                             for c in ("A", "B", "C")})
    policy = POLICY(min_admissible_effective_n=2)
    thresholds = THRESH([1, 2], [3, 4])
    rep = _report(dirs, policy, thresholds)
    # bumped 1 -> 2: the split-half noise floor was replaced by a paired
    # permutation null. 2 -> 3: the sensitivity requirement moved to the null
    # branch only. 3 -> 4: the strict sham equivalence warrant and the clause-0
    # evidence-admission contract (replay attestation, frozen terminal probe,
    # surviving-count bound, matched-unit grid). 4 -> 5: the operative null
    # narrowed to DISTRIBUTIONAL — the claim ceiling and verdict vocabulary
    # changed. A consumer must be able to tell which rule produced a verdict;
    # all five can disagree on identical evidence.
    assert rep["order_report_version"] == ORDER_REPORT_VERSION == "5"
    assert rep["admissibility_version"] == DECISION_ADMISSIBILITY_VERSION
    assert rep["policy_version"] == "1"
    assert rep["admissibility_policy"] == policy
    assert rep["thresholds"] == thresholds
    assert len(rep["policy_hash"]) == 64 and len(rep["thresholds_hash"]) == 64
    # METRICS-v1 definitions did not move: the new artifact carries its OWN version
    assert rep["metrics_version"] == METRICS_VERSION == "1"
    # v5 self-description: the operative distributional null, the per-unit-claim
    # limitation, the frozen probe, and the recorded replay gate
    assert rep["null_form"] == "distributional"
    assert "marginal" in rep["per_unit_claim_limitation"]
    assert "P(Y|A)" in rep["per_unit_claim_limitation"]
    assert rep["terminal_dp_id"] == TERMINAL
    assert rep["replay_verification"] == {"attestation_version": "1",
                                          "verified_run_n": 12}
    assert rep["surviving_counts"] is None       # not declared by this caller


# ------------------------------------------- 12. Phase-1 no-op / frozen instrument

def test_phase1_scripted_evidence_agrees_with_the_frozen_comparator(tmp_path):
    """On clean deterministic evidence — scripted nodes, no parser, therefore zero
    non-decisions — the new path must agree with the old one. The successor changes
    what happens to ARTIFACTS, not what happens to real decisions."""
    plan = {"A": [(1, "share"), (2, "share"), (3, "verify"), (4, "verify")],
            "B": [(1, "verify"), (2, "verify"), (3, "verify"), (4, "verify")],
            "C": [(1, "share"), (2, "share"), (3, "verify"), (4, "verify")]}
    dirs = _build(tmp_path, plan, scripted=True)

    old = scramble_terminal_distribution(dirs, CONDITIONS)["per_agent"]["live"]
    new = _report(dirs, POLICY(min_admissible_effective_n=2),
                  THRESH([1, 2], [3, 4]))["per_agent"]["live"]

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
