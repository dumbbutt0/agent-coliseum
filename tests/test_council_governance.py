"""A/B/C/D governance machinery — slice G1: the routing core (matter_class +
governance_route + governance_v1 policy version). INERT until the owner ratifies
v4; dormant under v1-v3. Every test proves a fail-closed boundary. governance_route
is SELF-AUTHENTICATING: it re-reads and hash-verifies the chain from root and
obtains the request through publish.verified_request (audit 000708) — it trusts NO
caller argument. The routing matter_class is the codex verdict in the verified chain
(hash-bound — Claude cannot forge it); an absent/invalid/unverifiable class, a
protected-path change, or any implicated Class-D predicate forces D."""
import json
import os
import subprocess

import pytest

from tests.council_util import (_inject_test_bindings, append, drive_to_claimed,
                                make_cfg, make_repo, make_request, make_root,
                                make_verdict)
from tools.council import checkpoint, events, policy, publish, storage
from tools.council.schemas import compute_verdict_payload_hash

RID = "gov-req-001"
CONTROL_RID = "council-control"

_D6 = list(policy.POLICY_VERSIONS[4]["governance"]["class_d_reserved"])
_LEGACY = ["destructive_tools", "cloud_apis", "website_automation", "weight_training"]
_FULL_FORBIDDEN = _D6 + _LEGACY


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
    for target in range(2, upto + 1):
        _amend(root, repo, head, cfg, target)
    assert policy.effective_policy_pin(events.read_chain(root))[1] == upto


def _publish_and_go(root, cfg, repo, head, matter_class, **req_ov):
    fields = dict(task_kind="source", forbidden_actions=list(_FULL_FORBIDDEN))
    fields.update(req_ov)
    ctx = drive_to_claimed(root, cfg, repo, head, request_id=RID, **fields)
    payload = make_verdict(head, RID, verdict="GO")
    if matter_class is not None:
        payload["matter_class"] = matter_class
    payload["schema_version"] = "source-verdict.v2"
    _inject_test_bindings(root, payload, RID, head, False)
    payload["verdict_payload_hash"] = compute_verdict_payload_hash(payload)
    append(root, cfg, "AUDIT_GO", "codex", RID, repo, head, payload)
    return ctx["request"]


def _route(root, cfg):
    return policy.governance_route(root, cfg, RID)


# ------------------------------------------------------------ version ladder

def test_ladder_is_additive_and_code_defined():
    v3, v4, v5 = (policy.POLICY_VERSIONS[i] for i in (3, 4, 5))
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
    root, _repo, _head, cfg = env                    # pinned at v1
    d = _route(root, cfg)
    assert not d.active and d.route == "owner"


def test_governance_dormant_under_v3(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 3)
    d = _route(root, cfg)
    assert not d.active and d.route == "owner"


# ------------------------------------------------- routing (active under v4)

@pytest.mark.parametrize("cls,route", [("A", "delegation"), ("B", "codex_lifecycle"),
                                       ("C", "council"), ("D", "owner")])
def test_routes_by_chain_matter_class(env, cls, route):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    _publish_and_go(root, cfg, repo, head, cls)
    d = _route(root, cfg)
    assert d.active and d.matter_class == cls and d.route == route
    assert d.declared_class == cls


# ----------------------------------------------------- fail-closed to D

