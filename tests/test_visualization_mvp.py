"""Read-only visualization MVP: evidence, non-interference, and HTTP boundary."""
from __future__ import annotations

import http.client
import json
import os
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from coliseum.textlab.schema import canonical_json, config_hash
from coliseum.textlab.spatial.run import execute_spatial_run
from coliseum.textlab.visualization import (
    EvidenceLimits, ReplayVerification, RunRoot, build_view_model,
    load_validated_run, verify_replay)
from coliseum.textlab.visualization.errors import VisualizationError
from coliseum.textlab.visualization.server import VisualizationService, serve
from coliseum.textlab.training.observation import observation_artifact

SCENARIO = "spatial_two_agent_private_object_v1"
LIVE_ID = "society_seed_v1--seed42--b63d84694594b499"
TREATMENT_ID = (
    "society_seed_v1--iv_society_seed_fact_flip_v1--seed42--0c6358d10a610b6a")


@pytest.fixture(scope="module")
def spatial_pack(tmp_path_factory):
    root = tmp_path_factory.mktemp("visualization-runs")
    summary = execute_spatial_run(SCENARIO, 42, out_root=str(root))
    return root, summary["run_id"]


@pytest.fixture(scope="module")
def validated(spatial_pack):
    return load_validated_run(*spatial_pack)


def _copy_pack(spatial_pack, tmp_path):
    root, run_id = spatial_pack
    tmp_path.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "runs"
    shutil.copytree(root, target)
    return target, run_id, target / run_id


def _write_json(path, value):
    path.write_text(canonical_json(value) + "\n", encoding="utf-8")


def _write_jsonl(path, rows):
    path.write_text("".join(canonical_json(row) + "\n" for row in rows),
                    encoding="utf-8")


def _sha_tree(run_dir):
    import hashlib
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in run_dir.iterdir() if path.is_file()}


def test_loader_rederives_complete_structural_evidence(validated):
    assert validated.run_id.startswith(f"{SCENARIO}--seed42--")
    assert len(validated.chain) == validated.run["chain_length"]
    assert len(validated.activations) == len(validated.chain) - 1
    assert len(validated.observations) == (
        len(validated.chain) * len(validated.run["observers"]))
    assert set(validated.file_hashes) == {
        "run.json", "chain.jsonl", "transitions.jsonl", "observations.jsonl",
        "activations.jsonl", "closure.json"}


def test_loader_is_immutable_and_does_not_write(validated):
    before = _sha_tree(Path(validated.run_dir))
    with pytest.raises(TypeError):
        validated.run["seed"] = 99
    assert _sha_tree(Path(validated.run_dir)) == before


def test_provider_free_spatial_replay_is_byte_identical(validated, tmp_path):
    result = verify_replay(validated, scratch_root=str(tmp_path / "scratch"))
    assert result.state == "verified"
    assert "byte-identical" in result.detail


def test_strict_json_refuses_duplicate_keys(spatial_pack, tmp_path):
    root, run_id, run_dir = _copy_pack(spatial_pack, tmp_path)
    path = run_dir / "run.json"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace('"seed":42', '"seed":42,"seed":42', 1),
                    encoding="utf-8")
    with pytest.raises(VisualizationError, match="malformed_json"):
        load_validated_run(root, run_id)


def test_unknown_schema_fails_closed(spatial_pack, tmp_path):
    root, run_id, run_dir = _copy_pack(spatial_pack, tmp_path)
    summary = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    summary["spatial_run_schema_version"] = "999"
    _write_json(run_dir / "run.json", summary)
    with pytest.raises(VisualizationError, match="unsupported_schema"):
        load_validated_run(root, run_id)


@pytest.mark.parametrize("field", [
    "scenario_schema_version", "spatial_schema_version",
    "scheduler_version", "renderer_version",
])
def test_every_summary_version_fails_closed_when_unsupported(
        spatial_pack, tmp_path, field):
    root, run_id, run_dir = _copy_pack(spatial_pack, tmp_path)
    summary = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    summary[field] = "unsupported-v999"
    _write_json(run_dir / "run.json", summary)
    with pytest.raises(VisualizationError, match="unsupported_schema"):
        load_validated_run(root, run_id)


