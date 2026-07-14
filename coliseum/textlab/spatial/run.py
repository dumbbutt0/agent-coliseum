"""Spatial S2D — the minimal scripted spatial runner (master runnable-experiments
directive, step 4): the bridge from the integrated S0..S2C APIs to a runnable,
replayable experiment behind one command.

A spatial run is EXPERIMENT EVIDENCE written to a run directory (never council
events): run.json + chain.jsonl + transitions.jsonl + observations.jsonl, every
line canonical JSON with NO wall-clock / host entropy, so a fresh re-execution is
byte-identical (the replay gate). The runner drives the integrated production
path only — build_scenario -> schedule() -> render_observation_pair — with no
test-only orchestration.
"""
from __future__ import annotations

import json
import os

from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.schema import canonical_json
from coliseum.textlab.spatial.perception import (RENDERER_VERSION,
                                                 render_observation_pair)
from coliseum.textlab.spatial.registry import SpatialSpecRegistry
from coliseum.textlab.spatial.scenario import (SPATIAL_SCENARIO_SCHEMA_VERSION,
                                               build_scenario)
from coliseum.textlab.spatial.scheduler import (SCHEDULER_VERSION,
                                                _rehydrate_world_state, schedule,
                                                verify_manifest)
from coliseum.textlab.spatial.world import SPATIAL_SCHEMA_VERSION

SPATIAL_RUN_SCHEMA_VERSION = "0.1"
DEFAULT_SPATIAL_ROOT = os.path.join("logs", "spatial-runs")

_EVIDENCE_FILES = ("run.json", "chain.jsonl", "transitions.jsonl",
                   "observations.jsonl")


def _observe_chain(chain, sc, registry):
    """Render the (actor, privileged) pair for EVERY observer at EVERY chain
    position (pure; registers nothing). Returns canonical observation rows."""
    rows = []
    for cursor in chain:
        state = _rehydrate_world_state(
            registry.get(cursor.content["current_world_state_hash"]))
        for key in sc["observers"]:
            body_id = sc["ids"][key]
            actor, priv = render_observation_pair(state, body_id, sc["closure"],
                                                  registry)
            rows.append({
                "scheduler_position": cursor.content["scheduler_position"],
                "scheduler_state_id": cursor.id,
                "world_state_id": state.id,
                "observer_key": key,
                "observer_body_id": body_id,
                "actor_observation_id": actor.id,
                "privileged_observation_id": priv.id,
                "actor_content": actor.content,
                "privileged_content": priv.content,
            })
    return rows


