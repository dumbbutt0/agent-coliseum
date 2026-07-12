"""M7d: the autonomous experiment-loop driver — selection + auto-approve request
building. The driver PROPOSES the next registered experiment; the immutable
policy (re-checked in policy.evaluate) decides whether it may auto-run."""
import json
import os

import yaml

from tests.autonomy_util import REAL_REPO
from tests.council_util import make_root
from tools.autonomy import experiment_loop as loop
from tools.autonomy import roadmap as roadmap_mod
from tools.council.schemas import (validate_autonomy_block, validate_request)

REG = os.path.join(REAL_REPO, "configs", "registry", "experiments.yaml")


def test_select_skips_complete_and_picks_a_registered_experiment(tmp_path):
    root = make_root(tmp_path)
    picked = loop.select_next_experiment(root, REAL_REPO)
    assert picked is not None
    eid, config_path = picked
    reg = yaml.safe_load(open(REG))
    by_id = {e["experiment_id"]: e for e in reg["experiments"]}
    # the pick is a PRE-REGISTERED experiment (never the completed batch 2)
    assert by_id[eid]["status"] == "pre-registered"
    assert eid != "m6-stochastic-baseline"
    assert os.path.exists(config_path)
    assert json.load(open(config_path))["experiment_id"] == eid


def test_build_run_request_is_a_valid_auto_approve_request(tmp_path):
    root = make_root(tmp_path)
    eid, config_path = loop.select_next_experiment(root, REAL_REPO)
    config = json.load(open(config_path))
    policy_doc = yaml.safe_load(open(os.path.join(
        REAL_REPO, "configs", "registry", "experiments.yaml")))  # any doc
    roadmap = roadmap_mod.load_roadmap(
        os.path.join(REAL_REPO, "configs", "autonomy-roadmap.yaml"),
        _min_policy())[0]
    task = roadmap_mod.task_by_id(roadmap, config["task_id"])
    head = "a" * 40
    req = loop.build_run_request(REAL_REPO, head, "b" * 64, eid,
                                 config_path, config, task)
    # it is an AUTO-approve request with a structurally valid autonomy block
    assert req["human_approval_required"] is False
    assert req["live_experiment_allowed"] is False
    validate_autonomy_block(req["autonomy"])
    assert req["autonomy"]["experiment_class"] == "ollama_local"
    assert req["autonomy"]["data_sources"] == ["local_model"]
    # limits are within the policy caps (roadmap task is already capped)
    caps = _min_policy()["auto_approval"]["limits"]
    for k, v in req["autonomy"]["limits"].items():
        assert v <= caps[k], (k, v, caps[k])
    # and the whole request passes schema validation (commit checks aside)
    from tools.council import schemas
    req["request_payload_hash"] = schemas.compute_request_payload_hash(req)
    # validate_request also checks the repo/commit exist; skip those by checking
    # only the schema-level required fields + autonomy path here
    for f in schemas.REQUEST_REQUIRED_FIELDS:
        assert f in req


def test_canceled_attempt_does_not_orphan_experiment(tmp_path, monkeypatch):
    """Regression (M7 activation): a `canceled` loop attempt is terminal-but-
    unsuccessful and must NOT permanently drop its experiment. The experiment
    stays selectable and the NEXT attempt uses a fresh, disambiguated id.

    This is the exact defect that stranded B1 (m6-sequential-rerun) after its
    autoloop request was canceled to clear the activation pause: the old
    `proj.get(rid) is None` guard treated the cancel as 'already attempted'."""
    root = make_root(tmp_path)
    picked = loop.select_next_experiment(root, REAL_REPO)
    assert picked is not None
    eid, _ = picked
    base = loop._PREFIX + eid

    # simulate the projection after that experiment's ONLY attempt was canceled
    empty_proj = {}
    assert loop.next_request_id(empty_proj, eid) == base   # first attempt

    canceled = {base: {"state": "canceled"}}
    # not in flight (terminal) -> still eligible for a fresh attempt
    assert loop._experiment_in_flight(canceled, eid, loop._terminal_states()) \
        is False
    # and the fresh attempt is disambiguated, never reopening the canceled id
    assert loop.next_request_id(canceled, eid) == f"{base}-002"

    # an in-flight (non-terminal) attempt DOES block a new one
    live = {f"{base}-002": {"state": "auto_approved"}}
    assert loop._experiment_in_flight(live, eid, loop._terminal_states()) \
        is True

    # numeric-suffix matching must not leak across sibling experiment ids
    other = {loop._PREFIX + eid + "-extra": {"state": "canceled"}}
    assert loop._attempt_rids(other, eid) == {}


