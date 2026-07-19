"""Decision admissibility — is a recorded decision a DECISION, or a format artifact?

This module does not invent a rule. It generalizes Ruling 1 (2026-07-10), already
implemented privately as `metrics._node_valid` and already audited: a decision whose
winning recommendation was a parse fallback is a FORMAT ARTIFACT and is never scored
as moral behavior. What is new here is only that the predicate becomes first-class,
versioned, shared, and — critically — SURFACED: `run_decision_census` reports how many
non-decisions a run contains and why, so a differential parse-failure rate across
experimental conditions is visible as itself rather than as a behavioral effect.

Why that matters (the defect this closes): when a live model's output fails to parse,
`LLMAgent._pass` substitutes a deterministic fallback onto `actions[0]` — the FIRST
available action, which is identical across conditions. Downstream readers that treat
`final_action` as a real choice therefore pile mass on one specific action in whichever
condition provokes more malformed output, manufacturing a distributional difference out
of pure formatting. The census bounds that artifact; it does not eliminate it.

HARD CONSTRAINT (deliberate): every input read here is a field ALREADY present in
existing decisions.jsonl records. Nothing new is logged, no run identity or hash moves,
and historical evidence under reports/*/run_logs/ remains fully re-analyzable. Adding a
logged field would have been easier and would have voided every prior run.

Evidence tags, in descending strength — a caller can always tell which it got:

  "arbitration_winner"    first-class: the run recorded which PASS won, or the literal
                          "fallback" (runner.py). Authoritative.
  "legacy_pass_inference" read-compat only: the node predates `arbitration_winner`, so
                          the winning pass is inferred by action equality — the very
                          inference Codex finding #4 warned against. Reproduced here so
                          legacy runs stay analyzable, tagged so they are never silently
                          claimed to carry first-class evidence.
  "no_parse_metadata"     scripted runs: no parser ran, so no parse failure is possible.

A missing key NEVER defaults to failure. That is what makes Phase-1 scripted evidence
regenerate unchanged: those runs carry neither `arbitration_winner` nor any `meta`, and
must census at exactly zero non-decisions.

Replay runs are deliberately NOT special-cased. Replay drives the same `LLMAgent._pass`
and so re-derives identical `meta` and `arbitration_winner`; a branch on "is this a
replay" would be a second code path that could silently diverge from the live one. The
absence of that branch is the assertion.

Explicitly NOT used as signals: `confidence == 0.0`, `reasoning_summary` text, latency.
All three correlate with the fallback path, none is a fact about it — a model may
genuinely answer with zero confidence, and a heuristic that quietly reclassifies real
decisions as artifacts is the same category of error, pointed the other way.
"""
from __future__ import annotations

# Bump on ANY change to what counts as an admissible decision. Stamped into every
# census so a reported non-decision rate can never be compared across definitions
# without the mismatch being visible.
DECISION_ADMISSIBILITY_VERSION = "1"

# The literal recorded by runner.py when the winning pass was itself a parse fallback.
_FALLBACK = "fallback"


def _choice(node: dict, key: str):
    """A pass's recorded Choice, or None if absent/malformed. Never raises."""
    c = node.get(key)
    return c if isinstance(c, dict) else None


def _meta(choice) -> dict:
    """A pass's meta dict. Scripted choices have no `meta` key at all — that is
    absence of a parser, not a parse failure, so it reads as an empty dict."""
    if not isinstance(choice, dict):
        return {}
    m = choice.get("meta")
    return m if isinstance(m, dict) else {}


def _r(admissible: bool, reason: str, evidence: str) -> dict:
    return {"admissible": admissible, "reason": reason, "evidence": evidence}


