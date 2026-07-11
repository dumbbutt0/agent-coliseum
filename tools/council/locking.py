"""O_CREAT|O_EXCL lock files with a LEASE and an unforgeable owner token
(hardening H5, item 7). A lock names its holder (request_id, role, pid,
host, timestamp) plus an owner_token (secrets) and a lease_expires_utc.
Release is COMPARE-AND-DELETE: only the token holder removes a live lock,
so PID reuse cannot steal a lock and an unrelated process cannot remove
one. Expired leases are eligible for the LOGGED stale-clearance paths
(cli clear-lock, the launcher's gate) — never removed implicitly."""
from __future__ import annotations

import datetime
import os
import secrets
import socket
import time
from dataclasses import dataclass

from tools.council import storage
from tools.council.schemas import LockHeld, canonical_json

EVENTS_LOCK = "_events"
DEFAULT_LEASE_SECONDS = 3600.0


@dataclass
class Lock:
    path: str
    name: str
    role: str
    root: str | None = None
    owner_token: str | None = None


def _lease_expiry(seconds: float) -> str:
    return (datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(seconds=seconds)).strftime(
                "%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def acquire(root: str, name: str, role: str, request_id: str,
            lease_seconds: float = DEFAULT_LEASE_SECONDS,
            kind: str = "generic", owner_token: str | None = None) -> Lock:
    """O_EXCL create + lease body. A caller may SUPPLY the owner_token
    (crash-safe claim records it in its journal BEFORE acquiring, so
    recovery can release a lock the process died holding); otherwise one is
    minted here."""
    path = storage.lock_path(root, name)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        holder = read_lock(root, name)
        raise LockHeld(f"lock {name!r} already held: {holder}")
    token = owner_token or secrets.token_hex(16)
    try:
        body = canonical_json({"schema_version": "lock.v1",
                               "request_id": request_id, "role": role,
                               "pid": os.getpid(),
                               "host": socket.gethostname(),
                               "timestamp_utc": storage.utc_now(),
                               "owner_token": token,
                               "lease_expires_utc": _lease_expiry(
                                   lease_seconds), "kind": kind})
        os.write(fd, (body + "\n").encode("utf-8"))
        try:
            os.fsync(fd)
        except OSError:
            pass
    finally:
        os.close(fd)
    return Lock(path=path, name=name, role=role, root=root,
                owner_token=token)


def renew(lock: Lock, lease_seconds: float = DEFAULT_LEASE_SECONDS) -> None:
    """Extend the lease — ownership-preserving compare-and-swap (H5 cycle-2
    fix). A plain read-verify-then-write let a stale owner overwrite a
    replacement lock if the holder was released and re-acquired between the
    read and the write. Instead we ATOMICALLY move the live lock aside
    (single-winner rename), confirm the moved body is still OURS, update it,
    and restore it with an O_EXCL create so a lock re-acquired during the
    swap window is never clobbered — a raced renew fails closed (LockHeld),
    never corrupts a live lease."""
    if lock.root is None or lock.owner_token is None:
        raise LockHeld("cannot renew a lock without its owner token")
    aside = f"{lock.path}.renew.{lock.owner_token}"
    try:
        os.rename(lock.path, aside)          # atomic single-winner grab
    except OSError:
        raise LockHeld("renew refused — lock is gone")
    body = read_lock_file(aside)
    if not isinstance(body, dict) or \
            body.get("owner_token") != lock.owner_token:
        # we grabbed a DIFFERENT owner's lock (released+reacquired between
        # our read and this rename) — put it back untouched and refuse
        try:
            os.rename(aside, lock.path)
        except OSError:
            pass
        raise LockHeld("renew refused — not the lock owner")
    body["lease_expires_utc"] = _lease_expiry(lease_seconds)
    try:
        fd = os.open(lock.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        # someone acquired in the swap window; do not clobber their lock
        try:
            os.unlink(aside)
        except OSError:
            pass
        raise LockHeld("renew refused — lock re-acquired during renew")
    try:
        os.write(fd, (canonical_json(body) + "\n").encode("utf-8"))
        try:
            os.fsync(fd)
        except OSError:
            pass
    finally:
        os.close(fd)
    try:
        os.unlink(aside)
    except OSError:
        pass


def release(lock: Lock) -> None:
    """COMPARE-AND-DELETE when the Lock carries its owner token (the
    normal path): verify the on-disk token still matches, then rename-then-
    unlink (a single-winner commit point on drvfs). A Lock WITHOUT a token
    (reconstructed by-name for a sanctioned logged clearance) blind-unlinks
    — that path is already gated + logged by its caller."""
    if lock.owner_token is None:
        try:
            os.unlink(lock.path)
        except FileNotFoundError:
            pass
        return
    holder = read_lock(lock.root, lock.name) if lock.root else None
    if not isinstance(holder, dict) or \
            holder.get("owner_token") != lock.owner_token:
        return  # not ours (or already gone) — never remove another's lock
    releasing = f"{lock.path}.releasing.{lock.owner_token[:8]}"
    try:
        os.rename(lock.path, releasing)   # atomic single-winner claim
    except OSError:
        return
    try:
        os.unlink(releasing)
    except OSError:
        pass


def read_lock(root: str, name: str):
    return read_lock_file(storage.lock_path(root, name))


def read_lock_file(path: str):
    """Read a lock body from an explicit path (used by renew's compare-and-
    swap on the moved-aside file)."""
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
