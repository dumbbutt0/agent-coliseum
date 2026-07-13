"""T0-A group-aware partition machinery (§8 of the training-annex, BLOCKER 3).

Random row-level splitting can place close siblings (paraphrase variants, control
twins, same-family scenarios) on both sides of a train/development/validation
split and inflate T1-T3 performance. This module assigns whole *partition groups*
to splits so that no sibling relation straddles a split, and provides an
independent leakage lint that FAILS on any straddle.

Faithful to §8:
  - A versioned `partition_group_id` binds the sibling-making field. §8 states "a
    scenario family ... never straddles a split", so the co-assignment unit is the
    registry `family` (the coarsest sibling relation); control twins and paraphrase
    variants live *inside* a family, so they are kept together by construction.
  - All members of a group are assigned to the same split together.
  - Assignment is DETERMINISTIC, dataset-version-bound (the split spec + schema
    versions seed it), and included in the dataset commitment.
  - A retry or alternate rendering cannot cross a split by acquiring a new row
    identity: a split is keyed on the scenario's group, never on a run/row id, so
    every attempt of a scenario lands in the same split.
  - Exact/retry de-duplication is already performed upstream (manifest_load +
    effective-unit collapse). At FAMILY granularity, any near-duplicate is either
    within a family (same split — safe) or across families (not a near-duplicate by
    construction), so cross-split near-duplicate leakage is structurally impossible;
    this limitation and its rationale are recorded in the partition provenance.

No labels, no training — this is structural T0-A machinery.
"""
from __future__ import annotations

import os

import yaml

from .schema import config_hash

PARTITION_SCHEME_VERSION = "1"
PARTITION_GROUP_DOMAIN = "dataset:partition_group:v1"
PARTITION_ASSIGN_DOMAIN = "dataset:partition_assign:v1"

# train/development/validation (final hidden evaluation stays in the held-out
# registry, refused from any exported dataset — see dataset_export held-out gate).
DEFAULT_SPLITS = (("train", 0.70), ("development", 0.15), ("validation", 0.15))


def load_scenario_siblings(registry_path):
    """{scenario_id: {"family", "control_of", "variants"}} from the scenario
    registry — the sibling-identity fields §8 partitions on."""
    raw = yaml.safe_load(open(registry_path, encoding="utf-8"))
    out = {}
    for e in raw.get("scenarios", []):
        out[e["scenario_id"]] = {
            "family": e.get("family"),
            "control_of": e.get("control_of") or "",
            "variants": list(e.get("variants") or []),
        }
    return out


def _validate_splits(splits):
    if not splits:
        raise ValueError("splits must be non-empty")
    names = [n for n, _ in splits]
    if len(names) != len(set(names)):
        raise ValueError(f"duplicate split name in {names}")
    weights = [w for _, w in splits]
    if any(w <= 0 for w in weights):
        raise ValueError(f"split weights must be positive: {weights}")
    total = sum(weights)
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"split weights must sum to 1.0 (got {total})")


def partition_group_id(family):
    """The versioned, content-addressed id of the partition group a scenario
    belongs to. The co-assignment unit is the registry family (§8)."""
    if not family:
        raise ValueError("scenario has no registry family — cannot partition "
                         "(a missing family is a provenance gap, fail closed)")
    return config_hash({"domain": PARTITION_GROUP_DOMAIN,
                        "partition_scheme_version": PARTITION_SCHEME_VERSION,
                        "family": family})


def _assign_split(group_id, splits, seed):
    """Deterministic split for a group: a domain-separated hash of (seed, group)
    mapped into the cumulative-weight buckets. dataset-version-bound via `seed`."""
    h = config_hash({"domain": PARTITION_ASSIGN_DOMAIN, "seed": seed,
                     "partition_group_id": group_id})
    frac = int(h[:15], 16) / float(1 << 60)
    cumulative = 0.0
    for name, weight in splits:
        cumulative += weight
        if frac < cumulative:
            return name
    return splits[-1][0]


