"""Filesystem primitives, drvfs-safe.

The council root lives on a WSL drvfs mount, so the strongest atomicity
available is same-directory os.rename plus O_CREAT|O_EXCL. fsync is applied
"when practical" (drvfs sometimes refuses it — swallowed, never fatal).
log.md is opened in append mode ONLY: this module physically cannot rewrite
history."""
from __future__ import annotations

import datetime
import json
import os

from tools.council.schemas import (SchemaViolation, canonical_json,
                                   validate_request_id)

EVENTS_FILE = "events.jsonl"
STATE_FILE = "state.json"
LOG_FILE = "log.md"
REQUEST_BUCKETS = ("draft", "ready", "claimed", "complete")


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc) \
        .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _fsync_quietly(fh) -> None:
    try:
        fh.flush()
        os.fsync(fh.fileno())
    except OSError:
        pass  # drvfs: fsync when practical


def ensure_layout(root: str) -> None:
    for bucket in REQUEST_BUCKETS:
        os.makedirs(os.path.join(root, "requests", bucket), exist_ok=True)
    os.makedirs(os.path.join(root, "verdicts"), exist_ok=True)
    os.makedirs(os.path.join(root, "locks"), exist_ok=True)
    os.makedirs(os.path.join(root, ".cursors"), exist_ok=True)
    events = os.path.join(root, EVENTS_FILE)
    if not os.path.exists(events):
        with open(events, "a", encoding="utf-8") as fh:
            _fsync_quietly(fh)


