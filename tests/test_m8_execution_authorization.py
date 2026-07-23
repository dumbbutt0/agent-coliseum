"""M8 owner-bound execution admission and lifecycle cross-checks.

All fixtures are provider-free. They exercise the request/event/runner seams
that must agree before the first evidence directory can be created.
"""
from __future__ import annotations

import hashlib
import json
import os
from types import SimpleNamespace

import pytest

from tests.autonomy_util import policy_doc
from tools.autonomy import roadmap
from tools.autonomy import runner
from tools.council import cli as council_cli
from tools.council import events, publish
from tools.council.schemas import (CouncilError, SchemaViolation,
                                   compute_execution_authorization_hash,
                                   validate_execution_authorization,
                                   validate_result_artifacts)


RID = "m8-owner-bound-test-001"
COMMIT = "a" * 40
REQUEST_HASH = "b" * 64
CONFIG_HASH = "c" * 64
DESIGN_HASH = "d" * 64
MODEL = "model:test"
DIGEST = "e" * 64
PUB_ID = "000010-aaaaaaaa"
PUB_HASH = "1" * 64
APPROVAL_ID = "000011-bbbbbbbb"
M7_IDS = ["001714-6f7a48e0", "001719-21604e97", "001724-8cebf880"]
INTEGRATION_IDS = [
    "000004-44444444", "000005-55555555", "000006-66666666",
    "000007-77777777", "000008-88888888",
]


def _authorization():
    return {
        "schema_version": "execution-authorization.v1",
        "experiment_id": "m8-phase2-live-order-sensitivity",
        "design_hash": DESIGN_HASH,
        "implementation_commit": COMMIT,
        "experiment_config_hash": CONFIG_HASH,
        "model_digests": {MODEL: DIGEST},
        "planned_runs": 144,
        "budget": {"max_units": 144, "max_compute_minutes": 180,
                   "max_wall_minutes": 210, "max_storage_mb": 768,
                   "max_retries_per_unit": 0, "max_scenarios": 3},
        "evidence_root": "logs/runs/m8-phase2-live-order-sensitivity",
        "manifest": ("logs/runs/m8-phase2-live-order-sensitivity/"
                     "manifest.jsonl"),
        "m7_prerequisite_events": list(M7_IDS),
        "source_integration_events": list(INTEGRATION_IDS),
        "resume_from": None,
    }


def _request(repo):
    return {
        "request_id": RID, "repository": str(repo),
        "target_commit": COMMIT, "request_payload_hash": REQUEST_HASH,
        "experiment_config_file": "configs/experiments/m8.json",
        "experiment_config_hash": CONFIG_HASH,
        "execution_authorization": _authorization(),
    }


def _publication():
    return {"event_id": PUB_ID, "event_hash": PUB_HASH,
            "event_type": "AUDIT_REQUESTED", "request_id": RID,
            "target_commit": COMMIT, "payload": {
                "request_payload_hash": REQUEST_HASH,
                "execution_authorization_hash":
                    compute_execution_authorization_hash(_authorization())}}


def _prerequisite_chain():
    chain = []
    chain.extend({"event_id": event_id, "event_type": "AUDIT_GO",
                  "request_id": f"m7-{i}", "target_commit": "f" * 40,
                  "payload": {}}
                 for i, event_id in enumerate(M7_IDS))
    chain.extend({"event_id": event_id,
                  "event_type": "CHANGE_INTEGRATED",
                  "request_id": f"m8-source-{i}",
                  "target_commit": COMMIT, "payload": {}}
                 for i, event_id in enumerate(INTEGRATION_IDS))
    chain.append(_publication())
    return chain


def _approval_payload():
    return {
        "approval_schema_version": "experiment-approval.v2",
        "approved_by": "human", "approval_commit": COMMIT,
        "request_payload_hash": REQUEST_HASH,
        "request_publication_event_id": PUB_ID,
        "request_publication_event_hash": PUB_HASH,
        "execution_authorization": _authorization(),
    }


def _approval_event():
    return {"event_id": APPROVAL_ID, "event_type": "EXPERIMENT_APPROVED",
            "request_id": RID, "target_commit": COMMIT,
            "payload": _approval_payload()}


