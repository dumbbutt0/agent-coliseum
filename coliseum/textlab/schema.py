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

# Day-5 stochastic-readiness versions (owner amendment 2): the regime derivation
# itself is versioned so its semantics can never silently change.
REGIME_SCHEMA_VERSION = "1"
# v2 (2026-07-10 full audit): behavioral_config gains interaction (mode + history
# versions), runner behavioral version, and backend_version/effective_think_mode in
# the agent spec. Pre-v2 runs keep their stored hashes; v2 runs can never pool with
# them even in independent mode — the schema version is itself a behavioral claim.
BEHAVIORAL_CONFIG_SCHEMA_VERSION = "2"
# v2 (audit item 5): twin pair cells key on BOTH full scenario hashes — two
# revisions of a primary can never pool against one control.
TWIN_MAPPING_VERSION = "2"

# Audit ruling (2026-07-10): TextLab supports two experimental modes that must
# never pool. independent_vignettes = each decision prompt stands alone (all
# pre-audit evidence); sequential_history = later prompts carry a canonical
# agent-visible history of prior final actions and visible outcomes — REQUIRED
# for any claim about remembered/multi-act behavior.
INTERACTION_MODES = ("independent_vignettes", "sequential_history")
HISTORY_SCHEMA_VERSION = "1"        # structure of a history entry
OBSERVATION_POLICY_VERSION = "1"    # v1 = narrative-only: final action + outcome
                                    # narrative; no numeric/hidden state, no moral
                                    # tags, no metrics, no evaluator labels
# bump on ANY behavioral change to the runner loop (arbitration semantics have
# their own version; this covers ordering, state threading, history assembly)
RUNNER_BEHAVIORAL_VERSION = "1"

# A point in a scenario is one of exactly two kinds (M8 Phase 2). "decision" is the
# default and the v0.1 behavior: the agent chooses among >= 2 actions. "exposure"
# delivers a world event with exactly ONE legal action, so the agent-visible history
# it produces is a function of the world alone — required for an "identical except
# order" A/B history to hold by construction rather than by assumption.
POINT_KINDS = ("decision", "exposure")

DEFAULT_SAMPLING = {"mode": "deterministic", "temperature": 0}
# Every decoder control that shapes the output distribution (audit b-002
# finding f0). num_ctx (effective context length) and stop join the sampler
# knobs so that a control left implicit — falling back to a backend default —
# can no longer let two hosts with different effective context lengths pool
# under one agent_regime_id. A key enters a run's lineage only when it is
# PRESENT in that run's sampling dict, so scripted/mock runs whose sampling
# never carries these keys are byte-unchanged.
DECODING_KEYS = ("temperature", "top_p", "top_k", "repeat_penalty",
                 "num_ctx", "stop")


class SchemaError(ValueError):
    """A record or scenario definition violates the schema."""


def validate_sampling(sampling: dict, sampler_seed) -> dict:
    """Sampling config + sampler_seed coherence. Deterministic = temp 0, no sampler
    seed; stochastic = temp > 0 AND an explicit integer sampler_seed (replicates
    must be identifiable — no anonymous randomness)."""
    s = dict(DEFAULT_SAMPLING if sampling is None else sampling)
    mode = s.get("mode")
    if mode not in ("deterministic", "stochastic"):
        raise SchemaError(f"sampling mode must be deterministic|stochastic, got {mode!r}")
    temp = s.get("temperature", 0)
    if not isinstance(temp, (int, float)) or isinstance(temp, bool) or temp < 0:
        raise SchemaError(f"temperature must be a number >= 0, got {temp!r}")
    if mode == "deterministic":
        if temp != 0:
            raise SchemaError("deterministic sampling requires temperature 0")
        if sampler_seed is not None:
            raise SchemaError("sampler_seed is meaningless for deterministic sampling")
    else:
        if temp <= 0:
            raise SchemaError("stochastic sampling requires temperature > 0")
        if not isinstance(sampler_seed, int) or isinstance(sampler_seed, bool):
            raise SchemaError("stochastic sampling requires an explicit integer sampler_seed")
    # b-002 finding f0: the added decoder controls are typed, so a frozen value
    # cannot be substituted for an ill-typed one that would still hash cleanly.
    for k in ("top_p", "repeat_penalty"):
        if k in s:
            v = s[k]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
                raise SchemaError(f"{k} must be a number >= 0, got {v!r}")
    if "top_k" in s:
        v = s["top_k"]
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise SchemaError(f"top_k must be a non-negative int, got {v!r}")
    if "num_ctx" in s:
        v = s["num_ctx"]
        if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
            raise SchemaError(f"num_ctx must be a positive int (the effective "
                              f"context length), got {v!r}")
    if "stop" in s:
        v = s["stop"]
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise SchemaError(f"stop must be a list of strings, got {v!r}")
    unknown = set(s) - {"mode"} - set(DECODING_KEYS)
    if unknown:
        raise SchemaError(f"unknown sampling keys: {sorted(unknown)}")
    return s


