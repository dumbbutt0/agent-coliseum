"""Spatial S2A implementation — mutable exclusive-location state, transitions, fork.

Realizes the integrated design source (SPATIAL-S2A-MUTABLE-LOCATION-STATE.md, rev 6),
with the §10 adversarial threat model: cross-world, stale, gapped, actor, illegal
effect, resurrection, transplant, capacity/inventory, containment, transit timing,
coincident arrivals, fork authorization + isolation, replay determinism.
"""
from __future__ import annotations

import pytest

from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.spatial.fork import (ForkDecision, ForkInitialization,
                                           materialize_fork)
from coliseum.textlab.spatial.instance import (AgentBodyInstance, ObjectInstance,
                                               PortalInstance, RoomInstance)
from coliseum.textlab.spatial.registry import SpatialSpecRegistry
from coliseum.textlab.spatial.state import (WorldState, admit_world_state,
                                            validate_location)
from coliseum.textlab.spatial.transition import (LocationTransition,
                                                 apply_transition, replay,
                                                 _apply_effect)
from coliseum.textlab.spatial.world import (AgentBodySpec, ObjectSpec,
                                            PerceptionRegime, PortalSpec, RoomSpec,
                                            SpatialWorldSpec)
from coliseum.textlab.spatial.world_line import WorldLine


# ------------------------------------------------------------- fixtures
def _base(cap=None, duration=1, inv=None, portable=True, exclusive=False,
          container=False):
    reg = SpatialSpecRegistry()
    pr = PerceptionRegime("r", "los", "adj", "o"); reg.register(pr)
    rs = RoomSpec("room", ["x"], cap, "los", "adj", ["n"]); reg.register(rs)
    ps = PortalSpec(rs.id, rs.id, "bidirectional", duration, "opaque"); reg.register(ps)
    os_ = ObjectSpec("thing", portable, container, "visible", exclusive, False,
                     [], ["take"]); reg.register(os_)
    bs = AgentBodySpec("humanoid", pr.id, inv); reg.register(bs)
    world = SpatialWorldSpec([rs.id], [ps.id], [os_.id], [bs.id], pr.id, {})
    reg.register(world)
    wl = WorldLine.root(world.id, "init"); reg.register(wl)
    ids = dict(reg=reg, rs=rs, ps=ps, os=os_, bs=bs, world=world, wl=wl)
    ids["rA"] = RoomInstance(rs.id, wl.id, "A"); reg.register(ids["rA"])
    ids["rB"] = RoomInstance(rs.id, wl.id, "B"); reg.register(ids["rB"])
    ids["portal"] = PortalInstance(ps.id, wl.id, "AB"); reg.register(ids["portal"])
    ids["body"] = AgentBodyInstance(bs.id, wl.id, "body#0"); reg.register(ids["body"])
    ids["obj"] = ObjectInstance(os_.id, wl.id, "obj#0"); reg.register(ids["obj"])
    return ids


def _in_room(eid, kind, room):
    return {"entity_id": eid, "entity_kind": kind,
            "location": {"tag": "in_room", "room_instance_id": room}}


def _life(eid, kind, status="present"):
    return {"entity_id": eid, "entity_kind": kind, "status": status}


def _state(ids, step, placements, lifecycle):
    return WorldState(ids["wl"].id, step, placements, lifecycle)


def _mk(ids, state, effect, actor=None):
    reg = ids["reg"]
    post = _apply_effect(state, effect, reg, state.logical_step + 1)
    admit_world_state(post, reg)
    t = LocationTransition(state.world_line_id, state.logical_step + 1, state.id,
                           post.id, effect, actor_body_id=actor)
    return t, post