def test_reordered_chain_cannot_masquerade_as_progress(spatial_pack, tmp_path):
    root, run_id, run_dir = _copy_pack(spatial_pack, tmp_path)
    rows = [json.loads(line) for line in
            (run_dir / "chain.jsonl").read_text(encoding="utf-8").splitlines()]
    rows[1], rows[2] = rows[2], rows[1]
    _write_jsonl(run_dir / "chain.jsonl", rows)
    with pytest.raises(VisualizationError, match="chain_order|chain_link"):
        load_validated_run(root, run_id)


@pytest.mark.parametrize("mutation", ["duplicate", "truncate"])
def test_duplicate_or_truncated_chain_fails_closed(spatial_pack, tmp_path, mutation):
    root, run_id, run_dir = _copy_pack(spatial_pack, tmp_path)
    path = run_dir / "chain.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows = (rows[:2] + [dict(rows[1])] + rows[2:]
            if mutation == "duplicate" else rows[:-1])
    _write_jsonl(path, rows)
    with pytest.raises(VisualizationError, match="chain_length|chain_order|chain_link"):
        load_validated_run(root, run_id)


def test_value_sensitive_candidate_validation(spatial_pack, tmp_path):
    root, run_id, run_dir = _copy_pack(spatial_pack, tmp_path)
    path = run_dir / "activations.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    activation = next(row for row in rows if row.get("candidate_universe"))
    activation["candidate_universe"][0]["effect"]["action"] = "advance_step"
    _write_jsonl(path, rows)
    with pytest.raises(VisualizationError, match="candidate_effect|candidate_identity"):
        load_validated_run(root, run_id)


def test_candidate_references_are_state_closure_bound(spatial_pack, tmp_path):
    root, run_id, run_dir = _copy_pack(spatial_pack, tmp_path)
    path = run_dir / "activations.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    activation = next(row for row in rows if len(row.get("candidate_universe", [])) > 1)
    candidate = activation["candidate_universe"][-1]
    effect = candidate["effect"]
    reference = next(key for key in effect if key.endswith("_id") and key != "agent_body_id")
    effect[reference] = "f" * 64
    candidate["action_id"] = canonical_json(effect)
    _write_jsonl(path, rows)
    with pytest.raises(VisualizationError, match="effect_closure"):
        load_validated_run(root, run_id)


def test_unsupported_action_and_malformed_location_fail_closed(spatial_pack, tmp_path):
    root, run_id, run_dir = _copy_pack(spatial_pack, tmp_path / "action")
    path = run_dir / "transitions.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[0]["content"]["effect"]["action"] = "execute_code"
    _write_jsonl(path, rows)
    with pytest.raises(VisualizationError, match="invalid_transition"):
        load_validated_run(root, run_id)

    root, run_id, run_dir = _copy_pack(spatial_pack, tmp_path / "location")
    path = run_dir / "observations.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    entity = rows[0]["actor_content"]["content"]["observable_state_projection"]["entities"][0]
    reference = next(key for key in entity["location"] if key.endswith("_id"))
    entity["location"][reference] = 7
    _write_jsonl(path, rows)
    with pytest.raises(VisualizationError, match="invalid_observation|actor_schema"):
        load_validated_run(root, run_id)


def test_actor_schema_rejects_privileged_carrier(spatial_pack, tmp_path):
    root, run_id, run_dir = _copy_pack(spatial_pack, tmp_path)
    path = run_dir / "observations.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[0]["actor_content"]["content"]["authoritative_placements"] = []
    _write_jsonl(path, rows)
    with pytest.raises(VisualizationError, match="actor_schema|invalid_observation|invalid_shape"):
        load_validated_run(root, run_id)


