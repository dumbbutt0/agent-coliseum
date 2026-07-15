"""Closed-schema, FSM, and binding regressions for result handoff."""
from copy import deepcopy
import hashlib
import json
import os
import shutil
from types import SimpleNamespace

import pytest

from tests.council_util import make_cfg, make_repo, make_root
from tools.autonomy.runner import validation_report_hash
from tools.council import (codex_watch, events, locking, publish,
                           state_machine, storage)
from tools.council.result_handoff import (
    ARTIFACT_ROLES, AUTHORIZATION_PROFILE, CONFIG_DOMAIN, CONCLUSION_SCOPE,
    INVENTORY_HASH, MANIFEST_FILE, PRIMARY_CAPTURE_HASHES, RESULT_CONFIG,
    RUN_DIR, RUN_ID)
from tools.council import result_handoff
from tools.council.schemas import (
    EVIDENCE_INVENTORY_DOMAIN, FULL_TEST_COMMAND, LockHeld, SchemaViolation,
    canonical_json, compute_request_payload_hash, domain_hash, payload_hash,
    validate_request)

RID = "result-handoff-test-001"


def handoff_request(repo, head, rid=RID, **changes):
    validations = [{"name": "zero_call_replay", "ok": True}]
    request = {
        "request_id": rid, "protocol_version": "2.0",
        "repository": repo, "target_commit": head,
        "require_clean_tree": True,
        "expected_test_command": FULL_TEST_COMMAND,
        "expected_test_count": 1451,
        "scope": ["independent audit of the preserved live capture"],
        "questions": ["Does the evidence authenticate and replay?"],
        "allowed_actions": ["read committed evidence", "offline replay"],
        "forbidden_actions": ["model contact", "evidence mutation"],
        "requested_verdicts": ["RESULT_APPROVED", "RESULT_BLOCKED"],
        "live_experiment_allowed": False, "human_approval_required": True,
        "originating_blocked_commit": "0" * 40,
        "blockers_addressed": ["post-integration chronology"],
        "task_kind": "result_handoff", "run_id": RUN_ID,
        "run_dir": RUN_DIR, "manifest_file": MANIFEST_FILE,
        "evidence_inventory_hash": INVENTORY_HASH,
        "validations": validations,
        "validation_report_hash": validation_report_hash(validations),
        "result_config": deepcopy(RESULT_CONFIG),
        "experiment_config_hash": domain_hash(CONFIG_DOMAIN, RESULT_CONFIG),
        "artifact_roles": deepcopy(ARTIFACT_ROLES),
        "primary_capture_hashes": deepcopy(PRIMARY_CAPTURE_HASHES),
        "authorization_profile": deepcopy(AUTHORIZATION_PROFILE),
        "live_source_evidence_id":
            RESULT_CONFIG["live_source_evidence_id"],
        "conclusion_scope": CONCLUSION_SCOPE,
    }
    request.update(changes)
    request["request_payload_hash"] = compute_request_payload_hash(request)
    return request


def ready_payload(request, txn="a" * 64):
    return {"transaction_id": txn, "phase": "ready_published",
            "request": request,
            "request_payload_hash": request["request_payload_hash"]}


def test_closed_request_accepts_exact_profile(tmp_path):
    repo, head = make_repo(tmp_path)
    validate_request(handoff_request(repo, head), (repo,))


@pytest.mark.parametrize("mutation", ["config", "role", "verdicts",
                                        "unknown", "validation"])
def test_closed_request_rejects_drift(tmp_path, mutation):
    repo, head = make_repo(tmp_path)
    request = handoff_request(repo, head)
    if mutation == "config":
        request["result_config"]["limits"]["live_runs"] = 2
    elif mutation == "role":
        request["artifact_roles"]["live_report.json"] = "primary_capture"
    elif mutation == "verdicts":
        request["requested_verdicts"].reverse()
    elif mutation == "unknown":
        request["authority_note"] = "trust me"
    else:
        request["validations"].append({"name": "changed", "ok": True})
    request["request_payload_hash"] = compute_request_payload_hash(request)
    with pytest.raises(SchemaViolation):
        validate_request(request, (repo,))


