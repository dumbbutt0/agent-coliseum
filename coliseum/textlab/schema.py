"""Record types for the textlab — every JSONL line and manifest field is defined here.

JSONL records carry a `record_type` discriminator. The DecisionNode is the core record:
one per decision point per run, holding BOTH the reflex and the planner choice (the
fast/slow prerequisite: temporal-dissociation reads stay computable after the fact).

Determinism contract: `run_id` and `config_hash` are pure functions of their inputs —
no wall-clock, no randomness — so the same (scenario, agent, seed) always names and
produces the same run.

SCHEMA v0.1 IS FROZEN (owner ruling, 2026-07-10): changes may only ADD fields with
defaults; renaming/removing/retyping a field requires bumping SCHEMA_VERSION.
Two rulings are baked in:
  1. Arbitration — reflex, planner, and final action are separate forever; every
     DecisionNode records the `arbitration_rule` that selected the final action.
  2. Delta state — explicit delta ops are the source of truth; absolute state
     (`state_after`) is a derived reconstruction layer, recomputable by folding
     `initial_state` through every op in the log.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict


SCHEMA_VERSION = "0.1"


class SchemaError(ValueError):
    """A record or scenario definition violates the schema."""


def canonical_json(obj) -> str:
    """Stable serialization: sorted keys, no whitespace. The hashing substrate."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def config_hash(obj) -> str:
    """sha256 of the canonical JSON of `obj` — the run-lineage fingerprint."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def _require(cond: bool, msg: str):
    if not cond:
        raise SchemaError(msg)


def _check_level(value, name: str):
    _require(isinstance(value, int) and 0 <= value <= 3, f"{name} must be an int in 0..3, got {value!r}")


# ------------------------------------------------------------------ delta ops
# Ruling 2 (2026-07-10): every state change is an explicit op; prose never
# secretly mutates the world. Ops: {"field": str, "op": "set"|"add", "value": num|str|bool}

DELTA_OPS = ("set", "add")


def validate_delta(ops, where: str = "state_delta"):
    _require(isinstance(ops, list), f"{where} must be a LIST of delta ops, got {type(ops).__name__}")
    for i, op in enumerate(ops):
        _require(isinstance(op, dict) and {"field", "op", "value"} <= set(op),
                 f"{where}[{i}] needs field/op/value, got {op!r}")
        _require(op["op"] in DELTA_OPS, f"{where}[{i}]: unknown op {op['op']!r} (want {DELTA_OPS})")
        if op["op"] == "add":
            _require(isinstance(op["value"], (int, float)) and not isinstance(op["value"], bool),
                     f"{where}[{i}]: 'add' needs a numeric value, got {op['value']!r}")
    return ops


def apply_delta(state: dict, ops: list) -> dict:
    """Fold delta ops into a NEW state dict (the reconstruction layer)."""
    out = dict(state)
    for op in validate_delta(ops):
        if op["op"] == "set":
            out[op["field"]] = op["value"]
        else:  # add
            base = out.get(op["field"], 0)
            _require(isinstance(base, (int, float)) and not isinstance(base, bool),
                     f"cannot 'add' to non-numeric state field {op['field']!r} = {base!r}")
            out[op["field"]] = base + op["value"]
    return out


# ---------------------------------------------------------------- agents & runs

@dataclass
class AgentSpec:
    """Who decided. `constitution` is the honest 'morals input' (system prompt / values)."""
    agent_id: str
    kind: str                    # "scripted" | "ollama" | "api"
    model: str = ""              # model name for llm kinds, "" for scripted
    persona_id: str = ""         # scripted only
    constitution: str = ""
    config_hash: str = ""

    def __post_init__(self):
        _require(self.kind in ("scripted", "ollama", "api"), f"unknown agent kind {self.kind!r}")

    def to_record(self) -> dict:
        return {"record_type": "agent", **asdict(self)}


@dataclass
class Run:
    """The run manifest (`run.json`). Timestamps are the ONLY wall-clock fields in a run
    directory — the determinism gate compares run.json minus these two fields."""
    run_id: str
    parent_id: str | None
    seed: int
    scenario_id: str
    variant_id: str
    agent_id: str
    config_hash: str
    started_at: str = ""
    finished_at: str = ""
    status: str = "running"      # "running" | "completed" | "failed"
    metrics: dict = field(default_factory=dict)   # RESERVED — post-hoc metrics live in derived/, never rewritten here
    code_version: str = "unknown"
    schema_version: str = SCHEMA_VERSION
    arbitration: str = "planner_priority"

    def to_record(self) -> dict:
        return {"record_type": "run", **asdict(self)}


# ---------------------------------------------------------------- scenario pieces

@dataclass
class Action:
    action_id: str
    label: str                   # agent-facing text (contamination-linted)
    moral_tags: list = field(default_factory=list)
    costs: dict = field(default_factory=dict)
    visible_reward: float = 0.0
    hidden_effects: dict = field(default_factory=dict)   # world-state changes the agent isn't told

    def to_record(self) -> dict:
        return {"record_type": "action", **asdict(self)}


@dataclass
class DecisionPoint:
    dp_id: str
    available_actions: list                 # action_ids
    authority_pressure: int = 0             # 0..3
    risk_level: int = 0                     # 0..3
    time_pressure: int = 0                  # 0..3
    facts: dict = field(default_factory=dict)   # ground truth the personas/metrics key on
    next_default: str = "end"               # fallback when an outcome rule has no `next`

    def __post_init__(self):
        _check_level(self.authority_pressure, "authority_pressure")
        _check_level(self.risk_level, "risk_level")
        _check_level(self.time_pressure, "time_pressure")
        _require(len(self.available_actions) >= 2, f"{self.dp_id}: a decision needs >=2 actions")


@dataclass
class Scenario:
    """A fully validated scenario template. Built only via `scenario.load_scenario` —
    `raw` keeps the exact YAML dict so config_hash covers the whole definition."""
    scenario_id: str
    archetype: str               # internal ID, never agent-facing
    purpose: str
    variants: list               # [{variant_id, intro, decision_texts: {dp_id: text}}]
    initial_state: dict
    roles: dict
    actions: dict                # action_id -> Action
    decision_points: list        # ordered DecisionPoints; first is the entry point
    outcome_rules: dict          # "dp_id/action_id" -> {state_delta, narrative, consequences_deferred, next}
    metrics_captured: list = field(default_factory=list)
    control_of: str = ""         # scenario_id this is a control twin of ("" = primary)
    raw: dict = field(default_factory=dict, repr=False)


# ---------------------------------------------------------------- per-step records

@dataclass
class DecisionNode:
    """The core record: one per decision point per run. Both passes logged."""
    run_id: str
    agent_id: str
    scenario_id: str
    timestep: int
    state_before: dict
    available_actions: list
    reflex_choice: dict          # Choice.to_dict()
    planner_choice: dict
    final_action: str            # action_id
    confidence: float            # agent-reported, 0..1, from the pass that won
    reasoning_summary: str
    moral_tags: list             # tags of the final action
    authority_pressure: int
    risk_level: int
    reward_expected: float       # agent-stated
    outcome: dict                # {narrative, state_delta: [ops]}
    state_after: dict            # DERIVED snapshot (fold of initial_state + all ops) — convenience, not truth
    memory_update: str
    reflex_latency_ms: float
    planner_latency_ms: float
    planner_consulted: bool
    arbitration_rule: str = "planner_priority"   # ruling 1: WHY final_action won
    dp_id: str = ""                              # which decision point (v0.1 additive)

    def __post_init__(self):
        _require(0.0 <= self.confidence <= 1.0, f"confidence must be in 0..1, got {self.confidence}")
        _check_level(self.authority_pressure, "authority_pressure")
        _check_level(self.risk_level, "risk_level")
        _require(self.final_action in [a for a in self.available_actions],
                 f"final_action {self.final_action!r} not in available_actions")

    def to_record(self) -> dict:
        return {"record_type": "decision_node", **asdict(self)}


@dataclass
class Outcome:
    run_id: str
    timestep: int
    action_id: str
    state_delta: list            # explicit delta ops — the truth layer (ruling 2)
    narrative: str               # agent-facing result text (contamination-linted)
    consequences_deferred: list = field(default_factory=list)  # [{after, narrative, state_delta: [ops]}]

    def __post_init__(self):
        validate_delta(self.state_delta, "Outcome.state_delta")

    def to_record(self) -> dict:
        return {"record_type": "outcome", **asdict(self)}


@dataclass
class EventDelta:
    """A world-originated state change (e.g. a matured deferred consequence) —
    logged as its own event so nothing mutates state outside the record stream."""
    run_id: str
    timestep: int
    source: str                  # "world" | an actor/role name
    state_delta: list            # explicit delta ops
    narrative: str = ""

    def __post_init__(self):
        validate_delta(self.state_delta, "EventDelta.state_delta")

    def to_record(self) -> dict:
        return {"record_type": "event_delta", **asdict(self)}


@dataclass
class MemoryUpdate:
    run_id: str
    timestep: int
    summary: str                 # what the agent carries forward
    author: str = "system"       # "agent" | "system"

    def __post_init__(self):
        _require(self.author in ("agent", "system"), f"unknown memory author {self.author!r}")

    def to_record(self) -> dict:
        return {"record_type": "memory_update", **asdict(self)}


@dataclass
class MetricReport:
    """Derived, regenerable, never fed back into a run (measure, never reward)."""
    report_id: str
    run_ids: list
    scenario_id: str
    metrics: dict                # name -> {"value": float, "n": int}
    seeds: list
    variant_spread: dict = field(default_factory=dict)  # metric -> per-variant values (contamination sanity)
    markdown_summary: str = ""

    def to_record(self) -> dict:
        return {"record_type": "metric_report", **asdict(self)}


RECORD_TYPES = {
    "agent": AgentSpec, "run": Run, "action": Action, "decision_node": DecisionNode,
    "outcome": Outcome, "event_delta": EventDelta, "memory_update": MemoryUpdate,
    "metric_report": MetricReport,
}


def from_record(rec: dict):
    """Rebuild a dataclass from a JSONL record dict (round-trip partner of to_record)."""
    kind = rec.get("record_type")
    _require(kind in RECORD_TYPES, f"unknown record_type {kind!r}")
    body = {k: v for k, v in rec.items() if k != "record_type"}
    return RECORD_TYPES[kind](**body)