@pytest.mark.parametrize("location", [
    {"tag": "in_room", "room_instance_id": "f" * 64},
    {"tag": "held_by", "agent_body_id": "f" * 64},
    {"tag": "in_transit", "portal_instance_id": "f" * 64,
     "origin_room_instance_id": "e" * 64,
     "destination_room_instance_id": "d" * 64,
     "start_step": 1, "arrival_step": 2},
])
def test_reidentified_actor_locations_remain_bound_to_authenticated_state(
        spatial_pack, tmp_path, location):
    root, run_id, run_dir = _copy_pack(spatial_pack, tmp_path)
    path = run_dir / "observations.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    required_kind = "object" if location["tag"] == "held_by" else "agent_body"
    row = next(
        candidate for candidate in rows
        if any(entity["entity_kind"] == required_kind for entity in
               candidate["actor_content"]["content"]
               ["observable_state_projection"]["entities"]))
    entity = next(
        entity for entity in row["actor_content"]["content"]
        ["observable_state_projection"]["entities"]
        if entity["entity_kind"] == required_kind)
    entity["location"] = dict(location)
    content = row["actor_content"]["content"]
    row["actor_observation_id"] = observation_artifact("actor", content).id
    _write_jsonl(path, rows)
    with pytest.raises(VisualizationError, match="actor_state_binding"):
        load_validated_run(root, run_id)


def test_reidentified_actor_kind_remains_bound_to_authenticated_state(
        spatial_pack, tmp_path):
    root, run_id, run_dir = _copy_pack(spatial_pack, tmp_path)
    path = run_dir / "observations.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    row = rows[0]
    entity = row["actor_content"]["content"]["observable_state_projection"] \
        ["entities"][0]
    entity["entity_kind"] = (
        "object" if entity["entity_kind"] == "agent_body" else "agent_body")
    content = row["actor_content"]["content"]
    row["actor_observation_id"] = observation_artifact("actor", content).id
    _write_jsonl(path, rows)
    with pytest.raises(VisualizationError, match="actor_state_binding"):
        load_validated_run(root, run_id)


@pytest.mark.parametrize("mutation", [
    "coordinated_in_closure", "coordinated_out_of_closure", "omit_portals",
])
def test_visible_room_and_portals_derive_from_authenticated_observer_location(
        spatial_pack, tmp_path, mutation):
    root, run_id, run_dir = _copy_pack(spatial_pack, tmp_path)
    path = run_dir / "observations.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    row = next(candidate for candidate in rows if
               candidate["actor_content"]["content"]
               ["observable_state_projection"]["portals"])
    body = row["observer_body_id"]
    privileged_projection = row["privileged_content"]["content"] \
        ["observable_state_projection"]
    observer = next(entry for entry in
                    privileged_projection["authoritative_placements"]
                    if entry["entity_id"] == body)
    authenticated_room = observer["location"]["room_instance_id"]
    closure = json.loads((run_dir / "closure.json").read_text(encoding="utf-8"))
    if mutation == "coordinated_in_closure":
        forged_room = next(room for room in closure["rooms"]
                           if room != authenticated_room)
        for view in ("actor", "privileged"):
            row[f"{view}_content"]["content"]["visible_room_identity"] = \
                forged_room
        row["actor_content"]["content"]["observable_state_projection"] \
            ["portals"] = [
                {"portal_instance_id": portal["portal_instance_id"],
                 "to_room_instance_id": portal["to_room_instance_id"]}
                for portal in closure["portals"]
                if portal["from_room_instance_id"] == forged_room
            ]
    elif mutation == "coordinated_out_of_closure":
        for view in ("actor", "privileged"):
            row[f"{view}_content"]["content"]["visible_room_identity"] = "f" * 64
        row["actor_content"]["content"]["observable_state_projection"] \
            ["portals"] = []
    else:
        row["actor_content"]["content"]["observable_state_projection"] \
            ["portals"] = []
    for view in ("actor", "privileged"):
        content = row[f"{view}_content"]["content"]
        row[f"{view}_observation_id"] = observation_artifact(view, content).id
    _write_jsonl(path, rows)
    with pytest.raises(VisualizationError, match="actor_state_binding"):
        load_validated_run(root, run_id)


def test_symlink_and_traversal_are_refused(spatial_pack, tmp_path):
    root, run_id, run_dir = _copy_pack(spatial_pack, tmp_path)
    closure = run_dir / "closure.json"
    source = tmp_path / "outside.json"
    source.write_bytes(closure.read_bytes())
    closure.unlink()
    closure.symlink_to(source)
    with pytest.raises(VisualizationError, match="unsafe_evidence_file"):
        load_validated_run(root, run_id)
    with pytest.raises(VisualizationError, match="unsafe_run_id"):
        load_validated_run(root, "../escape")


