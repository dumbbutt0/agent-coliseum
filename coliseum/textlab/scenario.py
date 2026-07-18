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
    # variant_ids must be UNIQUE: pick_variant selects by LIST POSITION
    # (variants[seed % len]), so a colliding id makes slot identity ambiguous —
    # two positions could carry the same id while delivering different text,
    # hiding a content swap behind an unchanged-looking id sequence.
    vids = [v.get("variant_id") for v in variants]
    if len(set(vids)) != len(vids):
        raise SchemaError(f"{where}: duplicate variant_id in {vids} — "
                          "variant selection is positional, so ids must "
                          "uniquely identify their slot")
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


# --------------------------------- scrambled-history gate invariants (m7)
#
# The admission-gate conditions are only interpretable if they are matched-
# except-order: A and B must carry the IDENTICAL multiset of world events merely
# reordered, and C must be semantically identical to A (wording/formatting only).
# lint_twin_pair checks per-step structure; these functions close the gap it
# leaves (it never compares the reordered event multiset). Run as a preflight
# assertion before any gate run — never in the hot loop.

_VAL_POS_RE = re.compile(r"^val_pos(\d+)$")


def _walked_dps(s: Scenario) -> list:
    """Decision points in DELIVERY order — the runner's next-chain walk from
    decision_points[0], not the authored list order (audit 001664 hardening:
    a scenario could list one order and chain another). Requires every action
    at a dp to share ONE successor (delivery is choice-independent for the
    gate contract) and the walk to visit every dp exactly once, ending at
    "end"."""
    by_id = {dp.dp_id: dp for dp in s.decision_points}
    walk, seen = [], set()
    dp_id = s.decision_points[0].dp_id
    while dp_id != "end":
        if dp_id in seen:
            raise SchemaError(f"{s.scenario_id}: delivery walk revisits "
                              f"{dp_id!r} — the gate contract needs an "
                              "acyclic single-pass chain")
        dp = by_id[dp_id]
        seen.add(dp_id)
        walk.append(dp)
        successors = {s.outcome_rules[f"{dp_id}/{aid}"].get(
            "next", dp.next_default) for aid in dp.available_actions}
        if len(successors) != 1:
            raise SchemaError(f"{s.scenario_id}.{dp_id}: successor is "
                              "choice-DEPENDENT (every action at a gate dp "
                              "must share one `next`)")
        (dp_id,) = successors
    if len(walk) != len(s.decision_points):
        missing = sorted(by_id.keys() - seen)
        raise SchemaError(f"{s.scenario_id}: decision points {missing} are "
                          "unreachable from the delivery walk")
    return walk


def _event_dps(s: Scenario) -> list:
    return [dp for dp in _walked_dps(s) if "event" in dp.facts]


def experience_sequence(s: Scenario) -> list:
    """Ordered (event_label, valence) pairs as DELIVERED by this scenario
    (next-chain walk order, not authored list order).

    Enforces the positional-delta contract in full (audit 001664 finding 2):
    every action at an event dp must carry the IDENTICAL COMPLETE state_delta
    (the event is world-driven, choice-independent — no per-action side
    channel of any kind), and that complete delta must be exactly ONE op,
    `val_pos<K> add <valence>` where K is the event's 1-based delivery
    position. Any additional operation on an event dp, valence-named or not,
    is refused."""
    seq = []
    for pos, dp in enumerate(_event_dps(s), start=1):
        event, valence = dp.facts.get("event"), dp.facts.get("valence")
        if event is None or valence is None:
            raise SchemaError(f"{s.scenario_id}.{dp.dp_id}: event dp needs "
                              "facts.event and facts.valence")
        deltas = set()
        for aid in dp.available_actions:
            ops = s.outcome_rules[f"{dp.dp_id}/{aid}"].get("state_delta", [])
            deltas.add(tuple(
                (o.get("field"), o.get("op"), o.get("value")) for o in ops))
        if len(deltas) != 1:
            raise SchemaError(f"{s.scenario_id}.{dp.dp_id}: event delta is "
                              "choice-DEPENDENT (the complete state_delta "
                              "must be identical for every action at an "
                              "event dp)")
        (all_ops,) = deltas
        want = ((f"val_pos{pos}", "add", valence),)
        if all_ops != want:
            raise SchemaError(f"{s.scenario_id}.{dp.dp_id}: event delta "
                              f"{all_ops} != expected {want} (exactly one "
                              "positional valence op; val_pos index must "
                              "equal the event's delivery position; no "
                              "extra state channels on event dps)")
        seq.append((event, valence))
    return seq


