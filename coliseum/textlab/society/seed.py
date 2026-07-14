"""Minimal Society Seed derivation (OWNER SC-LC 2026-07-14; design integrated
001238). The society layer is DERIVED evidence computed purely from the spatial
run's evidence bytes + the closed seed definition — it must re-derive
byte-identically (a counterfeit society chain over genuine spatial evidence is
refused by canonical re-derivation, per the audit-001219/001225 discipline).

Nothing here mutates the spatial substrate: trust, ticks, and the institutional
enforcement trace never enter any world state, observation, candidate set, or
scheduler input.
"""
from __future__ import annotations

import json
import os

from coliseum.textlab._content_record import (ContentRecord, ContentRecordError,
                                              content_id)
from coliseum.textlab.society.rules import (INSTITUTION_TOKEN_STAYS_IN_A,
                                            institutionally_blocked)

SOCIETY_SEED_VERSION = "1"
SCENARIO = "society_seed_v1"
SEED = 42
TICKS = 8
AGENTS = ("ada", "bo", "cy")
ORDERED_PAIRS = tuple((i, j) for i in AGENTS for j in AGENTS if i != j)
PRIVATE_FACT_HOLDER = "cy"
PRIVATE_FACT = "gem_in_box"
CLAIM_CEILING = ("the scripted seed demonstrates deterministic room separation, "
                 "private information, institutional enforcement, trust "
                 "bookkeeping, and counterfactual replay in one bounded run; it "
                 "makes no human-fidelity or society-simulation claim")


def _pair_key(i, j):
    return f"{i}->{j}"


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _is_hex64(v):
    return isinstance(v, str) and len(v) == 64 and \
        all(c in "0123456789abcdef" for c in v)


def _validate_private_facts(private_facts):
    """Exactly {holder-agent: {fact-name: bool}} for known agents (empty ok)."""
    if not isinstance(private_facts, dict):
        raise ContentRecordError("private_facts must be a dict")
    for holder, facts in private_facts.items():
        if holder not in AGENTS or not isinstance(facts, dict):
            raise ContentRecordError("private_facts keys must be agents -> fact dicts")
        for name, val in facts.items():
            if not isinstance(name, str) or not name or not isinstance(val, bool):
                raise ContentRecordError("each private fact must be name -> bool")


# ----------------------------------------------------------------- records
class SocietyTickState(ContentRecord):
    __slots__ = ()
    DOMAIN = "society.tick_state.v1"
    ID_FIELD = "society_tick_state_id"

    def __init__(self, tick_index, previous_society_tick_hash, trust_edges,
                 private_facts, enforcement_event_count, scheduler_position_range):
        if not isinstance(tick_index, int) or isinstance(tick_index, bool) \
                or tick_index < 0:
            raise ContentRecordError("tick_index must be a non-negative int")
        if (tick_index == 0) != (previous_society_tick_hash is None):
            raise ContentRecordError(
                "previous_society_tick_hash must be null exactly at tick 0")
        if set(trust_edges) != {_pair_key(i, j) for i, j in ORDERED_PAIRS}:
            raise ContentRecordError("trust_edges must be exactly the six ordered pairs")
        if any(not isinstance(v, int) or isinstance(v, bool)
               for v in trust_edges.values()):
            raise ContentRecordError("every trust edge value must be an int")
        if previous_society_tick_hash is not None and (
                not isinstance(previous_society_tick_hash, str) or
                len(previous_society_tick_hash) != 64 or
                any(c not in "0123456789abcdef" for c in previous_society_tick_hash)):
            raise ContentRecordError(
                "previous_society_tick_hash must be 64 lowercase hex chars or null")
        if tick_index >= TICKS:
            raise ContentRecordError(f"tick_index must be < {TICKS}")
        _validate_private_facts(private_facts)
        if not isinstance(enforcement_event_count, int) or \
                isinstance(enforcement_event_count, bool) or enforcement_event_count < 0:
            raise ContentRecordError("enforcement_event_count must be a non-negative int")
        if not isinstance(scheduler_position_range, (list, tuple)) or \
                len(scheduler_position_range) != 2 or \
                any(not isinstance(x, int) or isinstance(x, bool)
                    for x in scheduler_position_range) or \
                scheduler_position_range[0] > scheduler_position_range[1]:
            raise ContentRecordError(
                "scheduler_position_range must be [lo, hi] ints with lo <= hi")
        super().__init__({
            "society_seed_version": SOCIETY_SEED_VERSION,
            "tick_index": tick_index,
            "previous_society_tick_hash": previous_society_tick_hash,
            "trust_edges": dict(trust_edges),
            "private_facts": dict(private_facts),
            "enforcement_event_count": enforcement_event_count,
            "scheduler_position_range": list(scheduler_position_range),
        })


