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


def test_three_m6_preregs_present_and_frozen():
    raw = load_experiments_registry(EXPERIMENTS)
    pre = {e["experiment_id"]: e for e in raw["experiments"]
           if e["status"] == "pre-registered"}
    assert set(pre) == {"m6-sequential-rerun", "m6-stochastic-baseline",
                        "m6-paraphrase-replication"}
    for e in pre.values():
        assert e["manifest"] is None
        assert e["design_hash"] == design_hash(e["planned_design"])
        doc = os.path.join(ROOT, e["planned_design"]["prereg_doc"])
        assert os.path.exists(doc)


def test_prereg_is_not_citable_evidence(tmp_path):
    """A pre-registered design has no runs — a claim may not cite it as if
    it were evidence for replication/generalization."""
    claims = yaml.safe_load(open(CLAIMS))
    claims["claims"].append({
        "claim_id": "premature", "state": "replicated",
        "statement": "jumping the gun",
        "evidence": ["m6-sequential-rerun", "m6-paraphrase-replication"]})
    p = tmp_path / "claims.yaml"
    p.write_text(yaml.safe_dump(claims, sort_keys=False))
    issues = lint_claims_registry(str(p), EXPERIMENTS, ROOT)
    assert any("requires >=2 citable" in i for i in issues)


def _mutate(tmp_path, fn):
    raw = load_experiments_registry(EXPERIMENTS)
    fn(raw)
    p = tmp_path / "experiments.yaml"
    p.write_text(yaml.safe_dump(raw, sort_keys=False))
    return lint_experiments_registry(str(p), ROOT)


def test_prereg_design_tamper_refused(tmp_path):
    def fn(raw):
        e = next(x for x in raw["experiments"]
                 if x["experiment_id"] == "m6-sequential-rerun")
        e["planned_design"]["sampler_seeds"] = [11]   # weaken without rehash
    issues = _mutate(tmp_path, fn)
    assert any("design_hash" in i for i in issues)


def test_prereg_with_manifest_refused(tmp_path):
    def fn(raw):
        e = next(x for x in raw["experiments"]
                 if x["experiment_id"] == "m6-stochastic-baseline")
        e["manifest"] = "derived/textlab/sweep-manifest.jsonl"
    issues = _mutate(tmp_path, fn)
    assert any("must have manifest: null" in i for i in issues)


def test_prereg_manifest_must_be_literal_null(tmp_path):
    """Only literal YAML null passes — an empty string or the string
    'null' is a non-null field and must be refused (it would smuggle a
    non-null manifest past the no-runs guard)."""
    for sentinel in ("", "null"):
        def fn(raw, s=sentinel):
            e = next(x for x in raw["experiments"]
                     if x["experiment_id"] == "m6-stochastic-baseline")
            e["manifest"] = s
        issues = _mutate(tmp_path, fn)
        assert any("must have manifest: null" in i for i in issues), sentinel


def test_prereg_unregistered_scenario_refused(tmp_path):
    def fn(raw):
        e = next(x for x in raw["experiments"]
                 if x["experiment_id"] == "m6-sequential-rerun")
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