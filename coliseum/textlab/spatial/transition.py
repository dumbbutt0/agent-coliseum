"""Location transitions + the pure fold — S2A.

`LocationTransition` is a verifiable edge `prior_state_hash --(actor, effect)-->
resulting_state_hash`. `apply_transition` fails closed on cross-world / stale /
gapped-step / actor / illegal-effect / transplant, and `replay` folds an ordered
transition list from an admitted initial state to a byte-identical result.
"""
from __future__ import annotations

import copy

from coliseum.textlab._content_record import ContentRecord, ContentRecordError
from coliseum.textlab.spatial.state import (WorldState, admit_world_state,
                                            _resolve_spec, validate_location)

LOCATION_TRANSITION_SCHEMA_VERSION = "1"

_SYSTEM_ACTIONS = frozenset({"spawn", "despawn", "remove", "advance_step"})
_ACTOR_ACTIONS = frozenset({"move", "take", "drop", "give", "put_inside", "take_out"})
_ALL_ACTIONS = _SYSTEM_ACTIONS | _ACTOR_ACTIONS

_EFFECT_KEYS = {
    "spawn": {"action", "entity_id", "entity_kind", "location"},
    "despawn": {"action", "entity_id", "entity_kind"},
    "remove": {"action", "entity_id", "entity_kind"},
    "advance_step": {"action"},
    "move": {"action", "agent_body_id", "portal_instance_id",
             "from_room_instance_id", "to_room_instance_id"},
    "take": {"action", "agent_body_id", "object_instance_id"},
    "drop": {"action", "agent_body_id", "object_instance_id"},
    "give": {"action", "agent_body_id", "object_instance_id", "recipient_agent_body_id"},
    "put_inside": {"action", "agent_body_id", "object_instance_id",
                   "container_object_instance_id"},
    "take_out": {"action", "agent_body_id", "object_instance_id",
                 "container_object_instance_id"},
}
# the acting body field per actor action.
_ACTOR_FIELD = {"move": "agent_body_id", "take": "agent_body_id", "drop": "agent_body_id",
                "give": "agent_body_id", "put_inside": "agent_body_id",
                "take_out": "agent_body_id"}


class LocationTransition(ContentRecord):
    __slots__ = ()
    DOMAIN = "spatial.location_transition.v1"
    ID_FIELD = "location_transition_id"

    def __init__(self, world_line_id, logical_step, prior_state_hash,
                 resulting_state_hash, effect, actor_body_id=None,
                 spatial_schema_version=None):
        from coliseum.textlab.spatial.world import SPATIAL_SCHEMA_VERSION
        ver = spatial_schema_version or SPATIAL_SCHEMA_VERSION
        for name, val in (("world_line_id", world_line_id),
                          ("prior_state_hash", prior_state_hash),
                          ("resulting_state_hash", resulting_state_hash)):
            if not isinstance(val, str) or not val:
                raise ContentRecordError(f"{name} must be a non-empty string")
        if not isinstance(logical_step, int) or isinstance(logical_step, bool) or logical_step < 1:
            raise ContentRecordError("logical_step must be an int >= 1")
        _validate_effect_shape(effect)
        if actor_body_id is not None and (not isinstance(actor_body_id, str) or not actor_body_id):
            raise ContentRecordError("actor_body_id must be null or a non-empty string")
        super().__init__({
            "spatial_schema_version": ver,
            "schema_version": LOCATION_TRANSITION_SCHEMA_VERSION,
            "world_line_id": world_line_id,
            "logical_step": logical_step,
            "prior_state_hash": prior_state_hash,
            "resulting_state_hash": resulting_state_hash,
            "actor_body_id": actor_body_id,
            "effect": copy.deepcopy(effect),
        })


def _validate_effect_shape(effect):
    if not isinstance(effect, dict) or "action" not in effect:
        raise ContentRecordError("effect must be a tagged dict")
    action = effect["action"]
    if action not in _ALL_ACTIONS:
        raise ContentRecordError(f"unknown action {action!r}")
    if set(effect) != _EFFECT_KEYS[action]:
        raise ContentRecordError(
            f"effect {action!r} must have exactly keys {sorted(_EFFECT_KEYS[action])}")
    if action in ("spawn",):
        validate_location(effect["location"])
    return effect


def _index(state):
    placements = {p["entity_id"]: copy.deepcopy(p) for p in state.content["placements"]}
    lifecycle = {e["entity_id"]: copy.deepcopy(e) for e in state.content["entity_lifecycle"]}
    return placements, lifecycle


def _rebuild(state, placements, lifecycle, new_step):
    return WorldState(state.world_line_id, new_step, list(placements.values()),
                      list(lifecycle.values()))


def _status(lifecycle, eid):
    row = lifecycle.get(eid)
    return row["status"] if row else None


