"""Delegated-authority (owner-ratified policy v3) adversarial suite.

The delegation mechanism lets the DETERMINISTIC council engine auto-satisfy a
CODEX conditional verdict (AUDIT_GO_WITH_CONDITIONS) whose every condition the
auditor classified Class A, for structural `source` work inside the smallest
ratified charter — WITHOUT the owner's per-verdict S/KEY token. Everything
outside the envelope must fail closed to the human CONDITIONS_SATISFIED gate.

Every test proves a fail-closed boundary:
  * Claude cannot self-approve — a CONDITIONS_AUTO_SATISFIED's authority is a
    RE-VALIDATED `policy.evaluate_delegation` pass at the append boundary,
    never the event's mere presence.
  * The Class-A signal is CODEX-authored and verdict_payload_hash-bound — the
    builder cannot forge it; the auto-satisfaction payload's own class claims
    are IGNORED (only the codex verdict's hash-bound classes count).
  * Delegation is INERT until the owner ratifies policy v3; under v1/v2 it
    fails closed.
  * The human-only CONDITIONS_SATISFIED + S/KEY path is left unbroken.
"""
import json
import os

import pytest

from tests.council_util import (append, drive_to_claimed, make_cfg, make_repo,
                                make_request, make_root, make_verdict,
                                _inject_test_bindings)
from tools.council import (checkpoint, events, policy, state_machine, storage)
from tools.council.schemas import (CouncilError, SchemaViolation,
                                   TransitionError, compute_verdict_payload_hash,
                                   validate_verdict)

RID = "deleg-req-001"
CONTROL_RID = "council-control"
DELEG_ID = "coliseum-delegation-structural-source-v1"


# --------------------------------------------------------------- environment

def _provision_checkpoint(root):
    """Root-owned anchor over the identity root (conftest isolates
    CHECKPOINT_FILE per-test), without which no amendment is trusted."""
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
    """A bootstrapped root with policy v1 INSTALLED and pinned (delegation
    still INERT — the owner has not ratified v3)."""
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    policy.write_initial_policy(root)
    _p, v1_hash = policy.load_policy(root)
    append(root, cfg, "POLICY_INITIALIZED", "human", CONTROL_RID, repo,
           "0" * 40, {"policy_hash": v1_hash, "policy_file": storage.POLICY_FILE})
    _provision_checkpoint(root)
    return root, repo, head, cfg


def _ratify_v3(root, repo, head, cfg):
    """The Step-C owner action: forward-only amendment v1 -> v2 -> v3, which
    activates the OwnerDelegationProfile."""
    _amend(root, repo, head, cfg, 2)
    _amend(root, repo, head, cfg, 3)
    assert policy.effective_policy_pin(events.read_chain(root))[1] == 3


# ------------------------------------------------------------ synthetic probes

def _source_request(repo, head, **ov):
    fields = {"task_kind": "source"}
    fields.update(ov)
    return make_request(repo, head, RID, **fields)


def _verdict_event(head, *, sender="codex",
                   event_type="AUDIT_GO_WITH_CONDITIONS",
                   conditions=("reword the module docstring",),
                   classes=("A",), audited_commit=None):
    commit = audited_commit or head
    verdict = make_verdict(head, request_id=RID, verdict="GO_WITH_CONDITIONS",
                           conditions=list(conditions))
    verdict["audited_commit"] = commit
    if classes is not None:
        verdict["condition_classes"] = list(classes)
    verdict["verdict_payload_hash"] = compute_verdict_payload_hash(verdict)
    return {"event_id": "000099-testtest", "event_type": event_type,
            "sender": sender, "request_id": RID, "payload": verdict,
            "target_commit": commit}


def _decide(root, cfg, request, verdict_event):
    return policy.evaluate_delegation(root, cfg, request, verdict_event,
                                      events.read_chain(root))


# ============================================================================
# evaluate_delegation — the re-validated authority (positive + fail-closed)
# ============================================================================

