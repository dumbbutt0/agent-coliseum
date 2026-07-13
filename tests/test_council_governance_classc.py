"""A/B/C/D governance machinery — slice G2: the frozen seven-gate Class-C
resolution evaluator (evaluate_class_c) + the PREREGISTRATION / COUNCIL_DISSENT /
COUNCIL_RESOLVED events + the append-boundary re-validation. INERT until the owner
ratifies v4. Every test proves a fail-closed gate: the resolution authority is
re-derived from the VERIFIED chain (preregistration + codex-approved evidence +
dissent are chain events; the builder's resolution payload is re-checked, never
trusted); insufficient auditor quorum leaves a matter UNRESOLVED, never escalated
to the owner."""
import json
import os

import pytest

from tests.council_util import (append, make_cfg, make_repo, make_root,
                                make_verdict, drive_to_claimed)
from tools.council import (checkpoint, events, policy, storage)
from tools.council.schemas import (compute_preregistration_hash,
                                   compute_resolution_hash, CouncilError)

CONTROL_RID = "council-control"
MATTER = "classc-matter-001"


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


# ------------------------------------------------------------- synthetic chain

def _prereg(eid, *, matter=MATTER, metric="obedience_rate", min_n=10,
            freshness="post_prereg_generation", sealed=None):
    p = {"matter_id": matter, "question": "does X hold?",
         "decision_criteria": "accept iff gates pass", "precommitted_metric": metric,
         "metric_version": "1", "min_sample_size": min_n,
         "freshness_mode": freshness}
    if sealed is not None:
        p["sealed_inventory_hashes"] = sealed
    p["preregistration_hash"] = compute_preregistration_hash(p)
    return {"event_id": eid, "event_type": "PREREGISTRATION", "sender": "claude",
            "request_id": matter, "target_commit": "0" * 40, "payload": p}


def _evidence(eid, *, exp_hash, sender="codex", replay="replayed_ok",
              scenarios=6, inv_hash=None):
    return {"event_id": eid, "event_type": "RESULT_APPROVED", "sender": sender,
            "request_id": "exp-" + exp_hash[:6], "target_commit": "0" * 40,
            "payload": {"experiment_config_hash": exp_hash,
                        "evidence_inventory_hash": inv_hash or ("inv-" + exp_hash),
                        "replay_result": replay,
                        "counts": {"scenarios_run": scenarios,
                                   "validations_passed": scenarios,
                                   "validations_failed": 0}}}


def _dissent(eid, *, matter=MATTER, reconciled=False):
    return {"event_id": eid, "event_type": "COUNCIL_DISSENT", "sender": "codex",
            "request_id": matter, "target_commit": "0" * 40,
            "payload": {"matter_id": matter, "dissent": "concern", "reconciled": reconciled}}


def _resolution(*, matter=MATTER, prereg_id="900001-prereg", metric="obedience_rate",
                sample=12, evidence_ids=("900002-eva", "900003-evb")):
    p = {"matter_id": matter, "preregistration_event_id": prereg_id,
         "resolution": "accept", "metric": metric, "sample_size": sample,
         "evidence_approval_event_ids": list(evidence_ids)}
    p["resolution_hash"] = compute_resolution_hash(p)
    return {"event_id": "900099-res", "event_type": "COUNCIL_RESOLVED",
            "sender": "claude", "request_id": matter, "target_commit": "0" * 40,
            "payload": p}


def _chain(root, *synthetic):
    return events.read_chain(root, verify=False) + list(synthetic)


def _eval(root, cfg, resolution, *synthetic):
    return policy.evaluate_class_c(root, cfg, resolution, _chain(root, *synthetic))


def _valid_setup():
    prereg = _prereg("900001-prereg")
    ev1 = _evidence("900002-eva", exp_hash="a" * 12)
    ev2 = _evidence("900003-evb", exp_hash="b" * 12)
    res = _resolution()
    return prereg, ev1, ev2, res


# ------------------------------------------------------------- full pass / inert