def _room_of(placements, body_id):
    p = placements.get(body_id)
    if p and p["location"]["tag"] == "in_room":
        return p["location"]["room_instance_id"]
    return None


def _apply_effect(state, effect, registry, new_step):
    """Apply an effect's §4 pre (raise on violation) + post, returning the new
    WorldState (unadmitted — the caller admits + hash-checks)."""
    placements, lifecycle = _index(state)
    action = effect["action"]

    if action == "spawn":
        eid = effect["entity_id"]
        if _status(lifecycle, eid) == "removed":
            raise ContentRecordError("cannot spawn a removed entity (resurrection)")
        if eid in placements:
            raise ContentRecordError("cannot spawn an already-placed entity")
        lifecycle[eid] = {"entity_id": eid, "entity_kind": effect["entity_kind"],
                          "status": "present"}
        placements[eid] = {"entity_id": eid, "entity_kind": effect["entity_kind"],
                           "location": copy.deepcopy(effect["location"])}
    elif action == "despawn":
        eid = effect["entity_id"]
        if _status(lifecycle, eid) != "present":
            raise ContentRecordError("cannot despawn a non-present entity")
        placements.pop(eid, None)
        lifecycle[eid]["status"] = "absent"
    elif action == "remove":
        eid = effect["entity_id"]
        if _status(lifecycle, eid) == "removed":
            raise ContentRecordError("cannot remove an already-removed entity")
        if _status(lifecycle, eid) is None:
            raise ContentRecordError("cannot remove an unknown entity")
        placements.pop(eid, None)
        lifecycle[eid]["status"] = "removed"
    elif action == "advance_step":
        # atomically land every body due to arrive at new_step.
        for eid, p in list(placements.items()):
            loc = p["location"]
            if loc["tag"] == "in_transit" and loc["arrival_step"] == new_step:
                placements[eid]["location"] = {"tag": "in_room",
                                               "room_instance_id": loc["destination_room_instance_id"]}
    elif action == "move":
        body = effect["agent_body_id"]
        if _status(lifecycle, body) != "present":
            raise ContentRecordError("move actor body not present")
        frm = effect["from_room_instance_id"]
        if _room_of(placements, body) != frm:
            raise ContentRecordError("move body is not in from_room")
        _pic, pspec = _resolve_spec(registry, effect["portal_instance_id"],
                                    "spatial.portal_instance.v1")
        f_ic, _ = _resolve_spec(registry, frm, "spatial.room_instance.v1")
        t_ic, _ = _resolve_spec(registry, effect["to_room_instance_id"],
                                "spatial.room_instance.v1")
        endpoints = {pspec["origin_room_spec_id"], pspec["destination_room_spec_id"]}
        if not ({f_ic["room_spec_id"], t_ic["room_spec_id"]} <= endpoints):
            raise ContentRecordError("portal does not connect from->to")
        if pspec["directionality"] == "directed" and (
                f_ic["room_spec_id"] != pspec["origin_room_spec_id"]
                or t_ic["room_spec_id"] != pspec["destination_room_spec_id"]):
            raise ContentRecordError("directed portal wrong orientation")
        dur = pspec["traversal_duration_steps"]
        to_room = effect["to_room_instance_id"]
        if dur == 0:
            placements[body]["location"] = {"tag": "in_room", "room_instance_id": to_room}
        else:
            placements[body]["location"] = {
                "tag": "in_transit", "portal_instance_id": effect["portal_instance_id"],
                "origin_room_instance_id": frm, "destination_room_instance_id": to_room,
                "start_step": new_step, "arrival_step": new_step + dur}
    elif action == "take":
        body, obj = effect["agent_body_id"], effect["object_instance_id"]
        r = _room_of(placements, body)
        if r is None:
            raise ContentRecordError("take body not in a room")
        if _room_of(placements, obj) != r:
            raise ContentRecordError("take object not co-located")
        _ic, ospec = _resolve_spec(registry, obj, "spatial.object_instance.v1")
        if not ospec["portability"]:
            raise ContentRecordError("take object not portable")
        placements[obj]["location"] = {"tag": "held_by", "agent_body_id": body}
    elif action == "drop":
        body, obj = effect["agent_body_id"], effect["object_instance_id"]
        loc = placements.get(obj, {}).get("location", {})
        if loc.get("tag") != "held_by" or loc.get("agent_body_id") != body:
            raise ContentRecordError("drop object not held by body")
        r = _room_of(placements, body)
        if r is None:
            raise ContentRecordError("drop body not in a room")
        placements[obj]["location"] = {"tag": "in_room", "room_instance_id": r}
    elif action == "give":
        body, obj, rcpt = (effect["agent_body_id"], effect["object_instance_id"],
                           effect["recipient_agent_body_id"])
        loc = placements.get(obj, {}).get("location", {})
        if loc.get("tag") != "held_by" or loc.get("agent_body_id") != body:
            raise ContentRecordError("give object not held by giver")
        if _status(lifecycle, rcpt) != "present":
            raise ContentRecordError("give recipient not present")
        r = _room_of(placements, body)
        if r is None or _room_of(placements, rcpt) != r:
            raise ContentRecordError("give recipient not co-located")
        placements[obj]["location"] = {"tag": "held_by", "agent_body_id": rcpt}
    elif action == "put_inside":
        body, obj, cont = (effect["agent_body_id"], effect["object_instance_id"],
                           effect["container_object_instance_id"])
        loc = placements.get(obj, {}).get("location", {})
        if loc.get("tag") != "held_by" or loc.get("agent_body_id") != body:
            raise ContentRecordError("put_inside object not held by body")
        _ic, cspec = _resolve_spec(registry, cont, "spatial.object_instance.v1")
        if not cspec["container_capability"]:
            raise ContentRecordError("container lacks container_capability")
        if obj == cont:
            raise ContentRecordError("object cannot be put inside itself")
        cloc = placements.get(cont, {}).get("location", {})
        cont_room = (cloc.get("room_instance_id") if cloc.get("tag") == "in_room" else None)
        cont_held = (cloc.get("agent_body_id") == body if cloc.get("tag") == "held_by" else False)
        if not (cont_room == _room_of(placements, body) and cont_room is not None) and not cont_held:
            raise ContentRecordError("container not accessible to body")
        placements[obj]["location"] = {"tag": "inside", "object_instance_id": cont}
    elif action == "take_out":
        body, obj, cont = (effect["agent_body_id"], effect["object_instance_id"],
                           effect["container_object_instance_id"])
        loc = placements.get(obj, {}).get("location", {})
        if loc.get("tag") != "inside" or loc.get("object_instance_id") != cont:
            raise ContentRecordError("take_out object not inside container")
        cloc = placements.get(cont, {}).get("location", {})
        cont_room = (cloc.get("room_instance_id") if cloc.get("tag") == "in_room" else None)
        cont_held = (cloc.get("agent_body_id") == body if cloc.get("tag") == "held_by" else False)
        if not (cont_room is not None and cont_room == _room_of(placements, body)) and not cont_held:
            raise ContentRecordError("container not accessible to body")
        placements[obj]["location"] = {"tag": "held_by", "agent_body_id": body}
    else:  # pragma: no cover - guarded by shape validation
        raise ContentRecordError(f"unhandled action {action!r}")

    return _rebuild(state, placements, lifecycle, new_step)


