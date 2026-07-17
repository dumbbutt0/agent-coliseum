"""Canonical real-diff extractor (HSC-B component 8a).

Per design §6.0 the extractor never uses Git similarity heuristics. Given the
exact base and candidate trees (path -> ``(blob_sha256, git_mode)``) and the
program's predeclared pure renames, it validates each predicted rename in sorted
order (unique source/destination, source removed, destination new, identical
blob and mode), removes those paired paths, and classifies every remaining path
as ``add``/``delete``/``modify``/``mode`` from exact tree entries. An
unpredicted equal-content delete/add pair remains two changes — it is never
collapsed into a rename — so host Git rename detection cannot change the result.

The result is a sorted list of ``ACTUAL_CHANGE`` objects that satisfies the
HSC-A ``validate_actual_change`` truth table and feeds final-scope + real-diff
enforcement.
"""

from __future__ import annotations

from typing import Any, Mapping

from .core import HSCValidationError, change_sort_key, validate_actual_change

_MODES = ("100644", "100755")


def _require_entry(value: Any, where: str) -> tuple[str, str]:
    if not isinstance(value, tuple) or len(value) != 2:
        raise HSCValidationError(f"{where} must be a (blob, mode) pair")
    blob, mode = value
    if not (isinstance(blob, str) and len(blob) == 64) or mode not in _MODES:
        raise HSCValidationError(f"{where} has an invalid blob or mode")
    return blob, mode


def real_diff(base: Mapping[str, tuple[str, str]],
              candidate: Mapping[str, tuple[str, str]], *,
              predicted_renames: list[Mapping[str, Any]] | None = None) \
        -> list[dict[str, Any]]:
    """Return the sorted ``ACTUAL_CHANGE`` list from base to candidate."""
    base = {p: _require_entry(v, f"base[{p}]") for p, v in base.items()}
    candidate = {p: _require_entry(v, f"candidate[{p}]")
                 for p, v in candidate.items()}
    changes: list[dict[str, Any]] = []
    consumed_source: set[str] = set()
    consumed_dest: set[str] = set()

    renames = sorted(predicted_renames or [],
                     key=lambda r: (r["path"], r.get("rename_source") or ""))
    seen_pairs: set[tuple[str, str]] = set()
    for rename in renames:
        source = rename["rename_source"]
        dest = rename["path"]
        if source is None or source == dest:
            raise HSCValidationError("predicted rename must move between paths")
        pair = (source, dest)
        if pair in seen_pairs or source in consumed_source or \
                dest in consumed_dest:
            raise HSCValidationError("predicted rename source/dest is reused")
        seen_pairs.add(pair)
        if source not in base or dest in base or dest not in candidate or \
                source in candidate:
            raise HSCValidationError(
                "predicted rename does not match the base/candidate trees")
        if base[source] != candidate[dest]:
            raise HSCValidationError(
                "predicted rename changes content or mode (not a pure rename)")
        blob, mode = base[source]
        changes.append({
            "path": dest, "kind": "rename", "rename_source": source,
            "blob_before": blob, "blob_after": blob,
            "mode_before": mode, "mode_after": mode})
        consumed_source.add(source)
        consumed_dest.add(dest)

    for path in set(base) | set(candidate):
        if path in consumed_source or path in consumed_dest:
            continue
        in_base = path in base
        in_candidate = path in candidate
        if in_base and not in_candidate:
            blob, mode = base[path]
            changes.append({
                "path": path, "kind": "delete", "rename_source": None,
                "blob_before": blob, "blob_after": None,
                "mode_before": mode, "mode_after": None})
        elif in_candidate and not in_base:
            blob, mode = candidate[path]
            changes.append({
                "path": path, "kind": "add", "rename_source": None,
                "blob_before": None, "blob_after": blob,
                "mode_before": None, "mode_after": mode})
        else:
            (blob_before, mode_before) = base[path]
            (blob_after, mode_after) = candidate[path]
            if blob_before == blob_after and mode_before == mode_after:
                continue  # unchanged
            if blob_before != blob_after and mode_before != mode_after:
                # A combined content+mode edit is not a single frozen kind.
                raise HSCValidationError(
                    "combined content and mode change is not a single kind; "
                    "the program must express it as delete+add")
            if blob_before != blob_after:
                changes.append({
                    "path": path, "kind": "modify", "rename_source": None,
                    "blob_before": blob_before, "blob_after": blob_after,
                    "mode_before": mode_before, "mode_after": mode_after})
            else:
                changes.append({
                    "path": path, "kind": "mode", "rename_source": None,
                    "blob_before": blob_before, "blob_after": blob_after,
                    "mode_before": mode_before, "mode_after": mode_after})

    for change in changes:
        validate_actual_change(change)
    changes.sort(key=change_sort_key)
    return changes
