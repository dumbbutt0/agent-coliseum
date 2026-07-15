"""Live-persona pilot — unit regressions for the pure, replay-re-derivable
building blocks (parser + failure-taxonomy precedence). The state-dependent
actor-safe-menu leakage and prompt regressions live with the driver slice.

Preregistration: docs/first-gladiator/SOCIETY-LIVE-PERSONA-PILOT.md rev 7.
"""
from coliseum.textlab.society import live


# --- society_numeric_menu.v1 parser (§5) ------------------------------------

def test_parser_in_menu_number():
    assert live.parse_numeric_menu("2", 3) == (2, "ok")


def test_parser_first_digit_run_only():
    # only the FIRST maximal digit run counts; trailing text ignored.
    assert live.parse_numeric_menu("1 then maybe 3", 3) == (1, "ok")


def test_parser_think_wrapped_valid():
    assert live.parse_numeric_menu("<think>7 or 1?</think>2", 3) == (2, "ok")


def test_parser_no_digits():
    assert live.parse_numeric_menu("no menu choice", 3) == (None, "parse_failure")


def test_parser_below_range():
    assert live.parse_numeric_menu("0", 3) == (None, "illegal_selection")


def test_parser_above_range():
    assert live.parse_numeric_menu("9", 3) == (None, "illegal_selection")


def test_parser_boundaries():
    assert live.parse_numeric_menu("1", 3) == (1, "ok")
    assert live.parse_numeric_menu("3", 3) == (3, "ok")


# --- failure-taxonomy precedence (§5): total, mutually exclusive ------------
# N = 3 for every case; the auditor's reproduced overlaps are (a),(b),(c).

def test_taxonomy_length_plus_no_digits_is_budget():
    # (a) truncated + no digit -> budget_exhausted (truncation is primary cause)
    code, parsed, term = live.classify_decision(
        "responded", "no menu choice", "length", 256, 3)
    assert (code, parsed, term) == (
        "budget_exhausted", None, "externally_imposed_truncation")


def test_taxonomy_length_plus_out_of_range_is_budget():
    # (b) truncated + out-of-range digit -> budget_exhausted, NOT illegal_selection
    code, parsed, term = live.classify_decision(
        "responded", "9", "length", 256, 3)
    assert (code, parsed, term) == (
        "budget_exhausted", None, "externally_imposed_truncation")


def test_taxonomy_length_plus_in_menu_is_ok():
    # (c) truncated + valid in-menu digit -> ok (step 1 beats truncation; the
    # parser reads only the first digit run so the tail cannot corrupt it)
    code, parsed, term = live.classify_decision(
        "responded", "2", "length", 256, 3)
    assert (code, parsed, term) == ("ok", 2, None)


def test_taxonomy_eval_cap_alone_triggers_budget():
    # eval_count >= NUM_PREDICT is equivalent to completion_reason == "length"
    code, _p, term = live.classify_decision("responded", "junk", "stop", 256, 3)
    assert code == "budget_exhausted" and term == "externally_imposed_truncation"


def test_taxonomy_untruncated_no_digits_is_parse_failure():
    # (d)
    code, parsed, term = live.classify_decision(
        "responded", "hello", "stop", 12, 3)
    assert (code, parsed, term) == (
        "parse_failure", None, "parse_failure_termination")


def test_taxonomy_untruncated_out_of_range_is_illegal():
    # (e)
    code, parsed, term = live.classify_decision(
        "responded", "9", "stop", 12, 3)
    assert (code, parsed, term) == (
        "illegal_selection", None, "invalid_action_termination")


def test_taxonomy_untruncated_valid_is_ok():
    code, parsed, term = live.classify_decision("responded", "1", "stop", 5, 3)
    assert (code, parsed, term) == ("ok", 1, None)


def test_taxonomy_deadline_exceeded():
    # (f) non-responded: no parse, no re-timing
    code, parsed, term = live.classify_decision(
        "deadline_exceeded", None, None, None, 3)
    assert (code, parsed, term) == (
        "deadline_exceeded", None, "externally_imposed_truncation")


