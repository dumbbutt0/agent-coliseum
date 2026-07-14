"""Project a spatial run's evidence into the trajectory corpus (owner
golden-suite directive 2026-07-14, phase 2).

Pure over the run directory's evidence bytes: no registry, no re-execution, no
source write, deterministic ids. Per AGENT, every ACTIVATE decision becomes a
SpatialDecisionRecord (sequential prev links; the FULL recorded candidate
universe as its SpatialLegalActionSet; the recorded actor/privileged observation
ids of the state the decision observed) under one SpatialBehaviorPolicySpec, and
the agent's ordered decisions become a v1 TrajectoryManifest (REUSED as-is: its
optional world_line_id field was designed for exactly this producer).

Honesty rules: nothing is fabricated — no vignette regime ids, no invented
intents (`high_level_intent` is null: scenario intents are builder inputs, not
run evidence); PASS activations carry no legal actions and are NOT decisions
(counted + reported, never mis-coded); a run whose evidence schema predates
activations.jsonl is REFUSED, never approximated.
"""
from __future__ import annotations

import hashlib
import json
import os

from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.training.spatial_records import (SpatialBehaviorPolicySpec,
                                                       SpatialDecisionRecord,
                                                       SpatialLegalActionSet,
                                                       SpatialSourceEvidenceBinding)
from coliseum.textlab.training.trajectory import TrajectoryManifest

SPATIAL_INTERACTION_MODE = "spatial_sequential_v1"
#: 0.2 = control evidence; 0.3 = calibration TREATMENT evidence (0.2 + the
#: treatment fields, strictly validated below). Anything else fails closed.
_SUPPORTED_RUN_SCHEMAS = ("0.2", "0.3")
_TREATMENT_FIELDS = ("intervention_id", "execution_instance_id",
                     "treatment_bindings", "witness_ids")
