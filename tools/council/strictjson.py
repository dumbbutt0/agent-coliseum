"""One strict JSON parser for every council input (hardening H2, item 8).

Python's json.loads is permissive by default: duplicate keys silently
resolve last-wins, NaN/Infinity parse, and there is no bound on size or
nesting. For a hash-pinned append-only protocol that is a correctness
hazard — the bytes that get hashed must be the bytes that get validated,
with no ambiguity. loads_strict rejects, BEFORE parsing or hashing:

  - duplicate object keys (object_pairs_hook)
  - NaN / Infinity / -Infinity (parse_constant)
  - trailing data after the top-level value (json.loads already does)
  - invalid UTF-8 (strict decode)
  - oversize bytes, and after parsing: excess depth, string length,
    collection size, and total node count

Limits are applied to the raw bytes BEFORE the parse (cheap DoS bound)
and to the structure AFTER (bounds downstream cost). Every council JSON
load routes through here; per-site limits are passed by the caller.
"""
from __future__ import annotations

import json

from tools.council.schemas import SchemaViolation

DEFAULT_MAX_BYTES = 1_048_576       # 1 MiB
DEFAULT_MAX_DEPTH = 32
DEFAULT_MAX_STRING = 100_000
DEFAULT_MAX_ITEMS = 10_000          # per collection
DEFAULT_MAX_NODES = 50_000          # total across the document


class StrictJSONError(SchemaViolation):
    """A JSON input violated a strictness rule or a resource limit."""


def _reject_duplicate_keys(pairs):
    seen = set()
    for key, _value in pairs:
        if key in seen:
            raise StrictJSONError(f"duplicate JSON key {key!r} — refused "
                                  "(last-wins ambiguity)")
        seen.add(key)
    return dict(pairs)


def _reject_constant(text):
    raise StrictJSONError(f"non-finite JSON constant {text!r} refused "
                          "(NaN/Infinity)")


def _walk_limits(obj, max_depth: int, max_string: int, max_items: int,
                 max_nodes: int) -> None:
    """Iterative structural walk enforcing depth/string/items/nodes."""
    nodes = 0
    stack = [(obj, 1)]
    while stack:
        node, depth = stack.pop()
        nodes += 1
        if nodes > max_nodes:
            raise StrictJSONError(
                f"JSON has more than {max_nodes} nodes — refused")
        if depth > max_depth:
            raise StrictJSONError(
                f"JSON nesting deeper than {max_depth} — refused")
        if isinstance(node, str):
            if len(node) > max_string:
                raise StrictJSONError(
                    f"JSON string longer than {max_string} chars — refused")
        elif isinstance(node, dict):
            if len(node) > max_items:
                raise StrictJSONError(
                    f"JSON object with more than {max_items} keys — refused")
            for key, value in node.items():
                if len(key) > max_string:
                    raise StrictJSONError(
                        f"JSON key longer than {max_string} chars — refused")
                stack.append((value, depth + 1))
        elif isinstance(node, list):
            if len(node) > max_items:
                raise StrictJSONError(
                    f"JSON array longer than {max_items} items — refused")
            for value in node:
                stack.append((value, depth + 1))


def loads_strict(data, *, max_bytes: int = DEFAULT_MAX_BYTES,
                 max_depth: int = DEFAULT_MAX_DEPTH,
                 max_string: int = DEFAULT_MAX_STRING,
                 max_items: int = DEFAULT_MAX_ITEMS,
                 max_nodes: int = DEFAULT_MAX_NODES):
    """Strict-parse JSON from bytes or str. See the module docstring."""
    if isinstance(data, str):
        raw = data.encode("utf-8", "surrogatepass")
    elif isinstance(data, (bytes, bytearray)):
        raw = bytes(data)
    else:
        raise StrictJSONError("loads_strict expects bytes or str")
    if len(raw) > max_bytes:
        raise StrictJSONError(
            f"JSON input is {len(raw)} bytes (> {max_bytes}) — refused "
            "before parsing")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StrictJSONError(f"JSON input is not valid UTF-8: {exc}")
    try:
        obj = json.loads(text, object_pairs_hook=_reject_duplicate_keys,
                         parse_constant=_reject_constant)
    except StrictJSONError:
        raise
    except ValueError as exc:
        raise StrictJSONError(f"malformed JSON: {exc}")
    _walk_limits(obj, max_depth, max_string, max_items, max_nodes)
    return obj


def load_strict_file(path: str, **limits):
    """Read a file as bytes and strict-parse it (limits pass through)."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        raise StrictJSONError(f"cannot read {path}: {exc}")
    return loads_strict(raw, **limits)
