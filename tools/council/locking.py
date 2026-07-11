"""O_CREAT|O_EXCL lock files. A lock names its holder (request_id, role, pid,
host, timestamp). Duplicate acquisition raises LockHeld. Stale locks are
NEVER cleared implicitly — only cli clear-lock, which logs a WATCHER_ERROR
event first (the "explicit logged operation")."""
from __future__ import annotations

import json
import os
import socket
import time
from dataclasses import dataclass

from tools.council import storage
from tools.council.schemas import LockHeld, canonical_json

EVENTS_LOCK = "_events"


@dataclass
class Lock:
    path: str
    name: str
    role: str


def acquire(root: str, name: str, role: str, request_id: str) -> Lock:
    path = storage.lock_path(root, name)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        holder = read_lock(root, name)
        raise LockHeld(f"lock {name!r} already held: {holder}")
    try:
        body = canonical_json({"request_id": request_id, "role": role,
                               "pid": os.getpid(),
                               "host": socket.gethostname(),
                               "timestamp_utc": storage.utc_now()})
        os.write(fd, (body + "\n").encode("utf-8"))
        try:
            os.fsync(fd)
        except OSError:
            pass
    finally:
        os.close(fd)
    return Lock(path=path, name=name, role=role)


def release(lock: Lock) -> None:
    try:
        os.unlink(lock.path)
    except FileNotFoundError:
        pass


def read_lock(root: str, name: str):
    path = storage.lock_path(root, name)
    if not os.path.exists(path):
        return None
    from tools.council.strictjson import loads_strict, StrictJSONError
    try:
        with open(path, "rb") as fh:
            return loads_strict(fh.read(), max_bytes=16_384)
    except (OSError, ValueError, StrictJSONError):
        return {"unreadable": True}


def acquire_events_lock(root: str, role: str, request_id: str,
                        attempts: int = 50, delay: float = 0.1) -> Lock:
    """Short-lived mutex serializing appends to events.jsonl."""
    last = None
    for _ in range(attempts):
        try:
            return acquire(root, EVENTS_LOCK, role, request_id)
        except LockHeld as exc:
            last = exc
            time.sleep(delay)
    raise LockHeld(f"events lock unavailable after {attempts} attempts: {last}")


def clear_lock(root: str, name: str) -> dict:
    """Low-level removal. Callers MUST have appended the logging event first
    (cli.clear-lock is the only sanctioned path)."""
    holder = read_lock(root, name)
    path = storage.lock_path(root, name)
    if os.path.exists(path):
        os.unlink(path)
    return holder or {}