def test_taxonomy_backend_exception():
    # (g)
    code, parsed, term = live.classify_decision(
        "backend_exception", None, None, None, 3)
    assert (code, parsed, term) == (
        "backend_failure_midrun", None, "infrastructure_failure")


def test_taxonomy_single_valued_over_all_responded_shapes():
    # exhaustive: every responded row maps to exactly one of the four codes.
    valid_codes = {"ok", "budget_exhausted", "parse_failure", "illegal_selection"}
    for raw in ["2", "9", "0", "no digits", "<think>2</think>1", ""]:
        for reason in ["stop", "length", None]:
            for ec in [0, 12, 256, None]:
                code, _p, _t = live.classify_decision(
                    "responded", raw, reason, ec, 3)
                assert code in valid_codes


def test_unknown_call_outcome_refuses():
    import pytest
    with pytest.raises(ValueError):
        live.classify_decision("weird", "1", "stop", 1, 3)


def test_frozen_version_constants():
    assert live.PROMPT_VERSION == "society_persona_prompt.v1"
    assert live.PERSONA_PARSER_VERSION == "society_numeric_menu.v1"
    assert live.LIVE_AGENT_KEY == "ada"
    assert live.NUM_PREDICT == 256


# ===========================================================================
# State-dependent regressions: the live driver, capture/replay, leakage,
# control invariants, termination paths, and divergence classification.
# ===========================================================================
import json
import os

import pytest

from coliseum.textlab.spatial.registry import SpatialSpecRegistry
from coliseum.textlab.spatial.scenario import (_society_seed_intents,
                                               build_scenario)
from coliseum.textlab.spatial.run import execute_spatial_run, canonical_effect_id
from coliseum.textlab.spatial.scheduler import (ADVANCE, QUIESCENT, SchedulerRun,
                                                _mk_transition,
                                                action_script_commitment, consume,
                                                initial_scheduler_state, next_step)
from coliseum.textlab.spatial.perception import render_observation_pair
from coliseum.textlab.society.rules import institutional_filter
from coliseum.textlab.schema import canonical_json


def _follower(seed=42, fact=True):
    reg = SpatialSpecRegistry()
    base = build_scenario("society_seed_v1", reg, seed)
    intents = _society_seed_intents(fact)
    return live.ScriptFollowingPersona(intents["ada"], base["ids"])


@pytest.fixture(scope="module")
def mimic_run(tmp_path_factory):
    root = tmp_path_factory.mktemp("live")
    res = live.execute_live_persona_pilot(_follower(), 42, out_root=str(root))
    return res


