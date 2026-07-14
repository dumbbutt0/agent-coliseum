"""Spatial S2C — perception rendering + non-interference (design rev 3, integrated
001154 @ be6991a7).

The perception renderer is a PURE function of (registered+admitted world state,
observer body, authenticated topology closure, perception regime, schema + renderer
versions). It registers nothing, mutates nothing, draws nothing: perception is
evidence ABOUT a run, never an input TO it.

Every enumeration operates on the closure-visible restriction of the state
(``scheduler._closure_visible``), so an admitted same-world instance OUTSIDE the
authenticated closure changes NEITHER view's observation id. The privileged view
commits to the closure-projected constructed state id
(``closure_visible_state_commitment``) — never the registered full-state id, which
would re-import out-of-closure content into the privileged id.

Actor content is POSITIVELY CONSTRUCTED from the visibility policy (never derived
from privileged content by removing known-secret fields) and validated by the
CLOSED exact actor-schema validator: any unknown key at any depth is refused, which
excludes every smuggled privileged commitment under any field name.
"""
from __future__ import annotations

from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.spatial.scheduler import _closure_visible
from coliseum.textlab.spatial.state import (WorldState, admit_world_state,
                                            validate_location, _resolve_spec)
from coliseum.textlab.spatial.world import SUPPORTED_SPATIAL_SCHEMA_VERSIONS
from coliseum.textlab.training.observation import observation_artifact

#: frozen renderer semantics version (design §2). Renaming/removing/retyping ANY
#: content field — outer or per-view inner — bumps this.
RENDERER_VERSION = "0.1"
SUPPORTED_RENDERER_VERSIONS = ("0.1",)
#: complete fail-closed regime dispatch (design §3.5): EVERY PerceptionRegime field
#: is bound to exact supported literals and checked INDEPENDENTLY — a regime is
#: never silently approximated as v0.
SUPPORTED_VISIBILITY_POLICIES = ("room_v0",)
SUPPORTED_AUDIBILITY_POLICIES = ("off_v0",)
SUPPORTED_OBSERVATION_POLICY_VERSIONS = ("1",)

#: supported object-spec visibility behaviors (design §3.5: unknown values REFUSED,
#: never "assume hidden" or "assume visible").
_VISIBILITY_BEHAVIORS = ("visible", "hidden")

#: the frozen 7 outer content keys (design §2; both views).
_OUTER_KEYS = frozenset({
    "observer_identity", "world_line_id", "logical_step", "perception_regime",
    "visible_room_identity", "visible_entity_identities",
    "observable_state_projection",
})
#: exact actor location shapes permitted by design §4 (container contents are never
#: visible, so "inside" can never appear in an actor projection).
_ACTOR_LOCATION_KEYS = {
    "in_room": frozenset({"tag", "room_instance_id"}),
    "held_by": frozenset({"tag", "agent_body_id"}),
    "in_transit": frozenset({"tag", "portal_instance_id", "origin_room_instance_id",
                             "destination_room_instance_id", "start_step",
                             "arrival_step"}),
}


