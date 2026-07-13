"""Spatial spec-identity layer (S0) — content-addressed specs + collision/version/
construction-order registry (SPATIAL-WORLD-MODEL profile Appendix A).

Inert identity only: no world state, no instances, no simulation.
"""
from __future__ import annotations

import pytest

from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.spatial.registry import SpatialSpecRegistry
from coliseum.textlab.spatial.world import (SPATIAL_SCHEMA_VERSION, AgentBodySpec,
                                            ObjectSpec, PerceptionRegime, PortalSpec,
                                            RoomSpec, SpatialWorldSpec,
                                            is_supported_version)


def _regime():
    return PerceptionRegime("renderer-1", "line_of_sight", "adjacent", "obs-1")


def _room(name="hall", tags=("public",)):
    return RoomSpec(name, list(tags), 4, "line_of_sight", "adjacent", ["north"])


# ------------------------------------------------------------- identity
def test_spec_ids_are_domain_separated_and_self_excluded():
    pr = _regime()
    c = pr.content
    assert "perception_regime_id" not in c              # self-exclusion
    assert c["spatial_schema_version"] == SPATIAL_SCHEMA_VERSION
    assert pr.domain == "spatial.perception_regime.v1"
    # a different domain with the same-shaped content yields a different id.
    room = _room()
    assert room.id != pr.id


def test_identical_content_same_id():
    assert _regime().id == _regime().id
    assert _room().id == _room().id


def test_list_preimages_are_order_and_duplicate_independent():
    a = ObjectSpec("key", True, False, "visible", True, True,
                   ["held_by", "location"], ["take", "give"])
    b = ObjectSpec("key", True, False, "visible", True, True,
                   ["location", "held_by", "held_by"], ["give", "take"])
    assert a.id == b.id


def test_changing_a_field_changes_the_id():
    base = _room()
    other = RoomSpec("hall", ["private"], 4, "line_of_sight", "adjacent", ["north"])
    assert other.id != base.id


def test_construction_freeze_blocks_mutation():
    pr = _regime()
    with pytest.raises((ContentRecordError, AttributeError)):
        pr.renderer_version = "x"  # type: ignore[attr-defined]


# ------------------------------------------------------------- validation
def test_rejects_empty_and_wrong_typed_fields():
    with pytest.raises(ContentRecordError):
        PerceptionRegime("", "v", "a", "o")
    with pytest.raises(ContentRecordError):
        RoomSpec("hall", ["public"], -1, "v", "a")          # negative capacity
    with pytest.raises(ContentRecordError):
        PortalSpec("r1", "r2", "sideways", 1, "p")          # bad directionality
    with pytest.raises(ContentRecordError):
        ObjectSpec("key", "yes", False, "v", True, True)    # portability not bool


def test_capacity_and_inventory_limit_optional_null():
    assert RoomSpec("hall", ["public"], None, "v", "a").content["capacity"] is None
    assert AgentBodySpec("humanoid", "pid", None).content["inventory_limit"] is None


# ------------------------------------------------------------- registry
def _full_world(reg):
    pr = _regime(); reg.register(pr)
    r1 = _room("hall"); r2 = _room("vault", ("private",))
    reg.register(r1); reg.register(r2)
    portal = PortalSpec(r1.id, r2.id, "bidirectional", 1, "opaque_when_closed",
                        ["openable"])
    reg.register(portal)
    obj = ObjectSpec("key", True, False, "visible", True, True, ["held_by"],
                     ["take", "give"])
    reg.register(obj)
    body = AgentBodySpec("humanoid", pr.id, 2); reg.register(body)
    world = SpatialWorldSpec([r1.id, r2.id], [portal.id], [obj.id], [body.id],
                             pr.id, {"start_room": r1.id})
    reg.register(world)
    return pr, r1, r2, portal, obj, body, world


def test_registry_registers_a_full_world_spec():
    reg = SpatialSpecRegistry()
    pr, r1, r2, portal, obj, body, world = _full_world(reg)
    assert len(reg) == 7
    assert world.id in reg
    assert reg.get(world.id).content["perception_regime_id"] == pr.id


def test_registry_register_is_idempotent_for_identical_content():
    reg = SpatialSpecRegistry()
    pr = _regime()
    a = reg.register(pr)
    b = reg.register(_regime())
    assert a == b and len(reg) == 1


