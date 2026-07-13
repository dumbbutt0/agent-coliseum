"""A/B/C/D governance machinery — slice G1: the routing core (matter_class +
governance_route + governance_v1 policy version). INERT until the owner ratifies
v4; dormant under v1-v3. Every test proves a fail-closed boundary: the auditor —
not Claude — emits the hash-bound matter_class; an absent/invalid class routes to
D; and DEFLATION is caught — a D-touching change can never buy Class-A/B/C
authority (the anti-self-expansion invariant, enforced against the audited commit's
real diff)."""
import json
import os
import subprocess

import pytest

from tests.council_util import (append, make_cfg, make_repo, make_request,
                                make_root, make_verdict)
from tools.council import checkpoint, events, policy, storage
from tools.council.schemas import compute_verdict_payload_hash

RID = "gov-req-001"
CONTROL_RID = "council-control"


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
    return new_hash


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


def _ratify_v4(root, repo, head, cfg):
    for target in (2, 3, 4):
        _amend(root, repo, head, cfg, target)
    assert policy.effective_policy_pin(events.read_chain(root))[1] == 4


def _request(repo, head, **ov):
    return make_request(repo, head, RID, task_kind="source", **ov)


def _verdict_event(head, matter_class=None, *, event_type="AUDIT_GO",
                   sender="codex"):
    verdict = make_verdict(head, request_id=RID, verdict="GO")
    if matter_class is not None:
        verdict["matter_class"] = matter_class
    verdict["verdict_payload_hash"] = compute_verdict_payload_hash(verdict)
    return {"event_id": "000099-testtest", "event_type": event_type,
            "sender": sender, "request_id": RID, "payload": verdict,
            "target_commit": head}


def _route(root, cfg, request, verdict_event):
    return policy.governance_route(root, cfg, request, verdict_event,
                                   events.read_chain(root))


# ------------------------------------------------------------ version ladder

def test_ladder_is_additive_and_code_defined():
    v3, v4, v5 = (policy.POLICY_VERSIONS[i] for i in (3, 4, 5))
    # v4 = v3 + governance, delegation STILL enabled; v5 = forward revocation
    assert v3["owner_delegation"]["enabled"] is True and "governance" not in v3
    assert v4["owner_delegation"]["enabled"] is True and "governance" in v4
    assert v4["amends"] == 3 and v5["amends"] == 4
    assert v5["owner_delegation"]["enabled"] is False and "governance" in v5
    for v in (4, 5):
        assert policy.is_code_defined_version(dict(policy.POLICY_VERSIONS[v]))
    gov = v4["governance"]
    assert gov["enabled"] and gov["classes"] == ["A", "B", "C", "D"]
    assert len(gov["class_d_reserved"]) == 6 and len(gov["class_c_gates"]) == 7
    assert gov["required_auditors"] == ["codex"]
    assert gov["unclassified_routes_to"] == "D"


# ------------------------------------------------------------- dormant (v1-v3)

def test_governance_dormant_before_ratification(env):
    root, repo, head, cfg = env                    # pinned at v1
    d = _route(root, cfg, _request(repo, head), _verdict_event(head, "A"))
    assert not d.active and d.route == "owner"


def test_governance_dormant_under_v3(env):
    root, repo, head, cfg = env
    for t in (2, 3):
        _amend(root, repo, head, cfg, t)
    d = _route(root, cfg, _request(repo, head), _verdict_event(head, "A"))
    assert not d.active and d.route == "owner"


# ------------------------------------------------- routing (active under v4)

@pytest.mark.parametrize("cls,route", [("A", "delegation"), ("B", "codex_lifecycle"),
                                       ("C", "council"), ("D", "owner")])
def test_routes_by_matter_class(env, cls, route):
    root, repo, head, cfg = env
    _ratify_v4(root, repo, head, cfg)
    d = _route(root, cfg, _request(repo, head), _verdict_event(head, cls))
    assert d.active and d.matter_class == cls and d.route == route
    assert d.declared_class == cls


# ----------------------------------------------------- fail-closed to D

