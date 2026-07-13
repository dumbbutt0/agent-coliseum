"""Per-request finite state machine, replayed from the event chain.

events.jsonl is authoritative; state.json is a derived cache written by
rebuild(). An approval binds to the exact commit the request was published
for — the same request_id at a different commit is refused.

Autonomy extension: AUDIT_GO may proceed through POLICY_VALIDATION_REQUIRED
to AUTO_APPROVED (policy-gated, see policy.py) instead of the human gate;
HUMAN_APPROVAL_REQUIRED remains the path for anything outside policy.
"""
from __future__ import annotations

from tools.council import storage
from tools.council.schemas import TransitionError

# state names
NONE = "none"
BUILDING = "building"
FIXING = "fixing"
READY = "ready"
REQUESTED = "requested"
CLAIMED = "claimed"
BLOCKED = "blocked"
GO = "go"
POLICY_VALIDATION = "policy_validation"
AUTO_APPROVED = "auto_approved"
AWAITING_HUMAN = "awaiting_human"
APPROVED = "approved"
EXPERIMENT_RUNNING = "experiment_running"
EXPERIMENT_COMPLETE = "experiment_complete"
RESULT_VALIDATION = "result_validation"
RESULT_AUDIT = "result_audit"
RESULT_APPROVED = "result_approved"
RESULT_BLOCKED = "result_blocked"
INTEGRATED = "integrated"
NEXT_MILESTONE_READY = "next_milestone_ready"
CANCELED = "canceled"
AUTONOMY_PAUSED = "autonomy_paused"
MILESTONE_REACHED = "milestone_reached"

TERMINAL_STATES = frozenset({CANCELED, MILESTONE_REACHED})

# event_type -> (allowed source states, destination state)
TRANSITIONS = {
    "BUILD_STARTED": (frozenset({NONE}), BUILDING),
    "FIX_STARTED": (frozenset({BUILDING, BLOCKED, RESULT_BLOCKED}), FIXING),
    "BUILD_READY": (frozenset({BUILDING, FIXING}), READY),
    "AUDIT_REQUESTED": (frozenset({READY}), REQUESTED),
    "READY_FOR_REAUDIT": (frozenset({READY}), REQUESTED),
    "AUDIT_CLAIMED": (frozenset({REQUESTED}), CLAIMED),
    "AUDIT_BLOCKED": (frozenset({CLAIMED}), BLOCKED),
    "AUDIT_GO": (frozenset({CLAIMED}), GO),
    "AUDIT_GO_WITH_CONDITIONS": (frozenset({CLAIMED}), GO),
    "POLICY_VALIDATION_REQUIRED": (frozenset({GO}), POLICY_VALIDATION),
    "AUTO_APPROVED": (frozenset({POLICY_VALIDATION}), AUTO_APPROVED),
    "HUMAN_APPROVAL_REQUIRED": (frozenset({GO, POLICY_VALIDATION}),
                                AWAITING_HUMAN),
    "EXPERIMENT_APPROVED": (frozenset({AWAITING_HUMAN}), APPROVED),
    "EXPERIMENT_STARTED": (frozenset({APPROVED, AUTO_APPROVED}),
                           EXPERIMENT_RUNNING),
    "EXPERIMENT_COMPLETE": (frozenset({EXPERIMENT_RUNNING}),
                            EXPERIMENT_COMPLETE),
    "RESULT_VALIDATION_REQUIRED": (frozenset({EXPERIMENT_COMPLETE}),
                                   RESULT_VALIDATION),
    "RESULT_AUDIT_REQUESTED": (frozenset({RESULT_VALIDATION}), RESULT_AUDIT),
    "RESULT_APPROVED": (frozenset({RESULT_AUDIT}), RESULT_APPROVED),
    "RESULT_BLOCKED": (frozenset({RESULT_AUDIT}), RESULT_BLOCKED),
    # source-change tasks terminate at GO -> integration (no experiment
    # lifecycle); the integrated commit must be the GO-audited commit,
    # which the commit binding below enforces. A CONDITIONAL verdict
    # additionally requires the owner's CONDITIONS_SATISFIED first —
    # enforced in check(), not by prose.
    "CHANGE_INTEGRATED": (frozenset({GO}), INTEGRATED),
    # human sign-off that the verdict's conditions are met; state stays go
    "CONDITIONS_SATISFIED": (frozenset({GO}), GO),
    # delegated (tokenless) condition satisfaction under the owner-ratified
    # charter; state stays go. Its append is refused by events.append_event
    # unless policy.evaluate_delegation passes; check() below adds a chain-only
    # replay-safe gate (all conditions codex-classified Class A).
    "CONDITIONS_AUTO_SATISFIED": (frozenset({GO}), GO),
    "NEXT_MILESTONE_READY": (frozenset({RESULT_APPROVED, INTEGRATED}),
                             NEXT_MILESTONE_READY),
}

