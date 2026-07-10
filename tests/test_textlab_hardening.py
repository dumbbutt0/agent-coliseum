"""Day-4 hardening regressions — one section per Codex review finding (2026-07-10).
Every test here reproduces a reviewed failure and proves it fixed."""
import json
import os
import shutil
import urllib.request

import pytest

import coliseum.textlab.agents as agents_mod
from coliseum.textlab.agents import MockLLMAgent, OllamaAgent, parse_llm_response
from coliseum.textlab.metrics import aggregate, compute_run_metrics
from coliseum.textlab.runner import run_scenario
from coliseum.textlab.scenario import lint_twin_pair, load_scenario, structural_issues
from coliseum.textlab.schema import SchemaError, canonical_json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCEN = lambda name: os.path.join(ROOT, "configs", "scenarios", f"{name}.yaml")
CK = SCEN("corrupt_king")


class A:  # minimal action stub for parser tests
    def __init__(self, aid): self.action_id, self.label = aid, aid


def read_nodes(run_dir):
    out = []
    with open(os.path.join(run_dir, "decisions.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            ev = json.loads(line)
            if ev["kind"] == "decision_node":
                out.append(ev["data"])
    return out


# ---------------------------------------------------- finding 1: admission + keys

def test_non_reportable_runs_excluded_from_aggregate(tmp_path, monkeypatch):
    monkeypatch.setattr(MockLLMAgent, "_fetch_broken", True, raising=False)
    good = run_scenario(CK, "llm:mock:steward_obedient", 42, str(tmp_path / "g"))

    real_init = MockLLMAgent.__init__
    def broken_digest_init(self, fixture):
        real_init(self, fixture)
        self.model_digest, self.digest_status = "", "missing"
    monkeypatch.setattr(MockLLMAgent, "__init__", broken_digest_init)
    bad = run_scenario(CK, "llm:mock:steward_obedient", 7, str(tmp_path / "b"))

    agg = aggregate([good.run_dir, bad.run_dir])
    assert agg["admission"] == "deterministic_admitted_only"
    assert bad.run_dir.split(os.sep)[-1] in [e["report_id"] for e in agg["excluded"]]
    assert all("nodigest" not in k for k in agg["cells"])          # bad run's cell absent
    diag = aggregate([good.run_dir, bad.run_dir], include_non_reportable=True)
    assert diag["admission"] == "diagnostics_includes_non_reportable"
    assert any("nodigest" in k for k in diag["cells"])


def test_different_digests_never_pool(tmp_path, monkeypatch):
    fixdir = tmp_path / "fx"; fixdir.mkdir()
    shutil.copy(os.path.join(ROOT, "tests/fixtures/llm/steward_obedient.json"),
                fixdir / "steward_obedient.json")
    monkeypatch.setattr(agents_mod, "_fixtures_root", lambda: str(fixdir))
    a = run_scenario(CK, "llm:mock:steward_obedient", 42, str(tmp_path / "a"))
    fix = json.load(open(fixdir / "steward_obedient.json"))
    fix["responses"]["default"] = fix["responses"]["default"].replace("0.3", "0.31")
    (fixdir / "steward_obedient.json").write_text(json.dumps(fix))
    b = run_scenario(CK, "llm:mock:steward_obedient", 42, str(tmp_path / "b"))
    agg = aggregate([a.run_dir, b.run_dir])
    assert len(agg["cells"]) == 2                                   # digest is in the cell key


def test_different_arbitration_never_pools(tmp_path):
    a = run_scenario(CK, "scripted:obedient", 42, str(tmp_path / "a"))
    b = run_scenario(CK, "scripted:obedient", 42, str(tmp_path / "b"),
                     arbitration="reflex_under_time_pressure")
    agg = aggregate([a.run_dir, b.run_dir])
    assert len(agg["cells"]) == 2
    assert {c["arbitration"] for c in agg["cells"].values()} == {
        "planner_priority", "reflex_under_time_pressure"}


# ---------------------------------------------------- finding 2: offline replay

def _fake_ollama_live_run(tmp_path, monkeypatch, seed=42):
    """An Ollama-shaped live run with zero network: injected digest + canned responses."""
    responses = json.load(open(os.path.join(ROOT, "tests/fixtures/llm/steward_obedient.json")))["responses"]

    def fake_fetch(self):
        self.model_digest, self.model_family, self.digest_status = "sha256:deadbeef", "llama", "ok"
    calls = {"n": 0}
    def fake_generate(self, prompt, budget):
        calls["n"] += 1
        key = f"{self._current_prompt_key}"
        return responses.get(key, responses["default"]), 123.0
    def fake_pass(self, state, actions, deliberate):
        self._current_prompt_key = f"{state.get('dp_id','')}/{'plan' if deliberate else 'reflex'}"
        return agents_mod.LLMAgent._pass(self, state, actions, deliberate)

    monkeypatch.setattr(OllamaAgent, "_fetch_digest", fake_fetch)
    monkeypatch.setattr(OllamaAgent, "_generate", fake_generate)
    monkeypatch.setattr(OllamaAgent, "_pass", fake_pass)
    return run_scenario(CK, "llm:ollama:fakellama:8b", seed, str(tmp_path / "live")), calls


def test_ollama_replay_fully_offline(tmp_path, monkeypatch):
    live, _ = _fake_ollama_live_run(tmp_path, monkeypatch)
    monkeypatch.undo()
    # ANY network use during replay is a hard failure
    def no_network(*a, **k):
        raise AssertionError("network contacted during replay")
    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    replayed = run_scenario(CK, "llm:ollama:fakellama:8b", 42, str(tmp_path / "rp"),
                            replay_from=live.run_dir)
    assert replayed.run_id == live.run_id                           # stored spec reproduces lineage
    with open(os.path.join(live.run_dir, "decisions.jsonl"), "rb") as f1, \
         open(os.path.join(replayed.run_dir, "decisions.jsonl"), "rb") as f2:
        assert f1.read() == f2.read()
    rj = json.load(open(os.path.join(replayed.run_dir, "run.json")))
    assert rj["agent_config"]["model_digest"] == "sha256:deadbeef"  # from manifest, not live lookup


def test_replay_detects_corrupted_captures(tmp_path, monkeypatch):
    live, _ = _fake_ollama_live_run(tmp_path, monkeypatch)
    monkeypatch.undo()
    cap = os.path.join(live.run_dir, "captures.jsonl")
    data = open(cap, encoding="utf-8").read().replace("execute", "exexute", 1)
    open(cap, "w", encoding="utf-8").write(data)
    with pytest.raises(SchemaError, match="capture evidence corrupted"):
        run_scenario(CK, "llm:ollama:fakellama:8b", 42, str(tmp_path / "rp"),
                     replay_from=live.run_dir)


# ---------------------------------------------------- finding 3: evidence preservation

def test_live_attempts_never_overwrite(tmp_path, monkeypatch):
    latencies = iter([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0])
    orig = MockLLMAgent._generate
    monkeypatch.setattr(MockLLMAgent, "_generate",
                        lambda self, p, b: (orig(self, p, b)[0], next(latencies)))
    a = run_scenario(CK, "llm:mock:steward_obedient", 42, str(tmp_path))
    b = run_scenario(CK, "llm:mock:steward_obedient", 42, str(tmp_path))
    assert a.run_id == b.run_id                                     # same config identity
    assert a.run_dir != b.run_dir                                   # different evidence dirs
    assert a.run_dir.endswith(".a1") and b.run_dir.endswith(".a2")
    assert read_nodes(a.run_dir)[0]["reflex_latency_ms"] == 1.0     # first attempt intact
    assert read_nodes(b.run_dir)[0]["reflex_latency_ms"] == 101.0
    assert json.load(open(os.path.join(b.run_dir, "run.json")))["attempt"] == 2


def test_scripted_rerun_verifies_but_collision_refused(tmp_path):
    a = run_scenario(CK, "scripted:obedient", 42, str(tmp_path))
    first = open(os.path.join(a.run_dir, "decisions.jsonl"), "rb").read()
    b = run_scenario(CK, "scripted:obedient", 42, str(tmp_path))    # verification rerun: allowed
    assert b.run_dir == a.run_dir
    assert open(os.path.join(b.run_dir, "decisions.jsonl"), "rb").read() == first
    # forge a different config under the same path -> refused
    manifest = os.path.join(a.run_dir, "run.json")
    forged = json.load(open(manifest)); forged["config_hash"] = "f" * 64
    json.dump(forged, open(manifest, "w"))
    with pytest.raises(SchemaError, match="collision REFUSED"):
        run_scenario(CK, "scripted:obedient", 42, str(tmp_path))


# ---------------------------------------------------- finding 4: arbitration winner

def _pressured_scenario(tmp_path):
    import yaml
    raw = yaml.safe_load(open(CK, encoding="utf-8"))
    raw["decision_points"][1]["time_pressure"] = 3
    p = tmp_path / "ck_p.yaml"
    p.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return str(p)


def test_winner_recorded_not_inferred_same_action(tmp_path, monkeypatch):
    """Codex's exact case: valid reflex + fallback planner choosing the SAME action
    under reflex_under_time_pressure -> winner is the valid reflex, node VALID."""
    scen = _pressured_scenario(tmp_path)
    orig = MockLLMAgent._generate
    def planner_garbage(self, prompt, budget):
        raw, lat = orig(self, prompt, budget)
        return ("total garbage no json" if "IMMEDIATELY" not in prompt else raw), lat
    monkeypatch.setattr(MockLLMAgent, "_generate", planner_garbage)
    r = run_scenario(scen, "llm:mock:garbled", 42, str(tmp_path / "runs"),
                     arbitration="reflex_under_time_pressure")
    nodes = read_nodes(r.run_dir)
    d2 = nodes[1]   # tp=3 -> reflex wins; garbled d2 reflex = default (valid execute);
                    # planner = garbage fallback -> ALSO execute. Same action, one valid.
    assert d2["reflex_choice"]["action_id"] == d2["planner_choice"]["action_id"] == "execute"
    assert d2["reflex_choice"]["meta"]["parse_status"] == "ok"
    assert d2["planner_choice"]["meta"]["fallback"] is True
    assert d2["arbitration_winner"] == "reflex"                     # recorded, not inferred
    m = compute_run_metrics(r.run_dir)["metrics"]
    assert m["valid_decision_rate"]["n"] == 3                       # d2 counts as VALID
    node_valid_flags = [n["arbitration_winner"] != "fallback" for n in nodes]
    assert node_valid_flags[1] is True


def test_fallback_winner_labeled_and_excluded(tmp_path):
    r = run_scenario(CK, "llm:mock:garbled", 42, str(tmp_path))     # planner_priority
    nodes = read_nodes(r.run_dir)
    assert nodes[0]["arbitration_winner"] == "fallback"             # planner invalid_action won
    assert nodes[1]["arbitration_winner"] == "fallback"
    assert nodes[2]["arbitration_winner"] == "planner"
    m = compute_run_metrics(r.run_dir)["metrics"]
    assert m["compliance_rate"]["n"] == 1                           # only the valid node scores


# ---------------------------------------------------- finding 5: numeric hardening

ACTIONS = [A("execute"), A("refuse")]

@pytest.mark.parametrize("raw", [
    '{"action": "execute", "confidence": NaN, "reason": "x", "expected_reward": 0}',
    '{"action": "execute", "confidence": "NaN", "reason": "x", "expected_reward": 0}',
    '{"action": "execute", "confidence": 0.5, "reason": "x", "expected_reward": Infinity}',
    '{"action": "execute", "confidence": 0.5, "reason": "x", "expected_reward": "-Infinity"}',
])
def test_non_finite_numerics_become_parse_failures(raw):
    choice, status = parse_llm_response(raw, ACTIONS)
    assert choice is None and status == "parse_failure"


def test_non_mapping_json_rejected():
    choice, status = parse_llm_response('[1, 2, 3]', ACTIONS)
    assert choice is None and status == "parse_failure"


def test_decoder_scan_recovers_first_valid_object():
    two = ('{"note": "not an answer"} '
           '{"action": "refuse", "confidence": 0.9, "reason": "n", "expected_reward": 0}')
    choice, status = parse_llm_response(two, ACTIONS)
    assert status == "invalid_action"      # first valid MAPPING wins deterministically
    junk_then_valid = ('{oops not json} '
                       '{"action": "refuse", "confidence": 0.9, "reason": "n", "expected_reward": 0}')
    choice, status = parse_llm_response(junk_then_valid, ACTIONS)
    assert status == "ok" and choice.action_id == "refuse"          # greedy regex used to collapse this


def test_canonical_json_refuses_nan():
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})


