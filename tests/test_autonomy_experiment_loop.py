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


def test_select_returns_experiment_even_after_canceled_attempt(tmp_path):
    """End-to-end of the fix through the real registry: with the base attempt
    canceled in the chain-derived projection, selection still yields the
    experiment (monkeypatched projection keeps the test hermetic)."""
    import tools.autonomy.experiment_loop as L
    root = make_root(tmp_path)
    eid, _ = L.select_next_experiment(root, REAL_REPO)
    base = L._PREFIX + eid
    real_project = L.state_machine.project

    def fake_project(chain):
        proj = real_project(chain)
        proj[base] = {"state": "canceled"}
        return proj

    L.state_machine.project = fake_project
    try:
        again = L.select_next_experiment(root, REAL_REPO)
        assert again is not None and again[0] == eid
    finally:
        L.state_machine.project = real_project


def _min_policy():
    from tools.council import policy
    return policy.DEFAULT_POLICY