def _config():
    return {
        "experiment_id": "m8-phase2-live-order-sensitivity",
        "task_id": "m8-phase2-live-order-sensitivity",
        "design_hash": DESIGN_HASH, "model_digests": {MODEL: DIGEST},
        "expected_run_count": 144, "scenario_count": 3,
        "retries_per_unit": 0,
        "out_root": "logs/runs/m8-phase2-live-order-sensitivity",
        "manifest": ("logs/runs/m8-phase2-live-order-sensitivity/"
                     "manifest.jsonl"),
    }


def test_execution_authorization_schema_is_closed_and_allows_zero_retries():
    validate_execution_authorization(_authorization())
    for mutation in (
            lambda a: a["budget"].__setitem__("max_units", 143),
            lambda a: a["budget"].__setitem__("max_scenarios", 3.5),
            lambda a: a["budget"].__setitem__("max_retries_per_unit", -1),
            lambda a: a.__setitem__("planned_runs", True),
            lambda a: a.__setitem__("manifest", "../escape"),
            lambda a: a["m7_prerequisite_events"].append(M7_IDS[0]),
            lambda a: a.__setitem__(
                "m7_prerequisite_events", list(reversed(M7_IDS)))):
        candidate = json.loads(json.dumps(_authorization()))
        mutation(candidate)
        with pytest.raises(SchemaViolation):
            validate_execution_authorization(candidate)


def test_owner_approval_must_copy_publication_and_authorization(
        tmp_path, monkeypatch):
    request = _request(tmp_path)
    monkeypatch.setattr(publish, "verified_request",
                        lambda *_a: (request, [], str(tmp_path), COMMIT))
    chain = _prerequisite_chain()
    event = {"request_id": RID, "repository": str(tmp_path),
             "target_commit": COMMIT, "payload": _approval_payload()}
    events._verify_experiment_approval_binding(None, None, chain, event)

    event["payload"] = dict(event["payload"],
                            request_publication_event_hash="2" * 64)
    with pytest.raises(CouncilError, match="exactly copy"):
        events._verify_experiment_approval_binding(None, None, chain, event)

    event["payload"] = {"approved_by": "human",
                        "approval_commit": COMMIT}
    with pytest.raises(SchemaViolation):
        events._verify_experiment_approval_binding(None, None, chain, event)


def test_owner_cli_constructs_token_bound_v2_payload(tmp_path, monkeypatch):
    request = _request(tmp_path)
    captured = {}
    monkeypatch.setattr(council_cli, "_cfg",
                        lambda _args: (SimpleNamespace(), "root"))
    monkeypatch.setattr(publish, "verified_request",
                        lambda *_a: (request, [], str(tmp_path), COMMIT))
    monkeypatch.setattr(council_cli.events, "read_chain",
                        lambda _root: _prerequisite_chain())
    monkeypatch.setattr(council_cli, "_maybe_human_token",
                        lambda *_a: None)

    def append(_root, _cfg, event_type, sender, rid, repo, commit, payload):
        captured.update(event_type=event_type, sender=sender, rid=rid,
                        repo=repo, commit=commit, payload=payload)
        return {"event_id": APPROVAL_ID}

    monkeypatch.setattr(council_cli.events, "append_event", append)
    monkeypatch.setattr(council_cli.storage, "append_log_md",
                        lambda *_a: None)
    args = SimpleNamespace(role="human", request_id=RID, commit=COMMIT,
                           token_file=None)
    assert council_cli.cmd_approve(args) == 0
    assert captured["event_type"] == "EXPERIMENT_APPROVED"
    assert captured["payload"] == _approval_payload()