def build_behavioral_config(scenario_id: str, scenario_hash: str, agent_spec: dict,
                            arbitration: str, arbitration_version: str,
                            sampling: dict,
                            interaction_mode: str = "independent_vignettes",
                            history_template_version: str = "",
                            history_template_hash: str = "") -> dict:
    """The ONE canonical object the comparison regime derives from (amendment 2).
    Everything that fixes model behavior lives here; replicate dimensions
    (sampler_seed, scenario_seed, attempt) never do.

    v2: `interaction` declares the experimental mode; sequential mode also pins the
    history schema/policy/template so a history-rendering change is a new regime.
    Independent mode deliberately omits the history versions — bumping them must
    not churn regimes whose prompts never contain a history block."""
    if interaction_mode not in INTERACTION_MODES:
        raise SchemaError(f"unknown interaction_mode {interaction_mode!r} (want {INTERACTION_MODES})")
    interaction = {"mode": interaction_mode}
    if interaction_mode == "sequential_history":
        interaction.update({"history_schema_version": HISTORY_SCHEMA_VERSION,
                            "observation_policy_version": OBSERVATION_POLICY_VERSION,
                            "history_template_version": history_template_version,
                            "history_template_hash": history_template_hash})
    return {
        "regime_schema_version": REGIME_SCHEMA_VERSION,
        "behavioral_config_schema_version": BEHAVIORAL_CONFIG_SCHEMA_VERSION,
        "interaction": interaction,
        "runner": {"behavioral_version": RUNNER_BEHAVIORAL_VERSION},
        "scenario": {"scenario_id": scenario_id, "scenario_hash": scenario_hash},
        "agent": dict(agent_spec),
        "decoding": {"sampling_mode": sampling["mode"],
                     **{k: sampling[k] for k in DECODING_KEYS if k in sampling}},
        "arbitration": {"rule": arbitration, "version": arbitration_version},
    }


def regime_hashes(behavioral_config: dict) -> tuple:
    """(comparison_regime_id, agent_regime_id) — FULL sha256 hashes (amendment 1:
    full hashes are the source of truth; prefixes are display-only)."""
    comparison = config_hash(behavioral_config)
    agent_side = config_hash({k: v for k, v in behavioral_config.items() if k != "scenario"})
    return comparison, agent_side


