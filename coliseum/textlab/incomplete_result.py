"""Deterministic M8 budget-exhaustion closure artifacts.

This module is intentionally independent of the scientific analysis package.
It authenticates a stopped execution, constructs a coordinate census, and
emits only the fixed inconclusive outcome.  It has no provider adapter and no
statistics entry point.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path


PROFILE_ID = "m8_budget_exhausted_incomplete_handoff.v1"
SOURCE_REQUEST_ID = "first-gladiator-m8-phase2-live-001"
RESULT_REQUEST_ID = "first-gladiator-m8-incomplete-result-001"
EXPERIMENT_ID = "m8-phase2-live-order-sensitivity"
RUN_ID = "m8-phase2-live-001-budget-exhausted"
EVIDENCE_ROOT = "logs/runs/m8-phase2-live-order-sensitivity"
MANIFEST = f"{EVIDENCE_ROOT}/manifest.jsonl"
DERIVED_OUTPUT_ROOT = (
    "logs/results/m8-phase2-live-order-sensitivity-budget-exhausted")
MANIFEST_SHA256 = (
    "066f5166c3879dd3a265f04bbc21a9dd15c4517287ff50bdd6fd9aca89594575")
PRIMARY_FILE_COUNT = 423
PRIMARY_INVENTORY_CONTENT_HASH = (
    "28d6dede97507b386714942c55b6b992a12a65c98517442e0d3b6919bdd4ee13")
COORDINATE_CENSUS_CONTENT_HASH = (
    "79a42a4b068682b1ff2170669760a0712afdb93c62ebbedb0dc6b5e103fc4534")
PARTIAL_SNAPSHOT_SHA256 = (
    "3b7283e4760a2f8b0efd74e5ca992bae1177ad2d9073d53cad928f85634e3ce7")
PARTIAL_DECISIONS_SHA256 = (
    "f864e69922d01fe6e1dfe7ed83f407a158a8beab0f97acb22047d323d268d73a")

PRIMARY_INVENTORY_DOMAIN = (
    "coliseum:m8-budget-exhaustion-primary-inventory:v1")
COORDINATE_CENSUS_DOMAIN = (
    "coliseum:m8-budget-exhaustion-coordinate-census:v1")
PACKAGE_DOMAIN = "coliseum:m8-budget-exhaustion-package:v1"
DERIVED_BUNDLE_DOMAIN = "coliseum:m8-budget-exhaustion-derived-bundle:v1"
VALIDATION_DOMAIN = "coliseum:m8-budget-exhaustion-validation-report:v1"
REPLAY_DOMAIN = "coliseum:m8-budget-exhaustion-replay-attestation:v1"

OUTCOME = {
    "analysis_status": "budget_exhausted_incomplete",
    "scientific_verdict": "inconclusive",
    "statistics_computed": False,
    "claimable": False,
    "conclusion_scope": (
        "The frozen M8 execution did not complete within its owner-selected "
        "budget. The captured evidence is authenticated, but no order-effect "
        "or null claim is licensed."),
}
DERIVED_FILENAMES = (
    "primary_inventory.json",
    "replay_attestation.json",
    "coordinate_census.json",
    "incomplete_report.json",
    "incomplete_result_package.json",
    "validation_report.json",
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class IncompleteResultError(ValueError):
    """The stopped-execution closure inputs do not match the frozen profile."""


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def domain_hash(domain: str, value: object) -> str:
    return hashlib.sha256(
        domain.encode("ascii") + b"\0" +
        canonical_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: str | os.PathLike[str]) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def json_bytes(value: object) -> bytes:
    """Canonical, deterministic artifact bytes."""
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True,
                       allow_nan=False) + "\n").encode("utf-8")


def safe_repo_path(repo: str, relpath: str, *, may_be_absent: bool = False
                   ) -> str:
    if not isinstance(relpath, str) or not relpath or \
            relpath.startswith(("/", "\\")) or "\\" in relpath or \
            "\x00" in relpath or ".." in relpath.split("/"):
        raise IncompleteResultError("path must be safe and repository-relative")
    repo_real = os.path.realpath(repo)
    candidate = os.path.join(repo_real, relpath)
    parent = candidate if os.path.isdir(candidate) else os.path.dirname(candidate)
    probe = parent
    while may_be_absent and not os.path.lexists(probe):
        next_probe = os.path.dirname(probe)
        if next_probe == probe:
            break
        probe = next_probe
    parent_real = os.path.realpath(probe)
    if parent_real != repo_real and not parent_real.startswith(repo_real + os.sep):
        raise IncompleteResultError("path escapes the repository")
    current = repo_real
    for part in relpath.split("/")[:-1 if not os.path.isdir(candidate) else None]:
        current = os.path.join(current, part)
        if os.path.lexists(current) and os.path.islink(current):
            raise IncompleteResultError("path traverses a symbolic link")
    return candidate


def planned_coordinates(spec: dict) -> list[dict]:
    """Return the exact model-outer, interleaved M8 execution order."""
    from coliseum.textlab.sweep import cell_order

    scenario_seeds = spec.get("scenario_seeds", spec.get("seeds"))
    required = ("models", "scenarios", "sampler_seeds")
    if any(not isinstance(spec.get(k), list) or not spec[k] for k in required) \
            or not isinstance(scenario_seeds, list) or not scenario_seeds:
        raise IncompleteResultError("planned design axes must be non-empty lists")
    if spec.get("execution_order") != "interleaved":
        raise IncompleteResultError("M8 closure requires interleaved order")
    cells = cell_order(spec["scenarios"], scenario_seeds,
                       spec["sampler_seeds"], "interleaved")
    entries = []
    for model in spec["models"]:
        for scenario, scenario_seed, sampler_seed in cells:
            entries.append({
                "execution_index": len(entries),
                "model": model,
                "scenario": scenario,
                "scenario_seed": scenario_seed,
                "sampler_seed": sampler_seed,
            })
    if len(entries) != 144:
        raise IncompleteResultError(
            f"frozen coordinate grid must contain 144 runs, got {len(entries)}")
    return entries


def build_coordinate_census(spec: dict, success_rows: list[dict],
                            partial: dict) -> dict:
    planned = planned_coordinates(spec)
    by_coord = {}
    for row in success_rows:
        coord = (row.get("model"), row.get("scenario"),
                 row.get("scenario_seed"), row.get("sampler_seed"))
        if coord in by_coord:
            raise IncompleteResultError("duplicate successful coordinate")
        by_coord[coord] = row
    if len(by_coord) != 105:
        raise IncompleteResultError("closure requires exactly 105 successes")
    partial_coord = (partial.get("model"), partial.get("scenario"),
                     partial.get("scenario_seed"), partial.get("sampler_seed"))
    entries = []
    for entry in planned:
        coord = (entry["model"], entry["scenario"], entry["scenario_seed"],
                 entry["sampler_seed"])
        idx = entry["execution_index"]
        if coord in by_coord:
            classification = "success"
            if idx >= 105 or by_coord[coord].get("execution_index") != idx:
                raise IncompleteResultError(
                    "successes must occupy exact execution indices 0..104")
        elif coord == partial_coord:
            classification = "partial_nonterminal"
            if idx != 105 or partial.get("execution_index") != 105:
                raise IncompleteResultError(
                    "partial attempt must be global execution index 105")
        else:
            classification = "unattempted"
            if idx <= 105:
                raise IncompleteResultError(
                    "the first 106 coordinates are not fully accounted for")
        entries.append(dict(entry, classification=classification))
    classes = [entry["classification"] for entry in entries]
    if classes != (["success"] * 105 + ["partial_nonterminal"] +
                   ["unattempted"] * 38):
        raise IncompleteResultError("coordinate classifications drifted")
    content = {
        "schema_version": "m8-budget-exhaustion-coordinate-census.v1",
        "execution_order": "interleaved",
        "planned_runs": 144,
        "entries": entries,
    }
    return dict(content, content_hash=domain_hash(
        COORDINATE_CENSUS_DOMAIN, content))


def validate_partial_decisions(path: str) -> None:
    records = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                records.append(json.loads(line))
    if [record.get("seq") for record in records] != list(range(6)):
        raise IncompleteResultError("partial decision sequence must be 0..5")
    if [record.get("kind") for record in records] != [
            "decision_node", "outcome", "memory_update",
            "decision_node", "outcome", "memory_update"]:
        raise IncompleteResultError("partial decision cycle shape differs")
    points = [records[0].get("data", {}).get("dp_id"),
              records[3].get("data", {}).get("dp_id")]
    if points != ["e_trust", "e_betrayal"]:
        raise IncompleteResultError(
            "partial attempt must contain only trust and betrayal exposures")
    if any(record.get("data", {}).get("dp_id") in ("e_warning", "d_partner")
           for record in records):
        raise IncompleteResultError("partial attempt contains a terminal probe")


def primary_inventory(evidence_root: str, *, expected_dirs: dict[str, set[str]]
                      ) -> dict:
    """Inventory a closed primary tree without following aliases."""
    root = Path(evidence_root)
    if not root.is_dir() or root.is_symlink():
        raise IncompleteResultError("primary evidence root must be a real directory")
    actual_dirs: dict[str, set[str]] = {"": set()}
    files: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_dir = os.path.relpath(dirpath, root)
        rel_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, "/")
        if rel_dir not in expected_dirs:
            raise IncompleteResultError(f"unexpected primary directory {rel_dir!r}")
        for dirname in dirnames:
            path = os.path.join(dirpath, dirname)
            if os.path.islink(path):
                raise IncompleteResultError("primary tree contains a symbolic link")
            mode = os.lstat(path).st_mode
            if not stat.S_ISDIR(mode):
                raise IncompleteResultError("primary tree contains a special node")
        names = set(filenames)
        if names != expected_dirs[rel_dir]:
            raise IncompleteResultError(
                f"primary directory {rel_dir!r} member set differs")
        actual_dirs[rel_dir] = names
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            info = os.lstat(path)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise IncompleteResultError(
                    "primary files must be regular and have link count one")
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            files[rel] = file_sha256(path)
    if set(actual_dirs) != set(expected_dirs):
        raise IncompleteResultError("primary directory inventory differs")
    content = {
        "schema_version": "m8-budget-exhaustion-primary-inventory.v1",
        "evidence_root": EVIDENCE_ROOT,
        "file_count": len(files),
        "files": dict(sorted(files.items())),
    }
    return dict(content, content_hash=domain_hash(
        PRIMARY_INVENTORY_DOMAIN, content))


def incomplete_report() -> dict:
    return {
        "schema_version": "m8-budget-exhaustion-incomplete-report.v1",
        **OUTCOME,
        "expected_runs": 144,
        "successful_runs": 105,
        "partial_runs": 1,
        "unattempted_runs": 38,
        "tombstoned_runs": 0,
        "terminal_outcomes": 105,
    }


def derived_bundle_hash(file_hashes: dict[str, str]) -> str:
    if set(file_hashes) != set(DERIVED_FILENAMES):
        raise IncompleteResultError("derived bundle must contain exactly six files")
    if any(not _SHA256.fullmatch(value) for value in file_hashes.values()):
        raise IncompleteResultError("derived bundle contains a malformed hash")
    return domain_hash(DERIVED_BUNDLE_DOMAIN, dict(sorted(file_hashes.items())))


def validation_report(validations: list[str]) -> dict:
    if not isinstance(validations, list) or not validations or \
            any(not isinstance(item, str) or not item for item in validations):
        raise IncompleteResultError("validations must be non-empty strings")
    content = {
        "schema_version": "m8-budget-exhaustion-validation-report.v1",
        "validations": validations,
    }
    return dict(content, content_hash=domain_hash(VALIDATION_DOMAIN, content))


def replay_attestation(core: dict) -> dict:
    if not isinstance(core, dict) or set(core) != {
            "manifest_sha256", "tombstone_ledger", "runs"}:
        raise IncompleteResultError("provider-free replay core shape differs")
    if core["manifest_sha256"] != MANIFEST_SHA256 or \
            core["tombstone_ledger"] != {"state": "absent", "sha256": None} or \
            not isinstance(core["runs"], dict) or len(core["runs"]) != 105 or \
            any(record.get("replay_ok") is not True
                for record in core["runs"].values()):
        raise IncompleteResultError("provider-free replay core differs")
    content = {
        "schema_version": "m8-budget-exhaustion-replay-attestation.v1",
        **core,
        "successful_runs": 105,
    }
    return dict(content, content_hash=domain_hash(REPLAY_DOMAIN, content))