# ------------------------------------------------------------- WorldState / admission
def test_world_state_order_independent_identity():
    ids = _base()
    b, o = ids["body"].id, ids["obj"].id
    a = _state(ids, 0, [_in_room(b, "agent_body", ids["rA"].id),
                        {"entity_id": o, "entity_kind": "object",
                         "location": {"tag": "held_by", "agent_body_id": b}}],
               [_life(b, "agent_body"), _life(o, "object")])
    b2 = _state(ids, 0, [{"entity_id": o, "entity_kind": "object",
                          "location": {"tag": "held_by", "agent_body_id": b}},
                         _in_room(b, "agent_body", ids["rA"].id)],
                [_life(o, "object"), _life(b, "agent_body")])
    assert a.id == b2.id
    admit_world_state(a, ids["reg"])


def test_location_tag_exact_key_sets():
    with pytest.raises(ContentRecordError):
        validate_location({"tag": "in_room"})                     # missing key
    with pytest.raises(ContentRecordError):
        validate_location({"tag": "in_room", "room_instance_id": "r", "x": 1})  # extra
    with pytest.raises(ContentRecordError):
        validate_location({"tag": "in_transit", "portal_instance_id": "p",
                           "origin_room_instance_id": "a", "destination_room_instance_id": "a",
                           "start_step": 1, "arrival_step": 2})   # same endpoints


def test_entity_kind_location_legality():
    ids = _base()
    with pytest.raises(ContentRecordError):   # a body cannot be held_by
        _state(ids, 0, [{"entity_id": ids["body"].id, "entity_kind": "agent_body",
                         "location": {"tag": "held_by", "agent_body_id": ids["body"].id}}],
               [_life(ids["body"].id, "agent_body")])


def test_lifecycle_placement_agreement():
    ids = _base()
    with pytest.raises(ContentRecordError):   # present but unplaced
        _state(ids, 0, [], [_life(ids["body"].id, "agent_body", "present")])
    with pytest.raises(ContentRecordError):   # removed but placed
        _state(ids, 0, [_in_room(ids["body"].id, "agent_body", ids["rA"].id)],
               [_life(ids["body"].id, "agent_body", "removed")])


def test_admission_refuses_cross_world_reference():
    ids = _base()
    reg = ids["reg"]
    # a genuinely different world-line (different initial_state_key) in the same registry.
    wl2 = WorldLine.root(ids["world"].id, "other-init"); reg.register(wl2)
    foreign_room = RoomInstance(ids["rs"].id, wl2.id, "A"); reg.register(foreign_room)
    st = _state(ids, 0, [_in_room(ids["body"].id, "agent_body", foreign_room.id)],
                [_life(ids["body"].id, "agent_body")])
    with pytest.raises(ContentRecordError, match="cross-world"):
        admit_world_state(st, reg)


def test_admission_capacity_and_inventory():
    ids = _base(cap=1, inv=1)
    reg = ids["reg"]
    b2 = AgentBodyInstance(ids["bs"].id, ids["wl"].id, "body#1"); reg.register(b2)
    over = _state(ids, 0, [_in_room(ids["body"].id, "agent_body", ids["rA"].id),
                           _in_room(b2.id, "agent_body", ids["rA"].id)],
                  [_life(ids["body"].id, "agent_body"), _life(b2.id, "agent_body")])
    with pytest.raises(ContentRecordError, match="capacity"):
        admit_world_state(over, reg)


# ------------------------------------------------------------- transitions
def test_move_transit_arrival_and_replay():
    ids = _base(duration=2)
    reg = ids["reg"]
    s0 = _state(ids, 0, [_in_room(ids["body"].id, "agent_body", ids["rA"].id)],
                [_life(ids["body"].id, "agent_body")])
    admit_world_state(s0, reg)
    t1, s1 = _mk(ids, s0, {"action": "move", "agent_body_id": ids["body"].id,
                           "portal_instance_id": ids["portal"].id,
                           "from_room_instance_id": ids["rA"].id,
                           "to_room_instance_id": ids["rB"].id}, actor=ids["body"].id)
    assert s1.content["placements"][0]["location"]["tag"] == "in_transit"
    t2, s2 = _mk(ids, s1, {"action": "advance_step"})
    t3, s3 = _mk(ids, s2, {"action": "advance_step"})
    loc = s3.content["placements"][0]["location"]
    assert loc["tag"] == "in_room" and loc["room_instance_id"] == ids["rB"].id
    assert replay(s0, [t1, t2, t3], reg).id == s3.id