def test_nan_response_never_crashes_a_run(tmp_path, monkeypatch):
    orig = MockLLMAgent._generate
    monkeypatch.setattr(MockLLMAgent, "_generate", lambda self, p, b:
                        ('{"action": "execute", "confidence": NaN, "expected_reward": NaN}', 0.0))
    r = run_scenario(CK, "llm:mock:steward_obedient", 42, str(tmp_path))
    assert r.run.status == "completed"                              # fallback data, no SchemaError
    assert all(n["arbitration_winner"] == "fallback" for n in read_nodes(r.run_dir))


# ---------------------------------------------------- finding 6: paired deltas, logs-only

def test_aggregate_is_function_of_logs_alone(tmp_path, monkeypatch):
    dirs = []
    for scen in ("corrupt_king", "corrupt_king_harmless"):
        dirs.append(run_scenario(SCEN(scen), "scripted:merciful", 1, str(tmp_path / scen)).run_dir)
    a = canonical_json(aggregate(dirs))
    monkeypatch.chdir(tmp_path)                                     # config YAMLs now unreachable
    b = canonical_json(aggregate(dirs))
    assert a == b
    assert any(k.startswith("corrupt_king_vs_corrupt_king_harmless|scripted:merciful|nodigest|planner_priority")
               for k in aggregate(dirs)["control_twin_delta"])       # wiring came from provenance


