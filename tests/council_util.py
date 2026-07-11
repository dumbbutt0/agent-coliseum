"""Shared builders for the council test suites. NOT a test module.

Every helper works against throwaway tmp_path roots and scratch git repos —
the real council directory is never touched by tests."""
from __future__ import annotations

import os
import subprocess

from tools.council import Config, events, storage

TEST_COMMAND = "python3 -m pytest tests/ -q"


def make_root(tmp_path) -> str:
    root = str(tmp_path / "council")
    os.makedirs(root, exist_ok=True)
    storage.ensure_layout(root)
    with open(os.path.join(root, "log.md"), "w", encoding="utf-8") as fh:
        fh.write("STATUS: active\n\n# test council log\n")
    return root


def make_repo(tmp_path, name: str = "repo") -> tuple:
    """(repo_path, head_commit) — a one-commit scratch git repo."""
    repo = str(tmp_path / name)
    os.makedirs(repo, exist_ok=True)
    subprocess.run(["git", "-C", repo, "init", "-q"], check=True)
    with open(os.path.join(repo, "f.txt"), "w", encoding="utf-8") as fh:
        fh.write("content\n")
    subprocess.run(["git", "-C", repo, "add", "f.txt"], check=True)
    subprocess.run(["git", "-C", repo, "-c", "user.email=t@t",
                    "-c", "user.name=t", "commit", "-qm", "init"],
                   check=True)
    head = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                          capture_output=True, text=True,
                          check=True).stdout.strip()
    return repo, head


def make_cfg(repo: str, root: str, role: str = "claude") -> Config:
    return Config(council_root=root, repo_roots=(repo,), role=role)


def make_request(repo: str, head: str, request_id: str = "test-req-001",
                 **overrides) -> dict:
    request = {
        "request_id": request_id,
        "protocol_version": "1.0",
        "repository": repo,
        "target_commit": head,
        "require_clean_tree": True,
        "expected_test_command": TEST_COMMAND,
        "expected_test_count": 147,
        "scope": ["scope item"],
        "questions": ["question?"],
        "allowed_actions": ["read source", "run allowlisted tests"],
        "forbidden_actions": ["destructive_tools", "cloud_apis",
                              "website_automation", "weight_training"],
        "requested_verdicts": ["AUDIT_BLOCKED", "AUDIT_GO",
                               "AUDIT_GO_WITH_CONDITIONS"],
        "live_experiment_allowed": False,
        "human_approval_required": True,
        "originating_blocked_commit": head,
        "blockers_addressed": ["blocker one"],
    }
    request.update(overrides)
    return request


def make_verdict(head: str, request_id: str = "test-req-001",
                 verdict: str = "GO", **overrides) -> dict:
    body = {
        "request_id": request_id,
        "audited_commit": head,
        "audit_mode": "narrow",
        "working_tree_clean": True,
        "tests_observed": 147,
        "verdict": verdict,
        "summary": "test verdict",
        "blockers": [],
        "conditions": [],
        "findings": [],
        "commands_run": [TEST_COMMAND],
        "timestamp_utc": storage.utc_now(),
    }
    body.update(overrides)
    return body


def make_autonomy_block(**overrides) -> dict:
    block = {
        "experiment_class": "sandbox_local",
        "experiment_config_hash": "a" * 64,
        "data_sources": ["synthetic"],
        "model_digests": {"model-a": "sha256:" + "b" * 64},
        "limits": {"max_compute_minutes": 60, "max_wall_minutes": 60,
                   "max_storage_mb": 512, "max_retries_per_unit": 2,
                   "max_scenarios": 10},
        "offline_replay_supported": True,
    }
    block.update(overrides)
    return block


def append(root: str, cfg: Config, event_type: str, sender: str,
           request_id: str, repo: str, commit: str, payload=None) -> dict:
    return events.append_event(root, cfg, event_type, sender, request_id,
                               repo, commit, payload or {})


def drive_to_claimed(root, cfg, repo, head, request_id="test-req-001",
                     **request_overrides) -> dict:
    """BUILD_STARTED..AUDIT_CLAIMED via the real publish/claim paths."""
    from tools.council import codex_watch, publish
    append(root, cfg, "BUILD_STARTED", "claude", request_id, repo, head)
    append(root, cfg, "BUILD_READY", "claude", request_id, repo, head)
    request = make_request(repo, head, request_id, **request_overrides)
    publish.publish_request(root, cfg, request, reaudit=False)
    _event, lock = codex_watch.claim(root, cfg, request_id)
    return {"request": request, "lock": lock}