def test_started_event_rechecks_owner_binding_and_fresh_evidence_root(
        tmp_path, monkeypatch):
    request = _request(tmp_path)
    monkeypatch.setattr(publish, "verified_request",
                        lambda *_a: (request, [], str(tmp_path), COMMIT))
    chain = _prerequisite_chain() + [_approval_event()]
    payload = {
        "owner_approval_event_id": APPROVAL_ID,
        "request_payload_hash": REQUEST_HASH,
        "execution_authorization": _authorization(),
        "experiment_config_hash": CONFIG_HASH,
        "limits": {k: v for k, v in _authorization()["budget"].items()
                   if k != "max_units"},
    }
    event = {"request_id": RID, "repository": str(tmp_path),
             "target_commit": COMMIT,
             "payload": payload}
    events._verify_experiment_start_binding(None, None, chain, event)

    evidence = tmp_path / _authorization()["evidence_root"]
    evidence.mkdir(parents=True)
    with pytest.raises(CouncilError, match="pre-existing evidence"):
        events._verify_experiment_start_binding(None, None, chain, event)


def test_runner_rechecks_executable_values_budget_and_approval(
        tmp_path, monkeypatch):
    request = _request(tmp_path)
    monkeypatch.setattr(runner.events, "read_chain",
                        lambda _root: _prerequisite_chain() +
                        [_approval_event()])
    limits = {k: v for k, v in _authorization()["budget"].items()
              if k != "max_units"}
    failures, approval_id = runner._verify_execution_authorization(
        "unused", RID, request, _config(), CONFIG_HASH, limits)
    assert failures == []
    assert approval_id == APPROVAL_ID

    changed = _config()
    changed["expected_run_count"] = 143
    failures, _ = runner._verify_execution_authorization(
        "unused", RID, request, changed, CONFIG_HASH, limits)
    assert any("planned_runs" in failure for failure in failures)


