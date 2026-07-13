"""BehaviorPolicySpec — the policy that generated the behavior (profile §4.1).

Wraps the existing behavioral-config bundle + regime ids; the fields that
historical runs never recorded (tokenizer identity, action scores, memory-state
ref) are explicit availability wrappers, never fabricated (profile §5).
Appendix A: `_domain = trs.behavior_policy_spec.v1`, id `behavior_policy_spec_id`.
"""
from __future__ import annotations

from coliseum.textlab._content_record import ContentRecord, ContentRecordError
from coliseum.textlab.training.availability import (unavailable,
                                                    validate_availability)

BEHAVIOR_POLICY_SPEC_SCHEMA_VERSION = "1"


class BehaviorPolicySpec(ContentRecord):
    __slots__ = ()
    DOMAIN = "trs.behavior_policy_spec.v1"
    ID_FIELD = "behavior_policy_spec_id"

    def __init__(self, behavioral_config: dict, comparison_regime_id: str,
                 agent_regime_id: str, exploration_mechanism: str,
                 tokenizer_identity: dict | None = None,
                 action_score: dict | None = None,
                 memory_state_ref: dict | None = None):
        if not isinstance(behavioral_config, dict):
            raise ContentRecordError("behavioral_config must be a dict")
        for name, val in (("comparison_regime_id", comparison_regime_id),
                          ("agent_regime_id", agent_regime_id),
                          ("exploration_mechanism", exploration_mechanism)):
            if not isinstance(val, str) or not val:
                raise ContentRecordError(f"{name} must be a non-empty string")
        preimage = {
            "schema_version": BEHAVIOR_POLICY_SPEC_SCHEMA_VERSION,
            "behavioral_config": behavioral_config,
            "comparison_regime_id": comparison_regime_id,
            "agent_regime_id": agent_regime_id,
            "exploration_mechanism": exploration_mechanism,
            # explicit availability wrappers — unavailable for historical runs; an
            # *available* value must be non-empty (no blank-placeholder identity).
            "tokenizer_identity": validate_availability(
                tokenizer_identity if tokenizer_identity is not None else unavailable(),
                "tokenizer_identity", nonempty=True),
            "action_score": validate_availability(
                action_score if action_score is not None else unavailable(),
                "action_score", nonempty=True),
            "memory_state_ref": validate_availability(
                memory_state_ref if memory_state_ref is not None else unavailable(),
                "memory_state_ref", nonempty=True),
        }
        super().__init__(preimage)
