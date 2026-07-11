"""Hash-pinned machine-readable roadmap: the ONLY source of eligible tasks.

The roadmap file is a deliberately strict YAML SUBSET (this repo is
stdlib-only, so no PyYAML): two-space indentation, mappings, block sequences,
scalars, `[]` for an empty list, full-line comments. Anything else — tabs,
flow collections, anchors, aliases, multiline scalars, inline comments after
values — is refused loudly. The roadmap hash is the sha256 of the raw file
bytes; requests pin it, and the guard refuses drift.

Authority order (owner directive): the immutable autonomy policy caps every
roadmap limit — a roadmap limit may be STRICTER than policy, never larger.
"""
from __future__ import annotations

import hashlib
import re

from tools.autonomy import (ALLOWED_TASK_CLASSES, FORBIDDEN_TASK_CLASSES,
                            TASK_STATUSES)


class RoadmapError(Exception):
    pass


_TASK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
_INT_RE = re.compile(r"^-?\d+$")

REQUIRED_TASK_FIELDS = (
    "task_id", "title", "phase", "status", "dependencies",
    "allowed_files", "forbidden_files", "audit_scope", "experiment_class",
    "maximum_fix_cycles", "maximum_runtime_minutes",
    "maximum_storage_growth_mb", "expected_tests",
    "success_criteria", "failure_criteria", "evidence_required",
    "requires_human", "next_tasks",
)

_LIST_FIELDS = ("dependencies", "allowed_files", "forbidden_files",
                "success_criteria", "failure_criteria", "evidence_required",
                "next_tasks")
_INT_FIELDS = ("maximum_fix_cycles", "maximum_runtime_minutes",
               "maximum_storage_growth_mb")
_STR_FIELDS = ("task_id", "title", "phase", "status", "audit_scope",
               "experiment_class", "expected_tests")


# ------------------------------------------------------- strict YAML subset

def _scalar(raw: str, where: str):
    text = raw.strip()
    if text == "":
        raise RoadmapError(f"{where}: empty value (use [] for an empty list)")
    for marker in ("&", "*", "|", ">", "{", "}"):
        if text.startswith(marker):
            raise RoadmapError(
                f"{where}: YAML feature {marker!r} is outside the strict "
                "subset")
    if text == "[]":
        return []
    if text.startswith("[") or text.endswith("]"):
        raise RoadmapError(f"{where}: flow sequences other than [] refused")
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    if text == "true":
        return True
    if text == "false":
        return False
    if _INT_RE.match(text):
        return int(text)
    return text


def _tokenize(text: str) -> list:
    tokens = []
    for lineno, raw in enumerate(text.split("\n"), 1):
        if "\t" in raw:
            raise RoadmapError(f"line {lineno}: tabs are refused")
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent % 2:
            raise RoadmapError(f"line {lineno}: odd indentation {indent}")
        tokens.append((lineno, indent, stripped))
    return tokens