def execute_spatial_run(scenario, seed, out_root=DEFAULT_SPATIAL_ROOT):
    """Build + schedule + verify + observe the named scenario and write the run
    directory. Returns the run summary dict (= the run.json payload)."""
    registry = SpatialSpecRegistry()
    sc = build_scenario(scenario, registry, seed)
    chain, transitions, manifest = schedule(sc["run"], sc["genesis"],
                                            list(sc["script"]), sc["closure"],
                                            registry)
    # the determinism gate is not deferred to replay: verify the manifest NOW by
    # whole-chain re-derivation before any evidence is written.
    verify_manifest(manifest, sc["run"], sc["genesis"], list(sc["script"]),
                    sc["closure"], registry)
    observations = _observe_chain(chain, sc, registry)
    run_id = f"{scenario}--seed{seed}--{manifest.id[:16]}"
    summary = {
        "spatial_run_schema_version": SPATIAL_RUN_SCHEMA_VERSION,
        "scenario_schema_version": SPATIAL_SCENARIO_SCHEMA_VERSION,
        "spatial_schema_version": SPATIAL_SCHEMA_VERSION,
        "scheduler_version": SCHEDULER_VERSION,
        "renderer_version": RENDERER_VERSION,
        "run_id": run_id,
        "scenario": scenario,
        "seed": seed,
        "world_line_id": sc["world_line"].id,
        "world_line_genesis_id": sc["world_line_genesis"].id,
        "genesis_state_id": sc["genesis"].id,
        "topology_closure_hash": sc["world_line_genesis"].content["topology_closure_hash"],
        "scheduler_run_id": sc["run"].id,
        "manifest_id": manifest.id,
        "chain_length": len(chain),
        "terminal_scheduler_state_id": chain[-1].id,
        "terminal_world_state_id": chain[-1].content["current_world_state_hash"],
        "explicit_stop_position": sc["explicit_stop_position"],
        "fork_position": sc["fork_position"],
        "fork_state_hash": sc["fork_state_hash"],
        "random_stream_id": sc["random_stream"].id,
        "observers": {k: sc["ids"][k] for k in sc["observers"]},
        "private_object_key": sc["private_object_key"],
        "instance_ids": sc["ids"],
        "observation_count": len(observations),
    }
    run_dir = os.path.join(out_root, run_id)
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "run.json"), "w", encoding="utf-8") as fh:
        fh.write(canonical_json(summary) + "\n")
    with open(os.path.join(run_dir, "chain.jsonl"), "w", encoding="utf-8") as fh:
        for c in chain:
            fh.write(canonical_json({"scheduler_state_id": c.id,
                                     "content": c.content}) + "\n")
    with open(os.path.join(run_dir, "transitions.jsonl"), "w", encoding="utf-8") as fh:
        for t in transitions:
            fh.write(canonical_json({"transition_id": t.id,
                                     "content": t.content}) + "\n")
    with open(os.path.join(run_dir, "observations.jsonl"), "w", encoding="utf-8") as fh:
        for row in observations:
            fh.write(canonical_json(row) + "\n")
    return summary


def replay_spatial_run(run_id, out_root=DEFAULT_SPATIAL_ROOT, scratch_root=None):
    """The replay gate: re-execute the run's (scenario, seed) from nothing into a
    scratch directory and byte-compare EVERY evidence file. Returns (ok, detail)."""
    import tempfile
    run_dir = os.path.join(out_root, run_id)
    run_path = os.path.join(run_dir, "run.json")
    if not os.path.isfile(run_path):
        raise ContentRecordError(f"no such spatial run: {run_dir}")
    with open(run_path, encoding="utf-8") as fh:
        recorded = json.load(fh)
    scratch = scratch_root or tempfile.mkdtemp(prefix="spatial-replay-")
    fresh = execute_spatial_run(recorded["scenario"], recorded["seed"],
                                out_root=scratch)
    if fresh["run_id"] != run_id:
        return False, (f"replay derived a different run identity: "
                       f"{fresh['run_id']} != {run_id}")
    for name in _EVIDENCE_FILES:
        with open(os.path.join(run_dir, name), "rb") as fh:
            original = fh.read()
        with open(os.path.join(scratch, run_id, name), "rb") as fh:
            replayed = fh.read()
        if original != replayed:
            return False, f"{name} is not byte-identical"
    return True, f"byte-identical: {', '.join(_EVIDENCE_FILES)}"


def inspect_spatial_run(run_id, out_root=DEFAULT_SPATIAL_ROOT, view="actor",
                        agent=None):
    """Return the recorded observation rows for one view (and optionally one
    agent) — what an agent could see, step by step, from the evidence alone."""
    if view not in ("actor", "privileged"):
        raise ContentRecordError("view must be 'actor' or 'privileged'")
    run_dir = os.path.join(out_root, run_id)
    obs_path = os.path.join(run_dir, "observations.jsonl")
    if not os.path.isfile(obs_path):
        raise ContentRecordError(f"no such spatial run: {run_dir}")
    rows = []
    with open(obs_path, encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            if agent is not None and row["observer_key"] != agent:
                continue
            rows.append({
                "scheduler_position": row["scheduler_position"],
                "observer_key": row["observer_key"],
                "observation_id": row[f"{view}_observation_id"],
                "content": row[f"{view}_content"]["content"],
            })
    return rows
