"""P1-S5 — the governed view+partition training-export gate.

Exercises DatasetExportManifest / build_training_export over a real, hermetically
generated scripted vignette projection (P1-S4). Proves the two mandatory gates fail
closed and that an actor export can never carry privileged content or a held-out
scenario.
"""
from __future__ import annotations

import os

import pytest

from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.runner import run_scenario
from coliseum.textlab.training.export_manifest import (DatasetExportManifest,
                                                       build_training_export)
from coliseum.textlab.training.observation import assert_no_privileged_leak
from coliseum.textlab.training.trajectory_projection import project_trajectory

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "configs", "registry", "scenarios.yaml")
SCENARIO = os.path.join(ROOT, "configs", "scenarios", "corrupt_king.yaml")


@pytest.fixture
def projection(tmp_path):
    run_dir = run_scenario(SCENARIO, "scripted:merciful", 2,
                           out_root=str(tmp_path / "runs")).run_dir
    return project_trajectory(run_dir), run_dir


def _export(projection, view_kind, **kw):
    proj, run_dir = projection
    return build_training_export(proj, view_kind=view_kind, run_dir=run_dir,
                                 registry_path=REGISTRY, **kw)


# --------------------------------------------------------------- happy path
def test_actor_export_binds_view_split_commitment(projection):
    manifest, descriptor = _export(projection, "actor")
    c = manifest.content
    assert c["view_kind"] == "actor"
    assert c["scenario_id"] == "corrupt_king"
    assert c["split"] in ("train", "validation", "test")
    assert c["dataset_commitment"] == descriptor["dataset_commitment"]
    assert c["source_evidence_id"] == projection[0]["source_evidence"].id
    # 3 trajectory-level + 3 decisions x 3 actor-safe records = 12.
    assert len(c["included_record_ids"]) == 12


def test_privileged_export_is_superset_of_actor(projection):
    actor, _ = _export(projection, "actor")
    priv, _ = _export(projection, "privileged")
    a_ids = set(actor.content["included_record_ids"])
    p_ids = set(priv.content["included_record_ids"])
    assert a_ids < p_ids                        # strict superset
    assert len(priv.content["included_record_ids"]) == 18   # + 3 decisions x 2 privileged
    # the extra records are exactly the privileged observations + DecisionRecords.
    proj = projection[0]
    priv_only = p_ids - a_ids
    expected = {r.id for r in proj["privileged_observations"]} | \
               {r.id for r in proj["decision_records"]}
    assert priv_only == expected


def test_view_kind_changes_manifest_identity(projection):
    actor, _ = _export(projection, "actor")
    priv, _ = _export(projection, "privileged")
    assert actor.id != priv.id


# ------------------------------------------------ actor export leak isolation
def test_actor_export_carries_no_privileged_record(projection):
    actor, _ = _export(projection, "actor")
    proj = projection[0]
    a_ids = set(actor.content["included_record_ids"])
    # no privileged observation / DecisionRecord id is present in an actor export.
    for r in proj["privileged_observations"] + proj["decision_records"]:
        assert r.id not in a_ids


def test_actor_export_catches_leak_in_actor_safe_record(projection):
    """Defense in depth: even if an actor-safe record's content somehow carried a
    privileged field, the export re-check catches it (not merely record-type exclusion)."""
    proj, run_dir = projection

    class _Leaky:
        id = "de" * 32
        content = {"schema_version": "1", "view_kind": "actor",
                   "content": {"facts": {"harm": "x"}}}

    bad = dict(proj)
    bad["actor_observations"] = [_Leaky()] + list(proj["actor_observations"][1:])
    with pytest.raises(ContentRecordError, match="privileged"):
        build_training_export(bad, view_kind="actor", run_dir=run_dir,
                              registry_path=REGISTRY)


def test_actor_export_records_are_leak_free(projection):
    """Every record referenced by an actor export re-checks leak-free — a belt over
    the id-exclusion braces."""
    proj, run_dir = projection
    actor, _ = _export(projection, "actor")
    included = set(actor.content["included_record_ids"])
    actor_side = (proj["actor_observations"] + proj["actor_decision_records"]
                  + proj["legal_action_sets"]
                  + [proj["source_evidence"], proj["behavior_policy_spec"],
                     proj["trajectory_manifest"]])
    for rec in actor_side:
        if rec.id in included:
            assert_no_privileged_leak(rec.content, "actor export record")


# --------------------------------------------------------------- determinism
def test_export_is_deterministic(projection):
    a, da = _export(projection, "actor")
    b, db = _export(projection, "actor")
    assert a.id == b.id
    assert da["dataset_commitment"] == db["dataset_commitment"]


# -------------------------------------------------------------- fail closed
def test_missing_view_kind_refused(projection):
    with pytest.raises(ContentRecordError):
        _export(projection, "")
    with pytest.raises(ContentRecordError):
        _export(projection, "world")


def test_partition_mandatory_missing_registry_refused(projection):
    proj, run_dir = projection
    with pytest.raises(ValueError, match="requires registry_path"):
        build_training_export(proj, view_kind="actor", run_dir=run_dir,
                              registry_path=None)


def test_held_out_scenario_refused_by_id(projection):
    # a held-out scenario is refused before any export record is built; the §8
    # training-admission gate rejects it and records "held_out" as the reason.
    with pytest.raises(ValueError, match="rejected|held-out"):
        _export(projection, "actor", held_out_scenarios=["corrupt_king"])


def test_held_out_reason_is_recorded(projection):
    from coliseum.textlab.training_admission import admit_runs
    _, run_dir = projection
    rep = admit_runs([run_dir], held_out_ids={"corrupt_king"},
                     config_dir=os.path.join(ROOT, "configs", "scenarios"))
    assert rep["admitted"] == []
    assert rep["rejected"][0]["rejections"] == ["held_out"]


def test_held_out_scenario_refused_for_privileged_too(projection):
    with pytest.raises(ValueError, match="rejected|held-out"):
        _export(projection, "privileged", held_out_scenarios=["corrupt_king"])


# ------------------------------------------------- manifest record invariants
def test_manifest_rejects_duplicate_included_ids():
    with pytest.raises(ContentRecordError):
        DatasetExportManifest("actor", "train", "c" * 64, "s" * 64, "corrupt_king",
                              ["a" * 64, "a" * 64])


def test_manifest_rejects_unknown_view_kind():
    with pytest.raises(ContentRecordError):
        DatasetExportManifest("shadow", "train", "c" * 64, "s" * 64, "corrupt_king",
                              ["a" * 64])