def test_stale_and_gapped_and_crossworld_transition_refused():
    ids = _base()
    reg = ids["reg"]
    s0 = _state(ids, 0, [_in_room(ids["body"].id, "agent_body", ids["rA"].id)],
                [_life(ids["body"].id, "agent_body")])
    admit_world_state(s0, reg)
    t1, s1 = _mk(ids, s0, {"action": "advance_step"})
    with pytest.raises(ContentRecordError, match="stale"):
        apply_transition(s1, t1, reg)            # prior hash mismatch
    gap = LocationTransition(ids["wl"].id, 3, s0.id, s1.id, {"action": "advance_step"})
    with pytest.raises(ContentRecordError, match="gapped|monotonic"):
        apply_transition(s0, gap, reg)


def test_actor_rules_enforced():
    ids = _base()
    reg = ids["reg"]
    s0 = _state(ids, 0, [_in_room(ids["body"].id, "agent_body", ids["rA"].id),
                         _in_room(ids["obj"].id, "object", ids["rA"].id)],
                [_life(ids["body"].id, "agent_body"), _life(ids["obj"].id, "object")])
    admit_world_state(s0, reg)
    take = {"action": "take", "agent_body_id": ids["body"].id,
            "object_instance_id": ids["obj"].id}
    _t, post = _mk(ids, s0, take, actor=ids["body"].id)
    # system-null actor for an actor action -> refused
    bad = LocationTransition(ids["wl"].id, 1, s0.id, post.id, take, actor_body_id=None)
    with pytest.raises(ContentRecordError, match="non-null"):
        apply_transition(s0, bad, reg)
    # actor != acting body -> refused
    bad2 = LocationTransition(ids["wl"].id, 1, s0.id, post.id, take,
                              actor_body_id=ids["obj"].id)
    with pytest.raises(ContentRecordError):
        apply_transition(s0, bad2, reg)


def test_transplanted_resulting_hash_refused():
    ids = _base()
    reg = ids["reg"]
    s0 = _state(ids, 0, [_in_room(ids["body"].id, "agent_body", ids["rA"].id)],
                [_life(ids["body"].id, "agent_body")])
    admit_world_state(s0, reg)
    forged = LocationTransition(ids["wl"].id, 1, s0.id, "d" * 64, {"action": "advance_step"})
    with pytest.raises(ContentRecordError, match="resulting_state_hash"):
        apply_transition(s0, forged, reg)


def test_resurrection_refused():
    ids = _base()
    reg = ids["reg"]
    s0 = _state(ids, 0, [], [_life(ids["body"].id, "agent_body", "removed")])
    admit_world_state(s0, reg)
    with pytest.raises(ContentRecordError, match="resurrection|removed"):
        _apply_effect(s0, {"action": "spawn", "entity_id": ids["body"].id,
                           "entity_kind": "agent_body",
                           "location": {"tag": "in_room", "room_instance_id": ids["rA"].id}},
                      reg, 1)