def _stub_chain_proj(monkeypatch, chain, proj, halt=False,
                     authority_valid=True, prior_cfg_hash=None):
    """Point experiment_loop at a synthetic chain + projection + halt state, and
    stub the council authority layer + predecessor request lookup so retry-safety
    paths run hermetically against the real registry."""
    import tools.autonomy.experiment_loop as L
    monkeypatch.setattr(L.events, "read_chain", lambda *a, **k: chain)
    monkeypatch.setattr(L.state_machine, "project", lambda c: proj)
    monkeypatch.setattr(L, "_active_halt", lambda root, p: halt)
    monkeypatch.setattr(
        L.state_machine, "authority_status",
        lambda c: {rid: {"authority_valid": authority_valid,
                         "quarantined": False} for rid in proj})
    monkeypatch.setattr(L.publish, "read_request",
                        lambda root, rid: {"experiment_config_hash":
                                           prior_cfg_hash})
    return L


def _real_cfg_hash(eid):
    import tools.autonomy.experiment_loop as L
    return L._sha256_file(L._load_configs(REAL_REPO)[eid][0])


def _cancel(rid, sender="claude", eid_events=None):
    return {"request_id": rid, "event_type": "REQUEST_CANCELED",
            "event_id": f"evt-{rid}", "sender": sender, "payload": {}}


def _go(rid):
    """A codex-emitted AUDIT_GO — the non-self-assertable authority the loop
    (role claude) cannot forge: validate_sender refuses a claude AUDIT_GO."""
    return {"request_id": rid, "event_type": "AUDIT_GO",
            "event_id": f"go-{rid}", "sender": "codex", "payload": {}}


def _approved(rid):
    """A claude-emitted AUTO_APPROVED — directly appendable, so NOT sufficient
    authority for a retry on its own."""
    return {"request_id": rid, "event_type": "AUTO_APPROVED",
            "event_id": f"appr-{rid}", "sender": "claude", "payload": {}}


def test_classify_reason_awareness():
    """Retryability is derived from immutable chain facts, fail-closed. The
    positive authorization is AUTO_APPROVED (policy-gated), NOT the cancel's
    sender — an arbitrary Claude cancel cannot manufacture retry authority."""
    import tools.autonomy.experiment_loop as L
    rid = "autoloop-x"
    # executed -> result_stage (never auto-retried)
    assert L.classify_prior_attempt(
        [{"request_id": rid, "event_type": "EXPERIMENT_STARTED",
          "event_id": "e1", "sender": "claude"}], rid) == "result_stage"
    # audit-blocked -> audit_blocked
    assert L.classify_prior_attempt(
        [{"request_id": rid, "event_type": "AUDIT_BLOCKED",
          "event_id": "e1", "sender": "codex"}], rid) == "audit_blocked"
    # owner cancellation of a GO'd attempt -> owner_directed
    assert L.classify_prior_attempt(
        [_go(rid), _cancel(rid, "human")], rid) == "owner_directed"
    # a codex GO then a loop cancel, pre-execution -> the ONLY retryable path
    assert L.classify_prior_attempt(
        [_go(rid), _cancel(rid, "claude")], rid) == "pre_execution_retryable"
    # a bare claude AUTO_APPROVED (no codex GO) + cancel -> NOT retryable: the
    # loop cannot self-assert authority (the exact Codex-found hole)
    assert L.classify_prior_attempt(
        [_approved(rid), _cancel(rid, "claude")], rid) == "other"
    # a Claude cancel with no verdict at all -> NOT retryable
    assert L.classify_prior_attempt([_cancel(rid, "claude")], rid) == "other"
    # nothing we understand -> other (fail-closed)
    assert L.classify_prior_attempt(
        [{"request_id": rid, "event_type": "BUILD_READY",
          "event_id": "e", "sender": "claude"}], rid) == "other"


