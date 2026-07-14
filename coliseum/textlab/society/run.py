"""Minimal Society Seed runner + reports (OWNER SC-LC 2026-07-14).

execute_society_seed drives ONLY integrated production paths: the spatial runner
(society_seed_v1) → the society derivation → deterministic society evidence.
The run directory is a COMPLETE spatial 0.2 evidence set (the TRS projector
works unchanged) PLUS society.jsonl + society_report.json. The replay gate
re-executes from nothing and byte-compares ALL EIGHT files. No wall-clock or
host entropy anywhere; persistence is the run directory alone.
"""
from __future__ import annotations

import json
import os

from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.schema import canonical_json
from coliseum.textlab.spatial.run import execute_spatial_run
from coliseum.textlab.society.seed import (AGENTS, CLAIM_CEILING, ORDERED_PAIRS,
                                           PRIVATE_FACT, PRIVATE_FACT_HOLDER,
                                           SCENARIO, SEED, TICKS,
                                           SocietyRunManifest,
                                           assert_script_rule_clean,
                                           derive_society, _pair_key, _read)

SOCIETY_EVIDENCE_FILES = ("run.json", "chain.jsonl", "transitions.jsonl",
                          "observations.jsonl", "activations.jsonl",
                          "closure.json", "society.jsonl", "society_report.json")