def test_unpaired_runs_excluded_not_subtracted(tmp_path):
    dirs = [run_scenario(SCEN("corrupt_king"), "scripted:merciful", s,
                         str(tmp_path / f"p{s}")).run_dir for s in (1, 2)]
    dirs.append(run_scenario(SCEN("corrupt_king_harmless"), "scripted:merciful", 1,
                             str(tmp_path / "c1")).run_dir)         # only seed 1 has a twin
    agg = aggregate(dirs)
    hits = [k for k in agg["control_twin_delta"] if k.startswith("corrupt_king_vs_corrupt_king_harmless|scripted:merciful")]
    d = agg["control_twin_delta"][hits[0]]
    assert d["matched_pairs"] == 1
    assert len(d["unmatched_primary_sampler_seeds"]) <= 1   # deterministic: seeds are None
    assert d["excluded_attempts"] == 0
    assert d["pair_provenance"]["control_of"] == "corrupt_king"
    assert d["pair_provenance"]["twin_mapping_version"]


# ---------------------------------------------------- finding 7: twin structural lint

def test_clean_twins_lint_clean():
    for primary, twin in (("water_bearer", "water_bearer_saboteur"),
                          ("hidden_objective", "hidden_objective_aligned")):
        issues = lint_twin_pair(load_scenario(SCEN(primary)), load_scenario(SCEN(twin)))
        assert structural_issues(issues) == [], f"{twin}: {issues}"
    # the water_bearer harm-tag difference is the manipulated variable: a NOTE, not a violation
    wb = lint_twin_pair(load_scenario(SCEN("water_bearer")),
                        load_scenario(SCEN("water_bearer_saboteur")))
    assert any(i.startswith("note:") and "harm" in i for i in wb)


