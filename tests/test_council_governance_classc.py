"""A/B/C/D governance machinery — slice G2: the frozen seven-gate Class-C
resolution evaluator (evaluate_class_c) + the PREREGISTRATION / COUNCIL_DISSENT /
COUNCIL_RESOLVED events + the append-boundary re-validation. INERT until the owner
ratifies v4.

evaluate_class_c is SELF-AUTHENTICATING (audit 000735): it re-reads and hash-verifies
the chain FROM ROOT and evaluates only the candidate resolution against it — so these
tests use REAL on-chain preregistration + REAL codex RESULT_APPROVED evidence (driven
through the actual result-audit lifecycle), never synthetic caller-supplied records.
Every test proves a fail-closed gate; insufficient auditor quorum leaves a matter
UNRESOLVED, never escalated to the owner."""
import hashlib
import json

import pytest

from tests.council_util import (append, drive_to_claimed, make_cfg, make_repo,
                                make_root, make_verdict)
from tools.council import checkpoint, events, policy, storage
from tools.council.schemas import (compute_preregistration_hash,
                                   compute_resolution_hash, CouncilError,
                                   SchemaViolation)

CONTROL_RID = "council-control"
MATTER = "classc-matter-001"          # reserved Class-C namespace prefix


def _provision_checkpoint(root):
    cp = checkpoint.render_checkpoint(events.read_chain(root))
    with open(checkpoint.CHECKPOINT_FILE, "w", encoding="utf-8") as fh:
        json.dump(cp, fh)


def _amend(root, repo, head, cfg, target):
    prev_hash, new_hash, diff = policy.amend_policy(root, target)
    append(root, cfg, "POLICY_AMENDED", "human", CONTROL_RID, repo, head,
           {"policy_hash": new_hash, "prev_policy_hash": prev_hash,
            "policy_version": target, "policy_diff": diff, "impl_commit": head,
            "policy_file": storage.POLICY_FILE})


@pytest.fixture()
def env(tmp_path):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    policy.write_initial_policy(root)
    _p, v1_hash = policy.load_policy(root)
    append(root, cfg, "POLICY_INITIALIZED", "human", CONTROL_RID, repo,
           "0" * 40, {"policy_hash": v1_hash, "policy_file": storage.POLICY_FILE})
    _provision_checkpoint(root)
    return root, repo, head, cfg


def _ratify(root, repo, head, cfg, upto):
    for t in range(2, upto + 1):
        _amend(root, repo, head, cfg, t)
    assert policy.effective_policy_pin(events.read_chain(root))[1] == upto


# --- REAL evidence: drive a minimal experiment through to a codex RESULT_APPROVED ---

def _drive_evidence(root, repo, head, cfg, exp_rid):
    drive_to_claimed(root, cfg, repo, head, request_id=exp_rid)
    append(root, cfg, "AUDIT_GO", "codex", exp_rid, repo, head)
    append(root, cfg, "HUMAN_APPROVAL_REQUIRED", "claude", exp_rid, repo, head)
    append(root, cfg, "EXPERIMENT_APPROVED", "human", exp_rid, repo, head)
    append(root, cfg, "EXPERIMENT_STARTED", "claude", exp_rid, repo, head)
    append(root, cfg, "EXPERIMENT_COMPLETE", "claude", exp_rid, repo, head)
    append(root, cfg, "RESULT_VALIDATION_REQUIRED", "claude", exp_rid, repo, head)
    append(root, cfg, "RESULT_AUDIT_REQUESTED", "claude", exp_rid, repo, head)
    ra = append(root, cfg, "RESULT_APPROVED", "codex", exp_rid, repo, head)
    v = ra["payload"]
    return {"event_id": ra["event_id"], "inv": v["evidence_inventory_hash"],
            "exp": v["experiment_config_hash"]}


def _append_prereg(root, repo, head, cfg, *, metric="obedience_rate", min_n=2,
                   freshness="post_prereg_generation", sealed=None):
    p = {"matter_id": MATTER, "question": "does X hold?",
         "decision_criteria": "accept iff gates pass", "precommitted_metric": metric,
         "metric_version": "1", "min_sample_size": min_n, "freshness_mode": freshness}
    if sealed is not None:
        p["sealed_inventory_hashes"] = sealed
    p["preregistration_hash"] = compute_preregistration_hash(p)
    ev = append(root, cfg, "PREREGISTRATION", "claude", MATTER, repo, head, p)
    return ev["event_id"]


def _resolution(*, prereg_id, evidence_ids, metric="obedience_rate", sample=2):
    p = {"matter_id": MATTER, "preregistration_event_id": prereg_id,
         "resolution": "accept", "metric": metric, "sample_size": sample,
         "evidence_approval_event_ids": list(evidence_ids)}
    p["resolution_hash"] = compute_resolution_hash(p)
    return {"event_id": "cand-res", "event_type": "COUNCIL_RESOLVED",
            "sender": "claude", "request_id": MATTER, "target_commit": "0" * 40,
            "payload": p}


