"""Closed-schema, FSM, and binding regressions for result handoff."""
from copy import deepcopy

import pytest

from tests.council_util import make_cfg, make_repo, make_root
from tools.autonomy.runner import validation_report_hash
from tools.council import codex_watch, events, publish, state_machine, storage
from tools.council.result_handoff import (
    ARTIFACT_ROLES, AUTHORIZATION_PROFILE, CONFIG_DOMAIN, CONCLUSION_SCOPE,
    INVENTORY_HASH, MANIFEST_FILE, PRIMARY_CAPTURE_HASHES, RESULT_CONFIG,
    RUN_DIR, RUN_ID)
from tools.council import result_handoff
from tools.council.schemas import (
    FULL_TEST_COMMAND, SchemaViolation, compute_request_payload_hash,
    domain_hash, validate_request)

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