def partition_manifest(scenario_ids, siblings, *, splits=DEFAULT_SPLITS,
                       dataset_schema_version):
    """Deterministic, dataset-version-bound group-aware partition over the given
    scenarios. Returns a manifest {scenario_id -> split} plus the group table and
    the exact scheme/seed provenance so the assignment is fully reproducible and
    folds into the dataset commitment. Fails closed on an unknown/family-less
    scenario. Runs the leakage lint and RAISES on any sibling straddle."""
    _validate_splits(splits)
    scenario_ids = sorted(set(scenario_ids))
    missing = [s for s in scenario_ids if s not in siblings]
    if missing:
        raise ValueError(f"scenarios absent from the registry (cannot partition, "
                         f"fail closed): {missing}")

    # the assignment seed binds BOTH version axes and the exact split spec, so any
    # change to scheme/schema/split ratios yields a different, reproducible split.
    seed = {"partition_scheme_version": PARTITION_SCHEME_VERSION,
            "dataset_schema_version": dataset_schema_version,
            "splits": [[n, w] for n, w in splits]}

    groups = {}     # partition_group_id -> group record
    assignment = {}  # scenario_id -> split
    for sid in scenario_ids:
        family = siblings[sid]["family"]
        gid = partition_group_id(family)
        grp = groups.setdefault(gid, {"partition_group_id": gid, "family": family,
                                      "members": [], "split": None})
        grp["members"].append(sid)

    for gid, grp in groups.items():
        grp["members"] = sorted(grp["members"])
        grp["split"] = _assign_split(gid, splits, seed)
        for sid in grp["members"]:
            assignment[sid] = grp["split"]

    violations = leakage_lint(assignment, siblings)
    if violations:
        raise ValueError("group-aware partition leakage — REFUSED (§8): "
                         + "; ".join(violations))

    split_sizes = {name: 0 for name, _ in splits}
    for split in assignment.values():
        split_sizes[split] += 1

    return {
        "partition_scheme_version": PARTITION_SCHEME_VERSION,
        "dataset_schema_version": dataset_schema_version,
        "splits": [{"name": n, "weight": w} for n, w in splits],
        "assignment": dict(sorted(assignment.items())),
        "groups": [groups[g] for g in sorted(groups)],
        "group_count": len(groups),
        "split_sizes": split_sizes,
        "deduplication": {
            "exact": "manifest_load row<->evidence dedup + effective-unit "
                     "retry-collapse (audited, upstream)",
            "semantic_near_duplicate": "not applied at partition time; "
            "unnecessary at family granularity — a near-duplicate is within a "
            "family (same split) or across families (not a near-duplicate by "
            "construction), so no near-duplicate can straddle a split",
        },
        "leakage_lint": "passed",
    }


def leakage_lint(assignment, siblings):
    """Independently verify the §8 invariants against the assignment — never a
    tautology of the assigner: (1) a family never straddles a split; (2) a control
    twin shares its primary's split; (3) paraphrase variants share their scenario's
    split (trivial: same scenario_id -> one split). Returns [] when clean."""
    violations = []

    # (1) family cohesion
    by_family = {}
    for sid, split in assignment.items():
        fam = siblings.get(sid, {}).get("family")
        by_family.setdefault(fam, {}).setdefault(split, []).append(sid)
    for fam, splits_seen in sorted(by_family.items()):
        if len(splits_seen) > 1:
            violations.append(
                f"family {fam!r} straddles splits {sorted(splits_seen)}")

    # (2) control-twin cohesion (a twin must share its primary's split)
    for sid, split in sorted(assignment.items()):
        primary = siblings.get(sid, {}).get("control_of")
        if primary and primary in assignment and assignment[primary] != split:
            violations.append(
                f"control twin {sid!r} (split {split!r}) differs from its "
                f"primary {primary!r} (split {assignment[primary]!r})")

    return violations
