"""P1-S6 — end-to-end byte-identical proof for the training-readiness vertical.

Ties S1-S5 together through the single pipeline entry point and proves the top-level
guarantees the profile promises, using a real, hermetically generated scripted
vignette run (no logs/runs write):

* pipeline determinism over a fixed source (same run bytes -> same manifest id,
  commitment, and record ids);
* behavioral reproducibility (byte-identical decisions.jsonl replay), distinguished
  from source-byte identity: run.json carries wall-clock timestamps, so two
  independent runs share a byte-identical TRACE while their provenance (source
  evidence) legitimately differs;
* actor/privileged isolation across the whole chain (actor export is a strict subset
  and carries no privileged record);
* hidden-partition / held-out isolation end-to-end;
* source non-mutation and honest unavailable metadata.
"""
from __future__ import annotations

import hashlib
import os

import pytest

from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.runner import run_scenario
from coliseum.textlab.sweep import verify_run_replay
from coliseum.textlab.training.observation import assert_no_privileged_leak
from coliseum.textlab.training.pipeline import export_training_data_from_run

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "configs", "registry", "scenarios.yaml")
CONFIG_DIR = os.path.join(ROOT, "configs", "scenarios")
SCENARIO = os.path.join(CONFIG_DIR, "corrupt_king.yaml")


def _run(out):
    return run_scenario(SCENARIO, "scripted:merciful", 2, out_root=str(out)).run_dir


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


@pytest.fixture
def run_dir(tmp_path):
    return _run(tmp_path / "runs")


# ------------------------------------------------- end-to-end happy path
def test_pipeline_produces_actor_and_privileged_exports(run_dir):
    actor = export_training_data_from_run(
        run_dir, view_kind="actor", registry_path=REGISTRY, config_dir=CONFIG_DIR)
    priv = export_training_data_from_run(
        run_dir, view_kind="privileged", registry_path=REGISTRY, config_dir=CONFIG_DIR)
    assert actor["manifest"].content["view_kind"] == "actor"
    assert priv["manifest"].content["view_kind"] == "privileged"
    assert actor["manifest"].content["scenario_id"] == "corrupt_king"
    # actor is a strict subset of privileged, and shares one source-evidence identity.
    a_ids = set(actor["manifest"].content["included_record_ids"])
    p_ids = set(priv["manifest"].content["included_record_ids"])
    assert a_ids < p_ids
    assert (actor["manifest"].content["source_evidence_id"]
            == priv["manifest"].content["source_evidence_id"])


def test_pipeline_is_deterministic_over_fixed_source(run_dir):
    a = export_training_data_from_run(
        run_dir, view_kind="actor", registry_path=REGISTRY, config_dir=CONFIG_DIR)
    b = export_training_data_from_run(
        run_dir, view_kind="actor", registry_path=REGISTRY, config_dir=CONFIG_DIR)
    assert a["manifest"].id == b["manifest"].id
    assert a["manifest"].content["dataset_commitment"] == b["manifest"].content["dataset_commitment"]
    assert (a["manifest"].content["included_record_ids"]
            == b["manifest"].content["included_record_ids"])


# --------------------------------------- behavioral reproducibility vs provenance
def test_source_run_replays_byte_identical(run_dir):
    ok, detail = verify_run_replay(run_dir, CONFIG_DIR)
    assert ok, detail


def test_pipeline_verify_gate_passes_for_scripted_run(run_dir):
    # verify=True byte-gates the source run via replay before admission.
    out = export_training_data_from_run(
        run_dir, view_kind="actor", registry_path=REGISTRY, config_dir=CONFIG_DIR,
        verify=True)
    assert out["descriptor"]["replay_verification"]["verified_runs"] == 1


def test_behavioral_records_reproduce_across_independent_runs(tmp_path):
    """The behavioral evidence reproduces across independent runs: two runs share a
    byte-identical decisions.jsonl, and the projected policy + per-decision records
    (which derive from the trace + behavioral_config, never from run.json wall-clock)
    have identical ids. The source-evidence/trajectory identity binds run.json bytes
    (timestamps) and so is provenance, not behavior — it is deliberately NOT asserted
    equal here."""
    run_a = _run(tmp_path / "a")
    run_b = _run(tmp_path / "b")
    assert _sha(os.path.join(run_a, "decisions.jsonl")) == \
           _sha(os.path.join(run_b, "decisions.jsonl"))           # same behavior trace
    a = export_training_data_from_run(run_a, view_kind="actor",
                                      registry_path=REGISTRY, config_dir=CONFIG_DIR)
    b = export_training_data_from_run(run_b, view_kind="actor",
                                      registry_path=REGISTRY, config_dir=CONFIG_DIR)
    pa, pb = a["projection"], b["projection"]
    assert pa["behavior_policy_spec"].id == pb["behavior_policy_spec"].id
    assert [d.id for d in pa["decision_records"]] == [d.id for d in pb["decision_records"]]
    assert [o.id for o in pa["actor_observations"]] == [o.id for o in pb["actor_observations"]]
    assert [o.id for o in pa["privileged_observations"]] == \
           [o.id for o in pb["privileged_observations"]]


# -------------------------------------------------- isolation guarantees
def test_actor_export_never_carries_privileged_record(run_dir):
    out = export_training_data_from_run(
        run_dir, view_kind="actor", registry_path=REGISTRY, config_dir=CONFIG_DIR)
    proj = out["projection"]
    included = set(out["manifest"].content["included_record_ids"])
    for r in proj["privileged_observations"] + proj["decision_records"]:
        assert r.id not in included
    # and every actor-included record is leak-free.
    for r in (proj["actor_observations"] + proj["actor_decision_records"]
              + proj["legal_action_sets"]
              + [proj["source_evidence"], proj["behavior_policy_spec"],
                 proj["trajectory_manifest"]]):
        if r.id in included:
            assert_no_privileged_leak(r.content, "actor export record")


def test_held_out_scenario_isolated_end_to_end(run_dir):
    with pytest.raises((ValueError, ContentRecordError)):
        export_training_data_from_run(
            run_dir, view_kind="actor", registry_path=REGISTRY, config_dir=CONFIG_DIR,
            held_out_scenarios=["corrupt_king"])


def test_honest_unavailable_metadata_end_to_end(run_dir):
    out = export_training_data_from_run(
        run_dir, view_kind="actor", registry_path=REGISTRY, config_dir=CONFIG_DIR)
    policy = out["projection"]["behavior_policy_spec"].content
    assert policy["tokenizer_identity"] == {"status": "unavailable"}
    assert policy["action_score"] == {"status": "unavailable"}
    assert policy["memory_state_ref"] == {"status": "unavailable"}


# -------------------------------------------------- source non-mutation
def test_pipeline_does_not_mutate_source(run_dir):
    before = {name: _sha(os.path.join(run_dir, name))
              for name in ("run.json", "decisions.jsonl", "scenario.snapshot.json")}
    export_training_data_from_run(
        run_dir, view_kind="actor", registry_path=REGISTRY, config_dir=CONFIG_DIR)
    export_training_data_from_run(
        run_dir, view_kind="privileged", registry_path=REGISTRY, config_dir=CONFIG_DIR)
    for name, h in before.items():
        assert _sha(os.path.join(run_dir, name)) == h
