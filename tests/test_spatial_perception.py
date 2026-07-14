"""Spatial S2C implementation — perception rendering + non-interference (design
rev 3, integrated 001154). Covers the 18-vector threat model + the 7 invariants,
including the mandatory exact-id regressions (vectors 8, 11, 16, 17, 18)."""
from __future__ import annotations

import pytest

from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.spatial.perception import (RENDERER_VERSION,
                                                 assert_actor_content_schema,
                                                 closure_visible_state_commitment,
                                                 render_observation_pair)
from coliseum.textlab.spatial.registry import SpatialSpecRegistry
from coliseum.textlab.spatial.scheduler import (WorldLineGenesis, _closure_hash,
                                                action_script_commitment,
                                                materialize_root, schedule,
                                                sorted_eligible, candidate_effects,
                                                SchedulerRun)
from coliseum.textlab.spatial.state import WorldState, admit_world_state
from coliseum.textlab.spatial.transition import _apply_effect
from coliseum.textlab.spatial.world import (AgentBodySpec, ObjectSpec,
                                            PerceptionRegime, PortalSpec, RoomSpec,
                                            SpatialWorldSpec)
from coliseum.textlab.spatial.world_line import WorldLine
from coliseum.textlab.spatial.instance import AgentBodyInstance, ObjectInstance


V0_REGIME = dict(renderer_version="0.1", visibility_policy="room_v0",
                 audibility_policy="off_v0", observation_policy_version="1")


def _world(directionality="bidirectional", regime_overrides=None,
           extra_object_specs=(), extra_entities=(), suffix="x"):
    """Two rooms (one shared spec), one portal, alice(A)/bob(B), a visible token(A),
    a container box(A) with a gem INSIDE, and a hidden shadow(A)."""
    reg = SpatialSpecRegistry()
    rp = dict(V0_REGIME)
    rp.update(regime_overrides or {})
    pr = PerceptionRegime(rp["renderer_version"], rp["visibility_policy"],
                          rp["audibility_policy"], rp["observation_policy_version"])
    reg.register(pr)
    rs = RoomSpec("room", [suffix], None, "los", "adj", ["n"]); reg.register(rs)
    ps = PortalSpec(rs.id, rs.id, directionality, 0, "open"); reg.register(ps)
    token = ObjectSpec("token", True, False, "visible", True, False, [], ["take"])
    box = ObjectSpec("box", False, True, "visible", False, False, [], [])
    gem = ObjectSpec("gem", True, False, "visible", True, False, [], ["take"])
    shadow = ObjectSpec("shadow", False, False, "hidden", False, False, [], [])
    specs = [token, box, gem, shadow, *extra_object_specs]
    for s in specs:
        reg.register(s)
    bs = AgentBodySpec("humanoid", pr.id, None); reg.register(bs)
    entities = [
        {"entity_kind": "agent_body", "spec_id": bs.id, "logical_key": "alice",
         "location": {"tag": "in_room", "room_logical_key": "A"}},
        {"entity_kind": "agent_body", "spec_id": bs.id, "logical_key": "bob",
         "location": {"tag": "in_room", "room_logical_key": "B"}},
        {"entity_kind": "object", "spec_id": token.id, "logical_key": "token",
         "location": {"tag": "in_room", "room_logical_key": "A"}},
        {"entity_kind": "object", "spec_id": box.id, "logical_key": "box",
         "location": {"tag": "in_room", "room_logical_key": "A"}},
        {"entity_kind": "object", "spec_id": gem.id, "logical_key": "gem",
         "location": {"tag": "inside", "container_logical_key": "box"}},
        {"entity_kind": "object", "spec_id": shadow.id, "logical_key": "shadow",
         "location": {"tag": "in_room", "room_logical_key": "A"}},
        *extra_entities,
    ]
    layout = {"rooms": [{"room_spec_id": rs.id, "room_logical_key": "A"},
                        {"room_spec_id": rs.id, "room_logical_key": "B"}],
              "portals": [{"portal_spec_id": ps.id, "portal_logical_key": "AB",
                           "from_room_logical_key": "A", "to_room_logical_key": "B"}],
              "entities": entities}
    world = SpatialWorldSpec([rs.id], [ps.id], [s.id for s in specs], [bs.id],
                             pr.id, layout)
    reg.register(world)
    wl = WorldLine.root(world.id, "init"); reg.register(wl)
    genesis, closure = materialize_root(wl, reg)
    glx = WorldLineGenesis(wl.id, genesis.id, _closure_hash(closure), "root")
    reg.register(glx)
    ids = {}
    for stored_id in closure["bodies"] + closure["objects"]:
        key = reg.get(stored_id).content["deterministic_logical_instance_key"]
        ids[key] = stored_id
    ids["room_A"] = next(  # alice's room
        p["location"]["room_instance_id"]
        for p in genesis.content["placements"] if p["entity_id"] == ids["alice"])
    return dict(reg=reg, wl=wl, genesis=genesis, closure=closure, glx=glx,
                regime=pr, ids=ids)


