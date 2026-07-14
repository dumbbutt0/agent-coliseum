"""Spatial S2D — production scenario builders (master runnable-experiments
directive, step 4).

The builders auto-derive and verify EVERY content-addressed identity — spec ids,
instances, world line, genesis, topology closure, the committed action script, and
the SchedulerRun — so a user (or the CLI) never hand-builds a hash. The concrete
action script is derived by simulating the integrated S2B dispatch over symbolic
per-agent INTENTS: each intent selects its exact candidate from the
closure-and-attachment-bounded candidate set, so a scenario cannot commit an
illegal action. Simulation registers only records the canonical `schedule()` run
would register anyway (registration is idempotent for identical content).

Scenarios are minimal and closed (NO generic scenario DSL): a name maps to a
builder function.
"""
from __future__ import annotations

from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.spatial.scheduler import (ADVANCE, QUIESCENT, RandomStream,
                                                SchedulerRun, WorldLineGenesis,
                                                _closure_hash, _mk_transition,
                                                action_script_commitment,
                                                candidate_effects, consume,
                                                initial_scheduler_state,
                                                materialize_root, next_step)
from coliseum.textlab.spatial.world import (AgentBodySpec, ObjectSpec,
                                            PerceptionRegime, PortalSpec, RoomSpec,
                                            SpatialWorldSpec)
from coliseum.textlab.spatial.world_line import WorldLine

SPATIAL_SCENARIO_SCHEMA_VERSION = "0.1"


def _select_effect(cands, intent, ids):
    """Resolve a symbolic intent to its EXACT candidate-set member."""
    kind = intent[0]
    for eff in cands.get(kind, ()):
        if kind == "move" and eff["to_room_instance_id"] == ids[intent[1]]:
            return eff
        if kind in ("take", "drop") and eff["object_instance_id"] == ids[intent[1]]:
            return eff
    raise ContentRecordError(
        f"scenario intent {intent!r} is not a legal candidate at this state "
        "(state-dependent legality refused it)")


def _derive_script(genesis, closure, registry, world_line_id, glx, intents_by_key,
                   key_of, ids, fork_after_intent):
    """Simulate the canonical dispatch to derive the committed activate-effect
    script + the exclusive explicit stop position + the designated fork point.
    Returns (script, stop_position, fork_position, fork_state_hash).

    The PROBE run (empty commitment, no stop) is registered so consume() can mint
    its cursors; its chain is distinct from the canonical run's chain (different
    scheduler_run_id) and inert by the S2B old-cursor rule, while the world states
    and transitions it registers are byte-identical to the ones the canonical
    schedule() re-registers (registration is idempotent for identical content)."""
    probe_run = SchedulerRun(world_line_id, glx.id, action_script_commitment([]),
                             explicit_stop_position=None)
    registry.register(probe_run)
    cursor = initial_scheduler_state(probe_run, genesis, registry)
    state = genesis
    script = []
    pending = {k: list(v) for k, v in intents_by_key.items()}
    consumed = 0
    total = sum(len(v) for v in intents_by_key.values())
    fork_position = None
    fork_state_hash = None
    while True:
        step = next_step(cursor, state, closure, registry)
        if step == QUIESCENT:
            raise ContentRecordError("scenario reached quiescence before its intents")
        if step == ADVANCE:
            t = _mk_transition(state, {"action": "advance_step"}, registry)
            cursor, state = consume(cursor, state, t, closure, registry)
        else:
            body = step.content["agent_body_id"]
            key = key_of[body]
            if step.content["outcome_kind"] == "pass" or not pending.get(key):
                if step.content["outcome_kind"] != "pass" and not pending.get(key):
                    # intents exhausted for this body but it still has legal moves:
                    # the scenario must terminate BEFORE minting an unscripted
                    # activation — stop exactly here.
                    break
                cursor, state = consume(cursor, state, None, closure, registry)
            else:
                intent = pending[key].pop(0)
                cands = candidate_effects(body, state, closure, registry)
                eff = _select_effect(cands, intent, ids)
                t = _mk_transition(state, eff, registry, actor=body)
                cursor, state = consume(cursor, state, t, closure, registry)
                script.append(eff)
                consumed += 1
                if consumed == fork_after_intent:
                    fork_position = cursor.content["scheduler_position"]
                    fork_state_hash = state.id
        in_transit = any(p["location"]["tag"] == "in_transit"
                         for p in state.content["placements"])
        if consumed == total and not in_transit:
            # all intents consumed and every arrival resolved: deterministic terminal.
            break
    if consumed != total:
        raise ContentRecordError("scenario intents were not all consumable")
    return script, cursor.content["scheduler_position"], fork_position, fork_state_hash


