"""Project ONE existing vignette run into the full training-readiness record set
(P1-S4 vertical slice; profile §4, Appendix A).

Given a completed **modern** scripted-vignette run directory, deterministically
DERIVE — never fabricate — the training records the profile defines:

* one :class:`SourceEvidenceBinding` (binds the exact ``run.json`` +
  ``decisions.jsonl`` byte hashes — the provenance anchor),
* one :class:`BehaviorPolicySpec` (via :func:`run_projection.project_behavior_policy_spec`,
  which re-derives + cross-checks the regime ids; refuses legacy/forged/drifted runs),
* per decision point: a privileged and an actor :class:`ObservationArtifact`
  (actor built by an EXPLICIT allowlist, never copy-minus-secrets), a
  :class:`LegalActionSet`, a privileged :class:`DecisionRecord`, and its actor-safe
  :class:`ActorDecisionRecord` projection,
* one :class:`TrajectoryManifest` binding the ordered decision ids + episode
  boundaries under the source-evidence identity.

Discipline honored here:

* **Derived, not primary.** ``run.json`` / ``decisions.jsonl`` are read only; no
  runner/schema/registry/primary-evidence write. The records are a deterministic
  function of the source bytes, so the same run always yields the same ids.
* **No fabrication.** Fields historical runs never recorded (tokenizer identity,
  action scores, structured memory-state ref) stay explicit ``unavailable``; the
  free-text ``memory_update`` is NOT promoted to a structured memory ref.
* **Actor/privileged non-interference.** The privileged ground truth (``facts``,
  resolved ``state_after`` / ``outcome``) lives only in the privileged observation;
  the actor observation is an allowlist projection that can never carry it, so an
  actor id is independent of privileged content.
* **Explicit dispatch, fail closed.** Only a *completed* ``independent_vignettes``
  run is projected in this slice; any other interaction mode or non-completed
  status is refused rather than silently mis-coded (termination != truncation).
"""
from __future__ import annotations

import hashlib
import json
import os

from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.training.actions import LegalActionSet
from coliseum.textlab.training.actor_decision import project_actor_decision
from coliseum.textlab.training.availability import unavailable
from coliseum.textlab.training.decision_record import DecisionRecord
from coliseum.textlab.training.observation import (actor_observation_artifact,
                                                   observation_artifact)
from coliseum.textlab.training.policy import BehaviorPolicySpec
from coliseum.textlab.training.run_projection import (is_modern_run,
                                                      project_behavior_policy_spec)
from coliseum.textlab.training.trajectory import (SourceEvidenceBinding,
                                                  TrajectoryManifest)

# The ONLY keys an actor observation may carry — an explicit allowlist (never
# copy-minus-secrets). Privileged ground truth (facts / resolved state / outcome)
# is deliberately absent, so it can never reach the actor view.
ACTOR_OBSERVATION_ALLOWLIST = ("dp_id", "narrative", "available_actions")

# Interaction modes this slice can faithfully represent. independent_vignettes:
# each decision point stands alone -> its own episode, no cross-decision history,
# so prev links are null and every decision is a natural terminal of its vignette.
_SUPPORTED_INTERACTION_MODES = frozenset({"independent_vignettes"})


def _sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _load_run_json(run_dir: str) -> dict:
    with open(os.path.join(run_dir, "run.json"), "rb") as fh:
        return json.loads(fh.read())


def _load_decision_nodes(run_dir: str) -> list:
    """Return the ordered ``decision_node`` records (outcome/memory_update rows are
    skipped; they are captured inside the privileged observation, not as decisions)."""
    nodes = []
    with open(os.path.join(run_dir, "decisions.jsonl"), "rb") as fh:
        for raw in fh.read().splitlines():
            if not raw.strip():
                continue
            rec = json.loads(raw)
            if rec.get("kind") == "decision_node":
                nodes.append(rec)
    return nodes


def _interaction_mode(run_json: dict) -> str:
    mode = run_json.get("interaction_mode")
    if not mode:
        mode = (run_json.get("behavioral_config", {})
                .get("interaction", {}).get("mode"))
    return mode


def _privileged_observation_content(data: dict) -> dict:
    """The full privileged observation at decision time: the actor-visible prompt
    surface PLUS the ground truth the agent is never shown (``facts``) and the
    resolved effects (``state_after`` / ``outcome``)."""
    sb = data.get("state_before", {})
    return {
        "dp_id": data["dp_id"],
        "narrative": sb.get("narrative"),
        "available_actions": data["available_actions"],
        "authority_pressure": sb.get("authority_pressure"),
        "time_pressure": sb.get("time_pressure"),
        "risk_level": sb.get("risk_level"),
        "recent_events": sb.get("recent_events", []),
        # --- privileged ground truth / resolved effects (never in the actor view) ---
        "facts": sb.get("facts"),
        "state_after": data.get("state_after"),
        "outcome": data.get("outcome"),
    }