def test_configured_and_absolute_size_ceilings_fail_closed():
    with pytest.raises(VisualizationError, match="invalid_limits"):
        EvidenceLimits(line_bytes=4 * 1024 * 1024 + 1)
    with pytest.raises(VisualizationError, match="invalid_limits"):
        EvidenceLimits(rows_per_stream=0)


def test_bounded_loader_refuses_oversized_input(spatial_pack):
    root, run_id = spatial_pack
    with pytest.raises(VisualizationError, match="file_limit"):
        load_validated_run(root, run_id, EvidenceLimits(json_bytes=32))


def test_optional_file_names_are_closed(spatial_pack):
    root, run_id = spatial_pack
    with pytest.raises(VisualizationError, match="unsafe_evidence_file"):
        RunRoot(root).read(run_id, optional=("../outside",))


def test_actor_view_contains_no_privileged_carriers_or_other_actor_labels(validated):
    actor_key = sorted(validated.run["observers"])[0]
    model = build_view_model(validated, "actor", actor_key)
    encoded = json.dumps(model, sort_keys=True)
    for forbidden in ("privileged_content", "privileged_observation_id",
                      "authoritative_placements", "authoritative_lifecycle",
                      "closure_visible_state_commitment", "scheduler_state_id",
                      "transition_id", "activation_id", "instance_ids"):
        assert forbidden not in encoded
    for other_key in set(validated.run["observers"]) - {actor_key}:
        assert other_key not in encoded


def test_actor_view_omits_hidden_private_object(validated):
    private_key = validated.run["private_object_key"]
    assert private_key is not None
    private_id = validated.run["instance_ids"][private_key]
    visible_by_actor = {}
    for key, body in validated.run["observers"].items():
        visible_by_actor[key] = {entity["id"] for snapshot in
                                 build_view_model(validated, "actor", key)["snapshots"]
                                 for entity in snapshot["entities"]}
    hidden_actor = next(key for key, visible in visible_by_actor.items()
                        if private_id not in visible)
    assert private_id not in json.dumps(build_view_model(validated, "actor", hidden_actor))
    assert private_id in json.dumps(build_view_model(validated, "privileged"))


def test_view_model_ordering_and_layout_are_deterministic(validated):
    first = json.dumps(build_view_model(validated, "privileged"), sort_keys=True)
    second = json.dumps(build_view_model(validated, "privileged"), sort_keys=True)
    assert first == second
    model = json.loads(first)
    for snapshot in model["snapshots"]:
        assert [room["id"] for room in snapshot["rooms"]] == \
            sorted(room["id"] for room in snapshot["rooms"])
        assert [entity["id"] for entity in snapshot["entities"]] == \
            sorted(entity["id"] for entity in snapshot["entities"])
    assert [event["position"] for event in model["events"]] == \
        sorted(event["position"] for event in model["events"])
    chain_ids = {row["scheduler_state_id"] for row in validated.chain}
    assert all(event["structured"]["scheduler_state_id"] in chain_ids
               for event in model["events"])


def test_actor_events_link_only_to_actor_observation_records(validated):
    actor_key = sorted(validated.run["observers"])[0]
    body = validated.run["observers"][actor_key]
    allowed = {row["actor_observation_id"] for row in validated.observations
               if row["observer_body_id"] == body}
    model = build_view_model(validated, "actor", actor_key)
    assert model["events"]
    assert all(event["structured"]["source_actor_observation_id"] in allowed
               for event in model["events"])


def test_invalid_perspective_fails_closed(validated):
    with pytest.raises(VisualizationError, match="invalid_perspective"):
        build_view_model(validated, "client-toggle")


def test_visible_inventory_is_derived_only_from_visible_placements(validated):
    for perspective, actor in (("privileged", None),
                               ("actor", sorted(validated.run["observers"])[0])):
        model = build_view_model(validated, perspective, actor)
        for snapshot in model["snapshots"]:
            visible = {entity["id"] for entity in snapshot["entities"]}
            for entity in snapshot["entities"]:
                if entity["kind"] == "agent_body":
                    assert set(entity["visible_inventory_ids"]) <= visible


