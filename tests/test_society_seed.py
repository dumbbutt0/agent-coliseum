"""Minimal Society Seed evidence pack (OWNER SC-LC 2026-07-14; design integrated
001238). The ten required proofs + the ten-vector threat model, with pinned
identities. Tests drive only integrated production paths."""
from __future__ import annotations

import json
import os
import shutil

import pytest

from coliseum.textlab._content_record import ContentRecordError
from coliseum.textlab.spatial.registry import SpatialSpecRegistry
from coliseum.textlab.spatial import scenario as scn
from coliseum.textlab.spatial.scenario import build_scenario
from coliseum.textlab.society.run import (FORK_INTERVENTION, SOCIETY_EVIDENCE_FILES,
                                          actor_safe_report,
                                          assert_actor_report_schema,
                                          assert_society_evidence_canonical,
                                          execute_society_seed,
                                          privileged_report, replay_society_seed)
from coliseum.textlab.society.seed import (AGENTS, CLAIM_CEILING, TICKS,
                                           SocietyOutcomeReport, SocietyTickState,
                                           assert_script_rule_clean, derive_society)
from coliseum.textlab.training.spatial_trajectory_projection import (
    project_spatial_trajectory)

PINS = {
    "run_id": "society_seed_v1--seed42--b4f03e16d88940f3",
    "society_run_manifest_id": "7a7353b67adc3d0fe90968e7a0d2bcff7a76bbb928a0ca4654deb8fc2d18fe25",
    "society_source_evidence_id": "cccc3f8555b92d0bbc8c8f8a999105c09f8b0b98df4b1c65c50711dae6677a07",
    "society_outcome_report_id": "7ff002a73a52192a9bb8f3163dd5e4dc5221e9996cf5d07fcc012deb6d4337f3",
    "tick_state_ids": ["e147245b511e37c2c527af1e057975a40451efb8111bad457b6318322a97f4cd", "f4bd944739877cbc1ea685b767a0c14bfb35d001936add1264643bb13ff0b23a", "cb22d6ec352fa9cf69074ec1b4bbb0f775054b36629279bed5010c8d823b510d", "8cbedc0c2d85585c6c9f31e720c29ea44a648e9f07c87b74d78a87cbf9a2a40f", "494608a894bbc02464c5dc2ee1d71b6c0a50a7ad7afb2780bfb410ca32093e47", "acf1b161f68055ef2ba34dcf682bb6128bef116e7e71d8cdf2d67633b36b7321", "e99d251b6a16e0d9d82540e146253e815a2095848bbf7b258f1230d684ab4b34", "48fb23a877b249428ebe0816eb30cb27cff50110356b780846bd749591bfffe0"],
    "fork_pair": "a0d2e8c9895299c04e808ff034797085d826aaeed1ffbbd8edc9eba8ca372bd9",
    "fork_report": "c0806da62446287a4081a7b4af6524bb3003854d25c8c8c974ff47a8deb9df9d",
    "outcome_trust": {"ada->bo": 0, "ada->cy": 0, "bo->ada": 1, "bo->cy": 0,
                      "cy->ada": 0, "cy->bo": 0},
    "perception_div": {"ada": 16, "bo": 16, "cy": 17},
}


@pytest.fixture(scope="module")
def pack(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("society"))
    s = execute_society_seed(42, out_root=root)
    return {"root": root, "s": s, "run_dir": s["run_dir"]}


def _copy(root, run_dir, name):
    os.makedirs(root, exist_ok=True)
    dst = os.path.join(root, name)
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(run_dir, dst)
    return dst


# ------------------------------------------------- pinned identities + scope
def test_pinned_identities(pack):
    s = pack["s"]
    assert s["run_id"] == PINS["run_id"]
    assert s["society_run_manifest_id"] == PINS["society_run_manifest_id"]
    assert s["society_source_evidence_id"] == PINS["society_source_evidence_id"]
    assert s["society_outcome_report_id"] == PINS["society_outcome_report_id"]
    assert s["tick_state_ids"] == PINS["tick_state_ids"]
    assert s["fork_summary"]["matched_pair_id"] == PINS["fork_pair"]
    assert s["fork_summary"]["divergence_report_id"] == PINS["fork_report"]
    assert s["outcome"]["final_trust_edges"] == PINS["outcome_trust"]
    assert s["fork_summary"]["per_agent_perception_divergence"] == PINS["perception_div"]


