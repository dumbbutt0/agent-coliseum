"""Spatial world-line + instance identity (S1) — root/forked lineage, per-world
instances, and cross-world fail-closed isolation (profile §4/§4.1, Appendix A)."""
from __future__ import annotations

import pytest

from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.spatial.instance import (AgentBodyInstance, ObjectInstance,
                                               PortalInstance, RoomInstance,
                                               assert_same_world_line)
from coliseum.textlab.spatial.registry import SpatialSpecRegistry
from coliseum.textlab.spatial.world import (AgentBodySpec, ObjectSpec,
                                            PerceptionRegime, PortalSpec, RoomSpec,
                                            SpatialWorldSpec)
from coliseum.textlab.spatial.world_line import WorldLine


def _world(reg):
    pr = PerceptionRegime("r", "los", "adj", "o"); reg.register(pr)
    r1 = RoomSpec("hall", ["public"], 4, "los", "adj", ["n"]); reg.register(r1)
    world = SpatialWorldSpec([r1.id], [], [], [], pr.id, {"start": r1.id})
    reg.register(world)
    return pr, r1, world


# --------------------------------------------------------- world-line identity
def test_root_world_line_identity_and_determinism():
    a = WorldLine.root("wspec", "init-0")
    b = WorldLine.root("wspec", "init-0")
    assert a.id == b.id and a.is_root
    assert "world_line_id" not in a.content            # self-exclusion
    assert a.domain == "spatial.world_line.v1"


def test_forked_world_line_differs_from_root_and_parent():
    root = WorldLine.root("wspec", "init-0")
    child = WorldLine.forked(root.id, "f" * 16, "door_open", {"agent": "same"})
    assert not child.is_root
    assert child.id != root.id
    # a different changed_dimension is a different fork.
    other = WorldLine.forked(root.id, "f" * 16, "door_closed", {"agent": "same"})
    assert other.id != child.id


def test_world_line_rejects_mixed_or_partial_key_sets():
    with pytest.raises(ContentRecordError):
        WorldLine({"spatial_schema_version": "0.1", "spatial_world_spec_id": "w"})  # missing initial_state_key
    with pytest.raises(ContentRecordError):
        WorldLine.forked("p", "d", "c", ["not", "a", "dict"])  # type: ignore[arg-type]


# ------------------------------------------------------------- instances
def test_instance_identity_and_self_exclusion():
    ri = RoomInstance("room_spec", "wl", "room#0")
    assert "room_instance_id" not in ri.content
    assert ri.content["room_spec_id"] == "room_spec"
    assert ri.world_line_id == "wl"
    assert RoomInstance("room_spec", "wl", "room#0").id == ri.id


def test_sibling_world_lines_give_distinct_instance_ids():
    a = RoomInstance("room_spec", "wl-a", "room#0")
    b = RoomInstance("room_spec", "wl-b", "room#0")
    assert a.id != b.id                                # every instance id differs per world


def test_logical_key_changes_the_instance_id():
    a = RoomInstance("room_spec", "wl", "room#0")
    b = RoomInstance("room_spec", "wl", "room#1")
    assert a.id != b.id


def test_instance_rejects_empty_fields():
    for bad in (("", "wl", "k"), ("spec", "", "k"), ("spec", "wl", "")):
        with pytest.raises(ContentRecordError):
            RoomInstance(*bad)


# ------------------------------------------------- cross-world fail closed
def test_assert_same_world_line_passes_and_refuses():
    a = RoomInstance("s", "wl-a", "room#0")
    b = ObjectInstance("s", "wl-a", "obj#0")
    assert_same_world_line("wl-a", a, b)               # same world: OK
    foreign = AgentBodyInstance("s", "wl-b", "body#0")
    with pytest.raises(ContentRecordError, match="cross-world"):
        assert_same_world_line("wl-a", a, foreign)


def test_assert_same_world_line_type_checked():
    with pytest.raises(ContentRecordError):
        assert_same_world_line("wl", "not an instance")  # type: ignore[arg-type]


# ------------------------------------------------------------- registry
def test_registry_registers_world_line_and_instances():
    reg = SpatialSpecRegistry()
    pr, r1, world = _world(reg)
    wl = WorldLine.root(world.id, "init-0"); reg.register(wl)
    child = WorldLine.forked(wl.id, "f" * 16, "door_open", {}); reg.register(child)
    ri = RoomInstance(r1.id, wl.id, "room#0"); reg.register(ri)
    assert ri.id in reg and wl.id in reg and child.id in reg


def test_root_world_line_refuses_unregistered_world_spec():
    reg = SpatialSpecRegistry()
    with pytest.raises(ContentRecordError, match="unregistered"):
        reg.register(WorldLine.root("ghost-world-spec", "init-0"))


def test_forked_world_line_refuses_unregistered_parent():
    reg = SpatialSpecRegistry()
    with pytest.raises(ContentRecordError, match="unregistered"):
        reg.register(WorldLine.forked("ghost-parent", "f" * 16, "d", {}))


def test_instance_refuses_unregistered_world_line():
    reg = SpatialSpecRegistry()
    pr, r1, world = _world(reg)
    # a real-but-unregistered world-line id
    wl = WorldLine.root(world.id, "init-0")
    with pytest.raises(ContentRecordError, match="unregistered"):
        reg.register(RoomInstance(r1.id, wl.id, "room#0"))


def _registered_world(reg):
    """Register the full spec set + a root world-line; return the spec ids + world."""
    pr = PerceptionRegime("r", "los", "adj", "o"); reg.register(pr)
    room = RoomSpec("hall", ["public"], 4, "los", "adj", ["n"]); reg.register(room)
    portal = PortalSpec(room.id, room.id, "bidirectional", 1, "p"); reg.register(portal)
    obj = ObjectSpec("key", True, False, "visible", True, True); reg.register(obj)
    body = AgentBodySpec("humanoid", pr.id, 2); reg.register(body)
    world = SpatialWorldSpec([room.id], [portal.id], [obj.id], [body.id], pr.id, {})
    reg.register(world)
    wl = WorldLine.root(world.id, "init-0"); reg.register(wl)
    return pr, room, portal, obj, body, wl


# every instance kind must admit a valid record AND fail closed on a wrong-typed spec
# reference — parametrised so no single kind (e.g. agent_body) is left uncovered.
@pytest.mark.parametrize("kind,cls,spec_attr,key", [
    ("room", RoomInstance, "room", "room#0"),
    ("portal", PortalInstance, "portal", "portal#0"),
    ("object", ObjectInstance, "obj", "obj#0"),
    ("agent_body", AgentBodyInstance, "body", "body#0"),
])
def test_every_instance_kind_registers_and_type_checks(kind, cls, spec_attr, key):
    reg = SpatialSpecRegistry()
    pr, room, portal, obj, body, wl = _registered_world(reg)
    specs = {"room": room, "portal": portal, "obj": obj, "body": body}
    correct_spec = specs[spec_attr]
    # (1) a valid instance of this kind is admitted.
    inst = cls(correct_spec.id, wl.id, key)
    assert reg.register(inst) == inst.id and inst.id in reg
    # (2) the same kind with a wrong-typed spec reference (perception regime) is refused.
    with pytest.raises(ContentRecordError, match="wrong spec type|expected"):
        reg.register(cls(pr.id, wl.id, key + "!"))
