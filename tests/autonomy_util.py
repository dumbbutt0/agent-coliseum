"""Shared builders for the autonomy test suites. NOT a test module.

Everything works against throwaway tmp_path council roots and scratch git
repos (tests/council_util.py) — the real council root, the real roadmap,
and the real repo are never touched.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess

from tools.council import policy

REAL_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def policy_doc() -> dict:
    """The DEFAULT_POLICY shape, as load_policy would return it."""
    doc = json.loads(json.dumps(policy.DEFAULT_POLICY))
    doc["created_utc"] = "2026-07-11T00:00:00.000Z"
    return doc


def task_fields(**overrides) -> dict:
    task = {
        "task_id": "t-mock",
        "title": "harmless mock lifecycle",
        "phase": "phase-0",
        "status": "ready",
        "dependencies": [],
        "allowed_files": ["logs/runs/"],
        "forbidden_files": ["tools/council/", "autonomy_policy.json",
                            "PROTOCOL.md"],
        "audit_scope": "mock lifecycle",
        "experiment_class": "mock_experiment",
        "maximum_fix_cycles": 5,
        "maximum_runtime_minutes": 15,
        "maximum_storage_growth_mb": 1024,
        "expected_tests": "pytest green",
        "success_criteria": ["replay byte-identical"],
        "failure_criteria": ["replay mismatch"],
        "evidence_required": ["run dir"],
        "requires_human": False,
        "next_tasks": [],
    }
    task.update(overrides)
    return task


def _render_value(value) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def roadmap_text(tasks=None) -> str:
    """Render tasks into the strict YAML subset the loader accepts."""
    tasks = tasks if tasks is not None else [task_fields()]
    lines = ['roadmap_version: "1"', "milestone: society-substrate",
             "tasks:"]
    for task in tasks:
        first = True
        for key, value in task.items():
            prefix = "  - " if first else "    "
            first = False
            if isinstance(value, list):
                if not value:
                    lines.append(f"{prefix}{key}: []")
                else:
                    lines.append(f"{prefix}{key}:")
                    for item in value:
                        lines.append(f"      - {item}")
            else:
                lines.append(f"{prefix}{key}: {_render_value(value)}")
    return "\n".join(lines) + "\n"


def write_roadmap(tmp_path, tasks=None) -> str:
    path = str(tmp_path / "autonomy-roadmap.yaml")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(roadmap_text(tasks))
    return path


def seed_scratch_repo_for_mock(repo: str) -> None:
    """Give a scratch git repo the files the mock driver needs: the
    corrupt_king scenario (copied from the real repo) and a .gitignore so
    evidence keeps the tree clean, then commit."""
    os.makedirs(os.path.join(repo, "configs", "scenarios"), exist_ok=True)
    shutil.copy(os.path.join(REAL_REPO, "configs", "scenarios",
                             "corrupt_king.yaml"),
                os.path.join(repo, "configs", "scenarios",
                             "corrupt_king.yaml"))
    with open(os.path.join(repo, ".gitignore"), "w", encoding="utf-8") as fh:
        fh.write("logs/\n")
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    subprocess.run(["git", "-C", repo, "-c", "user.email=t@t", "-c",
                    "user.name=t", "commit", "-qm", "mock assets"],
                   check=True)


def head_of(repo: str) -> str:
    return subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                          capture_output=True, text=True,
                          check=True).stdout.strip()


def write_mock_config(tmp_path, **overrides) -> tuple:
    """(path, sha256). The frozen mock experiment configuration."""
    config = {
        "task_id": "t-mock",
        "driver": "mock_experiment",
        "scenario": "configs/scenarios/corrupt_king.yaml",
        "agent": "llm:mock:steward_obedient",
        "scenario_seed": 42,
        "out_root": "logs/runs",
        "expected_final_actions": ["execute", "verify", "refuse"],
    }
    config.update(overrides)
    path = str(tmp_path / "experiment.json")
    body = json.dumps(config, indent=2, sort_keys=True) + "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return path, hashlib.sha256(body.encode("utf-8")).hexdigest()
