"""Governance G4 — the GENERIC durable acceptance continuation (tools/council).
`continuation_status` is the self-authenticating resumability oracle; a MATTER_ACCEPTED
is the exactly-once, chain-anchored record admitted ONLY by
`policy.evaluate_matter_accepted` at the append boundary (authorized-under-governance +
accept resolution + bound resolved_event_id + no prior record). It performs no project
mutation and encodes no claim states. INERT under v3."""
import pytest

from tests.council_util import (append, drive_to_claimed, make_cfg, make_repo,
                                make_root)
from tools.council import checkpoint, events, policy, storage
from tools.council.schemas import (CouncilError, compute_preregistration_hash,
                                   compute_resolution_hash)

CONTROL_RID = "council-control"
MATTER = "classc-accept-001"


def _provision_checkpoint(root):
    import json
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
    return append(root, cfg, "COUNCIL_RESOLVED", "claude", MATTER, repo, head,
                  r)["event_id"]


def _record_accepted(root, repo, head, cfg, resolved_id, *, subject="c1",
                     result_hash="deadbeef"):
    payload = {"matter_id": MATTER, "resolved_event_id": resolved_id,
               "subject_ref": subject, "result_content_hash": result_hash}
    return append(root, cfg, "MATTER_ACCEPTED", "claude", MATTER, repo, head, payload)


# ----------------------------------------------------------- continuation_status

def test_status_authorized_not_yet_accepted(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    rid = _resolve(root, repo, head, cfg, resolution="accept")
    s = policy.continuation_status(root, cfg, MATTER)
    assert s.authorized and s.is_accept and s.resolved_event_id == rid
    assert not s.already_accepted and s.accepted_event_id is None


def test_status_inert_under_v3(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 3)
    s = policy.continuation_status(root, cfg, MATTER)
    assert not s.authorized and not s.already_accepted
    assert any("governance not active" in r for r in s.reasons)


# ----------------------------------------- MATTER_ACCEPTED append-boundary authority

def test_matter_accepted_admitted_after_resolution(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    rid = _resolve(root, repo, head, cfg, resolution="accept")
    ev = _record_accepted(root, repo, head, cfg, rid)
    assert ev["event_type"] == "MATTER_ACCEPTED"
    s = policy.continuation_status(root, cfg, MATTER)
    assert s.already_accepted and s.accepted_event_id == ev["event_id"]
    assert s.subject_ref == "c1" and s.result_content_hash == "deadbeef"


def test_matter_accepted_exactly_once(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    rid = _resolve(root, repo, head, cfg, resolution="accept")
    _record_accepted(root, repo, head, cfg, rid)
    with pytest.raises(CouncilError) as ei:
        _record_accepted(root, repo, head, cfg, rid)   # second record forbidden
    assert "exactly-once" in str(ei.value) or "already has a MATTER_ACCEPTED" \
        in str(ei.value)


def test_matter_accepted_inert_under_v3(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 3)   # no COUNCIL_RESOLVED can exist under v3
    with pytest.raises(CouncilError) as ei:
        _record_accepted(root, repo, head, cfg, "000999-none")
    assert "not authorized" in str(ei.value)


def test_matter_accepted_requires_bound_resolved_event_id(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    _resolve(root, repo, head, cfg, resolution="accept")
    with pytest.raises(CouncilError) as ei:
        _record_accepted(root, repo, head, cfg, "000001-wrong")
    assert "does not bind" in str(ei.value)


def test_matter_accepted_refused_when_resolution_not_accept(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    rid = _resolve(root, repo, head, cfg, resolution="reject")
    s = policy.continuation_status(root, cfg, MATTER)
    assert s.authorized and not s.is_accept   # authorized, but not an accept verdict
    with pytest.raises(CouncilError) as ei:
        _record_accepted(root, repo, head, cfg, rid)
    assert "not 'accept'" in str(ei.value)
