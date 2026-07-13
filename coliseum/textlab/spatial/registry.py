"""Spatial spec registry (profile §3-§4) — S0.

Wraps the hardened :class:`ContentRegistry` (collision / tamper / registry-truth) and
adds two spatial rules, both fail-closed:

* **version dispatch** — a record whose ``spatial_schema_version`` is not supported is
  refused (unknown versions never execute; mirrors the run-schema dispatcher);
* **acyclic construction order** — a spec may reference only ids that are ALREADY
  registered AND of the expected spec type. A portal that names a non-existent (or
  wrongly-typed) room, or a world spec that names an unregistered member, is refused —
  so no id can reference a not-yet-built or mistyped id.
"""
from __future__ import annotations

from coliseum.textlab._content_record import (ContentRecord, ContentRecordError,
                                              ContentRegistry, _StoredRecord,
                                              content_id)
from coliseum.textlab.spatial.world import is_supported_version

# scalar reference fields: content key -> the domain the referenced id must have.
_SCALAR_REFERENCES = {
    "spatial.portal_spec.v1": (
        ("origin_room_spec_id", "spatial.room_spec.v1"),
        ("destination_room_spec_id", "spatial.room_spec.v1"),
    ),
    "spatial.agent_body_spec.v1": (
        ("default_perception_regime_id", "spatial.perception_regime.v1"),
    ),
    "spatial.world_spec.v1": (
        ("perception_regime_id", "spatial.perception_regime.v1"),
    ),
}
# list reference fields: content key -> the domain every referenced id must have.
_LIST_REFERENCES = {
    "spatial.world_spec.v1": (
        ("room_spec_ids", "spatial.room_spec.v1"),
        ("portal_spec_ids", "spatial.portal_spec.v1"),
        ("object_spec_ids", "spatial.object_spec.v1"),
        ("agent_body_spec_ids", "spatial.agent_body_spec.v1"),
    ),
}


class SpatialSpecRegistry:
    """Collision-refusing, version- and construction-order-enforcing registry for the
    spatial spec layer."""

    __slots__ = ("_base",)

    def __init__(self):
        object.__setattr__(self, "_base", ContentRegistry())

    def _domain_of(self, record_id: str) -> str:
        try:
            return self._base.get(record_id).domain
        except ContentRecordError:
            raise ContentRecordError(
                f"references unregistered id {record_id!r} (construction order: a "
                "referenced spec must be registered first)")

    def _check_reference(self, referenced_id: str, expected_domain: str,
                         field: str) -> None:
        actual = self._domain_of(referenced_id)
        if actual != expected_domain:
            raise ContentRecordError(
                f"{field} references a {actual!r}, expected {expected_domain!r} "
                "(wrong spec type)")

    def register(self, record: "ContentRecord") -> str:
        if not isinstance(record, ContentRecord):
            raise ContentRecordError("not a ContentRecord")
        # SINGLE detached snapshot: capture domain + content exactly ONCE. Every check
        # below AND the final admission operate on this immutable snapshot, never on a
        # re-read of the caller-controlled record — closing the check/admit TOCTOU (a
        # record whose content accessor switches between reads cannot pass validation
        # with one snapshot and be admitted with another).
        domain = record.domain
        content = record.content
        id_field = type(record).ID_FIELD
        # re-derive the id from the snapshot; refuse a record whose claimed id does not
        # match its content (tampered/drifted). Storage uses the snapshot, not record.id.
        derived_id = content_id(domain, content, id_field) if id_field else None
        if derived_id is not None and record.id != derived_id:
            raise ContentRecordError(
                "record id does not match its content (tampered or drifted)")
        version = content.get("spatial_schema_version")
        if not is_supported_version(version):
            raise ContentRecordError(
                f"unsupported spatial_schema_version {version!r} — refused (unknown "
                "versions fail closed)")
        for field, expected in _SCALAR_REFERENCES.get(domain, ()):  # construction order
            self._check_reference(content[field], expected, field)
        for field, expected in _LIST_REFERENCES.get(domain, ()):
            for rid in content[field]:
                self._check_reference(rid, expected, field)
        # admit the EXACT validated snapshot as an immutable record — the base registry
        # reads only this detached snapshot, not the original polymorphic record.
        return self._base.register(_StoredRecord(domain, content))

    def get(self, record_id: str) -> "ContentRecord":
        return self._base.get(record_id)

    def admitted_id(self, record_id: str) -> str:
        return self._base.admitted_id(record_id)

    def ids(self) -> list:
        return self._base.ids()

    def __contains__(self, record_id) -> bool:
        return record_id in self._base

    def __len__(self) -> int:
        return len(self._base)