def _trace_ada(fact=True, ada_intents=None):
    """Step a live-shaped run with ada following ``ada_intents`` (default = the
    scripted ada tail) and bo/cy scripted; yield, at each ada activation,
    (tick, actor_content_json, menu_ids, permitted_ids, menu, actor_content) —
    real substrate states for the leakage regressions."""
    reg = SpatialSpecRegistry()
    base = build_scenario("society_seed_v1", reg, 42)
    intents = _society_seed_intents(fact)
    ada_tail = ada_intents if ada_intents is not None else intents["ada"]
    follower = live.ScriptFollowingPersona(ada_tail, base["ids"])
    control = {"bo": intents["bo"], "cy": intents["cy"]}
    genesis, closure, ids = base["genesis"], base["closure"], base["ids"]
    key_of = {ids[k]: k for k in ("ada", "bo", "cy")}
    probe = SchedulerRun(base["world_line"].id, base["world_line_genesis"].id,
                         action_script_commitment([]), explicit_stop_position=None)
    reg.register(probe)
    cursor = initial_scheduler_state(probe, genesis, reg)
    state = genesis
    pending = {k: list(v) for k, v in control.items()}
    ada_used = 0
    out = []
    while ada_used < live.TICKS:
        step = next_step(cursor, state, closure, reg)
        if step == QUIESCENT:
            break
        if step == ADVANCE:
            t = _mk_transition(state, {"action": "advance_step"}, reg)
            cursor, state = consume(cursor, state, t, closure, reg)
            continue
        if step.content["outcome_kind"] == "pass":
            cursor, state = consume(cursor, state, None, closure, reg)
            continue
        body = step.content["agent_body_id"]
        key = key_of[body]
        tick = step.content["round_index"]
        pos = step.content["scheduler_position"]
        if key == "ada":
            menu = live.actor_safe_menu(body, state, closure, reg, ids)
            actor, _p = render_observation_pair(state, body, closure, reg)
            ac = actor.content["content"]
            out.append((tick, canonical_json(ac),
                        [canonical_effect_id(e) for e in menu],
                        live.actor_permitted_ids(ac), menu, ac))
            d = follower.decide(live.assemble_prompt(ac, menu), menu,
                                {"scheduler_position": pos, "tick": tick})
            k = int(d["raw_completion"])
            eff = menu[k - 1]
            t = _mk_transition(state, eff, reg, actor=body)
            cursor, state = consume(cursor, state, t, closure, reg)
            ada_used += 1
        else:
            if not pending.get(key):
                break
            intent = pending[key].pop(0)
            cands = candidate_effects(body, state, closure, reg)
            cands, _b = institutional_filter(cands, state, ids)
            try:
                eff = live._select_effect(cands, intent, ids)
            except Exception:
                break                            # control desync -> stop tracing
            t = _mk_transition(state, eff, reg, actor=body)
            cursor, state = consume(cursor, state, t, closure, reg)
    return out


from coliseum.textlab.spatial.scheduler import candidate_effects


# --- faithfulness: the replicated spatial write matches the frozen pipeline ---

def test_mimic_spatial_matches_scripted_baseline(mimic_run, tmp_path):
    """A mock-mimics-scripted live run's chain/transitions/observations/
    activations/closure are BYTE-IDENTICAL to a plain society_seed_v1 spatial run
    — proving the new-module spatial write introduces no drift from the frozen
    execute_spatial_run pipeline (only run.json's run_id metadata is the same)."""
    baseline = execute_spatial_run("society_seed_v1", 42, out_root=str(tmp_path))
    base_dir = os.path.join(str(tmp_path), baseline["run_id"])
    for name in ("chain.jsonl", "transitions.jsonl", "observations.jsonl",
                 "activations.jsonl", "closure.json"):
        a = open(os.path.join(mimic_run["run_dir"], name), "rb").read()
        b = open(os.path.join(base_dir, name), "rb").read()
        assert a == b, f"{name} drifted from the frozen pipeline"


def test_mimic_run_is_complete_zero_departure(mimic_run):
    rep = mimic_run["report"]
    assert mimic_run["complete"] and rep["status"] == "complete"
    assert rep["effective_n"] == 8 and rep["per_code_counts"] == {"ok": 8}
    assert rep["behavioral_departure_count"] == 0
    assert rep["observability_restricted_count"] == 0
    assert rep["first_divergence_tick"] is None
    # trust/enforcement match the scripted baseline exactly
    assert all(v == 0 for v in rep["trust_matrix_delta"].values())
    assert rep["enforcement_count_delta"] == 0


def test_zero_call_replay_byte_identical(mimic_run):
    ok, detail = live.replay_live_persona_pilot(mimic_run["run_dir"])
    assert ok, detail


