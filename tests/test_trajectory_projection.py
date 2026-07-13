"""P1-S4 — project ONE real vignette trajectory into the full training-record set.

The source run is generated hermetically (scripted, deterministic, no model) into a
tmp out-root via ``run_scenario`` — a REAL corrupt_king / scripted:merciful vignette
trajectory, not a hand-built fixture — so the projector is exercised end-to-end while
the repo's ``logs/runs`` evidence is never touched.

Invariants proved here (profile §4 threat model):
* deterministic derivation (same source bytes -> same ids);
* actor/privileged NON-INTERFERENCE (mutating a privileged field changes the
  privileged observation id but never the actor id; the actor id is recomputable
  with privileged data physically absent);
* legal action set bound to the exact ordered action universe; selected action legal;
* honest ``unavailable`` metadata (no fabricated tokenizer/score/memory);
* the ActorDecisionRecord physically omits the privileged/world references;
* the SourceEvidenceBinding anchors the EXACT source bytes (a one-byte change flips
  the manifest run_identity);
* legacy / non-completed / unsupported-mode runs are REFUSED, never mis-coded;
* projecting the run does not mutate the source files.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil

import pytest

from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.runner import run_scenario
from coliseum.textlab.training.actor_decision import REMOVED_REFERENCES
from coliseum.textlab.training.observation import (assert_no_privileged_leak,
                                                   observation_artifact)
from coliseum.textlab.training.trajectory_projection import (
    ACTOR_OBSERVATION_ALLOWLIST, project_trajectory)

_SCENARIO = "configs/scenarios/corrupt_king.yaml"


@pytest.fixture
def run_dir(tmp_path):
    """A real, deterministic scripted vignette run in an isolated out-root."""
    res = run_scenario(_SCENARIO, "scripted:merciful", 2,
                       out_root=str(tmp_path / "runs"))
    return res.run_dir


def _stream(run_dir):
    with open(os.path.join(run_dir, "decisions.jsonl")) as fh:
        return [json.loads(l) for l in fh if l.strip()]


def _triples(stream):
    """Group the record stream into per-decision blocks (a decision_node and the
    outcome/memory rows that follow it up to the next decision_node)."""
    blocks, cur = [], []
    for rec in stream:
        if rec.get("kind") == "decision_node" and cur:
            blocks.append(cur)
            cur = []
        cur.append(rec)
    if cur:
        blocks.append(cur)
    return blocks


def _write_run(tmp_path, name, src_run_dir, *, stream=None, run_json=None):
    """Write a run dir with a (possibly tampered) decision stream / run.json,
    copying the scenario snapshot from the source run."""
    d = str(tmp_path / name)
    os.makedirs(d)
    if run_json is None:
        run_json = json.load(open(os.path.join(src_run_dir, "run.json")))
    with open(os.path.join(d, "run.json"), "w") as fh:
        json.dump(run_json, fh)
    if stream is None:
        shutil.copy(os.path.join(src_run_dir, "decisions.jsonl"),
                    os.path.join(d, "decisions.jsonl"))
    else:
        with open(os.path.join(d, "decisions.jsonl"), "w") as fh:
            for rec in stream:
                fh.write(json.dumps(rec) + "\n")
    snap = os.path.join(src_run_dir, "scenario.snapshot.json")
    if os.path.exists(snap):
        shutil.copy(snap, os.path.join(d, "scenario.snapshot.json"))
    return d


# --------------------------------------------------------------- happy path
def test_projects_full_record_set(run_dir):
    r = project_trajectory(run_dir)
    # three decision points in the corrupt_king vignette set.
    assert len(r["decision_records"]) == 3
    assert len(r["actor_decision_records"]) == 3
    assert len(r["actor_observations"]) == 3
    assert len(r["privileged_observations"]) == 3
    # manifest binds the ordered decision ids under the source-evidence identity.
    m = r["trajectory_manifest"].content
    assert m["ordered_decision_ids"] == [d.id for d in r["decision_records"]]
    assert m["run_identity"] == r["source_evidence"].id
    assert r["trajectory_manifest"].sequence_integrity() == {
        "length": 3, "duplicates": False, "episode_boundaries_valid": True}
    assert m["episode_boundaries"]["interaction_mode"] == "independent_vignettes"
    assert m["episode_boundaries"]["episode_starts"] == [0, 1, 2]


def test_policy_regime_ids_cross_checked(run_dir):
    r = project_trajectory(run_dir)
    run_json = json.load(open(os.path.join(run_dir, "run.json")))
    c = r["behavior_policy_spec"].content
    assert c["comparison_regime_id"] == run_json["comparison_regime_id"]
    assert c["agent_regime_id"] == run_json["agent_regime_id"]
    # honest unavailable metadata for a historical-shape run (no fabrication).
    assert c["tokenizer_identity"] == {"status": "unavailable"}
    assert c["action_score"] == {"status": "unavailable"}
    assert c["memory_state_ref"] == {"status": "unavailable"}


def test_determinism_same_bytes_same_ids(run_dir):
    a = project_trajectory(run_dir)
    b = project_trajectory(run_dir)
    assert a["trajectory_manifest"].id == b["trajectory_manifest"].id
    assert [d.id for d in a["decision_records"]] == [d.id for d in b["decision_records"]]
    assert a["source_evidence"].id == b["source_evidence"].id


# --------------------------------------------------- actor/privileged split
def test_actor_observation_is_leak_free_and_allowlisted(run_dir):
    r = project_trajectory(run_dir)
    for a in r["actor_observations"]:
        assert_no_privileged_leak(a.content)
        assert set(a.content["content"]) <= set(ACTOR_OBSERVATION_ALLOWLIST)
        assert "facts" not in a.content["content"]


def test_privileged_change_does_not_move_actor_id(run_dir):
    """The corrupt_king vignette carries a privileged ``facts`` block. Mutating it
    changes the privileged observation id but leaves the actor id byte-identical."""
    r = project_trajectory(run_dir)
    priv0 = r["privileged_observations"][0].content["content"]
    assert "facts" in priv0  # the privileged view really carries the ground truth
    actor_id_before = r["actor_observations"][0].id

    # rebuild the first privileged observation with a mutated facts block.
    mutated = copy.deepcopy(priv0)
    mutated["facts"] = {"harm": "SEVERE-injected"}
    priv_mut = observation_artifact("privileged", mutated)
    assert priv_mut.id != r["privileged_observations"][0].id  # privileged id moved
    # the actor projection over the same source is unchanged (facts not allowlisted).
    from coliseum.textlab.training.observation import actor_observation_artifact
    actor_mut = actor_observation_artifact(mutated, ACTOR_OBSERVATION_ALLOWLIST)
    assert actor_mut.id == actor_id_before  # actor id independent of privileged content


def test_actor_id_reconstructs_with_privileged_absent(run_dir):
    """Actor-only reconstruction: the actor id recomputes from a source that has NO
    privileged keys physically present at all."""
    r = project_trajectory(run_dir)
    priv0 = r["privileged_observations"][0].content["content"]
    actor_only_source = {k: priv0[k] for k in ACTOR_OBSERVATION_ALLOWLIST if k in priv0}
    assert "facts" not in actor_only_source and "state_after" not in actor_only_source
    from coliseum.textlab.training.observation import actor_observation_artifact
    rebuilt = actor_observation_artifact(actor_only_source, ACTOR_OBSERVATION_ALLOWLIST)
    assert rebuilt.id == r["actor_observations"][0].id


def test_actor_decision_omits_privileged_and_world_refs(run_dir):
    r = project_trajectory(run_dir)
    for adr in r["actor_decision_records"]:
        c = adr.content
        for ref in REMOVED_REFERENCES:
            assert ref not in c
        assert list(c["removed_references"]) == list(REMOVED_REFERENCES)
        assert c["memory_state_ref"] == {"status": "unavailable"}


# ------------------------------------------------------------- legal actions
def test_legal_action_set_bound_and_selected_legal(run_dir):
    r = project_trajectory(run_dir)
    recs = [json.loads(l) for l in open(os.path.join(run_dir, "decisions.jsonl"))
            if l.strip()]
    nodes = [rec for rec in recs if rec.get("kind") == "decision_node"]
    for las, node, dr in zip(r["legal_action_sets"], nodes, r["decision_records"]):
        avail = node["data"]["available_actions"]
        assert las.content["ordered_action_ids"] == avail            # exact order
        assert las.content["mask"] == [True] * len(avail)
        sym = dr.content["action_split"]["symbolic_action"]
        assert las.is_legal(sym)                                     # selected legal


# --------------------------------------------------------- provenance anchor
def test_source_evidence_anchors_exact_bytes(run_dir):
    r = project_trajectory(run_dir)
    se = r["source_evidence"].content
    run_bytes = open(os.path.join(run_dir, "run.json"), "rb").read()
    dec_bytes = open(os.path.join(run_dir, "decisions.jsonl"), "rb").read()
    assert se["run_json_content_hash"] == hashlib.sha256(run_bytes).hexdigest()
    assert se["decisions_jsonl_content_hash"] == hashlib.sha256(dec_bytes).hexdigest()


def test_one_byte_source_change_flips_run_identity(run_dir, tmp_path):
    """Tamper-evidence: a single appended byte in run.json changes the source-evidence
    id and therefore the manifest run_identity."""
    r = project_trajectory(run_dir)
    # copy the run into a fresh dir and corrupt run.json by one byte.
    import shutil
    dup = str(tmp_path / "dup")
    shutil.copytree(run_dir, dup)
    with open(os.path.join(dup, "run.json"), "ab") as fh:
        fh.write(b" ")
    # the extra byte breaks strict-JSON? trailing whitespace after a JSON object is
    # tolerated by json.loads, so projection still succeeds but the byte-hash differs.
    r2 = project_trajectory(dup)
    assert r2["source_evidence"].id != r["source_evidence"].id
    assert (r2["trajectory_manifest"].content["run_identity"]
            != r["trajectory_manifest"].content["run_identity"])


# -------------------------------------------------------------- refusals
def test_legacy_run_refused(run_dir, tmp_path):
    """A legacy-shape run (no behavioral_config / regime ids) is refused, not
    projected with fabricated identity."""
    run_json = json.load(open(os.path.join(run_dir, "run.json")))
    for k in ("behavioral_config", "comparison_regime_id", "agent_regime_id"):
        run_json.pop(k, None)
    legacy = str(tmp_path / "legacy")
    os.makedirs(legacy)
    with open(os.path.join(legacy, "run.json"), "w") as fh:
        json.dump(run_json, fh)
    # decisions.jsonl copied so the failure is the schema dispatch, not a missing file.
    import shutil
    shutil.copy(os.path.join(run_dir, "decisions.jsonl"),
                os.path.join(legacy, "decisions.jsonl"))
    with pytest.raises(ContentRecordError):
        project_trajectory(legacy)


def test_non_completed_run_refused(run_dir, tmp_path):
    run_json = json.load(open(os.path.join(run_dir, "run.json")))
    run_json["status"] = "aborted"
    d = str(tmp_path / "aborted")
    os.makedirs(d)
    with open(os.path.join(d, "run.json"), "w") as fh:
        json.dump(run_json, fh)
    import shutil
    shutil.copy(os.path.join(run_dir, "decisions.jsonl"),
                os.path.join(d, "decisions.jsonl"))
    with pytest.raises(ContentRecordError):
        project_trajectory(d)


def test_unsupported_interaction_mode_refused(run_dir, tmp_path):
    run_json = json.load(open(os.path.join(run_dir, "run.json")))
    run_json["interaction_mode"] = "sequential_history"
    run_json["behavioral_config"]["interaction"]["mode"] = "sequential_history"
    d = str(tmp_path / "seq")
    os.makedirs(d)
    with open(os.path.join(d, "run.json"), "w") as fh:
        json.dump(run_json, fh)
    import shutil
    shutil.copy(os.path.join(run_dir, "decisions.jsonl"),
                os.path.join(d, "decisions.jsonl"))
    with pytest.raises(ContentRecordError):
        project_trajectory(d)


# -------------------------------------- sequence-integrity fail-closed (blocker 1)
def test_duplicate_decision_triple_refused(run_dir, tmp_path):
    """Appending a duplicate of the first decision block (node+outcome+memory) must
    be refused — not silently renumbered into a clean 4-decision trajectory."""
    stream = _stream(run_dir)
    blocks = _triples(stream)
    tampered = stream + blocks[0]  # duplicate the first block verbatim
    d = _write_run(tmp_path, "dup", run_dir, stream=tampered)
    with pytest.raises(ContentRecordError):
        project_trajectory(d)


def test_bare_duplicate_decision_node_refused(run_dir, tmp_path):
    """Appending only a bare decision_node (unresolved by an outcome) — the auditor's
    exact probe — must be refused."""
    stream = _stream(run_dir)
    first_node = next(r for r in stream if r.get("kind") == "decision_node")
    d = _write_run(tmp_path, "barenode", run_dir, stream=stream + [first_node])
    with pytest.raises(ContentRecordError):
        project_trajectory(d)


def test_gapped_decision_sequence_refused(run_dir, tmp_path):
    """Dropping a MIDDLE decision block leaves a timestep gap ([0,2]) and must be
    refused rather than projected as a clean 2-decision trajectory."""
    blocks = _triples(_stream(run_dir))
    assert len(blocks) == 3
    tampered = [rec for rec in (blocks[0] + blocks[2])]  # skip the middle decision
    d = _write_run(tmp_path, "gap", run_dir, stream=tampered)
    with pytest.raises(ContentRecordError):
        project_trajectory(d)


def test_reordered_decisions_refused(run_dir, tmp_path):
    """Swapping the first two decision blocks makes the file-order timesteps
    non-ascending ([1,0,2]) and must be refused."""
    blocks = _triples(_stream(run_dir))
    tampered = blocks[1] + blocks[0] + blocks[2]
    d = _write_run(tmp_path, "reorder", run_dir, stream=tampered)
    with pytest.raises(ContentRecordError):
        project_trajectory(d)


def test_trailing_truncation_is_tamper_evident(run_dir, tmp_path):
    """Dropping the LAST decision block yields a structurally clean 2-decision
    sequence (timesteps [0,1]); it still projects, but the provenance anchor makes it
    tamper-evident — its run_identity differs from the untouched run's."""
    full = project_trajectory(run_dir)
    blocks = _triples(_stream(run_dir))
    truncated = blocks[0] + blocks[1]
    d = _write_run(tmp_path, "trunc", run_dir, stream=truncated)
    r = project_trajectory(d)
    assert len(r["decision_records"]) == 2                 # structurally clean
    assert (r["trajectory_manifest"].content["run_identity"]
            != full["trajectory_manifest"].content["run_identity"])  # provenance-caught


