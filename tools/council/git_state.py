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


def has_only_untracked_paths(repo: str, expected_paths, repo_roots) -> bool:
    """True only when porcelain contains exactly the named untracked files.

    ``--untracked-files=all`` prevents Git from collapsing an untracked
    directory to one entry.  ``-z`` makes paths unquoted and NUL-delimited, so
    the comparison is exact even when a repository permits unusual names.
    Every tracked/index status, rename/copy record, or extra path refuses.
    """
    if not isinstance(expected_paths, (set, frozenset, tuple, list)) or \
            any(not isinstance(path, str) or not path or "\x00" in path or
                path.startswith("/") or ".." in path.split("/")
                for path in expected_paths):
        raise CouncilError("expected untracked path set is invalid")
    expected = set(expected_paths)
    if len(expected) != len(tuple(expected_paths)):
        raise CouncilError("expected untracked paths contain duplicates")
    proc = _git(repo, ["status", "--porcelain=v1", "-z",
                       "--untracked-files=all"], repo_roots)
    if proc.returncode != 0:
        raise CouncilError(f"git status failed in {repo}: {proc.stderr.strip()}")
    records = proc.stdout.split("\x00")
    if records and records[-1] == "":
        records.pop()
    observed = set()
    for record in records:
        if not record.startswith("?? ") or len(record) <= 3:
            return False
        path = record[3:]
        if path in observed:
            return False
        observed.add(path)
    return observed == expected


def commit_exists(repo: str, commit: str, repo_roots) -> bool:
    validate_commit(commit)
    proc = _git(repo, ["cat-file", "-e", commit + "^{commit}"], repo_roots)
    return proc.returncode == 0


def is_ancestor(ancestor: str, descendant: str, repo: str, repo_roots) -> bool:
    """True only when both exact commits exist and git proves ancestry."""
    validate_commit(ancestor)
    validate_commit(descendant)
    proc = _git(repo, ["merge-base", "--is-ancestor", ancestor, descendant],
                repo_roots)
    if proc.returncode not in (0, 1):
        raise CouncilError(
            f"git merge-base failed in {repo}: {proc.stderr.strip()}")
    return proc.returncode == 0


def changed_paths(repo: str, commit: str, repo_roots) -> list:
    """The repo-relative paths the EXACT `commit` changed versus its parent
    (or, for a root commit, every path it introduced). This is the
    AUTHORITATIVE boundary for delegated protected-path enforcement — the
    audited commit's real diff, never the builder's free-form request prose
    (which is forgeable: a benign scope can hide a protocol change).

    Fail-closed by construction: a MERGE commit (>1 parent) has an ambiguous
    changed-path set and raises; any git failure raises. Callers treat a raise
    as 'refuse'."""
    validate_commit(commit)
    parents = _git(repo, ["rev-list", "--parents", "-n", "1", commit],
                   repo_roots)
    if parents.returncode != 0:
        raise CouncilError(
            f"git rev-list failed for {commit[:12]} in {repo}: "
            f"{parents.stderr.strip()}")
    n_parents = max(0, len(parents.stdout.split()) - 1)
    if n_parents > 1:
        raise CouncilError(
            f"commit {commit[:12]} is a merge ({n_parents} parents) — its "
            "changed-path set is ambiguous; delegation fails closed")
    # --root makes a root commit list every file it introduced; a non-root
    # commit still diffs against its (single) parent. --no-commit-id -r gives
    # a flat, one-path-per-line listing.
    proc = _git(repo, ["diff-tree", "--no-commit-id", "--name-only", "-r",
                       "--root", commit], repo_roots)
    if proc.returncode != 0:
        raise CouncilError(
            f"git diff-tree failed for {commit[:12]} in {repo}: "
            f"{proc.stderr.strip()}")
    return [p for p in proc.stdout.splitlines() if p.strip()]
