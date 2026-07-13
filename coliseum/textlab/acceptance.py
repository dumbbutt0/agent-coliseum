"""Coliseum ADAPTER for governance G3 — accepted-transition automation.

The GENERIC council core (`tools/council/policy.acceptance_authorization`) decides
ONLY whether a Class-C matter authorizes an `accepted` transition (a valid,
gate-passing COUNCIL_RESOLVED on the verified chain, governance active). THIS
adapter — the only place that knows the Coliseum claim registry — performs the
actual `accepted` mutation, and ONLY that transition. The generic core never imports
this module or the claim registry (the seam is one-directional: adapter -> core).

Frozen (governance charter §3.1): the real claim-ladder states are
speculation/observation/replicated/generalized/accepted/refuted/demoted (no
"proposed"); this automation performs ONLY the transition INTO `accepted`, only from
a replicated/generalized claim that already satisfies the ladder prerequisites
(>=2 distinct citable evidence experiments); it invents no new state and mutates no
other ladder entry. Any change to the ladder itself is a separate audited migration.
"""
from __future__ import annotations

import copy

from tools.council.policy import acceptance_authorization

from .registry import CLAIM_STATES

ACCEPT_RESOLUTION = "accept"                    # the resolution string the core reports
_PRE_ACCEPTED = ("replicated", "generalized")  # the only states acceptance may promote


def accepted_transition(root, cfg, claims: dict, claim_id: str, matter_id: str,
                        citable_experiments: set):
    """Return (new_claims, result). Performs ONLY the `accepted` transition on
    `claim_id` iff (a) the generic governance core authorizes the matter with an
    accept resolution AND (b) the claim's ladder prerequisites hold; otherwise it
    returns `claims` UNCHANGED plus a typed refusal. Pure — no file I/O; the caller
    supplies the set of citable (complete) experiment ids and persists the result.
    Fail-closed: any missing authority or prerequisite refuses without mutating."""
    def refuse(reason):
        return claims, {"accepted": False, "claim_id": claim_id, "reason": reason,
                        "resolved_event_id": None}

    # fail-closed on any malformed/missing input BEFORE dereferencing (audit 000747):
    # a bad registry shape or an authorization-boundary error is a typed refusal that
    # leaves the input unchanged, never an exception.
    if not isinstance(claims, dict) or not isinstance(claims.get("claims"), list) \
            or any(not isinstance(c, dict) for c in claims["claims"]):
        return refuse("claims registry is missing or malformed (expected a mapping "
                      "with a 'claims' list whose every entry is a mapping)")
    try:
        citable_set = set(citable_experiments or ())
    except TypeError:
        return refuse("citable_experiments is not iterable")
    try:
        auth = acceptance_authorization(root, cfg, matter_id)
    except Exception as exc:                      # authorization-boundary -> refuse
        return refuse(f"authorization failed: {exc}")
    if not auth.authorized:
        return refuse("not authorized by governance: " + "; ".join(auth.reasons))
    if auth.resolution != ACCEPT_RESOLUTION:
        return refuse(f"council resolution is {auth.resolution!r}, not "
                      f"{ACCEPT_RESOLUTION!r}")

    matches = [c for c in claims["claims"] if c.get("claim_id") == claim_id]
    if len(matches) != 1:
        return refuse(f"claim {claim_id!r} not found (or not unique)")
    claim = matches[0]
    state = claim.get("state")
    if state not in CLAIM_STATES:
        return refuse(f"claim has an invalid state {state!r}")
    if state == "accepted":
        return refuse("claim is already accepted")
    if state not in _PRE_ACCEPTED:
        return refuse(f"claim state {state!r} is not promotable to accepted "
                      f"(must be one of {_PRE_ACCEPTED})")
    if not (claim.get("statement") or "").strip():
        return refuse("claim has an empty statement")
    citable = set(claim.get("evidence") or []) & citable_set
    if len(citable) < 2:
        return refuse(f"accepted requires >=2 distinct citable evidence experiments "
                      f"(claim has {len(citable)})")

    # perform ONLY the accepted transition — deep-copy so the input is never mutated
    new_claims = copy.deepcopy(claims)
    target = next(c for c in new_claims["claims"] if c.get("claim_id") == claim_id)
    target["state"] = "accepted"
    # the governance COUNCIL_RESOLVED IS the independent finding audit of the claim
    target["finding_audit"] = auth.resolved_event_id
    target["council_resolved_event_id"] = auth.resolved_event_id
    return new_claims, {"accepted": True, "claim_id": claim_id,
                        "resolved_event_id": auth.resolved_event_id,
                        "reason": "governance-authorized accepted transition"}
