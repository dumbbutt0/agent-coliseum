"""Autonomy policy: immutability, condition matrix, milestone accounting."""
import json
import os
import stat

import pytest

from tests.council_util import (append, make_autonomy_block, make_cfg,
                                make_repo, make_request, make_root)
from tools.council import events, policy, storage
from tools.council.schemas import SchemaViolation, payload_hash

RID = "policy-req-001"


@pytest.fixture()
def env(tmp_path):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    return root, repo, head, make_cfg(repo, root)


def _go_event(head, verdict_payload, event_type="AUDIT_GO"):
    return {"event_id": "000009-testtest", "event_type": event_type,
            "sender": "codex", "request_id": RID, "payload": verdict_payload,
            "target_commit": head}


def _verdict(head):
    from tests.council_util import make_verdict
    from tools.council.schemas import compute_verdict_payload_hash
    verdict = make_verdict(head, request_id=RID)
    verdict["verdict_payload_hash"] = compute_verdict_payload_hash(verdict)
    return verdict


def _autonomy_request(repo, head, **overrides):
    return make_request(repo, head, RID, human_approval_required=False,
                        autonomy=make_autonomy_block(), **overrides)


def test_policy_write_once(env):
    root, _repo, _head, _cfg = env
    path = policy.write_initial_policy(root)
    assert os.path.exists(path)
    with pytest.raises(SchemaViolation):
        policy.write_initial_policy(root)  # immutable: no overwrite path


def test_policy_file_is_read_only_best_effort(env):
    root, _repo, _head, _cfg = env
    path = policy.write_initial_policy(root)
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert not mode & stat.S_IWUSR or os.name == "nt"


def test_load_policy_requires_sections(env):
    root, _repo, _head, _cfg = env
    with pytest.raises(SchemaViolation):
        policy.load_policy(root)  # not installed
    with open(storage.policy_path(root), "w", encoding="utf-8") as fh:
        json.dump({"policy_id": "incomplete"}, fh)
    with pytest.raises(SchemaViolation):
        policy.load_policy(root)


def test_evaluate_full_pass_auto_approves(env):
    root, repo, head, cfg = env
    policy.write_initial_policy(root)
    request = _autonomy_request(repo, head)
    decision = policy.evaluate(root, cfg, request, _go_event(head,
                               _verdict(head)), events.read_chain(root))
    assert decision.auto_approve, decision.reasons
    assert decision.policy_hash
    assert len(decision.checked) >= 13


def test_no_policy_installed_fails_closed(env):
    root, repo, head, cfg = env
    request = _autonomy_request(repo, head)
    decision = policy.evaluate(root, cfg, request, _go_event(head,
                               _verdict(head)), [])
    assert not decision.auto_approve
    assert any("policy_installed" in r for r in decision.reasons)


def test_go_with_conditions_fails(env):
    root, repo, head, cfg = env
    policy.write_initial_policy(root)
    request = _autonomy_request(repo, head)
    event = _go_event(head, _verdict(head),
                      event_type="AUDIT_GO_WITH_CONDITIONS")
    decision = policy.evaluate(root, cfg, request, event, [])
    assert not decision.auto_approve
    assert any("verdict_is_go" in r for r in decision.reasons)


def test_commit_mismatch_fails(env):
    root, repo, head, cfg = env
    policy.write_initial_policy(root)
    request = _autonomy_request(repo, head)
    bad = _verdict(head)
    bad["audited_commit"] = "d" * 40
    decision = policy.evaluate(root, cfg, request, _go_event(head, bad), [])
    assert any("verdict_commit_exact" in r for r in decision.reasons)


def test_dirty_tree_fails(env):
    root, repo, head, cfg = env
    policy.write_initial_policy(root)
    with open(os.path.join(repo, "dirty.txt"), "w") as fh:
        fh.write("x\n")
    request = _autonomy_request(repo, head)
    decision = policy.evaluate(root, cfg, request, _go_event(head,
                               _verdict(head)), [])
    assert any("working_tree_clean" in r for r in decision.reasons)


def test_emergency_stop_fails(env):
    root, repo, head, cfg = env
    policy.write_initial_policy(root)
    open(os.path.join(root, "STOP"), "w").close()
    request = _autonomy_request(repo, head)
    decision = policy.evaluate(root, cfg, request, _go_event(head,
                               _verdict(head)), [])
    assert any("emergency_stop_clear" in r for r in decision.reasons)


