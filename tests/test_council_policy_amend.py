"""M7a: the owner-token-gated policy-amendment mechanism. The immutable policy
may move only between CODE-DEFINED versions, only via a human-token
POLICY_AMENDED event that binds the prev/new hash + monotonic version, and an
autonomous agent can neither record the event nor otherwise advance the pin —
it cannot expand its own authority."""
import json
import os

import pytest

from tests.council_util import append, make_cfg, make_repo, make_root
from tools.council import events, policy, storage
from tools.council.schemas import SchemaViolation

CONTROL_RID = "council-control"


@pytest.fixture()
def env(tmp_path):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    policy.write_initial_policy(root)
    _p, v1_hash = policy.load_policy(root)
    append(root, cfg, "POLICY_INITIALIZED", "human", CONTROL_RID, repo,
           "0" * 40, {"policy_hash": v1_hash, "policy_file": storage.POLICY_FILE})
    return root, repo, head, cfg, v1_hash


def _amend_to_v2(root, repo, head, cfg):
    prev_hash, new_hash, diff = policy.amend_policy(root, 2)
    append(root, cfg, "POLICY_AMENDED", "human", CONTROL_RID, repo, head,
           {"policy_hash": new_hash, "prev_policy_hash": prev_hash,
            "policy_version": 2, "policy_diff": diff, "impl_commit": head,
            "policy_file": storage.POLICY_FILE})
    return prev_hash, new_hash


# ---------------------------------------------------------- version integrity

def test_v1_is_the_live_default_and_v2_only_adds_ollama():
    v1, v2 = policy.POLICY_VERSIONS[1], policy.POLICY_VERSIONS[2]
    assert "policy_version" not in v1                      # v1 predates the field
    assert v2["policy_version"] == 2 and v2["amends"] == 1
    assert v2["auto_approval"]["allowed_experiment_classes"] == \
        ["sandbox_local", "ollama_local"]
    assert v2["auto_approval"]["allowed_data_sources"] == \
        ["synthetic", "local_model"]
    # v2 changes ONLY the two auto_approval gates + version markers
    diff = policy._policy_diff(policy._content(v1), policy._content(v2))
    assert set(diff) == {"auto_approval", "policy_version", "amends"}


def test_effective_pin_before_and_after_amendment(env):
    root, repo, head, cfg, v1_hash = env
    chain = events.read_chain(root)
    assert policy.effective_policy_pin(chain) == (v1_hash, 1)
    _prev, new_hash = _amend_to_v2(root, repo, head, cfg)
    chain = events.read_chain(root)
    assert policy.effective_policy_pin(chain) == (new_hash, 2)
    live, live_hash = policy.load_policy(root)
    assert live_hash == new_hash and policy.policy_version_of(live) == 2
    assert policy.is_code_defined_version(live)


# --------------------------------- agents cannot expand their own authority

@pytest.mark.parametrize("sender", ["claude", "codex"])
def test_agent_cannot_record_policy_amended(env, sender):
    root, repo, head, cfg, v1_hash = env
    prev_hash, new_hash, diff = policy.amend_policy(root, 2)  # even if a file write happened
    with pytest.raises(Exception):   # sender not in SENDER_ALLOWED{human}
        append(root, cfg, "POLICY_AMENDED", sender, CONTROL_RID, repo, head,
               {"policy_hash": new_hash, "prev_policy_hash": prev_hash,
                "policy_version": 2, "policy_diff": diff, "impl_commit": head})


def test_hand_edited_policy_is_not_a_code_defined_version(env):
    """An owner (or anyone) hand-editing the file to grant extra classes
    without going through amend_policy fails the code-defined-version gate."""
    root, repo, head, cfg, v1_hash = env
    path = storage.policy_path(root)
    live, _ = policy.load_policy(root)
    live["auto_approval"]["allowed_experiment_classes"].append("ollama_local")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    storage.atomic_write_json(path, live)
    tampered, _h = policy.load_policy(root)
    assert not policy.is_code_defined_version(tampered)


# ------------------------------------------------- amendment binding integrity

def test_amendment_with_wrong_prev_hash_does_not_advance_pin(env):
    root, repo, head, cfg, v1_hash = env
    _prev, new_hash, diff = policy.amend_policy(root, 2)
    # bind to a WRONG prev hash — the walk must refuse to advance
    append(root, cfg, "POLICY_AMENDED", "human", CONTROL_RID, repo, head,
           {"policy_hash": new_hash, "prev_policy_hash": "0" * 64,
            "policy_version": 2, "policy_diff": diff, "impl_commit": head})
    pin, version = policy.effective_policy_pin(events.read_chain(root))
    assert (pin, version) == (v1_hash, 1)   # never advanced past the bad link


def test_non_monotonic_version_does_not_advance_pin(env):
    root, repo, head, cfg, v1_hash = env
    _prev, new_hash, diff = policy.amend_policy(root, 2)
    append(root, cfg, "POLICY_AMENDED", "human", CONTROL_RID, repo, head,
           {"policy_hash": new_hash, "prev_policy_hash": v1_hash,
            "policy_version": 3,   # must be exactly prev+1
            "policy_diff": diff, "impl_commit": head})
    assert policy.effective_policy_pin(events.read_chain(root)) == (v1_hash, 1)


def test_amend_refuses_from_unknown_base(env):
    root, repo, head, cfg, v1_hash = env
    _amend_to_v2(root, repo, head, cfg)          # now at v2
    with pytest.raises(SchemaViolation):
        policy.amend_policy(root, 2)              # base is v2, not v1 -> refuse


def test_amendment_flips_ollama_local_from_refused_to_allowed(env):
    """The end-to-end point of M7: an ollama_local experiment is refused under
    v1 and auto-approvable under v2 — solely because the owner amended."""
    from tests.council_util import make_autonomy_block, make_request, make_verdict
    from tools.council.schemas import compute_verdict_payload_hash
    root, repo, head, cfg, v1_hash = env
    autonomy = make_autonomy_block(experiment_class="ollama_local",
                                   data_sources=["local_model"])
    request = make_request(repo, head, "ol-req-001",
                           human_approval_required=False, autonomy=autonomy)
    verdict = make_verdict(head, request_id="ol-req-001", verdict="GO")
    verdict["verdict_payload_hash"] = compute_verdict_payload_hash(verdict)
    go = {"event_type": "AUDIT_GO", "sender": "codex",
          "request_id": "ol-req-001", "payload": verdict, "target_commit": head}

    reasons_v1 = policy.evaluate(root, cfg, request, go,
                                 events.read_chain(root)).reasons
    assert any("experiment_class_allowed" in r for r in reasons_v1)

    _amend_to_v2(root, repo, head, cfg)
    reasons_v2 = policy.evaluate(root, cfg, request, go,
                                 events.read_chain(root)).reasons
    assert not any("experiment_class_allowed" in r for r in reasons_v2)
    assert not any("synthetic_data_only" in r for r in reasons_v2)
    assert not any("policy_unchanged" in r for r in reasons_v2)
    assert not any("policy_is_code_defined_version" in r for r in reasons_v2)