def test_ready_event_is_authority_root_and_result_transition(tmp_path):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    request = handoff_request(repo, head)
    ready = events.append_event(root, cfg, "RESULT_HANDOFF_READY", "claude",
                                RID, repo, head, ready_payload(request))
    projected = state_machine.project(events.read_chain(root))
    assert projected[RID]["state"] == state_machine.RESULT_VALIDATION
    assert projected[RID]["audit_cycles"] == 1
    assert projected[RID]["publication_event_id"] == ready["event_id"]
    storage.atomic_write_json(storage.safe_request_path(root, "claimed", RID),
                              request)
    verified, failures, pinned_repo, pinned_commit = publish.verified_request(
        root, cfg, RID)
    assert verified == request and failures == []
    assert (pinned_repo, pinned_commit) == (repo, head)
    events.append_event(
        root, cfg, "RESULT_AUDIT_REQUESTED", "claude", RID, repo, head,
        {"transaction_id": "a" * 64,
         "experiment_config_hash": request["experiment_config_hash"],
         "run_id": RUN_ID, "run_dir": RUN_DIR,
         "evidence_inventory_hash": INVENTORY_HASH,
         "validation_report_hash": request["validation_report_hash"],
         "validations": request["validations"]})
    assert state_machine.project(events.read_chain(root))[RID]["state"] == \
        state_machine.RESULT_AUDIT


def test_ready_event_rejects_self_consistent_file_tamper(tmp_path):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    request = handoff_request(repo, head)
    events.append_event(root, cfg, "RESULT_HANDOFF_READY", "claude", RID,
                        repo, head, ready_payload(request))
    request["expected_test_count"] += 1
    request["request_payload_hash"] = compute_request_payload_hash(request)
    storage.atomic_write_json(storage.safe_request_path(root, "claimed", RID),
                              request)
    _request, failures, _repo, _commit = publish.verified_request(root, cfg, RID)
    assert any("pinned" in failure for failure in failures)


def test_fix_ready_requires_distinct_fixing_predecessor(tmp_path):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    request = handoff_request(repo, head, rid="result-fix-test-001",
                              prior_result_request_id="missing-prior-001",
                              prior_ready_event_id="000001-deadbeef",
                              prior_result_audit_event_id="000002-deadbeef",
                              prior_blocked_event_id="000003-deadbeef",
                              prior_fix_started_event_id="000004-deadbeef",
                              prior_experiment_config_hash=domain_hash(
                                  CONFIG_DOMAIN, RESULT_CONFIG),
                              prior_evidence_inventory_hash=INVENTORY_HASH)
    with pytest.raises(Exception, match="prior result request"):
        events.append_event(root, cfg, "RESULT_FIX_READY", "claude",
                            request["request_id"], repo, head,
                            ready_payload(request))


def test_handoff_binding_injection_uses_ready_not_result_audit(tmp_path):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    request = handoff_request(repo, head)
    ready = events.append_event(root, cfg, "RESULT_HANDOFF_READY", "claude",
                                RID, repo, head, ready_payload(request))
    storage.atomic_write_json(storage.safe_request_path(root, "claimed", RID),
                              request)
    result = events.append_event(
        root, cfg, "RESULT_AUDIT_REQUESTED", "claude", RID, repo, head,
        {"transaction_id": "a" * 64,
         "experiment_config_hash": request["experiment_config_hash"],
         "run_id": RUN_ID, "run_dir": RUN_DIR,
         "evidence_inventory_hash": INVENTORY_HASH,
         "validation_report_hash": request["validation_report_hash"],
         "validations": request["validations"]})
    verdict = {}
    codex_watch._inject_bindings(root, verdict, request, RID, True)
    assert verdict["publication_event_id"] == ready["event_id"]
    assert verdict["publication_event_id"] != result["event_id"]
    assert verdict["evidence_inventory_hash"] == INVENTORY_HASH