def _render(w, body_key="alice", state=None):
    return render_observation_pair(state or w["genesis"], w["ids"][body_key],
                                   w["closure"], w["reg"])


def _variant_state(w, mutate):
    """Register + admit a variant of genesis with mutated placements/lifecycle."""
    g = w["genesis"].content
    placements = [dict(p, location=dict(p["location"])) for p in g["placements"]]
    lifecycle = [dict(e) for e in g["entity_lifecycle"]]
    mutate(placements, lifecycle)
    s = WorldState(w["wl"].id, 0, placements, lifecycle)
    admit_world_state(s, w["reg"]); w["reg"].register(s)
    return s


# ------------------------------------------------------------------- happy path
def test_render_happy_path_pinned_visibility():
    w = _world()
    actor, priv = _render(w)
    ids = w["ids"]
    c = actor.content["content"]
    assert c["visible_room_identity"] == ids["room_A"]
    assert c["perception_regime"] == w["regime"].id
    vis = set(c["visible_entity_identities"])
    # sees itself, the visible token, the box — NOT the gem (inside), NOT the
    # hidden shadow, NOT bob (other room).
    assert vis == {ids["alice"], ids["token"], ids["box"]}
    # exactly the departing portal row (bidirectional -> one row leaves room A).
    assert len(c["observable_state_projection"]["portals"]) == 1
    assert c["observable_state_projection"]["portals"][0]["to_room_instance_id"] != ids["room_A"]
    # privileged sees the full closure-present universe.
    pv = priv.content["content"]
    assert set(pv["visible_entity_identities"]) == {
        ids["alice"], ids["bob"], ids["token"], ids["box"], ids["gem"], ids["shadow"]}
    assert actor.domain == "trs.observation.actor.v1"
    assert priv.domain == "trs.observation.privileged.v1"
    assert actor.id != priv.id                       # vector 14: never alias


def test_cross_registry_byte_identical_replay():
    a, b = _world(), _world()
    (aa, ap), (ba, bp) = _render(a), _render(b)
    assert aa.id == ba.id and ap.id == bp.id         # invariant 7


def test_held_object_visible_via_visible_holder():
    w = _world()
    s = _variant_state(w, lambda pl, lf: next(
        p for p in pl if p["entity_id"] == w["ids"]["token"])["location"].update(
        {"tag": "held_by", "agent_body_id": w["ids"]["alice"]}) or
        next(p for p in pl if p["entity_id"] == w["ids"]["token"])["location"].pop(
        "room_instance_id"))
    actor, _ = _render(w, state=s)
    row = next(r for r in actor.content["content"]["observable_state_projection"]["entities"]
               if r["entity_id"] == w["ids"]["token"])
    assert row["location"] == {"tag": "held_by", "agent_body_id": w["ids"]["alice"]}


# ------------------------------------------------ non-interference (invariants 2/3/6)
def test_hidden_container_and_other_room_non_interference():
    """States differing ONLY in non-visible content (hidden object moved; gem taken
    out of the box into the OTHER room; bob relocated within B-side context) render
    byte-identical ACTOR ids for alice — while the privileged ids differ."""
    w = _world()
    room_b = next(r for r in w["closure"]["rooms"] if r != w["ids"]["room_A"])
    def mutate(pl, lf):
        next(p for p in pl if p["entity_id"] == w["ids"]["shadow"])["location"] = \
            {"tag": "in_room", "room_instance_id": room_b}
        next(p for p in pl if p["entity_id"] == w["ids"]["gem"])["location"] = \
            {"tag": "in_room", "room_instance_id": room_b}
    s2 = _variant_state(w, mutate)
    (a1, p1) = _render(w)
    (a2, p2) = _render(w, state=s2)
    assert a1.id == a2.id                            # invariants 2 + 6
    assert p1.id != p2.id                            # invariant 3: privileged differs


