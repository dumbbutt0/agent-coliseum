"""Spatial trajectory-corpus record variants (owner golden-suite directive
2026-07-14, phase 2).

Phase-2 verification found the v1 training-readiness records PARTLY
architecture-neutral: ObservationArtifact and TrajectoryManifest are reused as-is
by the spatial producer, but SourceEvidenceBinding (hex run-id + vignette file
fields), BehaviorPolicySpec (requires vignette comparison/agent regime ids), and
LegalActionSet (cardinality >= 2; DecisionRecord is type-bound to it) cannot
represent a scripted spatial trajectory without fabrication. These ADDITIVE,
domain-separated spatial variants carry the SAME semantics with honest fields —
never a fabricated regime id, never a blank placeholder identity. Documented in
SPATIAL-TRAJECTORY-CORPUS-GAPS.md; a future owner-approved records rev may fold
them back into neutral v2 shapes.
"""
from __future__ import annotations

from coliseum.textlab._content_record import ContentRecord, ContentRecordError
from coliseum.textlab.training.termination import validate_termination_kind

SPATIAL_TRS_SCHEMA_VERSION = "1"


def _require_str(name, value):
    if not isinstance(value, str) or not value:
        raise ContentRecordError(f"{name} must be a non-empty string")
    return value


class SpatialSourceEvidenceBinding(ContentRecord):
    """Content-addresses the EXACT spatial-run evidence: the run id (descriptive,
    scenario-shaped, not hex) + the content hash of every evidence file."""
    __slots__ = ()
    DOMAIN = "trs.source_evidence.spatial.v1"
    ID_FIELD = "source_evidence_id"

    def __init__(self, run_id: str, evidence_file_hashes: dict):
        _require_str("run_id", run_id)
        if not isinstance(evidence_file_hashes, dict) or not evidence_file_hashes:
            raise ContentRecordError("evidence_file_hashes must be a non-empty dict")
        for name, h in evidence_file_hashes.items():
            _require_str("evidence file name", name)
            if not isinstance(h, str) or len(h) != 64 or \
                    any(c not in "0123456789abcdef" for c in h):
                raise ContentRecordError(f"{name} hash must be 64 lowercase hex chars")
        super().__init__({
            "schema_version": SPATIAL_TRS_SCHEMA_VERSION,
            "run_id": run_id,
            "evidence_file_hashes": dict(evidence_file_hashes),
        })


class SpatialBehaviorPolicySpec(ContentRecord):
    """The behavior policy of ONE scripted spatial agent. No vignette regime ids
    exist for a scripted spatial run and none are fabricated: the policy identity
    is (scenario, agent key, the committed action-script commitment, the agent's
    perception regime, and the frozen substrate versions)."""
    __slots__ = ()
    DOMAIN = "trs.behavior_policy_spec.spatial.v1"
    ID_FIELD = "behavior_policy_spec_id"

    def __init__(self, scenario: str, agent_key: str, agent_body_id: str,
                 action_script_commitment: str, perception_regime_id: str,
                 scheduler_version: str, renderer_version: str,
                 spatial_schema_version: str):
        content = {
            "schema_version": SPATIAL_TRS_SCHEMA_VERSION,
            "exploration_mechanism": "deterministic_script",
        }
        for name, val in (("scenario", scenario), ("agent_key", agent_key),
                          ("agent_body_id", agent_body_id),
                          ("action_script_commitment", action_script_commitment),
                          ("perception_regime_id", perception_regime_id),
                          ("scheduler_version", scheduler_version),
                          ("renderer_version", renderer_version),
                          ("spatial_schema_version", spatial_schema_version)):
            content[name] = _require_str(name, val)
        super().__init__(content)


