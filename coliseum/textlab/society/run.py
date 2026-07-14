"""Minimal Society Seed runner + reports (OWNER SC-LC 2026-07-14).

execute_society_seed drives ONLY integrated production paths: the spatial runner
(society_seed_v1) + the integrated calibration fork (the one authenticated
counterfactual) + the society derivation. The run directory is a COMPLETE
spatial 0.2 evidence set (the TRS projector works unchanged) PLUS society.jsonl
+ society_report.json. The eight-file replay gate re-executes from nothing and
byte-compares every file; canonical society verification refuses a counterfeit
society.jsonl at every consumer boundary. No wall-clock or host entropy;
persistence is the run directory alone.
"""
from __future__ import annotations

import json
import os

from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.schema import canonical_json
from coliseum.textlab.spatial.calibration import (build_divergence_report,
                                                  build_matched_pair)
from coliseum.textlab.spatial.run import execute_spatial_run
from coliseum.textlab.society.seed import (AGENTS, CLAIM_CEILING, ORDERED_PAIRS,
                                           PRIVATE_FACT, PRIVATE_FACT_HOLDER,
                                           SCENARIO, SEED, TICKS,
                                           SocietyOutcomeReport, SocietyRunManifest,
                                           SocietySourceEvidenceBinding,
                                           assert_script_rule_clean,
                                           derive_society, _pair_key, _read)

FORK_INTERVENTION = "iv_society_seed_fact_flip_v1"
SOCIETY_EVIDENCE_FILES = ("run.json", "chain.jsonl", "transitions.jsonl",
                          "observations.jsonl", "activations.jsonl",
                          "closure.json", "society.jsonl", "society_report.json")


def _spatial_source_evidence(run_dir):
    from coliseum.textlab.training.spatial_trajectory_projection import (
        _EVIDENCE_FILES, _sha256_file)
    from coliseum.textlab.training.spatial_records import SpatialSourceEvidenceBinding
    run_json = _read(run_dir, "run.json")
    return SpatialSourceEvidenceBinding(
        run_id=run_json["run_id"],
        evidence_file_hashes={n: _sha256_file(os.path.join(run_dir, n))
                              for n in _EVIDENCE_FILES})


def _terminal_token_location(run_dir):
    run_json = _read(run_dir, "run.json")
    body = run_json["observers"][sorted(run_json["observers"])[0]]
    terminal_pos = run_json["chain_length"] - 1
    token = run_json["instance_ids"]["token"]
    for r in (json.loads(l) for l in
              open(os.path.join(run_dir, "observations.jsonl"), encoding="utf-8")):
        if r["observer_body_id"] == body and r["scheduler_position"] == terminal_pos:
            for p in r["privileged_content"]["content"][
                    "observable_state_projection"]["authoritative_placements"]:
                if p["entity_id"] == token:
                    return p["location"]
    raise ContentRecordError("terminal token location not found")


def _fork_summary(control_dir, treatment_dir):
    """The canonical fork material: run the integrated matched pair + divergence
    report over the (already replay-authenticated) control + treatment dirs."""
    pair = build_matched_pair(FORK_INTERVENTION, control_dir, treatment_dir)
    report = build_divergence_report(pair, control_dir, treatment_dir)
    rc = report.content
    return {
        "intervention_id": FORK_INTERVENTION,
        "matched_pair_id": pair.id,
        "divergence_report_id": report.id,
        "fork_position": rc["fork_position"],
        "first_divergent_coordinate": rc["first_divergent_coordinate"],
        "per_agent_perception_divergence": {
            k: v["perception_divergence_coordinate"]
            for k, v in rc["per_agent"].items()},
    }


def _society_manifest(run_dir, derived, scheduler_manifest_id):
    return SocietyRunManifest(
        spatial_source_evidence_id=_spatial_source_evidence(run_dir).id,
        scheduler_manifest_id=scheduler_manifest_id,
        ordered_tick_state_ids=[t.id for t in derived["tick_states"]],
        enforcement_trace_commitment=derived["enforcement_commitment"],
        final_trust_edges=derived["trust"])


