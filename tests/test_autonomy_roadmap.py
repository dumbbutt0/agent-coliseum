"""Roadmap loader: strict subset parsing, schema validation, policy caps,
hash pinning. A roadmap that does not validate authorizes nothing."""
import pytest

from tests.autonomy_util import (policy_doc, roadmap_text, task_fields,
                                 write_roadmap)
from tools.autonomy import roadmap as rm
from tools.autonomy.roadmap import RoadmapError


POLICY = policy_doc()


def _load(tmp_path, tasks=None):
    return rm.load_roadmap(write_roadmap(tmp_path, tasks), POLICY)


# ------------------------------------------------------------------- parser

def test_valid_roadmap_parses_and_hashes(tmp_path):
    doc, digest = _load(tmp_path)
    assert doc["milestone"] == "society-substrate"
    assert doc["tasks"][0]["task_id"] == "t-mock"
    assert doc["tasks"][0]["dependencies"] == []
    assert doc["tasks"][0]["requires_human"] is False
    assert doc["tasks"][0]["maximum_storage_growth_mb"] == 1024
    assert len(digest) == 64


def test_hash_is_over_exact_bytes(tmp_path):
    path = write_roadmap(tmp_path)
    _doc, h1 = rm.load_roadmap(path, POLICY)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("# a comment changes the pin\n")
    _doc, h2 = rm.load_roadmap(path, POLICY)
    assert h1 != h2


@pytest.mark.parametrize("bad", [
    "roadmap_version: \"1\"\nmilestone: m\ntasks:\n\t- task_id: x\n",  # tab
    "roadmap_version: \"1\"\nmilestone: m\ntasks: {flow: refused}\n",
    "roadmap_version: \"1\"\nmilestone: m\ntasks: &anchor\n  - x\n",
])
def test_yaml_features_outside_subset_refused(tmp_path, bad):
    path = str(tmp_path / "bad.yaml")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(bad)
    with pytest.raises(RoadmapError):
        rm.load_roadmap(path, POLICY)


# --------------------------------------------------------------- validation

def test_missing_field_refused(tmp_path):
    task = task_fields()
    del task["evidence_required"]
    with pytest.raises(RoadmapError, match="missing required fields"):
        _load(tmp_path, [task])


def test_unknown_field_refused(tmp_path):
    with pytest.raises(RoadmapError, match="unknown fields"):
        _load(tmp_path, [task_fields(surprise="x")])


def test_two_active_tasks_refused(tmp_path):
    a = task_fields(task_id="t-a", status="active")
    b = task_fields(task_id="t-b", status="active")
    with pytest.raises(RoadmapError, match="one task may be active"):
        _load(tmp_path, [a, b])


def test_forbidden_class_refused(tmp_path):
    with pytest.raises(RoadmapError, match="FORBIDDEN"):
        _load(tmp_path, [task_fields(experiment_class="weight_training")])


def test_unknown_class_refused(tmp_path):
    with pytest.raises(RoadmapError, match="unknown experiment_class"):
        _load(tmp_path, [task_fields(experiment_class="mystery")])


def test_storage_limit_above_policy_cap_refused(tmp_path):
    # owner correction 1: stricter than policy is fine, larger never
    with pytest.raises(RoadmapError, match="exceeds the policy cap"):
        _load(tmp_path, [task_fields(maximum_storage_growth_mb=4096)])


def test_runtime_limit_above_policy_cap_refused(tmp_path):
    with pytest.raises(RoadmapError, match="exceeds the policy cap"):
        _load(tmp_path, [task_fields(maximum_runtime_minutes=999)])


def test_fix_cycles_above_bounded_loop_refused(tmp_path):
    with pytest.raises(RoadmapError, match="bounded-loop cap"):
        _load(tmp_path, [task_fields(maximum_fix_cycles=6)])


def test_dependency_to_unknown_task_refused(tmp_path):
    with pytest.raises(RoadmapError, match="references unknown task"):
        _load(tmp_path, [task_fields(dependencies=["t-ghost"])])


def test_protected_paths_must_be_forbidden(tmp_path):
    with pytest.raises(RoadmapError, match="protected"):
        _load(tmp_path, [task_fields(forbidden_files=["something-else/"])])


def test_duplicate_task_ids_refused(tmp_path):
    with pytest.raises(RoadmapError, match="duplicate task_id"):
        _load(tmp_path, [task_fields(), task_fields()])


# ---------------------------------------------------------------- selection

def test_eligibility_requires_completed_dependencies(tmp_path):
    done = task_fields(task_id="t-done", status="complete")
    gated = task_fields(task_id="t-gated", dependencies=["t-done"])
    waiting = task_fields(task_id="t-wait", dependencies=["t-gated"],
                          status="ready")
    doc, _ = _load(tmp_path, [done, gated, waiting])
    assert [t["task_id"] for t in rm.eligible_tasks(doc)] == ["t-gated"]
    assert rm.active_task(doc) is None


def test_the_real_roadmap_text_shape_round_trips():
    # the renderer in autonomy_util must emit exactly what the parser reads
    text = roadmap_text([task_fields(task_id="t-a", next_tasks=["t-a"])])
    doc = rm.parse_strict_yaml(text)
    assert doc["tasks"][0]["next_tasks"] == ["t-a"]