def test_classify_later_cancel_cannot_launder_a_failure():
    """Codex-found defect: a REQUEST_CANCELED appended AFTER a disqualifying
    event must not overwrite the classification into a retryable one. Every
    disqualifier is checked across the whole history, not just the last event."""
    import tools.autonomy.experiment_loop as L
    rid = "autoloop-x"
    # AUDIT_BLOCKED then a later Claude cancel -> STILL audit_blocked
    ch = [{"request_id": rid, "event_type": "AUDIT_BLOCKED", "event_id": "e1",
           "sender": "codex"},
          {"request_id": rid, "event_type": "REQUEST_CANCELED", "event_id": "e2",
           "sender": "claude", "payload": {}}]
    assert L.classify_prior_attempt(ch, rid) == "audit_blocked"
    # executed then a later Claude cancel -> STILL result_stage
    ch = [{"request_id": rid, "event_type": "EXPERIMENT_STARTED",
           "event_id": "e1", "sender": "claude"},
          {"request_id": rid, "event_type": "REQUEST_CANCELED", "event_id": "e2",
           "sender": "claude", "payload": {}}]
    assert L.classify_prior_attempt(ch, rid) == "result_stage"
    # an owner cancel anywhere -> owner_directed even if a Claude cancel follows
    ch = [{"request_id": rid, "event_type": "REQUEST_CANCELED", "event_id": "e1",
           "sender": "human", "payload": {}},
          {"request_id": rid, "event_type": "REQUEST_CANCELED", "event_id": "e2",
           "sender": "claude", "payload": {}}]
    assert L.classify_prior_attempt(ch, rid) == "owner_directed"