def test_registry_refuses_reference_to_unregistered_id():
    reg = SpatialSpecRegistry()
    r1 = _room("hall"); r2 = _room("vault", ("private",))
    reg.register(r1)  # r2 intentionally NOT registered
    with pytest.raises(ContentRecordError, match="unregistered"):
        reg.register(PortalSpec(r1.id, r2.id, "directed", 1, "p"))


def test_registry_refuses_wrong_typed_reference():
    reg = SpatialSpecRegistry()
    pr = _regime(); reg.register(pr)
    obj = ObjectSpec("key", True, False, "visible", True, True); reg.register(obj)
    # a portal whose 'origin room' is actually an object spec is refused.
    with pytest.raises(ContentRecordError, match="wrong spec type|expected"):
        reg.register(PortalSpec(obj.id, obj.id, "directed", 1, "p"))


def test_registry_refuses_world_spec_with_unregistered_member():
    reg = SpatialSpecRegistry()
    pr = _regime(); reg.register(pr)
    r1 = _room("hall"); reg.register(r1)
    ghost = _room("ghost", ("private",))  # not registered
    with pytest.raises(ContentRecordError, match="unregistered"):
        reg.register(SpatialWorldSpec([r1.id, ghost.id], [], [], [], pr.id, {}))


# ------------------------------------------------------------- version dispatch
def test_version_dispatch_fail_closed():
    assert is_supported_version(SPATIAL_SCHEMA_VERSION)
    assert not is_supported_version("9.9")


# ---------------------------------------------- single-snapshot atomicity (TOCTOU)
from coliseum.textlab._content_record import ContentRecord, content_id  # noqa: E402


class _SwitchingRecord(ContentRecord):
    """An adversarial record whose content accessor returns a clean snapshot on the
    first read and a dirty (unknown-version / unregistered-ref) snapshot afterwards —
    the check/admit TOCTOU probe."""

    # deliberately NO __slots__ so the read counter can live in __dict__.
    DOMAIN = "spatial.portal_spec.v1"
    ID_FIELD = "portal_spec_id"

    def __init__(self, clean, dirty, dirty_first=False):
        object.__setattr__(self, "_n", 0)
        object.__setattr__(self, "_clean", clean)
        object.__setattr__(self, "_dirty", dirty)
        object.__setattr__(self, "_dirty_first", dirty_first)

    @property
    def content(self):
        object.__setattr__(self, "_n", self._n + 1)
        first, second = ((self._dirty, self._clean) if self._dirty_first
                         else (self._clean, self._dirty))
        return dict(first if self._n == 1 else second)

    @property
    def domain(self):
        return self.DOMAIN

    @property
    def id(self):
        snap = self._dirty if self._dirty_first else self._clean
        return content_id(self.DOMAIN, snap, self.ID_FIELD)


def _clean_dirty_portals():
    reg = SpatialSpecRegistry()
    r1 = _room("hall"); r2 = _room("vault", ("private",))
    reg.register(r1); reg.register(r2)
    clean = dict(PortalSpec(r1.id, r2.id, "bidirectional", 1, "opaque",
                            ["openable"]).content)
    dirty = dict(clean)
    dirty["spatial_schema_version"] = "9.9"           # unknown version
    dirty["origin_room_spec_id"] = "unregistered-origin"  # unregistered ref
    return reg, r1, clean, dirty


def test_switching_content_admits_only_validated_snapshot():
    """A record that presents a clean snapshot to validation must not smuggle a dirty
    snapshot into registry truth: the validated snapshot is what gets admitted."""
    reg, r1, clean, dirty = _clean_dirty_portals()
    rid = reg.register(_SwitchingRecord(clean, dirty))
    stored = reg.get(rid).content
    assert stored["spatial_schema_version"] == SPATIAL_SCHEMA_VERSION
    assert stored["origin_room_spec_id"] == r1.id
    # the dirty snapshot's unknown version never entered registry truth.
    assert all(reg.get(i).content.get("spatial_schema_version") == SPATIAL_SCHEMA_VERSION
               for i in reg.ids())


def test_switching_content_dirty_first_refused_registry_unchanged():
    reg, r1, clean, dirty = _clean_dirty_portals()
    before = set(reg.ids())
    with pytest.raises(ContentRecordError):
        reg.register(_SwitchingRecord(clean, dirty, dirty_first=True))
    assert set(reg.ids()) == before   # refusal left registry truth untouched