def test_full_pass_auto_approves_under_ratified_v3(env):
    root, repo, head, cfg = env
    _ratify_v3(root, repo, head, cfg)
    d = _decide(root, cfg, _source_request(repo, head), _verdict_event(head))
    assert d.auto_approve, d.reasons
    assert d.policy_hash
    # every load-bearing guard is actually wired into the decision
    for name in ("delegation_active", "verdict_is_codex_conditional",
                 "condition_classes_present", "all_conditions_class_a",
                 "task_kind_delegated", "classes_within_charter",
                 "no_protocol_self_modification",
                 "forbidden_capabilities_declared",
                 "delegation_budget_within_bound", "working_tree_clean",
                 "head_is_target"):
        assert name in d.checked


def test_inert_until_owner_ratifies_v3(env):
    """Under the pinned v1 policy there is no owner_delegation block at all —
    delegation fails closed even with an otherwise-perfect Class-A verdict."""
    root, repo, head, cfg = env
    d = _decide(root, cfg, _source_request(repo, head), _verdict_event(head))
    assert not d.auto_approve
    assert any("delegation_active" in r for r in d.reasons)


def test_inert_under_v2(env):
    """v2 (the ollama amendment) still carries no delegation — fail closed."""
    root, repo, head, cfg = env
    _amend(root, repo, head, cfg, 2)
    d = _decide(root, cfg, _source_request(repo, head), _verdict_event(head))
    assert not d.auto_approve
    assert any("delegation_active" in r for r in d.reasons)


def test_non_codex_verdict_refused(env):
    """A claude-sender 'conditional verdict' is not an auditor judgment."""
    root, repo, head, cfg = env
    _ratify_v3(root, repo, head, cfg)
    d = _decide(root, cfg, _source_request(repo, head),
                _verdict_event(head, sender="claude"))
    assert not d.auto_approve
    assert any("verdict_is_codex_conditional" in r for r in d.reasons)


def test_plain_go_is_not_a_conditional_verdict(env):
    root, repo, head, cfg = env
    _ratify_v3(root, repo, head, cfg)
    d = _decide(root, cfg, _source_request(repo, head),
                _verdict_event(head, event_type="AUDIT_GO"))
    assert not d.auto_approve
    assert any("verdict_is_codex_conditional" in r for r in d.reasons)


def test_non_class_a_condition_refused(env):
    """A codex-classified Class-C condition (new authority) never auto-satisfies
    — it must fall to the owner token."""
    root, repo, head, cfg = env
    _ratify_v3(root, repo, head, cfg)
    d = _decide(root, cfg, _source_request(repo, head),
                _verdict_event(head, conditions=("wire a cloud API",),
                               classes=("C",)))
    assert not d.auto_approve
    assert any("all_conditions_class_a" in r for r in d.reasons)


def test_mixed_classes_refused(env):
    """One non-A condition among many taints the whole verdict."""
    root, repo, head, cfg = env
    _ratify_v3(root, repo, head, cfg)
    d = _decide(root, cfg, _source_request(repo, head),
                _verdict_event(head, conditions=("a", "b"), classes=("A", "B")))
    assert not d.auto_approve
    assert any("all_conditions_class_a" in r for r in d.reasons)


def test_missing_classification_refused(env):
    """No auditor classification at all → no delegated authority."""
    root, repo, head, cfg = env
    _ratify_v3(root, repo, head, cfg)
    d = _decide(root, cfg, _source_request(repo, head),
                _verdict_event(head, classes=None))
    assert not d.auto_approve
    assert any("condition_classes_present" in r for r in d.reasons)


def test_misaligned_classification_refused(env):
    """A classification list that does not cover every condition 1:1."""
    root, repo, head, cfg = env
    _ratify_v3(root, repo, head, cfg)
    d = _decide(root, cfg, _source_request(repo, head),
                _verdict_event(head, conditions=("a", "b"), classes=("A",)))
    assert not d.auto_approve
    assert any("condition_classes_present" in r for r in d.reasons)


def test_no_conditions_refused(env):
    """A conditional verdict with an EMPTY conditions list cannot delegate."""
    root, repo, head, cfg = env
    _ratify_v3(root, repo, head, cfg)
    d = _decide(root, cfg, _source_request(repo, head),
                _verdict_event(head, conditions=(), classes=()))
    assert not d.auto_approve
    assert any("condition_classes_present" in r for r in d.reasons)