def parse_strict_yaml(text: str):
    """Parse the strict subset. Returns the top-level mapping."""
    tokens = _tokenize(text)
    if not tokens:
        raise RoadmapError("empty roadmap")
    pos = [0]

    def peek():
        return tokens[pos[0]] if pos[0] < len(tokens) else None

    def parse_block(indent: int):
        tok = peek()
        if tok is None or tok[1] != indent:
            raise RoadmapError("internal: parse_block at wrong position")
        if tok[2].startswith("- ") or tok[2] == "-":
            return _parse_sequence(indent)
        return _parse_mapping(indent)

    def _parse_mapping(indent: int) -> dict:
        out: dict = {}
        while True:
            tok = peek()
            if tok is None or tok[1] < indent:
                return out
            lineno, tindent, body = tok
            if tindent > indent:
                raise RoadmapError(f"line {lineno}: unexpected indent")
            if body.startswith("- "):
                raise RoadmapError(
                    f"line {lineno}: sequence item where a mapping key was "
                    "expected")
            if ":" not in body:
                raise RoadmapError(f"line {lineno}: expected 'key: value'")
            key, _, rest = body.partition(":")
            key = key.strip()
            if not key:
                raise RoadmapError(f"line {lineno}: empty key")
            if key in out:
                raise RoadmapError(f"line {lineno}: duplicate key {key!r}")
            pos[0] += 1
            if rest.strip():
                out[key] = _scalar(rest, f"line {lineno} ({key})")
            else:
                nxt = peek()
                if nxt is None or nxt[1] <= indent:
                    raise RoadmapError(
                        f"line {lineno}: key {key!r} has no value "
                        "(use [] for an empty list)")
                out[key] = parse_block(nxt[1])

    def _parse_sequence(indent: int) -> list:
        out: list = []
        while True:
            tok = peek()
            if tok is None or tok[1] < indent:
                return out
            lineno, tindent, body = tok
            if tindent > indent:
                raise RoadmapError(f"line {lineno}: unexpected indent")
            if not body.startswith("- "):
                if body == "-":
                    raise RoadmapError(
                        f"line {lineno}: bare '-' items are refused")
                return out
            item = body[2:]
            pos[0] += 1
            if ":" in item and not (
                    len(item) >= 2 and item[0] == item[-1]
                    and item[0] in ("'", '"')):
                # inline mapping start: '- key: value'; continuation keys
                # align two spaces past the dash
                key, _, rest = item.partition(":")
                key = key.strip()
                if not key:
                    raise RoadmapError(f"line {lineno}: empty key in item")
                entry = {}
                if rest.strip():
                    entry[key] = _scalar(rest, f"line {lineno} ({key})")
                else:
                    nxt = peek()
                    if nxt is None or nxt[1] <= indent + 2:
                        raise RoadmapError(
                            f"line {lineno}: key {key!r} has no value")
                    entry[key] = parse_block(nxt[1])
                more = peek()
                if more is not None and more[1] == indent + 2:
                    rest_map = _parse_mapping(indent + 2)
                    dup = set(entry) & set(rest_map)
                    if dup:
                        raise RoadmapError(
                            f"line {lineno}: duplicate keys {sorted(dup)}")
                    entry.update(rest_map)
                out.append(entry)
            else:
                out.append(_scalar(item, f"line {lineno}"))

    top = parse_block(tokens[0][1])
    if pos[0] != len(tokens):
        lineno = tokens[pos[0]][0]
        raise RoadmapError(f"line {lineno}: trailing content outside the "
                           "top-level block")
    if not isinstance(top, dict):
        raise RoadmapError("roadmap top level must be a mapping")
    return top


# ------------------------------------------------------------- validation