def _two_agent_private_object_v1(registry, seed):
    """spatial_two_agent_private_object_v1 — 2 connected rooms; 2 scripted agents;
    1 portable token; 1 PRIVATE object (a gem INSIDE a container box: invisible to
    every actor view in renderer v0 — the private-object mechanism of the
    integrated S2C design); a deterministic ~7-position script with a portal move,
    object interactions, a state-dependent legality change (the token stops being
    takeable once held), a designated fork point, and an explicit terminal."""
    pr = PerceptionRegime("0.1", "room_v0", "off_v0", "1"); registry.register(pr)
    rs = RoomSpec("plain-room", ["scenario"], None, "los", "adj", ["n"])
    registry.register(rs)
    ps = PortalSpec(rs.id, rs.id, "bidirectional", 0, "open"); registry.register(ps)
    token = ObjectSpec("token", True, False, "visible", True, False, [], ["take"])
    box = ObjectSpec("box", False, True, "visible", False, False, [], [])
    gem = ObjectSpec("gem", True, False, "visible", True, False, [], ["take"])
    for s in (token, box, gem):
        registry.register(s)
    bs = AgentBodySpec("humanoid", pr.id, None); registry.register(bs)
    layout = {
        "rooms": [{"room_spec_id": rs.id, "room_logical_key": "A"},
                  {"room_spec_id": rs.id, "room_logical_key": "B"}],
        "portals": [{"portal_spec_id": ps.id, "portal_logical_key": "AB",
                     "from_room_logical_key": "A", "to_room_logical_key": "B"}],
        "entities": [
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
        ],
    }
    world = SpatialWorldSpec([rs.id], [ps.id], [token.id, box.id, gem.id], [bs.id],
                             pr.id, layout)
    registry.register(world)
    wl = WorldLine.root(world.id, "spatial_two_agent_private_object_v1")
    registry.register(wl)
    genesis, closure = materialize_root(wl, registry)
    glx = WorldLineGenesis(wl.id, genesis.id, _closure_hash(closure), "root")
    registry.register(glx)
    ids = {}
    for iid in closure["bodies"] + closure["objects"]:
        ids[registry.get(iid).content["deterministic_logical_instance_key"]] = iid
    for iid in closure["rooms"]:
        ids["room_" + registry.get(iid).content["deterministic_logical_instance_key"]] = iid
    # the story: alice takes the token (object interaction; after this the token is
    # no longer takeable by anyone — the state-dependent legality change); bob moves
    # B->A (portal move); alice carries the token A->B; bob follows A->B.
    intents = {"alice": [("take", "token"), ("move", "room_B")],
               "bob": [("move", "room_A"), ("move", "room_B")]}
    key_of = {ids[k]: k for k in ("alice", "bob")}
    script, stop, fork_position, fork_state_hash = _derive_script(
        genesis, closure, registry, wl.id, glx, intents, key_of, ids,
        fork_after_intent=1)                     # fork point: after alice's take
    run = SchedulerRun(wl.id, glx.id, action_script_commitment(script),
                       explicit_stop_position=stop)
    registry.register(run)
    stream = RandomStream(wl.id, 0, f"scenario-seed-{seed}")
    registry.register(stream)
    return {
        "scenario": "spatial_two_agent_private_object_v1",
        "scenario_schema_version": SPATIAL_SCENARIO_SCHEMA_VERSION,
        "seed": seed,
        "world_line": wl,
        "genesis": genesis,
        "closure": closure,
        "world_line_genesis": glx,
        "run": run,
        "script": script,
        "explicit_stop_position": stop,
        "fork_position": fork_position,
        "fork_state_hash": fork_state_hash,
        "random_stream": stream,
        "observers": ["alice", "bob"],
        "private_object_key": "gem",
        "ids": ids,
    }


SCENARIOS = {
    "spatial_two_agent_private_object_v1": _two_agent_private_object_v1,
}


def build_scenario(name, registry, seed):
    """Build the named scenario into ``registry`` with every identity auto-derived.
    Unknown scenario names fail closed."""
    if name not in SCENARIOS:
        raise ContentRecordError(
            f"unknown spatial scenario {name!r} (known: {sorted(SCENARIOS)})")
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ContentRecordError("seed must be a non-negative int")
    return SCENARIOS[name](registry, seed)
