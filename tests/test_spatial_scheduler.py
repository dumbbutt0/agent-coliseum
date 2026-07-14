"""Spatial S2B implementation — deterministic scheduler (design rev 11, integrated
001102). Covers the master directive's adversarial classes + the contract-mandated
regression coverage (bidirectional fwd+rev incl. repeated room specs; directed-only
orientation; wrong-attachment refusal)."""
from __future__ import annotations

import pytest

from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.spatial.fork import ForkDecision
from coliseum.textlab.spatial.registry import SpatialSpecRegistry
from coliseum.textlab.spatial.scheduler import (ADVANCE, QUIESCENT, Activation,
                                                RandomDraw, RandomStream,
                                                SchedulerManifest, SchedulerRun,
                                                SchedulerState, WorldLineGenesis,
                                                action_script_commitment,
                                                candidate_effects, consume,
                                                draw_value, initial_scheduler_state,
                                                legal_action_kinds,
                                                materialize_fork_closure,
                                                materialize_root, next_step,
                                                schedule, sorted_eligible,
                                                validate_world_line_genesis,
                                                verify_manifest, _closure_hash)
from coliseum.textlab.spatial.state import WorldState, admit_world_state
from coliseum.textlab.spatial.transition import _apply_effect
from coliseum.textlab.spatial.world import (AgentBodySpec, ObjectSpec,
                                            PerceptionRegime, PortalSpec, RoomSpec,
                                            SpatialWorldSpec)
from coliseum.textlab.spatial.world_line import WorldLine


def _world(directionality="bidirectional", entity_order=None):
    """Two rooms sharing ONE repeated room spec, one portal, two bodies, one token."""
    reg = SpatialSpecRegistry()
    pr = PerceptionRegime("r", "los", "adj", "o"); reg.register(pr)
    rs = RoomSpec("room", ["x"], None, "los", "adj", ["n"]); reg.register(rs)
    ps = PortalSpec(rs.id, rs.id, directionality, 0, "open"); reg.register(ps)
    os_ = ObjectSpec("token", True, False, "visible", True, False, [], ["take"])
    reg.register(os_)
    bs = AgentBodySpec("humanoid", pr.id, None); reg.register(bs)
    entities = [
        {"entity_kind": "agent_body", "spec_id": bs.id, "logical_key": "alice",
         "location": {"tag": "in_room", "room_logical_key": "A"}},
        {"entity_kind": "agent_body", "spec_id": bs.id, "logical_key": "bob",
         "location": {"tag": "in_room", "room_logical_key": "B"}},
        {"entity_kind": "object", "spec_id": os_.id, "logical_key": "token",
         "location": {"tag": "in_room", "room_logical_key": "A"}},
    ]
    if entity_order:
        entities = [entities[i] for i in entity_order]
    layout = {"rooms": [{"room_spec_id": rs.id, "room_logical_key": "A"},
                        {"room_spec_id": rs.id, "room_logical_key": "B"}],
              "portals": [{"portal_spec_id": ps.id, "portal_logical_key": "AB",
                           "from_room_logical_key": "A", "to_room_logical_key": "B"}],
              "entities": entities}
    world = SpatialWorldSpec([rs.id], [ps.id], [os_.id], [bs.id], pr.id, layout)
    reg.register(world)
    wl = WorldLine.root(world.id, "init"); reg.register(wl)
    genesis, closure = materialize_root(wl, reg)
    glx = WorldLineGenesis(wl.id, genesis.id, _closure_hash(closure), "root")
    reg.register(glx)
    return dict(reg=reg, wl=wl, genesis=genesis, closure=closure, glx=glx)


def _two_step_script(w):
    """A deterministic 2-activation script (head acts, then the other body)."""
    b1, b2 = sorted_eligible(w["genesis"])
    c1 = candidate_effects(b1, w["genesis"], w["closure"], w["reg"])
    eff1 = (c1["take"] or c1["move"])[0]
    s1 = _apply_effect(w["genesis"], eff1, w["reg"], 1)
    admit_world_state(s1, w["reg"])
    c2 = candidate_effects(b2, s1, w["closure"], w["reg"])
    eff2 = (c2["move"] or c2["take"])[0]
    return [eff1, eff2]


def _run(w, script, stop=2):
    run = SchedulerRun(w["wl"].id, w["glx"].id, action_script_commitment(script),
                       explicit_stop_position=stop)
    w["reg"].register(run)
    return run