def decision_admissibility(node: dict) -> dict:
    """Classify one decision node.

    Returns {"admissible": bool, "reason": str, "evidence": str}. Total function:
    a malformed node returns non-admissible with reason "unreadable_node" rather
    than raising, because a census that dies on one bad line silently truncates
    the denominator it is supposed to be protecting.
    """
    if not isinstance(node, dict):
        return _r(False, "unreadable_node", "unreadable_node")

    # --- Primary path: the run recorded the winner itself. -------------------
    winner = node.get("arbitration_winner")
    if isinstance(winner, str):
        if winner == _FALLBACK:
            return _r(False, "parse_fallback_winner", "arbitration_winner")
        return _r(True, "ok", "arbitration_winner")
    if winner is not None:
        # Present but not a string: the field exists and we cannot read it. Do not
        # quietly downgrade to the weaker legacy inference — say so.
        return _r(False, "unreadable_node", "unreadable_node")

    # --- Legacy read-compat: node predates `arbitration_winner`. -------------
    reflex, planner = _choice(node, "reflex_choice"), _choice(node, "planner_choice")
    final = node.get("final_action")
    if reflex is None or planner is None or not isinstance(final, str):
        return _r(False, "unreadable_node", "unreadable_node")

    # No parser ran on either pass (scripted): no parse failure is possible.
    if "meta" not in reflex and "meta" not in planner:
        return _r(True, "ok", "no_parse_metadata")

    # metrics._node_valid's inference, reproduced exactly: pick the pass whose
    # action_id equals the final action, then read that pass's fallback flag.
    won = planner if planner.get("action_id") == final else reflex
    if _meta(won).get("fallback", False):
        return _r(False, "legacy_inferred_fallback", "legacy_pass_inference")
    return _r(True, "ok", "legacy_pass_inference")


def is_admissible_decision(node: dict) -> bool:
    """True iff this record represents a genuine decision. The predicate that
    gates terminal-action distributions."""
    return decision_admissibility(node)["admissible"]


def strictly_admissible(node: dict) -> bool:
    """Admissible AND both passes parsed cleanly.

    For two-pass statistics ONLY (arbitration behavior, reflex/planner agreement).
    Never use this to gate terminal-action distributions: a valid planner win over
    a garbled reflex IS a genuine decision, and excluding it would throw away real
    behavior and bias the distribution toward whatever the parser found easy.
    """
    if not is_admissible_decision(node):
        return False
    return all(_meta(_choice(node, k)).get("parse_status", "ok") == "ok"
               for k in ("reflex_choice", "planner_choice"))


def run_decision_census(nodes: list) -> dict:
    """Count decisions vs. non-decisions over a run, with reasons.

    The reported artifact. `non_decision_rate` is what the preregistered
    admissibility bounds are charged against, and `reasons` is what makes a
    differential rate across conditions attributable rather than merely visible.
    """
    n_total = n_admissible = 0
    reasons: dict = {}
    for node in nodes or []:
        n_total += 1
        verdict = decision_admissibility(node)
        if verdict["admissible"]:
            n_admissible += 1
        else:
            reasons[verdict["reason"]] = reasons.get(verdict["reason"], 0) + 1
    n_non_decision = n_total - n_admissible
    return {
        "n_total": n_total,
        "n_admissible": n_admissible,
        "n_non_decision": n_non_decision,
        # None, not 0.0, on an empty run: an empty census has no rate, and a
        # reported 0.0 would read as "measured, clean".
        "non_decision_rate": round(n_non_decision / n_total, 6) if n_total else None,
        "reasons": reasons,
        "admissibility_version": DECISION_ADMISSIBILITY_VERSION,
    }


def load_decision_nodes(run_dir: str) -> list:
    """Convenience reader: the decision nodes of a run, in recorded order.

    Mirrors metrics._read's node selection so callers need not duplicate the
    record-kind filter. Read-only; opens nothing but decisions.jsonl.
    """
    import json
    import os

    nodes = []
    with open(os.path.join(run_dir, "decisions.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            ev = json.loads(line)
            if ev.get("kind") == "decision_node":
                nodes.append(ev["data"])
    return nodes