# events that never change request state (control/identity events use
# synthetic request ids and carry no request authority)
STATELESS_EVENTS = frozenset({"WATCHER_ERROR", "STATUS_CHANGED",
                              "POLICY_INITIALIZED", "POLICY_AMENDED",
                              "HUMAN_IDENTITY_INITIALIZED",
                              "HUMAN_IDENTITY_ROTATED",
                              "MIGRATION_APPROVED"})

# events exempt from the commit binding (they record incidents, not progress)
BINDING_EXEMPT = frozenset({"WATCHER_ERROR", "AUTONOMY_PAUSED",
                            "REQUEST_CANCELED"})

# once a request is in one of these states, its target_commit is bound
_BOUND_FROM = frozenset({REQUESTED, CLAIMED, BLOCKED, GO, POLICY_VALIDATION,
                         AUTO_APPROVED, AWAITING_HUMAN, APPROVED,
                         EXPERIMENT_RUNNING, EXPERIMENT_COMPLETE,
                         RESULT_VALIDATION, RESULT_AUDIT, RESULT_APPROVED,
                         RESULT_BLOCKED, INTEGRATED, NEXT_MILESTONE_READY})


def _blank_request() -> dict:
    return {"state": NONE, "target_commit": None, "claimed_by": None,
            "audit_cycles": 0, "history": [], "last_event_id": None,
            "last_verdict": None, "conditions_satisfied": False}


