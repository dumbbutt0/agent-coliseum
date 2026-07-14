"""The spatial TRAJECTORY CORPUS (owner golden-suite directive 2026-07-14,
phase 2): every golden-suite scenario + the original R3 scenario projects into
the training-readiness record layer, with pinned per-agent trajectory-manifest
ids, recorded-observation provenance, sequential integrity, selected-action
legality, honest termination/pass coding, and fail-closed refusal of pre-0.2
evidence."""
from __future__ import annotations

import json
import os

import pytest

from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.spatial.run import execute_spatial_run
from coliseum.textlab.training.spatial_records import (SpatialDecisionRecord,
                                                       SpatialLegalActionSet)
from coliseum.textlab.training.spatial_trajectory_projection import (
    SPATIAL_INTERACTION_MODE, project_spatial_trajectory)

#: pinned per-agent trajectory-manifest ids (seed 42) — the corpus drift gate.
CORPUS_PINS = {
    ("spatial_two_agent_private_object_v1", "alice"): "9680a6300927972a8106cb8d1a955ae4d948c78b0331fecf730f187213a527a3",
    ("spatial_two_agent_private_object_v1", "bob"): "b92355b1aeafac51d20c4937c212bdf54ed324fc0a2190845b18186518d09dae",
    ("spatial_nav_exploration_v1", "alice"): "e1d50b5a576a02bded417291e9c36bcba7e96fc3f32fc1e8929956d0dbdad25b",
    ("spatial_object_pipeline_v1", "alice"): "e3366e6c8a0fa8b195412371c72a72c37c49ac4f7dc34f7af70b4578a23c7668",
    ("spatial_object_pipeline_v1", "bob"): "b86445a3f925bc1e12bdb4012e89ff0312c3f06b60adda7287bca5ad05b9fc67",
    ("spatial_info_asymmetry_v1", "alice"): "57f40d3190a3d27ce2be3470567c4c86fa5a2719c6bc2b82581cd23f86cbb0ba",
    ("spatial_info_asymmetry_v1", "bob"): "0ffb5dafd8ea60d81d9cf875f111f5eaa853b634d4beff7745ce51f899312a2c",
    ("spatial_scarce_resource_v1", "alice"): "b4119ef91688e91085d0cd57e51ef4242c1f16c273473e3b908fce10057e61da",
    ("spatial_scarce_resource_v1", "bob"): "110a43a6d4e52b5d659b29a7d480fd8535c2d9363b6b28d866b6c6e47b957aed",
    ("spatial_long_march_v1", "alice"): "ae5b9518baa1e9c277bcb01683044cb26fbd027038c21c8c06e3d889706e97b5",
}
SCENARIOS = sorted({name for name, _ in CORPUS_PINS})


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("corpus"))
    out = {}
    for name in SCENARIOS:
        s = execute_spatial_run(name, 42, out_root=root)
        run_dir = os.path.join(root, s["run_id"])
        out[name] = {"run_dir": run_dir, "summary": s,
                     "projection": project_spatial_trajectory(run_dir)}
    return out


def test_corpus_manifest_ids_pinned(corpus):
    """Every (scenario, agent) trajectory manifest id is exactly the pinned
    literal — ANY drift in evidence, projection, record identity, or ordering
    across the whole substrate + corpus stack fails here."""
    seen = set()
    for name in SCENARIOS:
        for key, manifest in corpus[name]["projection"]["manifests"].items():
            assert manifest.id == CORPUS_PINS[(name, key)], (name, key)
            seen.add((name, key))
    assert seen == set(CORPUS_PINS)


def test_recorded_observation_provenance(corpus):
    """Every decision's actor/privileged observation hashes are EXACTLY the ids
    recorded in observations.jsonl for the observed position + agent — the
    corpus never re-derives or invents observation identity."""
    for name in SCENARIOS:
        run_dir = corpus[name]["run_dir"]
        obs = {(r["scheduler_position"], r["observer_body_id"]): r
               for r in (json.loads(l) for l in
                         open(os.path.join(run_dir, "observations.jsonl")))}
        p = corpus[name]["projection"]
        observers = corpus[name]["summary"]["observers"]
        for key, ds in p["decisions"].items():
            body = observers[key]
            for d in ds:
                row = obs[(d.content["scheduler_position"] - 1, body)]
                assert d.content["actor_observation_hash"] == \
                    row["actor_observation_id"]
                assert d.content["privileged_observation_hash"] == \
                    row["privileged_observation_id"]
                assert d.content["world_state_hash"] == row["world_state_id"]


def test_sequential_integrity_and_termination(corpus):
    """Contiguous 0-based positions, intact prev links, ascending scheduler
    positions, exactly one natural terminal (the last decision), all earlier
    decisions continuing, one episode starting at 0."""
    for name in SCENARIOS:
        p = corpus[name]["projection"]
        for key, ds in p["decisions"].items():
            assert [d.content["sequence_position"] for d in ds] == \
                list(range(len(ds)))
            assert ds[0].content["prev_decision_hash"] is None
            for a, b in zip(ds, ds[1:]):
                assert b.content["prev_decision_hash"] == a.id
            sched = [d.content["scheduler_position"] for d in ds]
            assert sched == sorted(sched)
            kinds = [d.content["termination_kind"] for d in ds]
            assert kinds[-1] == "natural_terminal"
            assert all(k == "continuing" for k in kinds[:-1])
            m = p["manifests"][key]
            assert m.content["episode_boundaries"] == {
                "interaction_mode": SPATIAL_INTERACTION_MODE,
                "episode_starts": [0]}
            assert m.content["world_line_id"] == \
                corpus[name]["summary"]["world_line_id"]


