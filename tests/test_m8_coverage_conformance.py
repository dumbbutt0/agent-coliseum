"""Coverage-map changed-path conformance (audit e-002 finding 0).

The finding: the base->target changed-path set exceeded the frozen coverage-map
union — four undeclared runtime/operator/executor surfaces reached the diff with
no predeclared audit ownership. A coverage map that a reader trusts to enumerate
"everything this candidate touches" is only trustworthy if a machine enforces
that it is exact.

This test binds the human-readable coverage map to a machine-readable allowlist
(docs/first-gladiator/M8-CHANGED-PATH-ALLOWLIST.json) and asserts that the
allowlist equals `git diff --name-only <base> <integrated-M8>` EXACTLY — committed content
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
INTEGRATED_M8 = "1e4cc64dab1b0f5dec71c80411367738c11ad37b"
ALLOWLIST_FILE_SHA256 = (
    "1a8b05d78b0df9647260673757f30e409600c695b5efcdad60cebc378759cb88")
CLOSURE_PATHS = {
    "docs/first-gladiator/M8-BUDGET-EXHAUSTION-CLOSURE.md",
    "docs/AUTONOMY.md",
    "coliseum/textlab/sweep.py",
    "coliseum/textlab/incomplete_result.py",
    "tools/council/m8_incomplete_handoff.py",
    "tools/council/publish.py",
    "tools/council/result_handoff.py",
    "tools/council/state_machine.py",
    "tools/council/schemas.py",
    "tools/council/events.py",
    "tools/council/cli.py",
    "tools/autonomy/resume.py",
    "tests/test_m8_incomplete_handoff.py",
    "tests/test_council_result_handoff.py",
    "tests/test_m8_coverage_conformance.py",
    "tests/test_m8_operator_surface.py",
}


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
    assert hashlib.sha256(open(ALLOWLIST, "rb").read()).hexdigest() == \
        ALLOWLIST_FILE_SHA256


def test_committed_m8_diff_equals_the_frozen_allowlist():
    """`git diff --name-only base INTEGRATED_M8` stays frozen, exactly.

    Committed content only: gitignored logs/derived evidence never appear in a
    name-only diff, so they cannot be an undeclared surface. A candidate that
    touches any runtime path not in the allowlist fails here before it can be
    published for audit."""
    a = _load()
    base = a["base_commit"]
    proc = subprocess.run(
        ["git", "-C", REPO, "diff", "--name-only", base, INTEGRATED_M8],
        capture_output=True, text=True)
    assert proc.returncode == 0, f"git diff failed: {proc.stderr}"
    actual = sorted(p for p in proc.stdout.splitlines() if p.strip())
    declared = a["paths"]
    undeclared = sorted(set(actual) - set(declared))
    stale = sorted(set(declared) - set(actual))
    assert not undeclared, f"undeclared changed paths (add to allowlist or revert): {undeclared}"
    assert not stale, f"allowlist declares paths not actually changed: {stale}"


def test_closure_head_descends_from_integrated_m8():
    proc = subprocess.run(
        ["git", "-C", REPO, "merge-base", "--is-ancestor",
         INTEGRATED_M8, "HEAD"])
    assert proc.returncode == 0


def test_closure_committed_diff_matches_section8_allowlist():
    proc = subprocess.run(
        ["git", "-C", REPO, "diff", "--name-only", INTEGRATED_M8, "HEAD"],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    actual = {path for path in proc.stdout.splitlines() if path}
    assert actual <= CLOSURE_PATHS, sorted(actual - CLOSURE_PATHS)
    # Before the closure commit is created the committed diff is empty. At the
    # audited closure commit all declared paths must be present.
    if actual:
        assert actual == CLOSURE_PATHS, sorted(CLOSURE_PATHS - actual)
