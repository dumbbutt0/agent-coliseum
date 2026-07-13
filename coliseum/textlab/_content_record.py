"""Shared content-addressed record foundation (training-readiness Phase 1, P1-S1).

The single hardened construction-freeze + content-addressed-registry standard that
every training-readiness record reuses — factored from the intervention.py identity
primitive (audits 000814/000820/000826/000832) so there is NOT a second, weaker
identity system. It is bound by the integrated design contract
docs/first-gladiator/TRAINING-READINESS-SUBSTRATE-PROFILE.md §3 + Appendix A (and
the amendment's Appendix A-1):

* **Content-addressed identity.** `id = config_hash(canonical_json({_domain:
  <literal>, **preimage}))` where the preimage is a strict JSON payload with
  **string-only object keys** and the record's own id field is **absent**
  (universal self-exclusion). `_domain` is reserved and may not appear in a
  caller preimage.
* **Canonical deterministic serialization.** Reuses `schema.canonical_json`
  (sorted keys, `allow_nan=False`) and `schema.config_hash` — no wall-clock, PID,
  object identity, or random material ever enters an id.
* **Construction-freeze.** A guarded `__setattr__`/`__delattr__` blocks ordinary
  assignment/deletion after `__init__`. `__slots__` alone is NOT immutability.
* **Registry truth is the protected invariant** (not held-object immutability).
  Per the 000826 lineage a caller holding a returned record MAY drift it via
  `object.__setattr__`; what is immutable is registry truth: the registry admits
  by content id, stores canonical strings, reconstructs a fresh record on `get()`,
  and refuses a duplicate id whose content differs (single-snapshot admission +
  reconstruct-on-get + drift-refusal).
"""
from __future__ import annotations

import json

from coliseum.textlab.schema import canonical_json, config_hash

# The reserved preimage key that carries the domain tag; a caller preimage that
# includes it (or would let it be overwritten) is rejected.
_DOMAIN_KEY = "_domain"


class ContentRecordError(ValueError):
    """A content record or registry operation violates the identity contract."""


def validate_json_payload(value, where: str = "payload") -> None:
    """Recursively require a strict JSON DATA-MODEL value: dict / list / str /
    finite-number / bool / None only, with **string-only object keys**.

    String-only keys close the non-injective-input hole (audit 000814): a
    non-string object key would be coerced by `json.dumps`, so `{1: "x"}` and
    `{"1": "x"}` would canonicalize identically. Tuples are rejected (they
    serialize like lists — another non-injective input)."""
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, str):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        # canonical_json uses allow_nan=False; reject non-finite explicitly too.
        if value != value or value in (float("inf"), float("-inf")):
            raise ContentRecordError(f"{where}: non-finite float is not allowed")
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise ContentRecordError(
                    f"{where}: object keys must be strings, got "
                    f"{type(k).__name__} {k!r}")
            validate_json_payload(v, f"{where}.{k}")
        return
    if isinstance(value, list):
        for i, v in enumerate(value):
            validate_json_payload(v, f"{where}[{i}]")
        return
    raise ContentRecordError(
        f"{where}: unsupported type {type(value).__name__} "
        "(only JSON dict/list/str/number/bool/null with string keys)")


def content_id(domain: str, preimage: dict, id_field: str) -> str:
    """The self-excluding content id: `config_hash({_domain: domain, **preimage})`.

    ``preimage`` must be a strict-JSON dict with string keys and must NOT contain
    either the reserved ``_domain`` key or the record's own declared output
    ``id_field`` — the foundation enforces **universal self-exclusion** here
    (profile §3), it is never delegated to the call site. Referenced ids with a
    *different* field name are legitimate and accepted. Two different domains
    never collide even on identical inner content."""
    if not isinstance(domain, str) or not domain:
        raise ContentRecordError("domain must be a non-empty string")
    if not isinstance(id_field, str) or not id_field:
        raise ContentRecordError("id_field must be a non-empty string")
    if not isinstance(preimage, dict):
        raise ContentRecordError("preimage must be a dict")
    if _DOMAIN_KEY in preimage:
        raise ContentRecordError(
            f"preimage must not contain the reserved key {_DOMAIN_KEY!r}")
    if id_field in preimage:
        raise ContentRecordError(
            f"preimage must not contain its own output id field {id_field!r} "
            "(universal self-exclusion)")
    validate_json_payload(preimage, "preimage")
    return config_hash({_DOMAIN_KEY: domain, **preimage})


