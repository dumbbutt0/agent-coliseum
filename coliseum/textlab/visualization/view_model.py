"""Perspective-scoped, deterministic presentation models for spatial evidence."""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from typing import Mapping

from .errors import refuse
from .evidence import (API_VERSION, VIEW_MODEL_VERSION, ReplayVerification,
                       ValidatedRun, thaw)

_PERSPECTIVES = frozenset({"actor", "privileged"})
_ACTION_LABELS = {
    "move": "moved", "take": "took an object", "drop": "dropped an object",
    "give": "gave an object", "put_inside": "stored an object",
    "take_out": "removed an object", "spawn": "appeared",
    "despawn": "departed", "remove": "was removed",
    "advance_step": "advanced the world clock",
}


def _short(identity):
    return identity[:8]


def _presentation_id(*parts):
    encoded = json.dumps(parts, ensure_ascii=True, separators=(",", ":"))
    return "p-" + hashlib.sha256(encoded.encode("ascii")).hexdigest()[:16]


def _labels(run):
    reverse = {}
    for key, identity in sorted(run["instance_ids"].items()):
        reverse.setdefault(identity, key)
    return reverse


def _entity_label(entity_id, kind, perspective, labels, actor_body=None):
    if perspective == "actor":
        if entity_id == actor_body:
            return "You"
        prefix = "Agent" if kind == "agent_body" else "Object"
        return f"{prefix} {_short(entity_id)}"
    return labels.get(entity_id, f"{'Agent' if kind == 'agent_body' else 'Object'} {_short(entity_id)}")


def _room_label(room_id, perspective, labels):
    if perspective == "actor":
        return f"Room {_short(room_id)}"
    return labels.get(room_id, f"Room {_short(room_id)}")