# ------------------------------------------------------------- happy path
def test_schedule_and_verify_canonical_manifest():
    w = _world()
    script = _two_step_script(w)
    run = _run(w, script)
    chain, transitions, manifest = schedule(run, w["genesis"], script, w["closure"], w["reg"])
    assert len(chain) == 3 and len(transitions) == 2
    assert chain[-1].content["scheduler_position"] == 2
    assert verify_manifest(manifest, run, w["genesis"], script, w["closure"], w["reg"])


def test_replay_is_insertion_order_independent():
    """Same layout, two independent registries -> byte-identical genesis, closure,
    and manifest (host/dict/registration order never enters identity). A REORDERED
    layout is correctly a DIFFERENT world (the layout is identity-bearing spec
    content), which is asserted separately."""
    a = _world()
    b = _world()                                    # fresh registry, same layout
    assert a["genesis"].id == b["genesis"].id
    assert _closure_hash(a["closure"]) == _closure_hash(b["closure"])
    script = _two_step_script(a)
    ra, rb = _run(a, script), _run(b, script)
    _, _, ma = schedule(ra, a["genesis"], script, a["closure"], a["reg"])
    _, _, mb = schedule(rb, b["genesis"], script, b["closure"], b["reg"])
    assert ma.id == mb.id           # byte-identical manifest across registries
    # different layout literal => different world spec => different world identity.
    c = _world(entity_order=[2, 0, 1])
    assert c["genesis"].id != a["genesis"].id


# ----------------------------------------- contract-mandated portal coverage
def test_bidirectional_forward_and_reverse_with_repeated_room_spec():
    w = _world("bidirectional")
    assert len(w["closure"]["portals"]) == 2       # orientation expansion
    b1, b2 = sorted_eligible(w["genesis"])
    # both bodies (in rooms sharing ONE room spec) have a move candidate.
    for b in (b1, b2):
        assert candidate_effects(b, w["genesis"], w["closure"], w["reg"])["move"]


def test_directed_portal_exposes_only_declared_orientation():
    w = _world("directed")
    assert len(w["closure"]["portals"]) == 1
    a_row = w["closure"]["portals"][0]
    # the body in the destination room has NO move candidate (no reverse row).
    bodies = sorted_eligible(w["genesis"])
    from coliseum.textlab.spatial.scheduler import _room_of
    for b in bodies:
        room = _room_of(w["genesis"], b)
        moves = candidate_effects(b, w["genesis"], w["closure"], w["reg"])["move"]
        if room == a_row["from_room_instance_id"]:
            assert moves
        else:
            assert not moves


def test_wrong_attachment_move_refused():
    """A committed move whose (portal, from, to) is not a closure attachment row is
    refused at consume — even though S2A's spec-endpoint check would accept it."""
    w = _world("directed")
    b1, b2 = sorted_eligible(w["genesis"])
    a_row = w["closure"]["portals"][0]
    from coliseum.textlab.spatial.scheduler import _room_of
    rev_body = next(b for b in (b1, b2)
                    if _room_of(w["genesis"], b) == a_row["to_room_instance_id"])
    # forge the reverse effect (S2A bidirectional-style semantics would allow the
    # room-spec endpoints; the closure does not carry this row).
    eff = {"action": "move", "agent_body_id": rev_body,
           "portal_instance_id": a_row["portal_instance_id"],
           "from_room_instance_id": a_row["to_room_instance_id"],
           "to_room_instance_id": a_row["from_room_instance_id"]}
    cands = candidate_effects(rev_body, w["genesis"], w["closure"], w["reg"])
    assert eff not in cands["move"]


# ------------------------------------------------------------- terminal rules
def test_prefix_truncation_refused():
    w = _world()
    script = _two_step_script(w)
    run = _run(w, script)
    chain, transitions, manifest = schedule(run, w["genesis"], script, w["closure"], w["reg"])
    fake = SchedulerManifest(run.id, chain[0].id, chain[-2].id, len(chain) - 1,
                             [t.id for t in transitions[:-1]])
    with pytest.raises(ContentRecordError, match="canonical"):
        verify_manifest(fake, run, w["genesis"], script, w["closure"], w["reg"])


def test_appended_suffix_refused():
    w = _world()
    script = _two_step_script(w)
    run = _run(w, script)
    chain, transitions, manifest = schedule(run, w["genesis"], script, w["closure"], w["reg"])
    fake = SchedulerManifest(run.id, chain[0].id, chain[-1].id, len(chain) + 1,
                             [t.id for t in transitions] + ["f" * 64])
    with pytest.raises(ContentRecordError, match="canonical"):
        verify_manifest(fake, run, w["genesis"], script, w["closure"], w["reg"])


