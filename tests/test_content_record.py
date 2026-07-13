"""P1-S1 — shared content-record foundation.

Pins the identity contract the whole training-readiness substrate reuses:
construction-freeze, self-excluded content-addressed ids, string-only-key
preimages, and a registry whose TRUTH is independent of a returned object's
mutability (the 000826 lineage). Positive, negative, adversarial, mutation,
identity, and reconstruction cases.
"""
from __future__ import annotations

import json

import pytest

from coliseum.textlab._content_record import (
    ContentRecord, ContentRecordError, ContentRegistry, _StoredRecord,
    content_id, validate_json_payload)
from coliseum.textlab.schema import canonical_json, config_hash


class _Rec(ContentRecord):
    __slots__ = ()
    DOMAIN = "trs.test_record.v1"
    ID_FIELD = "test_record_id"


def _rec(content=None):
    return _Rec({"a": 1, "b": {"c": [1, 2]}} if content is None else content)


# --------------------------------------------------------------- id / self-exclusion
def test_id_is_self_excluding_config_hash():
    r = _rec({"x": 1})
    expected = config_hash({"_domain": "trs.test_record.v1", "x": 1})
    assert r.id == expected
    # the id field is never part of its own preimage
    assert "id" not in r.content and "_domain" not in r.content


def test_key_order_independent():
    assert _rec({"a": 1, "b": 2}).id == _rec({"b": 2, "a": 1}).id


def test_domain_separation():
    class _Other(ContentRecord):
        __slots__ = ()
        DOMAIN = "trs.other_record.v1"
        ID_FIELD = "other_record_id"
    assert _Rec({"x": 1}).id != _Other({"x": 1}).id


def test_preimage_may_not_contain_reserved_domain_key():
    with pytest.raises(ContentRecordError):
        _Rec({"_domain": "spoof", "x": 1})


def test_content_id_helper_rejects_domain_key_and_bad_domain():
    with pytest.raises(ContentRecordError):
        content_id("trs.x.v1", {"_domain": "spoof"}, "x_id")
    with pytest.raises(ContentRecordError):
        content_id("", {"x": 1}, "x_id")
    with pytest.raises(ContentRecordError):
        content_id("trs.x.v1", {"x": 1}, "")           # empty id_field


def test_self_exclusion_enforced_by_foundation():
    # audit 000874: the FOUNDATION (not the call site) must reject a preimage
    # containing the record's own declared output id field.
    class _Bps(ContentRecord):
        __slots__ = ()
        DOMAIN = "trs.behavior_policy_spec.v1"
        ID_FIELD = "behavior_policy_spec_id"
    with pytest.raises(ContentRecordError):
        _Bps({"behavior_policy_spec_id": "self-ref", "schema_version": "1"})
    with pytest.raises(ContentRecordError):
        content_id("trs.behavior_policy_spec.v1",
                   {"behavior_policy_spec_id": "self-ref"},
                   "behavior_policy_spec_id")
    # a REFERENCED id with a DIFFERENT field name is accepted (not self-inclusion)
    ok = _Bps({"schema_version": "1", "comparison_regime_id": "abc"})
    assert ok.id and "behavior_policy_spec_id" not in ok.content


# --------------------------------------------------------------- strict JSON preimage
@pytest.mark.parametrize("bad", [
    {1: "x"}, {"ok": {2: "y"}}, {"t": (1, 2)}, {"s": {"a"}},
    {"f": float("inf")},
])
def test_malformed_preimage_rejected(bad):
    with pytest.raises(ContentRecordError):
        _Rec(bad)


def test_missing_domain_on_subclass_fails_closed():
    class _NoDomain(ContentRecord):
        __slots__ = ()
    with pytest.raises(ContentRecordError):
        _NoDomain({"x": 1})


# --------------------------------------------------------------- construction-freeze
def test_ordinary_mutation_and_deletion_refused():
    r = _rec()
    for attr in ("_id", "_content_json", "_domain_value", "_frozen", "id"):
        with pytest.raises((ContentRecordError, AttributeError)):
            setattr(r, attr, "hijack")
    with pytest.raises(ContentRecordError):
        del r._id


def test_content_returns_fresh_copy():
    r = _rec()
    c = r.content
    c["a"] = 999
    c["b"]["c"].append(3)
    assert r.content == {"a": 1, "b": {"c": [1, 2]}}   # unchanged


# --------------------------------------------------------------- registry truth
def test_registry_register_get_reconstructs_fresh():
    reg = ContentRegistry()
    r = _rec()
    rid = reg.register(r)
    assert rid == r.id == reg.admitted_id(rid)
    got = reg.get(rid)
    assert got is not r
    assert isinstance(got, _StoredRecord)
    assert got.id == rid and got.content == r.content
    assert got.canonical() == r.canonical()
    assert reg.register(r) == rid          # idempotent
    assert reg.ids() == [rid] and len(reg) == 1


def test_object_setattr_bypass_cannot_rewrite_registry_truth():
    reg = ContentRegistry()
    r = _rec({"n": 1})
    rid = reg.register(r)
    got = reg.get(rid)
    # low-level TAMPER of a returned object: drift its content but not its id.
    object.__setattr__(got, "_content_json", json.dumps({"n": 2}))
    # registry truth untouched: admitted id + a fresh get stay at the admitted id
    assert reg.admitted_id(rid) == rid
    assert reg.get(rid).content == {"n": 1}
    # re-registering the tampered object is refused (id no longer matches content)
    with pytest.raises(ContentRecordError):
        reg.register(got)


def test_registry_refuses_tampered_id_mismatch():
    reg = ContentRegistry()
    r = _rec({"n": 1})
    object.__setattr__(r, "_id", "0" * 64)   # id no longer matches content
    with pytest.raises(ContentRecordError):
        reg.register(r)


def test_registry_refuses_duplicate_id_different_content():
    # force a collision: two records with the SAME stored id but different content
    reg = ContentRegistry()
    a = _rec({"n": 1})
    reg.register(a)
    b = _rec({"n": 2})
    object.__setattr__(b, "_id", a.id)       # pretend b has a's id (collision/tamper)
    with pytest.raises(ContentRecordError):
        reg.register(b)


def test_registry_unknown_id():
    with pytest.raises(ContentRecordError):
        ContentRegistry().get("nope")
    with pytest.raises(ContentRecordError):
        ContentRegistry().admitted_id("nope")


def test_register_non_record_rejected():
    with pytest.raises(ContentRecordError):
        ContentRegistry().register({"not": "a record"})


# --------------------------------------------------------------- reconstruction
def test_canonical_is_byte_identical_across_equal_records():
    assert _rec({"a": 1}).canonical() == _rec({"a": 1}).canonical()
    # and reconstruction from stored content reproduces it exactly
    reg = ContentRegistry()
    rid = reg.register(_rec({"a": 1, "z": [3, 2, 1]}))
    assert reg.get(rid).canonical() == _rec({"a": 1, "z": [3, 2, 1]}).canonical()


def test_validate_json_payload_direct():
    validate_json_payload({"a": [1, "x", True, None, 1.5]})   # ok
    with pytest.raises(ContentRecordError):
        validate_json_payload({1: "x"})
