"""T0-A training-data admission gate (§8): explicit per-run training-eligibility
decisions with machine-readable rejection reasons, reusing the audited replay /
held-out primitives, and recording the not-yet-evaluable §8 criteria as deferred
(never silently passed). Structural — no labels, no training."""
import json
import os
import shutil

import pytest

from coliseum.textlab import training_admission as A
from coliseum.textlab.dataset_export import build_dataset, dataset_card
from coliseum.textlab.runner import run_scenario

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCEN = lambda name: os.path.join(ROOT, "configs", "scenarios", f"{name}.yaml")


def _runs(base):
    a = run_scenario(SCEN("corrupt_king"), "scripted:obedient", 42,
                     str(base / "a")).run_dir
    b = run_scenario(SCEN("corrupt_king"), "scripted:defiant", 42,
                     str(base / "b")).run_dir
    return [a, b]


def _tamper(run_dir, mutate):
    path = os.path.join(run_dir, "run.json")
    run = json.load(open(path, encoding="utf-8"))
    mutate(run)
    json.dump(run, open(path, "w", encoding="utf-8"))
    return run_dir


# ---------------------------------------------------------- per-run decisions

def test_clean_run_is_admitted(tmp_path):
    a, _b = _runs(tmp_path)
    d = A.admit_run(a)
    assert d["admitted"] and d["rejections"] == []
    assert d["scenario_id"] == "corrupt_king"


def test_provenance_incomplete_rejected(tmp_path):
    a, _b = _runs(tmp_path)
    _tamper(a, lambda r: r.pop("scenario_hash"))
    d = A.admit_run(a)
    assert not d["admitted"]
    assert any("provenance_incomplete:scenario_hash" in x for x in d["rejections"])


def test_held_out_rejected_by_id_and_hash(tmp_path):
    a, _b = _runs(tmp_path)
    assert "held_out" in A.admit_run(a, held_out_ids={"corrupt_king"})["rejections"]
    sh = json.load(open(os.path.join(a, "run.json")))["scenario_hash"]
    assert "held_out" in A.admit_run(a, held_out_hashes={sh})["rejections"]


def test_preregistered_exclusion_rejected(tmp_path):
    a, _b = _runs(tmp_path)
    rid = json.load(open(os.path.join(a, "run.json")))["run_id"]
    assert "preregistered_exclusion" in A.admit_run(a, exclusions={rid})["rejections"]
    assert "preregistered_exclusion" in \
        A.admit_run(a, exclusions={"corrupt_king"})["rejections"]


def test_non_reportable_rejected(tmp_path):
    a, _b = _runs(tmp_path)
    _tamper(a, lambda r: r.__setitem__("reportable", False))
    assert "non_reportable" in A.admit_run(a)["rejections"]


def test_unverified_digest_rejected(tmp_path):
    a, _b = _runs(tmp_path)
    _tamper(a, lambda r: r.__setitem__("digest_status", "unverified"))
    assert any("model_digest_unverified" in x for x in A.admit_run(a)["rejections"])


def test_not_a_run_record_rejected(tmp_path):
    a, _b = _runs(tmp_path)
    _tamper(a, lambda r: r.__setitem__("record_type", "diagnostic"))
    assert any("not_a_run_record" in x for x in A.admit_run(a)["rejections"])


def test_replay_gate_when_required(tmp_path):
    a, _b = _runs(tmp_path)
    # a clean scripted run replays; pointing at a bogus config_dir forces failure
    assert A.admit_run(a, require_replay=True, config_dir="configs/scenarios")["admitted"]
    bad = A.admit_run(a, require_replay=True, config_dir="/nonexistent/config/dir")
    assert not bad["admitted"]
    assert any("replay_failed" in x for x in bad["rejections"])


def test_unreadable_run_json_fails_closed(tmp_path):
    d = str(tmp_path / "empty")
    os.makedirs(d)
    with open(os.path.join(d, "run.json"), "w") as fh:
        fh.write("{ not json")
    dec = A.admit_run(d)
    assert not dec["admitted"]
    assert any("unreadable_run_json" in x for x in dec["rejections"])


# ------------------------------------------------------------- report shape

def test_report_records_evaluated_and_deferred(tmp_path):
    rep = A.admit_runs(_runs(tmp_path))
    assert rep["admission_version"] == A.ADMISSION_VERSION
    assert rep["admitted_count"] == 2 and rep["rejected_count"] == 0
    # the §8 criteria that need absent evidence are DEFERRED, never passed
    assert set(rep["deferred_criteria"]) == {
        "intervention_realization", "environment_trace",
        "random_stream_registration", "license_permits_training"}
    assert "replay_verified" not in rep["evaluated_criteria"]
    assert "replay_verified" in A.admit_runs(
        _runs(tmp_path / "r"), require_replay=True)["evaluated_criteria"]


def test_report_commitment_is_content_addressed(tmp_path):
    rep = A.admit_runs(_runs(tmp_path))
    assert rep["admission_commitment"] == A.admission_commitment(rep)
    assert A.ADMISSION_DOMAIN == "dataset:training_admission:v1"


# ---------------------------------------------- build_dataset integration

def test_admission_filters_and_folds_into_commitment(tmp_path):
    runs = _runs(tmp_path)
    _tamper(runs[1], lambda r: r.pop("scenario_hash"))   # reject run b
    plain = build_dataset(_runs(tmp_path / "p"))
    adm = build_dataset(runs, training_admission=True)
    assert adm["training_admission"]["rejected_count"] == 1
    assert adm["training_admission"]["admitted_count"] == 1
    # rejected run is excluded from the substrate
    assert {u["scenario_id"] for u in adm["units"]} == {"corrupt_king"}
    assert plain["dataset_commitment"] != adm["dataset_commitment"]


def test_all_rejected_raises(tmp_path):
    runs = _runs(tmp_path)
    for r in runs:
        _tamper(r, lambda x: x.pop("run_id"))
    with pytest.raises(ValueError, match="rejected every run"):
        build_dataset(runs, training_admission=True)


def test_card_reports_admission(tmp_path):
    card = dataset_card(build_dataset(_runs(tmp_path), training_admission=True))
    assert "Training-data admission gate" in card
    assert "admission commitment" in card
    assert "deferred" in card
