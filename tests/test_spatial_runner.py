"""Spatial S2D — the minimal scripted runner + CLI (master runnable-experiments
directive, step 4). Tests drive the SAME CLI entry point as a user (cli.main) —
no test-only orchestration path."""
from __future__ import annotations

import json
import os

import pytest

from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.cli import main as cli_main
from coliseum.textlab.spatial.registry import SpatialSpecRegistry
from coliseum.textlab.spatial.run import (execute_spatial_run,
                                          inspect_spatial_run,
                                          replay_spatial_run)
from coliseum.textlab.spatial.scenario import build_scenario

SCENARIO = "spatial_two_agent_private_object_v1"


def _cli_run(tmp_path, seed=42):
    root = str(tmp_path / "spatial-runs")
    cli_main(["spatial-run", "--scenario", SCENARIO, "--seed", str(seed),
              "--spatial-root", root])
    (run_id,) = os.listdir(root)
    return root, run_id


# ----------------------------------------------------------------- CLI vertical
def test_cli_run_replay_inspect(tmp_path, capsys):
    root, run_id = _cli_run(tmp_path)
    out = capsys.readouterr().out
    assert run_id in out and "manifest" in out
    # replay through the same entry point (the gate).
    cli_main(["spatial-replay", run_id, "--spatial-root", root])
    assert "byte-identical" in capsys.readouterr().out
    # inspect both views through the same entry point.
    cli_main(["spatial-inspect", run_id, "--view", "actor", "--agent", "alice",
              "--spatial-root", root])
    actor_out = capsys.readouterr().out
    assert "alice" in actor_out and "pos" in actor_out
    cli_main(["spatial-inspect", run_id, "--view", "privileged",
              "--spatial-root", root])
    assert "bob" in capsys.readouterr().out


def test_run_evidence_files_and_summary(tmp_path):
    root, run_id = _cli_run(tmp_path)
    run_dir = os.path.join(root, run_id)
    for name in ("run.json", "chain.jsonl", "transitions.jsonl",
                 "observations.jsonl"):
        assert os.path.getsize(os.path.join(run_dir, name)) > 0
    s = json.load(open(os.path.join(run_dir, "run.json")))
    assert s["scenario"] == SCENARIO and s["seed"] == 42
    assert s["chain_length"] == s["explicit_stop_position"] + 1
    assert s["fork_position"] is not None and s["fork_state_hash"]
    assert s["manifest_id"][:16] in run_id
    # the chain file carries exactly the scheduler states, positions 0..stop.
    chain = [json.loads(l) for l in open(os.path.join(run_dir, "chain.jsonl"))]
    assert [c["content"]["scheduler_position"] for c in chain] == \
        list(range(s["chain_length"]))


def test_reexecution_is_byte_identical_and_seed_scoped(tmp_path):
    root_a = str(tmp_path / "a"); root_b = str(tmp_path / "b")
    sa = execute_spatial_run(SCENARIO, 42, out_root=root_a)
    sb = execute_spatial_run(SCENARIO, 42, out_root=root_b)
    assert sa == sb                                  # identical summary
    for name in ("run.json", "chain.jsonl", "transitions.jsonl",
                 "observations.jsonl"):
        a = open(os.path.join(root_a, sa["run_id"], name), "rb").read()
        b = open(os.path.join(root_b, sb["run_id"], name), "rb").read()
        assert a == b                                # byte-identical evidence
    # a different seed changes ONLY the recorded random-stream identity (and the
    # run id, which embeds the seed) — the world/manifest identities are unchanged.
    s43 = execute_spatial_run(SCENARIO, 43, out_root=str(tmp_path / "c"))
    assert s43["manifest_id"] == sa["manifest_id"]
    assert s43["terminal_world_state_id"] == sa["terminal_world_state_id"]
    assert s43["random_stream_id"] != sa["random_stream_id"]
    assert s43["run_id"] != sa["run_id"]


def test_replay_detects_tampered_evidence(tmp_path):
    root, run_id = _cli_run(tmp_path)
    obs = os.path.join(root, run_id, "observations.jsonl")
    lines = open(obs, "rb").read()
    open(obs, "wb").write(lines[:-2] + b"X\n")       # flip one evidence byte
    ok, detail = replay_spatial_run(run_id, out_root=root,
                                    scratch_root=str(tmp_path / "scratch"))
    assert not ok and "observations.jsonl" in detail


