"""Runner: the full mock lifecycle end to end against a throwaway council
root + scratch repo, plus every refusal path (frozen-config mismatch,
limits, failed validations, human-gated tasks, wrong state)."""
import argparse
import hashlib
import json
import os

import pytest

from tests.autonomy_util import (REAL_REPO, seed_scratch_repo_for_mock,
                                 head_of, task_fields, write_mock_config,
                                 write_roadmap)
from tests.council_util import (append, make_autonomy_block, make_cfg,
                                make_repo, make_request, make_root,
                                make_verdict)
from tools.autonomy import cli as autonomy_cli
from tools.autonomy import roadmap as rm
from tools.autonomy import runner
from tools.council import codex_watch, events, policy, publish, \
    state_machine, storage

RID = "autonomy-mock-test-001"

FIXTURE_SHA = hashlib.sha256(open(os.path.join(
    REAL_REPO, "tests", "fixtures", "llm", "steward_obedient.json"),
    "rb").read()).hexdigest()


def _state(root, rid):
    return state_machine.project(events.read_chain(root)).get(
        rid, {}).get("state")


def _drive_to_auto_approved(tmp_path, config_sha, roadmap_path):
    """BUILD..AUTO_APPROVED through the REAL publish/claim/verdict/policy
    paths — no shortcuts around the protocol."""
    root = make_root(tmp_path)
    repo, _initial = make_repo(tmp_path)
    seed_scratch_repo_for_mock(repo)
    head = head_of(repo)
    cfg = make_cfg(repo, root)
    policy.write_initial_policy(root)
    _doc, rm_hash = rm.load_roadmap(roadmap_path, policy.load_policy(root)[0])

    append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    append(root, cfg, "BUILD_READY", "claude", RID, repo, head)
    request = make_request(
        repo, head, RID,
        human_approval_required=False,
        autonomy=make_autonomy_block(
            experiment_config_hash=config_sha,
            model_digests={"mock:steward_obedient": FIXTURE_SHA},
        ),
        roadmap_hash=rm_hash)
    publish.publish_request(root, cfg, request)
    codex_cfg = make_cfg(repo, root, role="codex")
    codex_watch.claim(root, codex_cfg, RID)
    codex_watch.submit_verdict(
        root, codex_cfg, make_verdict(head, RID, verdict="GO"))
    # deterministic policy continuation (state `go` -> AUTO_APPROVED)
    code = autonomy_cli.cmd_policy_continue(
        cfg, argparse.Namespace(request_id=RID))
    assert code == 0
    assert _state(root, RID) == "auto_approved"
    return root, repo, head, cfg


def test_full_mock_lifecycle_reaches_result_approved(tmp_path):
    config_path, config_sha = write_mock_config(tmp_path)
    roadmap_path = write_roadmap(tmp_path)
    root, repo, head, cfg = _drive_to_auto_approved(
        tmp_path, config_sha, roadmap_path)

    code = runner.run_task(cfg, RID, config_path, roadmap_path=roadmap_path)
    assert code == 0
    assert _state(root, RID) == "result_audit"

    chain = events.read_chain(root)
    types = [e["event_type"] for e in chain]
    for expected in ("EXPERIMENT_STARTED", "EXPERIMENT_COMPLETE",
                     "RESULT_VALIDATION_REQUIRED", "RESULT_AUDIT_REQUESTED"):
        assert expected in types
    started = next(e for e in chain
                   if e["event_type"] == "EXPERIMENT_STARTED")
    assert started["payload"]["experiment_config_hash"] == config_sha
    assert started["payload"]["roadmap_hash"]
    validated = next(e for e in chain
                     if e["event_type"] == "RESULT_VALIDATION_REQUIRED")
    assert all(v["ok"] for v in validated["payload"]["validations"])
    complete = next(e for e in chain
                    if e["event_type"] == "EXPERIMENT_COMPLETE")
    assert complete["payload"]["final_actions"] == ["execute", "verify",
                                                    "refuse"]
    # evidence exists in the scratch repo's out_root
    run_dir = os.path.join(repo, complete["payload"]["run_dir"])
    for name in ("run.json", "decisions.jsonl", "captures.jsonl"):
        assert os.path.exists(os.path.join(run_dir, name))
    # the request file moved back to claimed/ for the result audit
    assert os.path.exists(storage.safe_request_path(root, "claimed", RID))

    # Codex approves the result (generic record path — the codex_watch
    # wrapper cannot submit APPROVED, docs/AUTONOMY.md); claude advances.
    codex_cfg = make_cfg(repo, root, role="codex")
    append(root, codex_cfg, "RESULT_APPROVED", "codex", RID, repo, head,
           {"verdict": "APPROVED", "summary": "evidence checks out"})
    assert _state(root, RID) == "result_approved"
    append(root, cfg, "NEXT_MILESTONE_READY", "claude", RID, repo, head)
    assert _state(root, RID) == "next_milestone_ready"


def test_tampered_config_refused_and_pauses(tmp_path):
    config_path, config_sha = write_mock_config(tmp_path)
    roadmap_path = write_roadmap(tmp_path)
    root, repo, head, cfg = _drive_to_auto_approved(
        tmp_path, config_sha, roadmap_path)
    with open(config_path, "a", encoding="utf-8") as fh:
        fh.write("\n")
    code = runner.run_task(cfg, RID, config_path, roadmap_path=roadmap_path)
    assert code == 1
    assert _state(root, RID) == "autonomy_paused"
    last = events.read_chain(root)[-1]
    assert last["event_type"] == "AUTONOMY_PAUSED"
    assert "does not match" in last["payload"]["reason"]