def _layout(room_ids):
    """Versioned presentation-only grid; topology and identity never depend on it."""
    ordered = sorted(room_ids)
    columns = max(1, min(3, math.ceil(math.sqrt(len(ordered)))))
    return {room_id: {"x": 70 + (index % columns) * 260,
                      "y": 70 + (index // columns) * 210,
                      "width": 210, "height": 150}
            for index, room_id in enumerate(ordered)}


def _effective_room(entity_id, placement_by_id, seen=None):
    seen = set() if seen is None else seen
    if entity_id in seen:
        return None
    seen.add(entity_id)
    placement = placement_by_id.get(entity_id)
    if not placement:
        return None
    loc = placement["location"]
    if loc["tag"] == "in_room":
        return loc["room_instance_id"]
    if loc["tag"] == "held_by":
        return _effective_room(loc["agent_body_id"], placement_by_id, seen)
    if loc["tag"] == "inside":
        return _effective_room(loc["object_instance_id"], placement_by_id, seen)
    return loc.get("origin_room_instance_id")


def _entity_rows(placements, rooms, perspective, labels, actor_body=None):
    placement_by_id = {p["entity_id"]: p for p in placements}
    grouped = defaultdict(list)
    for placement in placements:
        grouped[_effective_room(placement["entity_id"], placement_by_id)].append(placement)
    rows = []
    for room_id in sorted(grouped, key=lambda value: value or ""):
        for offset, placement in enumerate(sorted(grouped[room_id], key=lambda p: p["entity_id"])):
            box = rooms.get(room_id, {"x": 20, "y": 20, "width": 210, "height": 150})
            column, row = offset % 5, offset // 5
            location = thaw(placement["location"])
            rows.append({
                "id": placement["entity_id"],
                "label": _entity_label(placement["entity_id"], placement["entity_kind"],
                                       perspective, labels, actor_body),
                "kind": placement["entity_kind"],
                "location": location,
                "room_id": room_id,
                "x": box["x"] + 34 + column * 34,
                "y": box["y"] + 58 + row * 36,
                "semantic_source": "authoritative",
            })
    visible_held = defaultdict(list)
    for placement in placements:
        location = placement["location"]
        if placement["entity_kind"] == "object" and location["tag"] == "held_by":
            visible_held[location["agent_body_id"]].append(placement["entity_id"])
    for row in rows:
        if row["kind"] == "agent_body":
            row["visible_inventory_ids"] = sorted(visible_held[row["id"]])
    return sorted(rows, key=lambda row: row["id"])


def _map_rows(room_ids, portal_rows, perspective, labels):
    layout = _layout(room_ids)
    rooms = [{"id": room_id, "label": _room_label(room_id, perspective, labels),
              **layout[room_id], "semantic_source": "derived"}
             for room_id in sorted(room_ids)]
    portals = []
    for portal in sorted(portal_rows, key=lambda p: (
            p["portal_instance_id"], p.get("from_room_instance_id", ""),
            p["to_room_instance_id"])):
        source = portal.get("from_room_instance_id")
        target = portal["to_room_instance_id"]
        if source not in layout or target not in layout:
            continue
        portals.append({
            "id": portal["portal_instance_id"],
            "from_room_id": source, "to_room_id": target,
            "x1": layout[source]["x"] + layout[source]["width"] / 2,
            "y1": layout[source]["y"] + layout[source]["height"] / 2,
            "x2": layout[target]["x"] + layout[target]["width"] / 2,
            "y2": layout[target]["y"] + layout[target]["height"] / 2,
            "semantic_source": "authoritative",
        })
    return rooms, portals, layout


def _observation_rows(validated):
    by_position = defaultdict(dict)
    for row in validated.observations:
        by_position[row["scheduler_position"]][row["observer_body_id"]] = row
    return by_position


def _privileged_snapshots(validated, labels):
    observations = _observation_rows(validated)
    first_body = sorted(validated.run["observers"].values())[0]
    room_ids = set(validated.closure["rooms"])
    portals = [thaw(p) for p in validated.closure["portals"]]
    room_rows, portal_rows, layout = _map_rows(room_ids, portals, "privileged", labels)
    activation_by_position = {row["scheduler_position"]: row
                              for row in validated.activations}
    snapshots = []
    for position in range(len(validated.chain)):
        observation = observations[position][first_body]
        content = observation["privileged_content"]["content"]
        projection = content["observable_state_projection"]
        entities = _entity_rows(projection["authoritative_placements"], layout,
                                "privileged", labels)
        lifecycle = {row["entity_id"]: row["status"]
                     for row in projection["authoritative_lifecycle"]}
        for entity in entities:
            entity["status"] = lifecycle[entity["id"]]
        dispatch = activation_by_position.get(position)
        snapshots.append({
            "position": position, "logical_step": content["logical_step"],
            "rooms": room_rows, "portals": portal_rows, "entities": entities,
            "dispatch": _privileged_dispatch(dispatch, labels) if dispatch else None,
            "map_state_source": "authoritative_with_derived_layout",
        })
    return snapshots


def _privileged_dispatch(row, labels):
    result = {"step_kind": row["step_kind"],
              "semantic_source": "authoritative"}
    if "activation" not in row:
        return result
    activation = row["activation"]
    body = activation["agent_body_id"]
    result.update({
        "agent_id": body,
        "agent_label": labels.get(body, f"Agent {_short(body)}"),
        "outcome": activation["outcome_kind"],
        "legal_action_kinds": list(activation["legal_action_kinds"]),
        "selected_action": (row["selected_effect"]["action"]
                            if row["selected_effect"] else None),
    })
    return result


def _actor_snapshots(validated, actor_key):
    if actor_key not in validated.run["observers"]:
        refuse("actor_unavailable", "pinned actor is not an observer in this run")
    actor_body = validated.run["observers"][actor_key]
    observations = _observation_rows(validated)
    known_rooms, known_portals = set(), {}
    snapshots = []
    for position in range(len(validated.chain)):
        row = observations[position][actor_body]
        content = row["actor_content"]["content"]
        room = content["visible_room_identity"]
        if room is not None:
            known_rooms.add(room)
        for portal in content["observable_state_projection"]["portals"]:
            known_rooms.add(portal["to_room_instance_id"])
            key = (portal["portal_instance_id"], room, portal["to_room_instance_id"])
            known_portals[key] = {"portal_instance_id": portal["portal_instance_id"],
                                  "from_room_instance_id": room,
                                  "to_room_instance_id": portal["to_room_instance_id"]}
        rooms, portals, layout = _map_rows(known_rooms, known_portals.values(),
                                           "actor", {})
        entities = _entity_rows(content["observable_state_projection"]["entities"],
                                layout, "actor", {}, actor_body)
        snapshots.append({
            "position": position, "logical_step": content["logical_step"],
            "rooms": rooms, "portals": portals, "entities": entities,
            "visible_room_id": room,
            "source_actor_observation_id": row["actor_observation_id"],
            "map_state_source": "actor_observation_with_derived_layout",
        })
    return snapshots, actor_body


def _privileged_events(validated, labels):
    events = []
    transitions = {row["transition_id"]: row["content"]
                   for row in validated.transitions}
    for row in validated.activations:
        position = row["scheduler_position"]
        kind = row["step_kind"]
        structured = {"step_kind": kind,
                      "scheduler_state_id": validated.chain[position]["scheduler_state_id"]}
        if "activation" in row:
            body = row["activation"]["agent_body_id"]
            label = labels.get(body, f"Agent {_short(body)}")
            structured["agent_id"] = body
            structured["activation_id"] = row["activation_id"]
            if kind == "pass":
                summary = f"{label} had no legal action and passed."
            else:
                action = row["selected_effect"]["action"]
                structured["action"] = action
                summary = f"{label} {_ACTION_LABELS.get(action, 'acted')}."
        else:
            summary = "The scheduler advanced the world state."
        transition_id = row["applied_transition_id"]
        if transition_id is not None:
            structured["transition_id"] = transition_id
            structured["effect"] = thaw(transitions[transition_id]["effect"])
        events.append({
            "id": _presentation_id("privileged", position, kind),
            "position": position, "category": kind, "summary": summary,
            "structured": structured, "semantic_source": "authoritative",
        })
    return events


def _actor_events(snapshots):
    events, previous_room, previous_entities = [], None, set()
    for snapshot in snapshots:
        position = snapshot["position"]
        room = snapshot.get("visible_room_id")
        entities = {entity["id"] for entity in snapshot["entities"]}
        if room != previous_room:
            summary = (f"You observed room {_short(room)}."
                       if room is not None else "You were between visible rooms.")
            events.append({
                "id": _presentation_id("actor", position, "room", room),
                "position": position, "category": "observation",
                "summary": summary,
                "structured": {"observation_change": "visible_room",
                               "room_id": room,
                               "source_actor_observation_id":
                                   snapshot["source_actor_observation_id"]},
                "semantic_source": "derived_from_actor_observation",
            })
        appeared, disappeared = sorted(entities - previous_entities), \
            sorted(previous_entities - entities)
        if appeared or disappeared:
            events.append({
                "id": _presentation_id("actor", position, "entities", appeared, disappeared),
                "position": position, "category": "visibility",
                "summary": f"Visible entities changed (+{len(appeared)}, -{len(disappeared)}).",
                "structured": {"appeared_count": len(appeared),
                               "disappeared_count": len(disappeared),
                               "source_actor_observation_id":
                                   snapshot["source_actor_observation_id"]},
                "semantic_source": "derived_from_actor_observation",
            })
        previous_room, previous_entities = room, entities
    return events


def _provenance(validated, replay, perspective):
    if perspective == "actor":
        # Actor responses are a positive projection of actor artifacts. Replay
        # gates, evaluator reports, and their presence/absence are privileged
        # carriers, so even conservative report ceilings must not enter this
        # payload or create a cross-report side channel.
        return {
            "artifact_validation": "valid",
            "replay_verification": "not_exposed",
            "replay_detail": "not exposed in actor view",
            "report_authentication": "not_exposed",
            "completion": "unknown",
            "behavioral_claimability": "unknown",
            "result_status": "unknown",
            "training_admission": "unknown",
            "governance_approval": "not_bound",
            "quarantine": "unknown",
            "correction_lineage": "unknown",
        }
    report = validated.live_report["content"] if validated.live_report else None
    authenticated_positive = (replay.state == "verified" and
                              (report is None or replay.report_state == "verified"))
    return {
        "artifact_validation": "valid",
        "replay_verification": replay.state,
        "replay_detail": replay.detail,
        "report_authentication": replay.report_state,
        # Negative ceilings remain useful diagnostically. Favorable states require
        # provider-free byte authentication, because content records are
        # constructible by anyone and structural self-consistency is not proof.
        "completion": ("complete" if report and report["complete"] is True
                       and authenticated_positive else
                       "incomplete" if report and report["complete"] is False else "unknown"),
        "behavioral_claimability": (
            "claimable" if report and report["behavioral_departure_claimable"] is True
            and authenticated_positive else
            "nonclaimable" if report and report["behavioral_departure_claimable"] is False
            else "unknown"),
        "result_status": (report["status"] if report and
                          (report["status"] == "incomplete" or authenticated_positive)
                          else "unknown"),
        "training_admission": "unknown",
        "governance_approval": "not_bound",
        "quarantine": "unknown",
        "correction_lineage": "unknown",
    }


def run_card(validated, perspective, actor_key=None, replay_verification=None):
    """Small perspective-safe listing record; never enumerates actor identities."""
    if perspective not in _PERSPECTIVES:
        refuse("invalid_perspective", "perspective must be actor or privileged")
    if perspective == "actor" and actor_key not in validated.run["observers"]:
        refuse("actor_unavailable", "pinned actor is not an observer in this run")
    replay = replay_verification or ReplayVerification("unverified", "not requested")
    card = {
        "run_id": validated.run_id, "scenario": validated.run["scenario"],
        "seed": validated.run["seed"],
        "experiment_id": None, "agent_regime": None,
        "source_schema_versions": {
            "spatial_run": validated.run["spatial_run_schema_version"],
            "spatial": validated.run["spatial_schema_version"],
            "scheduler": validated.run["scheduler_version"],
            "renderer": validated.run["renderer_version"],
        },
        "validation": _provenance(validated, replay, perspective),
    }
    if perspective == "privileged":
        card["observer_count"] = len(validated.run["observers"])
        card["chain_length"] = validated.run["chain_length"]
        if validated.live_report is not None:
            report = validated.live_report["content"]
            card["model_regime"] = {
                "model_id": report["regime"].get("model_id"),
                "source": "structurally_valid_unverified_report",
            }
            card["termination"] = thaw(report["terminated"])
        else:
            card["model_regime"] = None
            card["termination"] = None
    else:
        card["model_regime"] = None
        card["termination"] = None
    return card


def build_view_model(validated, perspective, actor_key=None,
                     replay_verification=None):
    """Return the sole renderer input; actor output uses actor artifacts only."""
    if not isinstance(validated, ValidatedRun):
        refuse("invalid_run", "build_view_model requires a ValidatedRun")
    if perspective not in _PERSPECTIVES:
        refuse("invalid_perspective", "perspective must be actor or privileged")
    replay = replay_verification or ReplayVerification("unverified", "not requested")
    labels = _labels(validated.run) if perspective == "privileged" else {}
    if perspective == "privileged":
        snapshots = _privileged_snapshots(validated, labels)
        events = _privileged_events(validated, labels)
        perspective_info = {"kind": "privileged", "label": "Privileged research view"}
    else:
        snapshots, _actor_body = _actor_snapshots(validated, actor_key)
        events = _actor_events(snapshots)
        perspective_info = {"kind": "actor", "label": "Actor-safe recorded view"}
    card = run_card(validated, perspective, actor_key, replay)
    experiment = {"experiment_id": None, "scenario": validated.run["scenario"],
                  "agent_regime": None, "model_regime": None,
                  "seed": validated.run["seed"], "termination": None}
    if perspective == "privileged" and validated.live_report is not None:
        report = validated.live_report["content"]
        regime = report["regime"]
        experiment["model_regime"] = {
            "model_id": regime.get("model_id"),
            "model_digest": regime.get("model_digest"),
            "decoding": thaw(regime.get("decoding")),
            "backend_version": regime.get("backend_version"),
            "seed_supported": regime.get("seed_supported"),
            "source": "structurally_valid_unverified_report",
        }
        experiment["termination"] = thaw(report["terminated"])
    return {
        "api_version": API_VERSION, "view_model_version": VIEW_MODEL_VERSION,
        "run_id": validated.run_id, "perspective": perspective_info,
        "source_schema_versions": card["source_schema_versions"],
        "validation": card["validation"],
        "experiment": experiment,
        "playback": {"first_position": 0,
                     "last_position": len(snapshots) - 1,
                     "position_count": len(snapshots)},
        "map_model": {"template_source": (
                          "validated recorded topology" if perspective == "privileged"
                          else "actor-observed topology only"),
                      "state_source": (
                          "validated privileged observations" if perspective == "privileged"
                          else "validated pinned-actor observations"),
                      "theme": "geometric_mvp",
                      "layout": "derived_grid_v1",
                      "simulation_impact": False},
        "overlay_catalog": [
            {"id": "room_labels", "label": "Room labels", "source": "derived"},
            {"id": "portal_connectivity", "label": "Portal connectivity",
             "source": "authoritative"},
            {"id": "entity_locations", "label": "Entity locations",
             "source": "authoritative"},
            {"id": "event_markers", "label": "Selected event marker",
             "source": "derived"},
        ],
        "snapshots": snapshots, "events": events,
    }