# --------------------------------------------------------- scenario guarantees
def test_private_object_never_enters_any_actor_view(tmp_path):
    """The scenario's private object (the gem inside the box) appears in NO actor
    observation at ANY position for EITHER agent, while the privileged view always
    carries it — the run-scale perception non-interference guarantee."""
    root, run_id = _cli_run(tmp_path)
    s = json.load(open(os.path.join(root, run_id, "run.json")))
    gem_id = s["instance_ids"]["gem"]
    actor_rows = inspect_spatial_run(run_id, out_root=root, view="actor")
    assert actor_rows                                # every position, both agents
    for r in actor_rows:
        assert gem_id not in r["content"]["visible_entity_identities"]
        assert all(e["entity_id"] != gem_id
                   for e in r["content"]["observable_state_projection"]["entities"])
    priv_rows = inspect_spatial_run(run_id, out_root=root, view="privileged")
    assert all(gem_id in r["content"]["visible_entity_identities"]
               for r in priv_rows)


def test_state_dependent_legality_change():
    """After alice takes the token, it is no longer a take candidate for bob even
    when co-located — the scenario's state-dependent legality check."""
    from coliseum.textlab.spatial.scheduler import candidate_effects
    reg = SpatialSpecRegistry()
    sc = build_scenario(SCENARIO, reg, 42)
    genesis, closure, ids = sc["genesis"], sc["closure"], sc["ids"]
    # at genesis, the token IS takeable (by whoever stands in room A).
    g_cands = candidate_effects(ids["alice"], genesis, closure, reg)
    assert any(e["object_instance_id"] == ids["token"] for e in g_cands["take"])
    # at the designated fork state (alice holds the token), no body has a take
    # candidate for the token any more.
    from coliseum.textlab.spatial.scheduler import _rehydrate_world_state
    fork_state = _rehydrate_world_state(reg.get(sc["fork_state_hash"]))
    for key in ("alice", "bob"):
        cands = candidate_effects(ids[key], fork_state, closure, reg)
        assert not any(e["object_instance_id"] == ids["token"]
                       for e in cands.get("take", ()))


def test_scenario_shape_meets_directive():
    """≥1 portal move, ≥1 object interaction, ~6-8 positions, fork point, explicit
    deterministic terminal — the directive's minimal-scenario contract."""
    reg = SpatialSpecRegistry()
    sc = build_scenario(SCENARIO, reg, 42)
    kinds = [e["action"] for e in sc["script"]]
    assert kinds.count("move") >= 1 and kinds.count("take") >= 1
    assert 5 <= sc["explicit_stop_position"] <= 8
    assert sc["fork_position"] is not None
    assert sc["run"].content["explicit_stop_position"] == sc["explicit_stop_position"]


def test_unknown_scenario_and_bad_seed_refused(tmp_path):
    reg = SpatialSpecRegistry()
    with pytest.raises(ContentRecordError, match="unknown spatial scenario"):
        build_scenario("spatial_nonexistent_v9", reg, 42)
    with pytest.raises(ContentRecordError, match="seed"):
        build_scenario(SCENARIO, SpatialSpecRegistry(), True)
    with pytest.raises(ContentRecordError):
        replay_spatial_run("no-such-run", out_root=str(tmp_path))


def test_illegal_intent_refused_at_build_time():
    """An intent that is not a legal candidate at its state fails the BUILDER
    (deterministic contention seed: a second take of an already-held exclusive
    object is refused as state-dependent illegality, never silently committed)."""
    from coliseum.textlab.spatial import scenario as scen
    reg = SpatialSpecRegistry()
    sc = build_scenario(SCENARIO, reg, 42)
    from coliseum.textlab.spatial.scheduler import _rehydrate_world_state
    fork_state = _rehydrate_world_state(reg.get(sc["fork_state_hash"]))
    from coliseum.textlab.spatial.scheduler import candidate_effects
    cands = candidate_effects(sc["ids"]["bob"], fork_state, sc["closure"], reg)
    with pytest.raises(ContentRecordError, match="not a legal candidate"):
        scen._select_effect(cands, ("take", "token"), sc["ids"])