def test_parser_5000_digit_terminates_illegal_with_one_row(tmp_path):
    """audit 001320 HIGH-1 closure: a 5000-digit completion (which would overflow
    Python's int() conversion) is TOTAL -> illegal_selection, terminates the run,
    and writes EXACTLY ONE persona.jsonl row (no crash, no lost decision)."""
    assert live.parse_numeric_menu("9" * 5000, 3) == (None, "illegal_selection")
    # non-truncated (eval_count small, reason 'stop') so the parser's
    # illegal_selection is the decision code, not budget_exhausted; the 5000-digit
    # completion is parsed WITHOUT crashing and one row is captured.
    res = _run_with_plan([{"raw_completion": "9" * 5000,
                           "completion_reason": "stop", "eval_count": 1}], tmp_path)
    assert res["terminated"]["code"] == "illegal_selection"
    assert res["persona_row_count"] == 1
    ok, detail = live.replay_live_persona_pilot(res["run_dir"])
    assert ok, detail
    # and a genuinely truncated 5000-token completion is budget_exhausted (the
    # precedence), still total + one row.
    res2 = _run_with_plan([{"raw_completion": "9" * 5000,
                            "completion_reason": "length", "eval_count": 5000}],
                          tmp_path / "b")
    assert res2["terminated"]["code"] == "budget_exhausted"
    assert res2["persona_row_count"] == 1


def test_complete_report_has_full_measurement_surface(mimic_run):
    """audit 001320 HIGH-3 closure: a complete pack's report carries the
    token-terminal-location delta + the privileged report + the closed-schema
    actor-safe reports for all three agents."""
    from coliseum.textlab.society.run import assert_actor_report_schema
    rep = mimic_run["report"]
    ttd = rep["token_terminal_delta"]
    assert set(ttd) == {"live", "baseline", "differs"} and ttd["differs"] is False
    priv = rep["privileged_report"]
    for k in ("trust_matrix", "trust_updates", "enforcement_trace",
              "enforcement_trace_commitment", "private_facts", "tick_state_ids",
              "token_terminal_location", "claim_ceiling"):
        assert k in priv, f"privileged report missing {k}"
    assert priv["private_facts"] == {"cy": {"gem_in_box": True}}
    assert set(rep["actor_safe_reports"]) == {"ada", "bo", "cy"}
    for a, report in rep["actor_safe_reports"].items():
        assert_actor_report_schema(report)          # closed seed schema
        assert "private_facts" not in report and "enforcement_trace" not in report


def test_regime_fields_mock(mimic_run):
    """audit 001320 HIGH-4 closure (mock-exercised): the report records a regime
    with the actual backend_version + seed_supported + a regime_id, plus the
    preregistered pins — all without a live call."""
    rep = mimic_run["report"]
    reg = rep["regime"]
    assert reg["backend_version"] == "mock" and reg["seed_supported"] is None
    assert reg["model_id"] == "mock-script-follower"
    assert reg["prompt_version"] == "society_persona_prompt.v1"
    assert reg["parser_version"] == "society_numeric_menu.v1"
    assert len(rep["regime_id"]) == 64
    assert rep["preregistered_model_id"] == live.PILOT_MODEL_ID
    assert rep["preregistered_model_digest"] == live.PILOT_MODEL_DIGEST


def test_replay_refuses_dropped_society_layer(mimic_run, tmp_path):
    """audit 001320 HIGH-2 closure: removing society.jsonl from a COMPLETE pack
    must NOT silently pass as a 7-file incomplete replay — the pack shape is
    authenticated from the re-derivation, so a dropped society layer refuses."""
    import shutil
    dst = str(tmp_path / "dropped")
    shutil.copytree(mimic_run["run_dir"], dst)
    os.remove(os.path.join(dst, "society.jsonl"))
    ok, detail = live.replay_live_persona_pilot(dst)
    assert not ok and "society.jsonl" in detail


class _FakeOllamaAgent:
    """A network-free stand-in for OllamaAgent that records the exact options each
    _post receives — for the seed-probe regression (no live backend)."""
    def __init__(self, model, host=None):
        self.model = model
        self.digest_status = "ok"
        self.model_digest = "sha256:" + live.PILOT_MODEL_DIGEST
        self.backend_version = "fake-0.1"
        self.posts = []

    def resolve_effective_config(self):
        pass

    def _post(self, prompt, num_predict, timeout_s, options_override=None):
        self.posts.append(options_override)
        return {"response": "ready", "done_reason": "stop", "eval_count": 1,
                "prompt_eval_count": 3}


