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
    """Load + validate one authored scenario YAML. Raises SchemaError naming the path."""
    where = os.path.basename(path)
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise SchemaError(f"{where}: top level must be a mapping")
    _req(raw, "archetype", where)
    _req(raw, "purpose", where)
    return build_scenario(raw, where)


def scenario_from_snapshot(snapshot: dict, control_of: str = "") -> Scenario:
    """Rebuild a Scenario from a run's stored behavioral snapshot (Day-5 replay
    self-containment). The snapshot IS the model-facing content; descriptive fields
    absent from it (archetype/purpose) are irrelevant to replay."""
    raw = dict(snapshot)
    raw.setdefault("archetype", "snapshot")
    raw.setdefault("purpose", "rebuilt from run snapshot")
    if control_of:
        raw.setdefault("control_of", control_of)
    return build_scenario(raw, f"snapshot:{raw.get('scenario_id', '?')}")


def build_scenario(raw: dict, where: str) -> Scenario:
    """Validate + construct from a raw dict (shared by YAML and snapshot paths)."""
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


# ----------------------------------------------------- scenario registry (M3)

# The SPEC's eight scenario families (docs/first-gladiator/SPEC.md §3,
# owner-ratified SC-3). A registry entry outside this set fails lint —
# the anti-sprawl rule made machine-checkable.
REGISTRY_FAMILIES = (
    "authority", "moral_conflict", "uncertainty", "time_pressure",
    "self_preservation", "social_pressure", "deception",
    "memory_persistence",
)
REGISTRY_STATUSES = ("draft", "pilot", "frozen")
REGISTRY_VERSION = "1"


def load_registry(path: str) -> dict:
    """Load the scenario registry YAML (no validation beyond shape — use
    lint_registry for the full checks)."""
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict) or "scenarios" not in raw:
        raise SchemaError(f"{os.path.basename(path)}: registry must be a "
                          "mapping with a 'scenarios' list")
    if raw.get("registry_version") != REGISTRY_VERSION:
        raise SchemaError(f"unsupported registry_version "
                          f"{raw.get('registry_version')!r}")
    return raw


def lint_registry(registry_path: str, config_dir: str) -> list:
    """Machine-check the registry against the SPEC rules and the actual
    scenario corpus. Returns issue strings (empty = clean). Checks:

    - every entry's file exists, loads, and its scenario_id matches;
    - behavioral_hash matches the loaded scenario (the SAME hash runs pin
      as scenario_hash — a stale registry row can never vouch for changed
      behavioral content);
    - family is one of the SPEC's eight (anti-sprawl);
    - >=2 paraphrase variants, and the registry's variant list matches the
      YAML exactly;
    - twin links agree with the YAMLs in BOTH directions (control_of and
      the primary's controls list);
    - status is draft|pilot|frozen; scenario_ids unique;
    - COMPLETENESS: every configs/scenarios/*.yaml is registered — an
      unregistered scenario cannot exist silently.
    """
    issues = []
    try:
        raw = load_registry(registry_path)
    except (SchemaError, OSError, yaml.YAMLError) as exc:
        return [f"registry unreadable: {exc}"]

    entries = raw["scenarios"]
    ids = [e.get("scenario_id") for e in entries]
    for sid in {i for i in ids if ids.count(i) > 1}:
        issues.append(f"duplicate registry entry for {sid!r}")

    loaded: dict = {}
    by_id: dict = {}
    for e in entries:
        sid = e.get("scenario_id", "?")
        by_id[sid] = e
        rel = e.get("file", "")
        # registry paths are repo-relative; resolve against the repo root
        # (config_dir = <repo>/configs/scenarios)
        repo_root = os.path.dirname(os.path.dirname(config_dir))
        path = rel if os.path.isabs(rel) else os.path.join(repo_root, rel)
        if not os.path.exists(path):
            issues.append(f"{sid}: file {rel!r} does not exist")
            continue
        try:
            s = loaded[sid] = load_scenario(path)
        except SchemaError as exc:
            issues.append(f"{sid}: file fails scenario validation: {exc}")
            continue
        if s.scenario_id != sid:
            issues.append(f"{sid}: file declares scenario_id "
                          f"{s.scenario_id!r}")
            continue
        if e.get("behavioral_hash") != s.behavioral_hash():
            issues.append(f"{sid}: behavioral_hash mismatch — registry "
                          f"{str(e.get('behavioral_hash'))[:16]}… vs loaded "
                          f"{s.behavioral_hash()[:16]}… (revision-bound "
                          "identity: register the new revision, never "
                          "mutate in place)")
        if e.get("family") not in REGISTRY_FAMILIES:
            issues.append(f"{sid}: family {e.get('family')!r} not one of "
                          f"the SPEC's eight {REGISTRY_FAMILIES}")
        if e.get("status") not in REGISTRY_STATUSES:
            issues.append(f"{sid}: status {e.get('status')!r} not in "
                          f"{REGISTRY_STATUSES}")
        want_variants = [v["variant_id"] for v in s.variants]
        if list(e.get("variants", [])) != want_variants:
            issues.append(f"{sid}: registry variants {e.get('variants')} != "
                          f"scenario variants {want_variants}")
        if len(want_variants) < 2:
            issues.append(f"{sid}: fewer than 2 paraphrase variants")
        reg_control = e.get("control_of") or ""
        if reg_control != (s.control_of or ""):
            issues.append(f"{sid}: registry control_of {reg_control!r} != "
                          f"YAML control_of {s.control_of!r}")

    # twin symmetry: X.control_of == P  <=>  X in P.controls
    for sid, e in by_id.items():
        control = e.get("control_of")
        if control:
            primary = by_id.get(control)
            if primary is None:
                issues.append(f"{sid}: control_of {control!r} is not "
                              "registered")
            elif sid not in (primary.get("controls") or []):
                issues.append(f"{control}: controls list missing {sid!r}")
        for twin in (e.get("controls") or []):
            t = by_id.get(twin)
            if t is None:
                issues.append(f"{sid}: controls entry {twin!r} is not "
                              "registered")
            elif (t.get("control_of") or "") != sid:
                issues.append(f"{twin}: control_of != {sid!r} but listed in "
                              f"{sid}'s controls")

    # completeness: no unregistered scenario file
    import glob as _glob
    for path in sorted(_glob.glob(os.path.join(config_dir, "*.yaml"))):
        try:
            s = load_scenario(path)
        except SchemaError:
            issues.append(f"unregistered file {os.path.basename(path)} also "
                          "fails validation")
            continue
        if s.scenario_id not in by_id:
            issues.append(f"UNREGISTERED scenario {s.scenario_id!r} "
                          f"({os.path.basename(path)}) — every scenario "
                          "must be in the registry")
    return issues
