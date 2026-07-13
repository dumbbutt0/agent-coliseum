"""ActorDecisionRecord — the actor-safe decision projection (profile §4.4, §7).

A typed projection of the privileged DecisionRecord that **physically omits** the
privileged observation reference and any world-instance reference, retaining only
actor-safe references. Its content and identity therefore cannot depend on
privileged-only facts: changing a privileged-only field leaves every actor
projection byte-identical, while an actor-visible change moves the actor identity.
It is the ONLY decision shape an actor export serializes. Appendix A:
`_domain = trs.actor_decision.v1`, id `actor_decision_id`.
"""
from __future__ import annotations

from coliseum.textlab._content_record import ContentRecord, ContentRecordError
from coliseum.textlab.training.availability import validate_availability
from coliseum.textlab.training.decision_record import DecisionRecord
from coliseum.textlab.training.observation import assert_no_privileged_leak

ACTOR_DECISION_SCHEMA_VERSION = "1"

#: privileged references that are physically removed from the actor projection.
REMOVED_REFERENCES = ("privileged_observation_hash", "world_instance_hash")


class ActorDecisionRecord(ContentRecord):
    __slots__ = ()
    DOMAIN = "trs.actor_decision.v1"
    ID_FIELD = "actor_decision_id"

    def __init__(self, preimage: dict):
        # fail closed: an actor decision may never reference a removed privileged
        # id or carry any registered privileged field at any depth, even when
        # constructed directly (not only via project_actor_decision).
        if isinstance(preimage, dict):
            for k in REMOVED_REFERENCES:
                if k in preimage:
                    raise ContentRecordError(
                        f"actor decision must not reference privileged {k!r}")
            assert_no_privileged_leak(preimage, "actor decision preimage")
        super().__init__(preimage)


def project_actor_decision(decision_record: "DecisionRecord",
                           memory_state_ref: dict,
                           prev_actor_decision_hash=None) -> "ActorDecisionRecord":
    """Project a privileged DecisionRecord to its actor-safe ActorDecisionRecord.

    Retains only actor-safe references (actor observation, legal-action set,
    behavior-policy spec) + sequence position, termination kind, the four-layer
    action split (checked leak-free), an actor-safe memory-state ref, and a
    `removed_references` list naming what was stripped. The privileged observation
    hash and any world-instance reference are physically absent, so the actor id
    is independent of privileged content (actor-only reconstruction)."""
    if not isinstance(decision_record, DecisionRecord):
        raise ContentRecordError("decision_record must be a DecisionRecord")
    c = decision_record.content
    action_split = c["action_split"]
    # the action split must carry no privileged field at any depth to be actor-safe.
    assert_no_privileged_leak(action_split, "actor action_split")
    validate_availability(memory_state_ref, "memory_state_ref")
    if prev_actor_decision_hash is not None and (
            not isinstance(prev_actor_decision_hash, str) or not prev_actor_decision_hash):
        raise ContentRecordError(
            "prev_actor_decision_hash must be null or a non-empty string")
    return ActorDecisionRecord({
        "schema_version": ACTOR_DECISION_SCHEMA_VERSION,
        "sequence_position": c["sequence_position"],
        "prev_actor_decision_hash": prev_actor_decision_hash,
        "termination_kind": c["termination_kind"],
        "action_split": action_split,
        "actor_observation_hash": c["actor_observation_hash"],
        "legal_action_set_hash": c["legal_action_set_hash"],
        "behavior_policy_spec_hash": c["behavior_policy_spec_hash"],
        "memory_state_ref": memory_state_ref,
        "removed_references": list(REMOVED_REFERENCES),
    })