def _terminal_token_location(run_dir):
    """The token's authoritative location at the terminal state (world truth)."""
    run_json = _read(run_dir, "run.json")
    body = run_json["observers"][sorted(run_json["observers"])[0]]
    terminal_pos = run_json["chain_length"] - 1
    token = run_json["instance_ids"]["token"]
    with open(os.path.join(run_dir, "observations.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r["observer_body_id"] == body and \
                    r["scheduler_position"] == terminal_pos:
                for p in r["privileged_content"]["content"][
                        "observable_state_projection"]["authoritative_placements"]:
                    if p["entity_id"] == token:
                        return p["location"]
    raise ContentRecordError("terminal token location not found")


def _society_outcome(run_dir, derived):
    """The society-level OUTCOME report (no human-fidelity/simulation claim)."""
    run_json = derived["run_json"]
    ids = run_json["instance_ids"]
    rid = {v: k for k, v in ids.items()}
    loc = _terminal_token_location(run_dir)
    token_where = (rid.get(loc.get("room_instance_id"))
                   if loc["tag"] == "in_room"
                   else "held_by:" + {b: k for k, b in run_json["observers"].items()}
                   .get(loc.get("agent_body_id"), "?"))
    return {
        "society_seed_version": derived["tick_states"][0].content["society_seed_version"],
        "scenario": SCENARIO, "seed": run_json["seed"], "ticks": TICKS,
        "final_trust_edges": derived["trust"],
        "trust_update_count": len(derived["trust_updates"]),
        "enforcement_event_count": len(derived["enforcement"]),
        "institutional_rule": (derived["enforcement"][0]["rule"]
                               if derived["enforcement"] else None),
        "token_terminal_location": token_where,
        "private_fact": {PRIVATE_FACT_HOLDER: {PRIVATE_FACT: True}},
        "claim_ceiling": CLAIM_CEILING,
    }


def execute_society_seed(seed=SEED, out_root=None):
    """Run the seed: spatial run → society derivation → society evidence."""
    if out_root is None:
        out_root = os.path.join("logs", "society-runs")
    spatial = execute_spatial_run(SCENARIO, seed, out_root=out_root)
    run_dir = os.path.join(out_root, spatial["run_id"])
    # the committed script must be institutionally rule-clean (no committed move
    # is a blocked move) — the run-side counterpart of build-time refusal.
    assert_script_rule_clean(run_dir)
    derived = derive_society(run_dir)
    manifest = SocietyRunManifest(
        spatial_source_evidence_id=_spatial_source_evidence_id(run_dir),
        scheduler_manifest_id=spatial["manifest_id"],
        ordered_tick_state_ids=[t.id for t in derived["tick_states"]],
        enforcement_trace_commitment=derived["enforcement_commitment"],
        final_trust_edges=derived["trust"])
    # society.jsonl: the tick chain + trust updates (with provenance) + trace.
    with open(os.path.join(run_dir, "society.jsonl"), "w", encoding="utf-8") as fh:
        fh.write(canonical_json({"record": "society_run_manifest",
                                 "id": manifest.id,
                                 "content": manifest.content}) + "\n")
        for ts in derived["tick_states"]:
            fh.write(canonical_json({"record": "society_tick_state",
                                     "id": ts.id, "content": ts.content}) + "\n")
        for u in derived["trust_updates"]:
            fh.write(canonical_json({"record": "trust_update", **u}) + "\n")
        for e in derived["enforcement"]:
            fh.write(canonical_json({"record": "enforcement_event", **e}) + "\n")
    outcome = _society_outcome(run_dir, derived)
    with open(os.path.join(run_dir, "society_report.json"), "w", encoding="utf-8") as fh:
        fh.write(canonical_json(outcome) + "\n")
    return {"run_id": spatial["run_id"], "run_dir": run_dir,
            "spatial": spatial, "society_run_manifest_id": manifest.id,
            "outcome": outcome, "tick_state_ids": [t.id for t in derived["tick_states"]]}


def _spatial_source_evidence_id(run_dir):
    from coliseum.textlab.training.spatial_trajectory_projection import (
        _EVIDENCE_FILES, _sha256_file)
    from coliseum.textlab.training.spatial_records import SpatialSourceEvidenceBinding
    run_json = _read(run_dir, "run.json")
    return SpatialSourceEvidenceBinding(
        run_id=run_json["run_id"],
        evidence_file_hashes={n: _sha256_file(os.path.join(run_dir, n))
                              for n in _EVIDENCE_FILES}).id


def replay_society_seed(run_id, out_root=None, scratch_root=None):
    """The eight-file replay gate: re-execute the seed from nothing and
    byte-compare EVERY evidence file (spatial six + society two)."""
    import tempfile
    if out_root is None:
        out_root = os.path.join("logs", "society-runs")
    run_dir = os.path.join(out_root, run_id)
    recorded = _read(run_dir, "run.json")
    scratch = scratch_root or tempfile.mkdtemp(prefix="society-replay-")
    fresh = execute_society_seed(recorded["seed"], out_root=scratch)
    if fresh["run_id"] != run_id:
        return False, f"replay derived a different run identity: {fresh['run_id']}"
    for name in SOCIETY_EVIDENCE_FILES:
        a = open(os.path.join(run_dir, name), "rb").read()
        b = open(os.path.join(scratch, run_id, name), "rb").read()
        if a != b:
            return False, f"{name} is not byte-identical"
    return True, f"byte-identical: {', '.join(SOCIETY_EVIDENCE_FILES)}"


# --------------------------------------------------------------------- reports
_ACTOR_REPORT_KEYS = frozenset({"agent", "observed_positions", "visible_entity_counts",
                                "outgoing_trust", "claim_ceiling"})


def assert_actor_report_schema(report):
    """Closed exact actor-safe report schema: exactly the permitted keys; the
    outgoing_trust maps ONLY this agent's own edges; no other agent's trust, no
    private facts of others, no privileged content, no chain hashes."""
    if not isinstance(report, dict) or set(report) != _ACTOR_REPORT_KEYS:
        raise ContentRecordError("actor report must have exactly the permitted keys")
    agent = report["agent"]
    if agent not in AGENTS:
        raise ContentRecordError("unknown agent in actor report")
    if set(report["outgoing_trust"]) != {_pair_key(agent, j)
                                         for j in AGENTS if j != agent}:
        raise ContentRecordError(
            "outgoing_trust must be exactly this agent's own outgoing edges")
    if report["claim_ceiling"] != CLAIM_CEILING:
        raise ContentRecordError("actor report claim_ceiling must be the fixed ceiling")


def actor_safe_report(run_dir, agent):
    """The per-agent ACTOR-SAFE report: derived exclusively from that agent's own
    recorded actor observations + its own outgoing trust edges."""
    if agent not in AGENTS:
        raise ContentRecordError(f"unknown agent {agent!r}")
    run_json = _read(run_dir, "run.json")
    body = run_json["observers"][agent]
    derived = derive_society(run_dir)
    observed, counts = [], {}
    with open(os.path.join(run_dir, "observations.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r["observer_body_id"] != body:
                continue
            pos = r["scheduler_position"]
            observed.append(pos)
            counts[str(pos)] = len(
                r["actor_content"]["content"]["visible_entity_identities"])
    report = {"agent": agent, "observed_positions": sorted(observed),
              "visible_entity_counts": counts,
              "outgoing_trust": {_pair_key(agent, j): derived["trust"][_pair_key(agent, j)]
                                 for j in AGENTS if j != agent},
              "claim_ceiling": CLAIM_CEILING}
    assert_actor_report_schema(report)
    return report


def privileged_report(run_dir):
    """The PRIVILEGED report: full trust matrix, facts, enforcement trace, chain."""
    derived = derive_society(run_dir)
    return {"scenario": SCENARIO, "trust_matrix": derived["trust"],
            "trust_updates": derived["trust_updates"],
            "private_facts": {PRIVATE_FACT_HOLDER: {PRIVATE_FACT: True}},
            "enforcement_trace": derived["enforcement"],
            "enforcement_trace_commitment": derived["enforcement_commitment"],
            "tick_state_ids": [t.id for t in derived["tick_states"]],
            "claim_ceiling": CLAIM_CEILING}
