"""DecisionRecord — one decision, privileged view (profile §4.4; Appendix A).

The canonical (privileged-view) decision record: references both the actor and
privileged observation hashes, the legal-action-set hash, and the policy hash;
carries the sequence position, a `prev_decision_hash` back-reference (strict-DAG;
`next` links live in the TrajectoryManifest, never here), the termination_kind,
and the four-layer action split. The actor-safe ActorDecisionRecord projection is
a later slice (P1-S3). Appendix A: `_domain = trs.decision_record.v1`, id
`decision_record_id`.
"""
from __future__ import annotations

from coliseum.textlab._content_record import ContentRecord, ContentRecordError
from coliseum.textlab.training.actions import LegalActionSet
from coliseum.textlab.training.termination import validate_termination_kind

DECISION_RECORD_SCHEMA_VERSION = "1"

_ACTION_SPLIT_KEYS = ("high_level_intent", "symbolic_action",
                      "controller_actions", "execution_result")


def _validate_action_split(action_split) -> dict:
    if not isinstance(action_split, dict) or set(action_split) != set(_ACTION_SPLIT_KEYS):
        raise ContentRecordError(
            f"action_split must be a dict with exactly {_ACTION_SPLIT_KEYS}")
    sym = action_split["symbolic_action"]
    if sym is not None and (not isinstance(sym, str) or not sym):
        raise ContentRecordError("symbolic_action must be null or a non-empty string")
    return action_split


class DecisionRecord(ContentRecord):
    __slots__ = ()
    DOMAIN = "trs.decision_record.v1"
    ID_FIELD = "decision_record_id"

    def __init__(self, sequence_position: int, prev_decision_hash,
                 termination_kind: str, action_split: dict,
                 actor_observation_hash: str, privileged_observation_hash: str,
                 legal_action_set: "LegalActionSet", behavior_policy_spec_hash: str,
                 world_instance_hash=None):
        if not isinstance(sequence_position, int) or isinstance(sequence_position, bool) \
                or sequence_position < 0:
            raise ContentRecordError("sequence_position must be a non-negative int")
        if prev_decision_hash is not None and (
                not isinstance(prev_decision_hash, str) or not prev_decision_hash):
            raise ContentRecordError("prev_decision_hash must be null or a non-empty string")
        validate_termination_kind(termination_kind)
        _validate_action_split(action_split)
        for name, val in (("actor_observation_hash", actor_observation_hash),
                          ("privileged_observation_hash", privileged_observation_hash),
                          ("behavior_policy_spec_hash", behavior_policy_spec_hash)):
            if not isinstance(val, str) or not val:
                raise ContentRecordError(f"{name} must be a non-empty string")
        if not isinstance(legal_action_set, LegalActionSet):
            raise ContentRecordError("legal_action_set must be a LegalActionSet")
        if world_instance_hash is not None and (
                not isinstance(world_instance_hash, str) or not world_instance_hash):
            raise ContentRecordError("world_instance_hash must be null or a non-empty string")
        # the selected action must be legal under the EXACT bound LegalActionSet,
        # unless this record explicitly represents an invalid-action attempt.
        sym = action_split["symbolic_action"]
        if termination_kind != "invalid_action_termination" and sym is not None:
            if not legal_action_set.is_legal(sym):
                raise ContentRecordError(
                    f"symbolic_action {sym!r} is not legal under the bound "
                    "LegalActionSet (and this is not an invalid-action record)")
        super().__init__({
            "schema_version": DECISION_RECORD_SCHEMA_VERSION,
            "sequence_position": sequence_position,
            "prev_decision_hash": prev_decision_hash,
            "termination_kind": termination_kind,
            "action_split": action_split,
            "actor_observation_hash": actor_observation_hash,
            "privileged_observation_hash": privileged_observation_hash,
            "legal_action_set_hash": legal_action_set.id,
            "behavior_policy_spec_hash": behavior_policy_spec_hash,
            "world_instance_hash": world_instance_hash,
        })