def test_dynamic_state_changes_follow_recorded_snapshots(validated):
    model = build_view_model(validated, "privileged")
    state_signatures = {
        tuple((entity["id"], canonical_json(entity["location"]))
              for entity in snapshot["entities"])
        for snapshot in model["snapshots"]}
    assert len(state_signatures) > 1
    assert model["map_model"]["simulation_impact"] is False
    assert model["experiment"]["experiment_id"] is None
    assert model["experiment"]["agent_regime"] is None
    assert {overlay["id"] for overlay in model["overlay_catalog"]} >= {
        "room_labels", "portal_connectivity", "entity_locations", "event_markers"}


def test_experiment_strings_remain_data_not_markup(spatial_pack, tmp_path):
    root, run_id, run_dir = _copy_pack(spatial_pack, tmp_path)
    path = run_dir / "run.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    body = next(iter(summary["observers"].values()))
    key = next(key for key, value in summary["instance_ids"].items() if value == body)
    hostile = '"><script>globalThis.pwned=true</script>'
    summary["instance_ids"].pop(key)
    summary["instance_ids"][hostile] = body
    _write_json(path, summary)
    model = build_view_model(load_validated_run(root, run_id), "privileged")
    assert any(entity["label"] == hostile for entity in model["snapshots"][0]["entities"])
    script = Path("coliseum/textlab/visualization/static/app.js").read_text(encoding="utf-8")
    assert "textContent" in script and "innerHTML" not in script


def _copy_treatment_pair(tmp_path):
    source_root = Path("logs/society-runs")
    treatment_summary = json.loads(
        (source_root / TREATMENT_ID / "run.json").read_text(encoding="utf-8"))
    control_id = treatment_summary["treatment_bindings"]["control_run_id"]
    root = tmp_path / "society-runs"
    shutil.copytree(source_root / control_id, root / control_id)
    shutil.copytree(source_root / TREATMENT_ID, root / TREATMENT_ID)
    return root, root / TREATMENT_ID


def _refresh_treatment_execution_identity(summary):
    from coliseum.textlab.spatial.calibration import (
        derive_execution_instance_id, intervention_record)
    spec = intervention_record(summary["intervention_id"]).canonical_spec
    bindings = summary["treatment_bindings"]
    summary["execution_instance_id"] = derive_execution_instance_id(
        summary["intervention_id"], summary["scenario"], summary["seed"],
        spec["agent_key"], bindings["parent_world_line_id"],
        bindings["control_source_evidence_id"], bindings["fork_position"],
        bindings["fork_state_hash"])


def test_treatment_provenance_cross_binds_valid_control(tmp_path):
    root, _run_dir = _copy_treatment_pair(tmp_path)
    validated = load_validated_run(root, TREATMENT_ID)
    assert validated.run["spatial_run_schema_version"] == "0.3"


@pytest.mark.parametrize("mutation", [
    "witness_manifest", "coordinated_manifest", "fork_genesis",
    "witness_state", "parent_world_line", "control_source", "control_run",
])
def test_treatment_provenance_drift_fails_closed(tmp_path, mutation):
    root, run_dir = _copy_treatment_pair(tmp_path)
    path = run_dir / "run.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    bindings = summary["treatment_bindings"]
    witness = summary["witness_ids"]
    if mutation == "witness_manifest":
        witness["scheduler_manifest_id"] = "f" * 64
    elif mutation == "coordinated_manifest":
        witness["scheduler_manifest_id"] = "f" * 64
        bindings["control_manifest_id"] = "f" * 64
    elif mutation == "fork_genesis":
        bindings["fork_genesis_id"] = "f" * 64
    elif mutation == "witness_state":
        witness["scheduler_state_id"] = "f" * 64
    elif mutation == "parent_world_line":
        bindings["parent_world_line_id"] = "f" * 64
        _refresh_treatment_execution_identity(summary)
    elif mutation == "control_source":
        bindings["control_source_evidence_id"] = "f" * 64
        _refresh_treatment_execution_identity(summary)
    elif mutation == "control_run":
        bindings["control_run_id"] = "society_seed_v1--seed42--" + "f" * 16
    _write_json(path, summary)
    with pytest.raises(VisualizationError):
        load_validated_run(root, TREATMENT_ID)