def atomic_write_json(path: str, obj) -> None:
    """Same-directory tmp -> fsync -> rename. Readers never see a partial."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(canonical_json(obj) + "\n")
        _fsync_quietly(fh)
    os.rename(tmp, path)


def append_line(path: str, line: str) -> None:
    if "\n" in line:
        raise SchemaViolation("append_line takes exactly one line")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        _fsync_quietly(fh)


def read_events_from(path: str, offset: int = 0):
    """Yield (next_offset, event_dict) for complete lines from byte offset.
    A torn trailing line (no newline yet) is NOT consumed — the caller's
    cursor stays before it and re-reads next poll."""
    if not os.path.exists(path):
        return
    with open(path, "rb") as fh:
        fh.seek(offset)
        while True:
            raw = fh.readline()
            if not raw:
                return
            if not raw.endswith(b"\n"):
                # torn write in progress: yield nothing for it, so the
                # caller's cursor stays put and re-reads it next poll
                return
            text = raw.decode("utf-8").strip()
            if not text:
                continue
            yield fh.tell(), json.loads(text)


def events_path(root: str) -> str:
    return os.path.join(root, EVENTS_FILE)


def state_path(root: str) -> str:
    return os.path.join(root, STATE_FILE)


def safe_request_path(root: str, bucket: str, request_id: str) -> str:
    """Paths are built only from a validated slug — no traversal possible."""
    if bucket not in REQUEST_BUCKETS:
        raise SchemaViolation(f"unknown request bucket {bucket!r}")
    validate_request_id(request_id)
    return os.path.join(root, "requests", bucket, request_id + ".json")


def lock_path(root: str, name: str) -> str:
    base = name if name.startswith("_") else validate_request_id(name)
    return os.path.join(root, "locks", base + ".lock")


def verdict_path(root: str, request_id: str) -> str:
    validate_request_id(request_id)
    return os.path.join(root, "verdicts", request_id + ".json")


def cursor_path(root: str, role: str) -> str:
    if role not in ("claude", "codex", "human"):
        raise SchemaViolation(f"unknown cursor role {role!r}")
    return os.path.join(root, ".cursors", role + ".json")


def read_cursor(root: str, role: str) -> dict:
    path = cursor_path(root, role)
    if not os.path.exists(path):
        return {"byte_offset": 0, "last_event_hash": None,
                "last_event_id": None, "updated_utc": None}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_cursor(root: str, role: str, byte_offset: int,
                 last_event_hash, last_event_id) -> None:
    atomic_write_json(cursor_path(root, role),
                      {"byte_offset": byte_offset,
                       "last_event_hash": last_event_hash,
                       "last_event_id": last_event_id,
                       "updated_utc": utc_now()})


# ----------------------------------------- emergency stop + control record

STOP_FILE = "STOP"
POLICY_FILE = "autonomy_policy.json"
CONTROL_FILE = "control.json"

_CONTROL_ROLES = ("claude", "codex", "human", "jaharri", "all")

FAIL_CLOSED_CONTROL = {
    "schema_version": "control.v1", "status": "paused",
    "paused_roles": ["all"],
    "reason": "control record missing or invalid — fail closed",
    "changed_utc": None, "authorized_by_event": None, "fail_closed": True,
}


def stop_file_path(root: str) -> str:
    return os.path.join(root, STOP_FILE)


def stop_file_present(root: str) -> bool:
    return os.path.exists(stop_file_path(root))


def policy_path(root: str) -> str:
    return os.path.join(root, POLICY_FILE)


def control_path(root: str) -> str:
    return os.path.join(root, CONTROL_FILE)


def read_control(root: str) -> dict:
    """The AUTHORITATIVE run/pause state (H1: STATUS moved out of log.md).
    Missing, unreadable, or schema-invalid → paused-all (FAIL CLOSED).
    A PAUSED record is honored as written — reducing authority needs no
    proof. An ACTIVE record is honored ONLY when it binds to the verified
    chain (cycle-2 blocker 2): its authorized_by_event must be the LAST
    STATUS_CHANGED event, whose replay-validated payload exactly matches
    the record — an attacker-written active file resumes nothing.
    Pre-cutover roots (no identity pin in the chain) keep legacy
    shape-only reads; the live council is pinned and fully bound."""
    path = control_path(root)
    if not os.path.exists(path):
        return dict(FAIL_CLOSED_CONTROL)
    try:
        with open(path, encoding="utf-8") as fh:
            control = json.load(fh)
    except (OSError, ValueError):
        return dict(FAIL_CLOSED_CONTROL)
    if not isinstance(control, dict) \
            or control.get("schema_version") != "control.v1" \
            or control.get("status") not in ("active", "paused") \
            or not isinstance(control.get("paused_roles"), list) \
            or any(r not in _CONTROL_ROLES
                   for r in control.get("paused_roles", [])):
        return dict(FAIL_CLOSED_CONTROL)
    if control["status"] == "paused":
        return control
    # ACTIVE requires chain authorization (lazy imports: events/identity
    # import storage at module load; by call time all are loaded)
    from tools.council import events, identity
    from tools.council.schemas import CouncilError
    try:
        chain = events.read_chain(root)
        root_pin, _state = identity.replay_identity(chain)
    except (CouncilError, KeyError, ValueError, OSError):
        return dict(FAIL_CLOSED_CONTROL)
    if root_pin is None:
        return control  # pre-cutover legacy root (documented)
    status_events = [e for e in chain
                     if e["event_type"] == "STATUS_CHANGED"]
    if not status_events:
        return dict(FAIL_CLOSED_CONTROL)
    last = status_events[-1]
    payload = last["payload"]
    if control.get("authorized_by_event") != last["event_id"] \
            or payload.get("status") != control["status"] \
            or payload.get("paused_roles") != control["paused_roles"] \
            or payload.get("reason") != control.get("reason"):
        return dict(FAIL_CLOSED_CONTROL)
    return control


def write_control(root: str, status: str, paused_roles: list, reason: str,
                  authorized_by_event) -> dict:
    """Derive control.json. Callers MUST have appended the authorizing
    STATUS_CHANGED event first (cli status-set is the only sanctioned
    path; tests and bootstrap write directly via this helper)."""
    control = {"schema_version": "control.v1", "status": status,
               "paused_roles": list(paused_roles), "reason": reason,
               "changed_utc": utc_now(),
               "authorized_by_event": authorized_by_event}
    atomic_write_json(control_path(root), control)
    return control


def emergency_stop_reason(root: str):
    """Checked before EVERY transition: the control record must read
    'active' and council/STOP must not exist. Returns a reason string, or
    None if clear. log.md is COSMETIC and can never resume autonomy."""
    if stop_file_present(root):
        return "council/STOP file exists"
    control = read_control(root)
    if control["status"] != "active":
        return (f"control record status is {control['status']!r} "
                f"({control.get('reason') or 'no reason recorded'})")
    return None


def status_allows(root: str, author: str) -> bool:
    control = read_control(root)
    if control["status"] == "active":
        return True
    roles = control.get("paused_roles") or ["all"]
    return "all" not in roles and author not in roles


# --------------------------------------------------------------------- log.md

def read_status(root: str) -> str:
    """COSMETIC ONLY (H1): the log.md first line survives as a mirror for
    humans skimming the log; no authority path reads it."""
    path = os.path.join(root, LOG_FILE)
    if not os.path.exists(path):
        return "STATUS: (no log.md)"
    with open(path, encoding="utf-8") as fh:
        first = fh.readline().strip()
    return first if first.upper().startswith("STATUS:") else "STATUS: (none)"


def append_log_md(root: str, author: str, body: str) -> None:
    """Append one attributed entry. 'a' mode only — history is untouchable.
    Refuses when the STATUS kill-switch pauses this author."""
    if author not in ("claude", "codex", "human", "jaharri"):
        raise SchemaViolation(f"unknown log author {author!r}")
    if not status_allows(root, author):
        raise SchemaViolation(
            f"log.md STATUS pauses {author!r} — refusing to append")
    date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    entry = f"\n## [{author}] {date}\n\n{body.rstrip()}\n"
    path = os.path.join(root, LOG_FILE)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(entry)
        _fsync_quietly(fh)
