"""The authoritative append-only, hash-chained event log.

Every append: events-lock -> emergency-stop check -> role check -> replay ->
transition check -> write one canonical line -> refresh state.json. There is
no API that edits or deletes an event, ever.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from tools.council import Config, locking, state_machine, storage
from tools.council.schemas import (ChainError, CouncilError, GENESIS_HASH,
                                   STOP_EXEMPT_EVENT_TYPES, canonical_json,
                                   compute_event_hash, protocol_version,
                                   validate_event)


@dataclass
class ChainReport:
    ok: bool
    length: int
    head_hash: str
    error: str | None = None
    error_index: int | None = None


def read_chain(root: str, verify: bool = True) -> list:
    """All complete events, optionally verifying every hash and link."""
    events = []
    prev_hash = GENESIS_HASH
    for _offset, event in storage.read_events_from(storage.events_path(root)):
        if verify:
            _verify_one(event, prev_hash, len(events))
        events.append(event)
        prev_hash = event["event_hash"]
    return events


def _verify_one(event: dict, prev_hash: str, index: int) -> None:
    if event.get("previous_event_hash") != prev_hash:
        raise ChainError(
            f"event #{index} ({event.get('event_id')!r}): "
            f"previous_event_hash {event.get('previous_event_hash')!r} "
            f"does not chain to {prev_hash!r}")
    if compute_event_hash(event) != event.get("event_hash"):
        raise ChainError(
            f"event #{index} ({event.get('event_id')!r}): event_hash "
            "does not match canonical content — chain tampered or torn")


def verify_chain(root: str) -> ChainReport:
    events = []
    prev_hash = GENESIS_HASH
    try:
        for _offset, event in storage.read_events_from(
                storage.events_path(root)):
            _verify_one(event, prev_hash, len(events))
            events.append(event)
            prev_hash = event["event_hash"]
    except (ChainError, ValueError, KeyError) as exc:
        return ChainReport(ok=False, length=len(events), head_hash=prev_hash,
                           error=str(exc), error_index=len(events))
    return ChainReport(ok=True, length=len(events), head_hash=prev_hash)


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
                 payload: dict) -> dict:
    """The one and only writer of events.jsonl."""
    lock = locking.acquire_events_lock(root, sender, request_id)
    try:
        # emergency stop precedes every transition; only the events that
        # RECORD a stop may pass while it is engaged
        if event_type not in STOP_EXEMPT_EVENT_TYPES:
            reason = storage.emergency_stop_reason(root)
            if reason:
                raise CouncilError(
                    f"emergency stop engaged ({reason}) — refusing "
                    f"{event_type}; record AUTONOMY_PAUSED instead")
        chain = read_chain(root, verify=True)
        seq = len(chain) + 1
        prev = chain[-1]["event_hash"] if chain else GENESIS_HASH
        event = build_event(event_type, sender, request_id, repository,
                            target_commit, payload, seq, prev)
        validate_event(event)
        requests = state_machine.project(chain)
        state_machine.check(event, requests)
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


def pause_autonomy(root: str, cfg: Config, sender: str, request_id: str,
                   repository: str, target_commit: str, reason: str) -> dict:
    """Record AUTONOMY_PAUSED (allowed even under emergency stop)."""
    return append_event(root, cfg, "AUTONOMY_PAUSED", sender, request_id,
                        repository, target_commit,
                        {"reason": reason, "recorded_by": sender})