class SpatialLegalActionSet(ContentRecord):
    """The FULL candidate-effect universe at one activation, as canonical action
    ids bound to their ordered id-space. Cardinality >= 1 (a spatial decision can
    have exactly one legal action; a forced move is still behavior-policy
    support). The vignette LegalActionSet's >= 2 bound is vignette-specific."""
    __slots__ = ()
    DOMAIN = "trs.legal_action_set.spatial.v1"
    ID_FIELD = "legal_action_set_id"

    def __init__(self, ordered_action_ids: list):
        if not isinstance(ordered_action_ids, list) or not ordered_action_ids:
            raise ContentRecordError("ordered_action_ids must be a non-empty list")
        if any(not isinstance(a, str) or not a for a in ordered_action_ids):
            raise ContentRecordError("action ids must be non-empty strings")
        if ordered_action_ids != sorted(set(ordered_action_ids)):
            raise ContentRecordError(
                "ordered_action_ids must be sorted and duplicate-free (the "
                "canonical ordered id-space)")
        super().__init__({
            "schema_version": SPATIAL_TRS_SCHEMA_VERSION,
            "ordered_action_ids": list(ordered_action_ids),
        })

    def is_legal(self, action_id: str) -> bool:
        return action_id in self.content["ordered_action_ids"]


class SpatialDecisionRecord(ContentRecord):
    """One agent decision at one activation — the spatial mirror of
    trs.decision_record.v1 (same field semantics; SPATIAL legal-set binding;
    sequential prev link within the agent's trajectory; the selected action must
    be legal under the EXACT bound set)."""
    __slots__ = ()
    DOMAIN = "trs.decision_record.spatial.v1"
    ID_FIELD = "decision_record_id"

    def __init__(self, sequence_position: int, prev_decision_hash,
                 termination_kind: str, action_split: dict,
                 actor_observation_hash: str, privileged_observation_hash: str,
                 legal_action_set: "SpatialLegalActionSet",
                 behavior_policy_spec_hash: str, scheduler_position: int,
                 world_line_id: str, world_state_hash: str):
        if not isinstance(sequence_position, int) or isinstance(sequence_position, bool) \
                or sequence_position < 0:
            raise ContentRecordError("sequence_position must be a non-negative int")
        if prev_decision_hash is not None and (
                not isinstance(prev_decision_hash, str) or not prev_decision_hash):
            raise ContentRecordError("prev_decision_hash must be null or a non-empty string")
        if (sequence_position == 0) != (prev_decision_hash is None):
            raise ContentRecordError(
                "prev_decision_hash must be null exactly at sequence_position 0 "
                "(spatial trajectories are sequential)")
        validate_termination_kind(termination_kind)
        keys = ("high_level_intent", "symbolic_action", "controller_actions",
                "execution_result")
        if not isinstance(action_split, dict) or set(action_split) != set(keys):
            raise ContentRecordError(f"action_split must have exactly keys {keys}")
        if not isinstance(legal_action_set, SpatialLegalActionSet):
            raise ContentRecordError("legal_action_set must be a SpatialLegalActionSet")
        if not isinstance(scheduler_position, int) or isinstance(scheduler_position, bool) \
                or scheduler_position < 1:
            raise ContentRecordError("scheduler_position must be a positive int")
        sym = action_split["symbolic_action"]
        if sym is not None and not legal_action_set.is_legal(sym):
            raise ContentRecordError(
                "symbolic_action is not legal under the bound SpatialLegalActionSet")
        for name, val in (("actor_observation_hash", actor_observation_hash),
                          ("privileged_observation_hash", privileged_observation_hash),
                          ("behavior_policy_spec_hash", behavior_policy_spec_hash),
                          ("world_line_id", world_line_id),
                          ("world_state_hash", world_state_hash)):
            _require_str(name, val)
        super().__init__({
            "schema_version": SPATIAL_TRS_SCHEMA_VERSION,
            "sequence_position": sequence_position,
            "prev_decision_hash": prev_decision_hash,
            "termination_kind": termination_kind,
            "action_split": action_split,
            "actor_observation_hash": actor_observation_hash,
            "privileged_observation_hash": privileged_observation_hash,
            "legal_action_set_hash": legal_action_set.id,
            "behavior_policy_spec_hash": behavior_policy_spec_hash,
            "scheduler_position": scheduler_position,
            "world_line_id": world_line_id,
            "world_state_hash": world_state_hash,
        })
