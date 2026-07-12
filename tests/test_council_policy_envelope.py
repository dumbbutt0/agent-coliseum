"""M7c autonomous safety envelope: return-to-manual, auto-halt on consecutive
failures, aggregate-compute ceiling. These gate ONLY auto-approval — the human
gate still works — and the counters reset on the owner's control actions."""
import os

import pytest

from tests.council_util import (append, make_autonomy_block, make_cfg,
                                make_repo, make_request, make_root,
                                make_verdict)
from tools.council import checkpoint, events, policy, storage
from tools.council.schemas import compute_verdict_payload_hash

CONTROL_RID = "council-control"


def _ev(et, **p):
    return {"event_type": et, "payload": p}


# ---------------------------------------------------------- metrics helper

def test_metrics_count_failures_and_aggregate_compute():
    chain = [
        _ev("EXPERIMENT_COMPLETE", elapsed_minutes=10),
        _ev("RESULT_APPROVED"),
        _ev("EXPERIMENT_COMPLETE", elapsed_minutes=5),
        _ev("RESULT_BLOCKED"),
        _ev("AUTONOMY_PAUSED"),
    ]
    fails, agg = policy.autonomous_safety_metrics(chain)
    assert fails == 2            # trailing BLOCKED + PAUSED, stops at APPROVED
    assert agg == 15.0           # 10 + 5


def test_owner_control_action_resets_the_window():
    chain = [
        _ev("EXPERIMENT_COMPLETE", elapsed_minutes=99),
        _ev("RESULT_BLOCKED"), _ev("RESULT_BLOCKED"),
        _ev("STATUS_CHANGED", status="active"),   # owner re-asserts control
        _ev("EXPERIMENT_COMPLETE", elapsed_minutes=3),
    ]
    fails, agg = policy.autonomous_safety_metrics(chain)
    assert fails == 0 and agg == 3.0             # only events after the reset


def test_success_resets_the_failure_streak():
    chain = [_ev("RESULT_BLOCKED"), _ev("RESULT_APPROVED"),
             _ev("RESULT_BLOCKED")]
    fails, _agg = policy.autonomous_safety_metrics(chain)
    assert fails == 1


# ------------------------------------------------------ evaluate integration

@pytest.fixture()
def env(tmp_path):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    policy.write_initial_policy(root)
    _p, v1_hash = policy.load_policy(root)
    append(root, cfg, "POLICY_INITIALIZED", "human", CONTROL_RID, repo,
           "0" * 40, {"policy_hash": v1_hash, "policy_file": storage.POLICY_FILE})
    return root, repo, head, cfg


def _decision(root, repo, head, cfg):
    autonomy = make_autonomy_block()
    request = make_request(repo, head, "env-req-001",
                           human_approval_required=False, autonomy=autonomy)
    verdict = make_verdict(head, request_id="env-req-001", verdict="GO")
    verdict["verdict_payload_hash"] = compute_verdict_payload_hash(verdict)
    go = {"event_type": "AUDIT_GO", "sender": "codex",
          "request_id": "env-req-001", "payload": verdict, "target_commit": head}
    return policy.evaluate(root, cfg, request, go, events.read_chain(root))


def test_manual_marker_disables_auto_approval(env):
    root, repo, head, cfg = env
    # baseline: the envelope conditions are all satisfied (they are CHECKED)
    dec = _decision(root, repo, head, cfg)
    assert "auto_approval_enabled" in dec.checked
    assert not any("auto_approval_enabled" in r for r in dec.reasons)
    # drop the MANUAL marker -> auto-approval refused (human gate), council up
    open(os.path.join(root, storage.MANUAL_FILE), "w").close()
    dec = _decision(root, repo, head, cfg)
    assert not dec.auto_approve
    assert any("manual mode" in r for r in dec.reasons)


def test_consecutive_failures_halt_auto_approval(env):
    root, repo, head, cfg = env
    for _ in range(policy.AUTO_HALT_CONSECUTIVE_FAILURES):
        append(root, cfg, "AUTONOMY_PAUSED", "claude", "x-req", repo, head,
               {"reason": "sim", "recorded_by": "claude"})
    dec = _decision(root, repo, head, cfg)
    assert not dec.auto_approve
    assert any("consecutive autonomous failures" in r for r in dec.reasons)