class SocietySourceEvidenceBinding(ContentRecord):
    """Content-addresses the EIGHT society evidence files (the spatial six plus
    society.jsonl + society_report.json) — the derived-evidence provenance
    anchor. Domain-separated from the spatial + calibration bindings."""
    __slots__ = ()
    DOMAIN = "trs.source_evidence.society.v1"
    ID_FIELD = "source_evidence_id"

    def __init__(self, run_id, evidence_file_hashes):
        if not isinstance(run_id, str) or not run_id:
            raise ContentRecordError("run_id must be a non-empty string")
        expected = {"run.json", "chain.jsonl", "transitions.jsonl",
                    "observations.jsonl", "activations.jsonl", "closure.json",
                    "society.jsonl", "society_report.json"}
        if not isinstance(evidence_file_hashes, dict) or \
                set(evidence_file_hashes) != expected:
            raise ContentRecordError(
                "evidence_file_hashes must bind exactly the eight society files")
        for h in evidence_file_hashes.values():
            if not isinstance(h, str) or len(h) != 64 or \
                    any(c not in "0123456789abcdef" for c in h):
                raise ContentRecordError("each hash must be 64 lowercase hex chars")
        super().__init__({
            "society_seed_version": SOCIETY_SEED_VERSION,
            "run_id": run_id,
            "evidence_file_hashes": dict(evidence_file_hashes),
        })


class SocietyOutcomeReport(ContentRecord):
    """The closed, validated society-level OUTCOME record (design §8): the final
    trust matrix, token terminal location, enforcement count, private fact, the
    canonical FORK divergence summary, and the FIXED claim ceiling. Any other
    claim string, or a missing fork summary, refuses."""
    __slots__ = ()
    DOMAIN = "society.outcome_report.v1"
    ID_FIELD = "society_outcome_report_id"

    _KEYS = frozenset({"society_seed_version", "scenario", "seed", "ticks",
                       "final_trust_edges", "trust_update_count",
                       "enforcement_event_count", "institutional_rule",
                       "token_terminal_location", "private_fact",
                       "fork_divergence_summary", "claim_ceiling"})

    def __init__(self, payload):
        if not isinstance(payload, dict) or set(payload) != self._KEYS:
            raise ContentRecordError(
                "society outcome report must have exactly the closed key set")
        if payload["claim_ceiling"] != CLAIM_CEILING:
            raise ContentRecordError("outcome claim_ceiling must be the fixed ceiling")
        if payload["society_seed_version"] != SOCIETY_SEED_VERSION:
            raise ContentRecordError("unsupported society_seed_version")
        if payload["scenario"] != SCENARIO:
            raise ContentRecordError("outcome scenario must be the society seed")
        if not _is_int(payload["seed"]) or payload["seed"] < 0:
            raise ContentRecordError("seed must be a non-negative int")
        if payload["ticks"] != TICKS:
            raise ContentRecordError(f"ticks must be {TICKS}")
        edges = payload["final_trust_edges"]
        if set(edges) != {_pair_key(i, j) for i, j in ORDERED_PAIRS} or \
                any(not _is_int(v) for v in edges.values()):
            raise ContentRecordError(
                "final_trust_edges must be the six ordered pairs of ints")
        for name in ("trust_update_count", "enforcement_event_count"):
            if not _is_int(payload[name]) or payload[name] < 0:
                raise ContentRecordError(f"{name} must be a non-negative int")
        rule = payload["institutional_rule"]
        if rule is not None and (not isinstance(rule, str) or not rule):
            raise ContentRecordError("institutional_rule must be null or a string")
        if not isinstance(payload["token_terminal_location"], str) or \
                not payload["token_terminal_location"]:
            raise ContentRecordError("token_terminal_location must be a non-empty string")
        _validate_private_facts(payload["private_fact"])
        fs = payload["fork_divergence_summary"]
        if not isinstance(fs, dict) or set(fs) != {
                "intervention_id", "matched_pair_id", "divergence_report_id",
                "fork_position", "first_divergent_coordinate",
                "per_agent_perception_divergence"}:
            raise ContentRecordError(
                "fork_divergence_summary must carry the canonical fork material")
        if not isinstance(fs["intervention_id"], str) or not fs["intervention_id"] or \
                not _is_hex64(fs["matched_pair_id"]) or \
                not _is_hex64(fs["divergence_report_id"]):
            raise ContentRecordError("fork summary ids must be well-formed")
        if not _is_int(fs["fork_position"]) or \
                not _is_int(fs["first_divergent_coordinate"]) or \
                fs["first_divergent_coordinate"] <= fs["fork_position"]:
            raise ContentRecordError(
                "fork summary divergence must be an int beyond the fork position")
        pad = fs["per_agent_perception_divergence"]
        if not isinstance(pad, dict) or set(pad) != set(AGENTS) or \
                any(v is not None and not _is_int(v) for v in pad.values()):
            raise ContentRecordError(
                "per_agent_perception_divergence must map every agent to an int or null")
        super().__init__(dict(payload))


