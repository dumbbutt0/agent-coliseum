"""The scenario runner: state -> reflex + plan -> resolve -> log, until "end".

Determinism contract (the Rung-0 gate for this harness):
  - run_id is a pure function of (scenario, variant, agent, seed) — no clock, no pid.
  - decision events are written with t=0.0; the ONLY wall-clock fields in a run
    directory are run.json's started_at/finished_at (excluded from the byte gate).
  - scripted agents report fixed 0.0 latencies; measured latencies begin with LLM
    agents, where nondeterminism is expected and the gate doesn't apply.
Same seed + scripted agent => byte-identical decisions.jsonl on every machine.
"""
from __future__ import annotations

import datetime
import json
import os
import subprocess
from dataclasses import dataclass

from ..logging_substrate import RunLogger
from ..seeding import seed_everything
from .agents import AgentInterface, make_agent
from .scenario import load_scenario, pick_variant
from .schema import (DecisionNode, EventDelta, MemoryUpdate, Outcome, Run,
                     SchemaError, apply_delta, canonical_json, config_hash)

# Ruling 1 (2026-07-10): personas RECOMMEND (reflex + plan, both preserved);
# the harness ARBITRATES and records which named rule selected the final action.
# A rule maps (reflex, planner, decision_point) -> the winning Choice.
ARBITRATION_RULES = {
    # deliberation wins whenever it was consulted (MVP default, Day-1 behavior)
    "planner_priority": lambda reflex, planner, dp: planner,
    # under maximal time pressure the fast system acts before deliberation lands
    "reflex_under_time_pressure": lambda reflex, planner, dp: (
        reflex if dp.time_pressure >= 3 else planner),
}


class DecisionLog(RunLogger):
    """Append-only decision log at logs/runs/<run_id>/decisions.jsonl, t pinned to 0.0
    (wall-clock would break byte-identical replay; humans get timestamps in run.json)."""

    def __init__(self, run_id: str, out_root: str = "logs/runs"):
        run_dir = os.path.join(out_root, run_id)
        os.makedirs(run_dir, exist_ok=True)
        self.run_id = run_id
        self.run_dir = run_dir
        self.path = os.path.join(run_dir, "decisions.jsonl")
        self._seq = 0
        self._fh = open(self.path, "w", encoding="utf-8")

    def log(self, kind: str, **data):
        ev = {"run_id": self.run_id, "seq": self._seq, "kind": kind, "t": 0.0, "data": data}
        self._fh.write(canonical_json(ev) + "\n")
        self._fh.flush()
        self._seq += 1
        return ev


@dataclass
class RunResult:
    run_id: str
    run_dir: str
    final_actions: list          # action_id per decision point, in order
    run: Run