def test_ollama_seed_probe_sends_seed_42(monkeypatch):
    """audit 001320 HIGH-1 closure: OllamaPersona's seed probe sends the exact
    frozen pilot options INCLUDING seed 42 (not a seedless probe), and records the
    genuine result before the regime is hashed."""
    import coliseum.textlab.agents as agents_mod
    monkeypatch.setattr(agents_mod, "OllamaAgent", _FakeOllamaAgent)
    p = live.OllamaPersona(host="http://localhost:11434")
    # both probe posts carried temperature 0 + seed 42
    assert len(p._agent.posts) >= 2
    for opts in p._agent.posts[:2]:
        assert opts["seed"] == 42 and opts["temperature"] == 0.0
    assert p.seed_supported is True          # identical output twice
    assert p.backend_version == "fake-0.1"


def test_replay_constructs_no_live_persona(mimic_run, monkeypatch):
    """§6 / threat vector 4: replay re-derives from captures and NEVER invokes the
    model. Poison OllamaPersona so any attempt to build the live backend during
    replay would raise — replay must still succeed byte-identically."""
    def _poison(*a, **k):
        raise AssertionError("replay must not construct a live persona")
    monkeypatch.setattr(live, "OllamaPersona", _poison)
    ok, detail = live.replay_live_persona_pilot(mimic_run["run_dir"])
    assert ok, detail


