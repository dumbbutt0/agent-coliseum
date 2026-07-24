"""Synthetic acceptance tests for the M8 incomplete-closure source slice.

No fixture reads the captured M8 namespace, contacts a model, or calls the
scientific order-report path.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import multiprocessing
import shutil
import subprocess
import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from coliseum.textlab import incomplete_result as ir
from tools.council import m8_incomplete_handoff as handoff
from tools.council import (
    codex_watch, events, locking, publish, state_machine, storage)
from tests.council_util import (
    append, make_cfg, make_repo, make_request, make_root, make_verdict)
from tools.council.schemas import (
    CouncilError, SchemaViolation, TransitionError,
    compute_execution_authorization_hash, compute_request_payload_hash,
    validate_result_artifacts)


COMMIT = "c" * 40


def _execution_authorization():
    return {
        "schema_version": "execution-authorization.v1",
        "experiment_id": ir.EXPERIMENT_ID,
        "design_hash":
            "431871d3266a96999ef02d0d9eb77caba7e6b317135155d3161b1eecf396d533",
        "implementation_commit": handoff.SOURCE_IMPLEMENTATION_COMMIT,
        "experiment_config_hash":
            "4847cadfdac059195986114fed6d61850f3c1d925ca4b97618a06cff59e5c960",
        "model_digests": {
            "huihui_ai/qwen2.5-abliterate:7b-instruct":
                "103482475c9b4d4032999dd5d7383478cad8b966ae6ae984d525daf7352c2219",
        },
        "planned_runs": 144,
        "budget": {
            "max_units": 144,
            "max_compute_minutes": 240,
            "max_wall_minutes": 240,
            "max_storage_mb": 1024,
            "max_retries_per_unit": 0,
            "max_scenarios": 3,
        },
        "evidence_root": ir.EVIDENCE_ROOT,
        "manifest": ir.MANIFEST,
        "m7_prerequisite_events": [
            "001714-6f7a48e0", "001719-21604e97", "001724-8cebf880"],
        "source_integration_events": [
            "002351-a757f517", "002352-60b9033f", "002353-23a8b8e9",
            "002354-a86c0efb", "002355-c7998be4"],
        "resume_from": None,
    }


def _partial():
    directory = f"{ir.EVIDENCE_ROOT}/partial-run"
    return {
        "execution_index": 105,
        "model": "huihui_ai/qwen2.5-abliterate:7b-instruct",
        "scenario": "scramble_dev_m8",
        "scenario_seed": 1,
        "sampler_seed": 2012,
        "directory": directory,
        "files": {
            f"{directory}/decisions.jsonl": ir.PARTIAL_DECISIONS_SHA256,
            f"{directory}/scenario.snapshot.json":
                ir.PARTIAL_SNAPSHOT_SHA256,
        },
        "sequence_start": 0,
        "sequence_end": 5,
        "completed_exposure_ids": ["e_trust", "e_betrayal"],
        "terminal_probe_present": False,
    }


def _authorization():
    execution = _execution_authorization()
    return {
        "schema_version":
            "m8-budget-exhaustion-closure-authorization.v1",
        "profile_id": ir.PROFILE_ID,
        "source_request": {
            "request_id": handoff.SOURCE_REQUEST_ID,
            "request_payload_hash": handoff.SOURCE_REQUEST_PAYLOAD_HASH,
            "publication_event_id": handoff.SOURCE_PUBLICATION_EVENT_ID,
            "publication_event_hash": handoff.SOURCE_PUBLICATION_EVENT_HASH,
            "audit_go_event_id": handoff.SOURCE_AUDIT_GO_EVENT_ID,
            "audit_go_event_hash": handoff.SOURCE_AUDIT_GO_EVENT_HASH,
            "owner_approval_event_id": "002363-31331680",
            "owner_approval_event_hash":
                handoff.SOURCE_OWNER_APPROVAL_EVENT_HASH,
        },
        "execution_authorization": execution,
        "execution_authorization_hash":
            compute_execution_authorization_hash(execution),
        "terminal_events": {
            "start": {
                "event_id": handoff.START_EVENT_ID,
                "event_hash": handoff.START_EVENT_HASH,
                "previous_event_hash": handoff.START_PREDECESSOR_HASH,
                "timestamp_utc": handoff.START_TIMESTAMP,
            },
            "pause": {
                "event_id": handoff.PAUSE_EVENT_ID,
                "event_hash": handoff.PAUSE_EVENT_HASH,
                "previous_event_hash": handoff.START_EVENT_HASH,
                "timestamp_utc": handoff.PAUSE_TIMESTAMP,
                "reason": handoff.PAUSE_REASON,
            },
        },
        "closure_tool": {
            "target_commit": COMMIT,
            "integration_events": [
                {
                    "request_id": rid,
                    "event_id": f"{i:06d}-{i:08x}",
                    "event_hash": f"{i:064x}",
                    "target_commit": COMMIT,
                }
                for i, rid in enumerate(
                    handoff.SOURCE_SLICE_REQUEST_IDS, 1)
            ],
        },
        "closure_budget": {
            "max_compute_minutes": 240,
            "max_wall_minutes": 240,
            "max_storage_mb": 1024,
            "max_replay_runs": 105,
            "max_retries_per_run": 0,
        },
        "primary_evidence": {
            "evidence_root": ir.EVIDENCE_ROOT,
            "manifest": ir.MANIFEST,
            "manifest_sha256": ir.MANIFEST_SHA256,
            "tombstone_ledger": {"state": "absent", "sha256": None},
            "primary_file_count": 423,
            "primary_inventory_content_hash":
                ir.PRIMARY_INVENTORY_CONTENT_HASH,
            "coordinate_census_content_hash":
                ir.COORDINATE_CENSUS_CONTENT_HASH,
            "successful_runs": 105,
            "partial_runs": 1,
            "unattempted_runs": 38,
            "tombstoned_runs": 0,
            "terminal_outcomes": 105,
            "partial": _partial(),
        },
        "outcome": copy.deepcopy(ir.OUTCOME),
        "derived_output_root": ir.DERIVED_OUTPUT_ROOT,
    }


def _proposal():
    auth = _authorization()
    return {
        "event_id": "000101-aaaaaaaa",
        "event_hash": "a" * 64,
        "event_type": "RESULT_HANDOFF_APPROVAL_REQUIRED",
        "request_id": ir.RESULT_REQUEST_ID,
        "repository": "/tmp/repo",
        "target_commit": COMMIT,
        "payload": {
            "schema_version": "result-handoff-approval-required.v1",
            "closure_authorization": auth,
            "closure_authorization_hash":
                handoff.closure_authorization_hash(auth),
        },
    }


def _approval():
    proposal = _proposal()
    return {
        "event_id": "000102-bbbbbbbb",
        "event_hash": "b" * 64,
        "event_type": "RESULT_HANDOFF_APPROVED",
        "request_id": ir.RESULT_REQUEST_ID,
        "repository": "/tmp/repo",
        "target_commit": COMMIT,
        "payload": {
            "schema_version": "result-handoff-approval.v1",
            "approved_by": "human",
            "approval_commit": COMMIT,
            "proposal_event_id": proposal["event_id"],
            "proposal_event_hash": proposal["event_hash"],
            "closure_authorization":
                proposal["payload"]["closure_authorization"],
            "closure_authorization_hash":
                proposal["payload"]["closure_authorization_hash"],
            "human_token": {
                "counter": 1, "preimage_hex": "f" * 64, "binds": "e" * 64},
        },
    }


def _spec():
    return {
        "models": ["huihui_ai/qwen2.5-abliterate:7b-instruct"],
        "scenarios":
            ["scramble_dev_m8", "scramble_perm_m8", "scramble_sham_m8"],
        "scenario_seeds": [42, 1],
        "sampler_seeds": list(range(2001, 2025)),
        "execution_order": "interleaved",
    }


def _repository_root():
    return os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))


def _success_rows():
    return [
        {
            **{key: value for key, value in entry.items()
               if key != "execution_index"},
            "execution_index": entry["execution_index"],
        }
        for entry in ir.planned_coordinates(_spec())[:105]
    ]


def _replay_core():
    return {
        "manifest_sha256": ir.MANIFEST_SHA256,
        "tombstone_ledger": {"state": "absent", "sha256": None},
        "runs": {
            f"run-{i:03d}": {
                "run_dir": f"run-{i:03d}",
                "replay_ok": True,
                "run_json_sha256": "1" * 64,
                "decisions_sha256": "2" * 64,
                "captures_sha256": "3" * 64,
            }
            for i in range(105)
        },
    }


def _snapshot():
    census = ir.build_coordinate_census(_spec(), _success_rows(), _partial())
    # Synthetic coordinates intentionally have a different content hash from
    # the captured pack; artifact construction binds whatever authenticated
    # snapshot the caller supplied. Production admission checks the frozen hash.
    census["content_hash"] = ir.COORDINATE_CENSUS_CONTENT_HASH
    return {
        "primary": _authorization()["primary_evidence"],
        "inventory": {
            "schema_version": "m8-budget-exhaustion-primary-inventory.v1",
            "evidence_root": ir.EVIDENCE_ROOT,
            "file_count": 423,
            "files": {"manifest.jsonl": ir.MANIFEST_SHA256},
            "content_hash": ir.PRIMARY_INVENTORY_CONTENT_HASH,
        },
        "census": census,
    }


def _objects_and_request(repo="/tmp/repo"):
    proposal, approval = _proposal(), _approval()
    objects = handoff._artifact_objects(
        _snapshot(), _replay_core(), _authorization(), proposal, approval,
        "d" * 64)
    data = handoff._artifact_bytes(objects)
    hashes = handoff._file_hashes(data)
    request = handoff._result_request(
        repo, _authorization(), approval, objects, hashes)
    return objects, data, request


def test_outcome_is_exact_inconclusive_claim_ceiling():
    assert ir.OUTCOME == {
        "analysis_status": "budget_exhausted_incomplete",
        "scientific_verdict": "inconclusive",
        "statistics_computed": False,
        "claimable": False,
        "conclusion_scope": (
            "The frozen M8 execution did not complete within its "
            "owner-selected budget. The captured evidence is authenticated, "
            "but no order-effect or null claim is licensed."),
    }


def test_module_has_no_scientific_analysis_import():
    source = open(ir.__file__, encoding="utf-8").read()
    assert "metrics" not in source
    assert "order_sensitivity_report" not in source


def test_planned_coordinates_are_exact_interleaved_grid():
    entries = ir.planned_coordinates(_spec())
    assert len(entries) == 144
    assert entries[0]["scenario"] == "scramble_dev_m8"
    assert entries[1]["scenario"] == "scramble_perm_m8"
    assert entries[2]["scenario"] == "scramble_sham_m8"
    assert entries[105] == {
        "execution_index": 105,
        "model": "huihui_ai/qwen2.5-abliterate:7b-instruct",
        "scenario": "scramble_dev_m8",
        "scenario_seed": 1,
        "sampler_seed": 2012,
    }


def test_resolved_closure_plan_binds_config_order_without_mutating_registry(
        monkeypatch):
    from coliseum.textlab import registry

    repo = _repository_root()
    registry_path = os.path.join(repo, handoff.REGISTRY_REL)
    bundle = registry.load_verified_bundle(registry_path, ir.EXPERIMENT_ID)
    original = copy.deepcopy(bundle.planned_design)
    monkeypatch.setattr(
        registry, "load_verified_bundle", lambda *_args, **_kwargs: bundle)

    plan = handoff._resolved_closure_plan(repo)

    assert bundle.planned_design == original
    assert plan is not bundle.planned_design
    assert plan["execution_order"] == "interleaved"
    assert len(ir.planned_coordinates(plan)) == 144
    assert ir.planned_coordinates(plan)[105] == {
        "execution_index": 105,
        "model": "huihui_ai/qwen2.5-abliterate:7b-instruct",
        "scenario": "scramble_dev_m8",
        "scenario_seed": 1,
        "sampler_seed": 2012,
    }
    plan["scenarios"].append("mutation-probe")
    assert bundle.planned_design == original


def _copied_frozen_config(tmp_path):
    repo = _repository_root()
    shutil.copytree(os.path.join(repo, "configs"), tmp_path / "configs")
    return str(tmp_path), tmp_path / handoff.EXPERIMENT_CONFIG_REL


def test_resolved_closure_plan_refuses_config_sha_drift_before_coordinates(
        tmp_path, monkeypatch):
    repo, config_path = _copied_frozen_config(tmp_path)
    with open(config_path, "a", encoding="utf-8") as fh:
        fh.write("\n")
    monkeypatch.setattr(
        ir, "planned_coordinates",
        lambda *_args, **_kwargs: pytest.fail("coordinates reached"))
    with pytest.raises(CouncilError, match="config hash differs"):
        handoff._resolved_closure_plan(repo)


@pytest.mark.parametrize("replacement", ["blocked", None])
def test_resolved_closure_plan_refuses_wrong_or_missing_order_before_coordinates(
        tmp_path, monkeypatch, replacement):
    from coliseum.textlab import registry

    repo, config_path = _copied_frozen_config(tmp_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if replacement is None:
        config.pop("execution_order")
    else:
        config["execution_order"] = replacement
    config_path.write_text(json.dumps(config), encoding="utf-8")
    original_hash = ir.file_sha256
    monkeypatch.setattr(
        ir, "file_sha256",
        lambda path: handoff.FROZEN_CONFIG_SHA256
        if os.path.realpath(path) == os.path.realpath(config_path)
        else original_hash(path))
    monkeypatch.setattr(
        registry, "lint_experiment_config", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        ir, "planned_coordinates",
        lambda *_args, **_kwargs: pytest.fail("coordinates reached"))
    with pytest.raises(CouncilError, match="execution order differs"):
        handoff._resolved_closure_plan(repo)


def test_resolved_closure_plan_refuses_config_design_mismatch(
        tmp_path, monkeypatch):
    repo, config_path = _copied_frozen_config(tmp_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["design_hash"] = "0" * 64
    config_path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(
        ir, "file_sha256", lambda _path: handoff.FROZEN_CONFIG_SHA256)
    monkeypatch.setattr(
        ir, "planned_coordinates",
        lambda *_args, **_kwargs: pytest.fail("coordinates reached"))
    with pytest.raises(CouncilError, match="config design identity differs"):
        handoff._resolved_closure_plan(repo)


def test_resolved_closure_plan_refuses_registry_design_mismatch(monkeypatch):
    from coliseum.textlab import registry

    bundle = registry.load_verified_bundle(
        os.path.join(_repository_root(), handoff.REGISTRY_REL),
        ir.EXPERIMENT_ID)
    monkeypatch.setattr(
        registry, "load_verified_bundle",
        lambda *_args, **_kwargs: SimpleNamespace(
            experiment_id=ir.EXPERIMENT_ID,
            design_hash="0" * 64,
            planned_design=copy.deepcopy(bundle.planned_design)))
    monkeypatch.setattr(
        ir, "planned_coordinates",
        lambda *_args, **_kwargs: pytest.fail("coordinates reached"))
    with pytest.raises(CouncilError, match="registry design identity differs"):
        handoff._resolved_closure_plan(_repository_root())


def test_resolved_closure_plan_refuses_lint_failure_before_coordinates(
        monkeypatch):
    from coliseum.textlab import registry

    monkeypatch.setattr(
        registry, "lint_experiment_config",
        lambda *_args, **_kwargs: ["synthetic mismatch"])
    monkeypatch.setattr(
        ir, "planned_coordinates",
        lambda *_args, **_kwargs: pytest.fail("coordinates reached"))
    with pytest.raises(CouncilError, match="synthetic mismatch"):
        handoff._resolved_closure_plan(_repository_root())


def test_source_request_generations_preserve_history_and_select_only_002():
    historical = {
        f"first-gladiator-m8-incomplete-closure-{section}-001"
        for section in "abcde"}
    current = {
        f"first-gladiator-m8-incomplete-closure-{section}-002"
        for section in "abcde"}
    assert historical | current <= state_machine.M8_CLOSURE_SOURCE_REQUESTS
    assert set(handoff.SOURCE_SLICE_REQUEST_IDS) == current
    recovery = {
        f"first-gladiator-m8-incomplete-recovery-{section}-001"
        for section in "abcde"}
    assert set(handoff.RECOVERY_SOURCE_REQUEST_IDS) == recovery
    assert recovery <= state_machine.M8_CLOSURE_SOURCE_REQUESTS


def test_proposal_primary_admission_passes_exact_resolved_plan_to_derivation(
        tmp_path, monkeypatch):
    repo = str(tmp_path)
    resolved_plan = _spec()
    original = copy.deepcopy(resolved_plan)
    observed = []
    sweep = handoff.importlib.import_module("coliseum.textlab.sweep")

    monkeypatch.setattr(
        handoff, "_resolved_closure_plan", lambda _repo: resolved_plan)

    @contextmanager
    def fake_manifest_lock(path):
        yield path

    monkeypatch.setattr(sweep, "_manifest_advisory_lock", fake_manifest_lock)

    def tracked_derivation(_repo, _manifest, _evidence_root, planned_design):
        observed.append(planned_design)
        return {"primary": {"synthetic": True}}

    monkeypatch.setattr(
        handoff, "_derive_primary_locked", tracked_derivation)

    assert handoff._derive_primary(repo) == {"synthetic": True}
    assert observed == [resolved_plan]
    assert observed[0] is resolved_plan
    assert resolved_plan == original


@pytest.mark.parametrize("field,value", [
    ("execution_order", "blocked"),
    ("models", []),
    ("scenarios", []),
    ("scenario_seeds", []),
    ("sampler_seeds", []),
])
def test_planned_coordinates_refuse_grid_drift(field, value):
    spec = _spec()
    spec[field] = value
    with pytest.raises(ir.IncompleteResultError):
        ir.planned_coordinates(spec)


def test_coordinate_census_has_exact_classification_sequence():
    census = ir.build_coordinate_census(_spec(), _success_rows(), _partial())
    classes = [entry["classification"] for entry in census["entries"]]
    assert classes == (
        ["success"] * 105 + ["partial_nonterminal"] + ["unattempted"] * 38)


@pytest.mark.parametrize("mutation", [
    lambda rows, partial: rows.pop(),
    lambda rows, partial: rows.append(copy.deepcopy(rows[0])),
    lambda rows, partial: partial.__setitem__("execution_index", 106),
    lambda rows, partial: partial.__setitem__("sampler_seed", 2013),
    lambda rows, partial: rows[0].__setitem__("execution_index", 3),
])
def test_coordinate_census_refuses_mismatch(mutation):
    rows, partial = _success_rows(), _partial()
    mutation(rows, partial)
    with pytest.raises(ir.IncompleteResultError):
        ir.build_coordinate_census(_spec(), rows, partial)


def _write_partial(path, records):
    path.write_text("".join(json.dumps(record) + "\n" for record in records),
                    encoding="utf-8")


def _partial_records():
    records = []
    for seq, (kind, dp) in enumerate([
            ("decision_node", "e_trust"), ("outcome", None),
            ("memory_update", None), ("decision_node", "e_betrayal"),
            ("outcome", None), ("memory_update", None)]):
        records.append({"seq": seq, "kind": kind,
                        "data": ({"dp_id": dp} if dp else {})})
    return records


def test_partial_ledger_accepts_two_complete_exposure_cycles(tmp_path):
    path = tmp_path / "decisions.jsonl"
    _write_partial(path, _partial_records())
    ir.validate_partial_decisions(str(path))


@pytest.mark.parametrize("mutation", [
    lambda records: records.pop(),
    lambda records: records[0].__setitem__("seq", 1),
    lambda records: records[1].__setitem__("kind", "decision_node"),
    lambda records: records[0]["data"].__setitem__("dp_id", "e_warning"),
    lambda records: records[3]["data"].__setitem__("dp_id", "d_partner"),
])
def test_partial_ledger_refuses_terminal_or_shape_drift(tmp_path, mutation):
    records = _partial_records()
    mutation(records)
    path = tmp_path / "decisions.jsonl"
    _write_partial(path, records)
    with pytest.raises(ir.IncompleteResultError):
        ir.validate_partial_decisions(str(path))


def test_closure_authorization_schema_accepts_exact_fixture():
    handoff.validate_closure_authorization(_authorization())


@pytest.mark.parametrize("path,value", [
    (("profile_id",), "other"),
    (("derived_output_root",), "../escape"),
    (("closure_budget", "max_replay_runs"), 106),
    (("closure_budget", "max_retries_per_run"), 1),
    (("closure_budget", "max_wall_minutes"), 241),
    (("primary_evidence", "successful_runs"), 104),
    (("primary_evidence", "tombstoned_runs"), 1),
    (("primary_evidence", "manifest_sha256"), "0" * 64),
    (("primary_evidence", "partial", "execution_index"), 104),
    (("primary_evidence", "partial", "terminal_probe_present"), True),
    (("outcome", "claimable"), True),
    (("outcome", "statistics_computed"), True),
])
def test_closure_authorization_refuses_semantic_drift(path, value):
    candidate = _authorization()
    cursor = candidate
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value
    with pytest.raises(SchemaViolation):
        handoff.validate_closure_authorization(candidate)


@pytest.mark.parametrize("unknown_at", [
    (),
    ("source_request",),
    ("closure_tool",),
    ("closure_budget",),
    ("primary_evidence",),
    ("primary_evidence", "partial"),
])
def test_closure_authorization_is_closed_at_every_layer(unknown_at):
    candidate = _authorization()
    cursor = candidate
    for key in unknown_at:
        cursor = cursor[key]
    cursor["unknown"] = True
    with pytest.raises(SchemaViolation):
        handoff.validate_closure_authorization(candidate)


def test_proposal_payload_binds_domain_hash():
    proposal = _proposal()
    handoff.validate_proposal_payload(proposal["payload"])


def test_proposal_payload_refuses_hash_substitution():
    payload = copy.deepcopy(_proposal()["payload"])
    payload["closure_authorization_hash"] = "0" * 64
    with pytest.raises(SchemaViolation):
        handoff.validate_proposal_payload(payload)


def test_approval_exactly_copies_proposal():
    proposal, approval = _proposal(), _approval()
    handoff.validate_approval_payload(approval["payload"])
    handoff.validate_approval_binding([proposal], approval)


@pytest.mark.parametrize("field", [
    "proposal_event_id", "proposal_event_hash",
    "closure_authorization_hash", "approval_commit",
])
def test_approval_refuses_stale_or_substituted_binding(field):
    proposal, approval = _proposal(), _approval()
    approval["payload"][field] = (
        "0" * 40 if field == "approval_commit" else
        ("000999-deadbeef" if field == "proposal_event_id" else "0" * 64))
    with pytest.raises((CouncilError, SchemaViolation, ValueError)):
        handoff.validate_approval_binding([proposal], approval)


def _state_event(event_type, payload=None):
    return {
        "event_type": event_type,
        "request_id": ir.RESULT_REQUEST_ID,
        "target_commit": COMMIT,
        "payload": payload or {},
        "event_id": "000001-aaaaaaaa",
    }


def _recovery_authorization():
    return {
        "schema_version":
            "m8-incomplete-publication-recovery-authorization.v1",
        "result_request_id": ir.RESULT_REQUEST_ID,
        "original_repository": "/tmp/repo",
        "original_target_commit":
            "e4cf7f7a8f0dbad208865e1abf76082c9098faae",
        "original_proposal": {
            "event_id": handoff.ORIGINAL_PROPOSAL_EVENT_ID,
            "event_hash": handoff.ORIGINAL_PROPOSAL_EVENT_HASH,
        },
        "original_approval": {
            "event_id": handoff.ORIGINAL_APPROVAL_EVENT_ID,
            "event_hash": handoff.ORIGINAL_APPROVAL_EVENT_HASH,
        },
        "closure_authorization_hash":
            handoff.ORIGINAL_CLOSURE_AUTHORIZATION_HASH,
        "bundle_transaction_id": handoff.ORIGINAL_BUNDLE_TRANSACTION_ID,
        "derived_artifact_hashes":
            dict(handoff.ORIGINAL_DERIVED_HASHES),
        "recovery_tool": {
            "repository": "/tmp/tool",
            "target_commit": COMMIT,
            "integration_events": [
                {
                    "request_id": request_id,
                    "event_id": f"{index:06d}-{index:08x}",
                    "event_hash": f"{index:064x}",
                    "target_commit": COMMIT,
                }
                for index, request_id in enumerate(
                    handoff.RECOVERY_SOURCE_REQUEST_IDS, 1)
            ],
        },
        "recovery_budget": {
            "max_compute_minutes": 240,
            "max_wall_minutes": 240,
            "max_storage_mb": 1024,
            "max_replay_runs": 105,
            "max_retries_per_run": 0,
        },
    }


def _recovery_proposal_payload():
    authorization = _recovery_authorization()
    return {
        "schema_version":
            "m8-incomplete-publication-recovery-approval-required.v1",
        "recovery_authorization": authorization,
        "recovery_authorization_hash":
            handoff.recovery_authorization_hash(authorization),
    }


def _production_owner_chain():
    authorization = _authorization()
    proposal = {
        "event_id": handoff.ORIGINAL_PROPOSAL_EVENT_ID,
        "event_hash": handoff.ORIGINAL_PROPOSAL_EVENT_HASH,
        "event_type": "RESULT_HANDOFF_APPROVAL_REQUIRED",
        "request_id": ir.RESULT_REQUEST_ID,
        "repository": "/tmp/original",
        "target_commit":
            "e4cf7f7a8f0dbad208865e1abf76082c9098faae",
        "payload": {
            "schema_version": "result-handoff-approval-required.v1",
            "closure_authorization": authorization,
            "closure_authorization_hash":
                handoff.ORIGINAL_CLOSURE_AUTHORIZATION_HASH,
        },
    }
    approval = {
        "event_id": handoff.ORIGINAL_APPROVAL_EVENT_ID,
        "event_hash": handoff.ORIGINAL_APPROVAL_EVENT_HASH,
        "event_type": "RESULT_HANDOFF_APPROVED",
        "request_id": ir.RESULT_REQUEST_ID,
        "repository": "/tmp/original",
        "target_commit": proposal["target_commit"],
        "payload": {
            "schema_version": "result-handoff-approval.v1",
            "approved_by": "human",
            "approval_commit": proposal["target_commit"],
            "proposal_event_id": proposal["event_id"],
            "proposal_event_hash": proposal["event_hash"],
            "closure_authorization": authorization,
            "closure_authorization_hash":
                handoff.ORIGINAL_CLOSURE_AUTHORIZATION_HASH,
            "human_token": {
                "counter": 1, "preimage_hex": "f" * 64,
                "binds": "e" * 64},
        },
    }
    return [proposal, approval]


def test_state_machine_requires_distinct_owner_result_gate():
    requests = {}
    proposal = _state_event("RESULT_HANDOFF_APPROVAL_REQUIRED")
    state_machine.check(proposal, requests)
    state_machine.apply(proposal, requests)
    assert requests[ir.RESULT_REQUEST_ID]["state"] == \
        state_machine.AWAITING_RESULT_HANDOFF_OWNER
    approval = _state_event("RESULT_HANDOFF_APPROVED")
    state_machine.check(approval, requests)
    state_machine.apply(approval, requests)
    assert requests[ir.RESULT_REQUEST_ID]["state"] == \
        state_machine.RESULT_HANDOFF_OWNER_APPROVED


def test_state_machine_allows_only_exact_m8_recovery_reproposal():
    requests = {}
    for event_type, event_id in (
            ("RESULT_HANDOFF_APPROVAL_REQUIRED",
             handoff.ORIGINAL_PROPOSAL_EVENT_ID),
            ("RESULT_HANDOFF_APPROVED",
             handoff.ORIGINAL_APPROVAL_EVENT_ID)):
        event = _state_event(event_type)
        event["event_id"] = event_id
        event["target_commit"] = \
            "e4cf7f7a8f0dbad208865e1abf76082c9098faae"
        state_machine.check(event, requests)
        state_machine.apply(event, requests)
    generic = _state_event("RESULT_HANDOFF_APPROVAL_REQUIRED", {
        "schema_version": "result-handoff-approval-required.v1"})
    with pytest.raises(TransitionError):
        state_machine.check(generic, requests)
    recovery = _state_event(
        "RESULT_HANDOFF_APPROVAL_REQUIRED",
        _recovery_proposal_payload())
    recovery["target_commit"] = \
        "e4cf7f7a8f0dbad208865e1abf76082c9098faae"
    state_machine.check(recovery, requests)
    state_machine.apply(recovery, requests)
    assert requests[ir.RESULT_REQUEST_ID]["state"] == \
        state_machine.AWAITING_RESULT_HANDOFF_OWNER
    approval = _state_event(
        "RESULT_HANDOFF_APPROVED", {
            "schema_version":
                "m8-incomplete-publication-recovery-approval.v1"})
    approval["target_commit"] = recovery["target_commit"]
    state_machine.check(approval, requests)
    state_machine.apply(approval, requests)
    with pytest.raises(TransitionError):
        state_machine.check(recovery, requests)


def test_recovery_owner_payloads_are_closed_and_exact():
    proposal = _recovery_proposal_payload()
    handoff.validate_proposal_payload(proposal)
    approval = {
        "schema_version":
            "m8-incomplete-publication-recovery-approval.v1",
        "approved_by": "human",
        "approval_commit":
            "e4cf7f7a8f0dbad208865e1abf76082c9098faae",
        "proposal_event_id": "000900-1234abcd",
        "proposal_event_hash": "a" * 64,
        "recovery_authorization": proposal["recovery_authorization"],
        "recovery_authorization_hash":
            proposal["recovery_authorization_hash"],
        "human_token": {
            "counter": 1, "preimage_hex": "f" * 64,
            "binds": "e" * 64},
    }
    handoff.validate_approval_payload(approval)
    for changed in ("bundle_transaction_id", "closure_authorization_hash"):
        bad = copy.deepcopy(proposal)
        bad["recovery_authorization"][changed] = "0" * 64
        with pytest.raises(SchemaViolation):
            handoff.validate_proposal_payload(bad)


def test_recovery_approval_and_ready_bind_latest_owner_cycle():
    recovery_payload = _recovery_proposal_payload()
    proposal = {
        "event_id": "000900-1234abcd",
        "event_hash": "a" * 64,
        "event_type": "RESULT_HANDOFF_APPROVAL_REQUIRED",
        "request_id": ir.RESULT_REQUEST_ID,
        "repository": "/tmp/repo",
        "target_commit":
            "e4cf7f7a8f0dbad208865e1abf76082c9098faae",
        "payload": recovery_payload,
    }
    approval = {
        "event_id": "000901-1234abce",
        "event_hash": "b" * 64,
        "event_type": "RESULT_HANDOFF_APPROVED",
        "request_id": ir.RESULT_REQUEST_ID,
        "repository": "/tmp/repo",
        "target_commit": proposal["target_commit"],
        "payload": {
            "schema_version":
                "m8-incomplete-publication-recovery-approval.v1",
            "approved_by": "human",
            "approval_commit": proposal["target_commit"],
            "proposal_event_id": proposal["event_id"],
            "proposal_event_hash": proposal["event_hash"],
            "recovery_authorization":
                recovery_payload["recovery_authorization"],
            "recovery_authorization_hash":
                recovery_payload["recovery_authorization_hash"],
            "human_token": {
                "counter": 1, "preimage_hex": "f" * 64,
                "binds": "e" * 64},
        },
    }
    handoff.validate_approval_binding([proposal], approval)
    old = _approval()
    request = {
        "authorization_profile": {
            "profile_id": ir.PROFILE_ID,
            "closure_owner_approval_event_id": old["event_id"],
            "closure_owner_approval_event_hash": old["event_hash"],
        },
        "closure_authorization":
            old["payload"]["closure_authorization"],
        "closure_authorization_hash":
            old["payload"]["closure_authorization_hash"],
        "publication_recovery": {
            "recovery_owner_approval_event_id": approval["event_id"],
            "recovery_owner_approval_event_hash": approval["event_hash"],
            "recovery_authorization":
                recovery_payload["recovery_authorization"],
            "recovery_authorization_hash":
                recovery_payload["recovery_authorization_hash"],
        },
    }
    ready = {"payload": {"request": request},
             "request_id": ir.RESULT_REQUEST_ID}
    handoff.validate_ready_binding([old, approval], ready)
    request["publication_recovery"][
        "recovery_owner_approval_event_hash"] = "0" * 64
    with pytest.raises(CouncilError, match="recovery binding"):
        handoff.validate_ready_binding([old, approval], ready)


def test_recovery_authorization_refuses_wrong_tool_or_stale_integrations(
        monkeypatch):
    from tools.council import git_state
    chain = _production_owner_chain()
    monkeypatch.setattr(events, "read_chain", lambda _root: chain)
    monkeypatch.setattr(
        state_machine, "project",
        lambda _chain: {ir.RESULT_REQUEST_ID: {
            "state": state_machine.RESULT_HANDOFF_OWNER_APPROVED}})
    monkeypatch.setattr(
        git_state, "head_commit",
        lambda repo, _roots: (
            COMMIT if repo == "/tmp/tool" else
            "e4cf7f7a8f0dbad208865e1abf76082c9098faae"))
    monkeypatch.setattr(git_state, "is_clean", lambda *_args: True)
    monkeypatch.setattr(git_state, "is_ancestor", lambda *_args: True)
    monkeypatch.setattr(
        handoff, "target_has_only_exact_bundle", lambda *_args: True)
    integrations = _recovery_authorization()[
        "recovery_tool"]["integration_events"]
    monkeypatch.setattr(
        handoff, "_recovery_integrations",
        lambda _chain, commit: copy.deepcopy(integrations)
        if commit == COMMIT else pytest.fail("wrong commit reached"))
    cfg = SimpleNamespace(repo_roots=("/tmp/original", "/tmp/tool"))
    authorization = handoff.build_recovery_authorization(
        "/tmp/council", cfg, "/tmp/tool", COMMIT, 240, 240, 1024)
    assert authorization["recovery_tool"]["integration_events"] == integrations

    monkeypatch.setattr(
        git_state, "head_commit",
        lambda repo, _roots: (
            "d" * 40 if repo == "/tmp/tool" else
            "e4cf7f7a8f0dbad208865e1abf76082c9098faae"))
    with pytest.raises(CouncilError, match="clean exact descendant"):
        handoff.build_recovery_authorization(
            "/tmp/council", cfg, "/tmp/tool", COMMIT, 240, 240, 1024)
    monkeypatch.setattr(
        git_state, "head_commit",
        lambda repo, _roots: (
            COMMIT if repo == "/tmp/tool" else
            "e4cf7f7a8f0dbad208865e1abf76082c9098faae"))
    monkeypatch.setattr(
        handoff, "_recovery_integrations",
        lambda *_args: (_ for _ in ()).throw(
            CouncilError("stale recovery integrations")))
    with pytest.raises(CouncilError, match="stale recovery integrations"):
        handoff.build_recovery_authorization(
            "/tmp/council", cfg, "/tmp/tool", COMMIT, 240, 240, 1024)


def test_old_approval_alone_cannot_run_recovery_and_consumption_is_once(
        tmp_path, monkeypatch):
    root = make_root(tmp_path)
    cfg = SimpleNamespace(repo_roots=("/tmp/original", "/tmp/tool"))
    chain = _production_owner_chain()
    monkeypatch.setattr(events, "read_chain", lambda _root: chain)
    monkeypatch.setattr(
        state_machine, "project",
        lambda _chain: {ir.RESULT_REQUEST_ID: {
            "state": state_machine.RESULT_HANDOFF_OWNER_APPROVED}})
    with pytest.raises(CouncilError, match="recovery request chain prefix"):
        handoff.recover_approved(root, cfg, ir.RESULT_REQUEST_ID)
    monkeypatch.setattr(
        state_machine, "project",
        lambda _chain: {ir.RESULT_REQUEST_ID: {
            "state": state_machine.RESULT_AUDIT}})
    with pytest.raises(CouncilError, match="already consumed"):
        handoff.recover_approved(root, cfg, ir.RESULT_REQUEST_ID)


def test_m8_ready_refused_without_result_owner_approval():
    request = {"authorization_profile": {"profile_id": ir.PROFILE_ID}}
    event = _state_event(
        "RESULT_HANDOFF_READY", {"request": request})
    with pytest.raises(TransitionError):
        state_machine.check(event, {})


def test_historical_ready_still_starts_from_none():
    request = {"authorization_profile": {
        "profile_id": "society_live_persona_result_handoff.v1"}}
    event = _state_event("RESULT_HANDOFF_READY", {"request": request})
    state_machine.check(event, {})


def test_synthetic_owner_to_result_lifecycle_reaches_result_approved():
    requests = {}
    events_in_order = [
        _state_event("RESULT_HANDOFF_APPROVAL_REQUIRED"),
        _state_event("RESULT_HANDOFF_APPROVED"),
        _state_event("RESULT_HANDOFF_READY", {"request": {
            "authorization_profile": {"profile_id": ir.PROFILE_ID}}}),
        _state_event("RESULT_AUDIT_REQUESTED"),
        _state_event("RESULT_APPROVED"),
    ]
    for index, event in enumerate(events_in_order, 1):
        event["event_id"] = f"{index:06d}-{index:08x}"
        state_machine.check(event, requests)
        state_machine.apply(event, requests)
    assert requests[ir.RESULT_REQUEST_ID]["state"] == \
        state_machine.RESULT_APPROVED


def test_source_rewind_cannot_use_the_generic_fix_transition():
    def advance(sequence, request_id):
        requests = {}
        for index, event_type in enumerate(sequence, 1):
            event = _state_event(event_type)
            event["request_id"] = request_id
            event["event_id"] = f"{index:06d}-{index:08x}"
            event["sender"] = (
                "codex" if event_type.startswith("AUDIT_") else "claude")
            state_machine.check(event, requests)
            state_machine.apply(event, requests)
        return requests

    requested = ["BUILD_STARTED", "BUILD_READY", "AUDIT_REQUESTED"]
    unrelated = advance(requested, "unrelated-source-request")
    with pytest.raises(TransitionError):
        event = _state_event("FIX_STARTED")
        event["request_id"] = "unrelated-source-request"
        state_machine.check(event, unrelated)

    exact = advance(requested, handoff.SOURCE_SLICE_REQUEST_IDS[0])
    with pytest.raises(TransitionError):
        event = _state_event("FIX_STARTED")
        event["request_id"] = handoff.SOURCE_SLICE_REQUEST_IDS[0]
        state_machine.check(event, exact)


def test_source_rewind_fabricated_payload_is_refused_at_append_boundary(
        tmp_path):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    request_id = handoff.SOURCE_SLICE_REQUEST_IDS[0]
    append(root, cfg, "BUILD_STARTED", "claude", request_id, repo, head)
    append(root, cfg, "BUILD_READY", "claude", request_id, repo, head)
    publication = publish.publish_request(
        root, cfg, make_request(
            repo, head, request_id, task_kind="source"))
    request_path = storage.safe_request_path(root, "ready", request_id)
    with open(request_path, "rb") as fh:
        request_bytes = fh.read()
    request_sha256 = hashlib.sha256(request_bytes).hexdigest()
    published_request = json.loads(request_bytes)
    payload = {
        "originating_blocked_commit": head,
        "blockers_addressed": ["fabricated"],
        "controlling_event_id": publication["event_id"],
        "superseded_audit": {
            "transaction_id": "a" * 64,
            "prior_state": "requested",
            "audit_cycle": 1,
            "publication_event_id": publication["event_id"],
            "publication_event_hash": publication["event_hash"],
            "request_payload_hash": published_request["request_payload_hash"],
            "request_file_sha256": request_sha256,
            "request_archive": "requests/complete/fabricated.json",
            "verdict_event_id": None,
            "verdict_event_hash": None,
            "verdict_file_sha256": None,
            "verdict_archive": None,
        },
    }
    with pytest.raises(CouncilError, match="journal unreadable"):
        events.append_event(
            root, cfg, "FIX_STARTED", "claude", request_id, repo, head,
            payload)


def test_source_rewind_archives_and_reaudits_requested_and_go_cycles(
        tmp_path):
    for prior_state, request_id in (
            ("requested", handoff.SOURCE_SLICE_REQUEST_IDS[3]),
            ("go", handoff.SOURCE_SLICE_REQUEST_IDS[0])):
        case = tmp_path / prior_state
        root = make_root(case)
        repo, head = make_repo(case)
        cfg = make_cfg(repo, root)
        codex_cfg = make_cfg(repo, root, role="codex")

        # Produce one real same-commit blocked event to bind the rewind.
        control_id = handoff.SOURCE_SLICE_REQUEST_IDS[2]
        append(root, cfg, "BUILD_STARTED", "claude", control_id, repo, head)
        append(root, cfg, "BUILD_READY", "claude", control_id, repo, head)
        publish.publish_request(
            root, cfg, make_request(
                repo, head, control_id, task_kind="source"))
        codex_watch.claim(root, codex_cfg, control_id)
        blocked = codex_watch.submit_verdict(
            root, codex_cfg, make_verdict(
                head, control_id, verdict="BLOCKED",
                blockers=["synthetic controlling blocker"]))

        append(root, cfg, "BUILD_STARTED", "claude", request_id, repo, head)
        append(root, cfg, "BUILD_READY", "claude", request_id, repo, head)
        published = publish.publish_request(
            root, cfg, make_request(
                repo, head, request_id, task_kind="source"))
        ready = storage.safe_request_path(root, "ready", request_id)
        old_request_bytes = open(ready, "rb").read()
        if prior_state == "go":
            codex_watch.claim(root, codex_cfg, request_id)
            codex_watch.submit_verdict(
                root, codex_cfg, make_verdict(
                    head, request_id, verdict="GO"))
            old_location = storage.safe_request_path(
                root, "complete", request_id)
            old_verdict_bytes = open(
                storage.verdict_path(root, request_id), "rb").read()
        else:
            old_location = ready
            old_verdict_bytes = None

        rewound = handoff.supersede_source_audit(
            root, cfg, request_id, repo, head,
            "synthetic semantic descendant", blocked["event_id"])
        assert rewound["event_type"] == "FIX_STARTED"
        assert state_machine.project(events.read_chain(root))[
            request_id]["state"] == state_machine.FIXING
        assert not os.path.exists(old_location)
        archive_rel = rewound["payload"]["superseded_audit"][
            "request_archive"]
        request_archive = os.path.join(root, archive_rel)
        assert open(request_archive, "rb").read() == old_request_bytes
        verdict_rel = rewound["payload"]["superseded_audit"][
            "verdict_archive"]
        if old_verdict_bytes is None:
            assert verdict_rel is None
        else:
            assert open(os.path.join(root, verdict_rel), "rb").read() == \
                old_verdict_bytes

        with open(os.path.join(repo, "f.txt"), "a", encoding="utf-8") as fh:
            fh.write("descendant\n")
        subprocess.run(["git", "-C", repo, "add", "f.txt"], check=True)
        subprocess.run([
            "git", "-C", repo, "-c", "user.email=t@t",
            "-c", "user.name=t", "commit", "-qm", "descendant"], check=True)
        new_head = subprocess.run(
            ["git", "-C", repo, "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True).stdout.strip()
        append(root, cfg, "BUILD_READY", "claude", request_id, repo, new_head)
        republished = publish.publish_request(
            root, cfg, make_request(
                repo, new_head, request_id, task_kind="source"),
            reaudit=True)
        assert republished["event_type"] == "READY_FOR_REAUDIT"
        codex_watch.claim(root, codex_cfg, request_id)
        fresh = codex_watch.submit_verdict(
            root, codex_cfg, make_verdict(
                new_head, request_id, verdict="GO"))
        assert fresh["target_commit"] == new_head
        assert fresh["event_type"] == "AUDIT_GO"
        assert rewound["payload"]["superseded_audit"][
            "publication_event_id"] == published["event_id"]


def test_source_rewind_recovers_after_event_before_archive(
        tmp_path):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    codex_cfg = make_cfg(repo, root, role="codex")
    control_id = handoff.SOURCE_SLICE_REQUEST_IDS[2]
    request_id = handoff.SOURCE_SLICE_REQUEST_IDS[4]
    append(root, cfg, "BUILD_STARTED", "claude", control_id, repo, head)
    append(root, cfg, "BUILD_READY", "claude", control_id, repo, head)
    publish.publish_request(
        root, cfg, make_request(repo, head, control_id, task_kind="source"))
    codex_watch.claim(root, codex_cfg, control_id)
    blocked = codex_watch.submit_verdict(
        root, codex_cfg, make_verdict(
            head, control_id, verdict="BLOCKED", blockers=["control"]))
    append(root, cfg, "BUILD_STARTED", "claude", request_id, repo, head)
    append(root, cfg, "BUILD_READY", "claude", request_id, repo, head)
    publish.publish_request(
        root, cfg, make_request(repo, head, request_id, task_kind="source"))

    def interrupt(stage):
        if stage == "after_event":
            raise OSError("synthetic interruption")

    event = handoff.supersede_source_audit(
        root, cfg, request_id, repo, head, "repair",
        blocked["event_id"], _fault=interrupt)
    assert event["event_type"] == "FIX_STARTED"
    assert not os.path.exists(
        storage.safe_request_path(root, "ready", request_id))
    archive = os.path.join(
        root, event["payload"]["superseded_audit"]["request_archive"])
    assert os.path.isfile(archive)
    transaction_id = event["payload"]["superseded_audit"]["transaction_id"]
    journal = handoff._source_rewind_paths(
        root, request_id, 1,
        event["payload"]["superseded_audit"]["request_file_sha256"],
        None, transaction_id)["journal"]
    assert not os.path.exists(journal)


@pytest.mark.parametrize("stage", [
    "after_journal",
    "after_lock",
    "after_event",
    "after_request_archive",
    "after_verdict_archive",
])
def test_source_rewind_real_process_exit_recovers_exactly_once(
        tmp_path, stage):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    codex_cfg = make_cfg(repo, root, role="codex")
    control_id = handoff.SOURCE_SLICE_REQUEST_IDS[2]
    request_id = handoff.SOURCE_SLICE_REQUEST_IDS[4]

    append(root, cfg, "BUILD_STARTED", "claude", control_id, repo, head)
    append(root, cfg, "BUILD_READY", "claude", control_id, repo, head)
    publish.publish_request(
        root, cfg, make_request(
            repo, head, control_id, task_kind="source"))
    codex_watch.claim(root, codex_cfg, control_id)
    blocked = codex_watch.submit_verdict(
        root, codex_cfg, make_verdict(
            head, control_id, verdict="BLOCKED", blockers=["control"]))

    append(root, cfg, "BUILD_STARTED", "claude", request_id, repo, head)
    append(root, cfg, "BUILD_READY", "claude", request_id, repo, head)
    publish.publish_request(
        root, cfg, make_request(
            repo, head, request_id, task_kind="source"))
    codex_watch.claim(root, codex_cfg, request_id)
    codex_watch.submit_verdict(
        root, codex_cfg, make_verdict(
            head, request_id, verdict="GO"))

    def worker():
        def stop(at):
            if at == stage:
                os._exit(73)

        handoff.supersede_source_audit(
            root, cfg, request_id, repo, head, "repair",
            blocked["event_id"], _fault=stop, _lease_seconds=0.01)

    process = multiprocessing.Process(target=worker)
    process.start()
    process.join(10)
    assert process.exitcode == 73

    event = None
    for _attempt in range(100):
        try:
            event = handoff.supersede_source_audit(
                root, cfg, request_id, repo, head, "repair",
                blocked["event_id"], _lease_seconds=0.01)
            break
        except CouncilError as exc:
            if "not yet available" not in str(exc):
                raise
            time.sleep(0.01)
    assert event is not None
    assert event["event_type"] == "FIX_STARTED"
    fixes = [
        item for item in events.read_chain(root)
        if item["request_id"] == request_id and
        item["event_type"] == "FIX_STARTED"]
    assert fixes == [event]
    assert state_machine.project(events.read_chain(root))[
        request_id]["state"] == state_machine.FIXING
    assert not handoff._source_rewind_journals(root, request_id)
    assert not os.path.lexists(storage.lock_path(root, request_id))
    nested = event["payload"]["superseded_audit"]
    assert os.path.isfile(os.path.join(root, nested["request_archive"]))
    assert os.path.isfile(os.path.join(root, nested["verdict_archive"]))


def test_source_rewind_concurrent_loser_cannot_poison_recovery(tmp_path):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    codex_cfg = make_cfg(repo, root, role="codex")
    control_id = handoff.SOURCE_SLICE_REQUEST_IDS[2]
    request_id = handoff.SOURCE_SLICE_REQUEST_IDS[4]

    append(root, cfg, "BUILD_STARTED", "claude", control_id, repo, head)
    append(root, cfg, "BUILD_READY", "claude", control_id, repo, head)
    publish.publish_request(
        root, cfg, make_request(
            repo, head, control_id, task_kind="source"))
    codex_watch.claim(root, codex_cfg, control_id)
    blocked = codex_watch.submit_verdict(
        root, codex_cfg, make_verdict(
            head, control_id, verdict="BLOCKED", blockers=["control"]))
    append(root, cfg, "BUILD_STARTED", "claude", request_id, repo, head)
    append(root, cfg, "BUILD_READY", "claude", request_id, repo, head)
    publish.publish_request(
        root, cfg, make_request(
            repo, head, request_id, task_kind="source"))
    codex_watch.claim(root, codex_cfg, request_id)
    codex_watch.submit_verdict(
        root, codex_cfg, make_verdict(
            head, request_id, verdict="GO"))

    barrier = multiprocessing.Barrier(2)
    outcomes = multiprocessing.Queue()

    def worker():
        def synchronize(at):
            if at == "after_journal":
                barrier.wait(5)

        try:
            event = handoff.supersede_source_audit(
                root, cfg, request_id, repo, head, "repair",
                blocked["event_id"], _fault=synchronize)
            outcomes.put(("event", event["event_id"]))
        except CouncilError as exc:
            outcomes.put(("refused", type(exc).__name__))

    processes = [multiprocessing.Process(target=worker) for _ in range(2)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(10)
        assert process.exitcode == 0
    results = sorted(outcomes.get(timeout=1) for _ in processes)
    assert [kind for kind, _detail in results] == ["event", "refused"]
    chain = events.read_chain(root)
    fixes = [
        item for item in chain
        if item["request_id"] == request_id and
        item["event_type"] == "FIX_STARTED"]
    assert len(fixes) == 1
    assert state_machine.project(chain)[request_id]["state"] == \
        state_machine.FIXING
    assert not handoff._source_rewind_journals(root, request_id)
    assert not os.path.lexists(storage.lock_path(root, request_id))
    nested = fixes[0]["payload"]["superseded_audit"]
    assert os.path.isfile(os.path.join(root, nested["request_archive"]))
    assert os.path.isfile(os.path.join(root, nested["verdict_archive"]))


def _source_reaudit_case(case, request_id):
    root = make_root(case)
    repo, head = make_repo(case)
    cfg = make_cfg(repo, root)
    codex_cfg = make_cfg(repo, root, role="codex")
    control_id = next(
        item for item in handoff.SOURCE_SLICE_REQUEST_IDS
        if item != request_id)
    append(root, cfg, "BUILD_STARTED", "claude", control_id, repo, head)
    append(root, cfg, "BUILD_READY", "claude", control_id, repo, head)
    publish.publish_request(
        root, cfg, make_request(
            repo, head, control_id, task_kind="source"))
    codex_watch.claim(root, codex_cfg, control_id)
    blocked = codex_watch.submit_verdict(
        root, codex_cfg, make_verdict(
            head, control_id, verdict="BLOCKED", blockers=["control"]))
    append(root, cfg, "BUILD_STARTED", "claude", request_id, repo, head)
    append(root, cfg, "BUILD_READY", "claude", request_id, repo, head)
    publish.publish_request(
        root, cfg, make_request(
            repo, head, request_id, task_kind="source"))
    codex_watch.claim(root, codex_cfg, request_id)
    codex_watch.submit_verdict(
        root, codex_cfg, make_verdict(
            head, request_id, verdict="GO"))
    handoff.supersede_source_audit(
        root, cfg, request_id, repo, head, "repair",
        blocked["event_id"])
    append(root, cfg, "BUILD_READY", "claude", request_id, repo, head)
    return root, repo, head, cfg, make_request(
        repo, head, request_id, task_kind="source")


def test_wrong_cycle_publication_rolls_back_for_every_source_id(
        tmp_path, monkeypatch):
    for index, request_id in enumerate(handoff.SOURCE_SLICE_REQUEST_IDS):
        root, repo, head, cfg, request = _source_reaudit_case(
            tmp_path / str(index), request_id)
        body = dict(request)
        body["request_payload_hash"] = compute_request_payload_hash(body)
        ready = storage.safe_request_path(root, "ready", request_id)
        storage.atomic_write_json(ready, body)
        before_bytes = open(ready, "rb").read()
        wrong_payload = {
            "request_payload_hash": body["request_payload_hash"],
            "request_file": f"requests/ready/{request_id}.json",
            "scope": body["scope"],
            "expected_test_command": body["expected_test_command"],
            "expected_test_count": body["expected_test_count"],
            "blockers_addressed": body["blockers_addressed"],
        }
        with pytest.raises(TransitionError):
            events.append_event(
                root, cfg, "AUDIT_REQUESTED", "claude", request_id,
                repo, head, wrong_payload)
        assert open(ready, "rb").read() == before_bytes
        os.unlink(ready)

        before = events.read_chain(root)
        with pytest.raises(TransitionError):
            publish.publish_request(root, cfg, request)
        assert not os.path.lexists(ready)
        assert not os.path.lexists(
            storage.safe_request_path(root, "draft", request_id) + ".tmp")
        after = events.read_chain(root)
        assert sum(
            item["request_id"] == request_id and
            item["event_type"] == "AUDIT_REQUESTED"
            for item in after) == 1
        assert len(after) == len(before)

        republished = publish.publish_request(
            root, cfg, request, reaudit=True)
        assert republished["event_type"] == "READY_FOR_REAUDIT"
        final = events.read_chain(root)
        assert sum(
            item["request_id"] == request_id and
            item["event_type"] == "READY_FOR_REAUDIT"
            for item in final) == 1

    request_id = handoff.SOURCE_SLICE_REQUEST_IDS[0]
    root, _repo, _head, cfg, request = _source_reaudit_case(
        tmp_path / "unknown-chain", request_id)
    original_read = publish.events.read_chain
    read_count = 0

    def uncertain_read(*args, **kwargs):
        nonlocal read_count
        read_count += 1
        if read_count > 1:
            raise CouncilError("synthetic chain uncertainty")
        return original_read(*args, **kwargs)

    def refused_append(*_args, **_kwargs):
        raise TransitionError("synthetic append refusal")

    with monkeypatch.context() as patch:
        patch.setattr(publish.events, "read_chain", uncertain_read)
        patch.setattr(publish.events, "append_event", refused_append)
        with pytest.raises(TransitionError):
            publish.publish_request(root, cfg, request)
    ready = storage.safe_request_path(root, "ready", request_id)
    assert os.path.isfile(ready)
    os.unlink(ready)


def test_two_publishers_cannot_remove_or_strand_request(tmp_path):
    request_id = handoff.SOURCE_SLICE_REQUEST_IDS[1]
    root, _repo, _head, cfg, request = _source_reaudit_case(
        tmp_path, request_id)
    ready = storage.safe_request_path(root, "ready", request_id)
    reached_append = multiprocessing.Event()
    release_append = multiprocessing.Event()
    wrong_result = multiprocessing.Queue()
    correct_result = multiprocessing.Queue()

    def wrong_worker():
        original = publish.events.append_event

        def paused_append(*args, **kwargs):
            reached_append.set()
            if not release_append.wait(5):
                raise OSError("synthetic publication pause expired")
            return original(*args, **kwargs)

        publish.events.append_event = paused_append
        try:
            publish.publish_request(root, cfg, request)
            wrong_result.put(("event", None))
        except CouncilError as exc:
            wrong_result.put(("refused", type(exc).__name__))

    def correct_worker():
        try:
            event = publish.publish_request(
                root, cfg, request, reaudit=True)
            correct_result.put(("event", event["event_id"]))
        except CouncilError as exc:
            correct_result.put(("refused", type(exc).__name__))

    wrong = multiprocessing.Process(target=wrong_worker)
    wrong.start()
    assert reached_append.wait(5)
    holder = locking.read_lock(root, request_id)
    assert holder["kind"] == "request_publication"
    assert os.path.isfile(ready)

    correct = multiprocessing.Process(target=correct_worker)
    correct.start()
    correct.join(5)
    release_append.set()
    wrong.join(10)
    assert correct.exitcode == 0
    assert wrong.exitcode == 0
    assert correct_result.get(timeout=1) == ("refused", "LockHeld")
    assert wrong_result.get(timeout=1) == ("refused", "TransitionError")
    assert not os.path.lexists(ready)
    assert not os.path.lexists(storage.lock_path(root, request_id))
    chain = events.read_chain(root)
    assert sum(
        item["request_id"] == request_id and
        item["event_type"] == "AUDIT_REQUESTED"
        for item in chain) == 1

    event = publish.publish_request(
        root, cfg, request, reaudit=True)
    assert event["event_type"] == "READY_FOR_REAUDIT"
    assert os.path.isfile(ready)


def test_resume_actions_keep_result_owner_gate_distinct():
    from tools.autonomy.resume import NEXT_ACTION
    assert NEXT_ACTION[state_machine.AWAITING_RESULT_HANDOFF_OWNER][0] == \
        "human"
    assert "approve-result-handoff" in NEXT_ACTION[
        state_machine.AWAITING_RESULT_HANDOFF_OWNER][1]
    assert NEXT_ACTION[state_machine.RESULT_HANDOFF_OWNER_APPROVED][0] == \
        "claude"
    assert "--request-id <id>" in NEXT_ACTION[
        state_machine.RESULT_HANDOFF_OWNER_APPROVED][1]


def test_source_close_payload_binds_exact_approved_result():
    _objects, _data, request = _objects_and_request()
    ready = {
        "event_id": "000201-aaaaaaaa",
        "event_hash": "a" * 64,
        "event_type": "RESULT_HANDOFF_READY",
        "request_id": ir.RESULT_REQUEST_ID,
        "payload": {"request": request},
    }
    approved = {
        "event_id": "000202-bbbbbbbb",
        "event_hash": "b" * 64,
        "event_type": "RESULT_APPROVED",
        "request_id": ir.RESULT_REQUEST_ID,
    }
    payload = handoff.source_close_payload(
        [ready, approved], ir.RESULT_REQUEST_ID, approved["event_id"])
    assert payload["result_approved_event_hash"] == approved["event_hash"]
    assert payload["closure_authorization_hash"] == \
        request["closure_authorization_hash"]
    close_event = {
        "request_id": ir.SOURCE_REQUEST_ID,
        "sender": "human",
        "payload": {
            **payload,
            "human_token": {
                "counter": 1, "preimage_hex": "f" * 64,
                "binds": "e" * 64},
        },
    }
    handoff.validate_source_close_binding(
        [ready, approved], close_event)
    close_event["payload"]["result_approved_event_hash"] = "9" * 64
    with pytest.raises(CouncilError):
        handoff.validate_source_close_binding(
            [ready, approved], close_event)


def test_publish_approved_synthetic_end_to_end_reaches_ready_and_audit(
        tmp_path, monkeypatch):
    repo, _head = make_repo(tmp_path)
    root = make_root(tmp_path)
    cfg = make_cfg(repo, root)
    inventory_content = {
        "schema_version": "m8-budget-exhaustion-primary-inventory.v1",
        "evidence_root": ir.EVIDENCE_ROOT,
        "file_count": 423,
        "files": {"manifest.jsonl": ir.MANIFEST_SHA256},
    }
    monkeypatch.setattr(
        ir, "PRIMARY_INVENTORY_CONTENT_HASH",
        ir.domain_hash(ir.PRIMARY_INVENTORY_DOMAIN, inventory_content))
    synthetic_census = ir.build_coordinate_census(
        _spec(), _success_rows(), _partial())
    monkeypatch.setattr(
        ir, "COORDINATE_CENSUS_CONTENT_HASH",
        synthetic_census["content_hash"])
    proposal, approval = _proposal(), _approval()
    proposal["repository"] = repo
    approval["repository"] = repo
    source_pause = {
        "event_id": "000100-cccccccc",
        "event_hash": "c" * 64,
        "event_type": "AUTONOMY_PAUSED",
        "request_id": ir.SOURCE_REQUEST_ID,
        "repository": repo,
        "target_commit": handoff.SOURCE_IMPLEMENTATION_COMMIT,
        "payload": {"reason": handoff.PAUSE_REASON},
    }
    chain = [source_pause, proposal, approval]
    synthetic_transaction = handoff.transaction_id(
        ir.RESULT_REQUEST_ID, proposal, approval,
        proposal["payload"]["closure_authorization_hash"], COMMIT)
    expected_objects = handoff._artifact_objects(
        _snapshot(), _replay_core(), _authorization(), proposal, approval,
        synthetic_transaction)
    expected_hashes = handoff._file_hashes(
        handoff._artifact_bytes(expected_objects))
    monkeypatch.setattr(
        handoff, "ORIGINAL_DERIVED_HASHES", expected_hashes)

    monkeypatch.setattr(events, "read_chain",
                        lambda _root, verify=True: list(chain))

    def append(_root, _cfg, event_type, sender, request_id, repository,
               target_commit, payload, **_kwargs):
        event = events.build_event(
            event_type, sender, request_id, repository, target_commit,
            payload, len(chain) + 1,
            chain[-1]["event_hash"] if chain else "0" * 64)
        state_machine.check(event, state_machine.project(chain))
        chain.append(event)
        return event

    monkeypatch.setattr(events, "append_event", append)
    monkeypatch.setattr(
        handoff, "_source_authority",
        lambda _chain: (proposal, {"event_id": "go"}, {
            "event_id": handoff.SOURCE_OWNER_APPROVAL_EVENT_ID}, source_pause))
    monkeypatch.setattr(
        handoff, "_closure_integrations",
        lambda _chain, _commit:
            _authorization()["closure_tool"]["integration_events"])
    from tools.council import git_state
    monkeypatch.setattr(git_state, "head_commit",
                        lambda *_args, **_kwargs: COMMIT)
    monkeypatch.setattr(git_state, "commit_exists",
                        lambda *_args, **_kwargs: True)

    sweep = handoff.importlib.import_module("coliseum.textlab.sweep")
    from tools.council import locking
    operation_order = []
    original_acquire = locking.acquire
    original_preflight = handoff._preflight_request_namespace

    def tracked_acquire(_root, name, *args, **kwargs):
        lease = original_acquire(_root, name, *args, **kwargs)
        if name == "_result_handoff":
            operation_order.append("journal_lease")
        return lease

    def tracked_preflight(_root, current_chain):
        operation_order.append("namespace")
        return original_preflight(_root, current_chain)

    monkeypatch.setattr(locking, "acquire", tracked_acquire)
    monkeypatch.setattr(
        handoff, "_preflight_request_namespace", tracked_preflight)

    @contextmanager
    def fake_manifest_lock(path):
        yield path

    monkeypatch.setattr(sweep, "_manifest_advisory_lock", fake_manifest_lock)

    resolved_plan = _spec()

    def tracked_replay(*_args, **_kwargs):
        assert _args[3] is resolved_plan
        operation_order.append("replay")
        return _replay_core()

    def tracked_resolver(*_args, **_kwargs):
        operation_order.append("registry")
        return resolved_plan

    def tracked_primary(*_args, **_kwargs):
        assert _args[3] is resolved_plan
        return _snapshot()

    monkeypatch.setattr(
        sweep, "build_pack_replay_core_locked", tracked_replay)
    monkeypatch.setattr(
        handoff, "_resolved_closure_plan", tracked_resolver)
    monkeypatch.setattr(
        handoff, "_derive_primary_locked", tracked_primary)
    budget_instances = []
    original_budget = handoff._Budget

    class TrackingBudget(original_budget):
        def __init__(self, limits):
            super().__init__(limits)
            budget_instances.append(self)

    monkeypatch.setattr(handoff, "_Budget", TrackingBudget)

    audit = handoff.publish_approved(
        root, cfg, ir.RESULT_REQUEST_ID)
    assert audit["event_type"] == "RESULT_AUDIT_REQUESTED"
    assert [event["event_type"] for event in chain[-2:]] == [
        "RESULT_HANDOFF_READY", "RESULT_AUDIT_REQUESTED"]
    assert state_machine.project(chain)[ir.SOURCE_REQUEST_ID]["state"] == \
        state_machine.AUTONOMY_PAUSED
    derived = os.path.join(repo, ir.DERIVED_OUTPUT_ROOT)
    assert sorted(os.listdir(derived)) == sorted(ir.DERIVED_FILENAMES)
    assert git_state.is_clean(repo, cfg.repo_roots) is False
    assert handoff.target_has_only_exact_bundle(
        repo, cfg.repo_roots, expected_hashes)
    claimed = storage.safe_request_path(
        root, "claimed", ir.RESULT_REQUEST_ID)
    assert os.path.isfile(claimed)
    assert len(budget_instances) == 1, \
        "construction and final deep replay must share one budget clock"
    lease_index = operation_order.index("journal_lease")
    assert operation_order[lease_index + 1] == "namespace"
    assert lease_index < operation_order.index("namespace", lease_index) < \
        operation_order.index("registry") < operation_order.index("replay")


def test_real_git_bundle_first_write_and_exact_adoption_preserve_inodes(
        tmp_path, monkeypatch):
    repo, _head = make_repo(tmp_path)
    _objects, data, _request = _objects_and_request(repo)
    hashes = handoff._file_hashes(data)
    monkeypatch.setattr(handoff, "ORIGINAL_DERIVED_HASHES", hashes)
    final = os.path.join(repo, ir.DERIVED_OUTPUT_ROOT)
    budget = handoff._Budget({
        "max_compute_minutes": 1, "max_wall_minutes": 1,
        "max_storage_mb": 16, "max_replay_runs": 105,
        "max_retries_per_run": 0})
    handoff._write_bundle_transaction(final, "d" * 64, data, budget)
    before = {
        name: (os.lstat(os.path.join(final, name)).st_ino,
               ir.file_sha256(os.path.join(final, name)))
        for name in ir.DERIVED_FILENAMES
    }
    handoff._write_bundle_transaction(final, "d" * 64, data, budget)
    after = {
        name: (os.lstat(os.path.join(final, name)).st_ino,
               ir.file_sha256(os.path.join(final, name)))
        for name in ir.DERIVED_FILENAMES
    }
    assert after == before
    assert handoff.target_has_only_exact_bundle(
        repo, (repo,), hashes)


@pytest.mark.parametrize("mutation", [
    "tracked", "index", "unrelated", "extra", "missing", "changed", "symlink",
    "hardlink",
])
def test_real_git_exact_bundle_predicate_refuses_every_other_tree(
        tmp_path, monkeypatch, mutation):
    repo, _head = make_repo(tmp_path)
    _objects, data, _request = _objects_and_request(repo)
    hashes = handoff._file_hashes(data)
    monkeypatch.setattr(handoff, "ORIGINAL_DERIVED_HASHES", hashes)
    final = os.path.join(repo, ir.DERIVED_OUTPUT_ROOT)
    budget = handoff._Budget({
        "max_compute_minutes": 1, "max_wall_minutes": 1,
        "max_storage_mb": 16, "max_replay_runs": 105,
        "max_retries_per_run": 0})
    handoff._write_bundle_transaction(final, "d" * 64, data, budget)
    member = os.path.join(final, ir.DERIVED_FILENAMES[0])
    if mutation == "tracked":
        with open(os.path.join(repo, "f.txt"), "a", encoding="utf-8") as fh:
            fh.write("changed\n")
    elif mutation == "index":
        with open(os.path.join(repo, "f.txt"), "a", encoding="utf-8") as fh:
            fh.write("staged\n")
        subprocess.run(
            ["git", "-C", repo, "add", "f.txt"], check=True)
    elif mutation == "unrelated":
        with open(os.path.join(repo, "unrelated.txt"), "w",
                  encoding="utf-8") as fh:
            fh.write("extra\n")
    elif mutation == "extra":
        with open(os.path.join(final, "extra.json"), "w",
                  encoding="utf-8") as fh:
            fh.write("{}\n")
    elif mutation == "missing":
        os.unlink(member)
    elif mutation == "changed":
        with open(member, "ab") as fh:
            fh.write(b" ")
    elif mutation == "symlink":
        os.unlink(member)
        os.symlink("replay_attestation.json", member)
    elif mutation == "hardlink":
        twin = os.path.join(repo, "bundle-twin")
        os.link(member, twin)
    assert not handoff.target_has_only_exact_bundle(
        repo, (repo,), hashes)


def test_recover_approved_end_to_end_adopts_once_and_rolls_forward(
        tmp_path, monkeypatch):
    from tools.council import git_state, result_handoff
    target_repo, _target_head = make_repo(tmp_path, "target")
    tool_repo, tool_head = make_repo(tmp_path, "tool")
    root = make_root(tmp_path)
    cfg = SimpleNamespace(
        council_root=root, repo_roots=(target_repo, tool_repo),
        role="claude")
    inventory_content = {
        "schema_version": "m8-budget-exhaustion-primary-inventory.v1",
        "evidence_root": ir.EVIDENCE_ROOT,
        "file_count": 423,
        "files": {"manifest.jsonl": ir.MANIFEST_SHA256},
    }
    monkeypatch.setattr(
        ir, "PRIMARY_INVENTORY_CONTENT_HASH",
        ir.domain_hash(ir.PRIMARY_INVENTORY_DOMAIN, inventory_content))
    synthetic_census = ir.build_coordinate_census(
        _spec(), _success_rows(), _partial())
    monkeypatch.setattr(
        ir, "COORDINATE_CENSUS_CONTENT_HASH",
        synthetic_census["content_hash"])
    original_commit = \
        "e4cf7f7a8f0dbad208865e1abf76082c9098faae"
    authorization = _authorization()
    authorization["closure_tool"]["target_commit"] = original_commit
    for integration in authorization["closure_tool"]["integration_events"]:
        integration["target_commit"] = original_commit
    closure_hash = handoff.closure_authorization_hash(authorization)
    monkeypatch.setattr(
        handoff, "ORIGINAL_CLOSURE_AUTHORIZATION_HASH", closure_hash)
    original_proposal = {
        "event_id": handoff.ORIGINAL_PROPOSAL_EVENT_ID,
        "event_hash": handoff.ORIGINAL_PROPOSAL_EVENT_HASH,
        "event_type": "RESULT_HANDOFF_APPROVAL_REQUIRED",
        "request_id": ir.RESULT_REQUEST_ID,
        "repository": target_repo,
        "target_commit": original_commit,
        "payload": {
            "schema_version": "result-handoff-approval-required.v1",
            "closure_authorization": authorization,
            "closure_authorization_hash": closure_hash,
        },
    }
    original_approval = {
        "event_id": handoff.ORIGINAL_APPROVAL_EVENT_ID,
        "event_hash": handoff.ORIGINAL_APPROVAL_EVENT_HASH,
        "event_type": "RESULT_HANDOFF_APPROVED",
        "request_id": ir.RESULT_REQUEST_ID,
        "repository": target_repo,
        "target_commit": original_commit,
        "payload": {
            "schema_version": "result-handoff-approval.v1",
            "approved_by": "human",
            "approval_commit": original_commit,
            "proposal_event_id": original_proposal["event_id"],
            "proposal_event_hash": original_proposal["event_hash"],
            "closure_authorization": authorization,
            "closure_authorization_hash": closure_hash,
            "human_token": {
                "counter": 1, "preimage_hex": "f" * 64,
                "binds": "e" * 64},
        },
    }
    transaction = handoff.transaction_id(
        ir.RESULT_REQUEST_ID, original_proposal, original_approval,
        closure_hash, original_commit)
    monkeypatch.setattr(
        handoff, "ORIGINAL_BUNDLE_TRANSACTION_ID", transaction)
    objects = handoff._artifact_objects(
        _snapshot(), _replay_core(), authorization, original_proposal,
        original_approval, transaction)
    data = handoff._artifact_bytes(objects)
    hashes = handoff._file_hashes(data)
    monkeypatch.setattr(handoff, "ORIGINAL_DERIVED_HASHES", hashes)
    final = os.path.join(target_repo, ir.DERIVED_OUTPUT_ROOT)
    handoff._write_bundle_transaction(
        final, transaction, data, handoff._Budget({
            "max_compute_minutes": 1, "max_wall_minutes": 1,
            "max_storage_mb": 16, "max_replay_runs": 105,
            "max_retries_per_run": 0}))
    before = {
        name: (os.lstat(os.path.join(final, name)).st_ino,
               ir.file_sha256(os.path.join(final, name)))
        for name in ir.DERIVED_FILENAMES
    }
    integrations = [
        {
            "request_id": request_id,
            "event_id": f"{index + 910:06d}-{index + 910:08x}",
            "event_hash": f"{index + 910:064x}",
            "target_commit": tool_head,
        }
        for index, request_id in enumerate(
            handoff.RECOVERY_SOURCE_REQUEST_IDS)
    ]
    recovery_authorization = {
        "schema_version":
            "m8-incomplete-publication-recovery-authorization.v1",
        "result_request_id": ir.RESULT_REQUEST_ID,
        "original_repository": target_repo,
        "original_target_commit": original_commit,
        "original_proposal": {
            "event_id": original_proposal["event_id"],
            "event_hash": original_proposal["event_hash"],
        },
        "original_approval": {
            "event_id": original_approval["event_id"],
            "event_hash": original_approval["event_hash"],
        },
        "closure_authorization_hash": closure_hash,
        "bundle_transaction_id": transaction,
        "derived_artifact_hashes": hashes,
        "recovery_tool": {
            "repository": tool_repo,
            "target_commit": tool_head,
            "integration_events": integrations,
        },
        # Deliberately differs from the historical 240/240/1024 budget.
        "recovery_budget": {
            "max_compute_minutes": 7, "max_wall_minutes": 8,
            "max_storage_mb": 9, "max_replay_runs": 105,
            "max_retries_per_run": 0,
        },
    }
    recovery_hash = handoff.recovery_authorization_hash(
        recovery_authorization)
    recovery_proposal = {
        "event_id": "000920-00000398",
        "event_hash": "c" * 64,
        "event_type": "RESULT_HANDOFF_APPROVAL_REQUIRED",
        "request_id": ir.RESULT_REQUEST_ID,
        "repository": target_repo,
        "target_commit": original_commit,
        "payload": {
            "schema_version":
                "m8-incomplete-publication-recovery-approval-required.v1",
            "recovery_authorization": recovery_authorization,
            "recovery_authorization_hash": recovery_hash,
        },
    }
    recovery_approval = {
        "event_id": "000921-00000399",
        "event_hash": "d" * 64,
        "event_type": "RESULT_HANDOFF_APPROVED",
        "request_id": ir.RESULT_REQUEST_ID,
        "repository": target_repo,
        "target_commit": original_commit,
        "payload": {
            "schema_version":
                "m8-incomplete-publication-recovery-approval.v1",
            "approved_by": "human",
            "approval_commit": original_commit,
            "proposal_event_id": recovery_proposal["event_id"],
            "proposal_event_hash": recovery_proposal["event_hash"],
            "recovery_authorization": recovery_authorization,
            "recovery_authorization_hash": recovery_hash,
            "human_token": {
                "counter": 2, "preimage_hex": "a" * 64,
                "binds": "b" * 64},
        },
    }
    chain = [
        original_proposal, original_approval,
        recovery_proposal, recovery_approval]
    assert state_machine.project(chain)[ir.RESULT_REQUEST_ID]["state"] == \
        state_machine.RESULT_HANDOFF_OWNER_APPROVED
    monkeypatch.setattr(events, "read_chain",
                        lambda _root, verify=True: list(chain))

    def append_event(_root, _cfg, event_type, sender, request_id,
                     repository, target_commit, payload, **_kwargs):
        event = events.build_event(
            event_type, sender, request_id, repository, target_commit,
            payload, len(chain) + 1,
            chain[-1]["event_hash"] if chain else "0" * 64)
        state_machine.check(event, state_machine.project(chain))
        chain.append(event)
        return event

    monkeypatch.setattr(events, "append_event", append_event)
    monkeypatch.setattr(
        handoff, "_runtime_tool_repository", lambda: tool_repo)
    monkeypatch.setattr(
        handoff, "_recovery_integrations",
        lambda _chain, commit: copy.deepcopy(integrations)
        if commit == tool_head else pytest.fail("wrong tool commit"))
    real_head = git_state.head_commit
    monkeypatch.setattr(
        git_state, "head_commit",
        lambda repo, roots: (
            original_commit if repo == target_repo
            else real_head(repo, roots)))
    monkeypatch.setattr(
        git_state, "commit_exists", lambda *_args, **_kwargs: True)
    sweep = handoff.importlib.import_module("coliseum.textlab.sweep")

    @contextmanager
    def fake_manifest_lock(path):
        yield path

    replay_calls = []
    monkeypatch.setattr(
        sweep, "_manifest_advisory_lock", fake_manifest_lock)
    monkeypatch.setattr(
        handoff, "_resolved_closure_plan", lambda _repo: _spec())
    monkeypatch.setattr(
        handoff, "_derive_primary_locked",
        lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(
        sweep, "build_pack_replay_core_locked",
        lambda *_args, **_kwargs: (
            replay_calls.append("replay") or _replay_core()))
    real_verify = handoff.verify_bundle_request
    deep_calls = []

    def bounded_verify(repo, request, *, chain=None, deep=True, budget=None):
        assert deep is True
        assert budget.limits == recovery_authorization["recovery_budget"]
        deep_calls.append(request["request_payload_hash"])
        return real_verify(
            repo, request, chain=chain, deep=True, budget=budget)

    monkeypatch.setattr(handoff, "verify_bundle_request", bounded_verify)
    real_write = storage.atomic_write_json
    failed = {"done": False}

    def fail_after_ready(path, value):
        if "/requests/claimed/" in path and not failed["done"]:
            failed["done"] = True
            raise OSError("synthetic interruption after ready")
        return real_write(path, value)

    monkeypatch.setattr(storage, "atomic_write_json", fail_after_ready)
    with pytest.raises(OSError, match="interruption after ready"):
        handoff.recover_approved(root, cfg, ir.RESULT_REQUEST_ID)
    assert [event["event_type"] for event in chain[-1:]] == [
        "RESULT_HANDOFF_READY"]
    assert len(deep_calls) == 1
    monkeypatch.setattr(storage, "atomic_write_json", real_write)
    audit = handoff.recover_approved(root, cfg, ir.RESULT_REQUEST_ID)
    assert audit["event_type"] == "RESULT_AUDIT_REQUESTED"
    assert len(deep_calls) == 1, \
        "exact ready-journal roll-forward must not replay a second time"
    assert replay_calls == ["replay"]
    assert state_machine.project(chain)[ir.RESULT_REQUEST_ID]["state"] == \
        state_machine.RESULT_AUDIT
    after = {
        name: (os.lstat(os.path.join(final, name)).st_ino,
               ir.file_sha256(os.path.join(final, name)))
        for name in ir.DERIVED_FILENAMES
    }
    assert after == before
    with pytest.raises(CouncilError, match="already consumed"):
        handoff.recover_approved(root, cfg, ir.RESULT_REQUEST_ID)


def test_result_artifacts_v2_accept_exact_request_record():
    _objects, _data, request = _objects_and_request()
    validate_result_artifacts(request["result_artifacts"])
    handoff.validate_m8_handoff_request(request)


def test_result_request_carries_no_execution_authority():
    _objects, _data, request = _objects_and_request()
    assert request["live_experiment_allowed"] is False
    assert "execution_authorization" not in request
    assert all("model" not in action.lower()
               for action in request["allowed_actions"])


@pytest.mark.parametrize("field,value", [
    ("analysis_status", "analyzed"),
    ("statistics_computed", True),
    ("successful_runs", 106),
    ("partial_runs", 0),
    ("unattempted_runs", 37),
    ("tombstoned_runs", 1),
    ("terminal_outcomes", 106),
    ("schema_version", "result-artifacts.v3"),
])
def test_result_artifacts_v2_refuses_claim_or_census_drift(field, value):
    _objects, _data, request = _objects_and_request()
    request["result_artifacts"][field] = value
    with pytest.raises(SchemaViolation):
        validate_result_artifacts(request["result_artifacts"])


@pytest.mark.parametrize("field,value", [
    ("start_event_id", "000999-deadbeef"),
    ("start_event_hash", "9" * 64),
    ("manifest_sha256", "9" * 64),
    ("derived_output_root", "logs/results/other"),
    ("primary_inventory_file_sha256", "9" * 64),
    ("coordinate_census_content_hash", "9" * 64),
])
def test_request_refuses_individually_substituted_v2_binding(field, value):
    _objects, _data, request = _objects_and_request()
    request["result_artifacts"][field] = value
    with pytest.raises(SchemaViolation):
        handoff.validate_m8_handoff_request(request)


def test_request_refuses_paired_partial_unattempted_census_drift():
    _objects, _data, request = _objects_and_request()
    request["result_artifacts"]["partial_runs"] = 2
    request["result_artifacts"]["unattempted_runs"] = 37
    # The equations still balance; exact cross-binding must be what refuses.
    validate_result_artifacts(request["result_artifacts"])
    with pytest.raises(SchemaViolation):
        handoff.validate_m8_handoff_request(request)


def test_artifact_bytes_are_deterministic_and_have_no_volatile_fields():
    objects1, data1, _request1 = _objects_and_request()
    objects2, data2, _request2 = _objects_and_request()
    assert objects1 == objects2
    assert data1 == data2
    joined = b"".join(data1.values())
    for forbidden in (b"generated_utc", b"hostname", b"process_id",
                      b"temporary_path"):
        assert forbidden not in joined


def test_artifact_construction_never_imports_provider_or_analysis(
        monkeypatch):
    real_import = handoff.importlib.import_module

    def guarded(name, *args, **kwargs):
        if "ollama" in name or name.endswith(".metrics"):
            raise AssertionError(f"forbidden construction import: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(handoff.importlib, "import_module", guarded)
    handoff._artifact_objects(
        _snapshot(), _replay_core(), _authorization(), _proposal(),
        _approval(), "d" * 64)


def test_atomic_bundle_publish_and_same_transaction_adoption(tmp_path):
    _objects, data, _request = _objects_and_request(str(tmp_path))
    final = tmp_path / "bundle"
    budget = handoff._Budget({
        "max_compute_minutes": 1, "max_wall_minutes": 1,
        "max_storage_mb": 10})
    handoff._write_bundle_transaction(
        str(final), "d" * 64, data, budget)
    first = {name: (final / name).read_bytes() for name in os.listdir(final)}
    handoff._write_bundle_transaction(
        str(final), "d" * 64, data, budget)
    assert {name: (final / name).read_bytes()
            for name in os.listdir(final)} == first


def test_existing_bundle_with_changed_byte_refuses(tmp_path):
    _objects, data, _request = _objects_and_request(str(tmp_path))
    final = tmp_path / "bundle"
    budget = handoff._Budget({
        "max_compute_minutes": 1, "max_wall_minutes": 1,
        "max_storage_mb": 10})
    handoff._write_bundle_transaction(str(final), "d" * 64, data, budget)
    (final / "incomplete_report.json").write_text("{}", encoding="utf-8")
    with pytest.raises(Exception):
        handoff._write_bundle_transaction(str(final), "d" * 64, data, budget)


def test_foreign_interrupted_transaction_refuses(tmp_path):
    _objects, data, _request = _objects_and_request(str(tmp_path))
    parent = tmp_path / "parent"
    parent.mkdir()
    temp = parent / f".m8-incomplete-{'d' * 64}.tmp"
    temp.mkdir()
    (temp / "incomplete_result_package.json").write_text(
        json.dumps({"transaction_id": "e" * 64}), encoding="utf-8")
    budget = handoff._Budget({
        "max_compute_minutes": 1, "max_wall_minutes": 1,
        "max_storage_mb": 10})
    with pytest.raises(Exception):
        handoff._write_bundle_transaction(
            str(parent / "bundle"), "d" * 64, data, budget)


@pytest.mark.parametrize("stage", [
    "after_owner_marker",
    *[f"before_write:{name}" for name in ir.DERIVED_FILENAMES],
    *[f"after_write:{name}" for name in ir.DERIVED_FILENAMES],
    "after_temp_fsync", "after_rename", "after_parent_fsync",
    "after_marker_remove",
])
def test_bundle_crash_matrix_is_recoverable_or_leaves_no_final(
        tmp_path, stage):
    _objects, data, _request = _objects_and_request(str(tmp_path))
    final = tmp_path / "bundle"
    budget = handoff._Budget({
        "max_compute_minutes": 1, "max_wall_minutes": 1,
        "max_storage_mb": 10})

    def fail(at):
        if at == stage:
            raise RuntimeError(stage)

    with pytest.raises(RuntimeError, match=stage):
        handoff._write_bundle_transaction(
            str(final), "d" * 64, data, budget, fault=fail)
    if stage in ("after_rename", "after_parent_fsync"):
        assert final.is_dir()
        handoff._write_bundle_transaction(
            str(final), "d" * 64, data, budget)
        handoff._verify_exact_bundle(str(final), data)
    else:
        assert not final.exists()


def test_real_process_exit_after_first_file_is_recoverable(tmp_path):
    _objects, data, _request = _objects_and_request(str(tmp_path))
    final = tmp_path / "bundle"

    def worker():
        budget = handoff._Budget({
            "max_compute_minutes": 1, "max_wall_minutes": 1,
            "max_storage_mb": 10})

        def stop(stage):
            if stage == "after_write:primary_inventory.json":
                os._exit(73)

        handoff._write_bundle_transaction(
            str(final), "d" * 64, data, budget, fault=stop)

    process = multiprocessing.Process(target=worker)
    process.start()
    process.join(10)
    assert process.exitcode == 73
    budget = handoff._Budget({
        "max_compute_minutes": 1, "max_wall_minutes": 1,
        "max_storage_mb": 10})
    handoff._write_bundle_transaction(
        str(final), "d" * 64, data, budget)
    handoff._verify_exact_bundle(str(final), data)


def test_adoption_flushes_parent_directory(tmp_path):
    _objects, data, _request = _objects_and_request(str(tmp_path))
    final = tmp_path / "bundle"
    budget = handoff._Budget({
        "max_compute_minutes": 1, "max_wall_minutes": 1,
        "max_storage_mb": 10})
    handoff._write_bundle_transaction(str(final), "d" * 64, data, budget)
    stages = []
    handoff._write_bundle_transaction(
        str(final), "d" * 64, data, budget, fault=stages.append)
    assert stages == ["after_adoption_parent_fsync"]


def test_storage_exhaustion_leaves_no_final_bundle(tmp_path):
    _objects, data, _request = _objects_and_request(str(tmp_path))
    final = tmp_path / "bundle"
    budget = handoff._Budget({
        "max_compute_minutes": 1, "max_wall_minutes": 1,
        "max_storage_mb": 0})
    with pytest.raises(Exception):
        handoff._write_bundle_transaction(
            str(final), "d" * 64, data, budget)
    assert not final.exists()


@pytest.mark.parametrize("kind", ["wall", "compute"])
def test_time_budget_exhaustion_is_checked_at_boundaries(kind):
    budget = handoff._Budget({
        "max_compute_minutes": 1, "max_wall_minutes": 1,
        "max_storage_mb": 10})
    if kind == "wall":
        budget.wall_start -= 61
    else:
        budget.compute_start -= 61
    with pytest.raises(CouncilError, match=kind):
        budget.check()


def test_preexisting_request_file_refuses_before_builder(tmp_path):
    root = make_root(tmp_path)
    proposal, approval = _proposal(), _approval()
    chain = [proposal, approval]
    storage.atomic_write_json(
        storage.safe_request_path(root, "ready", ir.RESULT_REQUEST_ID),
        {"foreign": True})
    with pytest.raises(CouncilError, match="lifecycle file"):
        handoff._preflight_request_namespace(root, chain)


def test_direct_append_path_invokes_authoritative_proposal_hook(
        tmp_path, monkeypatch):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    auth = _authorization()
    auth["closure_tool"]["target_commit"] = head
    for item in auth["closure_tool"]["integration_events"]:
        item["target_commit"] = head
    payload = {
        "schema_version": "result-handoff-approval-required.v1",
        "closure_authorization": auth,
        "closure_authorization_hash":
            handoff.closure_authorization_hash(auth),
    }
    monkeypatch.setattr(
        handoff, "validate_proposal_append",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            CouncilError("append-bound refusal")))
    before = events.read_chain(root)
    with pytest.raises(CouncilError, match="append-bound refusal"):
        events.append_event(
            root, cfg, "RESULT_HANDOFF_APPROVAL_REQUIRED", "claude",
            ir.RESULT_REQUEST_ID, repo, head, payload)
    assert events.read_chain(root) == before


@pytest.mark.parametrize("mutation", [
    lambda auth: auth["source_request"].__setitem__(
        "owner_approval_event_hash", "9" * 64),
    lambda auth: auth["terminal_events"]["start"].__setitem__(
        "previous_event_hash", "9" * 64),
    lambda auth: auth["terminal_events"]["pause"].__setitem__(
        "reason", "different"),
    lambda auth: auth["closure_tool"]["integration_events"][0].__setitem__(
        "event_hash", "9" * 64),
    lambda auth: auth["primary_evidence"].__setitem__(
        "primary_inventory_content_hash", "9" * 64),
])
def test_append_bound_proposal_refuses_authority_substitution(
        monkeypatch, mutation):
    expected = _authorization()
    candidate = copy.deepcopy(expected)
    mutation(candidate)
    event = {
        "request_id": ir.RESULT_REQUEST_ID,
        "repository": "/tmp/repo",
        "target_commit": COMMIT,
        "payload": {
            "closure_authorization": candidate,
            "closure_authorization_hash":
                handoff.closure_authorization_hash(candidate),
        },
    }
    monkeypatch.setattr(
        handoff, "build_closure_authorization",
        lambda *_args, **_kwargs: expected)
    with pytest.raises(CouncilError, match="authoritative derivation"):
        handoff.validate_proposal_append(
            "/tmp/council", SimpleNamespace(repo_roots=("/tmp/repo",)),
            [], event)


@pytest.mark.parametrize("path", [
    "../escape", "/absolute", "a\\b", "a/../../b", "",
])
def test_safe_repo_path_refuses_escaping_spelling(tmp_path, path):
    with pytest.raises(ir.IncompleteResultError):
        ir.safe_repo_path(str(tmp_path), path, may_be_absent=True)


def test_primary_inventory_refuses_hardlinks(tmp_path):
    root = tmp_path / "primary"
    root.mkdir()
    original = root / "manifest.jsonl"
    original.write_text("x", encoding="utf-8")
    os.link(original, root / "alias")
    with pytest.raises(ir.IncompleteResultError):
        ir.primary_inventory(
            str(root), expected_dirs={"": {"manifest.jsonl", "alias"}})


def test_primary_inventory_refuses_symlink(tmp_path):
    root = tmp_path / "primary"
    root.mkdir()
    target = tmp_path / "target"
    target.write_text("x", encoding="utf-8")
    os.symlink(target, root / "manifest.jsonl")
    with pytest.raises(ir.IncompleteResultError):
        ir.primary_inventory(
            str(root), expected_dirs={"": {"manifest.jsonl"}})


@pytest.mark.parametrize("mutation", ["add", "delete", "rename", "fifo"])
def test_primary_inventory_refuses_member_mutation(tmp_path, mutation):
    root = tmp_path / "primary"
    root.mkdir()
    manifest = root / "manifest.jsonl"
    manifest.write_text("x", encoding="utf-8")
    if mutation == "add":
        (root / "extra").write_text("x", encoding="utf-8")
    elif mutation == "delete":
        manifest.unlink()
    elif mutation == "rename":
        manifest.rename(root / "renamed")
    else:
        os.mkfifo(root / "extra")
    with pytest.raises(ir.IncompleteResultError):
        ir.primary_inventory(
            str(root), expected_dirs={"": {"manifest.jsonl"}})


def test_verify_bundle_request_detects_added_member(tmp_path, monkeypatch):
    inventory_content = {
        "schema_version": "m8-budget-exhaustion-primary-inventory.v1",
        "evidence_root": ir.EVIDENCE_ROOT,
        "file_count": 423,
        "files": {"manifest.jsonl": ir.MANIFEST_SHA256},
    }
    monkeypatch.setattr(
        ir, "PRIMARY_INVENTORY_CONTENT_HASH",
        ir.domain_hash(ir.PRIMARY_INVENTORY_DOMAIN, inventory_content))
    census = ir.build_coordinate_census(_spec(), _success_rows(), _partial())
    monkeypatch.setattr(
        ir, "COORDINATE_CENSUS_CONTENT_HASH", census["content_hash"])
    objects, data, request = _objects_and_request(str(tmp_path))
    root = tmp_path / ir.DERIVED_OUTPUT_ROOT
    root.mkdir(parents=True)
    for name, value in data.items():
        (root / name).write_bytes(value)
    handoff.verify_bundle_request(str(tmp_path), request, deep=False)
    (root / "extra.json").write_text("{}", encoding="utf-8")
    with pytest.raises(Exception):
        handoff.verify_bundle_request(str(tmp_path), request, deep=False)


def test_replay_attestation_requires_exact_105_successes():
    core = _replay_core()
    core["runs"].pop("run-104")
    with pytest.raises(ir.IncompleteResultError):
        ir.replay_attestation(core)


def test_derived_bundle_hash_is_domain_separated():
    _objects, data, _request = _objects_and_request()
    hashes = handoff._file_hashes(data)
    bare = hashlib.sha256(
        ir.canonical_json(dict(sorted(hashes.items()))).encode()).hexdigest()
    assert ir.derived_bundle_hash(hashes) != bare