def test_manifest_integrity_reports_boundaries(run_dir):
    r = project_trajectory(run_dir)
    integ = r["trajectory_manifest"].sequence_integrity()
    assert integ == {"length": 3, "duplicates": False,
                     "episode_boundaries_valid": True}


# ------------------------------------ interaction-mode conflict fail-closed (blocker 2)
def test_mode_conflict_top_supported_bc_unsupported_refused(run_dir, tmp_path):
    """Top-level independent_vignettes but behavioral_config says sequential_history
    (regime-consistent): the conflict must be refused, not coded as independent."""
    run_json = json.load(open(os.path.join(run_dir, "run.json")))
    run_json["behavioral_config"]["interaction"]["mode"] = "sequential_history"
    d = _write_run(tmp_path, "conflictA", run_dir, run_json=run_json)
    with pytest.raises(ContentRecordError):
        project_trajectory(d)


def test_mode_conflict_top_unsupported_bc_supported_refused(run_dir, tmp_path):
    """The other direction: top-level sequential_history, behavioral_config
    independent_vignettes — also refused."""
    run_json = json.load(open(os.path.join(run_dir, "run.json")))
    run_json["interaction_mode"] = "sequential_history"
    d = _write_run(tmp_path, "conflictB", run_dir, run_json=run_json)
    with pytest.raises(ContentRecordError):
        project_trajectory(d)


def test_missing_mode_field_refused(run_dir, tmp_path):
    run_json = json.load(open(os.path.join(run_dir, "run.json")))
    del run_json["interaction_mode"]
    d = _write_run(tmp_path, "nomode", run_dir, run_json=run_json)
    with pytest.raises(ContentRecordError):
        project_trajectory(d)


# ------------------------------------------------- source non-mutation
def test_projection_does_not_mutate_source_files(run_dir):
    before = {}
    for name in ("run.json", "decisions.jsonl", "scenario.snapshot.json"):
        p = os.path.join(run_dir, name)
        before[name] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    project_trajectory(run_dir)
    for name, h in before.items():
        p = os.path.join(run_dir, name)
        assert hashlib.sha256(open(p, "rb").read()).hexdigest() == h
