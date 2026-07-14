"""Deterministic scheduler — S2B implementation (design source
SPATIAL-S2B-DETERMINISTIC-SCHEDULER.md rev 11, integrated 001102).

Pure linear replay chain (owner architecture): no mutable/CAS pointer. A
`SchedulerRun` commits the complete action script + an exclusive terminal rule, so
exactly ONE canonical `SchedulerManifest` exists per run; truth is whole-chain
re-derivation from the authenticated `WorldLineGenesis` over the committed script.
"""
from __future__ import annotations

import copy
import json

from coliseum.textlab._content_record import (ContentRecord, ContentRecordError,
                                              content_id)
from coliseum.textlab.spatial.instance import (AgentBodyInstance, ObjectInstance,
                                               PortalInstance, RoomInstance)
from coliseum.textlab.spatial.state import WorldState, admit_world_state, _resolve_spec
from coliseum.textlab.spatial.transition import (LocationTransition,
                                                 _apply_effect, apply_transition)
from coliseum.textlab.spatial.fork import materialize_fork
from coliseum.textlab.spatial.world import SPATIAL_SCHEMA_VERSION

SCHEDULER_VERSION = "0.1"
SUPPORTED_SCHEDULER_VERSIONS = frozenset({SCHEDULER_VERSION})

QUIESCENT = "QUIESCENT"
ADVANCE = "ADVANCE"

_ACTOR_KINDS = ("move", "take", "drop", "give", "put_inside", "take_out")


def _require_str(name, value):
    if not isinstance(value, str) or not value:
        raise ContentRecordError(f"{name} must be a non-empty string")
    return value


def _require_nonneg(name, value):
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ContentRecordError(f"{name} must be a non-negative int")
    return value


# --------------------------------------------------------------------- records
class WorldLineGenesis(ContentRecord):
    __slots__ = ()
    DOMAIN = "spatial.world_line_genesis.v1"
    ID_FIELD = "world_line_genesis_id"

    def __init__(self, world_line_id, initial_world_state_hash, topology_closure_hash,
                 root_or_fork, parent_world_line_id=None, parent_state_hash=None,
                 fork_logical_step=None, source_fork_decision_hash=None):
        if root_or_fork not in ("root", "fork"):
            raise ContentRecordError("root_or_fork must be 'root' or 'fork'")
        fork_fields = (parent_world_line_id, parent_state_hash, fork_logical_step,
                       source_fork_decision_hash)
        if root_or_fork == "root" and any(f is not None for f in fork_fields):
            raise ContentRecordError("root genesis must have null fork fields")
        if root_or_fork == "fork" and any(f is None for f in fork_fields):
            raise ContentRecordError("fork genesis requires all fork fields")
        super().__init__({
            "spatial_schema_version": SPATIAL_SCHEMA_VERSION,
            "world_line_id": _require_str("world_line_id", world_line_id),
            "initial_world_state_hash": _require_str(
                "initial_world_state_hash", initial_world_state_hash),
            "topology_closure_hash": _require_str(
                "topology_closure_hash", topology_closure_hash),
            "root_or_fork": root_or_fork,
            "parent_world_line_id": parent_world_line_id,
            "parent_state_hash": parent_state_hash,
            "fork_logical_step": fork_logical_step,
            "source_fork_decision_hash": source_fork_decision_hash,
        })


class SchedulerRun(ContentRecord):
    __slots__ = ()
    DOMAIN = "spatial.scheduler_run.v1"
    ID_FIELD = "scheduler_run_id"

    def __init__(self, world_line_id, world_line_genesis_id, action_script_commitment,
                 explicit_stop_position=None):
        if explicit_stop_position is not None:
            _require_nonneg("explicit_stop_position", explicit_stop_position)
        super().__init__({
            "spatial_schema_version": SPATIAL_SCHEMA_VERSION,
            "scheduler_version": SCHEDULER_VERSION,
            "world_line_id": _require_str("world_line_id", world_line_id),
            "world_line_genesis_id": _require_str(
                "world_line_genesis_id", world_line_genesis_id),
            "action_script_commitment": _require_str(
                "action_script_commitment", action_script_commitment),
            "explicit_stop_position": explicit_stop_position,
        })


_LAST_OUTCOMES = ("initial", "activate", "pass", "advance_arrival", "advance_endround")