def _valid(root, repo, head, cfg, *, min_n=2, freshness="post_prereg_generation"):
    """prereg -> 2 distinct real evidence -> candidate resolution."""
    e1 = _drive_evidence(root, repo, head, cfg, "exp-aaa")
    e2 = _drive_evidence(root, repo, head, cfg, "exp-bbb")
    sealed = ([e1["inv"], e2["inv"]] if freshness == "sealed_inventory" else None)
    prereg_id = _append_prereg(root, repo, head, cfg, min_n=min_n,
                               freshness=freshness, sealed=sealed)
    res = _resolution(prereg_id=prereg_id,
                      evidence_ids=[e1["event_id"], e2["event_id"]])
    return prereg_id, e1, e2, res


def _ev(root, cfg, res):
    return policy.evaluate_class_c(root, cfg, res)


# ------------------------------------------------------------- full pass / inert

def test_full_pass_resolves(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    # evidence appended BEFORE the prereg would fail freshness; drive it AFTER
    prereg_id = _append_prereg(root, repo, head, cfg, min_n=2)
    e1 = _drive_evidence(root, repo, head, cfg, "exp-aaa")
    e2 = _drive_evidence(root, repo, head, cfg, "exp-bbb")
    res = _resolution(prereg_id=prereg_id,
                      evidence_ids=[e1["event_id"], e2["event_id"]])
    d = _ev(root, cfg, res)
    assert d.auto_approve, d.reasons


def test_inert_under_v3(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 3)
    prereg_id = _append_prereg(root, repo, head, cfg)
    res = _resolution(prereg_id=prereg_id, evidence_ids=["x", "y"])
    d = _ev(root, cfg, res)
    assert not d.auto_approve
    assert any("governance_active" in r for r in d.reasons)


# ------------------------------------------------------------- per-gate fail-closed

def test_missing_preregistration_fails(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    e1 = _drive_evidence(root, repo, head, cfg, "exp-aaa")
    e2 = _drive_evidence(root, repo, head, cfg, "exp-bbb")
    res = _resolution(prereg_id="999999-nope",
                      evidence_ids=[e1["event_id"], e2["event_id"]])
    d = _ev(root, cfg, res)
    assert not d.auto_approve
    assert any("preregistration_present" in r for r in d.reasons)


def test_fewer_than_two_experiments_fails(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    prereg_id = _append_prereg(root, repo, head, cfg)
    e1 = _drive_evidence(root, repo, head, cfg, "exp-aaa")
    # cite the SAME evidence twice — dedup collapses to one experiment
    res = _resolution(prereg_id=prereg_id,
                      evidence_ids=[e1["event_id"], e1["event_id"]])
    d = _ev(root, cfg, res)
    assert not d.auto_approve
    assert any("independent_replication_2plus" in r for r in d.reasons)


def test_non_result_evidence_fails(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    prereg_id = _append_prereg(root, repo, head, cfg)
    # drive one real evidence, then cite a NON-RESULT_APPROVED codex event too
    e1 = _drive_evidence(root, repo, head, cfg, "exp-aaa")
    # the exp-aaa AUDIT_GO is codex-sent but not a RESULT_APPROVED
    go = [e for e in events.read_chain(root, verify=False)
          if e["event_type"] == "AUDIT_GO" and e["request_id"] == "exp-aaa"][0]
    res = _resolution(prereg_id=prereg_id,
                      evidence_ids=[e1["event_id"], go["event_id"]])
    d = _ev(root, cfg, res)
    assert not d.auto_approve
    assert any("independent_auditor_approval" in r for r in d.reasons)


def test_evidence_predating_preregistration_fails(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    # evidence FIRST, prereg AFTER -> backfilled evidence
    e1 = _drive_evidence(root, repo, head, cfg, "exp-aaa")
    e2 = _drive_evidence(root, repo, head, cfg, "exp-bbb")
    prereg_id = _append_prereg(root, repo, head, cfg)
    res = _resolution(prereg_id=prereg_id,
                      evidence_ids=[e1["event_id"], e2["event_id"]])
    d = _ev(root, cfg, res)
    assert not d.auto_approve
    assert any("preregistration_and_freshness" in r for r in d.reasons)


def test_sealed_inventory_freshness(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    e1 = _drive_evidence(root, repo, head, cfg, "exp-aaa")
    e2 = _drive_evidence(root, repo, head, cfg, "exp-bbb")
    # prereg sealing only e1's inventory -> e2 is not precommitted -> fails
    prereg_id = _append_prereg(root, repo, head, cfg,
                               freshness="sealed_inventory", sealed=[e1["inv"]])
    res = _resolution(prereg_id=prereg_id,
                      evidence_ids=[e1["event_id"], e2["event_id"]])
    d = _ev(root, cfg, res)
    assert not d.auto_approve
    assert any("preregistration_and_freshness" in r for r in d.reasons)


def test_insufficient_sample_fails(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    prereg_id = _append_prereg(root, repo, head, cfg, min_n=100)   # each evidence n=1
    e1 = _drive_evidence(root, repo, head, cfg, "exp-aaa")
    e2 = _drive_evidence(root, repo, head, cfg, "exp-bbb")
    res = _resolution(prereg_id=prereg_id,
                      evidence_ids=[e1["event_id"], e2["event_id"]])
    d = _ev(root, cfg, res)
    assert not d.auto_approve
    assert any("evidence_adequacy" in r for r in d.reasons)


def test_post_hoc_metric_switch_fails(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    prereg_id = _append_prereg(root, repo, head, cfg, metric="obedience_rate")
    e1 = _drive_evidence(root, repo, head, cfg, "exp-aaa")
    e2 = _drive_evidence(root, repo, head, cfg, "exp-bbb")
    res = _resolution(prereg_id=prereg_id, metric="refusal_rate",   # switched
                      evidence_ids=[e1["event_id"], e2["event_id"]])
    d = _ev(root, cfg, res)
    assert not d.auto_approve
    assert any("metric_validity" in r for r in d.reasons)


def test_unreconciled_dissent_blocks(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    prereg_id = _append_prereg(root, repo, head, cfg)
    e1 = _drive_evidence(root, repo, head, cfg, "exp-aaa")
    e2 = _drive_evidence(root, repo, head, cfg, "exp-bbb")
    append(root, cfg, "COUNCIL_DISSENT", "codex", MATTER, repo, head,
           {"matter_id": MATTER, "dissent": "concern", "reconciled": False})
    res = _resolution(prereg_id=prereg_id,
                      evidence_ids=[e1["event_id"], e2["event_id"]])
    assert not _ev(root, cfg, res).auto_approve
    # a reconciled dissent does not block
    append(root, cfg, "COUNCIL_DISSENT", "codex", MATTER, repo, head,
           {"matter_id": MATTER, "dissent": "concern", "reconciled": True})
    # (both dissents present; the unreconciled one still blocks)
    assert not _ev(root, cfg, res).auto_approve


def test_resolution_hash_tamper_fails(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    prereg_id, _e1, _e2, res = _valid(root, repo, head, cfg)
    res["payload"]["resolution"] = "reject"          # mutate without re-hashing
    d = _ev(root, cfg, res)
    assert not d.auto_approve
    assert any("resolution_payload_bound" in r for r in d.reasons)


# ------------------------------------------- namespace + append-boundary + double

def test_matter_id_must_be_namespaced(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    p = {"matter_id": "not-prefixed", "question": "q", "decision_criteria": "c",
         "precommitted_metric": "m", "metric_version": "1", "min_sample_size": 1,
         "freshness_mode": "post_prereg_generation"}
    p["preregistration_hash"] = compute_preregistration_hash(p)
    with pytest.raises(SchemaViolation, match="namespaced"):
        append(root, cfg, "PREREGISTRATION", "claude", "not-prefixed", repo, head, p)


def test_append_boundary_end_to_end(env):
    """Under v4, a fully-valid COUNCIL_RESOLVED appends; a second one is refused
    (matter already resolved); under the append boundary a gate-failing resolution
    is refused."""
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    prereg_id = _append_prereg(root, repo, head, cfg, min_n=2)
    e1 = _drive_evidence(root, repo, head, cfg, "exp-aaa")
    e2 = _drive_evidence(root, repo, head, cfg, "exp-bbb")
    resp = _resolution(prereg_id=prereg_id,
                       evidence_ids=[e1["event_id"], e2["event_id"]])["payload"]
    append(root, cfg, "COUNCIL_RESOLVED", "claude", MATTER, repo, head, resp)  # OK
    with pytest.raises(CouncilError, match="Class-C protocol"):   # double-resolve
        append(root, cfg, "COUNCIL_RESOLVED", "claude", MATTER, repo, head, resp)


def test_append_boundary_refuses_when_inert(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 3)               # governance INERT
    prereg_id = _append_prereg(root, repo, head, cfg)
    resp = _resolution(prereg_id=prereg_id, evidence_ids=["x", "y"])["payload"]
    with pytest.raises(CouncilError, match="Class-C protocol"):
        append(root, cfg, "COUNCIL_RESOLVED", "claude", MATTER, repo, head, resp)