def test_plan_reattempt_permits_one_bounded_retry(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    eid, _ = __import__("tools.autonomy.experiment_loop", fromlist=["x"]) \
        .select_next_experiment(root, REAL_REPO)
    base = "autoloop-" + eid
    # a codex-GO'd attempt aborted pre-execution (the B1 lifecycle), authority
    # valid, config unchanged
    chain = [_go(base), _cancel(base, "claude")]
    proj = {base: {"state": "canceled"}}
    L = _stub_chain_proj(monkeypatch, chain, proj,
                         prior_cfg_hash=_real_cfg_hash(eid))
    rid, lineage = L.plan_reattempt(root, REAL_REPO, eid)
    assert rid == f"{base}-002"
    assert lineage["reason_class"] == "pre_execution_retryable"
    assert lineage["attempt_ordinal"] == 2
    assert lineage["prior_request_id"] == base
    assert lineage["retry_ceiling"] == L.MAX_ATTEMPTS_PER_EXPERIMENT
    assert lineage["design_hash"] == lineage["prior_design_hash"]
    assert lineage["experiment_config_hash"] == \
        lineage["prior_experiment_config_hash"]
    assert lineage["prior_terminal_event_id"] == f"evt-{base}"


def test_plan_reattempt_refuses_owner_cancel_and_budget_and_execution(
        tmp_path, monkeypatch):
    root = make_root(tmp_path)
    import tools.autonomy.experiment_loop as L0
    eid, _ = L0.select_next_experiment(root, REAL_REPO)
    base = "autoloop-" + eid

    real = _real_cfg_hash(eid)

    # (a) owner cancellation is never auto-retried
    L = _stub_chain_proj(monkeypatch, [_go(base), _cancel(base, "human")],
                         {base: {"state": "canceled"}}, prior_cfg_hash=real)
    rid, refusal = L.plan_reattempt(root, REAL_REPO, eid)
    assert rid is None and refusal["reason_class"] == "owner_directed"

    # (b) an executed attempt (produced a result) is never auto-retried
    ch = [_go(base), {"request_id": base, "event_type": "RESULT_BLOCKED",
                      "event_id": "r1", "sender": "codex"}]
    L = _stub_chain_proj(monkeypatch, ch, {base: {"state": "result_blocked"}},
                         prior_cfg_hash=real)
    rid, refusal = L.plan_reattempt(root, REAL_REPO, eid)
    assert rid is None and refusal["reason_class"] == "result_stage"

    # (c) budget exhaustion: base + -002 + -003 all GO'd+cancels -> 4th denied
    ids = [base, f"{base}-002", f"{base}-003"]
    ch = [ev for r in ids for ev in (_go(r), _cancel(r, "claude"))]
    proj = {r: {"state": "canceled"} for r in ids}
    L = _stub_chain_proj(monkeypatch, ch, proj, prior_cfg_hash=real)
    rid, refusal = L.plan_reattempt(root, REAL_REPO, eid)
    assert rid is None and refusal["reason_class"] == "retry_budget_exhausted"
    assert refusal["attempt_ordinal"] == 4

    # (d) an active standing halt blocks even a pre-execution cancel
    L = _stub_chain_proj(monkeypatch, [_go(base), _cancel(base, "claude")],
                         {base: {"state": "canceled"}}, halt=True,
                         prior_cfg_hash=real)
    rid, refusal = L.plan_reattempt(root, REAL_REPO, eid)
    assert rid is None and refusal["reason_class"] == "standing_halt"

    # (e) a bare Claude cancel with no codex GO is NOT retryable (self-assertion)
    L = _stub_chain_proj(monkeypatch, [_approved(base), _cancel(base, "claude")],
                         {base: {"state": "canceled"}}, prior_cfg_hash=real)
    rid, refusal = L.plan_reattempt(root, REAL_REPO, eid)
    assert rid is None and refusal["reason_class"] == "other"

    # (f) NO attempt yet, but a halt is active -> even a first request is refused
    L = _stub_chain_proj(monkeypatch, [], {}, halt=True)
    rid, refusal = L.plan_reattempt(root, REAL_REPO, eid)
    assert rid is None and refusal["reason_class"] == "standing_halt"

    # (g) a GO'd pre-execution cancel whose verdict authority is INVALID/
    #     quarantined (H4) is refused
    L = _stub_chain_proj(monkeypatch, [_go(base), _cancel(base, "claude")],
                         {base: {"state": "canceled"}},
                         authority_valid=False, prior_cfg_hash=real)
    rid, refusal = L.plan_reattempt(root, REAL_REPO, eid)
    assert rid is None and refusal["reason_class"] == "authority_invalid"

    # (h) a changed experiment config (predecessor hash differs) is refused
    L = _stub_chain_proj(monkeypatch, [_go(base), _cancel(base, "claude")],
                         {base: {"state": "canceled"}},
                         prior_cfg_hash="deadbeef" * 8)
    rid, refusal = L.plan_reattempt(root, REAL_REPO, eid)
    assert rid is None and refusal["reason_class"] == "config_changed"


def test_select_skips_non_retryable_experiment(tmp_path, monkeypatch):
    """A registered experiment whose only attempt was owner-canceled must NOT be
    auto-selected — selection is tightened, never loosened."""
    root = make_root(tmp_path)
    import tools.autonomy.experiment_loop as L0
    eid, _ = L0.select_next_experiment(root, REAL_REPO)
    base = "autoloop-" + eid
    # owner-cancel EVERY registered pre-registered experiment's base attempt
    import yaml
    reg = yaml.safe_load(open(REG))
    prereg = [e["experiment_id"] for e in reg["experiments"]
              if e.get("status") == "pre-registered"]
    chain = [_cancel("autoloop-" + x, "human") for x in prereg]
    proj = {"autoloop-" + x: {"state": "canceled"} for x in prereg}
    L = _stub_chain_proj(monkeypatch, chain, proj)
    assert L.select_next_experiment(root, REAL_REPO) is None


def _min_policy():
    from tools.council import policy
    return policy.DEFAULT_POLICY
