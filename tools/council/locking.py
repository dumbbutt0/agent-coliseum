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


def _write_all(fd: int, data: bytes) -> None:
    """Write EVERY byte of a lock body. os.write may perform a SHORT write
    (fewer bytes than requested, without raising), which would leave a
    truncated, unreadable, tokenless lock; loop until the whole body lands
    and raise if no progress can be made so the caller cleans up the
    partial."""
    view = memoryview(data)
    written = 0
    while written < len(data):
        n = os.write(fd, view[written:])
        if n <= 0:
            raise OSError("short write persisting lock body")
        written += n


def acquire(root: str, name: str, role: str, request_id: str,
            lease_seconds: float = DEFAULT_LEASE_SECONDS,
            kind: str = "generic", owner_token: str | None = None) -> Lock:
    """O_EXCL create + lease body. A caller may SUPPLY the owner_token
    (crash-safe claim records it in its journal BEFORE acquiring, so
    recovery can release a lock the process died holding); otherwise one is
    minted here."""
    path = storage.lock_path(root, name)
    token = owner_token or secrets.token_hex(16)
    body = canonical_json({"schema_version": "lock.v1",
                           "request_id": request_id, "role": role,
                           "pid": os.getpid(),
                           "host": socket.gethostname(),
                           "timestamp_utc": storage.utc_now(),
                           "owner_token": token,
                           "lease_expires_utc": _lease_expiry(lease_seconds),
                           "kind": kind})
    _create_lock(root, name, path, body)
    return Lock(path=path, name=name, role=role, root=root,
                owner_token=token)


def _create_lock(root: str, name: str, path: str, body: str) -> None:
    """The single durable lock-create boundary (H6 completeness fix): O_EXCL
    create then write the whole body.

    CONTRACT (H6 cycle-2, explicitly narrowed): if the BODY WRITE fails after
    the create, the on-disk lock is partial/tokenless — we unlink it before
    re-raising so no lock is stranded that compare-and-delete could never
    remove. The subsequent fsync is BEST-EFFORT, consistent with the
    codebase-wide `_fsync_quietly` policy (the council root lives on drvfs,
    where fsync can legitimately fail): once the body write has returned, the
    lock file is COMPLETE and carries its owner_token, so it is a valid,
    releasable lock even if the durability barrier could not be issued —
    unlinking a fully-written lock on an fsync error would wrongly drop a
    lock a caller believes it holds. O_EXCL guarantees we only ever unlink a
    lock WE just created — never another holder's."""
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        holder = read_lock(root, name)
        raise LockHeld(f"lock {name!r} already held: {holder}")
    try:
        _write_all(fd, (body + "\n").encode("utf-8"))
    except BaseException:
        # the body is not fully written (raise OR a short write): remove the
        # partial lock before re-raising so compare-and-delete never faces a
        # tokenless lock
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    try:
        os.fsync(fd)              # best-effort durability (drvfs-tolerant)
    except OSError:
        pass
    os.close(fd)


def _write_lock_excl(path: str, body: dict) -> bool:
    """O_EXCL-create `path` with `body`; return False WITHOUT clobbering if a
    file already exists there. The restore commit point for renew — a lock
    re-acquired in the swap vacancy is never overwritten."""
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    try:
        _write_all(fd, (canonical_json(body) + "\n").encode("utf-8"))
    except BaseException:
        # a partial/short write must not leave a truncated, unreadable lock
        # here either (H6 cycle-4): remove it before re-raising
        try:
            os.close(fd)
        except OSError:
            pass
        _unlink_quietly(path)
        raise
    try:
        os.fsync(fd)          # best-effort durability (drvfs-tolerant)
    except OSError:
        pass
    os.close(fd)
    return True


def renew(lock: Lock, lease_seconds: float = DEFAULT_LEASE_SECONDS) -> None:
    """Extend the lease — ownership-preserving (H5 cycle-2 fix, round 2).

    Two failure modes had to close together: (a) a stale owner must never
    OVERWRITE a replacement lock, and (b) renew must never MOVE a lock it
    does not own. So we first CONFIRM ownership by reading — a lock that is
    not ours is left completely untouched and renew fails closed. Only then
    do we move OUR lock aside (compare-and-delete already forbids any other
    party from taking it, so what we grab is still ours) and restore it in
    place with an O_EXCL create; if a lock was re-acquired during that brief
    vacancy we do NOT clobber it and fail closed instead. No path overwrites
    another holder's lock at any point."""
    if lock.root is None or lock.owner_token is None:
        raise LockHeld("cannot renew a lock without its owner token")
    # (1) confirm ownership by READING — never disturb a non-owned lock
    holder = read_lock(lock.root, lock.name)
    if not isinstance(holder, dict) or \
            holder.get("owner_token") != lock.owner_token:
        raise LockHeld("renew refused — not the lock owner")
    # (2) grab OUR lock aside (single-winner rename; compare-and-delete keeps
    #     it ours between the read above and here) and update its lease
    aside = f"{lock.path}.renew.{lock.owner_token}"
    try:
        os.rename(lock.path, aside)
    except OSError:
        raise LockHeld("renew refused — lock is gone")
    body = read_lock_file(aside)
    if not isinstance(body, dict) or \
            body.get("owner_token") != lock.owner_token:
        # unreachable while compare-and-delete protects our lock, but if it
        # ever happens, put the grabbed file back (write-free rename, never
        # clobbering a replacement) and fail closed.
        _restore_aside(aside, lock.path)
        raise LockHeld("renew refused — ownership changed during renew")
    body["lease_expires_utc"] = _lease_expiry(lease_seconds)
    try:
        placed = _write_lock_excl(lock.path, body)
    except OSError:
        # the renewed body could not be fully written (short-write stall);
        # _write_lock_excl already removed the truncated lock, so restore the
        # ORIGINAL lock — the aside file IS the intact original, so a
        # write-free rename puts it back with no risk of a second short write
        # (this is what a write-based restore could not guarantee). Then fail
        # closed.
        _restore_aside(aside, lock.path)
        raise LockHeld("renew refused — could not persist the renewed lease")
    if not placed:
        # a lock was re-acquired in the vacancy — do not clobber it
        _unlink_quietly(aside)
        raise LockHeld("renew refused — lock re-acquired during renew")
    _unlink_quietly(aside)


def _restore_aside(aside: str, path: str) -> None:
    """Put the intact original lock (already sitting at `aside` after the
    move-aside) back at `path` with a WRITE-FREE rename — no os.write, so no
    short-write can strand it. Only restores into a still-vacant path so a
    lock re-acquired in the renew vacancy is never clobbered; if `path` is
    occupied the caller's lock was legitimately superseded and the aside copy
    is discarded."""
    try:
        if not os.path.exists(path):
            os.rename(aside, path)      # atomic, write-free restore
        else:
            _unlink_quietly(aside)      # superseded by a racer — discard
    except OSError:
        pass


def _unlink_quietly(path: str) -> None:
    try:
        os.unlink(path)
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