_EVIDENCE_FILES = ("run.json", "chain.jsonl", "transitions.jsonl",
                   "observations.jsonl", "activations.jsonl", "closure.json")


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load(run_dir, name):
    path = os.path.join(run_dir, name)
    if not os.path.isfile(path):
        raise ContentRecordError(f"missing spatial evidence file {name!r}")
    if name.endswith(".jsonl"):
        with open(path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh]
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def project_spatial_trajectory(run_dir: str) -> dict:
    """Project one spatial run directory into per-agent trajectory records."""
    run_json = _load(run_dir, "run.json")
    schema = run_json.get("spatial_run_schema_version")
    if schema not in _SUPPORTED_RUN_SCHEMAS:
        raise ContentRecordError(
            f"spatial run schema {schema!r} is not projectable (supported: "
            f"{_SUPPORTED_RUN_SCHEMAS}) — evidence without the activation stream "
            "must be refused, never approximated")
    if schema == "0.3":
        # strict 0.3 validation: every treatment field present, well-formed,
        # AND canonically consistent — the recorded execution_instance_id must
        # RE-DERIVE from the closed intervention + the recorded bindings (a
        # well-formed-but-inconsistent or malformed value refuses).
        for field in _TREATMENT_FIELDS:
            if not run_json.get(field):
                raise ContentRecordError(
                    f"schema-0.3 treatment evidence is missing {field!r} — refused")
        from coliseum.textlab.spatial.calibration import (
            derive_execution_instance_id, intervention_record)
        tb = run_json["treatment_bindings"]
        required_tb = {"intervention_id", "control_run_id",
                       "control_source_evidence_id", "control_manifest_id",
                       "parent_world_line_id", "fork_position",
                       "fork_state_hash", "fork_decision_id", "fork_genesis_id"}
        if not isinstance(tb, dict) or set(tb) != required_tb:
            raise ContentRecordError(
                "schema-0.3 treatment_bindings must have exactly the canonical "
                "key set — refused")
        iv = intervention_record(run_json["intervention_id"])
        spec = iv.canonical_spec
        if run_json["scenario"] != spec["scenario"] or \
                run_json["seed"] != spec["seed"]:
            raise ContentRecordError(
                "schema-0.3 treatment scenario/seed do not match the closed "
                "intervention bindings — refused")
        # COORDINATED-DRIFT closure (audit 001225): the recorded binding fields
        # must equal the CLOSED intervention before any derivation — otherwise a
        # mutation that recomputes the instance over drifted fork fields would
        # pass the re-derivation check.
        if tb["intervention_id"] != run_json["intervention_id"]:
            raise ContentRecordError(
                "schema-0.3 treatment_bindings.intervention_id does not equal "
                "the run's intervention id — refused")
        if tb["fork_position"] != spec["fork_position"] or \
                tb["fork_state_hash"] != spec["fork_state_hash"]:
            raise ContentRecordError(
                "schema-0.3 recorded fork bindings do not equal the closed "
                "intervention's canonical fork — refused")
        expected = derive_execution_instance_id(
            iv.intervention_id, spec["scenario"], spec["seed"],
            spec["agent_key"], tb["parent_world_line_id"],
            tb["control_source_evidence_id"], tb["fork_position"],
            tb["fork_state_hash"])
        if run_json["execution_instance_id"] != expected:
            raise ContentRecordError(
                "schema-0.3 execution_instance_id does not re-derive from the "
                "closed intervention + recorded bindings — refused")
    observations = _load(run_dir, "observations.jsonl")
    activations = _load(run_dir, "activations.jsonl")

    source_evidence = SpatialSourceEvidenceBinding(
        run_id=run_json["run_id"],
        evidence_file_hashes={name: _sha256_file(os.path.join(run_dir, name))
                              for name in _EVIDENCE_FILES})

    # observation rows keyed by (observed position, observer body id).
    obs_by = {(r["scheduler_position"], r["observer_body_id"]): r
              for r in observations}
    # world-state id at each chain position (from the observation rows, which
    # cover every position for every observer).
    state_at = {r["scheduler_position"]: r["world_state_id"] for r in observations}

    observers = run_json["observers"]                    # key -> body id
    policies = {}
    for key, body_id in observers.items():
        first = obs_by[(0, body_id)]
        policies[key] = SpatialBehaviorPolicySpec(
            scenario=run_json["scenario"], agent_key=key, agent_body_id=body_id,
            action_script_commitment=run_json["action_script_commitment"],
            perception_regime_id=first["actor_content"]["content"]["perception_regime"],
            scheduler_version=run_json["scheduler_version"],
            renderer_version=run_json["renderer_version"],
            spatial_schema_version=run_json["spatial_schema_version"])

    decisions = {key: [] for key in observers}
    legal_sets = {key: [] for key in observers}
    pass_positions = {key: [] for key in observers}
    body_to_key = {b: k for k, b in observers.items()}

    activate_rows = [r for r in activations if "activation" in r]
    for row in activate_rows:
        body = row["activation"]["agent_body_id"]
        key = body_to_key[body]
        if row["activation"]["outcome_kind"] == "pass":
            # no legal actions existed: a forced non-decision, reported not coded.
            pass_positions[key].append(row["scheduler_position"])
            continue
        pos = row["scheduler_position"]
        observed = pos - 1                               # the state it decided at
        obs = obs_by[(observed, body)]
        legal = SpatialLegalActionSet(
            [c["action_id"] for c in row["candidate_universe"]])
        seq = len(decisions[key])
        prev = decisions[key][-1].id if decisions[key] else None
        decision = SpatialDecisionRecord(
            sequence_position=seq,
            prev_decision_hash=prev,
            termination_kind="continuing",               # finalized below
            action_split={
                "high_level_intent": None,
                "symbolic_action": row["selected_action_id"],
                "controller_actions": [row["selected_effect"]],
                "execution_result": {"post_world_state_hash": state_at[pos]},
            },
            actor_observation_hash=obs["actor_observation_id"],
            privileged_observation_hash=obs["privileged_observation_id"],
            legal_action_set=legal,
            behavior_policy_spec_hash=policies[key].id,
            scheduler_position=pos,
            world_line_id=run_json["world_line_id"],
            world_state_hash=obs["world_state_id"])
        decisions[key].append(decision)
        legal_sets[key].append(legal)

    # finalize termination: the LAST decision of each agent terminates its
    # trajectory at the scenario's designed exclusive stop (natural terminal).
    # Rebuilding the tail record keeps ids content-addressed and prev links valid.
    for key, ds in decisions.items():
        if not ds:
            continue
        last = ds[-1].content
        ds[-1] = SpatialDecisionRecord(
            sequence_position=last["sequence_position"],
            prev_decision_hash=last["prev_decision_hash"],
            termination_kind="natural_terminal",
            action_split=last["action_split"],
            actor_observation_hash=last["actor_observation_hash"],
            privileged_observation_hash=last["privileged_observation_hash"],
            legal_action_set=legal_sets[key][-1],
            behavior_policy_spec_hash=last["behavior_policy_spec_hash"],
            scheduler_position=last["scheduler_position"],
            world_line_id=last["world_line_id"],
            world_state_hash=last["world_state_hash"])

    manifests = {}
    for key, ds in decisions.items():
        if not ds:
            continue                                     # a pure-pass agent
        manifests[key] = TrajectoryManifest(
            run_identity=source_evidence.id,
            ordered_decision_ids=[d.id for d in ds],
            episode_boundaries={"interaction_mode": SPATIAL_INTERACTION_MODE,
                                "episode_starts": [0]},
            world_line_id=run_json["world_line_id"])
        integrity = manifests[key].sequence_integrity()
        if integrity["duplicates"] or not integrity["episode_boundaries_valid"]:
            raise ContentRecordError(f"trajectory integrity failed for {key!r}")

    return {
        "interaction_mode": SPATIAL_INTERACTION_MODE,
        "source_evidence": source_evidence,
        "policies": policies,
        "decisions": decisions,
        "legal_action_sets": legal_sets,
        "manifests": manifests,
        "pass_positions": pass_positions,
        "agents_without_decisions": sorted(k for k, d in decisions.items() if not d),
    }