class SchedulerState(ContentRecord):
    __slots__ = ()
    DOMAIN = "spatial.scheduler_state.v1"
    ID_FIELD = "scheduler_state_id"

    def __init__(self, scheduler_run_id, scheduler_position, previous_scheduler_state_hash,
                 world_line_id, current_world_state_hash, round_start_state_hash,
                 round_index, within_round_index, last_outcome,
                 last_applied_transition_hash=None):
        if last_outcome not in _LAST_OUTCOMES:
            raise ContentRecordError(f"last_outcome must be one of {_LAST_OUTCOMES}")
        _require_nonneg("scheduler_position", scheduler_position)
        _require_nonneg("round_index", round_index)
        _require_nonneg("within_round_index", within_round_index)
        if (scheduler_position == 0) != (previous_scheduler_state_hash is None):
            raise ContentRecordError(
                "previous_scheduler_state_hash is null iff scheduler_position == 0")
        if (last_outcome == "initial") != (scheduler_position == 0):
            raise ContentRecordError("last_outcome 'initial' iff position 0")
        super().__init__({
            "spatial_schema_version": SPATIAL_SCHEMA_VERSION,
            "scheduler_version": SCHEDULER_VERSION,
            "scheduler_run_id": _require_str("scheduler_run_id", scheduler_run_id),
            "scheduler_position": scheduler_position,
            "previous_scheduler_state_hash": previous_scheduler_state_hash,
            "world_line_id": _require_str("world_line_id", world_line_id),
            "current_world_state_hash": _require_str(
                "current_world_state_hash", current_world_state_hash),
            "round_start_state_hash": _require_str(
                "round_start_state_hash", round_start_state_hash),
            "round_index": round_index,
            "within_round_index": within_round_index,
            "last_outcome": last_outcome,
            "last_applied_transition_hash": last_applied_transition_hash,
        })


class Activation(ContentRecord):
    __slots__ = ()
    DOMAIN = "spatial.activation.v1"
    ID_FIELD = "activation_id"

    def __init__(self, scheduler_run_id, scheduler_position, world_line_id,
                 current_world_state_hash, round_start_state_hash, logical_step,
                 round_index, within_round_index, agent_body_id, outcome_kind,
                 legal_action_kinds):
        if outcome_kind not in ("activate", "pass"):
            raise ContentRecordError("outcome_kind must be 'activate' or 'pass'")
        if not isinstance(legal_action_kinds, list) or \
                legal_action_kinds != sorted(set(legal_action_kinds)) or \
                any(k not in _ACTOR_KINDS for k in legal_action_kinds):
            raise ContentRecordError("legal_action_kinds must be a sorted list of actor kinds")
        if (outcome_kind == "pass") != (len(legal_action_kinds) == 0):
            raise ContentRecordError("outcome_kind 'pass' iff legal_action_kinds empty")
        super().__init__({
            "spatial_schema_version": SPATIAL_SCHEMA_VERSION,
            "scheduler_version": SCHEDULER_VERSION,
            "scheduler_run_id": _require_str("scheduler_run_id", scheduler_run_id),
            "scheduler_position": _require_nonneg("scheduler_position", scheduler_position),
            "world_line_id": _require_str("world_line_id", world_line_id),
            "current_world_state_hash": _require_str(
                "current_world_state_hash", current_world_state_hash),
            "round_start_state_hash": _require_str(
                "round_start_state_hash", round_start_state_hash),
            "logical_step": _require_nonneg("logical_step", logical_step),
            "round_index": _require_nonneg("round_index", round_index),
            "within_round_index": _require_nonneg("within_round_index", within_round_index),
            "agent_body_id": _require_str("agent_body_id", agent_body_id),
            "outcome_kind": outcome_kind,
            "legal_action_kinds": list(legal_action_kinds),
        })


class SchedulerManifest(ContentRecord):
    __slots__ = ()
    DOMAIN = "spatial.scheduler_manifest.v1"
    ID_FIELD = "scheduler_manifest_id"

    def __init__(self, scheduler_run_id, genesis_scheduler_state_hash,
                 terminal_scheduler_state_hash, chain_length,
                 ordered_s2a_transition_hashes):
        if not isinstance(ordered_s2a_transition_hashes, list) or \
                any(not isinstance(h, str) or not h for h in ordered_s2a_transition_hashes):
            raise ContentRecordError("ordered_s2a_transition_hashes must be a list of hashes")
        if not isinstance(chain_length, int) or isinstance(chain_length, bool) or chain_length < 1:
            raise ContentRecordError("chain_length must be an int >= 1")
        super().__init__({
            "spatial_schema_version": SPATIAL_SCHEMA_VERSION,
            "scheduler_version": SCHEDULER_VERSION,
            "scheduler_run_id": _require_str("scheduler_run_id", scheduler_run_id),
            "genesis_scheduler_state_hash": _require_str(
                "genesis_scheduler_state_hash", genesis_scheduler_state_hash),
            "terminal_scheduler_state_hash": _require_str(
                "terminal_scheduler_state_hash", terminal_scheduler_state_hash),
            "chain_length": chain_length,
            "ordered_s2a_transition_hashes": list(ordered_s2a_transition_hashes),
        })


class RandomStream(ContentRecord):
    __slots__ = ()
    DOMAIN = "spatial.random_stream.v1"
    ID_FIELD = "random_stream_id"

    def __init__(self, world_line_id, logical_step, purpose):
        super().__init__({
            "spatial_schema_version": SPATIAL_SCHEMA_VERSION,
            "scheduler_version": SCHEDULER_VERSION,
            "world_line_id": _require_str("world_line_id", world_line_id),
            "logical_step": _require_nonneg("logical_step", logical_step),
            "purpose": _require_str("purpose", purpose),
        })


def draw_value(random_stream_id: str, draw_position: int) -> int:
    """The frozen integer draw word: int(digest[:16], 16), 0 <= value < 2**64."""
    digest = content_id("spatial.random_draw.v1",
                        {"random_stream_id": random_stream_id,
                         "draw_position": draw_position}, "random_draw_id")
    return int(digest[:16], 16)


class RandomDraw(ContentRecord):
    __slots__ = ()
    DOMAIN = "spatial.random_draw.v1"
    ID_FIELD = "random_draw_id"

    def __init__(self, random_stream_id, draw_position, value):
        _require_nonneg("draw_position", draw_position)
        if value != draw_value(random_stream_id, draw_position):
            raise ContentRecordError(
                "RandomDraw value disagrees with the frozen derivation")
        super().__init__({
            "spatial_schema_version": SPATIAL_SCHEMA_VERSION,
            "random_stream_id": _require_str("random_stream_id", random_stream_id),
            "draw_position": draw_position,
            "value": value,
        })


# ----------------------------------------------- action-script commitment
def action_script_commitment(action_script: list) -> str:
    """config_hash of the ordered committed actor decisions (concrete S2A effects)."""
    if not isinstance(action_script, list):
        raise ContentRecordError("action_script must be a list of effects")
    return content_id("spatial.action_script.v1",
                      {"actions": copy.deepcopy(action_script)},
                      "action_script_commitment")


# --------------------------------------------------- topology materialization
def _closure_hash(closure: dict) -> str:
    return content_id("spatial.topology_closure.v1", closure, "topology_closure_hash")


def materialize_root(world_line, registry):
    """Materialize a root world-line's canonical genesis + DIRECTED topology closure
    from the normative SpatialWorldSpec.initial_layout (§2.2). Returns
    (genesis_world_state, closure_dict). Pure/deterministic; fails closed on a
    malformed layout."""
    wl = world_line.content if isinstance(world_line, ContentRecord) else registry.get(world_line).content
    if "spatial_world_spec_id" not in wl:
        raise ContentRecordError("world_line is not a ROOT world-line")
    world_line_id = world_line.id if isinstance(world_line, ContentRecord) else world_line
    spec = registry.get(wl["spatial_world_spec_id"]).content
    layout = spec.get("initial_layout")
    if not isinstance(layout, dict) or not all(
            k in layout for k in ("rooms", "portals", "entities")):
        raise ContentRecordError(
            "initial_layout must define rooms, portals, entities (scheduler eligibility)")

    rooms = {}
    for r in layout["rooms"]:
        key = r["room_logical_key"]
        if key in rooms:
            raise ContentRecordError(f"duplicate room logical key {key!r}")
        inst = RoomInstance(r["room_spec_id"], world_line_id, key)
        registry.register(inst)
        rooms[key] = inst.id

    attachments = []
    portal_ids = []
    for p in layout["portals"]:
        key = p["portal_logical_key"]
        inst = PortalInstance(p["portal_spec_id"], world_line_id, key)
        registry.register(inst)
        if inst.id in portal_ids:
            raise ContentRecordError(f"duplicate portal logical key {key!r}")
        portal_ids.append(inst.id)
        frm = rooms.get(p["from_room_logical_key"])
        to = rooms.get(p["to_room_logical_key"])
        if frm is None or to is None:
            raise ContentRecordError("portal attachment references an unknown room key")
        pspec = registry.get(p["portal_spec_id"]).content
        f_spec = registry.get(rooms[p["from_room_logical_key"]]).content["room_spec_id"]
        t_spec = registry.get(rooms[p["to_room_logical_key"]]).content["room_spec_id"]
        if pspec["directionality"] == "directed":
            if f_spec != pspec["origin_room_spec_id"] or t_spec != pspec["destination_room_spec_id"]:
                raise ContentRecordError("directed portal attachment violates its spec orientation")
            attachments.append({"portal_instance_id": inst.id,
                                "from_room_instance_id": frm,
                                "to_room_instance_id": to})
        else:  # bidirectional -> TWO directed attachment rows (orientation expansion)
            if {f_spec, t_spec} - {pspec["origin_room_spec_id"], pspec["destination_room_spec_id"]}:
                raise ContentRecordError("portal attachment rooms do not match its spec endpoints")
            attachments.append({"portal_instance_id": inst.id,
                                "from_room_instance_id": frm,
                                "to_room_instance_id": to})
            attachments.append({"portal_instance_id": inst.id,
                                "from_room_instance_id": to,
                                "to_room_instance_id": frm})

    entities = {}
    kinds = {}
    for e in layout["entities"]:
        key = e["logical_key"]
        if key in entities:
            raise ContentRecordError(f"duplicate entity logical key {key!r}")
        cls = AgentBodyInstance if e["entity_kind"] == "agent_body" else ObjectInstance
        inst = cls(e["spec_id"], world_line_id, key)
        registry.register(inst)
        entities[key] = inst.id
        kinds[key] = e["entity_kind"]

    placements, lifecycle = [], []
    for e in layout["entities"]:
        key = e["logical_key"]
        loc = e["location"]
        tag = loc.get("tag")
        if tag == "in_room":
            resolved = {"tag": "in_room", "room_instance_id": rooms[loc["room_logical_key"]]}
        elif tag == "held_by":
            resolved = {"tag": "held_by", "agent_body_id": entities[loc["holder_logical_key"]]}
        elif tag == "inside":
            resolved = {"tag": "inside", "object_instance_id": entities[loc["container_logical_key"]]}
        else:
            raise ContentRecordError(f"unsupported layout location tag {tag!r}")
        placements.append({"entity_id": entities[key], "entity_kind": kinds[key],
                           "location": resolved})
        lifecycle.append({"entity_id": entities[key], "entity_kind": kinds[key],
                          "status": "present"})

    genesis = WorldState(world_line_id, 0, placements, lifecycle)
    admit_world_state(genesis, registry)
    registry.register(genesis)

    closure = {
        "rooms": sorted(rooms.values()),
        "portals": sorted(attachments, key=lambda a: (a["portal_instance_id"],
                                                      a["from_room_instance_id"],
                                                      a["to_room_instance_id"])),
        "objects": sorted(i for k, i in entities.items() if kinds[k] == "object"),
        "bodies": sorted(i for k, i in entities.items() if kinds[k] == "agent_body"),
    }
    return genesis, closure


def materialize_fork_closure(parent_closure, child_world_line_id, registry):
    """Additive S2B helper (§2.2): remap EVERY parent-closure instance — including
    unoccupied rooms, unused portals, and the attachment relation — into the child
    world-line via (spec_id, deterministic_logical_instance_key)."""
    def _remap(instance_id, cls, spec_field):
        c = registry.get(instance_id).content
        child = cls(c[spec_field], child_world_line_id,
                    c["deterministic_logical_instance_key"])
        registry.register(child)
        return child.id

    rooms = {r: _remap(r, RoomInstance, "room_spec_id") for r in parent_closure["rooms"]}
    portals = {}
    attachments = []
    for a in parent_closure["portals"]:
        pid = a["portal_instance_id"]
        if pid not in portals:
            portals[pid] = _remap(pid, PortalInstance, "portal_spec_id")
        attachments.append({"portal_instance_id": portals[pid],
                            "from_room_instance_id": rooms[a["from_room_instance_id"]],
                            "to_room_instance_id": rooms[a["to_room_instance_id"]]})
    objects = [_remap(o, ObjectInstance, "object_spec_id") for o in parent_closure["objects"]]
    bodies = [_remap(b, AgentBodyInstance, "agent_body_spec_id") for b in parent_closure["bodies"]]
    return {
        "rooms": sorted(rooms.values()),
        "portals": sorted(attachments, key=lambda a: (a["portal_instance_id"],
                                                      a["from_room_instance_id"],
                                                      a["to_room_instance_id"])),
        "objects": sorted(objects),
        "bodies": sorted(bodies),
    }


def validate_world_line_genesis(genesis, registry, witness=None):
    """Authenticate a WorldLineGenesis (§2.1). ROOT: the bound initial state + closure
    must equal the §2.2 materialization (unique + re-derivable — any other admitted
    step-0 snapshot is refused). FORK: re-verify the S2A anti-transplant (registered
    ForkDecision authorizing exactly this parent snapshot+step; materialize_fork
    reproduces the child state; closure = materialize_fork_closure of the parent
    closure) AND the reachability WITNESS `{"scheduler_state_id", "scheduler_manifest_id"}`
    proving parent_state_hash occurs on the parent's authenticated run — recursively
    (via `witness["parent"]` chains) to a root. The witness is NOT identity input."""
    g = genesis.content
    wl_id = g["world_line_id"]
    if g["root_or_fork"] == "root":
        world_line = registry.get(wl_id)
        derived_state, derived_closure = materialize_root(world_line, registry)
        if derived_state.id != g["initial_world_state_hash"]:
            raise ContentRecordError(
                "root genesis does not equal the materialized canonical initial state")
        if _closure_hash(derived_closure) != g["topology_closure_hash"]:
            raise ContentRecordError("root genesis topology closure mismatch")
        return derived_closure
    # fork
    from coliseum.textlab.spatial.fork import ForkDecision, ForkInitialization  # noqa: F401
    D = registry.get(g["source_fork_decision_hash"])
    if D.domain != "spatial.fork_decision.v1":
        raise ContentRecordError("source_fork_decision_hash is not a ForkDecision")
    dc = D.content
    if dc["parent_world_line_id"] != g["parent_world_line_id"] or \
            dc["parent_state_hash"] != g["parent_state_hash"] or \
            dc["fork_logical_step"] != g["fork_logical_step"]:
        raise ContentRecordError("ForkDecision does not authorize this parent snapshot")
    if not isinstance(witness, dict):
        raise ContentRecordError("fork genesis requires a reachability witness")
    ws = registry.get(witness["scheduler_state_id"])
    wm = registry.get(witness["scheduler_manifest_id"])
    if ws.domain != "spatial.scheduler_state.v1" or wm.domain != "spatial.scheduler_manifest.v1":
        raise ContentRecordError("witness records are of the wrong domain")
    if ws.content["scheduler_run_id"] != wm.content["scheduler_run_id"]:
        raise ContentRecordError("witness state does not belong to the witness manifest's run")
    if ws.content["world_line_id"] != g["parent_world_line_id"]:
        raise ContentRecordError("witness is not on the parent world-line")
    if ws.content["current_world_state_hash"] != g["parent_state_hash"]:
        raise ContentRecordError("witness state does not carry the parent snapshot")
    if ws.content["scheduler_position"] >= wm.content["chain_length"]:
        raise ContentRecordError("witness position is outside the finalized chain")
    # parent's own genesis authenticates recursively.
    parent_run = registry.get(ws.content["scheduler_run_id"])
    parent_genesis = registry.get(parent_run.content["world_line_genesis_id"])
    from coliseum.textlab.spatial.scheduler import validate_world_line_genesis as _v
    parent_closure = _v(parent_genesis, registry,
                        witness=witness.get("parent"))
    # deterministic child state + closure re-derivation (anti-transplant).
    parent_state = registry.get(g["parent_state_hash"])
    ps = WorldState(parent_state.content["world_line_id"],
                    parent_state.content["logical_step"],
                    parent_state.content["placements"],
                    parent_state.content["entity_lifecycle"])
    child_line = registry.get(wl_id)
    child_state, _finit = materialize_fork(ps, _as_world_line(child_line), D_as_decision(D), registry)
    if child_state.id != g["initial_world_state_hash"]:
        raise ContentRecordError("fork genesis is not the anti-transplant remap of the parent")
    child_closure = materialize_fork_closure(parent_closure, wl_id, registry)
    if _closure_hash(child_closure) != g["topology_closure_hash"]:
        raise ContentRecordError("fork genesis topology closure mismatch")
    return child_closure


def _as_world_line(stored):
    """Reconstruct a WorldLine record object from its stored content (for
    materialize_fork's isinstance checks)."""
    from coliseum.textlab.spatial.world_line import WorldLine
    return WorldLine(dict(stored.content))


def D_as_decision(stored):
    from coliseum.textlab.spatial.fork import ForkDecision
    c = stored.content
    return ForkDecision(c["parent_world_line_id"], c["parent_state_hash"],
                        c["fork_logical_step"], c["changed_dimension"],
                        c["unchanged_comparison_dims"])


# ------------------------------------------------------ eligibility + legality
def sorted_eligible(state: "WorldState") -> list:
    life = {e["entity_id"]: e for e in state.content["entity_lifecycle"]}
    out = []
    for p in state.content["placements"]:
        if p["entity_kind"] == "agent_body" and p["location"]["tag"] == "in_room" \
                and life[p["entity_id"]]["status"] == "present":
            out.append(p["entity_id"])
    return sorted(out)


def _room_of(state, body_id):
    for p in state.content["placements"]:
        if p["entity_id"] == body_id and p["location"]["tag"] == "in_room":
            return p["location"]["room_instance_id"]
    return None


def _effect_applies(state, effect, registry):
    """True iff the concrete effect satisfies its S2A precondition + admission at
    ``state`` (the normative S2A binding: try the pure application)."""
    try:
        post = _apply_effect(state, effect, registry, state.logical_step + 1)
        admit_world_state(post, registry)
        return True
    except ContentRecordError:
        return False


def candidate_effects(body_id, state, closure, registry, kinds=_ACTOR_KINDS):
    """The finite, closure-and-attachment-bounded candidate effect set (§4) for
    ``body_id`` at ``state``, per kind, filtered by the S2A precondition."""
    out = {k: [] for k in kinds}
    room = _room_of(state, body_id)
    placements = state.content["placements"]
    held = [p["entity_id"] for p in placements
            if p["location"]["tag"] == "held_by"
            and p["location"]["agent_body_id"] == body_id]
    co_objects = [p["entity_id"] for p in placements
                  if p["entity_kind"] == "object"
                  and p["location"]["tag"] == "in_room"
                  and p["location"]["room_instance_id"] == room]
    co_bodies = [p["entity_id"] for p in placements
                 if p["entity_kind"] == "agent_body" and p["entity_id"] != body_id
                 and p["location"]["tag"] == "in_room"
                 and p["location"]["room_instance_id"] == room]
    # accessible containers: objects with container_capability in the body's room or held.
    containers = []
    for p in placements:
        if p["entity_kind"] != "object":
            continue
        loc = p["location"]
        accessible = (loc["tag"] == "in_room" and loc["room_instance_id"] == room) or \
                     (loc["tag"] == "held_by" and loc["agent_body_id"] == body_id)
        if not accessible:
            continue
        _ic, spec = _resolve_spec(registry, p["entity_id"], "spatial.object_instance.v1")
        if spec.get("container_capability"):
            containers.append(p["entity_id"])

    if "move" in kinds and room is not None:
        for a in closure["portals"]:
            if a["from_room_instance_id"] == room:
                eff = {"action": "move", "agent_body_id": body_id,
                       "portal_instance_id": a["portal_instance_id"],
                       "from_room_instance_id": a["from_room_instance_id"],
                       "to_room_instance_id": a["to_room_instance_id"]}
                if _effect_applies(state, eff, registry):
                    out["move"].append(eff)
    if "take" in kinds:
        for obj in co_objects:
            eff = {"action": "take", "agent_body_id": body_id, "object_instance_id": obj}
            if _effect_applies(state, eff, registry):
                out["take"].append(eff)
    if "drop" in kinds:
        for obj in held:
            eff = {"action": "drop", "agent_body_id": body_id, "object_instance_id": obj}
            if _effect_applies(state, eff, registry):
                out["drop"].append(eff)
    if "give" in kinds:
        for obj in held:
            for rcpt in co_bodies:
                eff = {"action": "give", "agent_body_id": body_id,
                       "object_instance_id": obj, "recipient_agent_body_id": rcpt}
                if _effect_applies(state, eff, registry):
                    out["give"].append(eff)
    if "put_inside" in kinds:
        for obj in held:
            for cont in containers:
                if obj == cont:
                    continue
                eff = {"action": "put_inside", "agent_body_id": body_id,
                       "object_instance_id": obj, "container_object_instance_id": cont}
                if _effect_applies(state, eff, registry):
                    out["put_inside"].append(eff)
    if "take_out" in kinds:
        # take_out enumerates objects INSIDE each accessible container (S2A-consistent).
        for cont in containers:
            inside = [p["entity_id"] for p in placements
                      if p["location"]["tag"] == "inside"
                      and p["location"]["object_instance_id"] == cont]
            for obj in inside:
                eff = {"action": "take_out", "agent_body_id": body_id,
                       "object_instance_id": obj, "container_object_instance_id": cont}
                if _effect_applies(state, eff, registry):
                    out["take_out"].append(eff)
    return out


def legal_action_kinds(body_id, state, closure, registry) -> list:
    cands = candidate_effects(body_id, state, closure, registry)
    return sorted(k for k, effs in cands.items() if effs)


# ------------------------------------------------------------- the turn engine
def _arrival_due(state):
    for p in state.content["placements"]:
        loc = p["location"]
        if loc["tag"] == "in_transit" and loc["arrival_step"] == state.logical_step + 1:
            return True
    return False


def initial_scheduler_state(scheduler_run, genesis_state, registry):
    run = scheduler_run.content
    genesis = registry.get(run["world_line_genesis_id"]).content
    if genesis_state.id != genesis["initial_world_state_hash"]:
        raise ContentRecordError(
            "initial cursor must anchor the SchedulerRun's bound genesis state")
    s = SchedulerState(scheduler_run.id, 0, None, run["world_line_id"],
                       genesis_state.id, genesis_state.id, 0, 0, "initial", None)
    registry.register(s)
    return s


def next_step(scheduler_state, world_state, closure, registry):
    """The §3 dispatch: returns QUIESCENT, ADVANCE, or an (unregistered) Activation."""
    c = scheduler_state.content
    if c["scheduler_version"] not in SUPPORTED_SCHEDULER_VERSIONS:
        raise ContentRecordError("unsupported scheduler_version")
    if c["world_line_id"] != world_state.world_line_id:
        raise ContentRecordError("cursor is cross-world")
    if c["current_world_state_hash"] != world_state.id:
        raise ContentRecordError("stale cursor: current_world_state_hash != state id")
    eligible_now = sorted_eligible(world_state)
    in_transit = any(p["location"]["tag"] == "in_transit"
                     for p in world_state.content["placements"])
    if not eligible_now and not in_transit:                     # rule 0: quiescent
        return QUIESCENT
    if _arrival_due(world_state):                               # rule 1: arrivals first
        return ADVANCE
    round_start = registry.get(c["round_start_state_hash"]).content
    q = sorted(p["entity_id"] for p in round_start["placements"]
               if p["entity_kind"] == "agent_body" and p["location"]["tag"] == "in_room")
    # (round_start entities are present by admission; sorted_eligible over the stored
    # content — reconstruct minimal eligibility from the stored round-start snapshot.)
    life = {e["entity_id"]: e["status"] for e in round_start["entity_lifecycle"]}
    q = [b for b in q if life.get(b) == "present"]
    within = c["within_round_index"]
    if within < len(q):                                         # rule 2: head of round
        body = q[within]
        kinds = legal_action_kinds(body, world_state, closure, registry)
        return Activation(c["scheduler_run_id"], c["scheduler_position"] + 1,
                          c["world_line_id"], world_state.id,
                          c["round_start_state_hash"], world_state.logical_step,
                          c["round_index"], within, body,
                          "pass" if not kinds else "activate", kinds)
    return ADVANCE                                              # rule 3: end of round


def consume(scheduler_state, world_state, applied_transition, closure, registry):
    """The ONLY constructor of non-genesis cursors. Verifies the dispatch, the
    supplied S2A edge (or None for pass), candidate-set membership for activates,
    and returns the registered successor cursor + the possibly-new world state."""
    step = next_step(scheduler_state, world_state, closure, registry)
    c = scheduler_state.content
    pos = c["scheduler_position"] + 1
    if step == QUIESCENT:
        raise ContentRecordError("cannot consume a QUIESCENT state (run may end)")
    if step == ADVANCE:
        if not isinstance(applied_transition, LocationTransition) or \
                applied_transition.content["effect"]["action"] != "advance_step":
            raise ContentRecordError("ADVANCE requires an advance_step transition")
        post = apply_transition(world_state, applied_transition, registry)
        registry.register(post)
        arrival = _arrival_due(world_state)
        if arrival:   # same round continues
            nxt = SchedulerState(c["scheduler_run_id"], pos, scheduler_state.id,
                                 c["world_line_id"], post.id,
                                 c["round_start_state_hash"], c["round_index"],
                                 c["within_round_index"], "advance_arrival",
                                 applied_transition.id)
        else:         # end of round -> new round anchored at the post state
            nxt = SchedulerState(c["scheduler_run_id"], pos, scheduler_state.id,
                                 c["world_line_id"], post.id, post.id,
                                 c["round_index"] + 1, 0, "advance_endround",
                                 applied_transition.id)
        registry.register(nxt)
        return nxt, post
    # step is an Activation
    act = step
    if act.content["outcome_kind"] == "pass":
        if applied_transition is not None:
            raise ContentRecordError("pass consumes no transition")
        nxt = SchedulerState(c["scheduler_run_id"], pos, scheduler_state.id,
                             c["world_line_id"], world_state.id,
                             c["round_start_state_hash"], c["round_index"],
                             c["within_round_index"] + 1, "pass", None)
        registry.register(act)
        registry.register(nxt)
        return nxt, world_state
    # activate: the committed effect must be an EXACT candidate-set member.
    if not isinstance(applied_transition, LocationTransition):
        raise ContentRecordError("activate requires a LocationTransition")
    t = applied_transition.content
    body = act.content["agent_body_id"]
    if t["actor_body_id"] != body:
        raise ContentRecordError("transition actor is not the activated head body")
    kind = t["effect"]["action"]
    cands = candidate_effects(body, world_state, closure, registry, kinds=(kind,))
    if t["effect"] not in cands.get(kind, []):
        raise ContentRecordError(
            "committed effect is not a member of the closure-and-attachment-bounded "
            "candidate set for this body/state")
    post = apply_transition(world_state, applied_transition, registry)
    registry.register(post)
    nxt = SchedulerState(c["scheduler_run_id"], pos, scheduler_state.id,
                         c["world_line_id"], post.id, c["round_start_state_hash"],
                         c["round_index"], c["within_round_index"] + 1, "activate",
                         applied_transition.id)
    registry.register(act)
    registry.register(nxt)
    return nxt, post


def _mk_transition(state, effect, registry, actor=None):
    post = _apply_effect(state, effect, registry, state.logical_step + 1)
    admit_world_state(post, registry)
    return LocationTransition(state.world_line_id, state.logical_step + 1, state.id,
                              post.id, effect, actor_body_id=actor)


def schedule(scheduler_run, genesis_state, action_script, closure, registry):
    """Drive a run from its authenticated genesis over the committed action script to
    the run's EXCLUSIVE terminal (§5). Returns (chain, transitions, manifest)."""
    run = scheduler_run.content
    if action_script_commitment(action_script) != run["action_script_commitment"]:
        raise ContentRecordError("action_script does not match the run's commitment")
    cursor = initial_scheduler_state(scheduler_run, genesis_state, registry)
    chain = [cursor]
    transitions = []
    state = genesis_state
    script = list(action_script)
    stop = run["explicit_stop_position"]
    while True:
        if stop is not None and cursor.content["scheduler_position"] == stop:
            break                                        # exclusive explicit stop
        step = next_step(cursor, state, closure, registry)
        if step == QUIESCENT:
            if stop is not None:
                raise ContentRecordError(
                    "run reached quiescence before its committed explicit stop")
            if script:
                raise ContentRecordError(
                    "run reached quiescence with unconsumed committed actions")
            break                                        # exclusive quiescent terminal
        if step == ADVANCE:
            t = _mk_transition(state, {"action": "advance_step"}, registry)
            cursor, state = consume(cursor, state, t, closure, registry)
            transitions.append(t)
        else:
            if step.content["outcome_kind"] == "pass":
                cursor, state = consume(cursor, state, None, closure, registry)
            else:
                if not script:
                    raise ContentRecordError(
                        "committed action script exhausted before terminal")
                effect = script.pop(0)
                t = _mk_transition(state, effect, registry,
                                   actor=step.content["agent_body_id"])
                cursor, state = consume(cursor, state, t, closure, registry)
                transitions.append(t)
        chain.append(cursor)
    if stop is None and script:
        raise ContentRecordError("terminal reached with unconsumed committed actions")
    manifest = SchedulerManifest(scheduler_run.id, chain[0].id, chain[-1].id,
                                 len(chain), [t.id for t in transitions])
    registry.register(manifest)
    return chain, transitions, manifest


def verify_manifest(manifest, scheduler_run, genesis_state, action_script, closure,
                    registry):
    """Whole-chain re-derivation (§5): re-run the scheduler over the committed script
    and require the produced manifest content to equal the given manifest exactly.
    Rejects prefixes, extensions, branches, transition mismatches, and forged
    terminals — the canonical manifest is a pure function of the run."""
    m = manifest.content
    if m["scheduler_run_id"] != scheduler_run.id:
        raise ContentRecordError("manifest does not belong to this scheduler_run")
    _chain, _transitions, canonical = schedule(scheduler_run, genesis_state,
                                               action_script, closure, registry)
    if canonical.content != m:
        raise ContentRecordError(
            "manifest does not match the canonical whole-chain re-derivation")
    return True
