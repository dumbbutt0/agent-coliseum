"""Day-5 stochastic-readiness regressions — the pre-flight audit's minimal test list
plus the owner's four amendments (full-hash truth, versioned regime, scoped seed
probe, twin pair provenance)."""
import json
import os

import pytest

from coliseum.textlab.agents import MockLLMAgent, OllamaAgent
from coliseum.textlab.metrics import aggregate, compute_run_metrics
from coliseum.textlab.runner import run_scenario
from coliseum.textlab.schema import (SchemaError, build_behavioral_config,
                                     regime_hashes, validate_sampling)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCEN = lambda name: os.path.join(ROOT, "configs", "scenarios", f"{name}.yaml")
CK = SCEN("corrupt_king")
STOCH = {"mode": "stochastic", "temperature": 0.7}


def run_stoch(tmp, sub, sampler_seed, seed=42, fixture="steward_obedient", **kw):
    return run_scenario(CK, f"llm:mock:{fixture}", seed, str(tmp / sub),
                        sampling=dict(STOCH), sampler_seed=sampler_seed, **kw)


# ------------------------------------------------- regime identity (test 1, 2, 6)

def test_temperature_never_pools(tmp_path):
    det = run_scenario(CK, "llm:mock:steward_obedient", 42, str(tmp_path / "d"))
    sto = run_stoch(tmp_path, "s", sampler_seed=1)
    agg = aggregate([det.run_dir, sto.run_dir], mode="deterministic",
                    include_non_reportable=True)   # diagnostics: both admitted, still 2 cells
    assert len(agg["cells"]) == 2
    temps = {c["temperature"] for c in agg["cells"].values()}
    assert temps == {0, 0.7}


def test_regime_from_canonical_object_and_versioned():
    spec = {"agent_id": "x", "model_digest": "sha256:aa"}
    samp = validate_sampling(STOCH, 1)
    bc = build_behavioral_config("scen", "hash1", spec, "planner_priority", "2", samp)
    assert bc["regime_schema_version"] and bc["behavioral_config_schema_version"]
    full, agent_side = regime_hashes(bc)
    assert len(full) == 64 and len(agent_side) == 64          # FULL hashes (amendment 1)
    bc2 = build_behavioral_config("scen", "hash2", spec, "planner_priority", "2", samp)
    assert regime_hashes(bc2)[0] != full                       # scenario_hash changes regime
    assert regime_hashes(bc2)[1] == agent_side                 # ...but not the agent side


def test_changed_scenario_hash_never_pools(tmp_path):
    import yaml
    a = run_scenario(CK, "scripted:obedient", 42, str(tmp_path / "a"))
    raw = yaml.safe_load(open(CK, encoding="utf-8"))
    raw["outcome_rules"]["d1_ledger/stall"]["state_delta"][0]["value"] = -2   # behavioral edit
    p = tmp_path / "corrupt_king.yaml"
    p.write_text(yaml.safe_dump(raw), encoding="utf-8")
    b = run_scenario(str(p), "scripted:obedient", 42, str(tmp_path / "b"))
    agg = aggregate([a.run_dir, b.run_dir])
    assert len(agg["cells"]) == 2


# ------------------------------------------------- sampling provenance (tests 3, 5)

def test_sampler_seed_reaches_backend_payload(tmp_path):
    r = run_stoch(tmp_path, "s", sampler_seed=77)
    caps = [json.loads(l) for l in open(os.path.join(r.run_dir, "captures.jsonl"))]
    assert caps and all(c["backend_payload"]["options"]["seed"] == 77 for c in caps)
    assert all(c["backend_payload"]["options"]["temperature"] == 0.7 for c in caps)
    run = json.load(open(os.path.join(r.run_dir, "run.json")))
    assert run["sampler_seed"] == 77
    assert run["sampling"]["mode"] == "stochastic"
    assert run["behavioral_config"]["decoding"]["sampling_mode"] == "stochastic"
    assert "sampler_seed" not in json.dumps(run["behavioral_config"])   # replicate dim excluded
    assert ".k77." in r.run_id


def test_stochastic_requires_sampler_seed():
    with pytest.raises(SchemaError, match="sampler_seed"):
        validate_sampling(STOCH, None)
    with pytest.raises(SchemaError, match="temperature"):
        validate_sampling({"mode": "stochastic", "temperature": 0}, 1)
    with pytest.raises(SchemaError, match="meaningless"):
        validate_sampling({"mode": "deterministic", "temperature": 0}, 1)