def check(event: dict, requests: dict) -> None:
    """Raise TransitionError unless `event` is legal given the projection."""
    etype = event["event_type"]
    req = requests.get(event["request_id"], _blank_request())
    state = req["state"]

    if etype in STATELESS_EVENTS:
        return
    if etype == "AUTONOMY_PAUSED":
        return  # recordable from any state — it is the incident record
    if etype == "AUTONOMY_MILESTONE_REACHED":
        if state in TERMINAL_STATES:
            raise TransitionError(
                f"AUTONOMY_MILESTONE_REACHED on terminal request "
                f"{event['request_id']!r} ({state})")
        return
    if etype == "REQUEST_CANCELED":
        if state in TERMINAL_STATES:
            raise TransitionError(
                f"cannot cancel {event['request_id']!r} in terminal "
                f"state {state}")
        return
    if state == AUTONOMY_PAUSED:
        raise TransitionError(
            f"request {event['request_id']!r} is AUTONOMY_PAUSED — only a "
            "human cancel/fresh request may follow")

    if etype not in TRANSITIONS:
        raise TransitionError(f"no transition defined for {etype}")
    allowed_from, _to = TRANSITIONS[etype]
    if state not in allowed_from:
        raise TransitionError(
            f"{etype} not allowed from state {state!r} for request "
            f"{event['request_id']!r} (allowed from: {sorted(allowed_from)})")

    # a CONDITIONAL verdict never integrates on Claude's authority alone:
    # the owner must have recorded CONDITIONS_SATISFIED for this request
    # (cycle-2 audit blocker — the gate is mechanical, not printed advice)
    if etype == "CHANGE_INTEGRATED":
        last = (req.get("last_verdict") or {}).get("event_type")
        if last == "AUDIT_GO_WITH_CONDITIONS" \
                and not req.get("conditions_satisfied"):
            raise TransitionError(
                f"request {event['request_id']!r} carries a conditional "
                "verdict (AUDIT_GO_WITH_CONDITIONS) — integration is "
                "refused until a human records CONDITIONS_SATISFIED")
    if etype == "CONDITIONS_SATISFIED":
        last = (req.get("last_verdict") or {}).get("event_type")
        if last != "AUDIT_GO_WITH_CONDITIONS":
            raise TransitionError(
                "CONDITIONS_SATISFIED only applies to a request whose "
                f"last verdict is conditional (got {last!r})")
    if etype == "CONDITIONS_AUTO_SATISFIED":
        # Chain-only, replay-safe anti-forgery gate: delegated satisfaction is
        # legal ONLY for a conditional verdict EVERY one of whose conditions the
        # auditor (codex) classified Class A. The codex classification is
        # hash-bound in the verdict payload; the git/policy/budget envelope is
        # additionally re-validated by events.append_event before the append.
        lv = req.get("last_verdict") or {}
        if lv.get("event_type") != "AUDIT_GO_WITH_CONDITIONS":
            raise TransitionError(
                "CONDITIONS_AUTO_SATISFIED only applies to a conditional "
                f"verdict (got {lv.get('event_type')!r})")
        classes = lv.get("condition_classes")
        if not isinstance(classes, list) or not classes \
                or any(c != "A" for c in classes):
            raise TransitionError(
                "CONDITIONS_AUTO_SATISFIED refused: the verdict's conditions "
                "are not all auditor-classified Class A "
                f"(condition_classes={classes!r}) — use the human "
                "CONDITIONS_SATISFIED gate")

    # commit binding: an approval/audit for one commit never applies to
    # another. The binding is set when the request is published.
    if state in _BOUND_FROM and etype not in BINDING_EXEMPT:
        bound = req["target_commit"]
        if bound and event["target_commit"] != bound:
            raise TransitionError(
                f"{etype} carries commit {event['target_commit'][:12]} but "
                f"request {event['request_id']!r} is bound to {bound[:12]} "
                "— approvals do not transfer between commits")


def apply(event: dict, requests: dict) -> dict:
    """Fold one event into the projection (caller ran check())."""
    rid = event["request_id"]
    etype = event["event_type"]
    if etype in STATELESS_EVENTS:
        # control/identity/watcher events never materialize a phantom
        # request — they annotate an existing one at most
        if rid in requests:
            requests[rid]["history"].append(event["event_id"])
            requests[rid]["last_event_id"] = event["event_id"]
        return requests
    req = requests.setdefault(rid, _blank_request())
    req["history"].append(event["event_id"])
    req["last_event_id"] = event["event_id"]
    if etype == "AUTONOMY_PAUSED":
        req["state"] = AUTONOMY_PAUSED
        return requests
    if etype == "AUTONOMY_MILESTONE_REACHED":
        req["state"] = MILESTONE_REACHED
        return requests
    if etype == "REQUEST_CANCELED":
        req["state"] = CANCELED
        return requests
    _allowed, to_state = TRANSITIONS[etype]
    req["state"] = to_state
    if etype in ("AUDIT_REQUESTED", "READY_FOR_REAUDIT"):
        req["target_commit"] = event["target_commit"]
        req["audit_cycles"] += 1
    if etype == "AUDIT_CLAIMED":
        req["claimed_by"] = event["sender"]
    if etype in ("AUDIT_BLOCKED", "AUDIT_GO", "AUDIT_GO_WITH_CONDITIONS",
                 "RESULT_APPROVED", "RESULT_BLOCKED"):
        req["last_verdict"] = {
            "event_type": etype,
            "event_id": event["event_id"],
            "verdict": event["payload"].get("verdict"),
            # codex per-condition classification (delegated-authority extension);
            # None for verdicts that carry no classification
            "condition_classes": event["payload"].get("condition_classes")}
        # a fresh verdict always invalidates any earlier condition sign-off
        req["conditions_satisfied"] = False
    if etype in ("CONDITIONS_SATISFIED", "CONDITIONS_AUTO_SATISFIED"):
        req["conditions_satisfied"] = True
    return requests