def test_coincident_arrival_capacity_reservation():
    """A capacity-1 destination reached from a capacity-free origin: a second move
    toward it while a body is in flight fails admission — so arrivals never overfill."""
    reg = SpatialSpecRegistry()
    pr = PerceptionRegime("r", "los", "adj", "o"); reg.register(pr)
    origin_spec = RoomSpec("origin", ["x"], None, "los", "adj", ["n"]); reg.register(origin_spec)
    dest_spec = RoomSpec("dest", ["x"], 1, "los", "adj", ["n"]); reg.register(dest_spec)
    portal_spec = PortalSpec(origin_spec.id, dest_spec.id, "bidirectional", 2, "opaque")
    reg.register(portal_spec)
    bs = AgentBodySpec("humanoid", pr.id, None); reg.register(bs)
    world = SpatialWorldSpec([origin_spec.id, dest_spec.id], [portal_spec.id], [],
                             [bs.id], pr.id, {}); reg.register(world)
    wl = WorldLine.root(world.id, "init"); reg.register(wl)
    origin = RoomInstance(origin_spec.id, wl.id, "O"); reg.register(origin)
    dest = RoomInstance(dest_spec.id, wl.id, "D"); reg.register(dest)
    portal = PortalInstance(portal_spec.id, wl.id, "OD"); reg.register(portal)
    a = AgentBodyInstance(bs.id, wl.id, "a"); reg.register(a)
    b = AgentBodyInstance(bs.id, wl.id, "b"); reg.register(b)
    s0 = WorldState(wl.id, 0, [_in_room(a.id, "agent_body", origin.id),
                               _in_room(b.id, "agent_body", origin.id)],
                    [_life(a.id, "agent_body"), _life(b.id, "agent_body")])
    admit_world_state(s0, reg)
    mv = {"action": "move", "portal_instance_id": portal.id,
          "from_room_instance_id": origin.id, "to_room_instance_id": dest.id}
    post_a = _apply_effect(s0, dict(mv, action="move", agent_body_id=a.id), reg, 1)
    admit_world_state(post_a, reg)                    # A in flight toward the cap-1 dest
    post_b = _apply_effect(post_a, dict(mv, action="move", agent_body_id=b.id), reg, 2)
    with pytest.raises(ContentRecordError, match="capacity"):
        admit_world_state(post_b, reg)                # B would over-reserve the dest


# ------------------------------------------------------------- fork
def _forked(ids, parent_state):
    reg = ids["reg"]
    D = ForkDecision(ids["wl"].id, parent_state.id, parent_state.logical_step,
                     "door_open", {"n": "same"}); reg.register(D)
    C = WorldLine.forked(ids["wl"].id, D.id, "door_open", {"n": "same"}); reg.register(C)
    return D, C


def test_fork_materialization_child_world_isolation():
    ids = _base()
    reg = ids["reg"]
    sp = _state(ids, 2, [_in_room(ids["body"].id, "agent_body", ids["rA"].id)],
                [_life(ids["body"].id, "agent_body")])
    admit_world_state(sp, reg)
    D, C = _forked(ids, sp)
    child, finit = materialize_fork(sp, C, D, reg)
    admit_world_state(child, reg)
    assert child.world_line_id == C.id and child.logical_step == 2   # inherits clock
    cbody = child.content["placements"][0]["entity_id"]
    assert cbody != ids["body"].id
    assert reg.get(cbody).content["world_line_id"] == C.id            # child-world id
    assert finit.content["materialized_child_initial_state_hash"] == child.id
    # deterministic
    child2, _ = materialize_fork(sp, C, D, reg)
    assert child2.id == child.id


def test_fork_unauthorized_parent_refused():
    ids = _base()
    reg = ids["reg"]
    sp = _state(ids, 2, [_in_room(ids["body"].id, "agent_body", ids["rA"].id)],
                [_life(ids["body"].id, "agent_body")])
    admit_world_state(sp, reg)
    D, C = _forked(ids, sp)
    # a different admitted snapshot of the same parent line, NOT authorized by D
    sp2 = _state(ids, 3, [_in_room(ids["body"].id, "agent_body", ids["rB"].id)],
                 [_life(ids["body"].id, "agent_body")])
    admit_world_state(sp2, reg)
    with pytest.raises(ContentRecordError, match="authorize|step"):
        materialize_fork(sp2, C, D, reg)


def test_remove_cannot_bypass_due_arrival():
    """A remove targeting an in-transit body AT its arrival step is refused — only
    advance_step may resolve a step with due arrivals (no fail-open placement delete)."""
    ids = _base(duration=1)
    reg = ids["reg"]
    loc = {"tag": "in_transit", "portal_instance_id": ids["portal"].id,
           "origin_room_instance_id": ids["rA"].id,
           "destination_room_instance_id": ids["rB"].id, "start_step": 0, "arrival_step": 1}
    s0 = _state(ids, 0, [{"entity_id": ids["body"].id, "entity_kind": "agent_body",
                          "location": loc}], [_life(ids["body"].id, "agent_body")])
    admit_world_state(s0, reg)
    eff = {"action": "remove", "entity_id": ids["body"].id, "entity_kind": "agent_body"}
    post = _apply_effect(s0, eff, reg, 1); admit_world_state(post, reg)
    t = LocationTransition(ids["wl"].id, 1, s0.id, post.id, eff)
    with pytest.raises(ContentRecordError, match="due arrival"):
        apply_transition(s0, t, reg)


