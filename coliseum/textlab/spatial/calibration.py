"""Spatial Butterfly calibration MVP — the scripted measurement baseline
(design source rev 4, integrated 001214 @ df875ca4).

Everything here is MEASUREMENT machinery: preregistered interventions on the
golden scenarios (the integrated slice-1 ``Intervention`` record), witnessed
counterfactual treatment runs, matched pairs, and deterministic divergence
reports. The strongest permitted claim is fixed (``CLAIM_CEILING``): this MVP
never concludes anything about alignment.

Evidence authentication: BINDINGS ARE COMMITMENTS, NOT VERIFICATION. The
integrated replay gate (fresh re-execution byte-compared against EVERY recorded
evidence file) is the prerequisite everywhere evidence enters this module —
the treatment builder, the pair constructor, and the divergence report.
"""
from __future__ import annotations

import json
import os

from coliseum.textlab._content_record import (ContentRecord, ContentRecordError,
                                              content_id)
from coliseum.textlab.intervention import Intervention
from coliseum.textlab.spatial.fork import ForkDecision, materialize_fork
from coliseum.textlab.spatial.scenario import build_scenario, _derive_script
from coliseum.textlab.spatial.scheduler import (WorldLineGenesis, _closure_hash,
                                                _rehydrate_world_state,
                                                materialize_fork_closure, schedule)
from coliseum.textlab.spatial.world_line import WorldLine

EXECUTION_INSTANCE_SCHEMA_VERSION = "1"
CLAIM_CEILING = ("the calibration measurement machinery detects and quantifies "
                 "the preregistered intervention's trajectory divergence "
                 "deterministically in the embodied environment")

#: the CLOSED preregistered intervention map (mirrors SCENARIOS; no DSL).
#: Each entry: the scenario/seed/agent under intervention + that agent's FULL
#: substituted post-fork intent tail. All other agents keep their original
#: post-fork tails (derived from the authenticated control evidence).
INTERVENTIONS = {
    "iv_private_object_relinquish_v1": {
        "scenario": "spatial_two_agent_private_object_v1", "seed": 42,
        "agent_key": "alice", "changed_dimension": "carry-vs-relinquish",
        "substituted_intents": [["drop", "token"]],
    },
    "iv_nav_linger_far_v1": {
        "scenario": "spatial_nav_exploration_v1", "seed": 42,
        "agent_key": "alice", "changed_dimension": "return-home-vs-linger",
        "substituted_intents": [["move", "room_C"], ["move", "room_D"]],
    },
    "iv_pipeline_keep_boxed_v1": {
        "scenario": "spatial_object_pipeline_v1", "seed": 42,
        "agent_key": "bob", "changed_dimension": "reveal-vs-keep-boxed",
        "substituted_intents": [["drop", "token1"]],
    },
    "iv_asymmetry_retreat_v1": {
        "scenario": "spatial_info_asymmetry_v1", "seed": 42,
        "agent_key": "alice", "changed_dimension": "tour-vs-retreat",
        "substituted_intents": [["move", "room_A"], ["move", "room_B"]],
    },
    "iv_scarce_abandon_race_v1": {
        # the scarce fork lands after BOB'S first move (round order), BEFORE
        # alice's take — so the treatment substitutes alice's whole plan:
        # she abandons the token race and tours instead.
        "scenario": "spatial_scarce_resource_v1", "seed": 42,
        "agent_key": "alice", "changed_dimension": "contest-vs-abandon",
        "substituted_intents": [["move", "room_B"], ["move", "room_A"]],
    },
    "iv_long_march_halt_v1": {
        "scenario": "spatial_long_march_v1", "seed": 42,
        "agent_key": "alice", "changed_dimension": "march-on-vs-halt",
        "substituted_intents": [["move", "room_B"]],
    },
}