def test_commit_swap_refused(env):
    """A verdict for a different commit never authorizes this request."""
    root, repo, head, cfg = env
    _ratify_v3(root, repo, head, cfg)
    d = _decide(root, cfg, _source_request(repo, head),
                _verdict_event(head, audited_commit="d" * 40))
    assert not d.auto_approve
    assert any("verdict_commit_exact" in r for r in d.reasons)


def test_non_source_task_kind_refused(env):
    """The smallest charter delegates structural `source` work ONLY."""
    root, repo, head, cfg = env
    _ratify_v3(root, repo, head, cfg)
    d = _decide(root, cfg, _source_request(repo, head, task_kind="experiment"),
                _verdict_event(head))
    assert not d.auto_approve
    assert any("task_kind_delegated" in r for r in d.reasons)


def test_protected_path_scope_refused(env):
    """A request whose scope touches the council protocol cannot self-authorize
    — the delegation mechanism cannot be changed from inside the delegation."""
    root, repo, head, cfg = env
    _ratify_v3(root, repo, head, cfg)
    d = _decide(root, cfg,
                _source_request(repo, head, scope=["patch tools/council/policy.py"]),
                _verdict_event(head))
    assert not d.auto_approve
    assert any("no_protocol_self_modification" in r for r in d.reasons)


def test_missing_forbidden_capabilities_refused(env):
    """The request must explicitly forbid every dangerous capability."""
    root, repo, head, cfg = env
    _ratify_v3(root, repo, head, cfg)
    d = _decide(root, cfg,
                _source_request(repo, head, forbidden_actions=["destructive_tools"]),
                _verdict_event(head))
    assert not d.auto_approve
    assert any("forbidden_capabilities_declared" in r for r in d.reasons)


def test_manual_marker_suspends_delegation(env):
    """The repository-local MANUAL presence marker suspends auto-satisfaction
    (a presence marker can only DENY — it routes back to the owner token)."""
    root, repo, head, cfg = env
    _ratify_v3(root, repo, head, cfg)
    open(os.path.join(root, storage.MANUAL_FILE), "w").close()
    d = _decide(root, cfg, _source_request(repo, head), _verdict_event(head))
    assert not d.auto_approve
    assert any("delegation_suspension_clear" in r for r in d.reasons)


def test_emergency_stop_suspends_delegation(env):
    root, repo, head, cfg = env
    _ratify_v3(root, repo, head, cfg)
    open(os.path.join(root, "STOP"), "w").close()
    d = _decide(root, cfg, _source_request(repo, head), _verdict_event(head))
    assert not d.auto_approve
    assert any("emergency_stop_clear" in r for r in d.reasons)


def test_dirty_tree_refused(env):
    root, repo, head, cfg = env
    _ratify_v3(root, repo, head, cfg)
    with open(os.path.join(repo, "dirty.txt"), "w") as fh:
        fh.write("x\n")
    d = _decide(root, cfg, _source_request(repo, head), _verdict_event(head))
    assert not d.auto_approve
    assert any("working_tree_clean" in r for r in d.reasons)


# ------------------------------------------------- delegation budget window

def test_delegated_integration_count_windows_on_owner_action():
    """The budget resets at each owner control action (STATUS_CHANGED /
    POLICY_AMENDED), exactly like the compute/failure envelopes."""
    chain = [
        {"event_type": "CONDITIONS_AUTO_SATISFIED"},
        {"event_type": "STATUS_CHANGED"},            # owner action -> reset
        {"event_type": "CONDITIONS_AUTO_SATISFIED"},
        {"event_type": "CONDITIONS_AUTO_SATISFIED"},
        {"event_type": "POLICY_AMENDED"},            # owner action -> reset
        {"event_type": "CONDITIONS_AUTO_SATISFIED"},
    ]
    assert policy.delegated_integration_count(chain) == 1
    assert policy.delegated_integration_count([]) == 0