def test_out_of_closure_ghost_exact_ids_both_views():
    """Vector 8 mandatory regression: an admitted same-world state differing only by
    OUT-OF-CLOSURE instances yields EXACTLY the closure-only actor AND privileged ids."""
    w = _world()
    reg, ids = w["reg"], w["ids"]
    bs_id = reg.get(ids["alice"]).content["agent_body_spec_id"]
    os_id = reg.get(ids["token"]).content["object_spec_id"]
    ghost_b = AgentBodyInstance(bs_id, w["wl"].id, "ghost_b"); reg.register(ghost_b)
    ghost_o = ObjectInstance(os_id, w["wl"].id, "ghost_o"); reg.register(ghost_o)
    def mutate(pl, lf):
        pl.append({"entity_id": ghost_b.id, "entity_kind": "agent_body",
                   "location": {"tag": "in_room", "room_instance_id": ids["room_A"]}})
        pl.append({"entity_id": ghost_o.id, "entity_kind": "object",
                   "location": {"tag": "in_room", "room_instance_id": ids["room_A"]}})
        lf.append({"entity_id": ghost_b.id, "entity_kind": "agent_body", "status": "present"})
        lf.append({"entity_id": ghost_o.id, "entity_kind": "object", "status": "present"})
    ghost_state = _variant_state(w, mutate)
    (a1, p1) = _render(w)
    (a2, p2) = _render(w, state=ghost_state)
    assert a2.id == a1.id                            # exact actor id (invariant 5)
    assert p2.id == p1.id                            # exact privileged id (invariant 5)
    # the privileged commitment is the closure-projected id == the CLEAN state id,
    # never the ghost-bearing registered id.
    commit = p2.content["content"]["observable_state_projection"][
        "closure_visible_state_commitment"]
    assert commit == w["genesis"].id != ghost_state.id
    assert closure_visible_state_commitment(ghost_state, w["closure"]) == w["genesis"].id


# ----------------------------------------------------------------------- refusals
def test_out_of_closure_observer_refused():
    w = _world()
    bs_id = w["reg"].get(w["ids"]["alice"]).content["agent_body_spec_id"]
    ghost = AgentBodyInstance(bs_id, w["wl"].id, "ghost"); w["reg"].register(ghost)
    with pytest.raises(ContentRecordError, match="closure"):
        render_observation_pair(w["genesis"], ghost.id, w["closure"], w["reg"])


def test_cross_world_observer_refused():
    """Two root worlds in ONE registry: an observer that IS a member of the supplied
    closure but belongs to a different world-line than the state is refused."""
    reg = SpatialSpecRegistry()
    def build(suffix):
        pr = PerceptionRegime(V0_REGIME["renderer_version"],
                              V0_REGIME["visibility_policy"],
                              V0_REGIME["audibility_policy"],
                              V0_REGIME["observation_policy_version"])
        reg.register(pr)
        rs = RoomSpec("room", [suffix], None, "los", "adj", ["n"]); reg.register(rs)
        ps = PortalSpec(rs.id, rs.id, "bidirectional", 0, "open"); reg.register(ps)
        bs = AgentBodySpec("humanoid", pr.id, None); reg.register(bs)
        layout = {"rooms": [{"room_spec_id": rs.id, "room_logical_key": "A"},
                            {"room_spec_id": rs.id, "room_logical_key": "B"}],
                  "portals": [{"portal_spec_id": ps.id, "portal_logical_key": "AB",
                               "from_room_logical_key": "A", "to_room_logical_key": "B"}],
                  "entities": [{"entity_kind": "agent_body", "spec_id": bs.id,
                                "logical_key": "alice",
                                "location": {"tag": "in_room", "room_logical_key": "A"}}]}
        world = SpatialWorldSpec([rs.id], [ps.id], [], [bs.id], pr.id, layout)
        reg.register(world)
        wl = WorldLine.root(world.id, "init-" + suffix); reg.register(wl)
        genesis, closure = materialize_root(wl, reg)
        body = closure["bodies"][0]
        return genesis, closure, body
    g1, c1, b1 = build("x")
    g2, c2, b2 = build("y")
    # observer of world 1 IS in closure 1, but the state is world 2's -> cross-world.
    with pytest.raises(ContentRecordError, match="cross-world"):
        render_observation_pair(g2, b1, c1, reg)


