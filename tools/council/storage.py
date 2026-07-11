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


# ------------------------------------------------------------- emergency stop

STOP_FILE = "STOP"
POLICY_FILE = "autonomy_policy.json"


def stop_file_path(root: str) -> str:
    return os.path.join(root, STOP_FILE)


def policy_path(root: str) -> str:
    return os.path.join(root, POLICY_FILE)


def emergency_stop_reason(root: str):
    """Checked before EVERY transition: council STATUS must be 'active' and
    council/STOP must not exist. Returns a reason string, or None if clear."""
    status = read_status(root).split(":", 1)[1].strip()
    if status.lower() != "active":
        return f"council STATUS is {status!r} (must be 'active')"
    if os.path.exists(stop_file_path(root)):
        return "council/STOP file exists"
    return None


# --------------------------------------------------------------------- log.md

def read_status(root: str) -> str:
    """First line of log.md, e.g. 'STATUS: active' or 'STATUS: paused codex'."""
    path = os.path.join(root, LOG_FILE)
    if not os.path.exists(path):
        return "STATUS: active"
    with open(path, encoding="utf-8") as fh:
        first = fh.readline().strip()
    return first if first.upper().startswith("STATUS:") else "STATUS: active"


def status_allows(root: str, author: str) -> bool:
    status = read_status(root).split(":", 1)[1].strip().lower()
    if status.startswith("paused"):
        paused_for = status.split("paused", 1)[1].strip()
        return bool(paused_for) and paused_for != author and \
            paused_for != "all"
    return True


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
