"""The authoritative append-only, hash-chained event log.

Every append: events-lock -> emergency-stop check -> role check -> replay ->
transition check -> write one canonical line -> refresh state.json. There is
no API that edits or deletes an event, ever.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from tools.council import Config, locking, state_machine, storage
from tools.council.schemas import (CONTROL_BOOTSTRAP_EVENT_TYPES, ChainError,
                                   CouncilError, GENESIS_HASH,
                                   HUMAN_TOKEN_REQUIRED_EVENT_TYPES,
                                   STOP_EXEMPT_EVENT_TYPES, canonical_json,
                                   compute_event_hash, protocol_version,
                                   validate_event)


import re as _re

_EVENT_ID_RE = _re.compile(r"^\d{6}-[0-9a-f]{8}$")


@dataclass
class ChainReport:
    ok: bool
    length: int
    head_hash: str
    error: str | None = None
    error_index: int | None = None
    suffix_incomplete: bool = False
    torn_bytes: int = 0

    @property
    def healthy(self) -> bool:
        """H4: a chain is healthy for AUTHORITY decisions only when it is
        fully valid AND has no torn/incomplete suffix. Reads may still use
        a valid prefix (ok), but every authority consumer requires this."""
        return self.ok and not self.suffix_incomplete


def read_chain(root: str, verify: bool = True) -> list:
    """All complete events, optionally verifying every hash, link, seq,
    and id-uniqueness. A torn trailing line makes verify=True raise (a
    valid prefix with an incomplete suffix is NOT a safe authority chain)."""
    events = []
    seen_ids = set()
    prev_hash = GENESIS_HASH
    complete, tail = storage.read_events_with_tail(storage.events_path(root))
    for event in complete:
        if verify:
            _verify_one(event, prev_hash, len(events), seen_ids)
        events.append(event)
        seen_ids.add(event.get("event_id"))
        prev_hash = event["event_hash"]
    if verify and tail["torn"]:
        raise ChainError(
            f"chain has a torn trailing line ({tail['torn_bytes']} bytes) "
            "after a valid prefix — refusing (repair-tail required)")
    return events


def _verify_one(event: dict, prev_hash: str, index: int,
                seen_ids: set = None) -> None:
    eid = event.get("event_id")
    if event.get("previous_event_hash") != prev_hash:
        raise ChainError(
            f"event #{index} ({eid!r}): previous_event_hash "
            f"{event.get('previous_event_hash')!r} does not chain to "
            f"{prev_hash!r}")
    if not isinstance(eid, str) or not _EVENT_ID_RE.match(eid):
        raise ChainError(
            f"event #{index}: event_id {eid!r} is malformed "
            "(expected NNNNNN-xxxxxxxx)")
    if int(eid[:6]) != index + 1:
        raise ChainError(
            f"event #{index}: event_id sequence {eid[:6]} does not match "
            f"chain position {index + 1}")
    if seen_ids is not None and eid in seen_ids:
        raise ChainError(f"event #{index}: duplicate event_id {eid!r}")
    if compute_event_hash(event) != event.get("event_hash"):
        raise ChainError(
            f"event #{index} ({eid!r}): event_hash does not match canonical "
            "content — chain tampered or torn")


def verify_chain(root: str) -> ChainReport:
    events = []
    seen_ids = set()
    prev_hash = GENESIS_HASH
    complete, tail = storage.read_events_with_tail(storage.events_path(root))
    try:
        for event in complete:
            _verify_one(event, prev_hash, len(events), seen_ids)
            events.append(event)
            seen_ids.add(event.get("event_id"))
            prev_hash = event["event_hash"]
    except (ChainError, ValueError, KeyError) as exc:
        return ChainReport(ok=False, length=len(events), head_hash=prev_hash,
                           error=str(exc), error_index=len(events))
    return ChainReport(ok=True, length=len(events), head_hash=prev_hash,
                       suffix_incomplete=tail["torn"],
                       torn_bytes=tail["torn_bytes"])


def head(root: str) -> tuple:
    """(sequence_length, head_hash) — GENESIS_HASH for an empty chain."""
    events = read_chain(root, verify=False)
    return len(events), (events[-1]["event_hash"] if events else GENESIS_HASH)


def build_event(event_type: str, sender: str, request_id: str,
                repository: str, target_commit: str, payload: dict,
                seq: int, previous_event_hash: str) -> dict:
    event = {
        "protocol_version": protocol_version(),
        "event_id": f"{seq:06d}-{uuid.uuid4().hex[:8]}",
        "event_type": event_type,
        "request_id": request_id,
        "sender": sender,
        "timestamp_utc": storage.utc_now(),
        "repository": repository,
        "target_commit": target_commit,
        "payload": payload,
        "previous_event_hash": previous_event_hash,
    }
    event["event_hash"] = compute_event_hash(event)
    return event


def append_event(root: str, cfg: Config, event_type: str, sender: str,
                 request_id: str, repository: str, target_commit: str,
                 payload: dict, enrollment_token: str = None) -> dict:
    """The one and only writer of events.jsonl. enrollment_token is the
    NON-PERSISTED bootstrap proof required exclusively by
    HUMAN_IDENTITY_INITIALIZED (verified against the root-owned anchor
    inside _verify_human_token; it never enters the chain)."""
    lock = locking.acquire_events_lock(root, sender, request_id)
    try:
        # emergency stop precedes every transition; only the events that
        # RECORD a stop may pass while it is engaged. Bootstrap/control
        # events (H1) pass a control-record pause — they are how the owner
        # un-pauses a fail-closed root — but NEVER the STOP file.
        if event_type in CONTROL_BOOTSTRAP_EVENT_TYPES:
            if storage.stop_file_present(root):
                raise CouncilError(
                    "council/STOP file exists — the hard emergency stop "
                    f"refuses {event_type}; the owner removes STOP first")
        elif event_type not in STOP_EXEMPT_EVENT_TYPES:
            reason = storage.emergency_stop_reason(root)
            if reason:
                raise CouncilError(
                    f"emergency stop engaged ({reason}) — refusing "
                    f"{event_type}; record AUTONOMY_PAUSED instead")
        # H4: appending after a torn trailing line would fuse two lines
        # and corrupt the chain — read_chain(verify=True) now raises on a
        # torn tail, so this fails closed before any write
        chain = read_chain(root, verify=True)
        seq = len(chain) + 1
        prev = chain[-1]["event_hash"] if chain else GENESIS_HASH
        event = build_event(event_type, sender, request_id, repository,
                            target_commit, payload, seq, prev)
        validate_event(event, for_append=True)
        requests = state_machine.project(chain)
        state_machine.check(event, requests)
        # H3: verdict authority-context bindings verified against the chain
        from tools.council.schemas import (crosscheck_verdict_bindings,
                                           VERDICT_PAYLOAD_EVENT_TYPES)
        if event_type in VERDICT_PAYLOAD_EVENT_TYPES:
            crosscheck_verdict_bindings(event, chain, requests)
        # H1: burn the human one-time token (if this event type requires
        # one) durably BEFORE the line lands — a crash here wastes a
        # token, it never leaves a spendable one behind an appended event
        _verify_human_token(root, chain, event, enrollment_token)
        storage.append_line(storage.events_path(root), canonical_json(event))
        try:  # state.json is best-effort cache; the append already succeeded
            state_machine.apply(event, requests)
            chain.append(event)
            state_machine.rebuild(root, chain, event["event_hash"])
        except OSError:
            pass
        return event
    finally:
        locking.release(lock)


def _verify_human_token(root: str, chain: list, event: dict,
                        enrollment_token) -> None:
    """H1: human authority is a burned one-time token (tools/council/
    identity.py), never a caller-supplied sender string. Runs INSIDE the
    events lock, immediately before the append. The FIRST identity pin
    requires a NON-PERSISTED enrollment proof verified against the
    root-owned anchor (cycle-2 blocker 1: enforcement lives HERE in the
    authoritative writer, not in any CLI). Pre-cutover chains (no
    verifier file AND no pinned identity event) stay tokenless so legacy
    roots replay; once either exists, these events fail closed."""
    from tools.council import identity
    etype = event["event_type"]
    if etype == "HUMAN_IDENTITY_INITIALIZED":
        pin, _state = identity.replay_identity(chain)
        if pin is not None:
            raise CouncilError(
                "identity already rooted — re-rooting is impossible; use "
                "rotation (old-chain token required)")
        identity.check_enrollment(enrollment_token)
        return
    if etype not in HUMAN_TOKEN_REQUIRED_EVENT_TYPES:
        return
    if etype == "REQUEST_CANCELED" and event["sender"] != "human":
        return  # agent cancels revoke authority; they never grant it
    pin, expected_state = identity.replay_identity(chain)  # raises on
    # inconsistent identity history — every consumer fails closed
    verifier_exists = identity.read_verifier(root) is not None
    if pin is None and not verifier_exists:
        return  # pre-cutover legacy behavior
    if pin is None and verifier_exists:
        # cycle-1 blocker 2: a verifier without its chain pin is NEVER
        # authority — a crashed/refused bootstrap must complete (or be
        # removed by the owner) before any token event lands
        raise CouncilError(
            "identity verifier exists without a chain pin — bootstrap "
            "incomplete; token-required events fail closed (re-run "
            "identity-init after removing the orphan verifier, or "
            "complete the pin)")
    payload = event["payload"]
    expected = identity.binding_hash(
        etype, event["request_id"], event["target_commit"],
        {k: v for k, v in payload.items() if k != "human_token"})
    identity.verify_and_advance(root, payload.get("human_token"), expected,
                                expected_state=expected_state)


def pause_autonomy(root: str, cfg: Config, sender: str, request_id: str,
                   repository: str, target_commit: str, reason: str) -> dict:
    """Record AUTONOMY_PAUSED (allowed even under emergency stop)."""
    return append_event(root, cfg, "AUTONOMY_PAUSED", sender, request_id,
                        repository, target_commit,
                        {"reason": reason, "recorded_by": sender})