def test_corrupt_king_twins_known_structural_debt():
    """The corrupt_king controls change affordances at d1/d3 — documented debt.
    Whole-run deltas for these pairs are NOT clean; faith analysis is d2-only."""
    ck = load_scenario(CK)
    harmless = lint_twin_pair(ck, load_scenario(SCEN("corrupt_king_harmless")))
    verifiable = lint_twin_pair(ck, load_scenario(SCEN("corrupt_king_verifiable")))
    assert any("cardinality" in i for i in harmless)                # d2/d3 affordances differ
    assert any("cardinality" in i for i in verifiable)              # d3 differs


# ---------------------------------------------------- finding 8: selfish is a control

def test_selfish_labeled_reward_seeking_control(tmp_path):
    r = run_scenario(CK, "scripted:selfish", 42, str(tmp_path))
    run = json.load(open(os.path.join(r.run_dir, "run.json")))
    assert run["agent_config"]["persona_role"] == "reward_seeking_control"
    agg = aggregate([r.run_dir])
    cell = next(iter(agg["cells"].values()))
    assert cell["persona_role"] == "reward_seeking_control"


# ---------------------------------------------------- finding 9: lineage completeness

def test_timeout_budget_in_lineage(tmp_path, monkeypatch):
    a = run_scenario(CK, "llm:mock:steward_obedient", 42, str(tmp_path / "a"))
    monkeypatch.setitem(agents_mod.REFLEX_BUDGET, "timeout_s", 999)
    b = run_scenario(CK, "llm:mock:steward_obedient", 42, str(tmp_path / "b"))
    assert a.run_id != b.run_id                                     # Codex: this used to be invisible


def test_descriptive_metadata_not_in_behavioral_hash(tmp_path):
    import yaml
    raw = yaml.safe_load(open(CK, encoding="utf-8"))
    raw["purpose"] = "totally different words that no agent ever sees"
    raw["metrics_captured"] = ["something_else"]
    p = tmp_path / "corrupt_king.yaml"
    p.write_text(yaml.safe_dump(raw), encoding="utf-8")
    a = run_scenario(CK, "scripted:obedient", 42, str(tmp_path / "a"))
    b = run_scenario(str(p), "scripted:obedient", 42, str(tmp_path / "b"))
    assert a.run_id == b.run_id                                     # prose churn ≠ new lineage


def test_agent_spec_path_escaping_reversible(tmp_path):
    from urllib.parse import unquote
    r = run_scenario(CK, "llm:mock:steward_obedient", 42, str(tmp_path))
    segment = r.run_id.split(".")[2] + "." + r.run_id.split(".")[3]  # quoted spec may contain dots
    # reconstruct: the quoted spec is everything between variant and .s<seed>
    quoted = r.run_id.split(".v0_province.")[1].rsplit(".s42.", 1)[0]
    assert unquote(quoted) == "llm:mock:steward_obedient"
    assert len(r.run_id.rsplit(".", 1)[1]) == 16                    # longer hash segment