class SocietyRunManifest(ContentRecord):
    __slots__ = ()
    DOMAIN = "society.run_manifest.v1"
    ID_FIELD = "society_run_manifest_id"

    def __init__(self, spatial_source_evidence_id, scheduler_manifest_id,
                 ordered_tick_state_ids, enforcement_trace_commitment,
                 final_trust_edges):
        if not isinstance(ordered_tick_state_ids, list) or \
                len(ordered_tick_state_ids) != TICKS:
            raise ContentRecordError(f"ordered_tick_state_ids must have {TICKS} ids")
        super().__init__({
            "society_seed_version": SOCIETY_SEED_VERSION,
            "spatial_source_evidence_id": spatial_source_evidence_id,
            "scheduler_manifest_id": scheduler_manifest_id,
            "ordered_tick_state_ids": list(ordered_tick_state_ids),
            "enforcement_trace_commitment": enforcement_trace_commitment,
            "final_trust_edges": dict(final_trust_edges),
        })


# ------------------------------------------------- rule-clean verification
def assert_script_rule_clean(run_dir):
    """Every COMMITTED transition must be institutionally legal at ITS OWN prior
    state (no committed move is a blocked move). A committed blocked effect
    refuses — the run-side counterpart of the build-time refusal in the design
    §3."""
    run_json = _read(run_dir, "run.json")
    ids = run_json["instance_ids"]
    states = _privileged_states_by_world_id(run_dir)
    for t in _read_lines(run_dir, "transitions.jsonl"):
        eff = t["content"]["effect"]
        prior = states.get(t["content"]["prior_state_hash"])
        if prior is None:
            continue
        if institutionally_blocked(eff, _fake_state(prior), ids["token"],
                                   ids["room_A"]):
            raise ContentRecordError(
                f"committed transition {eff.get('action')} is institutionally "
                "blocked at its prior state — the committed script is not rule-clean")


class _fake_state:
    """Minimal WorldState-shaped wrapper for the rule predicate over recorded
    placements (the predicate reads only .content['placements'])."""
    def __init__(self, placements):
        self.content = {"placements": placements}


# ------------------------------------------------------ evidence readers
def _read(run_dir, name):
    with open(os.path.join(run_dir, name), encoding="utf-8") as fh:
        return json.load(fh)


def _read_lines(run_dir, name):
    with open(os.path.join(run_dir, name), encoding="utf-8") as fh:
        return [json.loads(l) for l in fh]


def _round_by_position(run_dir):
    return {r["content"]["scheduler_position"]: r["content"]["round_index"]
            for r in _read_lines(run_dir, "chain.jsonl")}


def _privileged_states_by_world_id(run_dir):
    """world_state_id -> authoritative placements (world truth), from one
    observer's privileged rows."""
    run_json = _read(run_dir, "run.json")
    body = run_json["observers"][sorted(run_json["observers"])[0]]
    out = {}
    for r in _read_lines(run_dir, "observations.jsonl"):
        if r["observer_body_id"] == body:
            out[r["world_state_id"]] = r["privileged_content"]["content"][
                "observable_state_projection"]["authoritative_placements"]
    return out


def _privileged_states_by_position(run_dir):
    """position -> authoritative placements (world truth), from one observer's
    privileged rows."""
    run_json = _read(run_dir, "run.json")
    body = run_json["observers"][sorted(run_json["observers"])[0]]
    out = {}
    for r in _read_lines(run_dir, "observations.jsonl"):
        if r["observer_body_id"] == body:
            out[r["scheduler_position"]] = r["privileged_content"]["content"][
                "observable_state_projection"]["authoritative_placements"]
    return out


def _actor_view(run_dir):
    """(position, agent_key) -> (visible entity id set, actor_observation_id) from
    that agent's recorded ACTOR observation."""
    run_json = _read(run_dir, "run.json")
    key_of = {b: k for k, b in run_json["observers"].items()}
    out = {}
    for r in _read_lines(run_dir, "observations.jsonl"):
        out[(r["scheduler_position"], key_of[r["observer_body_id"]])] = (
            set(r["actor_content"]["content"]["visible_entity_identities"]),
            r["actor_observation_id"])
    return out