def test_stochastic_admission_and_exclusion_reasons(tmp_path):
    ok = run_stoch(tmp_path, "ok", sampler_seed=5)
    run = json.load(open(os.path.join(ok.run_dir, "run.json")))
    assert run["stochastic_reportable"] is True
    assert run["backend_seed_supported"] is True
    det = run_scenario(CK, "llm:mock:steward_obedient", 42, str(tmp_path / "det"))
    drun = json.load(open(os.path.join(det.run_dir, "run.json")))
    assert drun["stochastic_reportable"] is False
    assert "deterministic_mode" in drun["stochastic_exclusion_reasons"]


def test_unverified_backend_seed_excludes(tmp_path, monkeypatch):
    monkeypatch.setattr(MockLLMAgent, "verify_seeded_sampling",
                        lambda self: setattr(self, "backend_seed_supported", False) or False)
    r = run_stoch(tmp_path, "s", sampler_seed=5)
    run = json.load(open(os.path.join(r.run_dir, "run.json")))
    assert run["stochastic_reportable"] is False
    assert "backend_seed_unverified" in run["stochastic_exclusion_reasons"]
    agg = aggregate([r.run_dir], mode="stochastic")
    assert not agg["cells"]
    assert agg["excluded"][0]["reasons"] == ["backend_seed_unverified"]


def _stub_digest(monkeypatch):
    monkeypatch.setattr(OllamaAgent, "_fetch_digest",
                        lambda self: (setattr(self, "model_digest", "sha256:beef"),
                                      setattr(self, "digest_status", "ok")))
    monkeypatch.setattr(OllamaAgent, "_backend_version", lambda self: "0.9.9")


def test_ollama_seed_probe_is_scoped_record(tmp_path, monkeypatch):
    """Amendment 3: the probe stores a scoped verification record, not a universal claim.

    M8 correction: this test previously drove the probe with a CONSTANT backend
    (`iter(["ready", "ready"])`) and asserted it verified. That fixture is a
    backend which ignores `options.seed` entirely, so asserting True for it
    pinned the exact false pass the two-arm probe now exists to reject — the old
    probe compared same-seed calls only, and "ready" satisfied it trivially. The
    scoped-record intent above is unchanged and every original assertion is
    retained; only the fixture is corrected to a backend that HONORS the seed,
    which is what the probe is entitled to call verified. The rejection case the
    old fixture masked is pinned in the companion test below. No assertion was
    removed or loosened.
    """
    _stub_digest(monkeypatch)
    # honors the seed: same seed -> same text, different seed -> different text
    monkeypatch.setattr(OllamaAgent, "_post",
                        lambda self, p, n, t, options_override=None:
                        {"response": f"nonsense-{(options_override or {}).get('seed')}"})
    agent = OllamaAgent("fake:1b")
    agent.configure_sampling(STOCH, 3)
    assert agent.verify_seeded_sampling() is True
    probe = agent.seed_probe
    assert probe["seed_probe_result"] == "verified"
    assert probe["backend_name"] == "ollama" and probe["backend_version"] == "0.9.9"
    assert probe["model_digest"] == "sha256:beef"
    assert probe["seed_probe_prompt_hash"] and probe["seed_probe_timestamp"]


def test_ollama_seed_probe_rejects_seed_ignoring_backend(tmp_path, monkeypatch):
    """The false pass the previous fixture encoded: a backend returning constant
    text regardless of seed cannot support seeded replication, so it must FAIL
    the divergence arm rather than be recorded as verified. sampler_seed enters
    both the effective-unit key and run_hash, so a silently-ignored seed would
    dress anonymous randomness as identified replicates."""
    _stub_digest(monkeypatch)
    monkeypatch.setattr(OllamaAgent, "_post",
                        lambda self, p, n, t, options_override=None: {"response": "ready"})
    agent = OllamaAgent("fake:1b")
    agent.configure_sampling(STOCH, 3)
    assert agent.verify_seeded_sampling() is False
    assert agent.backend_seed_supported is False
    arms = {a["arm"]: a["outcome"] for a in agent.seed_probe["seed_probe_arms"]}
    assert arms["same_seed_reproducibility"] == "pass"   # constant text IS reproducible
    assert arms["different_seed_divergence"] == "fail"   # ...but never diverges


