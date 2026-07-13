"""Governance G3 — the GENERIC acceptance authorization (tools/council). It reports
whether a Class-C matter is RESOLVED (authorizing an `accepted` transition): a valid
gate-passing COUNCIL_RESOLVED on the SELF-VERIFIED root chain, governance active. It
performs no project mutation and encodes no claim states — a project adapter reads
the decision. INERT under v3."""
import json

import pytest

from tests.council_util import (_inject_test_bindings, append, drive_to_claimed,
                                make_cfg, make_repo, make_root, make_verdict)
from tools.council import checkpoint, events, policy, storage
from tools.council.schemas import (compute_preregistration_hash,
                                   compute_resolution_hash)

CONTROL_RID = "council-control"
MATTER = "classc-accept-001"


def _provision_checkpoint(root):
    cp = checkpoint.render_checkpoint(events.read_chain(root))
    with open(checkpoint.CHECKPOINT_FILE, "w", encoding="utf-8") as fh:
        json.dump(cp, fh)


def _amend(root, repo, head, cfg, target):
    ph, nh, diff = policy.amend_policy(root, target)
    append(root, cfg, "POLICY_AMENDED", "human", CONTROL_RID, repo, head,
           {"policy_hash": nh, "prev_policy_hash": ph, "policy_version": target,
            "policy_diff": diff, "impl_commit": head, "policy_file": storage.POLICY_FILE})


@pytest.fixture()
def env(tmp_path):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    policy.write_initial_policy(root)
    _p, v1 = policy.load_policy(root)
    append(root, cfg, "POLICY_INITIALIZED", "human", CONTROL_RID, repo, "0" * 40,
           {"policy_hash": v1, "policy_file": storage.POLICY_FILE})
    _provision_checkpoint(root)
    return root, repo, head, cfg


def _ratify(root, repo, head, cfg, upto):
    for t in range(2, upto + 1):
        _amend(root, repo, head, cfg, t)


def _evidence(root, repo, head, cfg, rid):
    drive_to_claimed(root, cfg, repo, head, request_id=rid)
    for et, snd in [("AUDIT_GO", "codex"), ("HUMAN_APPROVAL_REQUIRED", "claude"),
                    ("EXPERIMENT_APPROVED", "human"), ("EXPERIMENT_STARTED", "claude"),
                    ("EXPERIMENT_COMPLETE", "claude"),
                    ("RESULT_VALIDATION_REQUIRED", "claude"),
                    ("RESULT_AUDIT_REQUESTED", "claude")]:
        append(root, cfg, et, snd, rid, repo, head)
    return append(root, cfg, "RESULT_APPROVED", "codex", rid, repo, head)["event_id"]


def _resolve(root, repo, head, cfg, *, resolution="accept"):
    p = {"matter_id": MATTER, "question": "q", "decision_criteria": "c",
         "precommitted_metric": "obedience_rate", "metric_version": "1",
         "min_sample_size": 2, "freshness_mode": "post_prereg_generation"}
    p["preregistration_hash"] = compute_preregistration_hash(p)
    prereg_id = append(root, cfg, "PREREGISTRATION", "claude", MATTER, repo, head,
                       p)["event_id"]
    e1 = _evidence(root, repo, head, cfg, "exp-aa")
    e2 = _evidence(root, repo, head, cfg, "exp-bb")
    r = {"matter_id": MATTER, "preregistration_event_id": prereg_id,
         "resolution": resolution, "metric": "obedience_rate", "sample_size": 2,
         "evidence_approval_event_ids": [e1, e2]}
    r["resolution_hash"] = compute_resolution_hash(r)
    append(root, cfg, "COUNCIL_RESOLVED", "claude", MATTER, repo, head, r)


def test_authorized_after_valid_resolution(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    _resolve(root, repo, head, cfg, resolution="accept")
    a = policy.acceptance_authorization(root, cfg, MATTER)
    assert a.authorized and a.resolution == "accept"
    assert a.resolved_event_id is not None


def test_reject_resolution_is_reported_not_accept(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    _resolve(root, repo, head, cfg, resolution="reject")
    a = policy.acceptance_authorization(root, cfg, MATTER)
    # a resolution EXISTS (authorized=True) but the resolution is not "accept" —
    # the generic core reports it; the adapter refuses to promote.
    assert a.authorized and a.resolution == "reject"


def test_no_resolution_is_not_authorized(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    a = policy.acceptance_authorization(root, cfg, MATTER)
    assert not a.authorized
    assert any("no COUNCIL_RESOLVED" in r for r in a.reasons)


def test_inert_under_v3(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 3)
    a = policy.acceptance_authorization(root, cfg, MATTER)
    assert not a.authorized
    assert any("governance not active" in r for r in a.reasons)


def test_unreadable_policy_fails_closed(tmp_path):
    """A policy read error (here: the policy path is a directory) must return
    not-authorized, never raise (audit 000747 HIGH)."""
    import os
    from tools.council import Config, storage
    root = str(tmp_path / "badroot")
    os.makedirs(root)
    os.makedirs(storage.policy_path(root))        # autonomy_policy.json is a dir
    cfg = Config(council_root=root, repo_roots=(root,), role="claude")
    a = policy.acceptance_authorization(root, cfg, "classc-x")   # must not raise
    assert not a.authorized
    assert any("unreadable" in r or "invalid" in r for r in a.reasons)