# ------------------------------------------------------ the derivation
def derive_society(run_dir):
    """Compute the society tick chain, trust matrix, enforcement trace, and the
    per-update provenance — purely from the spatial evidence. Deterministic."""
    run_json = _read(run_dir, "run.json")
    if run_json["scenario"] != SCENARIO:
        raise ContentRecordError("not a society_seed_v1 run")
    ids = run_json["instance_ids"]
    key_of = {b: k for k, b in run_json["observers"].items()}
    round_by_pos = _round_by_position(run_dir)
    states = _privileged_states_by_position(run_dir)
    actor = _actor_view(run_dir)
    token, room_a = ids["token"], ids["room_A"]

    trust = {_pair_key(i, j): 0 for i, j in ORDERED_PAIRS}
    trust_updates = []            # provenance-carrying
    enforcement = []              # (position, blocked action_id)

    # enforcement trace: blocked CANDIDATES at every activation (from the recorded
    # candidate universe; the committed action need not be the blocked one).
    for row in _read_lines(run_dir, "activations.jsonl"):
        if "activation" not in row:
            continue
        pos = row["scheduler_position"]
        pre = states.get(pos - 1)
        if pre is None:
            continue
        for cand in row.get("candidate_universe", []):
            if institutionally_blocked(cand["effect"], _fake_state(pre), token, room_a):
                enforcement.append({"scheduler_position": pos,
                                    "rule": INSTITUTION_TOKEN_STAYS_IN_A,
                                    "blocked_action_id": cand["action_id"]})

    # trust: give (+1 recipient->giver) and witnessed take (-1 witness->taker),
    # ordered by scheduler position of the committed transition.
    transitions = sorted(_read_lines(run_dir, "transitions.jsonl"),
                         key=lambda t: t["content"]["logical_step"])
    for t in transitions:
        eff = t["content"]["effect"]
        pos = t["content"]["logical_step"]
        decided_at = pos - 1
        if eff["action"] == "give" and eff["object_instance_id"] == token:
            giver = key_of[eff["agent_body_id"]]
            recip = key_of[eff["recipient_agent_body_id"]]
            # the recipient perceives its own receipt: bind to the recipient's
            # actor observation of the POST-transfer state (position ``pos``).
            _seen, obs_id = actor.get((pos, recip), (set(), None))
            if obs_id is None:
                raise ContentRecordError(
                    "no recipient actor observation to justify a give update")
            trust[_pair_key(recip, giver)] += 1
            trust_updates.append({"scheduler_position": pos, "kind": "give",
                                  "edge": _pair_key(recip, giver), "delta": +1,
                                  "actor_observation_id": obs_id,
                                  "provenance": "recipient perceives own receipt"})
        elif eff["action"] == "take" and eff["object_instance_id"] == token:
            taker = key_of[eff["agent_body_id"]]
            for other in AGENTS:
                if other == taker:
                    continue
                seen, obs_id = actor.get((decided_at, other), (set(), None))
                if ids[taker] in seen and token in seen:
                    trust[_pair_key(other, taker)] -= 1
                    trust_updates.append({
                        "scheduler_position": pos, "kind": "witnessed_take",
                        "edge": _pair_key(other, taker), "delta": -1,
                        "actor_observation_id": obs_id,
                        "provenance": f"actor view of {other} at pos {decided_at} "
                                      "contains taker and token"})

    # tick chain: one record per round 0..TICKS-1.
    positions_by_round = {}
    for pos, rnd in round_by_pos.items():
        positions_by_round.setdefault(rnd, []).append(pos)
    if sorted(positions_by_round) != list(range(TICKS)):
        raise ContentRecordError(
            f"society seed must span exactly {TICKS} ticks (rounds 0..{TICKS-1}), "
            f"got rounds {sorted(positions_by_round)}")

    # trust + enforcement counts are cumulative THROUGH each tick's positions.
    tick_states = []
    prev_hash = None
    running_trust = {k: 0 for k in trust}
    upd_by_pos = {}
    for u in trust_updates:
        upd_by_pos.setdefault(u["scheduler_position"], []).append(u)
    enf_by_pos = {}
    for e in enforcement:
        enf_by_pos.setdefault(e["scheduler_position"], []).append(e)
    enf_running = 0
    for rnd in range(TICKS):
        rng = sorted(positions_by_round[rnd])
        for pos in range(rng[0], rng[-1] + 1):
            for u in upd_by_pos.get(pos, []):
                running_trust[u["edge"]] += u["delta"]
            enf_running += len(enf_by_pos.get(pos, []))
        ts = SocietyTickState(
            tick_index=rnd, previous_society_tick_hash=prev_hash,
            trust_edges=dict(running_trust),
            private_facts={PRIVATE_FACT_HOLDER: {PRIVATE_FACT: True}},
            enforcement_event_count=enf_running,
            scheduler_position_range=[rng[0], rng[-1]])
        tick_states.append(ts)
        prev_hash = ts.id

    enforcement_commitment = content_id(
        "society.enforcement_trace.v1",
        {"events": enforcement}, "enforcement_trace_commitment")
    return {
        "run_json": run_json,
        "tick_states": tick_states,
        "trust": trust,
        "trust_updates": trust_updates,
        "enforcement": enforcement,
        "enforcement_commitment": enforcement_commitment,
    }
