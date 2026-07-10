"""Agent interface for the textlab: every decision is taken twice.

`reflex` = the fast pass (answer-first, no deliberation budget).
`plan`   = the slow pass (full deliberation).
The runner logs BOTH choices per decision node; `final_action` follows the planner
when it is consulted. This is the cheap prerequisite for the flinch/temporal-
dissociation analysis — divergence between the passes is a first-class measurement,
so scripted personas are deliberately built to diverge where a reflex would.

ScriptedAgents are fully deterministic: rules over the decision's `facts` (ground
truth like how verifiable/harmful a directive is) and the actions' `moral_tags`.
They exist for tests, baselines, and the determinism gate — not as models of anything.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from .schema import SchemaError, config_hash


@dataclass
class Choice:
    action_id: str
    confidence: float            # 0..1
    reasoning_summary: str
    reward_expected: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


class AgentInterface:
    """Two-pass contract. `state` includes the decision's facts/pressures; `actions`
    is the list of Action objects available at this decision point."""

    agent_id: str = "agent"
    kind: str = "abstract"
    constitution: str = ""

    def reflex(self, state: dict, actions: list) -> Choice:
        raise NotImplementedError

    def plan(self, state: dict, actions: list) -> Choice:
        raise NotImplementedError

    def spec_dict(self) -> dict:
        """The config that feeds run lineage (config_hash covers it)."""
        return {"kind": self.kind, "agent_id": self.agent_id, "constitution": self.constitution}


def _first_tagged(actions: list, tag: str):
    for a in actions:
        if tag in a.moral_tags:
            return a
    return None


def _total_cost(a) -> float:
    return sum(v for v in a.costs.values() if isinstance(v, (int, float)))


class ScriptedAgent(AgentInterface):
    """Deterministic personas. Tie-breaks always follow action list order."""

    PERSONAS = ("obedient", "defiant", "merciful", "selfish")

    def __init__(self, persona: str):
        if persona not in self.PERSONAS:
            raise SchemaError(f"unknown scripted persona {persona!r} (have {self.PERSONAS})")
        self.persona = persona
        self.kind = "scripted"
        self.agent_id = f"scripted:{persona}"
        self.constitution = f"scripted persona rules: {persona}"

    # -- persona rules -------------------------------------------------------
    # facts.harm is the scenario's ground truth: "none" | "unverifiable" | "verified"

    def _obedient(self, state, actions, deliberate):
        comply = _first_tagged(actions, "obedience")
        verify = _first_tagged(actions, "verify")
        harm = state.get("facts", {}).get("harm", "none")
        # The designed reflex/plan divergence: the reflex obeys on the spot; the
        # deliberate pass checks an unverifiable directive first when it can.
        if deliberate and harm == "unverifiable" and verify is not None:
            return Choice(verify.action_id, 0.7, "directive unclear; confirm before acting",
                          verify.visible_reward)
        if comply is not None:
            return Choice(comply.action_id, 0.9, "instruction from the proper authority; carry it out",
                          comply.visible_reward)
        return Choice(actions[0].action_id, 0.5, "no compliant option; taking the first available",
                      actions[0].visible_reward)

    def _defiant(self, state, actions, deliberate):
        refuse = _first_tagged(actions, "refusal")
        if refuse is not None:
            return Choice(refuse.action_id, 0.9, "not acting on orders I did not choose",
                          refuse.visible_reward)
        non_comply = next((a for a in actions if "obedience" not in a.moral_tags), actions[0])
        return Choice(non_comply.action_id, 0.6, "avoiding compliance where possible",
                      non_comply.visible_reward)

    def _merciful(self, state, actions, deliberate):
        harm = state.get("facts", {}).get("harm", "none")
        verify = _first_tagged(actions, "verify")
        refuse = _first_tagged(actions, "refusal")
        comply = _first_tagged(actions, "obedience")
        if harm == "verified" and refuse is not None:
            return Choice(refuse.action_id, 0.9, "this would hurt people; I won't do it",
                          refuse.visible_reward)
        if harm == "unverifiable":
            pick = verify or refuse or actions[0]
            return Choice(pick.action_id, 0.7, "possible harm; checking before anyone gets hurt",
                          pick.visible_reward)
        if comply is not None:
            return Choice(comply.action_id, 0.8, "harmless request; cooperating",
                          comply.visible_reward)
        return Choice(actions[0].action_id, 0.5, "no harm in sight; taking the first available",
                      actions[0].visible_reward)

    def _selfish(self, state, actions, deliberate):
        best = max(actions, key=lambda a: (a.visible_reward - _total_cost(a),
                                           -actions.index(a)))
        return Choice(best.action_id, 0.8, "best personal return", best.visible_reward)

    # ------------------------------------------------------------------------

    def _decide(self, state, actions, deliberate):
        return getattr(self, f"_{self.persona}")(state, actions, deliberate)

    def reflex(self, state: dict, actions: list) -> Choice:
        return self._decide(state, actions, deliberate=False)

    def plan(self, state: dict, actions: list) -> Choice:
        return self._decide(state, actions, deliberate=True)

    def spec_dict(self) -> dict:
        return {**super().spec_dict(), "persona": self.persona}


class OllamaAgent(AgentInterface):
    """Local-model agent (Day 3). Reflex = tiny num_predict answer-first prompt;
    plan = full reasoning prompt."""

    def __init__(self, model: str):
        raise NotImplementedError("OllamaAgent lands in Day 3 (see docs/TEXTLAB.md roadmap)")


class APIAgent(AgentInterface):
    """Hosted-model agent (Day 3). Same two-pass contract, key from env."""

    def __init__(self, model: str):
        raise NotImplementedError("APIAgent lands in Day 3 (see docs/TEXTLAB.md roadmap)")


def make_agent(agent_spec: str) -> AgentInterface:
    """Build an agent from a CLI spec: 'scripted:<persona>' | 'ollama:<model>' | 'api:<model>'."""
    kind, _, arg = agent_spec.partition(":")
    if kind == "scripted":
        return ScriptedAgent(arg or "obedient")
    if kind == "ollama":
        return OllamaAgent(arg)
    if kind == "api":
        return APIAgent(arg)
    raise SchemaError(f"unknown agent spec {agent_spec!r} (want scripted:|ollama:|api:)")


def agent_config_hash(agent: AgentInterface) -> str:
    return config_hash(agent.spec_dict())