def project(events) -> dict:
    """Replay a full event list into {request_id: request_state}, checking
    every transition (a chain that replays is a chain that was legal)."""
    requests: dict = {}
    for event in events:
        check(event, requests)
        apply(event, requests)
    return requests


QUARANTINED = "quarantined"

# states from which further AUTHORITY action proceeds — a request sitting
# here whose deriving verdict is invalid+unblessed is QUARANTINED (item 5).
# Settled states (blocked, result_blocked, result_approved, integrated,
# next_milestone_ready, canceled, milestone_reached, autonomy_paused) keep
# their history but never re-grant authority, so they are never quarantined.
_PENDING_AUTHORITY_STATES = frozenset({
    GO, POLICY_VALIDATION, AUTO_APPROVED, AWAITING_HUMAN, APPROVED,
    EXPERIMENT_RUNNING, EXPERIMENT_COMPLETE, RESULT_VALIDATION, RESULT_AUDIT,
})


def authority_status(events) -> dict:
    """H4 quarantine overlay: {request_id: {authority_valid, quarantined,
    invalid_events}}. Every VERDICT-authority event is re-validated during
    replay (version-dispatched schema, no chain crosscheck — self-contained);
    an invalid one that is not blessed by a human-token MIGRATION_APPROVED
    marks its request authority_invalid. A request is QUARANTINED only when
    it currently SITS in a pending-authority state derived from an invalid,
    unblessed verdict — so a settled/terminal request with a bad historical
    verdict stays inspectable and never silently upgrades to authority."""
    from tools.council.schemas import (validate_verdict_event_payload,
                                       VERDICT_PAYLOAD_EVENT_TYPES,
                                       CouncilError)
    from tools.council import identity
    # A MIGRATION_APPROVED counts as a blessing ONLY when it is a genuine
    # human-token event (cycle-1 blocker: a forged non-human/tokenless one
    # must not clear quarantine). identity.replay_identity validates the
    # WHOLE token succession incl. each event's binding (H1 cycle-5); if it
    # passes, every human-token MIGRATION_APPROVED was authorized. A
    # failing replay honors NO blessings — fail closed.
    try:
        identity.replay_identity(events)
        identity_ok = True
    except CouncilError:
        identity_ok = False
    blessed = set()
    if identity_ok:
        for event in events:
            if event["event_type"] == "MIGRATION_APPROVED" \
                    and event.get("sender") == "human":
                bid = event["payload"].get("blessed_event_id")
                bhash = event["payload"].get("blessed_event_hash")
                if bid:
                    blessed.add((bid, bhash))
    status: dict = {}
    for event in events:
        rid = event["request_id"]
        st = status.setdefault(rid, {"authority_valid": True,
                                     "invalid_events": []})
        if event["event_type"] in VERDICT_PAYLOAD_EVENT_TYPES:
            try:
                validate_verdict_event_payload(event)
            except CouncilError:
                if (event["event_id"], event["event_hash"]) not in blessed:
                    st["authority_valid"] = False
                    st["invalid_events"].append(event["event_id"])
    requests = project(events)
    for rid, req in requests.items():
        st = status.setdefault(rid, {"authority_valid": True,
                                     "invalid_events": []})
        st["quarantined"] = (not st["authority_valid"]
                             and req["state"] in _PENDING_AUTHORITY_STATES)
    return status


def global_flags(requests: dict) -> dict:
    states = {r["state"] for r in requests.values()}
    return {"milestone_reached": MILESTONE_REACHED in states,
            "autonomy_paused": AUTONOMY_PAUSED in states}


def rebuild(root: str, events: list, head_hash: str) -> dict:
    """Write the derived cache. events.jsonl always wins over this file."""
    requests = project(events)
    state = {"chain_length": len(events),
             "head_event_hash": head_hash,
             "requests": requests,
             "flags": global_flags(requests),
             "rebuilt_utc": storage.utc_now(),
             "note": "derived cache — events.jsonl is authoritative"}
    storage.atomic_write_json(storage.state_path(root), state)
    return state
