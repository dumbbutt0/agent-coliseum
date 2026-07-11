"""Crash-safe transactions with durable phase markers (hardening H5,
item 6).

Some council operations touch several files/events that must not be left
half-applied by a crash or an emergency STOP mid-operation. Each such
operation runs under a JOURNAL: council/txn/<txn_id>.json records the
ordered steps and which have completed. If the process dies (or STOP
refuses the terminal event) mid-transaction, recover() reads the journal,
consults the authoritative event chain, and either rolls forward (the
event landed) or rolls back (it did not) — idempotently. The journal is
deleted on clean completion.

The specific gap this closes (H4/plan): a STOP during CLAIM must not
strand a lock or leave a request half-moved without its AUDIT_CLAIMED
event. Recovery moves the file back to ready/ and releases the lock.
"""
from __future__ import annotations

import os
import uuid

from tools.council import locking, storage
from tools.council.schemas import CouncilError
from tools.council.strictjson import StrictJSONError, load_strict_file

TXN_DIR = "txn"


def _txn_dir(root: str) -> str:
    d = os.path.join(root, TXN_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def _txn_path(root: str, txn_id: str) -> str:
    return os.path.join(_txn_dir(root), txn_id + ".json")


def new_txn_id(kind: str, request_id: str) -> str:
    # no wall-clock in the id (Date.now is fine here, but keep it uuid-only
    # for determinism of tests); kind+rid+uuid is unique enough
    return f"{kind}-{request_id}-{uuid.uuid4().hex[:8]}"


class Txn:
    """A journalled transaction. begin() writes the journal; mark() records
    a durable phase; complete() deletes it. data carries the compensation
    inputs (paths, lock token)."""

    def __init__(self, root: str, txn_id: str, kind: str, request_id: str,
                 steps: list, data: dict):
        self.root = root
        self.txn_id = txn_id
        self.kind = kind
        self.request_id = request_id
        self.steps = steps
        self.completed: list = []
        self.data = data

    @classmethod
    def begin(cls, root: str, kind: str, request_id: str, steps: list,
              data: dict) -> "Txn":
        txn = cls(root, new_txn_id(kind, request_id), kind, request_id,
                  steps, data)
        txn._write()
        return txn

    def _write(self) -> None:
        storage.atomic_write_json(_txn_path(self.root, self.txn_id), {
            "schema_version": "txn.v1", "txn_id": self.txn_id,
            "kind": self.kind, "request_id": self.request_id,
            "steps": self.steps, "completed": self.completed,
            "data": self.data})

    def mark(self, step: str) -> None:
        if step not in self.completed:
            self.completed.append(step)
        self._write()

    def complete(self) -> None:
        try:
            os.unlink(_txn_path(self.root, self.txn_id))
        except OSError:
            pass


def _load(root: str, txn_id: str):
    try:
        return load_strict_file(_txn_path(root, txn_id), max_bytes=65_536)
    except (OSError, ValueError, StrictJSONError):
        return None


def _recover_claim(root: str, cfg, j: dict) -> str:
    """Roll forward if AUDIT_CLAIMED landed; else roll back the move + lock
    (idempotent). Returns 'forward' | 'back'."""
    from tools.council import events
    rid = j["request_id"]
    data = j["data"]
    claimed = any(e["event_type"] == "AUDIT_CLAIMED"
                  and e["request_id"] == rid
                  for e in events.read_chain(root))
    if claimed:
        return "forward"   # the event is authoritative; nothing to undo
    # roll back: request back to ready/ (if it was moved), lock released
    ready = storage.safe_request_path(root, "ready", rid)
    claimed_path = storage.safe_request_path(root, "claimed", rid)
    if os.path.exists(claimed_path) and not os.path.exists(ready):
        os.rename(claimed_path, ready)
    token = data.get("owner_token")
    if token:
        locking.release(locking.Lock(
            path=storage.lock_path(root, rid), name=rid, role="codex",
            root=root, owner_token=token))
    return "back"


_HANDLERS = {"claim": _recover_claim}


def recover(root: str, cfg) -> list:
    """Scan council/txn/ and finish every interrupted transaction. Runs at
    codex_watch startup and the launcher loop top. Idempotent."""
    d = os.path.join(root, TXN_DIR)
    if not os.path.isdir(d):
        return []
    healed = []
    for name in sorted(os.listdir(d)):
        if not name.endswith(".json"):
            continue
        j = _load(root, name[:-5])
        if not j or j.get("kind") not in _HANDLERS:
            continue
        try:
            outcome = _HANDLERS[j["kind"]](root, cfg, j)
            healed.append((j["txn_id"], outcome))
        except CouncilError:
            continue
        try:
            os.unlink(_txn_path(root, j["txn_id"]))
        except OSError:
            pass
    return healed
