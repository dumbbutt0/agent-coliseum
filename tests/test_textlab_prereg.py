"""M6 design-freeze: pre-registered experiments (design frozen, not yet run)
lint clean and refuse every defect class; only `complete` experiments are
citable evidence; the ollama pre-check flags an unreachable/incomplete
fleet."""
import copy
import os

import yaml

from coliseum.textlab.registry import (design_hash,
                                       lint_claims_registry,
                                       lint_experiments_registry,
                                       load_experiments_registry)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPERIMENTS = os.path.join(ROOT, "configs", "registry", "experiments.yaml")
CLAIMS = os.path.join(ROOT, "configs", "registry", "claims.yaml")


def test_registry_with_preregs_is_clean():
    assert lint_experiments_registry(EXPERIMENTS, ROOT) == []


def _synth_prereg(eid="synthetic-prereg", scenarios=("corrupt_king",)):
    """A valid pre-registered entry for exercising prereg-lint behavior. The
    real M6 preregs have all run and are now `complete`, so prereg-defect tests
    inject this synthetic design instead of depending on a live prereg."""
    pd = {"hypothesis": "synthetic prereg for lint tests",
          "models": ["gemma3@a2af6cc3"],
          "interaction_mode": "independent_vignettes",
          "scenarios": list(scenarios), "sampler_seeds": [11],
          "temperature": 0.7,
          "prereg_doc":
              "docs/first-gladiator/preregistrations/m6-b1-sequential-rerun.md"}
    return {"experiment_id": eid, "status": "pre-registered",
            "generalization_level": "L2", "manifest": None,
            "planned_design": pd, "design_hash": design_hash(pd)}


def test_all_three_m6_batches_complete_and_frozen():
    """All three M6 batches have now run and are registered complete+frozen
    (B1 sequential-history and B3 paraphrase joined B2); no M6 design remains
    merely pre-registered."""
    raw = load_experiments_registry(EXPERIMENTS)
    by = {e["experiment_id"]: e for e in raw["experiments"]}
    for eid in ("m6-stochastic-baseline", "m6-sequential-rerun",
                "m6-paraphrase-replication"):
        e = by[eid]
        assert e["status"] == "complete" and e["validation"] == "full"
        assert e["frozen"] is True and e.get("entry_hash")
    assert [e["experiment_id"] for e in raw["experiments"]
            if e["status"] == "pre-registered"] == []
    # a pre-registered design still binds its hash to its planned_design
    s = _synth_prereg()
    assert s["design_hash"] == design_hash(s["planned_design"])
    assert os.path.exists(os.path.join(ROOT, s["planned_design"]["prereg_doc"]))


def test_prereg_is_not_citable_evidence(tmp_path):
    """A pre-registered design has no runs — a claim may not cite it as if
    it were evidence for replication/generalization."""
    raw = load_experiments_registry(EXPERIMENTS)
    raw["experiments"] += [_synth_prereg("synthetic-prereg-a"),
                           _synth_prereg("synthetic-prereg-b")]
    ep = tmp_path / "experiments.yaml"
    ep.write_text(yaml.safe_dump(raw, sort_keys=False))
    claims = yaml.safe_load(open(CLAIMS))
    claims["claims"].append({
        "claim_id": "premature", "state": "replicated",
        "statement": "jumping the gun",
        "evidence": ["synthetic-prereg-a", "synthetic-prereg-b"]})
    cp = tmp_path / "claims.yaml"
    cp.write_text(yaml.safe_dump(claims, sort_keys=False))
    issues = lint_claims_registry(str(cp), str(ep), ROOT)
    assert any("requires >=2 citable" in i for i in issues)


def _mutate(tmp_path, fn):
    raw = load_experiments_registry(EXPERIMENTS)
    fn(raw)
    p = tmp_path / "experiments.yaml"
    p.write_text(yaml.safe_dump(raw, sort_keys=False))
    return lint_experiments_registry(str(p), ROOT)


def _append_prereg(raw, eid="synthetic-prereg"):
    e = _synth_prereg(eid)
    raw["experiments"].append(e)
    return e


def test_prereg_design_tamper_refused(tmp_path):
    def fn(raw):
        e = _append_prereg(raw)
        e["planned_design"]["sampler_seeds"] = [11, 12]   # change, no rehash
    issues = _mutate(tmp_path, fn)
    assert any("design_hash" in i for i in issues)


def test_prereg_with_manifest_refused(tmp_path):
    def fn(raw):
        _append_prereg(raw)["manifest"] = "derived/textlab/sweep-manifest.jsonl"
    issues = _mutate(tmp_path, fn)
    assert any("must have manifest: null" in i for i in issues)


def test_prereg_manifest_must_be_literal_null(tmp_path):
    """Only literal YAML null passes — an empty string or the string
    'null' is a non-null field and must be refused (it would smuggle a
    non-null manifest past the no-runs guard)."""
    for sentinel in ("", "null"):
        def fn(raw, s=sentinel):
            _append_prereg(raw)["manifest"] = s
        issues = _mutate(tmp_path, fn)
        assert any("must have manifest: null" in i for i in issues), sentinel


def test_prereg_unregistered_scenario_refused(tmp_path):
    def fn(raw):
        e = _append_prereg(raw)
        e["planned_design"]["scenarios"] = ["no_such_scenario"]
        e["design_hash"] = design_hash(e["planned_design"])   # rehash valid
    issues = _mutate(tmp_path, fn)
    assert any("not in the scenario registry" in i for i in issues)


def test_prereg_held_out_scenario_refused(tmp_path):
    def fn(raw):
        raw["held_out"]["scenarios"] = ["hidden_objective_aligned"]
    issues = _mutate(tmp_path, fn)
    assert any("HELD-OUT" in i for i in issues)


def test_ollama_precheck_unreachable(monkeypatch, capsys):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "precheck", os.path.join(ROOT, "scripts", "ollama_precheck.py"))
    pc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pc)
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:0")
    rc = pc.main()
    assert rc == 1
    assert "UNREACHABLE" in capsys.readouterr().out