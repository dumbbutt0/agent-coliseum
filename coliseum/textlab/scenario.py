"""Scenario templates: YAML in, validated `Scenario` out.

A scenario is DATA — the stage, never the performance. It defines conditions, roles,
affordances, and deterministic outcome rules; it never says what an agent should do.

Contamination hedge: agent-facing text (variant narratives, action labels, outcome
narratives) must not name the archetype or smell like an eval — famous-experiment and
scripture names, plus the words test/experiment/scenario/simulation, are rejected at
load time. Archetype names live only in internal IDs.
"""
from __future__ import annotations

import os
import re

import yaml

from .schema import Action, DecisionPoint, Scenario, SchemaError, validate_delta

# Word-boundary matches, case-insensitive. Extend as new archetypes join the pack.
CONTAMINATION_WORDS = [
    "test", "experiment", "scenario", "simulation", "evaluation",
    "milgram", "cain", "abel", "isaac", "abraham", "joseph", "goliath",
]
_CONTAMINATION_RE = re.compile(
    r"\b(" + "|".join(CONTAMINATION_WORDS) + r")\b", re.IGNORECASE
)


def lint_agent_facing(text: str, where: str):
    """Raise if agent-facing text would leak the archetype or the eval frame."""
    hit = _CONTAMINATION_RE.search(text or "")
    if hit:
        raise SchemaError(f"{where}: contamination word {hit.group(0)!r} in agent-facing text")


def _req(raw: dict, key: str, where: str):
    if key not in raw:
        raise SchemaError(f"{where}: missing required key {key!r}")
    return raw[key]


def load_scenario(path: str) -> Scenario:
    """Load + validate one scenario YAML. Raises SchemaError naming the offending path."""
    where = os.path.basename(path)
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise SchemaError(f"{where}: top level must be a mapping")

    scenario_id = _req(raw, "scenario_id", where)
    where = scenario_id  # richer error prefix from here on

    actions = {}
    for aid, spec in _req(raw, "actions", where).items():
        action = Action(action_id=aid, **spec)
        lint_agent_facing(action.label, f"{where}.actions.{aid}.label")
        actions[aid] = action

    decision_points = []
    for dp_raw in _req(raw, "decision_points", where):
        dp = DecisionPoint(**dp_raw)
        for aid in dp.available_actions:
            if aid not in actions:
                raise SchemaError(f"{where}.{dp.dp_id}: unknown action {aid!r}")
        decision_points.append(dp)
    if not decision_points:
        raise SchemaError(f"{where}: needs at least one decision point")
    dp_ids = [dp.dp_id for dp in decision_points]
    if len(set(dp_ids)) != len(dp_ids):
        raise SchemaError(f"{where}: duplicate dp_id")

    variants = _req(raw, "variants", where)
    if len(variants) < 2:
        raise SchemaError(f"{where}: needs >=2 paraphrase variants, got {len(variants)}")
    for v in variants:
        vid = _req(v, "variant_id", f"{where}.variants")
        lint_agent_facing(v.get("intro", ""), f"{where}.{vid}.intro")
        texts = _req(v, "decision_texts", f"{where}.{vid}")
        for dp_id in dp_ids:
            if dp_id not in texts:
                raise SchemaError(f"{where}.{vid}: no decision_texts entry for {dp_id!r}")
            lint_agent_facing(texts[dp_id], f"{where}.{vid}.decision_texts.{dp_id}")

    outcome_rules = _req(raw, "outcome_rules", where)
    for dp in decision_points:
        for aid in dp.available_actions:
            key = f"{dp.dp_id}/{aid}"
            if key not in outcome_rules:
                raise SchemaError(f"{where}: no outcome rule for {key!r}")
            rule = outcome_rules[key]
            lint_agent_facing(rule.get("narrative", ""), f"{where}.outcome_rules.{key}.narrative")
            validate_delta(rule.get("state_delta", []), f"{where}.outcome_rules.{key}.state_delta")
            nxt = rule.get("next", dp.next_default)
            if nxt != "end" and nxt not in dp_ids:
                raise SchemaError(f"{where}.outcome_rules.{key}: next -> unknown dp {nxt!r}")
            for cons in rule.get("consequences_deferred", []):
                if "after" not in cons:
                    raise SchemaError(f"{where}.outcome_rules.{key}: deferred consequence needs 'after' (timesteps)")
                lint_agent_facing(cons.get("narrative", ""), f"{where}.outcome_rules.{key}.deferred")
                validate_delta(cons.get("state_delta", []), f"{where}.outcome_rules.{key}.deferred.state_delta")

    return Scenario(
        scenario_id=scenario_id,
        archetype=_req(raw, "archetype", where),
        purpose=_req(raw, "purpose", where),
        variants=variants,
        initial_state=raw.get("initial_state", {}),
        roles=raw.get("roles", {}),
        actions=actions,
        decision_points=decision_points,
        outcome_rules=outcome_rules,
        metrics_captured=raw.get("metrics_captured", []),
        control_of=raw.get("control_of", ""),
        raw=raw,
    )


def pick_variant(scenario: Scenario, seed: int) -> dict:
    """Seed-selected paraphrase variant — logged on the Run so it's always attributable."""
    return scenario.variants[seed % len(scenario.variants)]


def lint_twin_pair(primary: Scenario, twin: Scenario) -> list:
    """Structural lint for a control twin (Codex finding #7): a twin must change ONE
    variable, so its decision structure must match the primary. Returns issue strings
    (empty = structurally clean). Whole-run twin deltas are only interpretable for
    clean pairs; mismatched pairs must restrict analysis to matched steps."""
    issues = []
    pid, tid = primary.scenario_id, twin.scenario_id
    if twin.control_of != pid:
        issues.append(f"{tid}: control_of != {pid!r}")
    if len(primary.decision_points) != len(twin.decision_points):
        issues.append(f"dp count differs: {len(primary.decision_points)} vs {len(twin.decision_points)}")
        return issues
    for pdp, tdp in zip(primary.decision_points, twin.decision_points):
        where = f"{pdp.dp_id}/{tdp.dp_id}"
        for dial in ("authority_pressure", "risk_level", "time_pressure"):
            if getattr(pdp, dial) != getattr(tdp, dial):
                issues.append(f"{where}: {dial} differs "
                              f"({getattr(pdp, dial)} vs {getattr(tdp, dial)})")
        if len(pdp.available_actions) != len(tdp.available_actions):
            issues.append(f"{where}: action cardinality differs "
                          f"({len(pdp.available_actions)} vs {len(tdp.available_actions)})")
            continue
        for pa, ta in zip(pdp.available_actions, tdp.available_actions):
            p_act, t_act = primary.actions[pa], twin.actions[ta]
            if p_act.visible_reward != t_act.visible_reward:
                issues.append(f"{where}: {pa}->{ta} visible_reward differs")
            if p_act.costs != t_act.costs:
                issues.append(f"{where}: {pa}->{ta} costs differ")
            if p_act.moral_tags != t_act.moral_tags:
                # tag differences can BE the manipulated variable (e.g. the same
                # removal is harm in water_bearer, not in the saboteur twin) —
                # semantic note, not a structural violation
                issues.append(f"note: {where}: {pa}->{ta} moral_tags differ "
                              f"({p_act.moral_tags} vs {t_act.moral_tags})")
    return issues


def structural_issues(issues: list) -> list:
    """The lint failures that invalidate whole-run twin deltas (notes excluded)."""
    return [i for i in issues if not i.startswith("note:")]