def test_live_pack_preserves_incomplete_nonclaimable_ceiling():
    root = Path("logs/live-persona-runs").resolve()
    validated = load_validated_run(root, LIVE_ID)
    actor_model = build_view_model(validated, "actor", "ada")
    privileged_model = build_view_model(validated, "privileged")
    assert actor_model["validation"]["completion"] == "unknown"
    assert actor_model["validation"]["behavioral_claimability"] == "unknown"
    assert actor_model["validation"]["result_status"] == "unknown"
    assert actor_model["validation"]["report_authentication"] == "not_exposed"
    assert privileged_model["validation"]["completion"] == "incomplete"
    assert privileged_model["validation"]["behavioral_claimability"] == \
        "nonclaimable"
    assert privileged_model["validation"]["result_status"] == "incomplete"
    assert actor_model["experiment"]["model_regime"] is None
    assert privileged_model["experiment"]["model_regime"]["source"] == \
        "structurally_valid_unverified_report"
    assert privileged_model["experiment"]["termination"]["code"] == "control_desync"


def test_actor_view_is_invariant_to_live_report_presence_and_content(tmp_path):
    source = Path("logs/live-persona-runs") / LIVE_ID
    models = []
    for label in ("committed", "absent", "mutated", "favorable"):
        root = tmp_path / label
        target = root / LIVE_ID
        shutil.copytree(source, target)
        report_path = target / "live_report.json"
        if label == "absent":
            report_path.unlink()
        elif label == "mutated":
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["content"]["regime"]["backend_version"] = "mutated-private-report"
            report["content"]["regime_id"] = config_hash(report["content"]["regime"])
            report["id"] = config_hash(report["content"])
            _write_json(report_path, report)
        elif label == "favorable":
            report = json.loads(report_path.read_text(encoding="utf-8"))
            floor = report["content"]["effective_n_floor"]
            report["content"].update({
                "status": "complete", "complete": True,
                "behavioral_departure_claimable": True, "terminated": None,
                "decisions_requested": floor, "decisions_parsed_ok": floor,
                "effective_n": floor, "per_code_counts": {"ok": floor},
            })
            while len(report["content"]["per_tick"]) < floor:
                report["content"]["per_tick"].append(
                    dict(report["content"]["per_tick"][-1]))
            report["content"]["per_tick"] = report["content"]["per_tick"][:floor]
            report["id"] = config_hash(report["content"])
            _write_json(report_path, report)
        validated = load_validated_run(root, LIVE_ID)
        replay = ReplayVerification(
            "failed" if label == "favorable" else "verified",
            f"private replay detail for {label}",
            "failed" if label == "mutated" else "unverified")
        models.append(json.dumps(
            build_view_model(validated, "actor", "ada", replay),
            sort_keys=True))
    assert len(set(models)) == 1


def test_counterfeit_favorable_report_is_not_presented_as_claimable(tmp_path):
    source = Path("logs/live-persona-runs") / LIVE_ID
    root = tmp_path / "live"
    target = root / LIVE_ID
    shutil.copytree(source, target)
    report_path = target / "live_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["content"]["status"] = "complete"
    report["content"]["complete"] = True
    report["content"]["behavioral_departure_claimable"] = True
    report["content"]["terminated"] = None
    report["content"]["effective_n"] = report["content"]["effective_n_floor"]
    report["content"]["decisions_parsed_ok"] = report["content"]["effective_n_floor"]
    report["content"]["decisions_requested"] = report["content"]["effective_n_floor"]
    report["content"]["per_code_counts"] = {"ok": report["content"]["effective_n_floor"]}
    while len(report["content"]["per_tick"]) < report["content"]["effective_n_floor"]:
        report["content"]["per_tick"].append(dict(report["content"]["per_tick"][-1]))
    report["id"] = config_hash(report["content"])
    _write_json(report_path, report)
    validated = load_validated_run(root, LIVE_ID)
    provenance = build_view_model(validated, "privileged")["validation"]
    assert provenance["replay_verification"] == "unverified"
    assert provenance["completion"] == "unknown"
    assert provenance["behavioral_claimability"] == "unknown"
    replay = verify_replay(validated, scratch_root=str(tmp_path / "counterfeit-replay"))
    assert replay.state == "verified"
    assert replay.report_state == "unverified"
    authenticated = build_view_model(validated, "privileged",
                                     replay_verification=replay)["validation"]
    assert authenticated["completion"] == "unknown"
    assert authenticated["behavioral_claimability"] == "unknown"