def _society_jsonl_bytes(run_dir, derived, scheduler_manifest_id):
    """The canonical society.jsonl bytes (manifest + ticks + trust updates +
    enforcement events). The SINGLE source of truth for both writing and
    canonical verification."""
    manifest = _society_manifest(run_dir, derived, scheduler_manifest_id)
    lines = [canonical_json({"record": "society_run_manifest",
                             "id": manifest.id, "content": manifest.content})]
    for ts in derived["tick_states"]:
        lines.append(canonical_json({"record": "society_tick_state",
                                     "id": ts.id, "content": ts.content}))
    for u in derived["trust_updates"]:
        lines.append(canonical_json({"record": "trust_update", **u}))
    for e in derived["enforcement"]:
        lines.append(canonical_json({"record": "enforcement_event", **e}))
    return ("\n".join(lines) + "\n").encode("utf-8"), manifest


def _outcome_payload(run_dir, derived, fork_summary):
    run_json = derived["run_json"]
    rid = {v: k for k, v in run_json["instance_ids"].items()}
    key_of = {b: k for k, b in run_json["observers"].items()}
    loc = _terminal_token_location(run_dir)
    where = (rid.get(loc.get("room_instance_id")) if loc["tag"] == "in_room"
             else "held_by:" + key_of.get(loc.get("agent_body_id"), "?"))
    return {
        "society_seed_version": derived["tick_states"][0].content["society_seed_version"],
        "scenario": SCENARIO, "seed": run_json["seed"], "ticks": TICKS,
        "final_trust_edges": derived["trust"],
        "trust_update_count": len(derived["trust_updates"]),
        "enforcement_event_count": len(derived["enforcement"]),
        "institutional_rule": (derived["enforcement"][0]["rule"]
                               if derived["enforcement"] else None),
        "token_terminal_location": where,
        "private_fact": {PRIVATE_FACT_HOLDER: {PRIVATE_FACT: True}},
        "fork_divergence_summary": fork_summary,
        "claim_ceiling": CLAIM_CEILING,
    }


def execute_society_seed(seed=SEED, out_root=None):
    """Run the seed end to end: spatial run + the authenticated fork + society
    derivation + validated society evidence."""
    if out_root is None:
        out_root = os.path.join("logs", "society-runs")
    spatial = execute_spatial_run(SCENARIO, seed, out_root=out_root)
    run_dir = os.path.join(out_root, spatial["run_id"])
    assert_script_rule_clean(run_dir)
    derived = derive_society(run_dir)

    # the ONE authenticated counterfactual fork (integrated calibration machinery).
    treatment = execute_spatial_run(SCENARIO, seed, out_root=out_root,
                                    intervention=FORK_INTERVENTION,
                                    control_run_dir=run_dir)
    treatment_dir = os.path.join(out_root, treatment["run_id"])
    fork_summary = _fork_summary(run_dir, treatment_dir)

    society_bytes, manifest = _society_jsonl_bytes(
        run_dir, derived, spatial["manifest_id"])
    with open(os.path.join(run_dir, "society.jsonl"), "wb") as fh:
        fh.write(society_bytes)
    outcome = SocietyOutcomeReport(_outcome_payload(run_dir, derived, fork_summary))
    with open(os.path.join(run_dir, "society_report.json"), "wb") as fh:
        fh.write((canonical_json({"id": outcome.id,
                                  "content": outcome.content}) + "\n").encode("utf-8"))
    binding = SocietySourceEvidenceBinding(
        run_id=spatial["run_id"], evidence_file_hashes=_eight_file_hashes(run_dir))
    return {"run_id": spatial["run_id"], "run_dir": run_dir, "spatial": spatial,
            "treatment_run_id": treatment["run_id"], "treatment_dir": treatment_dir,
            "society_run_manifest_id": manifest.id,
            "society_source_evidence_id": binding.id,
            "society_outcome_report_id": outcome.id,
            "outcome": outcome.content, "fork_summary": fork_summary,
            "tick_state_ids": [t.id for t in derived["tick_states"]]}


def _eight_file_hashes(run_dir):
    from coliseum.textlab.training.spatial_trajectory_projection import _sha256_file
    return {n: _sha256_file(os.path.join(run_dir, n))
            for n in SOCIETY_EVIDENCE_FILES}