def _code_version() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=5,
                              cwd=os.path.dirname(os.path.abspath(__file__))
                              ).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def run_scenario(scenario_path: str, agent_spec: str, seed: int,
                 out_root: str = "logs/runs", parent_id: str | None = None,
                 arbitration: str = "planner_priority",
                 replay_from: str | None = None) -> RunResult:
    """`replay_from`: path to a prior LLM run dir — the agent serves that run's
    captured raw outputs (and latencies) instead of calling the backend, so the
    replayed run is byte-identical to the live original (the LLM determinism tier)."""
    if arbitration not in ARBITRATION_RULES:
        raise SchemaError(f"unknown arbitration rule {arbitration!r} (have {sorted(ARBITRATION_RULES)})")
    arbitrate = ARBITRATION_RULES[arbitration]
    scenario = load_scenario(scenario_path)
    agent: AgentInterface = make_agent(agent_spec)
    if replay_from is not None:
        cap_path = os.path.join(replay_from, "captures.jsonl")
        if not hasattr(agent, "load_replay"):
            raise SchemaError(f"replay_from only applies to llm agents, not {agent_spec!r}")
        if not os.path.exists(cap_path):
            raise SchemaError(f"no captures to replay at {cap_path}")
        with open(cap_path, encoding="utf-8") as fh:
            agent.load_replay([json.loads(line) for line in fh if line.strip()])
    seed_everything(seed)
    variant = pick_variant(scenario, seed)

    run_hash = config_hash({"scenario": scenario.raw, "agent": agent.spec_dict(),
                            "arbitration": arbitration})
    run_id = ".".join([scenario.scenario_id, variant["variant_id"],
                       agent_spec.replace(":", "-"), f"s{seed}", run_hash[:8]])
    log = DecisionLog(run_id, out_root)
    run = Run(run_id=run_id, parent_id=parent_id, seed=seed,
              scenario_id=scenario.scenario_id, variant_id=variant["variant_id"],
              agent_id=agent.agent_id, config_hash=run_hash,
              started_at=_now(), code_version=_code_version(),
              arbitration=arbitration)

    dps = {dp.dp_id: dp for dp in scenario.decision_points}
    state = dict(scenario.initial_state)
    pending = []                 # [{due, narrative, state_delta}] — deferred consequences
    final_actions = []
    timestep = 0
    dp_id = scenario.decision_points[0].dp_id

    with log:
        while dp_id != "end":
            dp = dps[dp_id]

            # deferred consequences land before the agent sees the state — each one
            # logged as its own event_delta (ruling 2: nothing mutates state off-record)
            matured = [c for c in pending if c["due"] <= timestep]
            pending = [c for c in pending if c["due"] > timestep]
            recent_events = []
            for c in matured:
                ops = c.get("state_delta", [])
                state = apply_delta(state, ops)
                log.log("event_delta", **EventDelta(
                    run_id=run_id, timestep=timestep, source="world",
                    state_delta=ops, narrative=c.get("narrative", "")).to_record())
                if c.get("narrative"):
                    recent_events.append(c["narrative"])

            narrative = variant["decision_texts"][dp.dp_id]
            if timestep == 0 and variant.get("intro"):
                narrative = variant["intro"] + "\n\n" + narrative
            state_before = {**state, "narrative": narrative, "dp_id": dp.dp_id,
                            "recent_events": recent_events, "facts": dp.facts,
                            "authority_pressure": dp.authority_pressure,
                            "risk_level": dp.risk_level, "time_pressure": dp.time_pressure}
            actions = [scenario.actions[aid] for aid in dp.available_actions]

            reflex = agent.reflex(state_before, actions)
            planner = agent.plan(state_before, actions)   # consulted at every dp in MVP
            final = arbitrate(reflex, planner, dp)

            rule = scenario.outcome_rules[f"{dp.dp_id}/{final.action_id}"]
            delta_ops = rule.get("state_delta", [])
            state_after = apply_delta(state, delta_ops)   # derived snapshot; ops are the truth
            for cons in rule.get("consequences_deferred", []):
                pending.append({"due": timestep + cons["after"],
                                "narrative": cons.get("narrative", ""),
                                "state_delta": cons.get("state_delta", {})})
            memory = f"[t{timestep}] {rule.get('narrative', '')}".strip()

            outcome = Outcome(run_id=run_id, timestep=timestep, action_id=final.action_id,
                              state_delta=delta_ops,
                              narrative=rule.get("narrative", ""),
                              consequences_deferred=rule.get("consequences_deferred", []))
            node = DecisionNode(
                run_id=run_id, agent_id=agent.agent_id, scenario_id=scenario.scenario_id,
                timestep=timestep, state_before=state_before,
                available_actions=list(dp.available_actions),
                reflex_choice=reflex.to_dict(), planner_choice=planner.to_dict(),
                final_action=final.action_id, confidence=final.confidence,
                reasoning_summary=final.reasoning_summary,
                moral_tags=list(scenario.actions[final.action_id].moral_tags),
                authority_pressure=dp.authority_pressure, risk_level=dp.risk_level,
                reward_expected=final.reward_expected,
                outcome={"narrative": outcome.narrative, "state_delta": outcome.state_delta},
                state_after=state_after, memory_update=memory,
                # ruling 2 (Day 3): latency is LOG-ONLY behavioral evidence — recorded
                # here, never part of the lineage hash (scripted agents report 0.0)
                reflex_latency_ms=reflex.meta.get("latency_ms", 0.0),
                planner_latency_ms=planner.meta.get("latency_ms", 0.0),
                planner_consulted=True,
                arbitration_rule=arbitration, dp_id=dp.dp_id)

            log.log("decision_node", **node.to_record())
            log.log("outcome", **outcome.to_record())
            log.log("memory_update",
                    **MemoryUpdate(run_id=run_id, timestep=timestep, summary=memory).to_record())

            state = state_after
            final_actions.append(final.action_id)
            timestep += 1
            dp_id = rule.get("next", dp.next_default)

    run.finished_at = _now()
    run.status = "completed"
    # live LLM calls -> captures.jsonl, the replay substrate (absent for scripted/replayed runs)
    if getattr(agent, "captures", None):
        with open(os.path.join(log.run_dir, "captures.jsonl"), "w", encoding="utf-8") as fh:
            for cap in agent.captures:
                fh.write(canonical_json(cap) + "\n")
    with open(os.path.join(log.run_dir, "run.json"), "w", encoding="utf-8") as fh:
        json.dump(run.to_record(), fh, indent=2, sort_keys=True)
        fh.write("\n")
    return RunResult(run_id=run_id, run_dir=log.run_dir, final_actions=final_actions, run=run)