def experience_multiset(s: Scenario) -> dict:
    """Position-agnostic multiset of (event_label, valence) — the content that
    must be IDENTICAL across matched-except-order conditions."""
    counts: dict = {}
    for pair in experience_sequence(s):
        counts[pair] = counts.get(pair, 0) + 1
    return counts



def variant_payload_hash(variant: dict) -> str:
    """sha256 over a variant's agent-facing payload (intro + decision_texts).

    Used to commit a sham-control payload to its positional slot: selection is
    positional, so identifiers alone cannot prove which text a seed receives."""
    import hashlib
    from .schema import canonical_json
    body = {"intro": variant.get("intro", ""),
            "decision_texts": variant.get("decision_texts")}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def _dp_raw(dp) -> dict:
    return {"dp_id": dp.dp_id, "available_actions": list(dp.available_actions),
            "authority_pressure": dp.authority_pressure,
            "risk_level": dp.risk_level, "time_pressure": dp.time_pressure,
            "facts": dict(dp.facts)}


def _renumber_val_pos(ops: list, mapping: dict) -> list:
    out = []
    for op in ops:
        op = dict(op)
        m = _VAL_POS_RE.match(str(op.get("field", "")))
        if m and int(m.group(1)) in mapping:
            op["field"] = f"val_pos{mapping[int(m.group(1))]}"
        out.append(op)
    return out


def _b_equivalence_issues(a: Scenario, b: Scenario) -> list:
    """B must equal A modulo ONLY the declared event permutation and the
    positional val_pos renumbering it induces (audit 001664 finding 2): same
    actions, dials, facts, narratives, variant texts, terminal probe, and
    complete state deltas — order is the sole manipulated variable."""
    issues = []
    a_events, b_events = _event_dps(a), _event_dps(b)
    a_labels = [dp.facts["event"] for dp in a_events]
    b_labels = [dp.facts["event"] for dp in b_events]
    if len(set(a_labels)) != len(a_labels) or len(set(b_labels)) != len(b_labels):
        issues.append("A/B: duplicate event labels make the permutation "
                      "ambiguous — canonical B-equivalence cannot be proven")
        return issues
    if set(a_labels) != set(b_labels):
        return issues        # multiset check already reports this
    # position mapping induced by the permutation: A-position -> B-position
    b_pos = {label: i for i, label in enumerate(b_labels, start=1)}
    pos_map = {i: b_pos[label] for i, label in enumerate(a_labels, start=1)}

    # event dps: identical raw content per event label (position-independent)
    a_by_label = {dp.facts["event"]: dp for dp in a_events}
    b_by_label = {dp.facts["event"]: dp for dp in b_events}
    for label in a_labels:
        if _dp_raw(a_by_label[label]) != _dp_raw(b_by_label[label]):
            issues.append(f"B: event dp {label!r} differs from A beyond "
                          "position (actions/dials/facts must be identical)")
    # non-event dps (the terminal probe): identical raw content and identical
    # relative order
    a_rest = [_dp_raw(dp) for dp in _walked_dps(a) if "event" not in dp.facts]
    b_rest = [_dp_raw(dp) for dp in _walked_dps(b) if "event" not in dp.facts]
    if a_rest != b_rest:
        issues.append("B: non-event decision points differ from A — the "
                      "terminal probe must be identical")
    # whole-scenario behavioral surfaces that must be byte-equal
    for key in ("initial_state", "actions"):
        if a.raw.get(key) != b.raw.get(key):
            issues.append(f"B differs from A in behavioral key {key!r} — "
                          "order is the only permitted difference")
    # ORDERED comparison (audit 001678): pick_variant selects by LIST POSITION
    # (variants[seed % len]), so the variant LIST — ids, order, and content —
    # must be identical, not merely equal as an unordered mapping. A reordered
    # but otherwise unchanged list would silently deliver different wording
    # for the same seed.
    a_vars = [(v["variant_id"], v.get("intro", ""), v.get("decision_texts"))
              for v in a.variants]
    b_vars = [(v["variant_id"], v.get("intro", ""), v.get("decision_texts"))
              for v in b.variants]
    if a_vars != b_vars:
        issues.append("B: variant list differs from A in order or content — "
                      "seed-to-variant selection is positional, so list "
                      "drift changes the delivered wording (content "
                      "confound, not an order manipulation)")
    # outcome rules: narratives, deferred consequences, and COMPLETE deltas
    # must match A's modulo val_pos renumbering; successors must follow each
    # scenario's own declared chain (validated by _walked_dps)
    for dp in a_events + [dp for dp in _walked_dps(a) if "event" not in dp.facts]:
        for aid in dp.available_actions:
            key = f"{dp.dp_id}/{aid}"
            ra = dict(a.outcome_rules[key])
            rb = dict(b.outcome_rules.get(key, {}))
            for r in (ra, rb):
                r.pop("next", None)      # chain topology is checked by walks
            ra["state_delta"] = _renumber_val_pos(
                ra.get("state_delta", []), pos_map)
            rb["state_delta"] = list(rb.get("state_delta", []))
            if ra != rb:
                issues.append(f"B: outcome rule {key!r} differs from A "
                              "beyond val_pos renumbering (narrative/delta/"
                              "consequence drift)")
    return issues