def test_wrong_state_refused(tmp_path):
    config_path, config_sha = write_mock_config(tmp_path)
    roadmap_path = write_roadmap(tmp_path)
    root = make_root(tmp_path)
    repo, _initial = make_repo(tmp_path)
    seed_scratch_repo_for_mock(repo)
    head = head_of(repo)
    cfg = make_cfg(repo, root)
    policy.write_initial_policy(root)
    append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    append(root, cfg, "BUILD_READY", "claude", RID, repo, head)
    request = make_request(repo, head, RID)
    publish.publish_request(root, cfg, request)
    code = runner.run_task(cfg, RID, config_path, roadmap_path=roadmap_path)
    assert code == 1
    assert _state(root, RID) == "autonomy_paused"


def test_human_gated_task_never_runs(tmp_path):
    config_path, config_sha = write_mock_config(tmp_path)
    roadmap_path = write_roadmap(
        tmp_path, [task_fields(requires_human=True)])
    root, repo, head, cfg = _drive_to_auto_approved(
        tmp_path, config_sha, roadmap_path)
    code = runner.run_task(cfg, RID, config_path, roadmap_path=roadmap_path)
    assert code == 1
    last = events.read_chain(root)[-1]
    assert last["event_type"] == "AUTONOMY_PAUSED"
    assert "requires_human" in last["payload"]["reason"]


def test_storage_limit_enforced(tmp_path, monkeypatch):
    config_path, config_sha = write_mock_config(tmp_path)
    roadmap_path = write_roadmap(
        tmp_path, [task_fields(maximum_storage_growth_mb=1)])
    root, repo, head, cfg = _drive_to_auto_approved(
        tmp_path, config_sha, roadmap_path)

    def fat_driver(repo_path, config, deadline):
        out = os.path.join(repo_path, config["out_root"])
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "fat.bin"), "wb") as fh:
            fh.write(b"\0" * (2 * 1024 * 1024))
        return {"run_id": "fat", "run_dir": config["out_root"],
                "final_actions": [], "validations": [
                    {"name": "noop", "ok": True}]}

    monkeypatch.setitem(runner.DRIVERS, "mock_experiment", fat_driver)
    code = runner.run_task(cfg, RID, config_path, roadmap_path=roadmap_path)
    assert code == 1
    last = events.read_chain(root)[-1]
    assert last["event_type"] == "AUTONOMY_PAUSED"
    assert "storage growth" in last["payload"]["reason"]


def test_wall_clock_limit_enforced(tmp_path, monkeypatch):
    config_path, config_sha = write_mock_config(tmp_path)
    roadmap_path = write_roadmap(tmp_path)
    root, repo, head, cfg = _drive_to_auto_approved(
        tmp_path, config_sha, roadmap_path)

    ticks = iter([0.0, 10_000.0, 20_000.0, 30_000.0])

    class FakeTime:
        @staticmethod
        def monotonic():
            return next(ticks)

    monkeypatch.setattr(runner, "time", FakeTime)
    code = runner.run_task(cfg, RID, config_path, roadmap_path=roadmap_path)
    assert code == 1
    last = events.read_chain(root)[-1]
    assert last["event_type"] == "AUTONOMY_PAUSED"
    assert "wall-clock" in last["payload"]["reason"]


def test_failed_validation_pauses_before_result_audit(tmp_path, monkeypatch):
    config_path, config_sha = write_mock_config(tmp_path)
    roadmap_path = write_roadmap(tmp_path)
    root, repo, head, cfg = _drive_to_auto_approved(
        tmp_path, config_sha, roadmap_path)

    def bad_driver(repo_path, config, deadline):
        return {"run_id": "bad", "run_dir": config["out_root"],
                "final_actions": [], "validations": [
                    {"name": "offline_replay_byte_identical", "ok": False}]}

    monkeypatch.setitem(runner.DRIVERS, "mock_experiment", bad_driver)
    code = runner.run_task(cfg, RID, config_path, roadmap_path=roadmap_path)
    assert code == 1
    types = [e["event_type"] for e in events.read_chain(root)]
    assert "RESULT_VALIDATION_REQUIRED" in types
    assert "RESULT_AUDIT_REQUESTED" not in types
    assert types[-1] == "AUTONOMY_PAUSED"


def test_roadmap_pin_drift_refused(tmp_path):
    config_path, config_sha = write_mock_config(tmp_path)
    roadmap_path = write_roadmap(tmp_path)
    root, repo, head, cfg = _drive_to_auto_approved(
        tmp_path, config_sha, roadmap_path)
    with open(roadmap_path, "a", encoding="utf-8") as fh:
        fh.write("# drift after the pin\n")
    code = runner.run_task(cfg, RID, config_path, roadmap_path=roadmap_path)
    assert code == 1
    last = events.read_chain(root)[-1]
    assert last["event_type"] == "AUTONOMY_PAUSED"
    assert "pinned" in last["payload"]["reason"]