def test_absent_observer_refused():
    w = _world()
    def mutate(pl, lf):
        pl[:] = [p for p in pl if p["entity_id"] != w["ids"]["bob"]]
        next(e for e in lf if e["entity_id"] == w["ids"]["bob"])["status"] = "absent"
    s = _variant_state(w, mutate)
    with pytest.raises(ContentRecordError, match="present"):
        _render(w, body_key="bob", state=s)


def test_unregistered_state_refused():
    w = _world()
    g = w["genesis"].content
    s = WorldState(w["wl"].id, 3,
                   [dict(p, location=dict(p["location"])) for p in g["placements"]],
                   [dict(e) for e in g["entity_lifecycle"]])
    # NOT registered
    with pytest.raises(ContentRecordError):
        _render(w, state=s)


def test_registered_non_admitted_state_refused():
    """Vector 16: registration does not persist admission — a structurally valid but
    registry-INVALID state (an object held by another OBJECT) must be refused at
    render time by the mandatory admit_world_state revalidation."""
    w = _world()
    g = w["genesis"].content
    placements = [dict(p, location=dict(p["location"])) for p in g["placements"]]
    next(p for p in placements if p["entity_id"] == w["ids"]["gem"])["location"] = \
        {"tag": "held_by", "agent_body_id": w["ids"]["token"]}   # object as holder
    s = WorldState(w["wl"].id, 0, placements, [dict(e) for e in g["entity_lifecycle"]])
    w["reg"].register(s)                     # register() does NOT run S2A admission
    with pytest.raises(ContentRecordError):
        _render(w, state=s)


@pytest.mark.parametrize("field,bad", [
    ("renderer_version", "9.9"),
    ("visibility_policy", "xray_v1"),
    ("audibility_policy", "omniscient"),
    ("observation_policy_version", "0"),
])
def test_regime_field_mutations_refused(field, bad):
    """Vector 11: EVERY regime field is dispatched independently — a regime that is
    v0-like except ONE non-conforming field is refused, never approximated."""
    w = _world(regime_overrides={field: bad})
    with pytest.raises(ContentRecordError, match="unsupported perception regime"):
        _render(w)


def test_unknown_visibility_behavior_refused():
    ghost_spec = ObjectSpec("orb", True, False, "translucent", True, False, [], [])
    w = _world(extra_object_specs=(ghost_spec,),
               extra_entities=({"entity_kind": "object", "spec_id": ghost_spec.id,
                                "logical_key": "orb",
                                "location": {"tag": "in_room", "room_logical_key": "A"}},))
    with pytest.raises(ContentRecordError, match="visibility_behavior"):
        _render(w)


# ------------------------------------------------------------------ render purity
def test_render_purity_registers_nothing_and_replay_unchanged():
    """Invariant 1: rendering registers nothing; a run scheduled after rendering is
    byte-identical to a run scheduled with no rendering at all."""
    clean = _world()
    rendered = _world()
    before = set(rendered["reg"].ids())
    _render(rendered)                                   # render BEFORE scheduling
    _render(rendered, body_key="bob")
    assert set(rendered["reg"].ids()) == before          # nothing registered
    def run(w):
        b1, b2 = sorted_eligible(w["genesis"], w["closure"])
        c1 = candidate_effects(b1, w["genesis"], w["closure"], w["reg"])
        eff1 = (c1["take"] or c1["move"])[0]
        s1 = _apply_effect(w["genesis"], eff1, w["reg"], 1)
        admit_world_state(s1, w["reg"])
        c2 = candidate_effects(b2, s1, w["closure"], w["reg"])
        eff2 = (c2["move"] or c2["take"])[0]
        script = [eff1, eff2]
        r = SchedulerRun(w["wl"].id, w["glx"].id, action_script_commitment(script),
                         explicit_stop_position=2)
        w["reg"].register(r)
        _, _, manifest = schedule(r, w["genesis"], script, w["closure"], w["reg"])
        return manifest
    m_clean = run(clean)
    m_rendered = run(rendered)
    _render(rendered)                                   # render AFTER as well
    assert m_clean.id == m_rendered.id                   # byte-identical manifest


