"""Deterministic resume: same chain + same roadmap => same next action.
Read-only — computing a resume never appends events."""
import os

from tests.autonomy_util import task_fields, write_roadmap
from tests.council_util import (append, make_autonomy_block, make_cfg,
                                make_repo, make_request, make_root,
                                make_verdict)
from tools.autonomy import resume
from tools.council import codex_watch, events, policy, publish

RID = "autonomy-resume-test-001"


def _base(tmp_path):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    policy.write_initial_policy(root)
    roadmap_path = write_roadmap(tmp_path)
    return root, repo, head, cfg, roadmap_path


def test_empty_chain_points_at_first_eligible_task(tmp_path):
    root, repo, head, cfg, rm_path = _base(tmp_path)
    out = resume.compute_resume(cfg, rm_path)
    assert out["ok"]
    assert out["roadmap"]["eligible_tasks"] == ["t-mock"]
    assert out["current"]["request_id"] is None
    assert "t-mock" in out["current"]["next_action"]


def test_resume_is_deterministic_and_read_only(tmp_path):
    root, repo, head, cfg, rm_path = _base(tmp_path)
    append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    before = open(os.path.join(root, "events.jsonl"), "rb").read()
    a = resume.compute_resume(cfg, rm_path)
    b = resume.compute_resume(cfg, rm_path)
    assert a["requests"] == b["requests"]
    assert a["current"] == b["current"]
    assert open(os.path.join(root, "events.jsonl"), "rb").read() == before


def test_resume_tracks_states_through_the_lifecycle(tmp_path):
    root, repo, head, cfg, rm_path = _base(tmp_path)
    append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    out = resume.compute_resume(cfg, rm_path)
    assert out["requests"][RID]["state"] == "building"
    assert "BUILD_READY" in out["requests"][RID]["next_action"]

    append(root, cfg, "BUILD_READY", "claude", RID, repo, head)
    request = make_request(repo, head, RID, human_approval_required=False,
                           autonomy=make_autonomy_block())
    publish.publish_request(root, cfg, request)
    out = resume.compute_resume(cfg, rm_path)
    assert out["requests"][RID]["state"] == "requested"
    assert out["requests"][RID]["next_actor"] == "codex"

    codex_cfg = make_cfg(repo, root, role="codex")
    codex_watch.claim(root, codex_cfg, RID)
    codex_watch.submit_verdict(root, codex_cfg,
                               make_verdict(head, RID, verdict="GO"))
    out = resume.compute_resume(cfg, rm_path)
    assert out["requests"][RID]["state"] == "go"
    assert "policy-continue" in out["requests"][RID]["next_action"]
    assert out["current"]["request_id"] == RID

    append(root, cfg, "POLICY_VALIDATION_REQUIRED", "claude", RID, repo,
           head, {"policy_hash": None})
    append(root, cfg, "AUTO_APPROVED", "claude", RID, repo, head)
    out = resume.compute_resume(cfg, rm_path)
    assert "run-task" in out["requests"][RID]["next_action"]
    assert RID in out["requests"][RID]["next_action"]


def test_resume_surfaces_crash_mid_experiment(tmp_path):
    root, repo, head, cfg, rm_path = _base(tmp_path)
    append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    append(root, cfg, "BUILD_READY", "claude", RID, repo, head)
    request = make_request(repo, head, RID, human_approval_required=False,
                           autonomy=make_autonomy_block())
    publish.publish_request(root, cfg, request)
    codex_cfg = make_cfg(repo, root, role="codex")
    codex_watch.claim(root, codex_cfg, RID)
    codex_watch.submit_verdict(root, codex_cfg,
                               make_verdict(head, RID, verdict="GO"))
    append(root, cfg, "POLICY_VALIDATION_REQUIRED", "claude", RID, repo,
           head, {"policy_hash": None})
    append(root, cfg, "AUTO_APPROVED", "claude", RID, repo, head)
    append(root, cfg, "EXPERIMENT_STARTED", "claude", RID, repo, head,
           {"task_id": "t-mock"})
    out = resume.compute_resume(cfg, rm_path)
    assert out["requests"][RID]["state"] == "experiment_running"
    assert "CRASHED MID-EXPERIMENT" in out["requests"][RID]["next_action"]


def test_resume_reports_broken_chain_without_crashing(tmp_path):
    root, repo, head, cfg, rm_path = _base(tmp_path)
    append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    with open(os.path.join(root, "events.jsonl"), "a",
              encoding="utf-8") as fh:
        fh.write('{"tampered": true}\n')
    out = resume.compute_resume(cfg, rm_path)
    assert not out["ok"]
    assert not out["chain"]["ok"]


def test_resume_render_names_the_next_actor(tmp_path):
    root, repo, head, cfg, rm_path = _base(tmp_path)
    text = resume.render(resume.compute_resume(cfg, rm_path))
    assert "NEXT: [claude]" in text


def test_resume_never_recommends_a_human_gated_task(tmp_path):
    """Audit finding 3: with only a human-gated task ready, resume must
    hand the next action to the HUMAN, not recommend autonomous work."""
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    policy.write_initial_policy(root)
    rm_path = write_roadmap(tmp_path,
                            [task_fields(requires_human=True)])
    out = resume.compute_resume(cfg, rm_path)
    assert out["roadmap"]["eligible_tasks"] == []
    assert out["roadmap"]["human_gated_ready"] == ["t-mock"]
    assert out["current"]["next_actor"] == "human"
    assert "t-mock" in out["current"]["next_action"]