# --------------------------------------------------------------- schema validation
def assert_actor_content_schema(content) -> None:
    """The CLOSED exact actor-schema validator (design §2): the actor content must
    have EXACTLY the 7 outer keys, its projection EXACTLY the actor two-key
    container, and every row EXACTLY its frozen shape. ANY additional or unknown
    key at ANY depth is refused — carrier-name-independent, so no commitment to
    privileged truth can be smuggled under any field name."""
    if not isinstance(content, dict) or set(content) != _OUTER_KEYS:
        raise ContentRecordError(
            "actor content must have exactly the 7 canonical outer keys")
    if not isinstance(content["observer_identity"], str) or not content["observer_identity"]:
        raise ContentRecordError("observer_identity must be a non-empty string")
    if not isinstance(content["world_line_id"], str) or not content["world_line_id"]:
        raise ContentRecordError("world_line_id must be a non-empty string")
    step = content["logical_step"]
    if not isinstance(step, int) or isinstance(step, bool) or step < 0:
        raise ContentRecordError("logical_step must be a non-negative int")
    if not isinstance(content["perception_regime"], str) or not content["perception_regime"]:
        raise ContentRecordError("perception_regime must be a non-empty string")
    room = content["visible_room_identity"]
    if room is not None and (not isinstance(room, str) or not room):
        raise ContentRecordError("visible_room_identity must be null or a non-empty string")
    vis = content["visible_entity_identities"]
    if not isinstance(vis, list) or vis != sorted(vis) or \
            any(not isinstance(v, str) or not v for v in vis) or len(set(vis)) != len(vis):
        raise ContentRecordError(
            "visible_entity_identities must be a sorted duplicate-free list of ids")
    proj = content["observable_state_projection"]
    if not isinstance(proj, dict) or set(proj) != {"entities", "portals"}:
        raise ContentRecordError(
            "actor observable_state_projection must have exactly {entities, portals}")
    rows = proj["entities"]
    if not isinstance(rows, list):
        raise ContentRecordError("entities must be a list")
    for r in rows:
        if not isinstance(r, dict) or set(r) != {"entity_id", "entity_kind", "location"}:
            raise ContentRecordError(
                "entities rows must have exactly {entity_id, entity_kind, location}")
        if not isinstance(r["entity_id"], str) or not r["entity_id"]:
            raise ContentRecordError("entity_id must be a non-empty string")
        if r["entity_kind"] not in ("agent_body", "object"):
            raise ContentRecordError("unknown entity_kind in actor projection")
        loc = r["location"]
        if not isinstance(loc, dict) or "tag" not in loc or \
                loc["tag"] not in _ACTOR_LOCATION_KEYS or \
                set(loc) != _ACTOR_LOCATION_KEYS[loc["tag"]]:
            raise ContentRecordError(
                "actor entity location must be an exact permitted S2A tagged shape")
        # exact S2A value/type/semantic rules (non-empty string refs; non-negative
        # int steps; start_step < arrival_step; origin != destination).
        validate_location(loc)
        # the S2A kind binding: in_transit is agent_body-only; held_by is object-only.
        if loc["tag"] == "in_transit" and r["entity_kind"] != "agent_body":
            raise ContentRecordError("in_transit rows must be agent bodies")
        if loc["tag"] == "held_by" and r["entity_kind"] != "object":
            raise ContentRecordError("held_by rows must be objects")
    if [r["entity_id"] for r in rows] != sorted(r["entity_id"] for r in rows):
        raise ContentRecordError("entities rows must be sorted by entity_id")
    ports = proj["portals"]
    if not isinstance(ports, list):
        raise ContentRecordError("portals must be a list")
    for p in ports:
        if not isinstance(p, dict) or set(p) != {"portal_instance_id", "to_room_instance_id"}:
            raise ContentRecordError(
                "portals rows must have exactly {portal_instance_id, to_room_instance_id}")
        if any(not isinstance(p[k], str) or not p[k]
               for k in ("portal_instance_id", "to_room_instance_id")):
            raise ContentRecordError("portal row references must be non-empty strings")
    keyed = [(p["portal_instance_id"], p["to_room_instance_id"]) for p in ports]
    if keyed != sorted(keyed):
        raise ContentRecordError(
            "portals rows must be sorted by (portal_instance_id, to_room_instance_id)")


# ------------------------------------------------------------ privileged commitment
def closure_visible_state_commitment(state, closure) -> str:
    """The closure-projected state commitment (design §5): the content id of the
    canonically CONSTRUCTED WorldState over the closure-visible restriction. Derived
    via content addressing only — the projected state is NOT registered (render
    purity) and no chain membership is asserted. For every canonical chain state
    (where the restriction is the identity) it equals the registered state id."""
    visible = _closure_visible(state, closure)
    return visible.id


# --------------------------------------------------------------------- the renderer
def _validate_regime(regime_content) -> None:
    if regime_content.get("spatial_schema_version") not in SUPPORTED_SPATIAL_SCHEMA_VERSIONS:
        raise ContentRecordError("unsupported perception regime spatial_schema_version")
    if regime_content.get("renderer_version") not in SUPPORTED_RENDERER_VERSIONS:
        raise ContentRecordError("unsupported perception regime renderer_version")
    if regime_content.get("visibility_policy") not in SUPPORTED_VISIBILITY_POLICIES:
        raise ContentRecordError("unsupported perception regime visibility_policy")
    if regime_content.get("audibility_policy") not in SUPPORTED_AUDIBILITY_POLICIES:
        raise ContentRecordError("unsupported perception regime audibility_policy")
    if regime_content.get("observation_policy_version") not in \
            SUPPORTED_OBSERVATION_POLICY_VERSIONS:
        raise ContentRecordError("unsupported perception regime observation_policy_version")


def _object_visible(registry, object_id) -> bool:
    """visibility_behavior dispatch — unknown values are REFUSED (fail closed)."""
    _ic, spec = _resolve_spec(registry, object_id, "spatial.object_instance.v1")
    behavior = spec.get("visibility_behavior")
    if behavior not in _VISIBILITY_BEHAVIORS:
        raise ContentRecordError(
            f"unknown visibility_behavior {behavior!r} — refusing to render")
    return behavior == "visible"