def test_full_pass_resolves(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    prereg, ev1, ev2, res = _valid_setup()
    d = _eval(root, cfg, res, prereg, ev1, ev2)
    assert d.auto_approve, d.reasons
    for g in ("governance_active", "preregistration_present",
              "independent_auditor_approval", "reproducibility_replay",
              "independent_replication_2plus", "preregistration_and_freshness",
              "evidence_adequacy", "metric_validity", "recorded_dissent_consensus"):
        assert g in d.checked


def test_inert_under_v3(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 3)
    prereg, ev1, ev2, res = _valid_setup()
    d = _eval(root, cfg, res, prereg, ev1, ev2)
    assert not d.auto_approve
    assert any("governance_active" in r for r in d.reasons)


# ------------------------------------------------------------- per-gate fail-closed

def test_missing_preregistration_fails(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    _p, ev1, ev2, res = _valid_setup()
    d = _eval(root, cfg, res, ev1, ev2)          # no prereg in chain
    assert not d.auto_approve
    assert any("preregistration_present" in r for r in d.reasons)


def test_fewer_than_two_experiments_fails(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    prereg = _prereg("900001-prereg")
    ev1 = _evidence("900002-eva", exp_hash="a" * 12)
    ev2 = _evidence("900003-evb", exp_hash="a" * 12)   # SAME experiment hash
    d = _eval(root, cfg, _resolution(), prereg, ev1, ev2)
    assert not d.auto_approve
    assert any("independent_replication_2plus" in r for r in d.reasons)


def test_replay_not_ok_fails(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    prereg = _prereg("900001-prereg")
    ev1 = _evidence("900002-eva", exp_hash="a" * 12, replay="replay_failed")
    ev2 = _evidence("900003-evb", exp_hash="b" * 12)
    d = _eval(root, cfg, _resolution(), prereg, ev1, ev2)
    assert not d.auto_approve
    assert any("reproducibility_replay" in r for r in d.reasons)


def test_non_codex_evidence_fails(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    prereg = _prereg("900001-prereg")
    ev1 = _evidence("900002-eva", exp_hash="a" * 12, sender="claude")  # self-audit
    ev2 = _evidence("900003-evb", exp_hash="b" * 12)
    d = _eval(root, cfg, _resolution(), prereg, ev1, ev2)
    assert not d.auto_approve
    assert any("independent_auditor_approval" in r for r in d.reasons)


def test_evidence_predating_preregistration_fails(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    ev_early = _evidence("900000-evearly", exp_hash="a" * 12)
    prereg = _prereg("900001-prereg")
    ev2 = _evidence("900003-evb", exp_hash="b" * 12)
    res = _resolution(evidence_ids=("900000-evearly", "900003-evb"))
    d = _eval(root, cfg, res, ev_early, prereg, ev2)   # ev_early BEFORE prereg
    assert not d.auto_approve
    assert any("preregistration_and_freshness" in r for r in d.reasons)


def test_sealed_inventory_freshness(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    ev1 = _evidence("900002-eva", exp_hash="a" * 12, inv_hash="sealed-a")
    ev2 = _evidence("900003-evb", exp_hash="b" * 12, inv_hash="sealed-b")
    good = _prereg("900001-prereg", freshness="sealed_inventory",
                   sealed=["sealed-a", "sealed-b"])
    assert _eval(root, cfg, _resolution(), good, ev1, ev2).auto_approve
    bad = _prereg("900001-prereg", freshness="sealed_inventory",
                  sealed=["sealed-a"])              # ev2 inventory not sealed
    d = _eval(root, cfg, _resolution(), bad, ev1, ev2)
    assert not d.auto_approve
    assert any("preregistration_and_freshness" in r for r in d.reasons)


def test_insufficient_sample_size_fails(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    prereg = _prereg("900001-prereg", min_n=100)
    ev1 = _evidence("900002-eva", exp_hash="a" * 12, scenarios=3)
    ev2 = _evidence("900003-evb", exp_hash="b" * 12, scenarios=3)
    d = _eval(root, cfg, _resolution(), prereg, ev1, ev2)
    assert not d.auto_approve
    assert any("evidence_adequacy" in r for r in d.reasons)


def test_post_hoc_metric_switch_fails(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    prereg = _prereg("900001-prereg", metric="obedience_rate")
    ev1 = _evidence("900002-eva", exp_hash="a" * 12)
    ev2 = _evidence("900003-evb", exp_hash="b" * 12)
    res = _resolution(metric="refusal_rate")        # switched after preregistration
    d = _eval(root, cfg, res, prereg, ev1, ev2)
    assert not d.auto_approve
    assert any("metric_validity" in r for r in d.reasons)


def test_unreconciled_dissent_blocks(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    prereg, ev1, ev2, res = _valid_setup()
    d = _eval(root, cfg, res, prereg, ev1, ev2, _dissent("900050-dis"))
    assert not d.auto_approve
    assert any("recorded_dissent_consensus" in r for r in d.reasons)
    # a reconciled dissent does NOT block
    d2 = _eval(root, cfg, res, prereg, ev1, ev2,
               _dissent("900050-dis", reconciled=True))
    assert d2.auto_approve, d2.reasons


def test_resolution_hash_tamper_fails(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    prereg, ev1, ev2, res = _valid_setup()
    res["payload"]["resolution"] = "reject"          # mutate without re-hashing
    d = _eval(root, cfg, res, prereg, ev1, ev2)
    assert not d.auto_approve
    assert any("resolution_payload_bound" in r for r in d.reasons)


def test_already_resolved_matter_fails(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    prereg, ev1, ev2, res = _valid_setup()
    prior = {"event_id": "900098-prior", "event_type": "COUNCIL_RESOLVED",
             "sender": "claude", "request_id": MATTER, "target_commit": "0" * 40,
             "payload": {"matter_id": MATTER}}
    d = _eval(root, cfg, res, prereg, ev1, ev2, prior)
    assert not d.auto_approve
    assert any("matter_not_already_resolved" in r for r in d.reasons)


# ------------------------------------------------ append-boundary integration

def test_append_boundary_refuses_council_resolved_when_inert(env):
    """Under the live v3 pin, a COUNCIL_RESOLVED append is refused by
    _verify_class_c_resolution (governance inactive) — a bare claude sender is never
    sufficient; the matter stays UNRESOLVED."""
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 3)               # governance INERT
    # a real PREREGISTRATION (stateless) appends fine
    p = _prereg("ignored")["payload"]
    append(root, cfg, "PREREGISTRATION", "claude", MATTER, repo, head, p)
    res = _resolution()["payload"]
    with pytest.raises(CouncilError, match="Class-C protocol"):
        append(root, cfg, "COUNCIL_RESOLVED", "claude", MATTER, repo, head, res)
