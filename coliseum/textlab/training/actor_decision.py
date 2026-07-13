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

#: the EXACT Appendix-A actor_decision preimage key set (id self-excluded).
_ACTOR_DECISION_KEYS = frozenset({
    "schema_version", "sequence_position", "prev_actor_decision_hash",
    "termination_kind", "action_split", "actor_observation_hash",
    "legal_action_set_hash", "behavior_policy_spec_hash", "memory_state_ref",
    "removed_references",
})


def _assert_no_privileged_ref(payload, where: str = "actor decision") -> None:
    """Recursively reject a privileged/world-instance reference name at ANY depth
    (including inside action_split.execution_result), so a nested privileged ref
    can never become part of actor canonical bytes."""
    if isinstance(payload, dict):
        for k, v in payload.items():
            if k in REMOVED_REFERENCES:
                raise ContentRecordError(
                    f"{where}: actor decision must not contain privileged "
                    f"reference {k!r} at any depth")
            _assert_no_privileged_ref(v, f"{where}.{k}")
    elif isinstance(payload, list):
        for i, v in enumerate(payload):
            _assert_no_privileged_ref(v, f"{where}[{i}]")


class ActorDecisionRecord(ContentRecord):
    __slots__ = ()
    DOMAIN = "trs.actor_decision.v1"
    ID_FIELD = "actor_decision_id"

    def __init__(self, preimage: dict):
        if not isinstance(preimage, dict):
            raise ContentRecordError("preimage must be a dict")
        # exact Appendix-A key set + fixed schema version (no missing/extra keys).
        if set(preimage) != _ACTOR_DECISION_KEYS:
            missing = sorted(_ACTOR_DECISION_KEYS - set(preimage))
            extra = sorted(set(preimage) - _ACTOR_DECISION_KEYS)
            raise ContentRecordError(
                f"actor decision preimage must be exactly {sorted(_ACTOR_DECISION_KEYS)} "
                f"(missing={missing}, extra={extra})")
        if preimage["schema_version"] != ACTOR_DECISION_SCHEMA_VERSION:
            raise ContentRecordError(
                f"actor decision schema_version must be {ACTOR_DECISION_SCHEMA_VERSION!r}")
        if list(preimage["removed_references"]) != list(REMOVED_REFERENCES):
            raise ContentRecordError(
                f"removed_references must be exactly {list(REMOVED_REFERENCES)}")
        # fail closed: no registered privileged FIELD (facts/hidden_effects/…) and
        # no privileged/world REFERENCE name anywhere, even via direct construction.
        assert_no_privileged_leak(preimage, "actor decision preimage")
        _assert_no_privileged_ref(preimage, "actor decision preimage")
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