@pytest.mark.parametrize("field,value", [
    ("complete", 0), ("complete", 0.0),
    ("behavioral_departure_claimable", 0),
    ("behavioral_departure_claimable", 0.0),
])
def test_live_claim_booleans_are_type_exact(tmp_path, field, value):
    source = Path("logs/live-persona-runs") / LIVE_ID
    root = tmp_path / "live"
    target = root / LIVE_ID
    shutil.copytree(source, target)
    path = target / "live_report.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    report["content"][field] = value
    report["id"] = config_hash(report["content"])
    _write_json(path, report)
    with pytest.raises(VisualizationError, match="claim_integrity"):
        load_validated_run(root, LIVE_ID)


def test_provider_free_live_replay_is_byte_identical(tmp_path):
    validated = load_validated_run("logs/live-persona-runs", LIVE_ID)
    result = verify_replay(validated, scratch_root=str(tmp_path / "live-replay"))
    assert result.state == "verified"
    assert "zero model calls" in result.detail


@pytest.fixture
def actor_server(spatial_pack):
    root, _run_id = spatial_pack
    actor = sorted(load_validated_run(root, _run_id).run["observers"])[0]
    service = VisualizationService(root, "actor", actor, capability="t" * 43)
    server, url = serve(service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield service, server, url
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def test_http_boundary_sets_security_headers_and_serves_scoped_json(actor_server):
    service, _server, url = actor_server
    with urllib.request.urlopen(url + "api/v1/runs", timeout=5) as response:
        body = json.load(response)
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert "default-src 'self'" in response.headers["Content-Security-Policy"]
        assert response.headers.get("Access-Control-Allow-Origin") is None
    assert body["perspective"] == "actor"
    assert body["runs"] and "observer_count" not in body["runs"][0]
    run_id = body["runs"][0]["run_id"]
    with urllib.request.urlopen(url + f"api/v1/runs/{run_id}/view", timeout=5) as response:
        encoded = response.read().decode("utf-8")
    assert "authoritative_placements" not in encoded
    assert "privileged_content" not in encoded
    assert service.capability not in encoded
    run_id = body["runs"][0]["run_id"]
    assert service.view(run_id) is service.view(run_id)


def test_http_boundary_rejects_wrong_host_raw_paths_and_mutation(actor_server):
    service, server, url = actor_server
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    connection.request("GET", f"/{service.capability}/api/v1/health",
                       headers={"Host": "attacker.invalid"})
    assert connection.getresponse().status == 421
    connection.close()
    with pytest.raises(urllib.error.HTTPError) as raw:
        urllib.request.urlopen(url + "raw/run.json", timeout=5)
    assert raw.value.code == 404
    request = urllib.request.Request(url + "api/v1/runs", method="POST", data=b"{}")
    with pytest.raises(urllib.error.HTTPError) as mutation:
        urllib.request.urlopen(request, timeout=5)
    assert mutation.value.code == 405


def test_static_client_uses_safe_text_and_accessible_controls(actor_server):
    _service, _server, url = actor_server
    with urllib.request.urlopen(url, timeout=5) as response:
        html = response.read().decode("utf-8")
    with urllib.request.urlopen(url + "static/app.js", timeout=5) as response:
        script = response.read().decode("utf-8")
    assert "innerHTML" not in script and "eval(" not in script
    assert "textContent" in script and "createElementNS" in script
    assert "event-marker" in script and 'id="reset-camera"' in html
    assert not __import__("re").search(r"state\.model\.[A-Za-z0-9_]+\s*=", script)
    assert 'aria-live="polite"' in html
    assert 'id="play-pause"' in html and 'id="scrubber"' in html
    assert "prefers-reduced-motion" in (Path(
        "coliseum/textlab/visualization/static/styles.css").read_text(encoding="utf-8"))