def lint_scramble_triplet(a: Scenario, b: Scenario, c: Scenario) -> list:
    """Guard that the gate's conditions are matched-except-order.

    A = developmental order, B = same multiset permuted, C = sham reorder
    (semantically identical to A; agent-facing wording/formatting only).
    Returns issue strings (empty = clean); raises SchemaError if a scenario
    violates the positional-delta contract itself."""
    issues = []
    if experience_multiset(a) != experience_multiset(b):
        issues.append("A/B carry DIFFERENT experience multisets — B is not a "
                      "permutation of A")
    if experience_sequence(a) == experience_sequence(b):
        issues.append("A/B deliver the identical order — B is not scrambled")
    issues.extend(_b_equivalence_issues(a, b))
    if experience_sequence(a) != experience_sequence(c):
        issues.append("C differs from A in semantic event order — not a "
                      "sham (formatting-only) control")
    # C must be A everywhere EXCEPT agent-facing variant text: same state,
    # actions, decision structure, and outcome rules.
    for key in ("initial_state", "actions", "decision_points", "outcome_rules"):
        if a.raw.get(key) != c.raw.get(key):
            issues.append(f"C differs from A in behavioral key {key!r} — the "
                          "sham control may vary wording only")
    a_texts = [(v.get("intro", ""), v.get("decision_texts")) for v in a.variants]
    c_texts = [(v.get("intro", ""), v.get("decision_texts")) for v in c.variants]
    if a_texts == c_texts:
        issues.append("C's variant text is byte-identical to A — a sham "
                      "control must actually change the surface form")
    # positional alignment (audit 001678): C rewords each SLOT, but the slot
    # sequence must match A's — pick_variant is positional, so a reordered
    # variant_id list would compare different paraphrase slots per seed
    if [v["variant_id"] for v in a.variants] != \
            [v["variant_id"] for v in c.variants]:
        issues.append("C: variant_id list order differs from A — seed-to-"
                      "variant selection is positional, so slot order must "
                      "match for A|C to be a same-seed wording comparison")
    # payload-to-slot binding (audit 001700): matching ids in matching order
    # are NOT sufficient — C's two payloads can be exchanged while the ids
    # stay put, so a seed records one slot identity while receiving the other
    # slot's text. Each C variant must therefore DECLARE which A slot it
    # rewords and COMMIT its own payload by hash. Exchanging payloads breaks
    # the committed hash; recomputing the hash changes scramble_sham's
    # behavioral_hash, which the scenario registry pins (revision-bound
    # identity), so both routes are refused.
    for pos, cv in enumerate(c.variants):
        where = f"C slot {pos} ({cv.get('variant_id')!r})"
        declared = cv.get("rewords")
        expected = a.variants[pos]["variant_id"] if pos < len(a.variants) else None
        if declared is None:
            issues.append(f"{where}: missing 'rewords' — each sham slot must "
                          "declare which A slot it rewords")
        elif declared != expected:
            issues.append(f"{where}: rewords {declared!r} but occupies the "
                          f"slot of A's {expected!r}")
        committed = cv.get("payload_sha256")
        actual = variant_payload_hash(cv)
        if committed is None:
            issues.append(f"{where}: missing 'payload_sha256' — the sham "
                          "payload must be committed to its slot")
        elif committed != actual:
            issues.append(f"{where}: payload_sha256 {str(committed)[:12]}… != "
                          f"recomputed {actual[:12]}… — the agent-facing "
                          "payload is not the one committed to this slot")
    for twin, name in ((b, "B"), (c, "C")):
        if twin.control_of != a.scenario_id:
            issues.append(f"{name}: control_of != {a.scenario_id!r}")
    return issues


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
