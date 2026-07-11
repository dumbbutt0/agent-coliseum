"""M4 experiment registry: the back-filled registry lints clean against
the real evidence; citability requires full validation; frozen entries are
tamper-evident; held-out enforcement is mechanical; every defect class is
refused."""
import copy
import os

import yaml

from coliseum.textlab.registry import (entry_hash,
                                       lint_experiments_registry,
                                       load_experiments_registry)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "configs", "registry", "experiments.yaml")


def test_real_registry_is_clean():
    assert lint_experiments_registry(REGISTRY, ROOT) == []


def test_pre_migration_backups_preserved():
    """Evidence-preservation guard (M4 cycle-2 blocker): every manifest
    migration keeps its .pre-migration original committed. sweep-v2's is
    the ORIGINAL Day-5 backup; exp1/exp2's are from the M4 migration. The
    pilot sweep never migrated (its migration aborts on evidence
    contradictions), so it has no backup by design."""
    for name in ("sweep-v2-manifest", "exp1-gemma3-reversal-manifest",
                 "exp2-v1cistern-manifest"):
        backup = os.path.join(ROOT, "derived", "textlab",
                              f"{name}.jsonl.pre-migration")
        assert os.path.exists(backup), f"missing evidence backup: {backup}"
        assert os.path.getsize(backup) > 0


def test_backfill_shape():
    raw = load_experiments_registry(REGISTRY)
    by_id = {e["experiment_id"]: e for e in raw["experiments"]}
    assert set(by_id) == {"pilot-cross-model-sweep", "sweep-v2",
                          "exp1-gemma3-reversal",
                          "exp2-v1cistern-replication"}
    # demotions preserved honestly; citable entries fully validated
    assert by_id["pilot-cross-model-sweep"]["status"] == "pilot-demoted"
    assert by_id["sweep-v2"]["status"] == "legacy-demoted"
    for eid in ("exp1-gemma3-reversal", "exp2-v1cistern-replication"):
        assert by_id[eid]["status"] == "complete"
        assert by_id[eid]["validation"] == "full"
    assert all(e["frozen"] for e in raw["experiments"])


def _mutated(tmp_path, mutate):
    raw = load_experiments_registry(REGISTRY)
    mutate(raw)
    p = tmp_path / "experiments.yaml"
    p.write_text(yaml.safe_dump(raw, sort_keys=False))
    return lint_experiments_registry(str(p), ROOT)


def test_frozen_entry_mutation_refused(tmp_path):
    def mutate(raw):
        raw["experiments"][2]["finding"] = "a much stronger claim"
    issues = _mutated(tmp_path, mutate)
    assert any("FROZEN entry mutated" in i for i in issues)


def test_frozen_rehash_makes_edit_deliberate(tmp_path):
    """The only way to change a frozen entry is an explicit re-hash — the
    audited-change path."""
    def mutate(raw):
        e = raw["experiments"][2]
        e["finding"] = "amended finding"
        e["entry_hash"] = entry_hash(e)
    issues = _mutated(tmp_path, mutate)
    assert not any("FROZEN entry mutated" in i for i in issues)


def test_citable_status_requires_full_validation(tmp_path):
    def mutate(raw):
        e = raw["experiments"][2]
        e["validation"] = "legacy"
        e["entry_hash"] = entry_hash(e)
    issues = _mutated(tmp_path, mutate)
    assert any("citable status 'complete' requires validation: full" in i
               for i in issues)


def test_row_count_mismatch_refused(tmp_path):
    def mutate(raw):
        e = raw["experiments"][3]
        e["rows"] = 6
        e["entry_hash"] = entry_hash(e)
    issues = _mutated(tmp_path, mutate)
    assert any("declared rows 6 != manifest rows 5" in i for i in issues)


def test_interaction_mode_disagreement_refused(tmp_path):
    def mutate(raw):
        e = raw["experiments"][3]
        e["interaction_mode"] = "sequential_history"
        e["entry_hash"] = entry_hash(e)
    issues = _mutated(tmp_path, mutate)
    assert any("manifest interaction modes" in i for i in issues)


def test_held_out_contamination_refused(tmp_path):
    """Declaring an already-used scenario held-out must fire on every
    manifest that contains it — the SPEC E6 contamination lint."""
    def mutate(raw):
        raw["held_out"]["scenarios"] = ["hidden_objective_aligned"]
    issues = _mutated(tmp_path, mutate)
    assert any("HELD-OUT scenario 'hidden_objective_aligned'" in i
               for i in issues)


def test_duplicate_and_bad_enums_refused(tmp_path):
    def mutate(raw):
        raw["experiments"].append(copy.deepcopy(raw["experiments"][0]))
        raw["experiments"][1]["status"] = "vibes"
        raw["experiments"][1]["generalization_level"] = "L9"
    issues = _mutated(tmp_path, mutate)
    assert any("duplicate experiment entry" in i for i in issues)
    assert any("status 'vibes'" in i for i in issues)
    assert any("generalization_level 'L9'" in i for i in issues)