def test_absent_matter_class_routes_to_d(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    _publish_and_go(root, cfg, repo, head, None)
    d = _route(root, cfg)
    assert d.active and d.matter_class == "D" and d.route == "owner"
    assert d.declared_class is None


def test_no_codex_verdict_routes_to_d(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    # publish + claim but NO verdict yet
    drive_to_claimed(root, cfg, repo, head, request_id=RID, task_kind="source",
                     forbidden_actions=list(_FULL_FORBIDDEN))
    d = _route(root, cfg)
    assert d.active and d.matter_class == "D"
    assert any("no codex source verdict" in r for r in d.reasons)


def test_unpublished_request_routes_to_d(env):
    # governance active but no verified (published) request -> D
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    d = _route(root, cfg)
    assert d.active and d.matter_class == "D"
    assert any("not verifiable" in r for r in d.reasons)


# ------------------------- F1 (000708): chain provenance established from root

def test_codex_verdict_is_authoritative(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    _publish_and_go(root, cfg, repo, head, "A")
    d = _route(root, cfg)
    # the router read the chain from root and used the codex-authored, hash-bound
    # verdict — a claude-sender verdict can't even be appended (SENDER_ALLOWED), so
    # the only class the router can read is the codex one.
    assert d.matter_class == "A" and d.declared_class == "A"


# ------------------- F2 (000708): request bound to the published payload hash

def test_post_publication_request_mutation_forced_to_d(env):
    """A correct all-six-declared request routes A; mutating the request file after
    publication (stale hash) makes verified_request fail -> forced D (audit 000708)."""
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    _publish_and_go(root, cfg, repo, head, "A")
    assert _route(root, cfg).matter_class == "A"          # authentic -> A
    # tamper the claimed request file: drop a Class-D predicate, leave a stale hash
    path = os.path.join(root, "requests", "claimed", RID + ".json")
    req = json.load(open(path, encoding="utf-8"))
    req["forbidden_actions"] = [p for p in req["forbidden_actions"]
                                if p != "alteration_of_fundamental_mission"]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(req, fh)
    d = _route(root, cfg)
    assert d.matter_class == "D"
    assert any("not verifiable" in r for r in d.reasons)


# --------------------------------- F2/anti-deflation: Class-D predicates

def test_undeclared_class_d_predicate_forced_to_d(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    partial = [p for p in _FULL_FORBIDDEN
               if p != "external_publication_under_owner_identity"]
    _publish_and_go(root, cfg, repo, head, "A", forbidden_actions=partial)
    d = _route(root, cfg)
    assert d.matter_class == "D"
    assert any("Class-D predicate" in r for r in d.reasons)


def test_implicated_class_d_predicate_in_allowed_forced_to_d(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    _publish_and_go(
        root, cfg, repo, head, "B",
        allowed_actions=["read source", "expenditure_beyond_authorized_budget"])
    d = _route(root, cfg)
    assert d.matter_class == "D"
    assert any("Class-D predicate" in r for r in d.reasons)


def test_undeclared_legacy_capability_forced_to_d(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    partial = [p for p in _FULL_FORBIDDEN if p != "weight_training"]
    _publish_and_go(root, cfg, repo, head, "A", forbidden_actions=partial)
    d = _route(root, cfg)
    assert d.matter_class == "D"


# --------------------------------- anti-deflation: protected-path real diff

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
    root, _r0, _h0, cfg0 = env
    _ratify(root, _r0, _h0, cfg0, 4)
    repo, head = _repo_touching_protected(tmp_path)
    cfg = make_cfg(repo, root)
    _publish_and_go(root, cfg, repo, head, "A", scope=["benign refactor"])
    d = policy.governance_route(root, cfg, RID)
    assert d.matter_class == "D" and d.route == "owner"
    assert any("protected paths" in r for r in d.reasons)


# ------------------------- C1 (000714): malformed chain record fails closed to D

def test_malformed_chain_record_routes_to_d(env):
    """A newline-terminated malformed JSON event record must yield an owner/Class-D
    decision, never an uncaught StrictJSONError (audit 000714 C1)."""
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    _publish_and_go(root, cfg, repo, head, "A")
    assert _route(root, cfg).matter_class == "A"          # healthy -> A
    # append a malformed but newline-terminated (complete) record to the chain
    with open(os.path.join(root, "events.jsonl"), "a", encoding="utf-8") as fh:
        fh.write('{"event_type": "BUILD_STARTED", not valid json\n')
    d = _route(root, cfg)
    assert not d.active and d.matter_class == "D" and d.route == "owner"


# ----------------------------- F3: active only on the effective owner-ratified pin

def test_installed_policy_must_equal_effective_pin(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    path = storage.policy_path(root)
    os.chmod(path, 0o644)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(dict(policy.POLICY_VERSIONS[5], created_utc="x"), fh)
    d = policy.governance_route(root, cfg, RID)
    assert not d.active and d.route == "owner"


# ----------------------------------------- matter_class is codex-authored/bound

def test_matter_class_is_payload_hash_bound():
    a = make_verdict("a" * 40, RID, verdict="GO"); a["matter_class"] = "A"
    b = make_verdict("a" * 40, RID, verdict="GO"); b["matter_class"] = "D"
    assert compute_verdict_payload_hash(a) != compute_verdict_payload_hash(b)