# ------------------------------------------------- counting (tests 4, 8)

def test_attempts_do_not_inflate_effective_n(tmp_path):
    a = run_stoch(tmp_path, "runs", sampler_seed=9)
    b = run_stoch(tmp_path, "runs", sampler_seed=9)     # retry: new attempt dir
    assert a.run_dir != b.run_dir
    agg = aggregate([a.run_dir, b.run_dir], mode="stochastic")
    cell = next(iter(agg["cells"].values()))
    c = cell["counts"]
    assert c["raw_attempt_n"] == 2
    assert c["retry_n"] == 1
    assert c["unique_sampler_seed_n"] == 1
    assert c["effective_n"] == 1                        # retries are NOT observations
    assert cell["metrics"]["compliance_rate"]["n"] == 1


def test_scenario_seeds_are_not_samples(tmp_path):
    dirs = [run_scenario(CK, "llm:mock:steward_obedient", s, str(tmp_path / "runs")).run_dir
            for s in (1, 2, 3, 5, 8)]
    agg = aggregate(dirs, mode="deterministic")
    c = next(iter(agg["cells"].values()))["counts"]
    assert c["unique_scenario_seed_n"] == 5
    assert c["unique_variant_n"] == 2
    assert c["effective_n"] == 2                        # temp-0: variants ARE the observations
    assert c["unique_sampler_seed_n"] == 0


# ------------------------------------------------- twin pairing (test 7)

def test_twin_pairing_exact_sampler_seed_match(tmp_path):
    dirs = []
    for k in (1, 2, 3):
        dirs.append(run_scenario(SCEN("corrupt_king"), "llm:mock:steward_obedient", 42,
                                 str(tmp_path / "p"), sampling=dict(STOCH), sampler_seed=k).run_dir)
    dirs.append(run_scenario(SCEN("corrupt_king_verifiable"), "llm:mock:steward_obedient", 42,
                             str(tmp_path / "c"), sampling=dict(STOCH), sampler_seed=1).run_dir)
    agg = aggregate(dirs, mode="stochastic")
    pair = next(iter(agg["control_twin_delta"].values()))
    assert pair["matched_pairs"] == 1                    # only k=1 has a twin
    assert pair["unmatched_primary_sampler_seeds"] == [2, 3]
    assert pair["unmatched_control_sampler_seeds"] == []
    prov = pair["pair_provenance"]                       # amendment 4
    assert prov["primary_scenario_hash"] != prov["control_scenario_hash"]
    assert prov["control_of"] == "corrupt_king"
    assert prov["twin_mapping_version"]
    assert prov["action_correspondence_hash"]            # snapshots present -> provable mapping


def test_attempts_do_not_create_pairs(tmp_path):
    for _ in range(2):                                   # 2 attempts, same replicate
        run_scenario(SCEN("corrupt_king"), "llm:mock:steward_obedient", 42,
                     str(tmp_path / "p"), sampling=dict(STOCH), sampler_seed=1)
    run_scenario(SCEN("corrupt_king_verifiable"), "llm:mock:steward_obedient", 42,
                 str(tmp_path / "c"), sampling=dict(STOCH), sampler_seed=1)
    dirs = [os.path.join(str(tmp_path / d), n) for d in ("p", "c")
            for n in sorted(os.listdir(tmp_path / d))]
    agg = aggregate(dirs, mode="stochastic")
    pair = next(iter(agg["control_twin_delta"].values()))
    assert pair["matched_pairs"] == 1
    assert pair["excluded_attempts"] == 1                # the retry never became a pair


# ------------------------------------------------- modes (test 10 + step 8)

def test_mode_admission_refusals(tmp_path):
    det = run_scenario(CK, "llm:mock:steward_obedient", 42, str(tmp_path / "d"))
    sto = run_stoch(tmp_path, "s", sampler_seed=1)
    stoch_agg = aggregate([det.run_dir, sto.run_dir], mode="stochastic")
    assert len(stoch_agg["cells"]) == 1                  # deterministic run refused
    assert any("deterministic_mode" in e["reasons"] for e in stoch_agg["excluded"])
    det_agg = aggregate([det.run_dir, sto.run_dir], mode="deterministic")
    assert len(det_agg["cells"]) == 1                    # stochastic run refused
    assert any("stochastic_mode" in e["reasons"] for e in det_agg["excluded"])


