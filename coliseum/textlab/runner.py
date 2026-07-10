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

import hashlib
import urllib.parse

from ..logging_substrate import RunLogger
from ..seeding import seed_everything
from .agents import (HISTORY_TEMPLATE_HASH, HISTORY_TEMPLATE_VERSION,
                     AgentInterface, LLMAgent, agent_from_manifest, make_agent)
from .scenario import load_scenario, pick_variant, scenario_from_snapshot
from .schema import (INTERACTION_MODES, DecisionNode, EventDelta, MemoryUpdate,
                     Outcome, Run, SchemaError, apply_delta,
                     build_behavioral_config, canonical_json, config_hash,
                     regime_hashes, validate_sampling)

# Ruling 1 (2026-07-10): personas RECOMMEND (reflex + plan, both preserved);
# the harness ARBITRATES and records which named rule selected the final action.
# A rule maps (reflex, planner, decision_point) -> (winning pass NAME, Choice) —
# the name is recorded on the node so metrics never infer the winner from action
# equality (Codex finding #4).
ARBITRATION_RULES = {
    # deliberation wins whenever it was consulted (MVP default, Day-1 behavior)
    "planner_priority": lambda reflex, planner, dp: ("planner", planner),
    # under maximal time pressure the fast system acts before deliberation lands
    "reflex_under_time_pressure": lambda reflex, planner, dp: (
        ("reflex", reflex) if dp.time_pressure >= 3 else ("planner", planner)),
}
# bump on any change to arbitration semantics — it's a lineage input (finding #9)
ARBITRATION_VERSION = "2"


class DecisionLog(RunLogger):
    """Append-only decision log at <run_dir>/decisions.jsonl, t pinned to 0.0
    (wall-clock would break byte-identical replay; humans get timestamps in run.json).
    Directory allocation/collision policy lives in the runner (finding #3), not here."""

    def __init__(self, run_id: str, run_dir: str):
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


def _allocate_run_dir(out_root: str, run_id: str, run_hash: str, live_llm: bool) -> tuple[str, int]:
    """Evidence-preservation policy (Codex finding #3).

    Scripted/replay runs are pure functions of config -> the dir is the config id;
    an existing dir may be re-generated ONLY if its stored full config_hash matches
    (verification semantics); a hash mismatch is a refused collision.

    Live LLM outputs are nondeterministic evidence -> every attempt gets its own
    exclusive directory <run_id>.aN (monotonic); nothing is ever truncated."""
    os.makedirs(out_root, exist_ok=True)
    if live_llm:
        attempt = 1
        while True:
            run_dir = os.path.join(out_root, f"{run_id}.a{attempt}")
            try:
                os.makedirs(run_dir, exist_ok=False)
                return run_dir, attempt
            except FileExistsError:
                attempt += 1
    run_dir = os.path.join(out_root, run_id)
    manifest = os.path.join(run_dir, "run.json")
    if os.path.exists(manifest):
        stored = json.load(open(manifest, encoding="utf-8"))
        if stored.get("config_hash") != run_hash:
            raise SchemaError(
                f"run-directory collision REFUSED: {run_dir} holds config_hash "
                f"{stored.get('config_hash', '')[:16]}…, current is {run_hash[:16]}…")
    os.makedirs(run_dir, exist_ok=True)
    return run_dir, 0