def test_absent_matter_class_routes_to_d(env):
    root, repo, head, cfg = env
    _ratify_v4(root, repo, head, cfg)
    d = _route(root, cfg, _request(repo, head), _verdict_event(head, None))
    assert d.active and d.matter_class == "D" and d.route == "owner"
    assert d.declared_class is None
    assert any("matter_class" in r for r in d.reasons)


def test_non_codex_verdict_still_routes_by_bound_class(env):
    # matter_class is hash-bound in the verdict; even a non-codex sender's forged
    # verdict cannot present a class it did not author without breaking the hash
    # (schema). Here we assert the router reads the payload class deterministically.
    root, repo, head, cfg = env
    _ratify_v4(root, repo, head, cfg)
    d = _route(root, cfg, _request(repo, head),
               _verdict_event(head, "C", sender="claude"))
    assert d.matter_class == "C"       # routing is by the bound field, not sender


# --------------------------------- anti-deflation (the self-expansion guard)

def _repo_touching_protected(tmp_path, name="govprot"):
    repo = str(tmp_path / name)
    os.makedirs(os.path.join(repo, "tools", "council"), exist_ok=True)
    subprocess.run(["git", "-C", repo, "init", "-q"], check=True)
    with open(os.path.join(repo, "f.txt"), "w") as fh:
        fh.write("base\n")
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    subprocess.run(["git", "-C", repo, "-c", "user.email=t@t", "-c",
                    "user.name=t", "commit", "-qm", "base"], check=True)
    with open(os.path.join(repo, "tools", "council", "policy.py"), "w") as fh:
        fh.write("# smuggled protocol change\n")
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    subprocess.run(["git", "-C", repo, "-c", "user.email=t@t", "-c",
                    "user.name=t", "commit", "-qm", "touch protected"], check=True)
    head = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    return repo, head


def test_protected_path_change_forced_to_d_despite_label(env, tmp_path):
    # a Class-A label on a commit that ACTUALLY changes tools/council/* is forced to
    # D — deflation cannot buy autonomous authority for a protocol self-modification
    root, _r0, _h0, cfg0 = env
    _ratify_v4(root, _r0, _h0, cfg0)
    repo, head = _repo_touching_protected(tmp_path)
    cfg = make_cfg(repo, root)
    request = make_request(repo, head, RID, task_kind="source",
                           scope=["benign refactor"])
    d = policy.governance_route(root, cfg, request, _verdict_event(head, "A"),
                                events.read_chain(root))
    assert d.matter_class == "D" and d.route == "owner"
    assert any("protected paths" in r for r in d.reasons)


def test_undeclared_reserved_capability_forced_to_d(env):
    root, repo, head, cfg = env
    _ratify_v4(root, repo, head, cfg)
    d = _route(root, cfg,
               _request(repo, head, forbidden_actions=["destructive_tools"]),
               _verdict_event(head, "B"))
    assert d.matter_class == "D"
    assert any("reserved capabilities" in r for r in d.reasons)


def test_unverifiable_diff_fails_closed_to_d(env, tmp_path):
    root, repo, head, cfg = env
    _ratify_v4(root, repo, head, cfg)
    # a request pointing at a non-existent commit cannot have its diff verified -> D
    bad = make_request(repo, "d" * 40, RID, task_kind="source")
    d = policy.governance_route(root, cfg, bad, _verdict_event("d" * 40, "A"),
                                events.read_chain(root))
    assert d.matter_class == "D"
    assert any("changed paths" in r for r in d.reasons)


# ----------------------------------------- matter_class is codex-authored/bound

def test_matter_class_is_payload_hash_bound():
    # changing the class changes the verdict_payload_hash — a builder cannot alter
    # the auditor's classification without invalidating the hash the chain checks
    a = make_verdict("a" * 40, RID, verdict="GO"); a["matter_class"] = "A"
    b = make_verdict("a" * 40, RID, verdict="GO"); b["matter_class"] = "D"
    assert compute_verdict_payload_hash(a) != compute_verdict_payload_hash(b)