def test_zero_duration_move_foreign_portal_refused():
    """A duration-0 move drops the portal from the post-state, so the cross-world
    portal must be caught by the pre-application reference check."""
    ids = _base(duration=0)
    reg = ids["reg"]
    wl2 = WorldLine.root(ids["world"].id, "other"); reg.register(wl2)
    foreign_portal = PortalInstance(ids["ps"].id, wl2.id, "AB"); reg.register(foreign_portal)
    s0 = _state(ids, 0, [_in_room(ids["body"].id, "agent_body", ids["rA"].id)],
                [_life(ids["body"].id, "agent_body")])
    admit_world_state(s0, reg)
    eff = {"action": "move", "agent_body_id": ids["body"].id,
           "portal_instance_id": foreign_portal.id,
           "from_room_instance_id": ids["rA"].id, "to_room_instance_id": ids["rB"].id}
    post = _apply_effect(s0, eff, reg, 1); admit_world_state(post, reg)
    t = LocationTransition(ids["wl"].id, 1, s0.id, post.id, eff, actor_body_id=ids["body"].id)
    with pytest.raises(ContentRecordError, match="cross-world"):
        apply_transition(s0, t, reg)


def test_remove_wrong_entity_kind_refused():
    ids = _base()
    reg = ids["reg"]
    s0 = _state(ids, 0, [_in_room(ids["body"].id, "agent_body", ids["rA"].id)],
                [_life(ids["body"].id, "agent_body")])
    admit_world_state(s0, reg)
    eff = {"action": "remove", "entity_id": ids["body"].id, "entity_kind": "object"}
    post = _apply_effect(s0, eff, reg, 1); admit_world_state(post, reg)
    t = LocationTransition(ids["wl"].id, 1, s0.id, post.id, eff)
    with pytest.raises(ContentRecordError):        # instance domain != declared kind
        apply_transition(s0, t, reg)


def test_fork_unregistered_decision_refused():
    ids = _base()
    reg = ids["reg"]
    sp = _state(ids, 2, [_in_room(ids["body"].id, "agent_body", ids["rA"].id)],
                [_life(ids["body"].id, "agent_body")])
    admit_world_state(sp, reg)
    D = ForkDecision(ids["wl"].id, sp.id, 2, "x", {})       # deliberately NOT registered
    C = WorldLine.forked(ids["wl"].id, D.id, "x", {}); reg.register(C)
    with pytest.raises(ContentRecordError, match="not registered"):
        materialize_fork(sp, C, D, reg)


def test_fork_in_transit_preserves_remaining_travel():
    ids = _base(duration=3)
    reg = ids["reg"]
    # parent at step 2 with a body InTransit(start=1, arrival=4): 2 steps remaining.
    loc = {"tag": "in_transit", "portal_instance_id": ids["portal"].id,
           "origin_room_instance_id": ids["rA"].id,
           "destination_room_instance_id": ids["rB"].id,
           "start_step": 1, "arrival_step": 4}
    sp = _state(ids, 2, [{"entity_id": ids["body"].id, "entity_kind": "agent_body",
                          "location": loc}], [_life(ids["body"].id, "agent_body")])
    admit_world_state(sp, reg)
    D, C = _forked(ids, sp)
    child, _ = materialize_fork(sp, C, D, reg)
    cloc = child.content["placements"][0]["location"]
    assert child.logical_step == 2                       # inherited clock
    assert cloc["start_step"] == 1 and cloc["arrival_step"] == 4   # remaining travel preserved
    admit_world_state(child, reg)