def _publisher_env(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    request = handoff_request(repo, head)
    monkeypatch.setattr(result_handoff, "_validate_pack",
                        lambda _repo, _request: None)
    monkeypatch.setattr(result_handoff, "_validate_authority",
                        lambda _root, _cfg, _chain, _request: None)
    monkeypatch.setattr(result_handoff.git_state, "is_ancestor",
                        lambda *_args: True)
    return root, repo, head, cfg, request


def test_event_first_publisher_is_idempotent(tmp_path, monkeypatch):
    root, _repo, _head, cfg, request = _publisher_env(tmp_path, monkeypatch)
    first = result_handoff.publish_handoff(root, cfg, request)
    second = result_handoff.publish_handoff(root, cfg, request)
    assert second == first
    chain = events.read_chain(root)
    assert len([e for e in chain if e["request_id"] == RID and
                e["event_type"] == "RESULT_HANDOFF_READY"]) == 1
    assert len([e for e in chain if e["request_id"] == RID and
                e["event_type"] == "RESULT_AUDIT_REQUESTED"]) == 1


def test_crash_after_ready_rolls_forward_without_duplicate(tmp_path,
                                                            monkeypatch):
    root, _repo, _head, cfg, request = _publisher_env(tmp_path, monkeypatch)
    real_write = storage.atomic_write_json
    calls = {"count": 0}

    def fail_once(path, value):
        if "/requests/claimed/" in path:
            calls["count"] += 1
        if "/requests/claimed/" in path and calls["count"] == 1:
            raise OSError("injected crash after ready append")
        return real_write(path, value)

    monkeypatch.setattr(storage, "atomic_write_json", fail_once)
    with pytest.raises(OSError, match="injected crash"):
        result_handoff.publish_handoff(root, cfg, request)
    chain = events.read_chain(root)
    assert [e["event_type"] for e in chain if e["request_id"] == RID] == [
        "RESULT_HANDOFF_READY"]
    final = result_handoff.publish_handoff(root, cfg, request)
    assert final["event_type"] == "RESULT_AUDIT_REQUESTED"
    chain = events.read_chain(root)
    assert [e["event_type"] for e in chain if e["request_id"] == RID] == [
        "RESULT_HANDOFF_READY", "RESULT_AUDIT_REQUESTED"]


def correction_request(repo, head, **changes):
    config = deepcopy(RESULT_CONFIG)
    config["report_id"] = "b" * 64
    config["evidence_inventory_hash"] = "c" * 64
    request = handoff_request(
        repo, head, rid="result-fix-test-002", result_config=config,
        experiment_config_hash=domain_hash(CONFIG_DOMAIN, config),
        evidence_inventory_hash=config["evidence_inventory_hash"],
        prior_result_request_id="result-parent-test-001",
        prior_ready_event_id="000010-deadbeef",
        prior_result_audit_event_id="000011-deadbeef",
        prior_blocked_event_id="000012-deadbeef",
        prior_fix_started_event_id="000013-deadbeef",
        prior_experiment_config_hash="d" * 64,
        prior_evidence_inventory_hash="e" * 64)
    request.update(changes)
    request["request_payload_hash"] = compute_request_payload_hash(request)
    return request


def test_correction_schema_freezes_primary_but_allows_derived_identity(tmp_path):
    repo, head = make_repo(tmp_path)
    request = correction_request(repo, head)
    validate_request(request, (repo,))
    request["result_config"]["primary_capture_hashes"]["run.json"] = "f" * 64
    request["request_payload_hash"] = compute_request_payload_hash(request)
    with pytest.raises(SchemaViolation, match="frozen result_config"):
        validate_request(request, (repo,))


@pytest.mark.parametrize("field,value", [
    ("behavioral_departure_claimable", True),
    ("complete", True),
    ("status", "complete"),
])
def test_correction_cannot_expand_frozen_conclusion_ceiling(
        tmp_path, field, value):
    repo, head = make_repo(tmp_path)
    request = correction_request(repo, head)
    request["result_config"]["outcome"][field] = value
    request["experiment_config_hash"] = domain_hash(
        CONFIG_DOMAIN, request["result_config"])
    request["request_payload_hash"] = compute_request_payload_hash(request)
    with pytest.raises(SchemaViolation, match="conclusion ceiling"):
        validate_request(request, (repo,))


def test_correction_pack_may_change_only_derived_report(tmp_path, monkeypatch):
    repo, head = make_repo(tmp_path)
    source = os.path.join("logs", "live-persona-runs", RUN_ID)
    target = os.path.join(repo, RUN_DIR)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copytree(source, target)
    report_path = os.path.join(target, "live_report.json")
    report = json.load(open(report_path, encoding="utf-8"))
    report["content"]["repair_note"] = "derived-only correction"
    report["id"] = payload_hash(report["content"])
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(canonical_json(report) + "\n")
    files = {name: hashlib.sha256(
        open(os.path.join(target, name), "rb").read()).hexdigest()
             for name in sorted(os.listdir(target))}
    content = {"schema_version": "evidence-manifest.v1", "run_id": RUN_ID,
               "run_dir": RUN_DIR, "file_count": len(files), "files": files}
    inventory_hash = domain_hash(EVIDENCE_INVENTORY_DOMAIN, content)
    manifest = dict(content, inventory_hash=inventory_hash,
                    generated_utc="2026-07-15T00:00:00Z")
    with open(os.path.join(repo, MANIFEST_FILE), "w", encoding="utf-8") as fh:
        fh.write(canonical_json(manifest) + "\n")
    config = deepcopy(RESULT_CONFIG)
    config["report_id"] = report["id"]
    config["evidence_inventory_hash"] = inventory_hash
    request = correction_request(
        repo, head, result_config=config,
        experiment_config_hash=domain_hash(CONFIG_DOMAIN, config),
        evidence_inventory_hash=inventory_hash)
    monkeypatch.setattr(
        result_handoff.subprocess, "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout='{"replay_ok":true}', stderr=""))
    result_handoff._validate_pack(repo, request)


def test_transaction_lock_refuses_competing_publisher_before_event(tmp_path,
                                                                   monkeypatch):
    root, _repo, _head, cfg, request = _publisher_env(tmp_path, monkeypatch)
    held = locking.acquire(root, "_result_handoff", "claude", "holder-001")
    try:
        with pytest.raises(LockHeld):
            result_handoff.publish_handoff(root, cfg, request)
        assert not [e for e in events.read_chain(root)
                    if e["request_id"] == RID]
    finally:
        locking.release(held)


def test_valid_correction_advances_lineage_to_cycle_two(tmp_path):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    parent = handoff_request(repo, head, rid="result-parent-test-001")
    ready = events.append_event(
        root, cfg, "RESULT_HANDOFF_READY", "claude", parent["request_id"],
        repo, head, ready_payload(parent))
    storage.atomic_write_json(
        storage.safe_request_path(root, "claimed", parent["request_id"]), parent)
    result_audit = events.append_event(
        root, cfg, "RESULT_AUDIT_REQUESTED", "claude", parent["request_id"],
        repo, head, {"transaction_id": "a" * 64,
                     "experiment_config_hash": parent["experiment_config_hash"],
                     "run_id": RUN_ID, "run_dir": RUN_DIR,
                     "evidence_inventory_hash": parent["evidence_inventory_hash"],
                     "validation_report_hash": parent["validation_report_hash"],
                     "validations": parent["validations"]})
    blocked = codex_watch.submit_verdict(root, make_cfg(repo, root, "codex"), {
        "request_id": parent["request_id"], "audited_commit": head,
        "audit_mode": "result", "working_tree_clean": True,
        "tests_observed": parent["expected_test_count"], "verdict": "BLOCKED",
        "summary": "derived report needs correction", "blockers": ["derived"],
        "conditions": [], "findings": [], "commands_run": ["offline replay"],
        "timestamp_utc": storage.utc_now(), "replay_result": "replayed_ok",
        "counts": {"scenarios_run": 1, "validations_passed": 1,
                   "validations_failed": 0},
        "conclusion_scope": CONCLUSION_SCOPE}, result_audit=True)
    fixed = events.append_event(root, cfg, "FIX_STARTED", "claude",
                                parent["request_id"], repo, head,
                                {"reason": "derived-only repair"})
    child = correction_request(
        repo, head, prior_ready_event_id=ready["event_id"],
        prior_result_audit_event_id=result_audit["event_id"],
        prior_blocked_event_id=blocked["event_id"],
        prior_fix_started_event_id=fixed["event_id"],
        prior_experiment_config_hash=parent["experiment_config_hash"],
        prior_evidence_inventory_hash=parent["evidence_inventory_hash"])
    event = events.append_event(root, cfg, "RESULT_FIX_READY", "claude",
                                child["request_id"], repo, head,
                                ready_payload(child, "b" * 64))
    projected = state_machine.project(events.read_chain(root))
    assert event["event_type"] == "RESULT_FIX_READY"
    assert projected[child["request_id"]]["audit_cycles"] == 2


def test_cycle_six_is_refused_by_fsm():
    requests = {
        "prior-cycle-five": {
            "state": state_machine.FIXING, "target_commit": "1" * 40,
            "claimed_by": None, "audit_cycles": 5, "history": [],
            "last_event_id": None, "last_verdict": None,
            "conditions_satisfied": False}}
    event = {"event_type": "RESULT_FIX_READY", "request_id": "cycle-six-new",
             "target_commit": "2" * 40,
             "payload": {"request": {
                 "prior_result_request_id": "prior-cycle-five"}}}
    with pytest.raises(Exception, match="five audit cycles"):
        state_machine.check(event, requests)
