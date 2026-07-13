"""T0-A group-aware partition machinery (§8 of the training-annex, BLOCKER 3).

Random row-level splitting can place close siblings (paraphrase variants, control
twins, same-family scenarios) or exact/near-duplicate content on both sides of a
train/development/validation split and inflate T1-T3 performance. This module
de-duplicates by content BEFORE assignment, assigns whole *partition groups* to
splits so that no family, content-duplicate, or lineage relation straddles a split,
and provides an independent leakage lint that FAILS on any straddle.

Faithful to §8 (lines 232-249):
  - **Deduplicate exact content before partition assignment** (§8). Content identity
    (the canonical `scenario_hash`, the same value the held-out gate keys on) is a
    REQUIRED input; scenarios that share a content hash are exact duplicates and are
    unioned into the same partition group so they can never straddle a split. The
    deduplicator's version and its KNOWN LIMITATIONS are recorded and bound into the
    dataset commitment (§27) — the semantic deduplicator is not assumed perfect.
  - The co-assignment unit is the connected component under three sibling relations:
    registry **family**, **exact content-hash equality**, and **control_of lineage**.
    All members of a component are assigned to one split together.
  - Assignment is DETERMINISTIC and dataset-version-bound (split spec + scheme/schema
    versions seed it) and included in the dataset commitment.
  - A split is keyed on the scenario's group, never a run/row id, so every retry or
    alternate rendering of a scenario inherits its scenario's split — it cannot cross
    a partition by acquiring a new row identity.
  - The independent leakage lint re-derives family, content-hash, and lineage cohesion
    from the inputs (never a tautology of the assigner) and FAILS on any straddle.

No labels, no training — this is structural T0-A machinery.
"""
from __future__ import annotations

import yaml

from .schema import config_hash

PARTITION_SCHEME_VERSION = "1"
PARTITION_GROUP_DOMAIN = "dataset:partition_group:v1"
PARTITION_ASSIGN_DOMAIN = "dataset:partition_assign:v1"

# The content de-duplicator applied before assignment. Exact content-hash equality
# only; semantic near-duplicate detection is a recorded, deferred limitation.
DEDUP_VERSION = "exact-content-hash.v1"
DEDUP_KNOWN_LIMITATIONS = (
    "exact scenario content-hash equality only (scenario_hash); no semantic / "
    "near-duplicate detection. A near-duplicate that is neither exact-hash-equal "
    "nor sibling-linked (family / control_of) is NOT detected and could in "
    "principle straddle a split — a recorded limitation (§8/§27), to be closed "
    "when a versioned semantic deduplicator is introduced."
)

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