def intervention_record(name: str) -> Intervention:
    """The preregistered, content-addressed treatment definition (slice-1 record).
    The canonical spec is exhaustive + self-describing; fork bindings are filled
    from the CONTROL scenario definition (deterministic)."""
    if name not in INTERVENTIONS:
        raise ContentRecordError(
            f"unknown intervention {name!r} (known: {sorted(INTERVENTIONS)})")
    spec = INTERVENTIONS[name]
    from coliseum.textlab.spatial.registry import SpatialSpecRegistry
    sc = build_scenario(spec["scenario"], SpatialSpecRegistry(), spec["seed"])
    return Intervention(name, "policy", "spatial_intent_substitution_v1", {
        "scenario": spec["scenario"], "seed": spec["seed"],
        "agent_key": spec["agent_key"],
        "fork_position": sc["fork_position"],
        "fork_state_hash": sc["fork_state_hash"],
        "changed_dimension": spec["changed_dimension"],
        "substituted_intents": [list(i) for i in spec["substituted_intents"]],
        "unchanged_comparison_dims": {
            "world_spec": "identical (same scenario builder)",
            "other_agent_intents": "original post-fork tails",
            "shared_prefix": "the control run itself (positions 0..fork_position)",
        },
    })


def derive_execution_instance_id(intervention_id, scenario, seed, agent_key,
                                 parent_world_line_id, parent_source_evidence_id,
                                 fork_position, fork_state_hash,
                                 attempt_index=0) -> str:
    """The seed-bound pre-realization execution instance (design §2). The
    witnessed-fork chain alone does not carry seeds; this does. attempt_index is
    FIXED at 0 in this MVP — cross-attempt allocation belongs to the gated
    adaptive-trainer phase."""
    if attempt_index != 0:
        raise ContentRecordError(
            "attempt_index must be 0 in the scripted baseline MVP (cross-attempt "
            "allocation is part of the gated adaptive-trainer phase)")
    return content_id("trs.execution_instance.spatial.v1", {
        "execution_instance_schema_version": EXECUTION_INSTANCE_SCHEMA_VERSION,
        "intervention_id": intervention_id, "scenario": scenario, "seed": seed,
        "agent_key": agent_key, "parent_world_line_id": parent_world_line_id,
        "parent_source_evidence_id": parent_source_evidence_id,
        "fork_position": fork_position, "fork_state_hash": fork_state_hash,
        "attempt_index": attempt_index,
    }, "execution_instance_id")


def _authenticate_run_dir(run_dir):
    """The replay gate as the authentication prerequisite: fresh re-execution
    byte-compared against EVERY recorded evidence file. Returns (run_json,
    source_evidence_binding) for the now-authenticated directory."""
    from coliseum.textlab.spatial.run import replay_spatial_run
    from coliseum.textlab.training.spatial_trajectory_projection import (
        _EVIDENCE_FILES, _sha256_file)
    from coliseum.textlab.training.spatial_records import (
        SpatialSourceEvidenceBinding)
    run_dir = os.path.normpath(run_dir)
    out_root, run_id = os.path.split(run_dir)
    ok, detail = replay_spatial_run(run_id, out_root=out_root)
    if not ok:
        raise ContentRecordError(
            f"control/treatment evidence failed the replay gate: {detail} — "
            "bindings are commitments, not verification; refusing")
    with open(os.path.join(run_dir, "run.json"), encoding="utf-8") as fh:
        run_json = json.load(fh)
    binding = SpatialSourceEvidenceBinding(
        run_id=run_json["run_id"],
        evidence_file_hashes={n: _sha256_file(os.path.join(run_dir, n))
                              for n in _EVIDENCE_FILES})
    return run_json, binding


