"""Experiment registry (First Gladiator M4) — binds every experiment's
design → regimes → approvals → artifacts → replay → reports → verdicts.

The registry is the citability gate: an experiment that is not registered
(or whose registry row disagrees with its evidence) cannot be cited. Two
validation tiers reflect historical reality honestly:

- ``full``   — the manifest passes ``sweep_models.manifest_load`` full-row
  validation against the run evidence (required for every citable entry);
- ``legacy`` — DEMOTED datasets (the pilot sweep and sweep-v2) whose
  manifests predate the current row schema and are preserved AS-IS; they
  parse and count but are never citable, and their status says so.

Post-freeze mutation refusal: every frozen entry carries an ``entry_hash``
(sha256 of the canonical entry minus the hash field). Lint recomputes it —
editing a frozen entry without re-hashing (i.e. without an audited,
deliberate change) fails loudly. Held-out declarations live here too: a
held-out scenario may never appear in ANY registered manifest before the
M14 evaluation (SPEC E6); the lint enforces it mechanically.
"""
from __future__ import annotations

import hashlib
import json
import os

import yaml

from .schema import SchemaError, canonical_json

EXPERIMENTS_REGISTRY_VERSION = "1"
EXPERIMENT_STATUSES = ("exploratory", "pilot-demoted", "legacy-demoted",
                       "pre-registered", "complete")
VALIDATION_TIERS = ("full", "legacy")
GENERALIZATION_LEVELS = ("L1", "L2", "L3", "L4")


def entry_hash(entry: dict) -> str:
    """sha256 over the canonical entry with entry_hash itself excluded."""
    body = {k: v for k, v in entry.items() if k != "entry_hash"}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def load_experiments_registry(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict) or "experiments" not in raw:
        raise SchemaError(f"{os.path.basename(path)}: registry must be a "
                          "mapping with an 'experiments' list")
    if raw.get("registry_version") != EXPERIMENTS_REGISTRY_VERSION:
        raise SchemaError(f"unsupported experiments registry_version "
                          f"{raw.get('registry_version')!r}")
    return raw


def _manifest_rows_raw(path: str) -> list:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def lint_experiments_registry(registry_path: str, repo_root: str) -> list:
    """Machine-check the experiment registry. Returns issue strings
    (empty = clean)."""
    issues = []
    try:
        raw = load_experiments_registry(registry_path)
    except (SchemaError, OSError, yaml.YAMLError) as exc:
        return [f"registry unreadable: {exc}"]

    held_out = raw.get("held_out", {}) or {}
    held_ids = set(held_out.get("scenarios") or [])
    held_hashes = set(held_out.get("scenario_hashes") or [])

    entries = raw["experiments"]
    ids = [e.get("experiment_id") for e in entries]
    for eid in {i for i in ids if ids.count(i) > 1}:
        issues.append(f"duplicate experiment entry {eid!r}")

    out_root = os.path.join(repo_root, "logs", "runs")
    for e in entries:
        eid = e.get("experiment_id", "?")
        if e.get("status") not in EXPERIMENT_STATUSES:
            issues.append(f"{eid}: status {e.get('status')!r} not in "
                          f"{EXPERIMENT_STATUSES}")
        if e.get("validation") not in VALIDATION_TIERS:
            issues.append(f"{eid}: validation {e.get('validation')!r} not in "
                          f"{VALIDATION_TIERS}")
            continue
        if e.get("generalization_level") not in GENERALIZATION_LEVELS:
            issues.append(f"{eid}: generalization_level "
                          f"{e.get('generalization_level')!r} not in "
                          f"{GENERALIZATION_LEVELS}")
        # citability guard: demoted datasets may never claim full tier's
        # citable statuses, and citable statuses require full validation
        if e.get("status") in ("pre-registered", "complete") and \
                e.get("validation") != "full":
            issues.append(f"{eid}: citable status {e['status']!r} requires "
                          "validation: full")
        mpath = os.path.join(repo_root, e.get("manifest", ""))
        if not os.path.exists(mpath):
            issues.append(f"{eid}: manifest {e.get('manifest')!r} missing")
            continue
        try:
            if e["validation"] == "full":
                import sys
                scripts = os.path.join(repo_root, "scripts")
                if scripts not in sys.path:
                    sys.path.insert(0, scripts)
                from sweep_models import manifest_load
                rows = list(manifest_load(mpath, out_root).values())
                declared = e.get("interaction_mode")
                modes = {r["interaction_mode"] for r in rows}
                if modes != {declared}:
                    issues.append(f"{eid}: manifest interaction modes "
                                  f"{sorted(modes)} != declared "
                                  f"{declared!r}")
                if held_ids or held_hashes:
                    for r in rows:
                        if r["scenario"] in held_ids or \
                                r["scenario_hash"] in held_hashes:
                            issues.append(
                                f"{eid}: HELD-OUT scenario "
                                f"{r['scenario']!r} appears in the manifest "
                                "— held-out content may never be used "
                                "before the M14 evaluation (SPEC E6)")
                            break
            else:
                rows = _manifest_rows_raw(mpath)
                for r in rows:
                    sid = r.get("scenario", "")
                    if sid in held_ids or r.get("scenario_hash", "") in \
                            held_hashes:
                        issues.append(f"{eid}: HELD-OUT scenario {sid!r} "
                                      "appears in the legacy manifest")
                        break
        except (SchemaError, json.JSONDecodeError, OSError) as exc:
            issues.append(f"{eid}: manifest validation failed: "
                          f"{str(exc)[:160]}")
            continue
        if e.get("rows") != len(rows):
            issues.append(f"{eid}: declared rows {e.get('rows')} != manifest "
                          f"rows {len(rows)}")
        if e.get("frozen"):
            want = entry_hash(e)
            if e.get("entry_hash") != want:
                issues.append(f"{eid}: FROZEN entry mutated — entry_hash "
                              f"{str(e.get('entry_hash'))[:16]}… != "
                              f"recomputed {want[:16]}… (a frozen entry "
                              "changes only via an audited re-hash)")
    return issues