def run_scenario(scenario_path: str, agent_spec: str, seed: int,
                 out_root: str = "logs/runs", parent_id: str | None = None,
                 arbitration: str = "planner_priority",
                 replay_from: str | None = None,
                 sampling: dict | None = None,
                 sampler_seed: int | None = None,
                 interaction_mode: str = "independent_vignettes") -> RunResult:
    """`seed` is the SCENARIO seed (variant selection). `sampler_seed` + `sampling`
    control backend sampling: deterministic temp-0 by default; stochastic requires
    temperature > 0 and an explicit sampler_seed (replicates must be identifiable).

    `interaction_mode` (full-audit ruling): independent_vignettes = every decision
    prompt stands alone (pre-audit behavior, byte-frozen); sequential_history =
    later prompts carry the agent-visible history of prior final actions and
    visible outcomes. The mode lives inside the hashed behavioral_config, so the
    two can never share a comparison regime.

    `replay_from`: path to a prior LLM run dir. The replay agent's ENTIRE identity
    comes from that run's manifest; the scenario comes from the run's stored
    behavioral SNAPSHOT (a later YAML edit cannot alter replay); captures are
    integrity-checked and served verbatim — byte-identical to the live original."""
    if arbitration not in ARBITRATION_RULES:
        raise SchemaError(f"unknown arbitration rule {arbitration!r} (have {sorted(ARBITRATION_RULES)})")
    if interaction_mode not in INTERACTION_MODES:
        raise SchemaError(f"unknown interaction_mode {interaction_mode!r} (have {INTERACTION_MODES})")
    arbitrate = ARBITRATION_RULES[arbitration]

    if replay_from is not None:
        manifest_path = os.path.join(replay_from, "run.json")
        cap_path = os.path.join(replay_from, "captures.jsonl")
        snap_path = os.path.join(replay_from, "scenario.snapshot.json")
        if not agent_spec.startswith("llm:"):
            raise SchemaError(f"replay_from only applies to llm agents, not {agent_spec!r}")
        if not os.path.exists(manifest_path):
            raise SchemaError(f"no run manifest to replay at {manifest_path}")
        if not os.path.exists(cap_path):
            raise SchemaError(f"no captures to replay at {cap_path}")
        original = json.load(open(manifest_path, encoding="utf-8"))
        if original["agent_id"] != agent_spec:
            raise SchemaError(f"replay agent mismatch: recorded {original['agent_id']!r}, "
                              f"requested {agent_spec!r}")
        # scenario self-containment (Day-5 #6): stored snapshot wins; without one,
        # the current YAML must PROVE it matches the recorded behavioral hash
        if os.path.exists(snap_path):
            snapshot = json.load(open(snap_path, encoding="utf-8"))
            if config_hash(snapshot) != original.get("scenario_hash"):
                raise SchemaError("scenario snapshot does not match recorded scenario_hash "
                                  "— snapshot evidence corrupted")
            scenario = scenario_from_snapshot(snapshot, control_of=original.get("control_of", ""))
        else:
            scenario = load_scenario(scenario_path)
            if scenario.behavioral_hash() != original.get("scenario_hash"):
                raise SchemaError(
                    "REPLAY REFUSED: no stored snapshot and the current scenario YAML's "
                    f"behavioral hash differs from the recorded one "
                    f"({scenario.behavioral_hash()[:16]}… vs {original.get('scenario_hash', '')[:16]}…)")
        cap_bytes = open(cap_path, "rb").read()
        stored_hash = original.get("llm_info", {}).get("capture_hash", "")
        actual_hash = "sha256:" + hashlib.sha256(cap_bytes).hexdigest()[:24]
        if stored_hash and stored_hash != actual_hash:
            raise SchemaError(f"capture evidence corrupted: stored {stored_hash}, "
                              f"recomputed {actual_hash}")
        agent = agent_from_manifest(original)
        agent.load_replay([json.loads(line) for line in cap_bytes.decode("utf-8").splitlines()
                           if line.strip()])
        # replicate identity from the manifest, never current defaults — including
        # the interaction mode: a legacy run without the field was independent by
        # construction and is never silently reinterpreted as sequential
        sampling = dict(original.get("sampling", {"mode": "deterministic", "temperature": 0}))
        sampler_seed = original.get("sampler_seed")
        seed = original["seed"]
        interaction_mode = original.get("interaction_mode", "independent_vignettes")
    else:
        scenario = load_scenario(scenario_path)
        agent: AgentInterface = make_agent(agent_spec)

    sampling = validate_sampling(sampling, sampler_seed)
    if sampling["mode"] == "stochastic":
        if not isinstance(agent, LLMAgent):
            raise SchemaError("stochastic sampling applies to llm agents only")
        if replay_from is None:
            agent.configure_sampling(sampling, sampler_seed)
            # scoped probe: seeded sampling verified for THIS backend/model/config
            agent.verify_seeded_sampling()
    elif isinstance(agent, LLMAgent) and replay_from is None:
        agent.configure_sampling(sampling, sampler_seed)
    if isinstance(agent, LLMAgent) and replay_from is None:
        # audit item 8: effective think mode + backend version resolve BEFORE the
        # regime hash — the hash names what the backend actually did
        agent.resolve_effective_config()

    seed_everything(seed)
    variant = pick_variant(scenario, seed)

    # THE canonical regime object (Day-5 amendment 2): one versioned source for
    # everything behavioral except the replicate dimensions.
    if replay_from is not None and original.get("behavioral_config"):
        behavioral_config = original["behavioral_config"]
    else:
        behavioral_config = build_behavioral_config(
            scenario.scenario_id, scenario.behavioral_hash(), agent.spec_dict(),
            arbitration, ARBITRATION_VERSION, sampling,
            interaction_mode=interaction_mode,
            history_template_version=HISTORY_TEMPLATE_VERSION,
            history_template_hash=HISTORY_TEMPLATE_HASH)
    comparison_regime_id, agent_regime_id = regime_hashes(behavioral_config)

    run_hash = config_hash({"behavioral_config": behavioral_config,
                            "sampler_seed": sampler_seed})
    id_parts = [scenario.scenario_id, variant["variant_id"],
                urllib.parse.quote(agent_spec, safe=""),   # reversible escaping
                f"s{seed}"]
    if sampler_seed is not None:
        id_parts.append(f"k{sampler_seed}")
    id_parts.append(run_hash[:16])       # display segment; FULL hash lives in run.json
    run_id = ".".join(id_parts)
    live_llm = isinstance(agent, LLMAgent) and replay_from is None
    run_dir, attempt = _allocate_run_dir(out_root, run_id, run_hash, live_llm)

    # behavioral snapshot: makes the run dir self-contained for replay (Day-5 #6)
    snapshot_dict = scenario.behavioral_dict()
    with open(os.path.join(run_dir, "scenario.snapshot.json"), "w", encoding="utf-8") as fh:
        fh.write(canonical_json(snapshot_dict) + "\n")

    # stochastic admission (machine-readable exclusion reasons)
    reasons = []
    if sampling["mode"] != "stochastic":
        reasons.append("deterministic_mode")
    else:
        if sampler_seed is None:
            reasons.append("no_sampler_seed")
        if getattr(agent, "digest_status", "n/a") != "ok":
            reasons.append("digest_missing")
        if getattr(agent, "backend_seed_supported", None) is not True:
            reasons.append("backend_seed_unverified")

    log = DecisionLog(run_id, run_dir)
    run = Run(run_id=run_id, parent_id=parent_id, seed=seed,
              scenario_id=scenario.scenario_id, variant_id=variant["variant_id"],
              agent_id=agent.agent_id, config_hash=run_hash,
              started_at=_now(), code_version=_code_version(),
              arbitration=arbitration, attempt=attempt,
              agent_config=agent.spec_dict(),
              scenario_hash=config_hash(snapshot_dict),
              control_of=scenario.control_of,
              behavioral_config=behavioral_config,
              comparison_regime_id=comparison_regime_id,
              agent_regime_id=agent_regime_id,
              scenario_seed=seed, sampler_seed=sampler_seed, sampling=sampling,
              backend_seed_supported=getattr(agent, "backend_seed_supported", None),
              stochastic_reportable=(not reasons),
              stochastic_exclusion_reasons=reasons,
              interaction_mode=interaction_mode)

    dps = {dp.dp_id: dp for dp in scenario.decision_points}
    state = dict(scenario.initial_state)
    pending = []                 # [{due, narrative, state_delta}] — deferred consequences
    final_actions = []
    history = []                 # sequential mode: allowlisted agent-visible entries only
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
            if interaction_mode == "sequential_history":
                # the ONLY channel by which prior decisions reach a later prompt —
                # explicit allowlisted entries, hashed as evidence. Independent mode
                # never sets the key, so its state/prompt bytes are pre-audit frozen.
                state_before["history"] = [dict(h) for h in history]
                history_prompt_hash = config_hash(history)
            else:
                history_prompt_hash = ""
            actions = [scenario.actions[aid] for aid in dp.available_actions]

            reflex = agent.reflex(state_before, actions)
            planner = agent.plan(state_before, actions)   # consulted at every dp in MVP
            winner_pass, final = arbitrate(reflex, planner, dp)
            # the recorded winner: which PASS won, or "fallback" if that pass's
            # recommendation was itself a parse fallback (finding #4)
            arbitration_winner = ("fallback" if final.meta.get("fallback") else winner_pass)

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
                arbitration_rule=arbitration, dp_id=dp.dp_id,
                arbitration_winner=arbitration_winner,
                history_prompt_hash=history_prompt_hash)

            log.log("decision_node", **node.to_record())
            log.log("outcome", **outcome.to_record())
            log.log("memory_update",
                    **MemoryUpdate(run_id=run_id, timestep=timestep, summary=memory).to_record())

            if interaction_mode == "sequential_history":
                history.append({"dp_id": dp.dp_id, "action_id": final.action_id,
                                "action_label": scenario.actions[final.action_id].label,
                                "outcome_narrative": rule.get("narrative", "")})
            state = state_after
            final_actions.append(final.action_id)
            timestep += 1
            dp_id = rule.get("next", dp.next_default)

    run.finished_at = _now()
    run.status = "completed"
    # live LLM calls -> captures.jsonl, the replay substrate (absent for scripted/replayed runs)
    if getattr(agent, "captures", None):
        capture_bytes = "".join(canonical_json(c) + "\n" for c in agent.captures).encode("utf-8")
        with open(os.path.join(log.run_dir, "captures.jsonl"), "wb") as fh:
            fh.write(capture_bytes)
        run.llm_info = {**agent.llm_info(),
                        "capture_hash": "sha256:" + hashlib.sha256(capture_bytes).hexdigest()[:24]}
    elif hasattr(agent, "llm_info"):      # replayed LLM run: identity yes, fresh captures no
        run.llm_info = agent.llm_info()
    if hasattr(agent, "digest_status"):   # ruling 2: no digest, not reportable
        run.digest_status = agent.digest_status
        run.reportable = agent.digest_status == "ok"
    with open(os.path.join(log.run_dir, "run.json"), "w", encoding="utf-8") as fh:
        json.dump(run.to_record(), fh, indent=2, sort_keys=True)
        fh.write("\n")
    return RunResult(run_id=run_id, run_dir=log.run_dir, final_actions=final_actions, run=run)
