"""M3 scenario registry: the real corpus lints clean, and every defect
class (stale hash, bad family, unregistered scenario, asymmetric twins,
variant mismatch, bad status, duplicates) is refused. The registry's
behavioral_hash is the SAME hash runs pin as scenario_hash — a registry
row can never vouch for changed behavioral content."""
import os
import shutil

import yaml

from coliseum.textlab.scenario import (REGISTRY_FAMILIES, lint_registry,
                                       load_registry, load_scenario)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "configs", "registry", "scenarios.yaml")
CONFIG_DIR = os.path.join(ROOT, "configs", "scenarios")


def test_real_registry_is_clean():
    assert lint_registry(REGISTRY, CONFIG_DIR) == []


def test_registry_covers_whole_corpus_with_spec_families():
    raw = load_registry(REGISTRY)
    ids = {e["scenario_id"] for e in raw["scenarios"]}
    assert len(ids) == 7
    for e in raw["scenarios"]:
        assert e["family"] in REGISTRY_FAMILIES
        assert len(e["variants"]) >= 2
        assert e["status"] == "frozen"   # the audited existing corpus


def test_registry_hash_is_the_run_pinned_hash():
    raw = load_registry(REGISTRY)
    e = next(x for x in raw["scenarios"] if x["scenario_id"] == "corrupt_king")
    s = load_scenario(os.path.join(CONFIG_DIR, "corrupt_king.yaml"))
    assert e["behavioral_hash"] == s.behavioral_hash()


# --------------------------------------------------------- defect classes

def _sandbox(tmp_path, mutate):
    """Copy the real corpus + registry into a sandbox, apply `mutate` to the
    registry dict (or the sandbox itself), and lint."""
    cfg = tmp_path / "configs"
    shutil.copytree(os.path.join(ROOT, "configs", "scenarios"),
                    cfg / "scenarios")
    (cfg / "registry").mkdir()
    raw = load_registry(REGISTRY)
    # rewrite file paths so they resolve inside the sandbox repo root
    mutate(raw, tmp_path)
    reg = cfg / "registry" / "scenarios.yaml"
    reg.write_text(yaml.safe_dump(raw, sort_keys=False))
    return lint_registry(str(reg), str(cfg / "scenarios"))


def test_stale_hash_refused(tmp_path):
    def mutate(raw, _):
        raw["scenarios"][0]["behavioral_hash"] = "0" * 64
    issues = _sandbox(tmp_path, mutate)
    assert any("behavioral_hash mismatch" in i for i in issues)


def test_bad_family_refused(tmp_path):
    def mutate(raw, _):
        raw["scenarios"][0]["family"] = "gladiator_drama"
    issues = _sandbox(tmp_path, mutate)
    assert any("not one of the SPEC's eight" in i for i in issues)


def test_unregistered_scenario_refused(tmp_path):
    def mutate(raw, _):
        raw["scenarios"] = [e for e in raw["scenarios"]
                            if e["scenario_id"] != "water_bearer_saboteur"]
        # drop the dangling twin link so ONLY completeness fires
        for e in raw["scenarios"]:
            if e["scenario_id"] == "water_bearer":
                e["controls"] = []
    issues = _sandbox(tmp_path, mutate)
    assert any("UNREGISTERED scenario 'water_bearer_saboteur'" in i
               for i in issues)


def test_asymmetric_twin_refused(tmp_path):
    def mutate(raw, _):
        for e in raw["scenarios"]:
            if e["scenario_id"] == "corrupt_king":
                e["controls"] = ["corrupt_king_harmless"]  # drops verifiable
    issues = _sandbox(tmp_path, mutate)
    assert any("controls list missing 'corrupt_king_verifiable'" in i
               for i in issues)


def test_variant_mismatch_refused(tmp_path):
    def mutate(raw, _):
        raw["scenarios"][0]["variants"] = ["v0_province"]
    issues = _sandbox(tmp_path, mutate)
    assert any("registry variants" in i for i in issues)


def test_bad_status_refused(tmp_path):
    def mutate(raw, _):
        raw["scenarios"][0]["status"] = "believed_fine"
    issues = _sandbox(tmp_path, mutate)
    assert any("status 'believed_fine'" in i for i in issues)


def test_duplicate_entry_refused(tmp_path):
    def mutate(raw, _):
        raw["scenarios"].append(dict(raw["scenarios"][0]))
    issues = _sandbox(tmp_path, mutate)
    assert any("duplicate registry entry" in i for i in issues)