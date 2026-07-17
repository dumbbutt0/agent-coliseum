"""Real-diff extractor proofs (HSC-B component 8a)."""

from __future__ import annotations

import pytest

from tools.section_council.core import HSCValidationError
from tools.section_council.diff import real_diff

A = "a" * 64
B = "b" * 64
C = "c" * 64


def _kinds(changes):
    return {(c["path"], c["kind"]) for c in changes}


def test_every_change_kind_is_classified():
    base = {"keep": (A, "100644"), "del": (B, "100644"),
            "mod": (A, "100644"), "chmod": (A, "100644")}
    candidate = {"keep": (A, "100644"), "add": (C, "100755"),
                 "mod": (B, "100644"), "chmod": (A, "100755")}
    changes = real_diff(base, candidate)
    assert _kinds(changes) == {
        ("add", "add"), ("del", "delete"), ("mod", "modify"),
        ("chmod", "mode")}
    add = next(c for c in changes if c["path"] == "add")
    assert (add["blob_after"], add["mode_after"]) == (C, "100755")
    assert add["blob_before"] is None and add["mode_before"] is None
    mode = next(c for c in changes if c["path"] == "chmod")
    assert mode["blob_before"] == mode["blob_after"] == A
    assert (mode["mode_before"], mode["mode_after"]) == ("100644", "100755")
    # sorted by (path, kind, rename_source)
    assert [c["path"] for c in changes] == sorted(c["path"] for c in changes)


def test_predicted_pure_rename_is_recognized():
    base = {"old": (A, "100644"), "stable": (B, "100644")}
    candidate = {"new": (A, "100644"), "stable": (B, "100644")}
    # without prediction: two changes (delete old + add new + the typo path)
    plain = real_diff(base, candidate)
    assert ("old", "delete") in _kinds(plain)
    assert ("new", "add") in _kinds(plain)
    # with the predicted rename: exactly one rename change for old->new
    renamed = real_diff(base, candidate, predicted_renames=[
        {"path": "new", "rename_source": "old"}])
    rename = [c for c in renamed if c["kind"] == "rename"]
    assert len(rename) == 1
    assert rename[0]["rename_source"] == "old" and rename[0]["path"] == "new"
    assert rename[0]["blob_before"] == rename[0]["blob_after"] == A
    assert not any(c["path"] in ("old", "new") and c["kind"] in ("add", "delete")
                   for c in renamed)


def test_equal_content_delete_add_is_not_collapsed_without_prediction():
    base = {"x": (A, "100644")}
    candidate = {"y": (A, "100644")}
    changes = real_diff(base, candidate)  # no predicted rename
    assert _kinds(changes) == {("x", "delete"), ("y", "add")}
    assert not any(c["kind"] == "rename" for c in changes)


def test_rename_that_changes_content_refuses():
    base = {"old": (A, "100644")}
    candidate = {"new": (B, "100644")}
    with pytest.raises(HSCValidationError, match="pure rename"):
        real_diff(base, candidate,
                  predicted_renames=[{"path": "new", "rename_source": "old"}])


def test_rename_not_matching_trees_refuses():
    base = {"old": (A, "100644")}
    candidate = {"old": (A, "100644")}  # source still present
    with pytest.raises(HSCValidationError, match="base/candidate"):
        real_diff(base, candidate,
                  predicted_renames=[{"path": "new", "rename_source": "old"}])


def test_combined_content_and_mode_change_refuses():
    base = {"f": (A, "100644")}
    candidate = {"f": (B, "100755")}
    with pytest.raises(HSCValidationError, match="combined content and mode"):
        real_diff(base, candidate)


def test_finding5_malformed_unchanged_entry_fails_closed():
    # Regression (audit 001635 finding 5): a malformed entry that happens to be
    # identical in base and candidate (so it is "unchanged" and never reaches
    # per-change classification) must still fail closed up front — an invalid
    # path or digest cannot ride through by being unchanged.
    bad_digest = {"f": ("zz", "100644")}  # not a 64-hex blob
    with pytest.raises(HSCValidationError):
        real_diff(bad_digest, bad_digest)
    bad_path = {"../escape": (A, "100644")}
    with pytest.raises(HSCValidationError, match="path"):
        real_diff(bad_path, bad_path)


def test_identical_trees_yield_no_changes():
    tree = {"a": (A, "100644"), "b": (B, "100755")}
    assert real_diff(tree, dict(tree)) == []