def validate_roadmap(doc: dict, policy: dict) -> None:
    """Schema + policy-cap validation. Raises RoadmapError on the first
    violation; a roadmap that does not validate authorizes nothing."""
    if doc.get("roadmap_version") != "1":
        raise RoadmapError("roadmap_version must be '1' (string)")
    if not isinstance(doc.get("milestone"), str) or not doc["milestone"]:
        raise RoadmapError("milestone must be a non-empty string")
    tasks = doc.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise RoadmapError("tasks must be a non-empty sequence")

    caps = policy["auto_approval"]["limits"]
    loops = policy["bounded_loops"]
    protected = tuple(policy["protected_paths"])

    ids = set()
    active = []
    for i, task in enumerate(tasks):
        where = f"tasks[{i}]"
        if not isinstance(task, dict):
            raise RoadmapError(f"{where}: task must be a mapping")
        missing = [f for f in REQUIRED_TASK_FIELDS if f not in task]
        if missing:
            raise RoadmapError(f"{where}: missing required fields {missing}")
        extra = [k for k in task if k not in REQUIRED_TASK_FIELDS]
        if extra:
            raise RoadmapError(f"{where}: unknown fields {sorted(extra)}")
        tid = task["task_id"]
        if not isinstance(tid, str) or not _TASK_ID_RE.match(tid):
            raise RoadmapError(f"{where}: invalid task_id {tid!r}")
        if tid in ids:
            raise RoadmapError(f"duplicate task_id {tid!r}")
        ids.add(tid)
        for f in _STR_FIELDS:
            if not isinstance(task[f], str) or not task[f]:
                raise RoadmapError(f"{tid}: {f} must be a non-empty string")
        for f in _LIST_FIELDS:
            v = task[f]
            if not isinstance(v, list) or \
                    any(not isinstance(x, str) or not x for x in v):
                raise RoadmapError(f"{tid}: {f} must be a list of strings")
        for f in _INT_FIELDS:
            v = task[f]
            if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
                raise RoadmapError(f"{tid}: {f} must be a positive int")
        if not isinstance(task["requires_human"], bool):
            raise RoadmapError(f"{tid}: requires_human must be a bool")
        if task["status"] not in TASK_STATUSES:
            raise RoadmapError(f"{tid}: unknown status {task['status']!r}")
        cls = task["experiment_class"]
        if cls in FORBIDDEN_TASK_CLASSES:
            raise RoadmapError(
                f"{tid}: experiment_class {cls!r} is FORBIDDEN for "
                "autonomous execution — this pauses autonomy, it never runs")
        if cls not in ALLOWED_TASK_CLASSES:
            raise RoadmapError(f"{tid}: unknown experiment_class {cls!r}")
        if not task["allowed_files"]:
            raise RoadmapError(f"{tid}: allowed_files must not be empty")
        for path in protected:
            if not any(path in f for f in task["forbidden_files"]):
                raise RoadmapError(
                    f"{tid}: forbidden_files must include the protected "
                    f"path {path!r}")
        # a roadmap limit may be stricter than policy, never larger
        if task["maximum_storage_growth_mb"] > caps["max_storage_mb"]:
            raise RoadmapError(
                f"{tid}: maximum_storage_growth_mb "
                f"{task['maximum_storage_growth_mb']} exceeds the policy cap "
                f"{caps['max_storage_mb']} MB")
        if task["maximum_runtime_minutes"] > caps["max_wall_minutes"]:
            raise RoadmapError(
                f"{tid}: maximum_runtime_minutes "
                f"{task['maximum_runtime_minutes']} exceeds the policy cap "
                f"{caps['max_wall_minutes']} min")
        if task["maximum_fix_cycles"] > loops["max_audit_cycles_per_request"]:
            raise RoadmapError(
                f"{tid}: maximum_fix_cycles {task['maximum_fix_cycles']} "
                "exceeds the policy bounded-loop cap "
                f"{loops['max_audit_cycles_per_request']}")
        if task["status"] == "active":
            active.append(tid)

    if len(active) > 1:
        raise RoadmapError(f"only one task may be active — found {active}")
    for task in tasks:
        for ref_field in ("dependencies", "next_tasks"):
            for ref in task[ref_field]:
                if ref not in ids:
                    raise RoadmapError(
                        f"{task['task_id']}: {ref_field} references unknown "
                        f"task {ref!r}")


# --------------------------------------------------------------- interface

def roadmap_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_roadmap(path: str, policy: dict) -> tuple:
    """(doc, hash). The hash is over the exact file bytes — the pin."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        raise RoadmapError(f"cannot read roadmap {path}: {exc}")
    doc = parse_strict_yaml(raw.decode("utf-8"))
    validate_roadmap(doc, policy)
    return doc, roadmap_hash(raw)


def task_by_id(doc: dict, task_id: str) -> dict:
    for task in doc["tasks"]:
        if task["task_id"] == task_id:
            return task
    raise RoadmapError(f"no task {task_id!r} in the roadmap")


def active_task(doc: dict):
    for task in doc["tasks"]:
        if task["status"] == "active":
            return task
    return None


def eligible_tasks(doc: dict) -> list:
    """Tasks that may start next: status ready, every dependency complete,
    and not requiring the human. requires_human tasks are listed by resume
    but never started autonomously."""
    done = {t["task_id"] for t in doc["tasks"] if t["status"] == "complete"}
    out = []
    for task in doc["tasks"]:
        if task["status"] != "ready":
            continue
        if any(dep not in done for dep in task["dependencies"]):
            continue
        out.append(task)
    return out