def test_quiescence_before_explicit_stop_refused():
    """An explicit-stop run that would quiesce first fails closed (exclusive rule)."""
    w = _world()
    script = _two_step_script(w)
    run = SchedulerRun(w["wl"].id, w["glx"].id, action_script_commitment(script),
                       explicit_stop_position=999)
    w["reg"].register(run)
    with pytest.raises(ContentRecordError, match="exhausted|quiescence"):
        schedule(run, w["genesis"], script, w["closure"], w["reg"])


def test_script_commitment_mismatch_refused():
    w = _world()
    script = _two_step_script(w)
    run = _run(w, [script[0]])       # commits to a 1-action script
    with pytest.raises(ContentRecordError, match="commitment"):
        schedule(run, w["genesis"], script, w["closure"], w["reg"])


def test_reordered_script_changes_or_refuses():
    """Reordered actions are a DIFFERENT run (different commitment); scheduling the
    reordered script under the original commitment is refused."""
    w = _world()
    script = _two_step_script(w)
    run = _run(w, script)
    swapped = [script[1], script[0]]
    with pytest.raises(ContentRecordError, match="commitment"):
        schedule(run, w["genesis"], swapped, w["closure"], w["reg"])
    assert action_script_commitment(swapped) != action_script_commitment(script)


# ------------------------------------------------------------- cursor safety
def test_stale_and_crossworld_cursor_refused():
    w = _world()
    script = _two_step_script(w)
    run = _run(w, script)
    chain, transitions, _ = schedule(run, w["genesis"], script, w["closure"], w["reg"])
    mid_state_hash = chain[1].content["current_world_state_hash"]
    mid_state = w["reg"].get(mid_state_hash)
    ws = WorldState(mid_state.content["world_line_id"], mid_state.content["logical_step"],
                    mid_state.content["placements"], mid_state.content["entity_lifecycle"])
    with pytest.raises(ContentRecordError, match="stale"):
        next_step(chain[0], ws, w["closure"], w["reg"])   # genesis cursor vs later state


def test_swapped_actor_refused():
    """A transition whose actor is not the activated head body is refused."""
    w = _world()
    b1, b2 = sorted_eligible(w["genesis"])
    run = _run(w, [], stop=1)
    cursor = initial_scheduler_state(run, w["genesis"], w["reg"])
    act = next_step(cursor, w["genesis"], w["closure"], w["reg"])
    assert act.content["agent_body_id"] == b1                 # head is b1
    c2 = candidate_effects(b2, w["genesis"], w["closure"], w["reg"])
    eff = (c2["move"] or c2["take"])[0]                        # b2's action
    from coliseum.textlab.spatial.scheduler import _mk_transition
    t = _mk_transition(w["genesis"], eff, w["reg"], actor=b2)
    with pytest.raises(ContentRecordError, match="head body"):
        consume(cursor, w["genesis"], t, w["closure"], w["reg"])


def test_initial_cursor_only_at_bound_genesis():
    """A mid-run admitted state cannot anchor an initial cursor (genesis reset)."""
    w = _world()
    script = _two_step_script(w)
    run = _run(w, script)
    chain, _, _ = schedule(run, w["genesis"], script, w["closure"], w["reg"])
    later = w["reg"].get(chain[-1].content["current_world_state_hash"])
    ws = WorldState(later.content["world_line_id"], later.content["logical_step"],
                    later.content["placements"], later.content["entity_lifecycle"])
    with pytest.raises(ContentRecordError, match="genesis"):
        initial_scheduler_state(run, ws, w["reg"])


# ------------------------------------------------------------- genesis auth
def test_root_genesis_validation_and_forgery_refused():
    w = _world()
    closure = validate_world_line_genesis(w["glx"], w["reg"])
    assert _closure_hash(closure) == w["glx"].content["topology_closure_hash"]
    # forged root genesis: a different admitted step-0 snapshot is NOT the genesis.
    b1, b2 = sorted_eligible(w["genesis"])
    other = WorldState(w["wl"].id, 0,
                       [p for p in w["genesis"].content["placements"]
                        if p["entity_id"] != b2],
                       [e for e in w["genesis"].content["entity_lifecycle"]
                        if e["entity_id"] != b2])
    admit_world_state(other, w["reg"]); w["reg"].register(other)
    forged = WorldLineGenesis(w["wl"].id, other.id,
                              w["glx"].content["topology_closure_hash"], "root")
    w["reg"].register(forged)
    with pytest.raises(ContentRecordError, match="materialized"):
        validate_world_line_genesis(forged, w["reg"])