def test_full_grid_reports_replicate_matrix(tmp_path):
    dirs = []
    for k in (1, 2):
        for s in (1, 2):
            dirs.append(run_scenario(CK, "llm:mock:steward_obedient", s, str(tmp_path / "r"),
                                     sampling=dict(STOCH), sampler_seed=k).run_dir)
    agg = aggregate(dirs, mode="full-grid")
    cell = next(iter(agg["cells"].values()))
    assert len(cell["grid"]) == 4                        # 2 variants x 2 sampler seeds
    assert cell["counts"]["effective_n"] == 4
    assert cell["counts"]["unique_sampler_seed_n"] == 2


def test_legacy_runs_cannot_enter_stochastic_comparison(tmp_path):
    """Runs without sampling metadata (pre-Day-5) are deterministic-only by default."""
    r = run_scenario(CK, "scripted:obedient", 42, str(tmp_path))
    manifest = os.path.join(r.run_dir, "run.json")
    run = json.load(open(manifest))
    for k in ("sampling", "sampler_seed", "stochastic_reportable",
              "stochastic_exclusion_reasons", "scenario_seed"):
        run.pop(k, None)                                 # simulate a legacy manifest
    json.dump(run, open(manifest, "w"))
    agg = aggregate([r.run_dir], mode="stochastic")
    assert not agg["cells"]
    assert agg["excluded"][0]["reasons"] == ["legacy_no_sampling_metadata"]


# ------------------------------------------------- replay (test 9)

def test_stochastic_replay_offline_byte_identical(tmp_path, monkeypatch):
    import urllib.request
    live = run_stoch(tmp_path, "live", sampler_seed=13)
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("network in replay")))
    replayed = run_scenario(CK, "llm:mock:steward_obedient", 999,  # wrong seed on purpose:
                            str(tmp_path / "rp"), replay_from=live.run_dir)  # manifest must win
    assert replayed.run_id == live.run_id
    with open(os.path.join(live.run_dir, "decisions.jsonl"), "rb") as f1, \
         open(os.path.join(replayed.run_dir, "decisions.jsonl"), "rb") as f2:
        assert f1.read() == f2.read()
    rj = json.load(open(os.path.join(replayed.run_dir, "run.json")))
    assert rj["sampler_seed"] == 13                      # stored sampling, not current defaults
    assert rj["sampling"]["temperature"] == 0.7


def test_replay_survives_yaml_edit_via_snapshot(tmp_path):
    import yaml
    live = run_scenario(CK, "llm:mock:steward_obedient", 42, str(tmp_path / "live"))
    raw = yaml.safe_load(open(CK, encoding="utf-8"))
    raw["variants"][0]["intro"] = "A completely different opening paragraph."
    edited = tmp_path / "corrupt_king.yaml"
    edited.write_text(yaml.safe_dump(raw), encoding="utf-8")
    # replay pointed at the EDITED yaml: the stored snapshot must win
    replayed = run_scenario(str(edited), "llm:mock:steward_obedient", 42,
                            str(tmp_path / "rp"), replay_from=live.run_dir)
    assert replayed.run_id == live.run_id
    with open(os.path.join(live.run_dir, "decisions.jsonl"), "rb") as f1, \
         open(os.path.join(replayed.run_dir, "decisions.jsonl"), "rb") as f2:
        assert f1.read() == f2.read()


def test_replay_without_snapshot_requires_hash_match(tmp_path):
    import yaml
    live = run_scenario(CK, "llm:mock:steward_obedient", 42, str(tmp_path / "live"))
    os.remove(os.path.join(live.run_dir, "scenario.snapshot.json"))   # simulate legacy
    raw = yaml.safe_load(open(CK, encoding="utf-8"))
    raw["variants"][0]["intro"] = "Changed after the run."
    edited = tmp_path / "corrupt_king.yaml"
    edited.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(SchemaError, match="REPLAY REFUSED"):
        run_scenario(str(edited), "llm:mock:steward_obedient", 42,
                     str(tmp_path / "rp"), replay_from=live.run_dir)