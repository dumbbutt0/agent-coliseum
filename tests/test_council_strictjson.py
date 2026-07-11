"""H2 item 8: the single strict JSON parser rejects duplicate keys,
NaN/Infinity, trailing data, invalid UTF-8, and enforces byte/depth/
string/collection/node limits before hashing or validation."""
import pytest

from tools.council import strictjson
from tools.council.strictjson import StrictJSONError, loads_strict


def test_accepts_well_formed():
    assert loads_strict('{"a": 1, "b": [1, 2, 3]}') == {"a": 1,
                                                        "b": [1, 2, 3]}
    assert loads_strict(b'{"x": "y"}') == {"x": "y"}


def test_rejects_duplicate_keys():
    with pytest.raises(StrictJSONError, match="duplicate"):
        loads_strict('{"a": 1, "a": 2}')


def test_rejects_nested_duplicate_keys():
    with pytest.raises(StrictJSONError, match="duplicate"):
        loads_strict('{"outer": {"k": 1, "k": 2}}')


@pytest.mark.parametrize("const", ["NaN", "Infinity", "-Infinity"])
def test_rejects_non_finite_constants(const):
    with pytest.raises(StrictJSONError):
        loads_strict('{"x": %s}' % const)


def test_rejects_trailing_data():
    with pytest.raises(StrictJSONError):
        loads_strict('{"a": 1} garbage')
    with pytest.raises(StrictJSONError):
        loads_strict('{"a": 1}{"b": 2}')


def test_rejects_invalid_utf8():
    with pytest.raises(StrictJSONError, match="UTF-8"):
        loads_strict(b'{"a": "\xff\xfe"}')


def test_rejects_oversize_before_parse():
    big = b'{"a": "' + b'x' * 2000 + b'"}'
    with pytest.raises(StrictJSONError, match="before parsing"):
        loads_strict(big, max_bytes=100)


def test_rejects_excess_depth():
    deep = "[" * 40 + "]" * 40
    with pytest.raises(StrictJSONError, match="nesting"):
        loads_strict(deep, max_depth=8)


def test_rejects_long_string():
    with pytest.raises(StrictJSONError, match="string"):
        loads_strict('{"a": "%s"}' % ("x" * 500), max_string=100)


def test_rejects_long_key():
    with pytest.raises(StrictJSONError, match="key"):
        loads_strict('{"%s": 1}' % ("k" * 500), max_string=100)


def test_rejects_oversize_collection():
    arr = "[" + ",".join("1" for _ in range(50)) + "]"
    with pytest.raises(StrictJSONError, match="items"):
        loads_strict(arr, max_items=10)


def test_rejects_too_many_nodes():
    arr = "[" + ",".join('{"k": 1}' for _ in range(50)) + "]"
    with pytest.raises(StrictJSONError, match="nodes"):
        loads_strict(arr, max_nodes=20)


def test_malformed_json_wrapped():
    with pytest.raises(StrictJSONError, match="malformed"):
        loads_strict('{not json')


def test_bad_type_refused():
    with pytest.raises(StrictJSONError):
        loads_strict(12345)


def test_all_council_json_sites_use_strictjson():
    """Guard: no bare json.load(s) survives in the council/autonomy code
    (H2 item 8 uniformity)."""
    import os
    import re
    roots = [os.path.dirname(strictjson.__file__),
             os.path.join(os.path.dirname(os.path.dirname(
                 strictjson.__file__)), "autonomy")]
    bare = re.compile(r"\bjson\.loads?\b")
    offenders = []
    for base in roots:
        for name in os.listdir(base):
            if not name.endswith(".py") or name == "strictjson.py":
                continue
            path = os.path.join(base, name)
            with open(path, encoding="utf-8") as fh:
                for i, line in enumerate(fh, 1):
                    if bare.search(line) and "json.dumps" not in line:
                        offenders.append(f"{name}:{i}")
    assert offenders == [], f"bare json.load(s) sites remain: {offenders}"


# ------------------------------ atomic_write_json unique tmp (H2 race fix)

def test_atomic_write_uses_unique_tmp(tmp_path, monkeypatch):
    """Two concurrent writers to the same path must not collide on one
    fixed `.tmp` file (the pre-H2 race)."""
    from tools.council import storage
    target = str(tmp_path / "control.json")
    seen = []
    real_open = open

    def spy_open(path, *a, **k):
        if str(path).endswith(".tmp"):
            seen.append(str(path))
        return real_open(path, *a, **k)

    monkeypatch.setattr("builtins.open", spy_open)
    storage.atomic_write_json(target, {"a": 1})
    storage.atomic_write_json(target, {"a": 2})
    # each write used a DISTINCT tmp name (pid+uuid), never a shared one
    assert len(seen) == 2 and seen[0] != seen[1]
    import json as _json
    assert _json.load(real_open(target)) == {"a": 2}


def test_atomic_write_cleans_tmp_on_failure(tmp_path, monkeypatch):
    from tools.council import storage
    target = str(tmp_path / "sub" / "x.json")  # parent missing -> failure
    with pytest.raises(OSError):
        storage.atomic_write_json(target, {"a": 1})
    # no orphan .tmp left in tmp_path
    leftovers = [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []
