"""Mutable world state — S2A (design source SPATIAL-S2A-MUTABLE-LOCATION-STATE.md).

The immutable identity records (S0 specs, S1 world-lines + instances) are never
mutated. Mutable state lives in content-addressed :class:`WorldState` snapshots.
This module defines the exclusive-location tagged union, the `WorldState` record
(structural self-validation) and the single-snapshot `admit_world_state` validator
(the registry-dependent world/type/exclusivity/capacity/inventory/transit invariants).
"""
from __future__ import annotations

from coliseum.textlab._content_record import ContentRecord, ContentRecordError

WORLD_STATE_SCHEMA_VERSION = "1"
_ENTITY_KINDS = ("agent_body", "object")
_STATUSES = ("present", "absent", "removed")

# location tag -> exact non-tag key set + the entity kinds it is legal for.
_LOCATION_TAGS = {
    "in_room": (("room_instance_id",), _ENTITY_KINDS),
    "held_by": (("agent_body_id",), ("object",)),
    "inside": (("object_instance_id",), ("object",)),
    "in_transit": (("portal_instance_id", "origin_room_instance_id",
                    "destination_room_instance_id", "start_step", "arrival_step"),
                   ("agent_body",)),
}
# which spec domain each location instance-ref field must resolve to.
_LOCATION_REF_DOMAINS = {
    "room_instance_id": "spatial.room_instance.v1",
    "agent_body_id": "spatial.agent_body_instance.v1",
    "object_instance_id": "spatial.object_instance.v1",
    "portal_instance_id": "spatial.portal_instance.v1",
    "origin_room_instance_id": "spatial.room_instance.v1",
    "destination_room_instance_id": "spatial.room_instance.v1",
}


def _require_str(name, value):
    if not isinstance(value, str) or not value:
        raise ContentRecordError(f"{name} must be a non-empty string")
    return value


def _require_int(name, value):
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ContentRecordError(f"{name} must be a non-negative int")
    return value


def validate_location(loc: dict) -> dict:
    """Structural validation of a tagged location: exact tag + key set + types."""
    if not isinstance(loc, dict) or "tag" not in loc:
        raise ContentRecordError("location must be a tagged dict")
    tag = loc["tag"]
    if tag not in _LOCATION_TAGS:
        raise ContentRecordError(f"unknown location tag {tag!r}")
    keys, _kinds = _LOCATION_TAGS[tag]
    if set(loc) != {"tag", *keys}:
        raise ContentRecordError(
            f"location {tag!r} must have exactly keys {('tag', *keys)}, got {sorted(loc)}")
    for k in keys:
        if k in ("start_step", "arrival_step"):
            _require_int(k, loc[k])
        else:
            _require_str(k, loc[k])
    if tag == "in_transit":
        if not (loc["start_step"] < loc["arrival_step"]):
            raise ContentRecordError("in_transit requires start_step < arrival_step")
        if loc["origin_room_instance_id"] == loc["destination_room_instance_id"]:
            raise ContentRecordError("in_transit origin and destination must differ")
    return loc


def _location_legal_for_kind(entity_kind: str, loc: dict) -> bool:
    return entity_kind in _LOCATION_TAGS[loc["tag"]][1]


def _location_ref_ids(loc: dict):
    """(field, instance_id) pairs of every instance reference nested in a location."""
    return [(k, loc[k]) for k in loc if k in _LOCATION_REF_DOMAINS]


class WorldState(ContentRecord):
    """A content-addressed snapshot of where every entity is. Construction performs
    structural self-validation; registry-dependent invariants are `admit_world_state`."""
    __slots__ = ()
    DOMAIN = "spatial.world_state.v1"
    ID_FIELD = "world_state_id"

    def __init__(self, world_line_id, logical_step, placements, entity_lifecycle,
                 spatial_schema_version=None):
        from coliseum.textlab.spatial.world import SPATIAL_SCHEMA_VERSION
        ver = spatial_schema_version or SPATIAL_SCHEMA_VERSION
        _require_str("world_line_id", world_line_id)
        _require_int("logical_step", logical_step)
        placements = self._canonical_placements(placements)
        entity_lifecycle = self._canonical_lifecycle(entity_lifecycle)
        self._check_agreement(placements, entity_lifecycle, logical_step)
        super().__init__({
            "spatial_schema_version": ver,
            "schema_version": WORLD_STATE_SCHEMA_VERSION,
            "world_line_id": world_line_id,
            "logical_step": logical_step,
            "placements": placements,
            "entity_lifecycle": entity_lifecycle,
        })

    @staticmethod
    def _canonical_placements(placements):
        if not isinstance(placements, list):
            raise ContentRecordError("placements must be a list")
        out = []
        for p in placements:
            if not isinstance(p, dict) or set(p) != {"entity_id", "entity_kind", "location"}:
                raise ContentRecordError(
                    "each placement must have exactly entity_id, entity_kind, location")
            _require_str("entity_id", p["entity_id"])
            if p["entity_kind"] not in _ENTITY_KINDS:
                raise ContentRecordError(f"entity_kind must be one of {_ENTITY_KINDS}")
            loc = validate_location(p["location"])
            if not _location_legal_for_kind(p["entity_kind"], loc):
                raise ContentRecordError(
                    f"location {loc['tag']!r} illegal for {p['entity_kind']!r}")
            out.append({"entity_id": p["entity_id"], "entity_kind": p["entity_kind"],
                        "location": loc})
        ids = [p["entity_id"] for p in out]
        if len(set(ids)) != len(ids):
            raise ContentRecordError("placements entity_id values must be unique")
        return sorted(out, key=lambda p: p["entity_id"])

    @staticmethod
    def _canonical_lifecycle(entity_lifecycle):
        if not isinstance(entity_lifecycle, list):
            raise ContentRecordError("entity_lifecycle must be a list")
        out = []
        for e in entity_lifecycle:
            if not isinstance(e, dict) or set(e) != {"entity_id", "entity_kind", "status"}:
                raise ContentRecordError(
                    "each entity_lifecycle row must have exactly entity_id, entity_kind, status")
            _require_str("entity_id", e["entity_id"])
            if e["entity_kind"] not in _ENTITY_KINDS:
                raise ContentRecordError(f"entity_kind must be one of {_ENTITY_KINDS}")
            if e["status"] not in _STATUSES:
                raise ContentRecordError(f"status must be one of {_STATUSES}")
            out.append({"entity_id": e["entity_id"], "entity_kind": e["entity_kind"],
                        "status": e["status"]})
        ids = [e["entity_id"] for e in out]
        if len(set(ids)) != len(ids):
            raise ContentRecordError("entity_lifecycle entity_id values must be unique")
        return sorted(out, key=lambda e: e["entity_id"])

    @staticmethod
    def _check_agreement(placements, entity_lifecycle, logical_step):
        life = {e["entity_id"]: e for e in entity_lifecycle}
        placed = {p["entity_id"]: p for p in placements}
        # every placed entity is 'present' with matching kind; present <=> exactly one placement.
        for eid, p in placed.items():
            e = life.get(eid)
            if e is None or e["status"] != "present":
                raise ContentRecordError(
                    f"placed entity {eid[:12]!r} must have a 'present' lifecycle row")
            if e["entity_kind"] != p["entity_kind"]:
                raise ContentRecordError(f"entity_kind disagreement for {eid[:12]!r}")
        for eid, e in life.items():
            if e["status"] == "present" and eid not in placed:
                raise ContentRecordError(
                    f"present entity {eid[:12]!r} must have exactly one placement")
            if e["status"] in ("absent", "removed") and eid in placed:
                raise ContentRecordError(
                    f"{e['status']} entity {eid[:12]!r} must have no placement")
        # transit invariant: a body mid-transit at this state (structural bound check).
        for p in placements:
            loc = p["location"]
            if loc["tag"] == "in_transit":
                if not (loc["start_step"] <= logical_step < loc["arrival_step"]):
                    raise ContentRecordError(
                        f"in_transit body {p['entity_id'][:12]!r} requires "
                        "start_step <= logical_step < arrival_step")

    @property
    def world_line_id(self):
        return self.content["world_line_id"]

    @property
    def logical_step(self):
        return self.content["logical_step"]


def _resolve_spec(registry, instance_id, expected_instance_domain):
    """Return (instance_content, spec_content) for a registered instance of the
    expected domain, or raise. Enforces registration + type + spec resolution."""
    try:
        inst = registry.get(instance_id)
    except ContentRecordError:
        raise ContentRecordError(f"unregistered instance {instance_id[:12]!r}")
    if inst.domain != expected_instance_domain:
        raise ContentRecordError(
            f"{instance_id[:12]!r} is a {inst.domain!r}, expected {expected_instance_domain!r}")
    ic = inst.content
    spec_field = {
        "spatial.room_instance.v1": "room_spec_id",
        "spatial.portal_instance.v1": "portal_spec_id",
        "spatial.object_instance.v1": "object_spec_id",
        "spatial.agent_body_instance.v1": "agent_body_spec_id",
    }[expected_instance_domain]
    spec = registry.get(ic[spec_field])
    return ic, spec.content


def admit_world_state(state: "WorldState", registry) -> "WorldState":
    """Single-snapshot registry-dependent validation (§5). Every entity + nested
    location id is registered, type-correct, and in this world-line; effective room
    occupancy (InRoom + InTransit-toward-room) <= capacity; exclusive_possession held
    <= 1; inventory_limit; containment acyclic; transit endpoints connected in-world.
    Returns the state unchanged on success; raises ContentRecordError otherwise."""
    if not isinstance(state, WorldState):
        raise ContentRecordError("admit_world_state requires a WorldState")
    from coliseum.textlab.spatial.world import is_supported_version
    if not is_supported_version(state.content["spatial_schema_version"]):
        raise ContentRecordError("unsupported spatial_schema_version")
    wl = state.world_line_id
    try:
        if registry.get(wl).domain != "spatial.world_line.v1":
            raise ContentRecordError("world_line_id is not a world-line")
    except ContentRecordError as e:
        raise ContentRecordError(f"world_line_id unregistered/invalid: {e}")

    placements = state.content["placements"]
    kind_of = {e["entity_id"]: e["entity_kind"] for e in state.content["entity_lifecycle"]}

    def _check_in_world(instance_id, expected_domain):
        ic, spec = _resolve_spec(registry, instance_id, expected_domain)
        if ic["world_line_id"] != wl:
            raise ContentRecordError(
                f"cross-world reference: {instance_id[:12]!r} is in a different world-line")
        return ic, spec

    # every entity id + nested location id registered, type-correct, in-world.
    entity_domain = {"agent_body": "spatial.agent_body_instance.v1",
                     "object": "spatial.object_instance.v1"}
    for e in state.content["entity_lifecycle"]:
        _check_in_world(e["entity_id"], entity_domain[e["entity_kind"]])
    for p in placements:
        _check_in_world(p["entity_id"], entity_domain[p["entity_kind"]])
        for field, ref in _location_ref_ids(p["location"]):
            _check_in_world(ref, _LOCATION_REF_DOMAINS[field])

    # effective room occupancy = InRoom bodies + InTransit-toward-room bodies <= capacity.
    occ = {}
    for p in placements:
        if p["entity_kind"] != "agent_body":
            continue
        loc = p["location"]
        room = (loc["room_instance_id"] if loc["tag"] == "in_room"
                else loc["destination_room_instance_id"] if loc["tag"] == "in_transit"
                else None)
        if room is not None:
            occ[room] = occ.get(room, 0) + 1
    for room, n in occ.items():
        _ic, spec = _resolve_spec(registry, room, "spatial.room_instance.v1")
        cap = spec.get("capacity")
        if cap is not None and n > cap:
            raise ContentRecordError(
                f"room {room[:12]!r} effective occupancy {n} exceeds capacity {cap}")

    # exclusive_possession: an object held by <= 1; inventory_limit per body;
    # containment acyclic.
    held_by = {}
    inside = {}
    for p in placements:
        loc = p["location"]
        if loc["tag"] == "held_by":
            held_by.setdefault(loc["agent_body_id"], []).append(p["entity_id"])
            _ic, ospec = _resolve_spec(registry, p["entity_id"], "spatial.object_instance.v1")
            # (exclusive_possession is about a single holder, always <=1 per holder edge)
        elif loc["tag"] == "inside":
            inside[p["entity_id"]] = loc["object_instance_id"]
    for body, objs in held_by.items():
        _ic, bspec = _resolve_spec(registry, body, "spatial.agent_body_instance.v1")
        lim = bspec.get("inventory_limit")
        if lim is not None and len(objs) > lim:
            raise ContentRecordError(
                f"body {body[:12]!r} holds {len(objs)} objects, inventory_limit {lim}")
    # containment acyclicity: follow object -> container chains, detect cycles.
    for start in inside:
        seen = set()
        cur = start
        while cur in inside:
            if cur in seen:
                raise ContentRecordError(f"containment cycle at {cur[:12]!r}")
            seen.add(cur)
            cur = inside[cur]

    # in_transit endpoints must be connected by the named portal in-world.
    for p in placements:
        loc = p["location"]
        if loc["tag"] != "in_transit":
            continue
        _pic, pspec = _resolve_spec(registry, loc["portal_instance_id"],
                                    "spatial.portal_instance.v1")
        o_ic, _ = _resolve_spec(registry, loc["origin_room_instance_id"],
                                "spatial.room_instance.v1")
        d_ic, _ = _resolve_spec(registry, loc["destination_room_instance_id"],
                                "spatial.room_instance.v1")
        endpoints = {pspec["origin_room_spec_id"], pspec["destination_room_spec_id"]}
        if not ({o_ic["room_spec_id"], d_ic["room_spec_id"]} <= endpoints):
            raise ContentRecordError(
                "in_transit endpoints are not connected by the named portal")
        if pspec["directionality"] == "directed" and (
                o_ic["room_spec_id"] != pspec["origin_room_spec_id"]
                or d_ic["room_spec_id"] != pspec["destination_room_spec_id"]):
            raise ContentRecordError("in_transit violates directed portal orientation")
    return state