def render_observation_pair(state, observer_body_id, closure, registry):
    """Render the (actor, privileged) ObservationArtifact pair for ``observer_body_id``
    at ``state`` under the authenticated ``closure`` (design §3–§5). Pure: neither
    artifact (nor anything else) is registered here."""
    # §3.2 — the state must be a REGISTERED spatial.world_state.v1 for this world.
    stored = registry.get(state.id)
    if stored.domain != "spatial.world_state.v1":
        raise ContentRecordError("state is not a registered spatial.world_state.v1")
    # §3.3 — mandatory render-time admission revalidation: registration does NOT
    # persist admission status, so a merely-registered registry-invalid state is
    # refused here. admit_world_state is pure, preserving render purity.
    admit_world_state(state, registry)
    # §3.1 — perception is a closure capability.
    if observer_body_id not in set(closure["bodies"]):
        raise ContentRecordError("observer is not a member of the authenticated closure")
    inst_content, body_spec = _resolve_spec(
        registry, observer_body_id, "spatial.agent_body_instance.v1")
    if inst_content["world_line_id"] != state.world_line_id:
        raise ContentRecordError("observer is cross-world with the state")
    # §3.5 — complete fail-closed regime dispatch.
    regime_id = body_spec["default_perception_regime_id"]
    regime = registry.get(regime_id)
    if regime.domain != "spatial.perception_regime.v1":
        raise ContentRecordError("resolved perception regime has the wrong domain")
    _validate_regime(regime.content)

    # every enumeration below ranges over the closure-visible restriction (§4).
    visible_state = _closure_visible(state, closure)
    placements = visible_state.content["placements"]
    lifecycle = {e["entity_id"]: e["status"]
                 for e in visible_state.content["entity_lifecycle"]}
    # §3.4 — observer presence + exactly one placement.
    if lifecycle.get(observer_body_id) != "present":
        raise ContentRecordError("observer is not present in the state")
    own = [p for p in placements if p["entity_id"] == observer_body_id]
    if len(own) != 1:
        raise ContentRecordError("observer must have exactly one placement")
    own_loc = own[0]["location"]

    entities = {}          # entity_id -> row
    portals = []

    def _add(p):
        entities[p["entity_id"]] = {"entity_id": p["entity_id"],
                                    "entity_kind": p["entity_kind"],
                                    "location": dict(p["location"])}

    if own_loc["tag"] == "in_room":
        room = own_loc["room_instance_id"]
        visible_bodies = set()
        for p in placements:
            if p["entity_kind"] == "agent_body" and p["location"]["tag"] == "in_room" \
                    and p["location"]["room_instance_id"] == room \
                    and lifecycle.get(p["entity_id"]) == "present":
                _add(p)
                visible_bodies.add(p["entity_id"])
        for p in placements:
            if p["entity_kind"] != "object" or lifecycle.get(p["entity_id"]) != "present":
                continue
            loc = p["location"]
            in_view = (loc["tag"] == "in_room" and loc["room_instance_id"] == room) or \
                      (loc["tag"] == "held_by" and loc["agent_body_id"] in visible_bodies)
            if in_view and _object_visible(registry, p["entity_id"]):
                _add(p)
        for a in closure["portals"]:
            if a["from_room_instance_id"] == room:
                portals.append({"portal_instance_id": a["portal_instance_id"],
                                "to_room_instance_id": a["to_room_instance_id"]})
        visible_room = room
    elif own_loc["tag"] == "in_transit":
        # §4 in-transit: the observer + its inventory only; no room/portal visibility.
        _add(own[0])
        for p in placements:
            if p["entity_kind"] == "object" and lifecycle.get(p["entity_id"]) == "present" \
                    and p["location"]["tag"] == "held_by" \
                    and p["location"]["agent_body_id"] == observer_body_id \
                    and _object_visible(registry, p["entity_id"]):
                _add(p)
        visible_room = None
    else:
        raise ContentRecordError("observer placement tag cannot be observed from")

    rows = [entities[k] for k in sorted(entities)]
    portals.sort(key=lambda p: (p["portal_instance_id"], p["to_room_instance_id"]))
    actor_content = {
        "observer_identity": observer_body_id,
        "world_line_id": state.world_line_id,
        "logical_step": state.logical_step,
        "perception_regime": regime_id,
        "visible_room_identity": visible_room,
        "visible_entity_identities": sorted(entities),
        "observable_state_projection": {"entities": rows, "portals": portals},
    }
    assert_actor_content_schema(actor_content)
    actor = observation_artifact("actor", actor_content)

    # §5 — the privileged inner schema (exactly three keys; never the actor container).
    present_all = sorted(p["entity_id"] for p in placements
                         if lifecycle.get(p["entity_id"]) == "present")
    privileged_content = {
        "observer_identity": observer_body_id,
        "world_line_id": state.world_line_id,
        "logical_step": state.logical_step,
        "perception_regime": regime_id,
        "visible_room_identity": visible_room,
        "visible_entity_identities": present_all,
        "observable_state_projection": {
            "authoritative_placements": [dict(p, location=dict(p["location"]))
                                         for p in placements],
            "authoritative_lifecycle": list(visible_state.content["entity_lifecycle"]),
            "closure_visible_state_commitment": visible_state.id,
        },
    }
    privileged = observation_artifact("privileged", privileged_content)
    return actor, privileged