def apply_transition(state, transition, registry):
    """Fail-closed pure transition (§6). Returns the admitted post-state."""
    if not isinstance(state, WorldState) or not isinstance(transition, LocationTransition):
        raise ContentRecordError("apply_transition needs a WorldState + LocationTransition")
    c = transition.content
    if c["world_line_id"] != state.world_line_id:
        raise ContentRecordError("transition world_line_id != state world_line_id")
    if c["prior_state_hash"] != state.id:
        raise ContentRecordError("stale transition: prior_state_hash != state id")
    if c["logical_step"] != state.logical_step + 1:
        raise ContentRecordError("non-monotonic/gapped logical_step")
    effect = c["effect"]
    action = effect["action"]
    actor = c["actor_body_id"]
    # actor rule (§4/§6.4).
    if action in _SYSTEM_ACTIONS:
        if actor is not None:
            raise ContentRecordError(f"system action {action!r} requires null actor_body_id")
    else:
        if actor is None:
            raise ContentRecordError(f"actor action {action!r} requires a non-null actor_body_id")
        if actor != effect[_ACTOR_FIELD[action]]:
            raise ContentRecordError("actor_body_id != effect's acting agent_body_id")
        ic, _ = _resolve_spec(registry, actor, "spatial.agent_body_instance.v1")
        if ic["world_line_id"] != state.world_line_id:
            raise ContentRecordError("actor body is cross-world")
        row = next((e for e in state.content["entity_lifecycle"] if e["entity_id"] == actor), None)
        if row is None or row["status"] != "present":
            raise ContentRecordError("actor body is not present")
    # compute + admit the post-state; verify the claimed resulting hash.
    post = _apply_effect(state, effect, registry, c["logical_step"])
    admit_world_state(post, registry)
    if post.id != c["resulting_state_hash"]:
        raise ContentRecordError("resulting_state_hash does not match recomputed post-state")
    return post


def replay(initial_state, transitions, registry):
    """Fold an ordered transition list from an admitted initial state (§7)."""
    admit_world_state(initial_state, registry)
    state = initial_state
    for t in transitions:
        state = apply_transition(state, t, registry)
    return state
