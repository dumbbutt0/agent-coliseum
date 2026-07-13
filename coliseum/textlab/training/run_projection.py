"""Project a run.json into a BehaviorPolicySpec with a canonical identity
cross-check (P1-S4 prerequisite).

The integrated BehaviorPolicySpec requires genuine comparison_regime_id /
agent_regime_id. A MODERN run.json carries them + the behavioral_config the
canonical builder derived them from; a legacy schema-0.1 run.json lacks them.
This projector:

* **Dispatches on schema** (enumerate-and-refuse, like agents.DISPATCHABLE_PARSER_VERSIONS
  and metrics._regime_ids): a run without behavioral_config + both regime ids is a
  legacy run — its regime ids are UNAVAILABLE and are NEVER fabricated; projection
  is refused. Historical runs keep their original schema/builder untouched.
* **Re-derives** `(comparison, agent) = schema.regime_hashes(behavioral_config)` and
  **rejects** any stored id that disagrees — catching forged, swapped, and
  configuration-drift ids. Caller-supplied ids that disagree with canonical
  derivation are refused.

No fabrication, no config_hash substitution, no legacy mutation.
"""
from __future__ import annotations

from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.schema import regime_hashes
from coliseum.textlab.training.policy import BehaviorPolicySpec


def is_modern_run(run_json: dict) -> bool:
    """True iff the run carries the modern identity fields (behavioral_config +
    both regime ids). A legacy schema-0.1 run returns False."""
    return (isinstance(run_json, dict)
            and isinstance(run_json.get("behavioral_config"), dict)
            and isinstance(run_json.get("comparison_regime_id"), str)
            and bool(run_json.get("comparison_regime_id"))
            and isinstance(run_json.get("agent_regime_id"), str)
            and bool(run_json.get("agent_regime_id")))


def project_behavior_policy_spec(run_json: dict) -> "BehaviorPolicySpec":
    """Build a BehaviorPolicySpec from a MODERN run.json, cross-checking the stored
    regime ids against a canonical re-derivation from behavioral_config. Refuses a
    legacy run (regime ids unavailable — never fabricated) and any forged / swapped
    / drifted id."""
    if not isinstance(run_json, dict):
        raise ContentRecordError("run_json must be a dict")
    if not is_modern_run(run_json):
        raise ContentRecordError(
            "legacy/pre-regime run (missing behavioral_config + "
            "comparison_regime_id/agent_regime_id): regime ids are UNAVAILABLE for "
            "this schema and must not be fabricated — project only a modern-schema run")
    bc = run_json["behavioral_config"]
    stored_cmp = run_json["comparison_regime_id"]
    stored_agt = run_json["agent_regime_id"]
    # canonical re-derivation — the pure deterministic builder used everywhere.
    derived_cmp, derived_agt = regime_hashes(bc)
    if stored_cmp != derived_cmp or stored_agt != derived_agt:
        raise ContentRecordError(
            "regime id does not match canonical derivation from behavioral_config "
            "(forged / swapped / configuration drift): "
            f"stored=({stored_cmp[:12]},{stored_agt[:12]}) "
            f"derived=({derived_cmp[:12]},{derived_agt[:12]})")
    # exploration mechanism is DERIVED honestly from the behavioral_config decoding.
    decoding = bc.get("decoding", {})
    mode = decoding.get("sampling_mode")
    exploration = "deterministic" if mode == "deterministic" else f"stochastic:{mode}"
    return BehaviorPolicySpec(
        behavioral_config=bc,
        comparison_regime_id=stored_cmp,
        agent_regime_id=stored_agt,
        exploration_mechanism=exploration,
    )