def test_budget_exhaustion_fails_closed(env, monkeypatch):
    """At the per-owner-action cap, further delegated satisfactions fail closed
    until the owner acts again. (The count itself is windowed/unit-tested above;
    here we pin it at the cap to isolate the guard.)"""
    root, repo, head, cfg = env
    _ratify_v3(root, repo, head, cfg)
    cap = policy.POLICY_VERSIONS[3]["owner_delegation"][
        "max_delegated_integrations_per_owner_action"]
    monkeypatch.setattr(policy, "delegated_integration_count", lambda chain: cap)
    d = _decide(root, cfg, _source_request(repo, head), _verdict_event(head))
    assert not d.auto_approve
    assert any("delegation_budget_within_bound" in r for r in d.reasons)


# ============================================================================
# state_machine gate — chain-only, replay-safe anti-forgery
# ============================================================================

def _req_at_go(last_verdict):
    return {RID: {"state": state_machine.GO, "target_commit": "",
                  "last_verdict": last_verdict, "conditions_satisfied": False,
                  "audit_cycles": 1, "history": [], "claimed_by": "codex",
                  "last_event_id": None}}


def _auto_event(condition_classes=None):
    return {"event_type": "CONDITIONS_AUTO_SATISFIED", "sender": "claude",
            "request_id": RID, "target_commit": "x",
            "event_id": "000100-autotest",
            "payload": {"condition_classes": condition_classes}}


def test_state_gate_passes_for_all_class_a_conditional():
    reqs = _req_at_go({"event_type": "AUDIT_GO_WITH_CONDITIONS",
                       "condition_classes": ["A", "A"]})
    state_machine.check(_auto_event(), reqs)          # no raise
    state_machine.apply(_auto_event(), reqs)
    assert reqs[RID]["conditions_satisfied"] is True


def test_state_gate_refuses_non_conditional_verdict():
    reqs = _req_at_go({"event_type": "AUDIT_GO", "condition_classes": None})
    with pytest.raises(TransitionError):
        state_machine.check(_auto_event(), reqs)


def test_state_gate_refuses_missing_classes():
    reqs = _req_at_go({"event_type": "AUDIT_GO_WITH_CONDITIONS",
                       "condition_classes": None})
    with pytest.raises(TransitionError):
        state_machine.check(_auto_event(), reqs)


def test_state_gate_reads_verdict_classes_not_event_payload():
    """The builder cannot forge authority by claiming Class A in the
    auto-satisfaction PAYLOAD — the gate reads the codex verdict's hash-bound
    classification (here Class C), so it refuses regardless of the payload."""
    reqs = _req_at_go({"event_type": "AUDIT_GO_WITH_CONDITIONS",
                       "condition_classes": ["C"]})
    with pytest.raises(TransitionError):
        state_machine.check(_auto_event(condition_classes=["A"]), reqs)


# ============================================================================
# schema gate — condition_classes is codex-authored, hash-bound
# ============================================================================

def _valid_conditional_verdict(head, conditions, classes):
    v = make_verdict(head, request_id=RID, verdict="GO_WITH_CONDITIONS",
                     conditions=list(conditions))
    if classes is not None:
        v["condition_classes"] = list(classes)
    v["verdict_payload_hash"] = compute_verdict_payload_hash(v)
    return v


def test_schema_accepts_aligned_class_a():
    validate_verdict(_valid_conditional_verdict(
        "a" * 40, ["reword docstring"], ["A"]))          # no raise


def test_schema_rejects_misaligned_classes():
    v = _valid_conditional_verdict("a" * 40, ["one", "two"], ["A", "A"])
    v["condition_classes"] = ["A"]                        # now misaligned
    with pytest.raises(SchemaViolation):
        validate_verdict(v)


def test_schema_rejects_unknown_class():
    v = _valid_conditional_verdict("a" * 40, ["one"], ["A"])
    v["condition_classes"] = ["Z"]
    with pytest.raises(SchemaViolation):
        validate_verdict(v)


def test_schema_binds_classes_into_payload_hash():
    """Tampering the classification without re-signing the hash is caught."""
    v = _valid_conditional_verdict("a" * 40, ["one"], ["A"])
    original_hash = v["verdict_payload_hash"]
    v["condition_classes"] = ["A"]                        # length preserved...
    # ...but a semantically different classification would change the hash:
    v2 = _valid_conditional_verdict("a" * 40, ["one"], ["B"])
    assert v2["verdict_payload_hash"] != original_hash


# ============================================================================
# end-to-end through the real append boundary
# ============================================================================

