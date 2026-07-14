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
        super().__init__({
            "society_seed_version": SOCIETY_SEED_VERSION,
            "tick_index": tick_index,
            "previous_society_tick_hash": previous_society_tick_hash,
            "trust_edges": dict(trust_edges),
            "private_facts": dict(private_facts),
            "enforcement_event_count": enforcement_event_count,
            "scheduler_position_range": list(scheduler_position_range),
        })


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
    """(position, agent_key) -> the set of visible entity ids from that agent's
    recorded ACTOR observation."""
    run_json = _read(run_dir, "run.json")
    key_of = {b: k for k, b in run_json["observers"].items()}
    out = {}
    for r in _read_lines(run_dir, "observations.jsonl"):
        out[(r["scheduler_position"], key_of[r["observer_body_id"]])] = set(
            r["actor_content"]["content"]["visible_entity_identities"])
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
            trust[_pair_key(recip, giver)] += 1
            trust_updates.append({"scheduler_position": pos, "kind": "give",
                                  "edge": _pair_key(recip, giver), "delta": +1,
                                  "provenance": "recipient perceives own receipt"})
        elif eff["action"] == "take" and eff["object_instance_id"] == token:
            taker = key_of[eff["agent_body_id"]]
            for other in AGENTS:
                if other == taker:
                    continue
                seen = actor.get((decided_at, other), set())
                if ids[taker] in seen and token in seen:
                    trust[_pair_key(other, taker)] -= 1
                    trust_updates.append({
                        "scheduler_position": pos, "kind": "witnessed_take",
                        "edge": _pair_key(other, taker), "delta": -1,
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