class ContentRecord:
    """An immutable, content-addressed record.

    Subclasses set the class attribute ``DOMAIN`` to their literal Appendix-A
    ``_domain`` string and build their preimage (a strict-JSON dict WITHOUT their
    own id field) then call ``super().__init__(preimage)``. The record detaches +
    canonicalizes the preimage at construction, computes its self-excluded id, and
    seals itself. ``content`` returns a FRESH copy per access, so mutating the
    returned value never touches the record.
    """

    __slots__ = ("_domain_value", "_content_json", "_id", "_frozen")

    #: literal Appendix-A ``_domain`` string for this record kind.
    DOMAIN: str | None = None
    #: literal name of this record's OWN output id field (e.g.
    #: ``"behavior_policy_spec_id"``); a preimage containing it is rejected
    #: (universal self-exclusion, profile §3). Referenced ids with a different
    #: field name are accepted.
    ID_FIELD: str | None = None

    def __init__(self, preimage: dict):
        cls = type(self)
        domain = cls.DOMAIN
        id_field = cls.ID_FIELD
        if not isinstance(domain, str) or not domain:
            raise ContentRecordError(
                f"{cls.__name__}.DOMAIN must be a non-empty literal string")
        if not isinstance(id_field, str) or not id_field:
            raise ContentRecordError(
                f"{cls.__name__}.ID_FIELD must be a non-empty literal string")
        if not isinstance(preimage, dict):
            raise ContentRecordError("preimage must be a dict")
        # content_id enforces (inside the foundation, never delegated): strict
        # JSON with string-only keys, rejection of the reserved _domain key, and
        # universal self-exclusion of this record's own output id field.
        rid = content_id(domain, preimage, id_field)
        # now that the preimage is validated, detach + canonicalize for storage
        # (round-trip so no caller object is retained; key order is irrelevant).
        detached = json.loads(canonical_json(preimage))
        object.__setattr__(self, "_domain_value", domain)
        object.__setattr__(self, "_content_json", canonical_json(detached))
        object.__setattr__(self, "_id", rid)
        object.__setattr__(self, "_frozen", True)

    # ---- construction-freeze (ordinary assignment/deletion refused) ----
    def __setattr__(self, name, value):
        if getattr(self, "_frozen", False):
            raise ContentRecordError(
                f"{type(self).__name__} is immutable after construction; cannot "
                f"set {name!r} (identity is content-addressed and fixed at creation)")
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        raise ContentRecordError(
            f"{type(self).__name__} is immutable; cannot delete {name!r}")

    # ---- read-only accessors ----
    @property
    def id(self) -> str:
        return self._id

    @property
    def domain(self) -> str:
        return self._domain_value

    @property
    def content(self) -> dict:
        """A FRESH copy of the canonical preimage content on every access."""
        return json.loads(self._content_json)

    def canonical(self) -> str:
        """The canonical JSON of the full identity payload ({_domain} + content) —
        the exact bytes hashed to produce ``id``. Byte-identical for equal records."""
        return canonical_json({_DOMAIN_KEY: self._domain_value,
                               **json.loads(self._content_json)})

    def __repr__(self) -> str:
        return f"{type(self).__name__}(id={self._id[:12]}…)"


class _StoredRecord(ContentRecord):
    """A generic reconstructed record: the registry hands these back on ``get()``
    with a domain + content but no producing subclass. It is a real, immutable,
    content-addressed record with the same id as the original."""

    __slots__ = ()

    def __init__(self, domain: str, content: dict):
        # set DOMAIN per-instance via the base machinery: reuse the class path by
        # temporarily binding DOMAIN through a subclass is overkill; instead build
        # directly with the given domain.
        if not isinstance(domain, str) or not domain:
            raise ContentRecordError("domain must be a non-empty string")
        if not isinstance(content, dict):
            raise ContentRecordError("content must be a dict")
        if _DOMAIN_KEY in content:
            raise ContentRecordError(
                f"content must not contain the reserved key {_DOMAIN_KEY!r}")
        validate_json_payload(content, "content")
        detached = json.loads(canonical_json(content))
        object.__setattr__(self, "_domain_value", domain)
        object.__setattr__(self, "_content_json", canonical_json(detached))
        object.__setattr__(self, "_id", config_hash({_DOMAIN_KEY: domain, **detached}))
        object.__setattr__(self, "_frozen", True)


class ContentRegistry:
    """A content-addressed registry whose TRUTH is independent of any returned
    object's mutability.

    ``register`` normalizes the record from a single read into canonical strings,
    recomputes the id from that snapshot, and refuses (a) a record whose stored id
    does not match its content (tampered) and (b) a duplicate id whose content
    differs (registry disagreement / collision). ``get`` reconstructs a FRESH
    ``_StoredRecord`` from the stored canonical content, so mutating a previously
    returned record — even via ``object.__setattr__`` — cannot rewrite registry
    truth or be blessed on re-registration."""

    __slots__ = ("_by_id",)

    def __init__(self):
        object.__setattr__(self, "_by_id", {})

    def register(self, record: "ContentRecord") -> str:
        if not isinstance(record, ContentRecord):
            raise ContentRecordError("not a ContentRecord")
        # single-read normalization: capture domain + content ONCE.
        domain = record.domain
        content = record.content            # fresh copy, single read
        id_field = type(record).ID_FIELD
        if id_field:
            # re-enforce strict JSON + reserved-key + self-exclusion on the content.
            recomputed = content_id(domain, content, id_field)
        else:
            validate_json_payload(content, "content")
            if _DOMAIN_KEY in content:
                raise ContentRecordError(
                    f"content must not contain the reserved key {_DOMAIN_KEY!r}")
            recomputed = config_hash({_DOMAIN_KEY: domain, **content})
        if recomputed != record.id:
            raise ContentRecordError(
                "record id does not match its content (tampered or drifted)")
        content_json = canonical_json(content)
        prior = self._by_id.get(recomputed)
        if prior is not None and prior != (domain, content_json):
            raise ContentRecordError(
                f"duplicate id {recomputed[:12]} with different content "
                "— registry disagreement")
        self._by_id[recomputed] = (domain, content_json)
        return recomputed

    def get(self, record_id: str) -> "ContentRecord":
        rec = self._by_id.get(record_id)
        if rec is None:
            raise ContentRecordError(f"unknown record id {record_id!r}")
        domain, content_json = rec
        return _StoredRecord(domain, json.loads(content_json))

    def admitted_id(self, record_id: str) -> str:
        """The id captured at admission — registry truth, independent of any later
        mutation of a previously returned object (content-addressed: the id IS the
        truth)."""
        if record_id not in self._by_id:
            raise ContentRecordError(f"unknown record id {record_id!r}")
        return record_id

    def ids(self) -> list:
        return sorted(self._by_id)

    def __contains__(self, record_id) -> bool:
        return record_id in self._by_id

    def __len__(self) -> int:
        return len(self._by_id)
