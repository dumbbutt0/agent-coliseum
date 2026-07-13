"""T0-A dataset export: a provenance-complete, non-pooled descriptor + content-addressed commitment
+ descriptive card, built by reusing the audited admission/retry-collapse/effective-unit pipeline.
Structural only — no normative labels, no partitioning, no training."""
import json
import os

import pytest

from coliseum.textlab.dataset_export import (
    DATASET_COMMITMENT_DOMAIN, build_dataset, dataset_card, dataset_commitment)
from coliseum.textlab.runner import run_scenario

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCEN = lambda name: os.path.join(ROOT, "configs", "scenarios", f"{name}.yaml")


def _runs(base):
    # two distinct agent regimes over one scenario -> two NON-POOLED cells
    a = run_scenario(SCEN("corrupt_king"), "scripted:obedient", 42, str(base / "a")).run_dir
    b = run_scenario(SCEN("corrupt_king"), "scripted:defiant", 42, str(base / "b")).run_dir
    return [a, b]


def test_descriptor_nonpooled_effective_units(tmp_path):
    desc = build_dataset(_runs(tmp_path))
    assert desc["effective_unit_count"] == 2                       # never pooled across regimes
    assert {u["scenario_id"] for u in desc["units"]} == {"corrupt_king"}
    assert all(u["effective_n"] >= 1 for u in desc["units"])
    assert desc["dataset_schema_version"] == "1"
    assert desc["excluded"] == [] and desc["attempt_exclusions"] == []


def test_commitment_stable_and_content_addressed(tmp_path):
    # same scripted evidence (deterministic run_ids) -> byte-identical descriptor + commitment
    d1 = build_dataset(_runs(tmp_path / "x"))
    d2 = build_dataset(_runs(tmp_path / "y"))
    assert d1 == d2
    assert d1["dataset_commitment"] == d2["dataset_commitment"]
    # recomputation matches and excludes the commitment field itself
    assert dataset_commitment(d1) == d1["dataset_commitment"]
    assert DATASET_COMMITMENT_DOMAIN == "dataset:commitment:v1"


def test_commitment_changes_with_content(tmp_path):
    one = build_dataset([run_scenario(SCEN("corrupt_king"), "scripted:obedient", 42,
                                      str(tmp_path / "one")).run_dir])
    two = build_dataset(_runs(tmp_path / "two"))
    assert one["dataset_commitment"] != two["dataset_commitment"]


def test_held_out_scenario_refused_by_id_and_hash(tmp_path):
    runs = _runs(tmp_path)
    with pytest.raises(ValueError, match="held-out"):
        build_dataset(runs, held_out_scenarios={"corrupt_king"})
    sh = json.load(open(os.path.join(runs[0], "run.json"), encoding="utf-8"))["scenario_hash"]
    with pytest.raises(ValueError, match="held-out"):
        build_dataset(runs, held_out_hashes={sh})


def test_card_idempotent_and_disciplined(tmp_path):
    desc = build_dataset(_runs(tmp_path))
    card = dataset_card(desc)
    assert card == dataset_card(desc)                             # idempotent
    assert "Dataset Card" in card and desc["dataset_commitment"] in card
    assert "no training" in card                                 # discipline is stated on the card
