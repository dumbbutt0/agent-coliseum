"""Read-only git interrogation. Fixed argv lists, never shell=True, and the
repository path is validated against the configured roots before any call —
council request content can never smuggle a path or a flag in here."""
from __future__ import annotations

import subprocess

from tools.council.schemas import CouncilError, validate_commit, \
    validate_repository


def _git(repo: str, args: list, repo_roots) -> subprocess.CompletedProcess:
    validate_repository(repo, repo_roots)
    return subprocess.run(["git", "-C", repo] + args, capture_output=True,
                          text=True, timeout=30)


def head_commit(repo: str, repo_roots) -> str:
    proc = _git(repo, ["rev-parse", "HEAD"], repo_roots)
    if proc.returncode != 0:
        raise CouncilError(f"git rev-parse failed in {repo}: {proc.stderr.strip()}")
    return validate_commit(proc.stdout.strip())


def is_clean(repo: str, repo_roots) -> bool:
    proc = _git(repo, ["status", "--porcelain"], repo_roots)
    if proc.returncode != 0:
        raise CouncilError(f"git status failed in {repo}: {proc.stderr.strip()}")
    return proc.stdout.strip() == ""


def commit_exists(repo: str, commit: str, repo_roots) -> bool:
    validate_commit(commit)
    proc = _git(repo, ["cat-file", "-e", commit + "^{commit}"], repo_roots)
    return proc.returncode == 0