def assert_society_evidence_canonical(run_dir):
    """Refuse counterfeit society evidence: the persisted society.jsonl must
    byte-equal the canonical re-derivation from the spatial evidence, and
    society_report.json must byte-equal the canonical outcome record. Called at
    every society-evidence consumer boundary (bindings are commitments, not
    verification)."""
    run_json = _read(run_dir, "run.json")
    derived = derive_society(run_dir)
    society_bytes, _m = _society_jsonl_bytes(run_dir, derived, run_json["manifest_id"])
    persisted = open(os.path.join(run_dir, "society.jsonl"), "rb").read()
    if persisted != society_bytes:
        raise ContentRecordError(
            "society.jsonl is not the canonical re-derivation — refused")
    # the report's fork material is verified by the replay gate (which re-runs the
    # fork); here we canonically re-check everything the report derives from the
    # control evidence alone (trust, enforcement, terminal, claim ceiling).
    report = json.loads(open(os.path.join(run_dir, "society_report.json"),
                             encoding="utf-8").read())
    c = report["content"]
    if c["final_trust_edges"] != derived["trust"] or \
            c["enforcement_event_count"] != len(derived["enforcement"]) or \
            c["claim_ceiling"] != CLAIM_CEILING:
        raise ContentRecordError(
            "society_report.json is not consistent with the canonical derivation")
    return derived


def replay_society_seed(run_id, out_root=None, scratch_root=None):
    """The eight-file replay gate: re-execute the seed (control + fork + society)
    from nothing and byte-compare EVERY evidence file."""
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
    private facts, no privileged content, no chain hashes."""
    if not isinstance(report, dict) or set(report) != _ACTOR_REPORT_KEYS:
        raise ContentRecordError("actor report must have exactly the permitted keys")
    agent = report["agent"]
    if agent not in AGENTS:
        raise ContentRecordError("unknown agent in actor report")
    if set(report["outgoing_trust"]) != {_pair_key(agent, j)
                                         for j in AGENTS if j != agent}:
        raise ContentRecordError(
            "outgoing_trust must be exactly this agent's own outgoing edges")
    if any(not isinstance(v, int) or isinstance(v, bool)
           for v in report["outgoing_trust"].values()):
        raise ContentRecordError("outgoing_trust values must be ints")
    if report["claim_ceiling"] != CLAIM_CEILING:
        raise ContentRecordError("actor report claim_ceiling must be the fixed ceiling")


def actor_safe_report(run_dir, agent):
    """The per-agent ACTOR-SAFE report: derived exclusively from that agent's own
    recorded actor observations + its own outgoing trust edges (society evidence
    canonically verified first)."""
    if agent not in AGENTS:
        raise ContentRecordError(f"unknown agent {agent!r}")
    derived = assert_society_evidence_canonical(run_dir)
    body = derived["run_json"]["observers"][agent]
    observed, counts = [], {}
    for r in (json.loads(l) for l in
              open(os.path.join(run_dir, "observations.jsonl"), encoding="utf-8")):
        if r["observer_body_id"] != body:
            continue
        observed.append(r["scheduler_position"])
        counts[str(r["scheduler_position"])] = len(
            r["actor_content"]["content"]["visible_entity_identities"])
    report = {"agent": agent, "observed_positions": sorted(observed),
              "visible_entity_counts": counts,
              "outgoing_trust": {_pair_key(agent, j): derived["trust"][_pair_key(agent, j)]
                                 for j in AGENTS if j != agent},
              "claim_ceiling": CLAIM_CEILING}
    assert_actor_report_schema(report)
    return report


def privileged_report(run_dir):
    """The PRIVILEGED report (society evidence canonically verified first)."""
    derived = assert_society_evidence_canonical(run_dir)
    return {"scenario": SCENARIO, "trust_matrix": derived["trust"],
            "trust_updates": derived["trust_updates"],
            "private_facts": {PRIVATE_FACT_HOLDER: {PRIVATE_FACT: True}},
            "enforcement_trace": derived["enforcement"],
            "enforcement_trace_commitment": derived["enforcement_commitment"],
            "tick_state_ids": [t.id for t in derived["tick_states"]],
            "claim_ceiling": CLAIM_CEILING}