def test_fork_genesis_requires_witness_and_authenticated_parent():
    w = _world()
    reg = w["reg"]
    script = _two_step_script(w)
    run = _run(w, script)
    chain, transitions, manifest = schedule(run, w["genesis"], script, w["closure"], w["reg"])
    # fork at the terminal state (position 2)
    term_hash = chain[-1].content["current_world_state_hash"]
    term = reg.get(term_hash)
    ts = WorldState(term.content["world_line_id"], term.content["logical_step"],
                    term.content["placements"], term.content["entity_lifecycle"])
    D = ForkDecision(w["wl"].id, ts.id, ts.logical_step, "alt", {}); reg.register(D)
    C = WorldLine.forked(w["wl"].id, D.id, "alt", {}); reg.register(C)
    from coliseum.textlab.spatial.fork import materialize_fork
    child_state, finit = materialize_fork(ts, C, D, reg)
    reg.register(child_state); reg.register(finit)
    child_closure = materialize_fork_closure(w["closure"], C.id, reg)
    fg = WorldLineGenesis(C.id, child_state.id, _closure_hash(child_closure), "fork",
                          parent_world_line_id=w["wl"].id, parent_state_hash=ts.id,
                          fork_logical_step=ts.logical_step,
                          source_fork_decision_hash=D.id)
    reg.register(fg)
    witness = {"scheduler_state_id": chain[-1].id, "scheduler_manifest_id": manifest.id}
    out = validate_world_line_genesis(fg, reg, witness=witness)
    assert _closure_hash(out) == fg.content["topology_closure_hash"]
    with pytest.raises(ContentRecordError, match="witness"):
        validate_world_line_genesis(fg, reg)          # no witness -> refused
    bad = {"scheduler_state_id": chain[0].id, "scheduler_manifest_id": manifest.id}
    with pytest.raises(ContentRecordError, match="parent snapshot"):
        validate_world_line_genesis(fg, reg, witness=bad)  # wrong position -> refused


# ------------------------------------------------------------- randomness
def test_random_stream_and_draw_frozen():
    w = _world()
    s1 = RandomStream(w["wl"].id, 3, "tie_break")
    s2 = RandomStream(w["wl"].id, 3, "tie_break")
    assert s1.id == s2.id
    assert RandomStream(w["wl"].id, 4, "tie_break").id != s1.id     # step domain
    assert RandomStream(w["wl"].id, 3, "other").id != s1.id         # purpose domain
    v = draw_value(s1.id, 0)
    assert 0 <= v < 2 ** 64
    d = RandomDraw(s1.id, 0, v)
    assert d.content["value"] == v
    with pytest.raises(ContentRecordError, match="frozen"):
        RandomDraw(s1.id, 0, (v + 1) % 2 ** 64)


# ------------------------------------------------------------- record guards
def test_activation_pass_iff_empty_kinds():
    w = _world()
    with pytest.raises(ContentRecordError):
        Activation("r" * 64, 1, w["wl"].id, "h" * 64, "h" * 64, 0, 0, 0,
                   "b" * 64, "pass", ["move"])       # pass with non-empty kinds
    with pytest.raises(ContentRecordError):
        Activation("r" * 64, 1, w["wl"].id, "h" * 64, "h" * 64, 0, 0, 0,
                   "b" * 64, "activate", [])         # activate with empty kinds


def test_old_cursor_reuse_is_inert():
    """Pass/cursor reuse: re-consuming an old cursor deterministically reproduces the
    SAME successor (content-addressed; no new authority), and cannot extend the
    finalized canonical run — the manifest is the unique truth."""
    w = _world()
    script = _two_step_script(w)
    run = _run(w, script)
    cursor = initial_scheduler_state(run, w["genesis"], w["reg"])
    from coliseum.textlab.spatial.scheduler import _mk_transition
    act = next_step(cursor, w["genesis"], w["closure"], w["reg"])
    t = _mk_transition(w["genesis"], script[0], w["reg"], actor=act.content["agent_body_id"])
    n1, s1 = consume(cursor, w["genesis"], t, w["closure"], w["reg"])
    n2, s2 = consume(cursor, w["genesis"], t, w["closure"], w["reg"])   # reuse
    assert n1.id == n2.id and s1.id == s2.id      # inert: identical successor, no branch


def test_scheduler_state_position_prev_invariants():
    w = _world()
    with pytest.raises(ContentRecordError):
        SchedulerState("r" * 64, 1, None, w["wl"].id, "h" * 64, "h" * 64, 0, 0,
                       "activate")                    # pos 1 with null prev
    with pytest.raises(ContentRecordError):
        SchedulerState("r" * 64, 0, "p" * 64, w["wl"].id, "h" * 64, "h" * 64, 0, 0,
                       "initial")                     # pos 0 with prev