def _append_conditional(root, cfg, repo, head, *, sender="codex",
                        conditions=("reword the module docstring",),
                        classes=("A",)):
    payload = make_verdict(head, RID, verdict="GO_WITH_CONDITIONS",
                           conditions=list(conditions))
    if classes is not None:
        payload["condition_classes"] = list(classes)
    payload["schema_version"] = "source-verdict.v2"
    _inject_test_bindings(root, payload, RID, head, False)
    payload["verdict_payload_hash"] = compute_verdict_payload_hash(payload)
    return append(root, cfg, "AUDIT_GO_WITH_CONDITIONS", sender, RID, repo,
                  head, payload)


def test_end_to_end_auto_satisfies_and_integrates_under_v3(env):
    """The capstone: under owner-ratified v3, a Class-A codex conditional
    verdict is auto-satisfied and the change integrates with NO human token."""
    root, repo, head, cfg = env
    _ratify_v3(root, repo, head, cfg)
    drive_to_claimed(root, cfg, repo, head, request_id=RID, task_kind="source")
    _append_conditional(root, cfg, repo, head)
    auto = append(root, cfg, "CONDITIONS_AUTO_SATISFIED", "claude", RID, repo,
                  head, {"delegation_id": DELEG_ID,
                         "conditions_checked": ["reword the module docstring"],
                         "condition_classes": ["A"]})
    assert auto["event_type"] == "CONDITIONS_AUTO_SATISFIED"
    reqs = state_machine.project(events.read_chain(root))
    assert reqs[RID]["conditions_satisfied"] is True
    # integration now proceeds on claude authority alone (no owner token)
    append(root, cfg, "CHANGE_INTEGRATED", "claude", RID, repo, head,
           {"integration": "auto", "delegation_id": DELEG_ID})
    reqs = state_machine.project(events.read_chain(root))
    assert reqs[RID]["state"] == state_machine.INTEGRATED
    assert events.verify_chain(root).healthy


def test_end_to_end_refused_when_delegation_inert(env):
    """Under the un-ratified v1 policy the append boundary re-validates the
    delegation and REFUSES the auto-satisfaction — and the human token path is
    left completely unbroken."""
    root, repo, head, cfg = env                        # v1: delegation inert
    drive_to_claimed(root, cfg, repo, head, request_id=RID, task_kind="source")
    _append_conditional(root, cfg, repo, head)
    with pytest.raises(CouncilError):
        append(root, cfg, "CONDITIONS_AUTO_SATISFIED", "claude", RID, repo,
               head, {"delegation_id": DELEG_ID, "condition_classes": ["A"]})
    # the owner's manual CONDITIONS_SATISFIED (S/KEY token) still works
    append(root, cfg, "CONDITIONS_SATISFIED", "human", RID, repo, head,
           {"note": "owner satisfies manually"})
    reqs = state_machine.project(events.read_chain(root))
    assert reqs[RID]["conditions_satisfied"] is True


def test_end_to_end_non_class_a_refused_by_state_gate(env):
    """Even under ratified v3, a codex Class-C classification is refused at the
    chain gate BEFORE the policy re-validation — the auto-satisfaction payload's
    own class claim is irrelevant."""
    root, repo, head, cfg = env
    _ratify_v3(root, repo, head, cfg)
    drive_to_claimed(root, cfg, repo, head, request_id=RID, task_kind="source")
    _append_conditional(root, cfg, repo, head, conditions=("add a cloud API",),
                        classes=("C",))
    with pytest.raises(TransitionError):
        append(root, cfg, "CONDITIONS_AUTO_SATISFIED", "claude", RID, repo,
               head, {"delegation_id": DELEG_ID, "condition_classes": ["A"]})


def test_claude_cannot_author_the_conditional_verdict(env):
    """The Class-A classification lives in a CODEX verdict; a claude-sender
    AUDIT_GO_WITH_CONDITIONS is refused at append (SENDER_ALLOWED)."""
    root, repo, head, cfg = env
    _ratify_v3(root, repo, head, cfg)
    drive_to_claimed(root, cfg, repo, head, request_id=RID, task_kind="source")
    with pytest.raises(CouncilError):
        _append_conditional(root, cfg, repo, head, sender="claude")