class _UnionFind:
    def __init__(self, items):
        self.parent = {x: x for x in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # deterministic root: the lexicographically smaller id
            hi, lo = (ra, rb) if ra > rb else (rb, ra)
            self.parent[hi] = lo


def _components(scenario_ids, siblings, content_ids):
    """Connected components under family + exact-content-hash + control_of lineage
    edges. Returns {component_root: sorted[member scenario_ids]}."""
    uf = _UnionFind(scenario_ids)
    by_family = {}
    by_content = {}
    for sid in scenario_ids:
        by_family.setdefault(siblings[sid]["family"], []).append(sid)
        by_content.setdefault(content_ids[sid], []).append(sid)
    for members in list(by_family.values()) + list(by_content.values()):
        for other in members[1:]:
            uf.union(members[0], other)
    for sid in scenario_ids:
        primary = siblings[sid]["control_of"]
        if primary and primary in uf.parent:
            uf.union(sid, primary)
    comps = {}
    for sid in scenario_ids:
        comps.setdefault(uf.find(sid), []).append(sid)
    return {root: sorted(members) for root, members in comps.items()}


def partition_group_id(members, families, content_hashes):
    """Content-addressed id of a partition group (a connected component), binding
    the exact members + the families + the content hashes that fused them."""
    return config_hash({"domain": PARTITION_GROUP_DOMAIN,
                        "partition_scheme_version": PARTITION_SCHEME_VERSION,
                        "members": sorted(members),
                        "families": sorted(set(families)),
                        "content_hashes": sorted(set(content_hashes))})


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


def partition_manifest(scenario_ids, siblings, content_ids, *,
                       splits=DEFAULT_SPLITS, dataset_schema_version):
    """Deterministic, dataset-version-bound group-aware partition. De-duplicates by
    content BEFORE assignment, assigns each connected component (family + exact
    content-hash + lineage) to one split, and RAISES on any leakage the independent
    lint reports. Fails closed on an unknown/family-less scenario or a missing/
    conflicting content hash. Returns a manifest with the assignment, the group
    table, the exact scheme/seed provenance, and the deduplicator provenance — all
    folded into the dataset commitment by the caller."""
    _validate_splits(splits)
    scenario_ids = sorted(set(scenario_ids))
    missing = [s for s in scenario_ids if s not in siblings]
    if missing:
        raise ValueError(f"scenarios absent from the registry (cannot partition, "
                         f"fail closed): {missing}")
    no_family = [s for s in scenario_ids if not siblings[s].get("family")]
    if no_family:
        raise ValueError(f"scenarios without a registry family (cannot partition, "
                         f"fail closed): {no_family}")
    no_content = [s for s in scenario_ids
                  if not (content_ids or {}).get(s)]
    if no_content:
        raise ValueError(f"scenarios without a content hash (§8 dedup requires "
                         f"content identity, fail closed): {no_content}")

    # the assignment seed binds BOTH version axes and the exact split spec, so any
    # change to scheme/schema/split ratios yields a different, reproducible split.
    seed = {"partition_scheme_version": PARTITION_SCHEME_VERSION,
            "dataset_schema_version": dataset_schema_version,
            "splits": [[n, w] for n, w in splits]}

    comps = _components(scenario_ids, siblings, content_ids)
    groups = []
    assignment = {}
    for members in comps.values():
        families = [siblings[s]["family"] for s in members]
        hashes = [content_ids[s] for s in members]
        gid = partition_group_id(members, families, hashes)
        split = _assign_split(gid, splits, seed)
        groups.append({"partition_group_id": gid,
                       "families": sorted(set(families)),
                       "content_hashes": sorted(set(hashes)),
                       "members": members, "split": split})
        for s in members:
            assignment[s] = split
    groups.sort(key=lambda g: g["partition_group_id"])

    violations = leakage_lint(assignment, siblings, content_ids)
    if violations:
        raise ValueError("group-aware partition leakage — REFUSED (§8): "
                         + "; ".join(violations))

    split_sizes = {name: 0 for name, _ in splits}
    for split in assignment.values():
        split_sizes[split] += 1
    dup_clusters = sorted(
        [sorted(g) for h, g in _by_content(scenario_ids, content_ids).items()
         if len(g) > 1])

    return {
        "partition_scheme_version": PARTITION_SCHEME_VERSION,
        "dataset_schema_version": dataset_schema_version,
        "splits": [{"name": n, "weight": w} for n, w in splits],
        "assignment": dict(sorted(assignment.items())),
        "groups": groups,
        "group_count": len(groups),
        "split_sizes": split_sizes,
        "deduplication": {
            "version": DEDUP_VERSION,
            "method": "exact scenario content-hash equality (scenario_hash); "
                      "duplicates unioned into one partition group before assignment",
            "exact_duplicate_clusters": dup_clusters,
            "known_limitations": DEDUP_KNOWN_LIMITATIONS,
        },
        "leakage_lint": "passed",
    }


def _by_content(scenario_ids, content_ids):
    out = {}
    for s in scenario_ids:
        out.setdefault(content_ids[s], []).append(s)
    return out


def leakage_lint(assignment, siblings, content_ids):
    """Independently verify the §8 invariants against the assignment — never a
    tautology of the assigner: (1) a family never straddles a split; (2) exact
    content duplicates never straddle a split; (3) a control twin shares its
    primary's split. Returns [] when clean."""
    violations = []

    def _straddle(label, key_of):
        buckets = {}
        for sid, split in assignment.items():
            buckets.setdefault(key_of(sid), {}).setdefault(split, []).append(sid)
        for key, splits_seen in sorted(buckets.items(),
                                       key=lambda kv: str(kv[0])):
            if key is not None and len(splits_seen) > 1:
                violations.append(
                    f"{label} {key!r} straddles splits {sorted(splits_seen)}")

    _straddle("family", lambda s: siblings.get(s, {}).get("family"))
    _straddle("content hash", lambda s: (content_ids or {}).get(s))

    for sid, split in sorted(assignment.items()):
        primary = siblings.get(sid, {}).get("control_of")
        if primary and primary in assignment and assignment[primary] != split:
            violations.append(
                f"control twin {sid!r} (split {split!r}) differs from its "
                f"primary {primary!r} (split {assignment[primary]!r})")

    return violations
