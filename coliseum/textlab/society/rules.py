"""The ONE hard-coded institutional rule (design MINIMAL-SOCIETY-SEED.md §3,
integrated 001238). A LEAF module: importable by the scenario builder without
cycles. The rule is a frozen constant, not configuration."""
from __future__ import annotations

#: the rule's identity string (frozen; appears in the enforcement trace).
INSTITUTION_TOKEN_STAYS_IN_A = "institution.token_stays_in_a.v1"


def _held_token(state, token_id):
    """The body holding the token at ``state``, or None."""
    for p in state.content["placements"]:
        if p["entity_id"] == token_id and p["location"]["tag"] == "held_by":
            return p["location"]["agent_body_id"]
    return None


def institutionally_blocked(effect, state, token_id, room_a_id) -> bool:
    """True iff the rule blocks this concrete effect at this state: a MOVE by
    the agent currently HOLDING the token to any destination other than room A.
    (The token can therefore never leave room A except by lying on its floor.)"""
    if effect.get("action") != "move":
        return False
    holder = _held_token(state, token_id)
    if holder is None or effect.get("agent_body_id") != holder:
        return False
    return effect.get("to_room_instance_id") != room_a_id


def institutional_filter(cands, state, ids):
    """The society-legality filter (applied ABOVE the untouched spatial
    candidates): returns (filtered_candidates, blocked_effects)."""
    token_id, room_a_id = ids["token"], ids["room_A"]
    out = {}
    blocked = []
    for kind, effs in cands.items():
        keep = []
        for eff in effs:
            if institutionally_blocked(eff, state, token_id, room_a_id):
                blocked.append(eff)
            else:
                keep.append(eff)
        out[kind] = keep
    return out, blocked