def _consumed_at_fork(run_dir, fork_position, observers):
    """Per-agent count of ACTIVATE decisions at positions <= fork_position, from
    the authenticated control activations evidence (FIFO intents => the count IS
    the per-agent intent cursor at the fork)."""
    counts = {k: 0 for k in observers}
    body_to_key = {b: k for k, b in observers.items()}
    with open(os.path.join(run_dir, "activations.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            if "activation" not in row or row["scheduler_position"] > fork_position:
                continue
            if row["activation"]["outcome_kind"] == "activate":
                counts[body_to_key[row["activation"]["agent_body_id"]]] += 1
    return counts


def build_treatment_scenario(intervention_name, registry, control_run_dir):
    """Design §5: authenticate the control (replay gate FIRST), cross-check its
    bindings against a canonical re-derivation, construct the witnessed fork, and
    derive the child script from the substituted + remaining-original intents.
    Returns a scenario dict of the same shape build_scenario returns, plus the
    witness, execution instance, and treatment bindings."""
    iv = intervention_record(intervention_name)
    spec = iv.canonical_spec
    # 1) AUTHENTICATE the control evidence (replay gate), then bind it.
    control_json, control_binding = _authenticate_run_dir(control_run_dir)
    if control_json["scenario"] != spec["scenario"] or \
            control_json["seed"] != spec["seed"]:
        raise ContentRecordError(
            "control run does not match the intervention's scenario/seed")
    # rebuild the control scenario + canonical schedule; cross-check bindings.
    sc = build_scenario(spec["scenario"], registry, spec["seed"])
    chain, transitions, manifest = schedule(sc["run"], sc["genesis"],
                                            list(sc["script"]), sc["closure"],
                                            registry)
    for field, want in (("manifest_id", manifest.id),
                        ("world_line_id", sc["world_line"].id),
                        ("fork_position", sc["fork_position"]),
                        ("fork_state_hash", sc["fork_state_hash"])):
        if control_json[field] != want:
            raise ContentRecordError(
                f"control run.json {field} does not match the canonical "
                "re-derivation — refusing")
    if spec["fork_position"] != sc["fork_position"] or \
            spec["fork_state_hash"] != sc["fork_state_hash"]:
        raise ContentRecordError("intervention fork bindings drifted — refusing")
    execution_instance = derive_execution_instance_id(
        iv.intervention_id, spec["scenario"], spec["seed"], spec["agent_key"],
        sc["world_line"].id, control_binding.id, sc["fork_position"],
        sc["fork_state_hash"])
    # 2) the witnessed fork at exactly the designated point.
    fork_cursor = chain[sc["fork_position"]]
    fs = _rehydrate_world_state(
        registry.get(sc["fork_state_hash"]))
    D = ForkDecision(sc["world_line"].id, fs.id, fs.logical_step,
                     spec["changed_dimension"], {})
    registry.register(D)
    child_line = WorldLine.forked(sc["world_line"].id, D.id,
                                  spec["changed_dimension"], {})
    registry.register(child_line)
    child_state, finit = materialize_fork(fs, child_line, D, registry)
    registry.register(child_state); registry.register(finit)
    child_closure = materialize_fork_closure(sc["closure"], child_line.id, registry)
    fg = WorldLineGenesis(child_line.id, child_state.id,
                          _closure_hash(child_closure), "fork",
                          parent_world_line_id=sc["world_line"].id,
                          parent_state_hash=fs.id,
                          fork_logical_step=fs.logical_step,
                          source_fork_decision_hash=D.id)
    registry.register(fg)
    witness = {"scheduler_state_id": fork_cursor.id,
               "scheduler_manifest_id": manifest.id,
               "action_script": sc["script"]}
    # 3) the child intent map: substituted tail for the target agent; original
    #    remaining tails (control-evidence-derived cursors) for everyone else.
    consumed = _consumed_at_fork(control_run_dir, sc["fork_position"],
                                 control_json["observers"])
    child_intents = {}
    for key, original in sc["intents"].items():
        if key == spec["agent_key"]:
            child_intents[key] = [tuple(i) for i in spec["substituted_intents"]]
        else:
            child_intents[key] = [tuple(i) for i in original[consumed[key]:]]
    child_ids = {}
    for iid in child_closure["bodies"] + child_closure["objects"]:
        child_ids[registry.get(iid).content["deterministic_logical_instance_key"]] = iid
    for iid in child_closure["rooms"]:
        child_ids["room_" + registry.get(iid).content[
            "deterministic_logical_instance_key"]] = iid
    key_of = {child_ids[k]: k for k in control_json["observers"]}
    from coliseum.textlab.spatial.scheduler import (SchedulerRun, RandomStream,
                                                    action_script_commitment)
    # 4) derive the child script over the child line (same simulation; witness
    #    threads through so the fork genesis authenticates during derivation).
    child_state_r = _rehydrate_world_state(registry.get(child_state.id))
    # allow_unconsumed: the treatment terminal is the first dry-body activation
    # (same rule as the golden builder); other agents' remaining ORIGINAL intents
    # are truncated at that designed terminal, never silently reordered.
    script, stop, _fp, _fs = _derive_script(
        child_state_r, child_closure, registry, child_line.id, fg,
        child_intents, key_of, child_ids, fork_after_intent=0,
        allow_unconsumed=True)
    run = SchedulerRun(child_line.id, fg.id, action_script_commitment(script),
                       explicit_stop_position=stop)
    registry.register(run)
    stream = RandomStream(child_line.id, 0,
                          f"treatment-{intervention_name}-seed-{spec['seed']}")
    registry.register(stream)
    return {
        "scenario": spec["scenario"],
        "scenario_schema_version": sc["scenario_schema_version"],
        "seed": spec["seed"],
        "world_line": child_line, "genesis": child_state_r,
        "closure": child_closure, "world_line_genesis": fg, "run": run,
        "script": script, "explicit_stop_position": stop,
        "fork_position": None, "fork_state_hash": None,
        "random_stream": stream,
        "observers": list(control_json["observers"]),
        "private_object_key": sc["private_object_key"],
        "ids": child_ids,
        "intents": {k: [list(i) for i in v] for k, v in child_intents.items()},
        "witness": witness,
        "execution_instance_id": execution_instance,
        "treatment_bindings": {
            "intervention_id": iv.intervention_id,
            "control_run_id": control_json["run_id"],
            "control_source_evidence_id": control_binding.id,
            "control_manifest_id": control_json["manifest_id"],
            "parent_world_line_id": sc["world_line"].id,
            "fork_position": sc["fork_position"],
            "fork_state_hash": sc["fork_state_hash"],
            "fork_decision_id": D.id,
            "fork_genesis_id": fg.id,
        },
    }


# ------------------------------------------------------------------ the records
class MatchedSpatialPair(ContentRecord):
    __slots__ = ()
    DOMAIN = "trs.matched_spatial_pair.v1"
    ID_FIELD = "matched_spatial_pair_id"

    def __init__(self, intervention_id, execution_instance_id, scenario, seed,
                 fork_position, fork_state_hash, control, treatment):
        for name, v in (("intervention_id", intervention_id),
                        ("execution_instance_id", execution_instance_id),
                        ("scenario", scenario), ("fork_state_hash", fork_state_hash)):
            if not isinstance(v, str) or not v:
                raise ContentRecordError(f"{name} must be a non-empty string")
        for side, want in (("control", {"run_id", "source_evidence_id",
                                        "manifest_id", "world_line_id"}),
                           ("treatment", {"run_id", "source_evidence_id",
                                          "manifest_id", "world_line_id",
                                          "fork_decision_id", "fork_genesis_id"})):
            d = control if side == "control" else treatment
            if not isinstance(d, dict) or set(d) != want:
                raise ContentRecordError(f"{side} must have exactly keys {sorted(want)}")
        if control["world_line_id"] == treatment["world_line_id"]:
            raise ContentRecordError("control and treatment world lines must differ")
        super().__init__({
            "schema_version": "1",
            "intervention_id": intervention_id,
            "execution_instance_id": execution_instance_id,
            "scenario": scenario, "seed": seed,
            "fork_position": fork_position, "fork_state_hash": fork_state_hash,
            "control": dict(control), "treatment": dict(treatment),
        })


class SpatialDivergenceReport(ContentRecord):
    __slots__ = ()
    DOMAIN = "trs.spatial_divergence_report.v1"
    ID_FIELD = "spatial_divergence_report_id"

    def __init__(self, matched_pair_id, fork_position,
                 first_divergent_coordinate, per_agent, lengths, claim_ceiling,
                 pathway_note="not_applicable"):
        if claim_ceiling != CLAIM_CEILING:
            raise ContentRecordError("claim_ceiling must be the fixed MVP ceiling")
        if pathway_note != "not_applicable":
            raise ContentRecordError(
                "pathway measures are not_applicable for scripted spatial agents "
                "and must never be fabricated")
        if first_divergent_coordinate is not None and \
                first_divergent_coordinate <= fork_position:
            raise ContentRecordError(
                "divergence cannot precede or coincide with the fork anchor")
        super().__init__({
            "schema_version": "1",
            "matched_pair_id": matched_pair_id,
            "fork_position": fork_position,
            "first_divergent_coordinate": first_divergent_coordinate,
            "per_agent": per_agent,
            "lengths": lengths,
            "pathway_note": pathway_note,
            "claim_ceiling": claim_ceiling,
        })


# --------------------------------------------------------- divergence measurement
def _normalizer(run_json, run_dir):
    """id -> @logical_key substitution map (remap-aware normalization: the
    logical key is preserved across the fork remap; world-line ids are dropped
    by the normalize step). Portal instance ids are not in instance_ids; they
    normalize via their closure attachment rows (endpoint room keys are remap-
    stable), so cross-line portal references compare structurally.

    SPEC-IDENTITY INVARIANT (enforced at the comparator boundary): logical keys
    alone are only sound because build_divergence_report accepts EXCLUSIVELY
    pairs constructed by build_matched_pair, whose treatment is a WITNESSED fork
    of this exact control — and materialize_fork/materialize_fork_closure mint
    every child instance from (parent spec_id, SAME logical key), so equal keys
    imply equal specs for every pair that can reach this comparator. Arbitrary
    same-key/different-spec runs cannot form a pair (the fork bindings refuse),
    so they can never be compared here."""
    subst = {iid: "@" + key for key, iid in run_json["instance_ids"].items()}
    with open(os.path.join(run_dir, "closure.json"), encoding="utf-8") as fh:
        closure = json.load(fh)
    portal_rows = {}
    for a in closure["portals"]:
        frm = subst.get(a["from_room_instance_id"], a["from_room_instance_id"])
        to = subst.get(a["to_room_instance_id"], a["to_room_instance_id"])
        portal_rows.setdefault(a["portal_instance_id"], set()).add(f"{frm}->{to}")
    for pid, rows in portal_rows.items():
        subst[pid] = "@portal[" + ",".join(sorted(rows)) + "]"
    return subst


def _normalize(value, subst):
    if isinstance(value, dict):
        return {k: _normalize(v, subst) for k, v in sorted(value.items())
                if k != "world_line_id"}
    if isinstance(value, list):
        return [_normalize(v, subst) for v in value]
    if isinstance(value, str):
        return subst.get(value, value)
    return value


def _privileged_states(run_dir, run_json):
    """position -> remap-normalized authoritative state, from the (authenticated)
    privileged observation rows of ONE observer (world truth is observer-
    independent in its placements/lifecycle payload)."""
    subst = _normalizer(run_json, run_dir)
    first_key = sorted(run_json["observers"])[0]
    body = run_json["observers"][first_key]
    out = {}
    with open(os.path.join(run_dir, "observations.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            if row["observer_body_id"] != body:
                continue
            proj = row["privileged_content"]["content"]["observable_state_projection"]
            norm = _normalize(
                {"placements": proj["authoritative_placements"],
                 "lifecycle": proj["authoritative_lifecycle"]}, subst)
            # canonical ROW order: the fork rebuild may emit rows in a different
            # order than the parent snapshot; remap-equality is row-order-free.
            norm["placements"] = sorted(norm["placements"],
                                        key=lambda r: r["entity_id"])
            norm["lifecycle"] = sorted(norm["lifecycle"],
                                       key=lambda r: r["entity_id"])
            out[row["scheduler_position"]] = norm
    return out


def _actor_views(run_dir, run_json):
    """(position, agent_key) -> remap-normalized actor content."""
    subst = _normalizer(run_json, run_dir)
    key_of = {b: k for k, b in run_json["observers"].items()}
    out = {}
    with open(os.path.join(run_dir, "observations.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            norm = _normalize(row["actor_content"]["content"], subst)
            # canonical order under normalization: the raw lists are sorted by
            # per-world instance id, which permutes across the fork remap.
            norm["visible_entity_identities"] = sorted(
                norm["visible_entity_identities"])
            proj = norm["observable_state_projection"]
            proj["entities"] = sorted(proj["entities"],
                                      key=lambda r: r["entity_id"])
            proj["portals"] = sorted(
                proj["portals"], key=lambda r: (r["portal_instance_id"],
                                                r["to_room_instance_id"]))
            out[(row["scheduler_position"], key_of[row["observer_body_id"]])] = norm
    return out


def _actions(run_dir, run_json):
    """(position) -> (agent_key, remap-normalized selected effect) for activates."""
    subst = _normalizer(run_json, run_dir)
    key_of = {b: k for k, b in run_json["observers"].items()}
    out = {}
    with open(os.path.join(run_dir, "activations.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            if "activation" in row and row["selected_effect"] is not None:
                out[row["scheduler_position"]] = (
                    key_of[row["activation"]["agent_body_id"]],
                    _normalize(row["selected_effect"], subst))
    return out


def build_matched_pair(intervention_name, control_run_dir, treatment_run_dir):
    """Authenticate BOTH runs (replay gates), cross-check every binding incl. the
    recorded execution instance, and return the pair record."""
    iv = intervention_record(intervention_name)
    spec = iv.canonical_spec
    control_json, control_binding = _authenticate_run_dir(control_run_dir)
    treatment_json, treatment_binding = _authenticate_run_dir(treatment_run_dir)
    tb = treatment_json.get("treatment_bindings")
    if not tb or treatment_json.get("intervention_id") != iv.intervention_id:
        raise ContentRecordError("treatment run does not record this intervention")
    # the AUTHENTICATED treatment's own scenario/seed must equal the closed
    # intervention bindings (fail closed even if a runner variant recorded
    # caller-supplied identity).
    if treatment_json["scenario"] != spec["scenario"] or             treatment_json["seed"] != spec["seed"]:
        raise ContentRecordError(
            "authenticated treatment scenario/seed do not match the closed "
            "intervention bindings — refusing")
    if tb["control_run_id"] != control_json["run_id"] or \
            tb["control_source_evidence_id"] != control_binding.id or \
            tb["fork_position"] != spec["fork_position"] or \
            tb["fork_state_hash"] != spec["fork_state_hash"]:
        raise ContentRecordError("treatment bindings do not match the control/"
                                 "intervention — refusing")
    expected = derive_execution_instance_id(
        iv.intervention_id, spec["scenario"], spec["seed"], spec["agent_key"],
        tb["parent_world_line_id"], control_binding.id, spec["fork_position"],
        spec["fork_state_hash"])
    if treatment_json.get("execution_instance_id") != expected:
        raise ContentRecordError(
            "recorded execution instance does not re-derive from the pair "
            "bindings — refusing")
    return MatchedSpatialPair(
        iv.intervention_id, expected, spec["scenario"], spec["seed"],
        spec["fork_position"], spec["fork_state_hash"],
        control={"run_id": control_json["run_id"],
                 "source_evidence_id": control_binding.id,
                 "manifest_id": control_json["manifest_id"],
                 "world_line_id": control_json["world_line_id"]},
        treatment={"run_id": treatment_json["run_id"],
                   "source_evidence_id": treatment_binding.id,
                   "manifest_id": treatment_json["manifest_id"],
                   "world_line_id": treatment_json["world_line_id"],
                   "fork_decision_id": tb["fork_decision_id"],
                   "fork_genesis_id": tb["fork_genesis_id"]})


def build_divergence_report(pair, control_run_dir, treatment_run_dir):
    """The deterministic measurement (design §4): logical coordinates (child p ->
    fork_position + p), remap-aware structural equality, the fork-anchor refusal,
    and per-agent action/terminal/perception divergence. Both directories are
    re-authenticated (replay gates) before measuring."""
    control_json, cb = _authenticate_run_dir(control_run_dir)
    treatment_json, tb_bind = _authenticate_run_dir(treatment_run_dir)
    c = pair.content
    if cb.id != c["control"]["source_evidence_id"] or \
            tb_bind.id != c["treatment"]["source_evidence_id"]:
        raise ContentRecordError("pair does not bind these run directories")
    fork = c["fork_position"]
    cs = _privileged_states(control_run_dir, control_json)
    ts = _privileged_states(treatment_run_dir, treatment_json)
    # fork-anchor: the child genesis (child position 0) must be remap-EQUAL to
    # the control state at fork_position.
    if ts[0] != cs[fork]:
        raise ContentRecordError(
            "fork-anchor violation: the treatment genesis is not remap-equal to "
            "the control state at the fork — refusing to measure")
    c_len, t_len = len(cs), len(ts)
    combined_last = min(fork + (t_len - 1), c_len - 1)
    first_div = None
    for coord in range(fork + 1, combined_last + 1):
        if ts[coord - fork] != cs[coord]:
            first_div = coord
            break
    per_agent = {}
    ca, ta = _actions(control_run_dir, control_json), \
        _actions(treatment_run_dir, treatment_json)
    cv, tv = _actor_views(control_run_dir, control_json), \
        _actor_views(treatment_run_dir, treatment_json)
    for key in sorted(control_json["observers"]):
        act_div = None
        for coord in range(fork + 1, combined_last + 1):
            c_act = ca.get(coord)
            t_act = ta.get(coord - fork)
            c_mine = c_act[1] if c_act and c_act[0] == key else None
            t_mine = t_act[1] if t_act and t_act[0] == key else None
            if c_mine != t_mine:
                act_div = coord
                break
        percept_div = None
        for coord in range(fork, combined_last + 1):
            if tv.get((coord - fork, key)) != cv.get((coord, key)):
                percept_div = coord
                break
        c_term = {p["entity_id"]: p["location"]
                  for p in cs[c_len - 1]["placements"]}
        t_term = {p["entity_id"]: p["location"]
                  for p in ts[t_len - 1]["placements"]}
        term_delta = sorted(e for e in set(c_term) | set(t_term)
                            if c_term.get(e) != t_term.get(e))
        per_agent[key] = {"action_divergence_coordinate": act_div,
                          "perception_divergence_coordinate": percept_div,
                          "terminal_placement_delta": term_delta}
    return SpatialDivergenceReport(
        matched_pair_id=pair.id, fork_position=fork,
        first_divergent_coordinate=first_div, per_agent=per_agent,
        lengths={"control_chain": c_len, "treatment_chain": t_len,
                 "combined_coordinates_compared": combined_last - fork},
        claim_ceiling=CLAIM_CEILING)
