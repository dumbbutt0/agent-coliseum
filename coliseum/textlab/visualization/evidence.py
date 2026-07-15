"""Bounded, read-only validation of persisted spatial replay evidence.

Structural validation and replay authentication are deliberately separate.
Every persisted content identity whose full preimage is available is recomputed;
only the existing provider-free replay gates may call a run ``verified``.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.schema import config_hash
from coliseum.textlab.spatial.perception import (
    SUPPORTED_RENDERER_VERSIONS, assert_actor_content_schema)
from coliseum.textlab.spatial.run import canonical_effect_id, replay_spatial_run
from coliseum.textlab.spatial.scenario import SPATIAL_SCENARIO_SCHEMA_VERSION
from coliseum.textlab.spatial.scheduler import (
    SUPPORTED_SCHEDULER_VERSIONS, Activation, SchedulerRun, SchedulerState,
    _closure_hash)
from coliseum.textlab.spatial.state import WorldState
from coliseum.textlab.spatial.transition import (LocationTransition,
                                                 _validate_effect_shape)
from coliseum.textlab.spatial.world import SUPPORTED_SPATIAL_SCHEMA_VERSIONS
from coliseum.textlab.training.observation import observation_artifact
from coliseum.textlab.training.spatial_records import SpatialSourceEvidenceBinding

from .errors import VisualizationError, refuse

API_VERSION = "1"
VIEW_MODEL_VERSION = "1"
SUPPORTED_RUN_SCHEMAS = frozenset({"0.2", "0.3"})
SUPPORTED_SCENARIO_SCHEMAS = frozenset({SPATIAL_SCENARIO_SCHEMA_VERSION})
RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,240}$")
REQUIRED_FILES = (
    "run.json", "chain.jsonl", "transitions.jsonl", "observations.jsonl",
    "activations.jsonl", "closure.json",
)
OPTIONAL_FILES = ("live_report.json",)
JSONL_FILES = frozenset(n for n in REQUIRED_FILES if n.endswith(".jsonl"))

_RUN_KEYS_02 = frozenset({
    "action_script_commitment", "chain_length", "explicit_stop_position",
    "fork_position", "fork_state_hash", "genesis_state_id", "instance_ids",
    "manifest_id", "observation_count", "observers", "private_object_key",
    "random_stream_id", "renderer_version", "run_id", "scenario",
    "scenario_schema_version", "scheduler_run_id", "scheduler_version", "seed",
    "spatial_run_schema_version", "spatial_schema_version",
    "terminal_scheduler_state_id", "terminal_world_state_id",
    "topology_closure_hash", "world_line_genesis_id", "world_line_id",
})
_TREATMENT_KEYS = frozenset({
    "intervention_id", "execution_instance_id", "treatment_bindings",
    "witness_ids",
})
_OBS_OUTER_KEYS = frozenset({
    "scheduler_position", "scheduler_state_id", "world_state_id",
    "observer_key", "observer_body_id", "actor_observation_id",
    "privileged_observation_id", "actor_content", "privileged_content",
})
_OBS_INNER_KEYS = frozenset({
    "observer_identity", "world_line_id", "logical_step", "perception_regime",
    "visible_room_identity", "visible_entity_identities",
    "observable_state_projection",
})
_PRIV_PROJECTION_KEYS = frozenset({
    "authoritative_placements", "authoritative_lifecycle",
    "closure_visible_state_commitment",
})
_LIVE_REPORT_KEYS = frozenset({
    "live_scenario", "baseline_scenario", "seed", "fact", "live_agent",
    "status", "complete", "terminated", "decisions_requested",
    "decisions_parsed_ok", "per_code_counts", "effective_n",
    "effective_n_floor", "behavioral_departure_claimable", "per_tick",
    "first_divergence_tick", "behavioral_departure_count",
    "observability_restricted_count", "trust_matrix_delta",
    "enforcement_count_delta", "token_terminal_delta", "privileged_report",
    "actor_safe_reports", "prompt_version", "parser_version",
    "preregistered_model_id", "preregistered_model_digest", "regime",
    "regime_id", "claim_ceiling",
})
_REGIME_KEYS = frozenset({
    "model_id", "model_digest", "decoding", "backend_version",
    "seed_supported", "prompt_version", "parser_version",
    "persona_actor_version",
})


@dataclass(frozen=True)
class EvidenceLimits:
    json_bytes: int = 8 * 1024 * 1024
    jsonl_bytes: int = 64 * 1024 * 1024
    line_bytes: int = 1024 * 1024
    rows_per_stream: int = 250_000
    run_bytes: int = 256 * 1024 * 1024

    def __post_init__(self):
        values = (self.json_bytes, self.jsonl_bytes, self.line_bytes,
                  self.rows_per_stream, self.run_bytes)
        if any(type(v) is not int or v < 1 for v in values):
            refuse("invalid_limits", "evidence limits must be positive integers")
        if self.json_bytes > 256 * 1024 * 1024 or \
                self.jsonl_bytes > 256 * 1024 * 1024 or \
                self.line_bytes > 4 * 1024 * 1024 or \
                self.rows_per_stream > 1_000_000 or \
                self.run_bytes > 1024 * 1024 * 1024:
            refuse("invalid_limits", "evidence limit exceeds the absolute ceiling")

    def public(self):
        return {k: getattr(self, k) for k in
                ("json_bytes", "jsonl_bytes", "line_bytes", "rows_per_stream",
                 "run_bytes")}


@dataclass(frozen=True)
class ReplayVerification:
    state: str
    detail: str
    report_state: str = "not_applicable"

    def __post_init__(self):
        if self.state not in ("verified", "unverified", "failed"):
            refuse("invalid_replay_state", "unknown replay verification state")
        if self.report_state not in ("verified", "unverified", "failed", "not_applicable"):
            refuse("invalid_replay_state", "unknown report authentication state")


@dataclass(frozen=True)
class ValidatedRun:
    root: str
    run_dir: str
    run: Mapping[str, Any]
    closure: Mapping[str, Any]
    chain: tuple
    transitions: tuple
    observations: tuple
    activations: tuple
    file_hashes: Mapping[str, str]
    live_report: Mapping[str, Any] | None

    @property
    def run_id(self):
        return self.run["run_id"]


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


def thaw(value):
    if isinstance(value, Mapping):
        return {k: thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [thaw(v) for v in value]
    return value


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate object key {key!r}")
        out[key] = value
    return out


def _strict_json(data: bytes, where: str):
    try:
        return json.loads(
            data.decode("utf-8", "strict"), object_pairs_hook=_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite number {value}")))
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        refuse("malformed_json", f"{where} is not strict UTF-8 JSON: {str(exc)[:120]}")


def _strict_jsonl(data: bytes, where: str, limits: EvidenceLimits):
    lines = data.splitlines()
    if len(lines) > limits.rows_per_stream:
        refuse("row_limit", f"{where} exceeds the row limit")
    rows = []
    for index, line in enumerate(lines, 1):
        if not line.strip():
            refuse("blank_jsonl_row", f"{where}:{index} is blank")
        if len(line) > limits.line_bytes:
            refuse("line_limit", f"{where}:{index} exceeds the line limit")
        rows.append(_strict_json(line, f"{where}:{index}"))
    return rows


def _read_all(fd, limit, where):
    chunks, total = [], 0
    while True:
        block = os.read(fd, min(65536, limit + 1 - total))
        if not block:
            return b"".join(chunks)
        total += len(block)
        if total > limit:
            refuse("file_limit", f"{where} exceeds the file limit")
        chunks.append(block)


class RunRoot:
    """A pinned root that opens named evidence relative to directory FDs."""

    def __init__(self, root, limits=None):
        self.limits = limits or EvidenceLimits()
        try:
            self.path = Path(root).expanduser().resolve(strict=True)
        except OSError:
            refuse("invalid_root", "run root cannot be resolved")
        if not self.path.is_dir():
            refuse("invalid_root", "run root is not a directory")

    @staticmethod
    def _valid_id(run_id):
        if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
            refuse("unsafe_run_id", "run id must be one bounded ASCII component")

    def list_ids(self):
        result = []
        with os.scandir(self.path) as entries:
            for entry in entries:
                if RUN_ID_RE.fullmatch(entry.name) and \
                        entry.is_dir(follow_symlinks=False) and not entry.is_symlink():
                    result.append(entry.name)
        return sorted(result)

    def run_path(self, run_id):
        self._valid_id(run_id)
        candidate = self.path / run_id
        try:
            if candidate.is_symlink() or not candidate.is_dir():
                refuse("unsafe_run_path", "run is absent, non-directory, or a symlink")
            resolved = candidate.resolve(strict=True)
        except OSError:
            refuse("unsafe_run_path", "run cannot be resolved")
        if resolved.parent != self.path:
            refuse("path_escape", "run escapes the pinned root")
        return resolved

    def read(self, run_id, optional=()):
        self._valid_id(run_id)
        if not isinstance(optional, tuple) or not set(optional) <= set(OPTIONAL_FILES):
            refuse("unsafe_evidence_file", "optional evidence name is not allowlisted")
        directory = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        root_fd = os.open(self.path, directory)
        try:
            try:
                run_fd = os.open(run_id, directory | nofollow, dir_fd=root_fd)
            except OSError:
                refuse("unsafe_run_path", "run cannot be opened safely")
            try:
                result, total = {}, 0
                for name in REQUIRED_FILES + tuple(optional):
                    try:
                        info = os.stat(name, dir_fd=run_fd, follow_symlinks=False)
                    except FileNotFoundError:
                        if name in REQUIRED_FILES:
                            refuse("missing_evidence", f"missing {name}")
                        continue
                    if not stat.S_ISREG(info.st_mode):
                        refuse("unsafe_evidence_file", f"{name} is not regular")
                    limit = (self.limits.jsonl_bytes if name.endswith(".jsonl")
                             else self.limits.json_bytes)
                    if info.st_size > limit or total + info.st_size > self.limits.run_bytes:
                        refuse("file_limit", f"{name} exceeds configured limits")
                    try:
                        fd = os.open(name, os.O_RDONLY | nofollow, dir_fd=run_fd)
                    except OSError:
                        refuse("unsafe_evidence_file", f"{name} cannot be opened safely")
                    try:
                        opened = os.fstat(fd)
                        if not stat.S_ISREG(opened.st_mode) or opened.st_size > limit:
                            refuse("unsafe_evidence_file", f"{name} changed during safe open")
                        result[name] = _read_all(fd, limit, name)
                    finally:
                        os.close(fd)
                    total += len(result[name])
                return result
            finally:
                os.close(run_fd)
        finally:
            os.close(root_fd)


def _object(value, where):
    if not isinstance(value, dict):
        refuse("invalid_shape", f"{where} must be an object")
    return value


def _exact(value, keys, where):
    _object(value, where)
    if set(value) != set(keys):
        refuse("invalid_shape", f"{where} has an unsupported key set")


def _string(value, where):
    if not isinstance(value, str) or not value:
        refuse("invalid_type", f"{where} must be a non-empty string")
    return value


def _hash(value, where):
    _string(value, where)
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        refuse("invalid_identity", f"{where} must be 64 lowercase hex characters")
    return value


def _uint(value, where):
    if type(value) is not int or value < 0:
        refuse("invalid_type", f"{where} must be a non-negative integer")
    return value


def _record(record, record_id, content, where):
    if record.id != record_id or record.content != content:
        refuse("identity_mismatch", f"{where} identity does not re-derive")


def _validate_summary(run, run_id):
    schema = _object(run, "run.json").get("spatial_run_schema_version")
    if schema not in SUPPORTED_RUN_SCHEMAS:
        refuse("unsupported_schema", f"unsupported spatial run schema {schema!r}")
    _exact(run, _RUN_KEYS_02 | (_TREATMENT_KEYS if schema == "0.3" else set()),
           "run.json")
    if run["run_id"] != run_id:
        refuse("identity_mismatch", "run id differs from directory")
    _string(run["scenario"], "run.scenario")
    _uint(run["seed"], "run.seed")
    _uint(run["explicit_stop_position"], "run.explicit_stop_position")
    _uint(run["chain_length"], "run.chain_length")
    _uint(run["observation_count"], "run.observation_count")
    if run["chain_length"] < 1:
        refuse("invalid_run", "chain must have at least one row")
    for key in ("world_line_id", "world_line_genesis_id", "genesis_state_id",
                "topology_closure_hash", "scheduler_run_id",
                "action_script_commitment", "manifest_id",
                "terminal_scheduler_state_id", "terminal_world_state_id",
                "random_stream_id"):
        _hash(run[key], f"run.{key}")
    supported_versions = {
        "scenario_schema_version": SUPPORTED_SCENARIO_SCHEMAS,
        "spatial_schema_version": SUPPORTED_SPATIAL_SCHEMA_VERSIONS,
        "scheduler_version": SUPPORTED_SCHEDULER_VERSIONS,
        "renderer_version": frozenset(SUPPORTED_RENDERER_VERSIONS),
    }
    for key, supported in supported_versions.items():
        value = _string(run[key], f"run.{key}")
        if value not in supported:
            refuse("unsupported_schema", f"unsupported {key} {value!r}")
    if not isinstance(run["observers"], dict) or not run["observers"]:
        refuse("invalid_run", "observers must be a non-empty object")
    for key, value in run["observers"].items():
        _string(key, "observer key"); _hash(value, f"observers.{key}")
    if len(set(run["observers"].values())) != len(run["observers"]):
        refuse("invalid_run", "observer bodies must be unique")
    if not isinstance(run["instance_ids"], dict):
        refuse("invalid_run", "instance_ids must be an object")
    for key, value in run["instance_ids"].items():
        _string(key, "instance key"); _hash(value, f"instance_ids.{key}")
    if run["private_object_key"] is not None:
        _string(run["private_object_key"], "private_object_key")
    if (run["fork_position"] is None) != (run["fork_state_hash"] is None):
        refuse("invalid_run", "fork position/hash must be null together")
    if run["fork_position"] is not None:
        _uint(run["fork_position"], "fork_position"); _hash(run["fork_state_hash"], "fork_state_hash")
    prefix = run["scenario"] if schema == "0.2" else \
        f"{run['scenario']}--{run['intervention_id']}"
    if run_id != f"{prefix}--seed{run['seed']}--{run['manifest_id'][:16]}":
        refuse("identity_mismatch", "run id differs from scenario/seed/manifest")
    try:
        sr = SchedulerRun(run["world_line_id"], run["world_line_genesis_id"],
                          run["action_script_commitment"], run["explicit_stop_position"])
    except ContentRecordError as exc:
        refuse("invalid_run", str(exc))
    if sr.id != run["scheduler_run_id"]:
        refuse("identity_mismatch", "scheduler run identity does not re-derive")


def _validate_closure(closure, run):
    _exact(closure, {"bodies", "objects", "portals", "rooms"}, "closure")
    for kind in ("bodies", "objects", "rooms"):
        rows = closure[kind]
        if not isinstance(rows, list) or rows != sorted(rows) or len(rows) != len(set(rows)):
            refuse("invalid_closure", f"{kind} must be sorted and unique")
        for value in rows: _hash(value, f"closure.{kind}")
    if set(closure["bodies"]) & set(closure["objects"]):
        refuse("invalid_closure", "body/object identities overlap")
    keyed = []
    if not isinstance(closure["portals"], list):
        refuse("invalid_closure", "portals must be a list")
    for row in closure["portals"]:
        _exact(row, {"portal_instance_id", "from_room_instance_id",
                     "to_room_instance_id"}, "portal row")
        for value in row.values(): _hash(value, "portal identity")
        if row["from_room_instance_id"] not in closure["rooms"] or \
                row["to_room_instance_id"] not in closure["rooms"]:
            refuse("invalid_closure", "portal endpoint is outside closure")
        keyed.append((row["portal_instance_id"], row["from_room_instance_id"],
                      row["to_room_instance_id"]))
    if keyed != sorted(keyed) or len(keyed) != len(set(keyed)):
        refuse("invalid_closure", "portal rows must be sorted and unique")
    try:
        derived = _closure_hash(closure)
    except ContentRecordError as exc:
        refuse("invalid_closure", str(exc))
    if derived != run["topology_closure_hash"]:
        refuse("identity_mismatch", "closure commitment does not re-derive")
    if not set(run["observers"].values()) <= set(closure["bodies"]):
        refuse("invalid_closure", "observer is outside body closure")


def _validate_chain(rows, run):
    if not isinstance(rows, list) or len(rows) != run["chain_length"]:
        refuse("chain_length", "chain count differs from run.json")
    content_rows = []
    for index, row in enumerate(rows):
        _exact(row, {"scheduler_state_id", "content"}, f"chain[{index}]")
        c = _object(row["content"], f"chain[{index}].content")
        if c.get("scheduler_position") != index:
            refuse("chain_order", "chain positions are not contiguous")
        try:
            rec = SchedulerState(c.get("scheduler_run_id"), c.get("scheduler_position"),
                c.get("previous_scheduler_state_hash"), c.get("world_line_id"),
                c.get("current_world_state_hash"), c.get("round_start_state_hash"),
                c.get("round_index"), c.get("within_round_index"),
                c.get("last_outcome"), c.get("last_applied_transition_hash"))
            _record(rec, row["scheduler_state_id"], c, f"chain[{index}]")
        except (ContentRecordError, TypeError) as exc:
            refuse("invalid_chain", str(exc))
        if c["scheduler_run_id"] != run["scheduler_run_id"] or \
                c["world_line_id"] != run["world_line_id"]:
            refuse("chain_binding", "chain is bound to another run/world")
        if c["spatial_schema_version"] != run["spatial_schema_version"] or \
                c["scheduler_version"] != run["scheduler_version"]:
            refuse("chain_binding", "chain versions differ from run.json")
        previous = None if index == 0 else rows[index - 1]["scheduler_state_id"]
        if c["previous_scheduler_state_hash"] != previous:
            refuse("chain_link", "previous scheduler-state link is broken")
        content_rows.append(c)
    if content_rows[0]["current_world_state_hash"] != run["genesis_state_id"]:
        refuse("genesis_binding", "chain genesis differs from run.json")
    if rows[-1]["scheduler_state_id"] != run["terminal_scheduler_state_id"] or \
            content_rows[-1]["current_world_state_hash"] != run["terminal_world_state_id"] or \
            run["explicit_stop_position"] != len(rows) - 1:
        refuse("terminal_binding", "terminal rule/identity differs from chain")
    return content_rows


def _validate_transitions(rows, run, closure, chain_rows, chain_content):
    if not isinstance(rows, list):
        refuse("invalid_transitions", "transition stream must be a list")
    by_id = {}
    for index, row in enumerate(rows):
        _exact(row, {"transition_id", "content"}, f"transitions[{index}]")
        transition_id = _hash(row["transition_id"], f"transitions[{index}].id")
        content = _object(row["content"], f"transitions[{index}].content")
        try:
            record = LocationTransition(
                content.get("world_line_id"), content.get("logical_step"),
                content.get("prior_state_hash"), content.get("resulting_state_hash"),
                content.get("effect"), content.get("actor_body_id"),
                content.get("spatial_schema_version"),
            )
            _record(record, transition_id, content, f"transitions[{index}]")
            _validate_effect_shape(content["effect"])
            _validate_effect_closure(content["effect"], run, closure)
        except (ContentRecordError, KeyError, TypeError) as exc:
            refuse("invalid_transition", str(exc))
        if transition_id in by_id:
            refuse("duplicate_transition", "transition identities must be unique")
        if content["world_line_id"] != run["world_line_id"]:
            refuse("transition_binding", "transition is bound to another world line")
        if content["spatial_schema_version"] != run["spatial_schema_version"]:
            refuse("transition_binding", "transition spatial version differs from run.json")
        action = content["effect"]["action"]
        actor = content["actor_body_id"]
        if action in {"move", "take", "drop", "give", "put_inside", "take_out"}:
            if actor != content["effect"].get("agent_body_id"):
                refuse("transition_actor", "actor transition is not bound to its effect actor")
        elif actor is not None:
            refuse("transition_actor", "system transition must not name an actor")
        by_id[transition_id] = content

    used = []
    for position in range(1, len(chain_rows)):
        current = chain_content[position]
        transition_id = current["last_applied_transition_hash"]
        if transition_id is None:
            if current["current_world_state_hash"] != \
                    chain_content[position - 1]["current_world_state_hash"]:
                refuse("transition_gap", "a state changed without an authenticated transition")
            continue
        if transition_id not in by_id:
            refuse("transition_gap", "scheduler state references a missing transition")
        content = by_id[transition_id]
        if content["prior_state_hash"] != \
                chain_content[position - 1]["current_world_state_hash"] or \
                content["resulting_state_hash"] != current["current_world_state_hash"]:
            refuse("transition_chain", "transition endpoints do not bind adjacent states")
        used.append(transition_id)
    if len(used) != len(set(used)) or set(used) != set(by_id):
        refuse("transition_membership", "transition stream is not exactly the scheduler references")
    return by_id


def _validate_effect_closure(effect, run, closure):
    """Bind every concrete instance reference to the authenticated closure."""
    # Transition validation runs before the caller has supplied closure to this
    # helper in older call sites; the run-level world binding still applies.
    if closure is None:
        return
    bodies, objects, rooms = (set(closure["bodies"]), set(closure["objects"]),
                              set(closure["rooms"]))
    portals = {row["portal_instance_id"] for row in closure["portals"]}
    expected = {
        "agent_body_id": bodies, "recipient_agent_body_id": bodies,
        "object_instance_id": objects, "container_object_instance_id": objects,
        "room_instance_id": rooms, "from_room_instance_id": rooms,
        "to_room_instance_id": rooms, "origin_room_instance_id": rooms,
        "destination_room_instance_id": rooms, "portal_instance_id": portals,
    }
    for key, allowed in expected.items():
        if key in effect and effect[key] not in allowed:
            refuse("effect_closure", f"effect reference {key} is outside closure")
    if effect["action"] in {"spawn", "despawn", "remove"}:
        allowed = bodies if effect["entity_kind"] == "agent_body" else objects
        if effect["entity_id"] not in allowed:
            refuse("effect_closure", "effect entity is outside closure")
        if effect["action"] == "spawn":
            for key, value in effect["location"].items():
                if key in expected and value not in expected[key]:
                    refuse("effect_closure", "spawn location is outside closure")
    if effect["action"] == "move":
        arc = (effect["portal_instance_id"], effect["from_room_instance_id"],
               effect["to_room_instance_id"])
        allowed_arcs = {(row["portal_instance_id"], row["from_room_instance_id"],
                         row["to_room_instance_id"]) for row in closure["portals"]}
        if arc not in allowed_arcs:
            refuse("effect_closure", "move does not match an authenticated directed arc")


def _validate_state_closure(state, closure):
    bodies, objects = set(closure["bodies"]), set(closure["objects"])
    rooms = set(closure["rooms"])
    portals = {row["portal_instance_id"] for row in closure["portals"]}
    for row in state.content["entity_lifecycle"]:
        allowed = bodies if row["entity_kind"] == "agent_body" else objects
        if row["entity_id"] not in allowed:
            refuse("world_state_closure", "lifecycle entity kind/id differs from closure")
    for row in state.content["placements"]:
        allowed = bodies if row["entity_kind"] == "agent_body" else objects
        if row["entity_id"] not in allowed:
            refuse("world_state_closure", "placement entity kind/id differs from closure")
        loc = row["location"]
        checks = {
            "room_instance_id": rooms, "agent_body_id": bodies,
            "object_instance_id": objects, "portal_instance_id": portals,
            "origin_room_instance_id": rooms, "destination_room_instance_id": rooms,
        }
        for key, allowed_ids in checks.items():
            if key in loc and loc[key] not in allowed_ids:
                refuse("world_state_closure", "placement location reference is outside closure")


def _validate_observation_wrapper(wrapper, view, where):
    _exact(wrapper, {"schema_version", "view_kind", "content"}, where)
    if wrapper["schema_version"] != "1" or wrapper["view_kind"] != view:
        refuse("observation_schema", f"{where} has the wrong schema/view")
    content = _object(wrapper["content"], f"{where}.content")
    _exact(content, _OBS_INNER_KEYS, f"{where}.content")
    try:
        artifact = observation_artifact(view, content)
    except ContentRecordError as exc:
        refuse("invalid_observation", str(exc))
    return content, artifact


def _validate_observations(rows, run, closure, chain_rows, chain_content):
    if not isinstance(rows, list) or len(rows) != run["observation_count"]:
        refuse("observation_count", "observation count differs from run.json")
    expected = len(chain_rows) * len(run["observers"])
    if len(rows) != expected:
        refuse("observation_matrix", "observation stream is not positions x observers")
    observer_by_body = {body: key for key, body in run["observers"].items()}
    closure_portals = {(p["portal_instance_id"], p["from_room_instance_id"],
                        p["to_room_instance_id"]) for p in closure["portals"]}
    seen, state_by_position = set(), {}
    validated = []
    for index, row in enumerate(rows):
        _exact(row, _OBS_OUTER_KEYS, f"observations[{index}]")
        position = _uint(row["scheduler_position"], f"observations[{index}].position")
        if position >= len(chain_rows):
            refuse("observation_position", "observation position is outside the chain")
        body = _hash(row["observer_body_id"], f"observations[{index}].body")
        key = row["observer_key"]
        if key not in run["observers"] or run["observers"][key] != body or \
                observer_by_body.get(body) != key:
            refuse("observation_observer", "observer key/body does not bind run.json")
        matrix_key = (position, body)
        if matrix_key in seen:
            refuse("observation_matrix", "duplicate position/observer row")
        seen.add(matrix_key)
        if row["scheduler_state_id"] != chain_rows[position]["scheduler_state_id"] or \
                row["world_state_id"] != chain_content[position]["current_world_state_hash"]:
            refuse("observation_chain", "observation does not bind its chain state")

        actor, actor_record = _validate_observation_wrapper(
            row["actor_content"], "actor", f"observations[{index}].actor")
        privileged, privileged_record = _validate_observation_wrapper(
            row["privileged_content"], "privileged",
            f"observations[{index}].privileged")
        try:
            assert_actor_content_schema(actor)
        except ContentRecordError as exc:
            refuse("actor_schema", str(exc))
        if actor_record.id != row["actor_observation_id"] or \
                privileged_record.id != row["privileged_observation_id"]:
            refuse("observation_identity", "observation identity does not re-derive")
        for content in (actor, privileged):
            if content["observer_identity"] != body or \
                    content["world_line_id"] != run["world_line_id"]:
                refuse("observation_binding", "observation is bound to another observer/world")
        if actor["logical_step"] != privileged["logical_step"]:
            refuse("observation_step", "actor and privileged logical steps differ")
        if actor["perception_regime"] != privileged["perception_regime"]:
            refuse("observation_regime", "actor and privileged regimes differ")
        if actor["visible_room_identity"] != privileged["visible_room_identity"]:
            refuse("observation_visibility", "actor and privileged visible-room facts differ")

        projection = _object(privileged["observable_state_projection"],
                             f"observations[{index}].privileged.projection")
        _exact(projection, _PRIV_PROJECTION_KEYS,
               f"observations[{index}].privileged.projection")
        try:
            state = WorldState(
                run["world_line_id"], privileged["logical_step"],
                projection["authoritative_placements"],
                projection["authoritative_lifecycle"],
                run["spatial_schema_version"],
            )
        except (ContentRecordError, TypeError) as exc:
            refuse("invalid_world_state", str(exc))
        _validate_state_closure(state, closure)
        if state.id != row["world_state_id"] or \
                projection["closure_visible_state_commitment"] != state.id:
            refuse("world_state_identity", "privileged state commitment does not re-derive")
        lifecycle_ids = [entry["entity_id"]
                         for entry in projection["authoritative_lifecycle"]]
        closure_entity_ids = sorted([*closure["bodies"], *closure["objects"]])
        if lifecycle_ids != closure_entity_ids:
            refuse("world_state_closure", "privileged state is not exactly closure-scoped")
        placement_ids = [entry["entity_id"]
                         for entry in projection["authoritative_placements"]]
        if privileged["visible_entity_identities"] != placement_ids:
            refuse("observation_visibility", "privileged visible ids differ from placements")
        prior = state_by_position.setdefault(position, state.content)
        if prior != state.content:
            refuse("world_state_disagreement", "observers disagree on authoritative state")

        actor_projection = actor["observable_state_projection"]
        visible_ids = [r["entity_id"] for r in actor_projection["entities"]]
        if visible_ids != actor["visible_entity_identities"] or body not in visible_ids:
            refuse("actor_visibility", "actor entity projection/list is inconsistent")
        if not set(visible_ids) <= set(placement_ids):
            refuse("actor_visibility", "actor projection names an entity outside privileged state")
        placement_by_id = {
            entry["entity_id"]: entry
            for entry in projection["authoritative_placements"]
        }
        closure_refs = {
            "room_instance_id": set(closure["rooms"]),
            "agent_body_id": set(closure["bodies"]),
            "object_instance_id": set(closure["objects"]),
            "portal_instance_id": {
                entry["portal_instance_id"] for entry in closure["portals"]
            },
            "origin_room_instance_id": set(closure["rooms"]),
            "destination_room_instance_id": set(closure["rooms"]),
        }
        for actor_entity in actor_projection["entities"]:
            location = actor_entity["location"]
            for field, allowed in closure_refs.items():
                if field in location and location[field] not in allowed:
                    refuse("actor_state_binding",
                           "actor entity location reference is outside closure")
            authoritative = placement_by_id[actor_entity["entity_id"]]
            if actor_entity["entity_kind"] != authoritative["entity_kind"] or \
                    actor_entity["location"] != authoritative["location"]:
                refuse("actor_state_binding",
                       "actor entity kind/location differs from authenticated state")
        observer_location = placement_by_id[body]["location"]
        if observer_location["tag"] == "in_room":
            expected_visible_room = observer_location["room_instance_id"]
        elif observer_location["tag"] == "in_transit":
            expected_visible_room = None
        else:
            refuse("actor_state_binding",
                   "observer body has an unsupported authenticated location")
        if actor["visible_room_identity"] != expected_visible_room:
            refuse("actor_state_binding",
                   "visible room differs from the authenticated observer location")
        expected_portals = [
            {"portal_instance_id": portal_id, "to_room_instance_id": destination}
            for portal_id, origin, destination in sorted(closure_portals)
            if origin == expected_visible_room
        ]
        if actor_projection["portals"] != expected_portals:
            refuse("actor_state_binding",
                   "actor portals differ from the authenticated visible-room arcs")
        validated.append(row)
    if seen != {(p, body) for p in range(len(chain_rows))
                for body in run["observers"].values()}:
        refuse("observation_matrix", "observation matrix has missing cells")
    if set(state_by_position) != set(range(len(chain_rows))):
        refuse("observation_matrix", "one or more states have no observations")
    return validated, state_by_position


def _validate_activations(rows, run, closure, chain_content, transitions,
                          state_by_position):
    if not isinstance(rows, list) or len(rows) != len(chain_content) - 1:
        refuse("activation_count", "activation stream must cover every consumed position")
    bodies = set(closure["bodies"])
    validated = []
    for expected_position, row in enumerate(rows, 1):
        position = row.get("scheduler_position") if isinstance(row, dict) else None
        if position != expected_position:
            refuse("activation_order", "activation positions are not contiguous")
        current = chain_content[position]
        previous = chain_content[position - 1]
        base_keys = {"scheduler_position", "step_kind", "applied_transition_id"}
        step_kind = row.get("step_kind")
        if step_kind != current["last_outcome"] or \
                row.get("applied_transition_id") != current["last_applied_transition_hash"]:
            refuse("activation_chain", "activation row does not bind its scheduler state")
        if step_kind not in {"activate", "pass", "advance_arrival", "advance_endround"}:
            refuse("activation_kind", "unsupported scheduler step kind")
        if step_kind.startswith("advance_"):
            _exact(row, base_keys, f"activations[{expected_position - 1}]")
            if row["applied_transition_id"] not in transitions:
                refuse("activation_transition", "advance row lacks its transition")
            transition = transitions[row["applied_transition_id"]]
            if transition["effect"] != {"action": "advance_step"} or \
                    transition["actor_body_id"] is not None:
                refuse("activation_transition", "advance row is not an advance_step transition")
            validated.append(row)
            continue

        extra = {"activation_id", "activation", "candidate_universe",
                 "selected_effect", "selected_action_id"}
        _exact(row, base_keys | extra, f"activations[{expected_position - 1}]")
        activation = _object(row["activation"], "activation.content")
        try:
            record = Activation(
                activation.get("scheduler_run_id"),
                activation.get("scheduler_position"),
                activation.get("world_line_id"),
                activation.get("current_world_state_hash"),
                activation.get("round_start_state_hash"),
                activation.get("logical_step"), activation.get("round_index"),
                activation.get("within_round_index"),
                activation.get("agent_body_id"), activation.get("outcome_kind"),
                activation.get("legal_action_kinds"),
            )
            _record(record, row["activation_id"], activation,
                    f"activations[{expected_position - 1}]")
        except (ContentRecordError, KeyError, TypeError) as exc:
            refuse("invalid_activation", str(exc))
        if activation["scheduler_position"] != position or \
                activation["scheduler_run_id"] != run["scheduler_run_id"] or \
                activation["world_line_id"] != run["world_line_id"] or \
                activation["current_world_state_hash"] != previous["current_world_state_hash"] or \
                activation["round_start_state_hash"] != previous["round_start_state_hash"] or \
                activation["round_index"] != previous["round_index"] or \
                activation["within_round_index"] != previous["within_round_index"] or \
                activation["logical_step"] != state_by_position[position - 1]["logical_step"] or \
                activation["agent_body_id"] not in bodies or \
                activation["outcome_kind"] != step_kind:
            refuse("activation_binding", "activation does not bind the pre-step state")

        universe = row["candidate_universe"]
        if not isinstance(universe, list):
            refuse("candidate_universe", "candidate universe must be a list")
        action_ids, action_kinds = [], set()
        for candidate in universe:
            _exact(candidate, {"action_id", "effect"}, "candidate")
            try:
                _validate_effect_shape(candidate["effect"])
                _validate_effect_closure(candidate["effect"], run, closure)
                derived_id = canonical_effect_id(candidate["effect"])
            except (ContentRecordError, TypeError) as exc:
                refuse("candidate_effect", str(exc))
            if candidate["action_id"] != derived_id:
                refuse("candidate_identity", "candidate action id does not match its value")
            if candidate["effect"].get("agent_body_id") != activation["agent_body_id"]:
                refuse("candidate_actor", "candidate is not bound to activated actor")
            action_ids.append(derived_id)
            action_kinds.add(candidate["effect"]["action"])
        if action_ids != sorted(action_ids) or len(action_ids) != len(set(action_ids)):
            refuse("candidate_order", "candidate identities must be sorted and unique")
        if sorted(action_kinds) != activation["legal_action_kinds"]:
            refuse("legal_action_binding", "legal action kinds differ from candidate values")
        selected_id, selected_effect = row["selected_action_id"], row["selected_effect"]
        if step_kind == "pass":
            if universe or selected_id is not None or selected_effect is not None or \
                    row["applied_transition_id"] is not None:
                refuse("pass_semantics", "pass must have no candidates, selection, or transition")
        else:
            if not universe or selected_id not in action_ids or \
                    canonical_effect_id(selected_effect) != selected_id:
                refuse("selection_binding", "selected action is not a candidate value")
            transition = transitions.get(row["applied_transition_id"])
            if transition is None or transition["effect"] != selected_effect or \
                    transition["actor_body_id"] != activation["agent_body_id"]:
                refuse("selection_transition", "selected effect differs from applied transition")
        validated.append(row)
    return validated


def _validate_treatment(run):
    if run["spatial_run_schema_version"] != "0.3":
        return
    for field in _TREATMENT_KEYS:
        if not run[field]:
            refuse("treatment_binding", f"treatment field {field!r} is empty")
    try:
        from coliseum.textlab.spatial.calibration import (
            derive_execution_instance_id, intervention_record)
        intervention = intervention_record(run["intervention_id"])
        spec = intervention.canonical_spec
        bindings = run["treatment_bindings"]
        required = {"intervention_id", "control_run_id", "control_source_evidence_id",
                    "control_manifest_id", "parent_world_line_id", "fork_position",
                    "fork_state_hash", "fork_decision_id", "fork_genesis_id"}
        _exact(bindings, required, "treatment_bindings")
        _string(run["intervention_id"], "intervention_id")
        _hash(run["execution_instance_id"], "execution_instance_id")
        _exact(run["witness_ids"], {"scheduler_state_id", "scheduler_manifest_id"},
               "witness_ids")
        for value in run["witness_ids"].values():
            _hash(value, "witness identity")
        RunRoot._valid_id(bindings["control_run_id"])
        for field in ("control_source_evidence_id", "control_manifest_id",
                      "parent_world_line_id", "fork_state_hash",
                      "fork_decision_id", "fork_genesis_id"):
            _hash(bindings[field], f"treatment_bindings.{field}")
        _uint(bindings["fork_position"], "treatment_bindings.fork_position")
        if run["scenario"] != spec["scenario"] or run["seed"] != spec["seed"] or \
                bindings["intervention_id"] != run["intervention_id"] or \
                bindings["fork_position"] != spec["fork_position"] or \
                bindings["fork_state_hash"] != spec["fork_state_hash"]:
            refuse("treatment_binding", "treatment differs from its closed intervention")
        if run["witness_ids"]["scheduler_manifest_id"] != \
                bindings["control_manifest_id"]:
            refuse("treatment_binding",
                   "witness manifest differs from the bound control manifest")
        if bindings["fork_genesis_id"] != run["world_line_genesis_id"]:
            refuse("treatment_binding",
                   "fork genesis differs from the run world-line genesis")
        expected = derive_execution_instance_id(
            intervention.intervention_id, spec["scenario"], spec["seed"],
            spec["agent_key"], bindings["parent_world_line_id"],
            bindings["control_source_evidence_id"], bindings["fork_position"],
            bindings["fork_state_hash"],
        )
    except VisualizationError:
        raise
    except (ContentRecordError, KeyError, TypeError) as exc:
        refuse("treatment_binding", str(exc))
    if run["execution_instance_id"] != expected:
        refuse("treatment_binding", "execution instance identity does not re-derive")


def _validate_treatment_control(run, run_root, limits):
    """Cross-bind a treatment to its structurally validated sibling control.

    This remains structural admission, not replay authentication: the named
    control is passed through the same bounded loader and every locally
    reconstructible treatment/control equality is checked.
    """
    if run["spatial_run_schema_version"] != "0.3":
        return
    bindings = run["treatment_bindings"]
    control_run_id = bindings["control_run_id"]
    if control_run_id == run["run_id"]:
        refuse("treatment_binding", "treatment cannot name itself as its control")

    # Refuse treatment-of-treatment recursion before invoking the public loader.
    control_files = run_root.read(control_run_id)
    control_summary = _strict_json(control_files["run.json"], "control/run.json")
    if control_summary.get("spatial_run_schema_version") != "0.2":
        refuse("treatment_binding", "treatment control must be a schema-0.2 run")
    control = load_validated_run(run_root, control_run_id, limits)
    witness = run["witness_ids"]
    fork_position = bindings["fork_position"]
    if fork_position >= len(control.chain):
        refuse("treatment_binding", "fork position is outside the control chain")
    control_cursor = control.chain[fork_position]
    control_content = control_cursor["content"]
    control_binding = SpatialSourceEvidenceBinding(
        control_run_id, dict(control.file_hashes))

    expected = {
        "control scenario": (control.run["scenario"], run["scenario"]),
        "control seed": (control.run["seed"], run["seed"]),
        "control manifest": (control.run["manifest_id"],
                             bindings["control_manifest_id"]),
        "witness manifest": (witness["scheduler_manifest_id"],
                             control.run["manifest_id"]),
        "control source evidence": (control_binding.id,
                                    bindings["control_source_evidence_id"]),
        "parent world line": (bindings["parent_world_line_id"],
                              control.run["world_line_id"]),
        "control fork position": (control.run["fork_position"], fork_position),
        "control fork state": (control.run["fork_state_hash"],
                               bindings["fork_state_hash"]),
        "witness scheduler state": (witness["scheduler_state_id"],
                                    control_cursor["scheduler_state_id"]),
        "witness world state": (bindings["fork_state_hash"],
                                control_content["current_world_state_hash"]),
    }
    for label, (actual, wanted) in expected.items():
        if actual != wanted:
            refuse("treatment_binding", f"{label} does not cross-bind")


def _validate_live_report(value, run):
    if value is None:
        return None
    _exact(value, {"id", "content"}, "live_report")
    report_id = _hash(value["id"], "live_report.id")
    content = _object(value["content"], "live_report.content")
    _exact(content, _LIVE_REPORT_KEYS, "live_report.content")
    if config_hash(content) != report_id:
        refuse("live_report_identity", "live report identity does not re-derive")
    if content["baseline_scenario"] != run["scenario"] or content["seed"] != run["seed"]:
        refuse("live_report_binding", "live report is bound to another scenario/seed")
    if type(content["complete"]) is not bool or \
            type(content["behavioral_departure_claimable"]) is not bool:
        refuse("claim_integrity", "completion and claimability must be exact booleans")
    relation = {
        "incomplete": (False, False),
        "underpowered": (True, False),
        "complete": (True, True),
    }
    if content["status"] not in relation or \
            (content["complete"], content["behavioral_departure_claimable"]) != \
            relation[content["status"]]:
        refuse("claim_integrity", "live result status violates the claim ceiling")
    counts = (content["decisions_requested"], content["decisions_parsed_ok"],
              content["effective_n"], content["effective_n_floor"])
    if any(type(number) is not int or number < 0 for number in counts) or \
            content["decisions_parsed_ok"] > content["decisions_requested"] or \
            content["effective_n"] != content["decisions_parsed_ok"]:
        refuse("claim_integrity", "live report decision counts are inconsistent")
    if not isinstance(content["per_code_counts"], dict) or \
            any(not isinstance(key, str) or type(count) is not int or count < 0
                for key, count in content["per_code_counts"].items()) or \
            sum(content["per_code_counts"].values()) != content["decisions_requested"]:
        refuse("claim_integrity", "live report outcome counts are inconsistent")
    if not isinstance(content["per_tick"], list) or \
            len(content["per_tick"]) != content["decisions_requested"]:
        refuse("claim_integrity", "live report per-tick count is inconsistent")
    if content["status"] == "incomplete":
        if not isinstance(content["terminated"], dict) or not content["terminated"]:
            refuse("claim_integrity", "incomplete result requires a termination record")
    else:
        if content["terminated"] is not None:
            refuse("claim_integrity", "complete result cannot carry failure termination")
        above_floor = content["effective_n"] >= content["effective_n_floor"]
        if (content["status"] == "complete") != above_floor:
            refuse("claim_integrity", "complete/underpowered status disagrees with effective N")
    if config_hash(content["regime"]) != content["regime_id"]:
        refuse("live_report_regime", "live report regime identity does not re-derive")
    regime = _object(content["regime"], "live_report.regime")
    _exact(regime, _REGIME_KEYS, "live_report.regime")
    for field in ("model_id", "model_digest", "prompt_version", "parser_version",
                  "persona_actor_version"):
        _string(regime[field], f"live_report.regime.{field}")
    if regime["backend_version"] is not None:
        _string(regime["backend_version"], "live_report.regime.backend_version")
    if regime["seed_supported"] is not None and type(regime["seed_supported"]) is not bool:
        refuse("live_report_regime", "seed_supported must be Boolean or null")
    decoding = _object(regime["decoding"], "live_report.regime.decoding")
    _exact(decoding, {"temperature", "num_predict", "seed"},
           "live_report.regime.decoding")
    if type(decoding["temperature"]) not in (int, float) or \
            type(decoding["num_predict"]) is not int or decoding["num_predict"] < 1 or \
            type(decoding["seed"]) is not int or decoding["seed"] < 0:
        refuse("live_report_regime", "decoding values have invalid types/ranges")
    return value


def load_validated_run(root, run_id, limits=None):
    """Load one run through bounded validation without writing or replaying it."""
    run_root = root if isinstance(root, RunRoot) else RunRoot(root, limits)
    files = run_root.read(run_id, optional=("live_report.json",))
    parsed = {}
    for name in REQUIRED_FILES:
        parsed[name] = (_strict_jsonl(files[name], name, run_root.limits)
                        if name in JSONL_FILES else _strict_json(files[name], name))
    report = (_strict_json(files["live_report.json"], "live_report.json")
              if "live_report.json" in files else None)
    run = parsed["run.json"]
    closure = parsed["closure.json"]
    _validate_summary(run, run_id)
    _validate_treatment(run)
    _validate_closure(closure, run)
    chain_rows = parsed["chain.jsonl"]
    chain_content = _validate_chain(chain_rows, run)
    transitions = _validate_transitions(
        parsed["transitions.jsonl"], run, closure, chain_rows, chain_content)
    observations, state_by_position = _validate_observations(
        parsed["observations.jsonl"], run, closure, chain_rows, chain_content)
    activations = _validate_activations(
        parsed["activations.jsonl"], run, closure, chain_content, transitions,
        state_by_position)
    _validate_treatment_control(run, run_root, limits)
    live_report = _validate_live_report(report, run)
    hashes = {name: hashlib.sha256(data).hexdigest()
              for name, data in files.items() if name in REQUIRED_FILES}
    return ValidatedRun(
        root=str(run_root.path), run_dir=str(run_root.run_path(run_id)),
        run=_freeze(run), closure=_freeze(closure), chain=_freeze(chain_rows),
        transitions=_freeze(parsed["transitions.jsonl"]),
        observations=_freeze(observations), activations=_freeze(activations),
        file_hashes=_freeze(hashes), live_report=_freeze(live_report),
    )


def verify_replay(validated_run, scratch_root=None):
    """Run an existing provider-free byte replay gate; never contacts a model."""
    if not isinstance(validated_run, ValidatedRun):
        refuse("invalid_run", "verify_replay requires a ValidatedRun")
    try:
        if validated_run.live_report is not None:
            from coliseum.textlab.society.live import replay_live_persona_pilot
            ok, detail = replay_live_persona_pilot(
                validated_run.run_dir, scratch_root=scratch_root)
            detail = f"{detail}; live_report.json is outside this replay gate"
            return ReplayVerification("verified" if ok else "failed", str(detail)[:400],
                                      "unverified" if ok else "failed")
        else:
            ok, detail = replay_spatial_run(
                validated_run.run_id, out_root=validated_run.root,
                scratch_root=scratch_root)
    except Exception as exc:  # the public boundary converts internals to a closed state
        return ReplayVerification("failed", f"replay refused: {type(exc).__name__}: {str(exc)[:160]}")
    return ReplayVerification("verified" if ok else "failed", str(detail)[:400])