def test_replay_rejects_tampered_prompt_hash(mimic_run, tmp_path):
    """A tampered persona.jsonl prompt_hash fails the ReplayPersona authentication
    (the re-assembled prompt no longer matches the captured hash)."""
    import shutil
    dst = str(tmp_path / "tampered")
    shutil.copytree(mimic_run["run_dir"], dst)
    rows = [json.loads(l) for l in
            open(os.path.join(dst, "persona.jsonl"), encoding="utf-8") if l.strip()]
    rows[0]["prompt_hash"] = "0" * 64
    with open(os.path.join(dst, "persona.jsonl"), "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(canonical_json(r) + "\n")
    with pytest.raises(Exception):
        live.replay_live_persona_pilot(dst)


# --- leakage regressions (§3): actor-safe menu never leaks hidden state -------

def test_no_menu_or_prompt_names_an_unseen_entity():
    """Two-part leakage (§3), no-unseen-entity half: at EVERY ada activation, every
    id referenced by every menu effect is in ada's actor projection, and the
    assembled prompt never contains an id outside that projection."""
    for tick, _acj, _mids, permitted, menu, ac in _trace_ada():
        for eff in menu:
            for v in live._effect_referenced_ids(eff):
                assert v in permitted, (
                    f"menu effect names unseen id at tick {tick}: {eff}")
        prompt = live.assemble_prompt(ac, menu)
        import re as _re
        for tok in _re.findall(r"[0-9a-f]{64}", prompt):
            assert tok in permitted, (
                f"prompt names unseen id {tok[:12]} at tick {tick}")


from coliseum.textlab.schema import config_hash
from coliseum.textlab.spatial.scheduler import WorldState, admit_world_state

# frozen literals (§3): the template hash + the 8 assembled-prompt hashes at seed
# 42. Any serializer/template drift changes these and refuses.
_FROZEN_TEMPLATE_HASH = \
    "11cfbe5d22446f207f898ebfd2c352a6d13711df39cf1bf1258e1cb305b2e518"
_FROZEN_PROMPT_HASHES = [
    "c7cfa972480557180d7cb7f8b20a2de3b578c86789ac2174ce0ef9f172e5d2c5",
    "23f173848c4cd689cec12530c7bf3efaae9318b159fe413ed11994af3efebfa1",
    "3e348cfb5f1116e97cd94d9de03062bd8d8e9235848f04e59811617c2f356971",
    "10fda4ba4d28426512757cc4805a69b2402a1e41063b276d31d14b74ced55ab9",
    "26388791c93aa4475ba83cb4b358c1e013b9e9b84b498ca1518ccd40af95193a",
    "5b62417aff3edfbb57b070c7fbd657579ec42443fbf70213319d48079fe71a11",
    "9c5b79e80b45c7937c39133aa92438555c4bee69c71b1ab99f5fdc2f3791fb1f",
    "30f2f5bb2a0bed863f95370d9eebe60cf3ad7d19d0c2703fb2a7d9a73e1b3c4d",
]


def test_frozen_prompt_template_hash():
    assert config_hash(live.PROMPT_TEMPLATE) == _FROZEN_TEMPLATE_HASH


def test_eight_assembled_prompt_hashes_pinned(mimic_run):
    """§3: the assembled-prompt config_hash at each of the eight ada activations
    is pinned; any serializer drift refuses."""
    rows = [json.loads(l) for l in open(
        os.path.join(mimic_run["run_dir"], "persona.jsonl"), encoding="utf-8")
        if l.strip()]
    assert [r["prompt_hash"] for r in rows] == _FROZEN_PROMPT_HASHES


def test_privileged_invariance_two_admitted_states():
    """§3 privileged-invariance (two-state form): two ADMITTED states with
    byte-identical ada actor content but DIFFERENT hidden gem containment (gem
    inside the box vs gem free on room C's floor — both invisible to ada in room
    A) yield byte-identical ada actor content AND byte-identical menu ids. A
    privileged-only change therefore cannot alter ada's prompt/menu."""
    reg = SpatialSpecRegistry()
    base = build_scenario("society_seed_v1", reg, 42)
    genesis, closure, ids = base["genesis"], base["closure"], base["ids"]
    ada, gem, room_c = ids["ada"], ids["gem"], ids["room_C"]
    # s2: relocate the (hidden-from-ada) gem from inside the box to the floor of
    # room C — a privileged-only mutation ada in room A cannot perceive.
    placements2 = []
    for p in genesis.content["placements"]:
        if p["entity_id"] == gem:
            p = dict(p, location={"tag": "in_room", "room_instance_id": room_c})
        placements2.append(p)
    s2 = WorldState(genesis.world_line_id, genesis.logical_step, placements2,
                    genesis.content["entity_lifecycle"])
    admit_world_state(s2, reg)
    reg.register(s2)
    assert s2.id != genesis.id, "the privileged mutation must produce a distinct state"
    a1, _ = render_observation_pair(genesis, ada, closure, reg)
    a2, _ = render_observation_pair(s2, ada, closure, reg)
    assert canonical_json(a1.content) == canonical_json(a2.content), \
        "ada actor content changed under a hidden-only mutation"
    m1 = [canonical_effect_id(e) for e in live.actor_safe_menu(ada, genesis, closure, reg, ids)]
    m2 = [canonical_effect_id(e) for e in live.actor_safe_menu(ada, s2, closure, reg, ids)]
    assert m1 == m2, "ada menu changed under a hidden-only mutation (leak)"


def test_hidden_gem_never_appears_when_ada_co_located_with_box():
    """The auditor's reproduced leak (audit 001293), directly refuted: drive ada
    INTO room C so it is co-located with the box whose HIDDEN gem it cannot
    perceive; assert no menu effect and no prompt byte names the gem — even though
    the privileged candidate_effects at that state contains a take_out of the gem.
    A privileged-only change to the gem's containment therefore cannot alter ada's
    menu, because the gem id is filtered out of the actor-safe projection."""
    reg = SpatialSpecRegistry()
    base = build_scenario("society_seed_v1", reg, 42)
    gem = base["ids"]["gem"]
    # ada walks A->B->C (never holding the token, so the institution permits it),
    # reaching room C where the box + hidden gem sit.
    ada_to_c = [("move", "room_B"), ("move", "room_C"), ("move", "room_B"),
                ("move", "room_C"), ("move", "room_B"), ("move", "room_C"),
                ("move", "room_B"), ("move", "room_C")]
    saw_room_c = False
    for tick, _acj, mids, permitted, menu, ac in _trace_ada(ada_intents=ada_to_c):
        prompt = live.assemble_prompt(ac, menu)
        assert gem not in prompt, f"gem id leaked into prompt at tick {tick}"
        assert gem not in permitted, f"gem in permitted set at tick {tick}"
        for eff in menu:
            assert gem not in live._effect_referenced_ids(eff), (
                f"menu names the hidden gem at tick {tick}")
        # detect the co-located-with-box moment (box visible in ada's room)
        box = base["ids"]["box"]
        if box in permitted:
            saw_room_c = True
    assert saw_room_c, "ada never reached the box's room — test did not exercise the leak"


# --- control invariants (§12) ------------------------------------------------

def test_control_pins_unchanged_vs_seed(mimic_run):
    """Divergence-independent artifacts (§12.2/4) equal the seed's: world line,
    genesis state, institution rule, and the six trust-edge keys."""
    from coliseum.textlab.society.run import execute_society_seed
    import tempfile
    seed_run = execute_society_seed(42, out_root=tempfile.mkdtemp())
    live_run_json = json.loads(open(os.path.join(
        mimic_run["run_dir"], "run.json"), encoding="utf-8").read())
    seed_run_json = json.loads(open(os.path.join(
        seed_run["run_dir"], "run.json"), encoding="utf-8").read())
    for k in ("world_line_id", "world_line_genesis_id", "genesis_state_id",
              "topology_closure_hash"):
        assert live_run_json[k] == seed_run_json[k]
    assert live.INSTITUTION_TOKEN_STAYS_IN_A == "institution.token_stays_in_a.v1"


# --- termination paths (§5): a failed decision terminates, no behavioral claim -

def _run_with_plan(plan, tmp_path, fact=True):
    persona = live.MockPersona(plan)
    return live.execute_live_persona_pilot(persona, 42, out_root=str(tmp_path))


def test_parse_failure_terminates_incomplete(tmp_path):
    # ada answers with no digit on its FIRST activation -> parse_failure -> the run
    # terminates (no pass fallback), incomplete pack, no behavioral claim.
    res = _run_with_plan(["no choice here"], tmp_path)
    assert not res["complete"]
    assert res["terminated"]["code"] == "parse_failure"
    assert res["terminated"]["terminal_coding"] == "parse_failure_termination"
    assert res["report"]["status"] == "incomplete"
    assert res["report"]["behavioral_departure_claimable"] is False
    # captures preserved: exactly one persona row at the failed decision
    assert res["persona_row_count"] == 1
    assert not os.path.isfile(os.path.join(res["run_dir"], "society.jsonl"))


def test_deadline_terminates_incomplete(tmp_path):
    res = _run_with_plan([{"call_outcome": "deadline_exceeded"}], tmp_path)
    assert not res["complete"]
    assert res["terminated"]["code"] == "deadline_exceeded"
    assert res["terminated"]["terminal_coding"] == "externally_imposed_truncation"
    row = [json.loads(l) for l in
           open(os.path.join(res["run_dir"], "persona.jsonl"), encoding="utf-8")][0]
    assert row["call_outcome"] == "deadline_exceeded"
    assert row["raw_completion"] is None and row["parse_status"] is None


def test_backend_exception_terminates_incomplete(tmp_path):
    res = _run_with_plan([{"call_outcome": "backend_exception"}], tmp_path)
    assert res["terminated"]["code"] == "backend_failure_midrun"
    assert res["terminated"]["terminal_coding"] == "infrastructure_failure"


def test_incomplete_replays_byte_identical(tmp_path):
    res = _run_with_plan(["9999"], tmp_path)     # illegal_selection at tick 0
    assert res["terminated"]["code"] == "illegal_selection"
    ok, detail = live.replay_live_persona_pilot(res["run_dir"])
    assert ok, detail


# --- divergence classification (§7) -----------------------------------------

def test_behavioral_departure_counted(tmp_path):
    """A persona that picks a DIFFERENT actor-safe menu item at ada's first
    activation than the scripted baseline yields a counted behavioral departure
    (both actions were in ada's actor-safe menu), classified behavioral — not
    observability_restricted. (The run may then terminate on control desync; the
    tick-0 classification is recorded regardless.)"""
    reg = SpatialSpecRegistry()
    base = build_scenario("society_seed_v1", reg, 42)
    menu0 = live.actor_safe_menu(base["ids"]["ada"], base["genesis"],
                                 base["closure"], reg, base["ids"])
    assert len(menu0) >= 2, "need >=2 actor-safe options at tick 0 to force a departure"
    # the scripted baseline picks 'move room_B'; pick the OTHER actor-safe option.
    baseline_id = None
    intents = _society_seed_intents(True)
    for k, e in enumerate(menu0, 1):
        if live._effect_matches_intent(e, intents["ada"][0], base["ids"]):
            baseline_id = k
    other = 1 if baseline_id != 1 else 2
    plan = [str(other)] + ["1"] * 7
    res = _run_with_plan(plan, tmp_path)
    rep = res["report"]
    assert rep["first_divergence_tick"] == 0
    assert rep["per_tick"][0]["classification"] == "behavioral_departure"
    assert rep["behavioral_departure_count"] >= 1


def test_no_actor_safe_action_never_triggers_in_seed():
    """The pre-call no_actor_safe_action terminal (§5) never fires in
    society_seed_v1: ada always has >=1 actor-safe action at every activation."""
    for tick, _acj, mids, *_ in _trace_ada():
        assert len(mids) >= 1, f"empty actor-safe menu at tick {tick}"


def test_live_source_binding_binds_society_for_complete_packs():
    """§6: a COMPLETE pack's LiveSourceEvidenceBinding binds the spatial six +
    society.jsonl + persona.jsonl; an INCOMPLETE pack binds the spatial six +
    persona.jsonl; any other key set (or pack_kind) refuses fail-closed."""
    complete = {n: "0" * 64 for n in live.LIVE_EVIDENCE_FILES_COMPLETE}
    assert "society.jsonl" in complete
    b = live.LiveSourceEvidenceBinding("society_seed_v1--seed42--x", complete,
                                       "complete")
    assert b.content["pack_kind"] == "complete"
    incomplete = {n: "0" * 64 for n in live.LIVE_EVIDENCE_FILES_INCOMPLETE}
    bi = live.LiveSourceEvidenceBinding("x", incomplete, "incomplete")
    assert bi.content["pack_kind"] == "incomplete"
    # complete hashes under 'incomplete' pack_kind (society.jsonl extra) refuses
    with pytest.raises(Exception):
        live.LiveSourceEvidenceBinding("x", complete, "incomplete")
    # a wrong file set refuses
    with pytest.raises(Exception):
        live.LiveSourceEvidenceBinding("x", {"run.json": "0" * 64}, "complete")
    # an unknown pack_kind refuses
    with pytest.raises(Exception):
        live.LiveSourceEvidenceBinding("x", complete, "partial")


def test_complete_pack_binding_includes_society(mimic_run):
    """The executed mimics-scripted (complete) pack's binding is over the complete
    file set including society.jsonl (rebuild the binding from the run dir)."""
    import os as _os
    hashes = {n: live._sha256_file(_os.path.join(mimic_run["run_dir"], n))
              for n in live.LIVE_EVIDENCE_FILES_COMPLETE}
    b = live.LiveSourceEvidenceBinding(mimic_run["run_id"], hashes, "complete")
    assert b.id == mimic_run["live_source_evidence_id"]