def canonical_json(obj) -> str:
    """Stable serialization: sorted keys, no whitespace, finite numbers only
    (allow_nan=False — NaN/Infinity must be caught upstream as parse failures,
    never serialized; Codex finding #5). The hashing substrate."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


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
    # ruling 2 (2026-07-10): model identity + reportability. Scripted runs are
    # reportable by definition (digest_status "n/a"); LLM runs require a pinned digest.
    llm_info: dict = field(default_factory=dict)
    reportable: bool = True
    digest_status: str = "n/a"   # "ok" | "missing" | "n/a"
    # Day-4 hardening (Codex findings #2/#3/#6/#9), all additive:
    attempt: int = 0             # live LLM attempt number; 0 = scripted/replay
    agent_config: dict = field(default_factory=dict)   # the EXACT spec_dict that was hashed
    scenario_hash: str = ""      # behavioral-subset hash of the scenario
    control_of: str = ""         # twin wiring persisted in provenance (aggregate reads logs only)
    # Day-5 stochastic readiness (pre-flight audit), all additive:
    behavioral_config: dict = field(default_factory=dict)   # THE canonical regime object
    comparison_regime_id: str = ""    # FULL hash of behavioral_config (prefixes display-only)
    agent_regime_id: str = ""         # FULL hash, scenario block excluded (twin pairing)
    scenario_seed: int | None = None  # = seed; selects the paraphrase variant
    sampler_seed: int | None = None   # backend sampling replicate (stochastic only)
    sampling: dict = field(default_factory=lambda: dict(DEFAULT_SAMPLING))
    backend_seed_supported: bool | None = None   # None = not applicable / not probed
    stochastic_reportable: bool = False
    stochastic_exclusion_reasons: list = field(default_factory=list)
    # Full-audit ruling (2026-07-10), additive: which experimental mode produced this
    # evidence. Legacy runs without the field are independent_vignettes by
    # construction (they never received history) — labeled at read time, never
    # silently reinterpreted as sequential.
    interaction_mode: str = "independent_vignettes"

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
    # M8 Phase 2 (additive, default preserves v0.1 behavior byte-for-byte): a point
    # is either a DECISION (the agent chooses; >= 2 actions, audit 000886) or an
    # EXPOSURE (the world delivers an event and the agent has no choice; exactly 1
    # action). An exposure point is honestly NOT a decision — it is named so rather
    # than smuggled in as a degenerate one-action decision, which would weaken the
    # >= 2 invariant instead of narrowing its domain.
    kind: str = "decision"                  # "decision" | "exposure"

    def __post_init__(self):
        _check_level(self.authority_pressure, "authority_pressure")
        _check_level(self.risk_level, "risk_level")
        _check_level(self.time_pressure, "time_pressure")
        _require(self.kind in POINT_KINDS,
                 f"{self.dp_id}: unknown point kind {self.kind!r} (want {POINT_KINDS})")
        if self.kind == "exposure":
            # mutually exclusive with `decision`, not a loophole around it: an
            # exposure point that offered a choice would BE a decision.
            _require(len(self.available_actions) == 1,
                     f"{self.dp_id}: an exposure point needs exactly 1 action")
        else:
            _require(len(self.available_actions) >= 2, f"{self.dp_id}: a decision needs >=2 actions")

    def is_exposure(self) -> bool:
        """True iff this point carries no agent choice (see POINT_KINDS)."""
        return self.kind == "exposure"


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

    BEHAVIORAL_KEYS = ("scenario_id", "initial_state", "actions",
                       "decision_points", "variants", "outcome_rules")

    def behavioral_dict(self) -> dict:
        """The model-facing subset that enters lineage hashes (Codex finding #9):
        descriptive metadata (purpose, metrics_captured, archetype, control_of,
        comments) must not churn behavioral lineage — only content the agent can
        see or that changes outcomes belongs here.

        control_of stays OUT of this hash by design; its identity is instead
        revision-bound at aggregation (metrics.aggregate, audit blocker 2):
        the binding key is (scenario_id, scenario_hash, control_of) and
        conflicting control_of for one behavioral identity fails loudly."""
        return {k: self.raw[k] for k in self.BEHAVIORAL_KEYS if k in self.raw}

    def behavioral_hash(self) -> str:
        return config_hash(self.behavioral_dict())


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
    arbitration_winner: str = "planner"          # "reflex"|"planner"|"fallback" — WHICH pass won
                                                 # (never inferred from action equality; finding #4)
    history_prompt_hash: str = ""                # sequential mode only: hash of the structured
                                                 # history that entered this decision's prompts

    def __post_init__(self):
        _require(0.0 <= self.confidence <= 1.0, f"confidence must be in 0..1, got {self.confidence}")
        _check_level(self.authority_pressure, "authority_pressure")
        _check_level(self.risk_level, "risk_level")
        _require(self.final_action in [a for a in self.available_actions],
                 f"final_action {self.final_action!r} not in available_actions")

    def to_record(self) -> dict:
        rec = {"record_type": "decision_node", **asdict(self)}
        # emitted ONLY in sequential mode: independent-mode and legacy decision logs
        # must stay byte-identical under replay (the field would break the byte gate)
        if not self.history_prompt_hash:
            rec.pop("history_prompt_hash")
        return rec


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