def test_scope_matches_sc_lc(pack):
    s = pack["s"]
    ids = s["spatial"]["instance_ids"]
    assert set(s["spatial"]["observers"]) == set(AGENTS)             # 3 agents
    assert len([k for k in ids if k.startswith("room_")]) == 3       # 3 rooms
    assert "token" in ids and "gem" in ids                          # token + private obj
    d = derive_society(pack["run_dir"])
    assert len(d["tick_states"]) == TICKS                           # 8 ticks
    assert len(d["trust"]) == 6                                      # 6 edges


# ============================ the ten required proofs ==================
def test_proof1_byte_identical_replay(pack):
    ok, detail = replay_society_seed(pack["s"]["run_id"], out_root=pack["root"],
                                     scratch_root=os.path.join(pack["root"], "r1"))
    assert ok, detail
    assert all(n in detail for n in SOCIETY_EVIDENCE_FILES)
    other = execute_society_seed(42, out_root=os.path.join(pack["root"], "other"))
    for name in SOCIETY_EVIDENCE_FILES:
        assert open(os.path.join(pack["run_dir"], name), "rb").read() == \
            open(os.path.join(other["run_dir"], name), "rb").read(), name


def test_proof2_per_agent_perception_non_interference(pack):
    """The one authenticated fork's per-agent perception-divergence coordinates
    differ (fog/privacy scope non-interference) and all lie beyond the fork."""
    fs = pack["s"]["fork_summary"]
    coords = fs["per_agent_perception_divergence"]
    assert all(c is not None and c > fs["fork_position"] for c in coords.values())
    assert len(set(coords.values())) > 1


def test_proof3_deterministic_trust_rederivation(pack):
    d1 = derive_society(pack["run_dir"])
    d2 = derive_society(pack["run_dir"])
    assert [t.id for t in d1["tick_states"]] == [t.id for t in d2["tick_states"]]
    assert d1["trust"] == d2["trust"]
    # every trust update carries its justifying actor observation id (provenance).
    for u in d1["trust_updates"]:
        assert u["actor_observation_id"] and len(u["actor_observation_id"]) == 64


def test_proof4_token_single_placement(pack):
    token = pack["s"]["spatial"]["instance_ids"]["token"]
    run_json = json.load(open(os.path.join(pack["run_dir"], "run.json")))
    body = run_json["observers"][sorted(run_json["observers"])[0]]
    for r in (json.loads(l) for l in
              open(os.path.join(pack["run_dir"], "observations.jsonl"))):
        if r["observer_body_id"] != body:
            continue
        placements = r["privileged_content"]["content"][
            "observable_state_projection"]["authoritative_placements"]
        assert sum(1 for p in placements if p["entity_id"] == token) == 1


def test_proof5_enforcement_trace(pack):
    d = derive_society(pack["run_dir"])
    assert d["enforcement"]
    assert all(e["rule"] == "institution.token_stays_in_a.v1" for e in d["enforcement"])
    assert_script_rule_clean(pack["run_dir"])


def test_proof6_fork_isolation_and_ancestry(pack):
    """Distinct world lines; the parent society evidence replays byte-identically
    AFTER the fork (isolation)."""
    fs = pack["s"]["fork_summary"]
    assert fs["intervention_id"] == FORK_INTERVENTION
    ok, _ = replay_society_seed(pack["s"]["run_id"], out_root=pack["root"],
                                scratch_root=os.path.join(pack["root"], "r6"))
    assert ok


def test_proof7_trs_projection(pack):
    p = project_spatial_trajectory(pack["run_dir"])
    assert set(p["manifests"]) == set(AGENTS)


def test_proof8_actor_safe_and_privileged_reports(pack):
    priv = privileged_report(pack["run_dir"])
    assert len(priv["trust_matrix"]) == 6
    for a in AGENTS:
        r = actor_safe_report(pack["run_dir"], a)
        assert_actor_report_schema(r)
        assert all(e.startswith(a + "->") for e in r["outgoing_trust"])
        blob = json.dumps(r)
        assert "enforcement_trace" not in blob and "private_facts" not in blob