# ----------------------------------------------------------- policy: portals/transit
def test_directed_portal_visibility_orientation():
    """Vector 17: a directed portal is visible ONLY from its origin room."""
    w = _world("directed")
    a_actor, _ = _render(w, body_key="alice")
    b_actor, _ = _render(w, body_key="bob")
    assert len(a_actor.content["content"]["observable_state_projection"]["portals"]) == 1
    assert b_actor.content["content"]["observable_state_projection"]["portals"] == []


def test_in_transit_observer_sees_only_self_and_inventory():
    """Vector 15: in-transit observer -> room null, portals [], self + inventory only."""
    w = _world()
    a_row = w["closure"]["portals"][0]
    def mutate(pl, lf):
        alice = next(p for p in pl if p["entity_id"] == w["ids"]["alice"])
        alice["location"] = {"tag": "in_transit",
                             "portal_instance_id": a_row["portal_instance_id"],
                             "origin_room_instance_id": a_row["from_room_instance_id"],
                             "destination_room_instance_id": a_row["to_room_instance_id"],
                             "start_step": 0, "arrival_step": 1}
        token = next(p for p in pl if p["entity_id"] == w["ids"]["token"])
        token["location"] = {"tag": "held_by", "agent_body_id": w["ids"]["alice"]}
    s = _variant_state(w, mutate)
    actor, _ = _render(w, state=s)
    c = actor.content["content"]
    assert c["visible_room_identity"] is None
    assert c["observable_state_projection"]["portals"] == []
    assert set(c["visible_entity_identities"]) == {w["ids"]["alice"], w["ids"]["token"]}
    own = next(r for r in c["observable_state_projection"]["entities"]
               if r["entity_id"] == w["ids"]["alice"])
    assert own["location"]["tag"] == "in_transit"        # own placement verbatim


# ------------------------------------------------------- closed schema (vector 6/4)
def test_actor_schema_closed_exact_multi_depth():
    """Invariant 4 / vector 6: ANY unknown key at ANY depth is refused — including
    hash-carrier names under any spelling; the pinned valid content passes."""
    w = _world()
    actor, _ = _render(w)
    valid = actor.content["content"]
    assert_actor_content_schema(valid)                  # pinned valid artifact passes
    import copy
    for mutate in (
        lambda c: c.update({"world_state_hash": "h" * 64}),               # top level
        lambda c: c["observable_state_projection"].update({"digest": "h" * 64}),
        lambda c: c["observable_state_projection"]["entities"][0].update(
            {"state_commitment": "h" * 64}),                              # entity row
        lambda c: c["observable_state_projection"]["portals"][0].update(
            {"manifest_hash": "h" * 64}),                                 # portal row
        lambda c: c["observable_state_projection"]["entities"][0]["location"].update(
            {"cursor_hash": "h" * 64}),                                   # location
    ):
        bad = copy.deepcopy(valid)
        mutate(bad)
        with pytest.raises(ContentRecordError):
            assert_actor_content_schema(bad)


def test_privileged_inner_schema_exact():
    """Vector 18: the privileged projection has EXACTLY the three-key inner schema and
    the closure-projected commitment equals the registered id for canonical states."""
    w = _world()
    _, priv = _render(w)
    proj = priv.content["content"]["observable_state_projection"]
    assert set(proj) == {"authoritative_placements", "authoritative_lifecycle",
                         "closure_visible_state_commitment"}
    assert proj["closure_visible_state_commitment"] == w["genesis"].id
    # the actor factory refuses the privileged carrier names outright (backstop).
    from coliseum.textlab.training.observation import observation_artifact
    with pytest.raises(ContentRecordError, match="privileged"):
        observation_artifact("actor", {"authoritative_placements": []})


def test_renderer_version_frozen():
    assert RENDERER_VERSION == "0.1"