def _action_split(data: dict) -> dict:
    """The four-layer action split. A text vignette has no spatial controller and
    surfaces no separate execution layer to the actor (the resolved effect lives in
    the privileged observation), so those two layers are null — honestly absent, not
    fabricated. ``high_level_intent`` is the agent's own stated reasoning (actor-safe);
    ``symbolic_action`` is the chosen action id (validated legal by DecisionRecord)."""
    return {
        "high_level_intent": data.get("reasoning_summary"),
        "symbolic_action": data["final_action"],
        "controller_actions": None,
        "execution_result": None,
    }


def project_trajectory(run_dir: str) -> dict:
    """Project a completed modern ``independent_vignettes`` run at ``run_dir`` into
    the full training-record set. Returns a dict of the built records. Pure over the
    source bytes (deterministic ids); no registry/global state, no source write.

    Refuses (never mis-codes): a non-modern/legacy run (regime ids unavailable), a
    non-completed run, an unsupported interaction mode, or an empty decision set."""
    run_json = _load_run_json(run_dir)
    if not is_modern_run(run_json):
        raise ContentRecordError(
            "run is not modern (missing behavioral_config + regime ids): its policy "
            "identity is unavailable and must not be fabricated — project only a "
            "modern-schema run")
    status = run_json.get("status")
    if status != "completed":
        raise ContentRecordError(
            f"run status is {status!r}, not 'completed': this slice codes only a "
            "naturally-terminating run and will not mis-code an incomplete/failed run")
    mode = _interaction_mode(run_json)
    if mode not in _SUPPORTED_INTERACTION_MODES:
        raise ContentRecordError(
            f"interaction mode {mode!r} is not supported by this projector "
            f"(supported: {sorted(_SUPPORTED_INTERACTION_MODES)}) — refused rather "
            "than silently mis-representing episode structure")

    # provenance anchor: the exact source bytes.
    source_evidence = SourceEvidenceBinding(
        run_id=run_json["run_id"],
        run_json_content_hash=_sha256_file(os.path.join(run_dir, "run.json")),
        decisions_jsonl_content_hash=_sha256_file(
            os.path.join(run_dir, "decisions.jsonl")),
    )

    # the policy is constant across the run; re-derive + cross-check its regime ids.
    policy = project_behavior_policy_spec(run_json)

    nodes = _load_decision_nodes(run_dir)
    if not nodes:
        raise ContentRecordError("run has no decision_node records to project")

    decisions = []      # DecisionRecord
    actor_decisions = []  # ActorDecisionRecord
    actor_obs = []
    privileged_obs = []
    legal_sets = []
    for i, node in enumerate(nodes):
        data = node["data"]
        source_obs = _privileged_observation_content(data)
        priv = observation_artifact("privileged", source_obs)
        actor = actor_observation_artifact(source_obs, ACTOR_OBSERVATION_ALLOWLIST)
        legal = LegalActionSet(list(data["available_actions"]))
        # independent_vignettes: each decision is a standalone episode -> no prev
        # link and each terminates its own vignette naturally (run completed).
        decision = DecisionRecord(
            sequence_position=i,
            prev_decision_hash=None,
            termination_kind="natural_terminal",
            action_split=_action_split(data),
            actor_observation_hash=actor.id,
            privileged_observation_hash=priv.id,
            legal_action_set=legal,
            behavior_policy_spec_hash=policy.id,
        )
        # memory_state_ref: the run records only a free-text memory_update, not a
        # structured content-addressed memory reference -> explicit unavailable.
        actor_decision = project_actor_decision(
            decision, memory_state_ref=unavailable(), prev_actor_decision_hash=None)
        privileged_obs.append(priv)
        actor_obs.append(actor)
        legal_sets.append(legal)
        decisions.append(decision)
        actor_decisions.append(actor_decision)

    manifest = TrajectoryManifest(
        run_identity=source_evidence.id,
        ordered_decision_ids=[d.id for d in decisions],
        episode_boundaries={
            "interaction_mode": mode,
            # each decision starts (and ends) its own episode in this mode.
            "episode_starts": list(range(len(decisions))),
        },
    )
    return {
        "source_evidence": source_evidence,
        "behavior_policy_spec": policy,
        "trajectory_manifest": manifest,
        "decision_records": decisions,
        "actor_decision_records": actor_decisions,
        "actor_observations": actor_obs,
        "privileged_observations": privileged_obs,
        "legal_action_sets": legal_sets,
    }