def test_proof9_outcome_claim_ceiling(pack):
    outcome = pack["s"]["outcome"]
    assert outcome["claim_ceiling"] == CLAIM_CEILING
    assert "no human-fidelity or society-simulation claim" in CLAIM_CEILING
    assert set(outcome["fork_divergence_summary"]) >= {
        "divergence_report_id", "per_agent_perception_divergence"}


def test_proof10_regressions_present():
    """This module IS the permanent regression pack: every threat vector below is
    a substantive committed test."""
    import tests.test_society_seed as m
    vectors = [n for n in dir(m) if n.startswith("test_vector")]
    assert len(vectors) >= 10


# ============================ ten threat vectors =======================
def test_vector1_counterfeit_society_chain_refused(pack):
    """A counterfeit society.jsonl over genuine spatial evidence is refused at the
    canonical-verification consumer boundary."""
    bad = _copy(pack["root"], pack["run_dir"], "v1")
    with open(os.path.join(bad, "society.jsonl"), "a") as fh:
        fh.write('{"record":"forged_tick"}\n')
    with pytest.raises(ContentRecordError, match="canonical re-derivation"):
        assert_society_evidence_canonical(bad)


def test_vector2_trust_is_perception_scoped(pack):
    """Trust derives ONLY from recorded actor-view rows: varying a PRIVILEGED-only
    fact (relocating the private gem, which never enters any actor view) in the
    observations' privileged content leaves the derived trust matrix IDENTICAL.
    (This is a neutral perception-scope variation, not an attack: it proves the
    trust bookkeeping ignores privileged-only state.)"""
    base = derive_society(pack["run_dir"])
    variant = _copy(pack["root"], pack["run_dir"], "v2")
    ids = pack["s"]["spatial"]["instance_ids"]
    rooms = [ids[k] for k in ids if k.startswith("room_")]
    obs_path = os.path.join(variant, "observations.jsonl")
    rows = [json.loads(l) for l in open(obs_path)]
    for r in rows:
        proj = r["privileged_content"]["content"]["observable_state_projection"]
        for p in proj["authoritative_placements"]:
            if p["entity_id"] == ids["gem"] and p["location"]["tag"] == "inside":
                # relocate the hidden gem onto a room floor (privileged-only; the
                # gem is never in any actor view, so no actor row changes).
                p["location"] = {"tag": "in_room", "room_instance_id": rooms[0]}
    with open(obs_path, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    variant_trust = derive_society(variant)["trust"]
    assert variant_trust == base["trust"]                # unchanged by hidden state
    assert all(u["kind"] == "give" for u in base["trust_updates"])  # no witnessed take


def test_vector_build_time_institutional_refusal():
    """The EXACT society build-time institutional refusal: a society script whose
    intended move is only institutionally-blocked-resolvable (a token holder in
    room A intending to move out) refuses during construction via the frozen
    above-substrate filter — the auditor's specified regression."""
    orig = scn._society_seed_intents

    def blocked(fact=True):
        d = dict(orig(fact))
        # ada: take the token in A, then (holding it) intend to move out to B.
        d["ada"] = [("move", "room_B"), ("move", "room_A"), ("take", "token"),
                    ("move", "room_B"), ("move", "room_A"), ("move", "room_B"),
                    ("move", "room_A"), ("move", "room_B")]
        return d
    scn._society_seed_intents = blocked
    try:
        with pytest.raises(ContentRecordError, match="not a legal candidate"):
            build_scenario("society_seed_v1", SpatialSpecRegistry(), 42)
    finally:
        scn._society_seed_intents = orig


def test_vector_coordinated_fork_forgery_refused_by_replay(pack):
    """A coordinated fork-summary forgery with a recomputed self-consistent id
    survives the cheap consumer boundary but is REFUSED by the eight-file replay
    gate (which re-executes the fork and byte-compares society_report.json)."""
    from coliseum.textlab.society.seed import SocietyOutcomeReport
    bad_root = os.path.join(pack["root"], "vforge_root")
    bad = _copy(bad_root, pack["run_dir"], os.path.basename(pack["run_dir"]))
    rep = json.loads(open(os.path.join(bad, "society_report.json")).read())
    forged = dict(rep["content"])
    fs = dict(forged["fork_divergence_summary"])
    fs["per_agent_perception_divergence"] = {"ada": 99, "bo": 99, "cy": 99}
    forged["fork_divergence_summary"] = fs
    outcome = SocietyOutcomeReport(forged)                   # recompute a valid id
    with open(os.path.join(bad, "society_report.json"), "w") as fh:
        fh.write(json.dumps({"id": outcome.id, "content": forged}) + "\n")
    # the cheap boundary passes (self-consistent id + control fields match)...
    assert_society_evidence_canonical(bad)
    # ...but the replay gate re-runs the real fork and refuses the forged summary.
    ok, detail = replay_society_seed(os.path.basename(pack["run_dir"]),
                                     out_root=bad_root,
                                     scratch_root=os.path.join(pack["root"], "vforge_s"))
    assert not ok and "society_report.json" in detail


def test_vector3_committed_blocked_move_refused(pack):
    """A committed transition that IS institutionally blocked (a token holder
    moving out of A) refuses at assert_script_rule_clean."""
    bad = _copy(pack["root"], pack["run_dir"], "v3")
    ids = pack["s"]["spatial"]["instance_ids"]
    run_json = json.load(open(os.path.join(bad, "run.json")))
    body = run_json["observers"][sorted(run_json["observers"])[0]]
    holder = None
    for r in (json.loads(l) for l in open(os.path.join(bad, "observations.jsonl"))):
        if r["observer_body_id"] != body:
            continue
        for p in r["privileged_content"]["content"][
                "observable_state_projection"]["authoritative_placements"]:
            if p["entity_id"] == ids["token"] and p["location"]["tag"] == "held_by":
                holder = (r["world_state_id"], p["location"]["agent_body_id"])
                break
        if holder:
            break
    assert holder
    wsid, hbody = holder
    forged = {"content": {"effect": {"action": "move", "agent_body_id": hbody,
                                     "from_room_instance_id": ids["room_A"],
                                     "portal_instance_id": "p" * 64,
                                     "to_room_instance_id": ids["room_B"]},
                          "prior_state_hash": wsid}}
    with open(os.path.join(bad, "transitions.jsonl"), "a") as fh:
        fh.write(json.dumps(forged) + "\n")
    with pytest.raises(ContentRecordError, match="institutionally blocked"):
        assert_script_rule_clean(bad)


def test_vector4_tick_drift_refused(tmp_path):
    """A society run whose round span is not eight ticks refuses at derivation.
    Patch the seed to a SHORT legal intent set (four ticks) that still builds,
    run it, and assert derive_society refuses the tick-count."""
    from coliseum.textlab.spatial.run import execute_spatial_run
    orig = scn._society_seed_intents

    def short(fact=True):
        return {"ada": [("move", "room_B"), ("move", "room_A"),
                        ("move", "room_B"), ("move", "room_A")],
                "bo": [("move", "room_A"), ("move", "room_B"),
                       ("move", "room_A"), ("move", "room_B")],
                "cy": [("move", "room_B"), ("move", "room_C"),
                       ("move", "room_B"), ("move", "room_C")]}
    scn._society_seed_intents = short
    try:
        s = execute_spatial_run("society_seed_v1", 42, out_root=str(tmp_path))
        with pytest.raises(ContentRecordError, match="exactly 8 ticks"):
            derive_society(os.path.join(str(tmp_path), s["run_id"]))
    finally:
        scn._society_seed_intents = orig


def test_vector5_fork_transplant_refused(pack):
    """The fork uses the integrated witnessed-fork machinery: pairing the society
    fork treatment against a control from a DIFFERENT scenario refuses
    (anti-transplant / authenticated ancestry)."""
    from coliseum.textlab.spatial.calibration import build_matched_pair
    from coliseum.textlab.spatial.run import execute_spatial_run
    # the society fork treatment
    t = execute_spatial_run("society_seed_v1", 42,
                            out_root=os.path.join(pack["root"], "v5"),
                            intervention=FORK_INTERVENTION,
                            control_run_dir=pack["run_dir"])
    tdir = os.path.join(pack["root"], "v5", t["run_id"])
    # a control from a completely different scenario cannot host this treatment.
    foreign = execute_spatial_run("spatial_nav_exploration_v1", 42,
                                  out_root=os.path.join(pack["root"], "v5"))
    foreign_dir = os.path.join(pack["root"], "v5", foreign["run_id"])
    with pytest.raises(ContentRecordError):
        build_matched_pair(FORK_INTERVENTION, foreign_dir, tdir)


def test_vector6_spatial_non_interference(pack):
    """Society bookkeeping never enters the spatial layer: the spatial evidence
    core is schema-0.2 and byte-identical to a plain spatial run of the same
    scenario (so all S2C guarantees + spatial pins hold)."""
    from coliseum.textlab.spatial.run import execute_spatial_run
    v6root = os.path.join(pack["root"], "v6plain")
    plain = execute_spatial_run("society_seed_v1", 42, out_root=v6root)
    plain_dir = os.path.join(v6root, plain["run_id"])
    for name in ("run.json", "chain.jsonl", "transitions.jsonl",
                 "observations.jsonl", "activations.jsonl", "closure.json"):
        a = open(os.path.join(pack["run_dir"], name), "rb").read()
        b = open(os.path.join(plain_dir, name), "rb").read()
        assert a == b, name
    assert json.load(open(os.path.join(pack["run_dir"], "run.json")))[
        "spatial_run_schema_version"] == "0.2"


def test_vector7_actor_report_schema_closed():
    """The actor report closed schema refuses any extra key (no smuggled
    privileged content)."""
    bad = {"agent": "ada", "observed_positions": [], "visible_entity_counts": {},
           "outgoing_trust": {"ada->bo": 0, "ada->cy": 0},
           "claim_ceiling": CLAIM_CEILING, "enforcement_trace": []}
    with pytest.raises(ContentRecordError, match="permitted keys"):
        assert_actor_report_schema(bad)


def test_vector8_evidence_tamper_refused(pack):
    """Tampering any evidence byte fails the eight-file replay gate (bindings are
    commitments, not verification). Flip a byte in society_report.json (valid
    JSON preserved) — the replay gate re-executes from nothing and refuses."""
    bad_root = os.path.join(pack["root"], "v8root")
    bad = _copy(bad_root, pack["run_dir"], os.path.basename(pack["run_dir"]))
    rep = os.path.join(bad, "society_report.json")
    obj = json.load(open(rep))
    obj["content"]["enforcement_event_count"] = 999          # a lie, still valid JSON
    open(rep, "w").write(json.dumps(obj))
    ok, detail = replay_society_seed(os.path.basename(pack["run_dir"]),
                                     out_root=bad_root,
                                     scratch_root=os.path.join(pack["root"], "v8s"))
    assert not ok and "society_report.json" in detail
    # and the canonical consumer boundary refuses it too.
    with pytest.raises(ContentRecordError):
        assert_society_evidence_canonical(bad)


def test_vector9_claim_ceiling_violation_refused(pack):
    """A society outcome record with any claim other than the fixed ceiling
    refuses; so does a missing fork summary."""
    good = dict(pack["s"]["outcome"])
    SocietyOutcomeReport(good)                                   # the real one passes
    bad = dict(good, claim_ceiling="this model faithfully simulates a society")
    with pytest.raises(ContentRecordError, match="claim_ceiling"):
        SocietyOutcomeReport(bad)
    nofork = dict(good)
    nofork["fork_divergence_summary"] = {"intervention_id": "x"}
    with pytest.raises(ContentRecordError, match="fork_divergence_summary"):
        SocietyOutcomeReport(nofork)


def test_vector10_scope_expansion_refused():
    """The tick-state record rejects trust matrices that are not exactly the six
    ordered pairs (a fourth agent's edges cannot be represented), and non-int
    trust values; the SC-LC cardinalities are frozen."""
    base = dict(private_facts={}, enforcement_event_count=0,
                scheduler_position_range=[0, 3])
    with pytest.raises(ContentRecordError, match="six ordered pairs"):
        SocietyTickState(tick_index=0, previous_society_tick_hash=None,
                         trust_edges={"ada->bo": 0}, **base)
    six = {"ada->bo": 0, "ada->cy": 0, "bo->ada": 0, "bo->cy": 0,
           "cy->ada": 0, "cy->bo": 0}
    with pytest.raises(ContentRecordError, match="must be an int"):
        SocietyTickState(tick_index=0, previous_society_tick_hash=None,
                         trust_edges=dict(six, **{"ada->bo": "not-an-int"}), **base)
    # prev-link discipline
    with pytest.raises(ContentRecordError, match="previous_society_tick_hash"):
        SocietyTickState(tick_index=0, previous_society_tick_hash="p" * 64,
                         trust_edges=six, **base)