def test_human_gate_request_never_auto_approves(env):
    root, repo, head, cfg = env
    policy.write_initial_policy(root)
    request = make_request(repo, head, RID)  # human_approval_required: True
    decision = policy.evaluate(root, cfg, request, _go_event(head,
                               _verdict(head)), [])
    assert not decision.auto_approve
    assert any("request_declares_autonomy" in r for r in decision.reasons)


def test_policy_hash_drift_pauses_autonomy(env):
    root, repo, head, cfg = env
    policy.write_initial_policy(root)
    _pol, original_hash = policy.load_policy(root)
    append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head,
           {"policy_hash": original_hash})  # pin it in the chain
    # someone edits the policy file mid-flight
    path = storage.policy_path(root)
    os.chmod(path, 0o644)
    doctored = json.load(open(path, encoding="utf-8"))
    doctored["auto_approval"]["limits"]["max_scenarios"] = 10_000
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doctored, fh)
    request = _autonomy_request(repo, head)
    decision = policy.evaluate(root, cfg, request, _go_event(head,
                               _verdict(head)), events.read_chain(root))
    assert not decision.auto_approve
    assert any("policy_unchanged" in r for r in decision.reasons)


def test_limits_over_policy_fail(env):
    root, repo, head, cfg = env
    policy.write_initial_policy(root)
    block = make_autonomy_block()
    block["limits"]["max_storage_mb"] = 999_999
    request = make_request(repo, head, RID, human_approval_required=False,
                           autonomy=block)
    decision = policy.evaluate(root, cfg, request, _go_event(head,
                               _verdict(head)), [])
    assert any("limits_within_policy" in r for r in decision.reasons)


def test_retry_limit_capped_at_two(env):
    root, repo, head, cfg = env
    policy.write_initial_policy(root)
    block = make_autonomy_block()
    block["limits"]["max_retries_per_unit"] = 3
    request = make_request(repo, head, RID, human_approval_required=False,
                           autonomy=block)
    decision = policy.evaluate(root, cfg, request, _go_event(head,
                               _verdict(head)), [])
    assert not decision.auto_approve


def test_missing_forbidden_capabilities_fail(env):
    root, repo, head, cfg = env
    policy.write_initial_policy(root)
    request = _autonomy_request(repo, head,
                                forbidden_actions=["destructive_tools"])
    decision = policy.evaluate(root, cfg, request, _go_event(head,
                               _verdict(head)), [])
    assert any("forbidden_capabilities_declared" in r
               for r in decision.reasons)


def test_protocol_self_modification_refused(env):
    root, repo, head, cfg = env
    policy.write_initial_policy(root)
    request = _autonomy_request(
        repo, head, scope=["improve tools/council/state_machine.py"])
    decision = policy.evaluate(root, cfg, request, _go_event(head,
                               _verdict(head)), [])
    assert any("no_protocol_self_modification" in r
               for r in decision.reasons)


def test_milestone_reached_blocks_autonomy(env):
    root, repo, head, cfg = env
    policy.write_initial_policy(root)
    append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    append(root, cfg, "AUTONOMY_MILESTONE_REACHED", "claude", RID, repo,
           head, {"reason": "society milestone"})
    request = _autonomy_request(repo, head)
    decision = policy.evaluate(root, cfg, request, _go_event(head,
                               _verdict(head)), events.read_chain(root))
    assert not decision.auto_approve
    assert any("milestone_not_reached" in r for r in decision.reasons)


def test_milestone_status_accumulates_codex_signed_criteria(env):
    root, _repo, _head, _cfg = env
    policy.write_initial_policy(root)
    pol, _hash = policy.load_policy(root)
    criteria = pol["society_milestone"]["criteria"]
    partial = [{"event_type": "RESULT_APPROVED",
                "payload": {"milestones_completed": criteria[:4]}}]
    reached, satisfied, missing = policy.milestone_status(partial, pol)
    assert not reached and len(satisfied) == 4
    full = partial + [
        {"event_type": "RESULT_APPROVED",
         "payload": {"milestones_completed": criteria[4:-1]}},
        {"event_type": "AUDIT_GO",
         "payload": {"milestones_completed": [criteria[-1]]}},
    ]
    reached, satisfied, missing = policy.milestone_status(full, pol)
    assert reached and not missing
    # agent-sent event types never certify criteria
    fake = [{"event_type": "BUILD_READY",
             "payload": {"milestones_completed": criteria}}]
    reached, satisfied, _missing = policy.milestone_status(fake, pol)
    assert not reached and not satisfied


def test_policy_hash_is_content_addressed(env):
    root, _repo, _head, _cfg = env
    policy.write_initial_policy(root)
    pol, h = policy.load_policy(root)
    assert h == payload_hash(pol)
