"""Coverage-map changed-path conformance (audit e-002 finding 0).

The finding: the base->target changed-path set exceeded the frozen coverage-map
union — four undeclared runtime/operator/executor surfaces reached the diff with
no predeclared audit ownership. A coverage map that a reader trusts to enumerate
"everything this candidate touches" is only trustworthy if a machine enforces
that it is exact.

This test binds the human-readable coverage map to a machine-readable allowlist
(docs/first-gladiator/M8-CHANGED-PATH-ALLOWLIST.json) and asserts that the
allowlist equals `git diff --name-only <base> HEAD` EXACTLY — committed content
only, so gitignored evidence trees never appear and cannot smuggle a surface in.
Any path added to the candidate without being declared here fails closed; any
declared path that is not actually changed also fails (the allowlist cannot rot
ahead of the diff). The allowlist is self-inclusive: it lists itself and this
test, because both are part of the commit.
"""
import hashlib
import json
import os
import subprocess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWLIST = os.path.join(REPO, "docs", "first-gladiator",
                         "M8-CHANGED-PATH-ALLOWLIST.json")


def _load():
    with open(ALLOWLIST, encoding="utf-8") as fh:
        return json.load(fh)


def test_allowlist_is_internally_consistent():
    a = _load()
    paths = a["paths"]
    assert paths == sorted(set(paths)), "paths must be sorted and unique"
    assert a["path_count"] == len(paths)
    assert a["paths_sha256"] == hashlib.sha256(
        "\n".join(paths).encode()).hexdigest()
    # self-inclusive: the allowlist and this test are part of the commit
    assert "docs/first-gladiator/M8-CHANGED-PATH-ALLOWLIST.json" in paths
    assert "tests/test_m8_coverage_conformance.py" in paths


def test_committed_diff_equals_the_frozen_allowlist():
    """`git diff --name-only base HEAD` == the frozen allowlist, exactly.

    Committed content only: gitignored logs/derived evidence never appear in a
    name-only diff, so they cannot be an undeclared surface. A candidate that
    touches any runtime path not in the allowlist fails here before it can be
    published for audit."""
    a = _load()
    base = a["base_commit"]
    proc = subprocess.run(
        ["git", "-C", REPO, "diff", "--name-only", base, "HEAD"],
        capture_output=True, text=True)
    assert proc.returncode == 0, f"git diff failed: {proc.stderr}"
    actual = sorted(p for p in proc.stdout.splitlines() if p.strip())
    declared = a["paths"]
    undeclared = sorted(set(actual) - set(declared))
    stale = sorted(set(declared) - set(actual))
    assert not undeclared, f"undeclared changed paths (add to allowlist or revert): {undeclared}"
    assert not stale, f"allowlist declares paths not actually changed: {stale}"