def test_selected_action_legal_and_universe_faithful(corpus):
    """Every decision's symbolic action is a member of its EXACT bound legal
    universe, and that universe equals the candidate universe recorded in the
    evidence for the same position (behavior-policy support from evidence)."""
    for name in SCENARIOS:
        run_dir = corpus[name]["run_dir"]
        acts = {r["scheduler_position"]: r
                for r in (json.loads(l) for l in
                          open(os.path.join(run_dir, "activations.jsonl")))
                if "activation" in r}
        p = corpus[name]["projection"]
        for key, ds in p["decisions"].items():
            for d, legal in zip(ds, p["legal_action_sets"][key]):
                sym = d.content["action_split"]["symbolic_action"]
                assert legal.is_legal(sym)
                row = acts[d.content["scheduler_position"]]
                assert legal.content["ordered_action_ids"] == \
                    sorted(c["action_id"] for c in row["candidate_universe"])
                assert sym == row["selected_action_id"]


def test_policy_identity_honest_and_stable(corpus):
    """One policy per agent per run: scripted identity (scenario + agent + script
    commitment + perception regime + versions), exploration_mechanism
    deterministic_script, NO vignette regime fields anywhere."""
    for name in SCENARIOS:
        p = corpus[name]["projection"]
        s = corpus[name]["summary"]
        for key, policy in p["policies"].items():
            c = policy.content
            assert c["scenario"] == name and c["agent_key"] == key
            assert c["action_script_commitment"] == s["action_script_commitment"]
            assert c["exploration_mechanism"] == "deterministic_script"
            assert "comparison_regime_id" not in c and "agent_regime_id" not in c
            for d in p["decisions"][key]:
                assert d.content["behavior_policy_spec_hash"] == policy.id


def test_source_evidence_binds_every_file(corpus):
    for name in SCENARIOS:
        binding = corpus[name]["projection"]["source_evidence"].content
        assert set(binding["evidence_file_hashes"]) == {
            "run.json", "chain.jsonl", "transitions.jsonl",
            "observations.jsonl", "activations.jsonl", "closure.json"}
        assert binding["run_id"] == corpus[name]["summary"]["run_id"]


def test_v1_binding_contract_documented_accurately():
    """Audit 001183: the v1 SourceEvidenceBinding's run_id is DESCRIPTIVE — any
    non-empty string is accepted (the gap-report G1 rationale is the fixed
    two-file preimage shape, never a run-id format restriction). This regression
    pins the actual v1 contract so the documented finding stays accurate."""
    from coliseum.textlab.training.trajectory import SourceEvidenceBinding
    v1 = SourceEvidenceBinding("neutral-scenario-shaped-run-id", "a" * 64, "b" * 64)
    assert v1.content["run_id"] == "neutral-scenario-shaped-run-id"
    # the ACTUAL v1 limitation: its preimage holds exactly the two vignette file
    # hashes — no field exists for the other four spatial evidence files.
    assert set(v1.content) == {"schema_version", "run_id",
                               "run_json_content_hash",
                               "decisions_jsonl_content_hash"}


def test_pre_02_evidence_refused(corpus, tmp_path):
    """A run dir whose schema predates the activation stream is REFUSED (the
    projector never approximates behavior-policy support)."""
    import shutil
    src = corpus["spatial_nav_exploration_v1"]["run_dir"]
    stale = tmp_path / "stale-run"
    shutil.copytree(src, stale)
    run_json = json.load(open(stale / "run.json"))
    run_json["spatial_run_schema_version"] = "0.1"
    (stale / "run.json").write_text(json.dumps(run_json))
    with pytest.raises(ContentRecordError, match="not projectable"):
        project_spatial_trajectory(str(stale))


def test_spatial_record_refusals():
    """The variant records fail closed: empty/unsorted legal universes; a
    non-legal symbolic action; a prev link at position 0; a null prev at a
    later position."""
    with pytest.raises(ContentRecordError):
        SpatialLegalActionSet([])
    with pytest.raises(ContentRecordError, match="sorted"):
        SpatialLegalActionSet(["b", "a"])
    legal = SpatialLegalActionSet(["actA"])
    kw = dict(termination_kind="continuing",
              action_split={"high_level_intent": None, "symbolic_action": "actA",
                            "controller_actions": [], "execution_result": {}},
              actor_observation_hash="a" * 64,
              privileged_observation_hash="b" * 64,
              legal_action_set=legal, behavior_policy_spec_hash="c" * 64,
              scheduler_position=1, world_line_id="w" * 64,
              world_state_hash="s" * 64)
    SpatialDecisionRecord(sequence_position=0, prev_decision_hash=None, **kw)
    with pytest.raises(ContentRecordError, match="prev_decision_hash"):
        SpatialDecisionRecord(sequence_position=0, prev_decision_hash="p" * 64, **kw)
    with pytest.raises(ContentRecordError, match="prev_decision_hash"):
        SpatialDecisionRecord(sequence_position=3, prev_decision_hash=None, **kw)
    bad = dict(kw)
    bad["action_split"] = dict(kw["action_split"], symbolic_action="actZ")
    with pytest.raises(ContentRecordError, match="not legal"):
        SpatialDecisionRecord(sequence_position=0, prev_decision_hash=None, **bad)