def test_publication_crosschecks_config_registry_chain_and_empty_namespace(
        tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    config_path = repo / "configs" / "experiments" / "m8.json"
    config_path.parent.mkdir(parents=True)
    config = _config()
    body = json.dumps(config, sort_keys=True).encode()
    config_path.write_bytes(body)
    authorization = _authorization()
    authorization["experiment_config_hash"] = hashlib.sha256(body).hexdigest()
    request = _request(repo)
    request["experiment_config_hash"] = authorization["experiment_config_hash"]
    request["execution_authorization"] = authorization
    from tools.autonomy import execution_binding
    monkeypatch.setattr(
        execution_binding, "verified_experiment_identity",
        lambda *_a: {"design_hash": DESIGN_HASH,
                     "model_digests": {MODEL: DIGEST},
                     "planned_runs": 144})
    publish._validate_execution_request_bindings(
        "unused", request, _prerequisite_chain())

    (repo / authorization["evidence_root"]).mkdir(parents=True)
    with pytest.raises(SchemaViolation, match="must be absent"):
        publish._validate_execution_request_bindings(
            "unused", request, _prerequisite_chain())

    # A fresh owner-approved request may resume the SAME frozen pack after the
    # prior request paused, but it must preserve every binding and reuse the
    # existing terminal ledger rather than create a replacement namespace.
    manifest_path = repo / authorization["manifest"]
    manifest_path.write_text("", encoding="utf-8")
    prior_rid = "prior-m8-run-001"
    prior_approval_id = "000009-99999999"
    prior_auth = json.loads(json.dumps(authorization))
    resume_auth = json.loads(json.dumps(authorization))
    resume_auth["resume_from"] = {
        "request_id": prior_rid,
        "owner_approval_event_id": prior_approval_id,
    }
    resume_request = dict(request, execution_authorization=resume_auth)
    prior_lineage = [
        {"event_id": "000103-33333333", "event_type": "BUILD_STARTED",
         "sender": "claude", "request_id": prior_rid,
         "target_commit": COMMIT, "payload": {}},
        {"event_id": "000104-44444444", "event_type": "BUILD_READY",
         "sender": "claude", "request_id": prior_rid,
         "target_commit": COMMIT, "payload": {}},
        {"event_id": "000105-55555555", "event_type": "AUDIT_REQUESTED",
         "sender": "claude", "request_id": prior_rid,
         "target_commit": COMMIT, "payload": {}},
        {"event_id": "000106-66666666", "event_type": "AUDIT_CLAIMED",
         "sender": "codex", "request_id": prior_rid,
         "target_commit": COMMIT, "payload": {}},
        {"event_id": "000107-77777777", "event_type": "AUDIT_GO",
         "sender": "codex", "request_id": prior_rid,
         "target_commit": COMMIT, "payload": {}},
        {"event_id": "000108-88888888",
         "event_type": "HUMAN_APPROVAL_REQUIRED",
         "sender": "claude", "request_id": prior_rid,
         "target_commit": COMMIT, "payload": {}},
        {"event_id": prior_approval_id, "event_type": "EXPERIMENT_APPROVED",
         "sender": "human", "request_id": prior_rid,
         "target_commit": COMMIT,
         "payload": {"execution_authorization": prior_auth}},
        {"event_id": "000112-cccccccc", "event_type": "AUTONOMY_PAUSED",
         "sender": "claude", "request_id": prior_rid,
         "target_commit": COMMIT, "payload": {}},
    ]
    resume_chain = _prerequisite_chain() + prior_lineage
    publish._validate_execution_request_bindings(
        "unused", resume_request, resume_chain)


def test_repository_roadmap_contains_owner_only_m8_run_task():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(repo, "configs", "autonomy-roadmap.yaml")
    doc, _digest = roadmap.load_roadmap(path, policy_doc())
    task = roadmap.task_by_id(doc, "m8-phase2-live-order-sensitivity")
    assert task["status"] == "ready"
    assert task["experiment_class"] == "ollama_local"
    assert task["requires_human"] is False
    # The dependency remains non-complete in the YAML, so automatic selection
    # cannot choose this owner-event-only task.
    assert task not in roadmap.eligible_tasks(doc)


def test_result_artifact_binding_closes_terminal_census():
    artifacts = {
        "owner_approval_event_id": APPROVAL_ID,
        "request_payload_hash": REQUEST_HASH,
        "manifest_sha256": "1" * 64,
        "tombstone_ledger": {"state": "present", "sha256": "2" * 64},
        "replay_attestation_sha256": "3" * 64,
        "order_report_sha256": "4" * 64,
        "result_package_file_sha256": "5" * 64,
        "result_package_content_sha256": "6" * 64,
        "successful_runs": 143, "tombstoned_runs": 1,
        "terminal_outcomes": 144,
        "analysis_status": "terminal_failure_inconclusive",
    }
    validate_result_artifacts(artifacts)
    artifacts["terminal_outcomes"] = 143
    with pytest.raises(SchemaViolation, match="census"):
        validate_result_artifacts(artifacts)


def test_bound_completion_and_result_audit_require_same_artifact_record(
        tmp_path, monkeypatch):
    request = _request(tmp_path)
    monkeypatch.setattr(publish, "verified_request",
                        lambda *_a: (request, [], str(tmp_path), COMMIT))
    chain = _prerequisite_chain() + [_approval_event()]
    base_event = {"request_id": RID, "repository": str(tmp_path),
                  "target_commit": COMMIT}

    missing = dict(base_event, event_type="EXPERIMENT_COMPLETE", payload={})
    with pytest.raises(CouncilError, match="must carry"):
        events._verify_result_artifact_binding(None, None, chain, missing)

    artifacts = {
        "owner_approval_event_id": APPROVAL_ID,
        "request_payload_hash": REQUEST_HASH,
        "manifest_sha256": "1" * 64,
        "tombstone_ledger": {"state": "present", "sha256": "2" * 64},
        "replay_attestation_sha256": "3" * 64,
        "order_report_sha256": "4" * 64,
        "result_package_file_sha256": "5" * 64,
        "result_package_content_sha256": "6" * 64,
        "successful_runs": 143, "tombstoned_runs": 1,
        "terminal_outcomes": 144,
        "analysis_status": "terminal_failure_inconclusive",
    }
    complete = dict(base_event, event_type="EXPERIMENT_COMPLETE",
                    payload={"result_artifacts": artifacts})
    events._verify_result_artifact_binding(None, None, chain, complete)

    changed = json.loads(json.dumps(artifacts))
    changed["order_report_sha256"] = "7" * 64
    audit_event = dict(base_event, event_type="RESULT_AUDIT_REQUESTED",
                       payload={"result_artifacts": changed})
    with pytest.raises(CouncilError, match="exactly equal"):
        events._verify_result_artifact_binding(
            None, None, chain + [complete], audit_event)
