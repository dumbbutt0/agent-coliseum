"""T0-A group-aware partition machinery (§8): a deterministic, dataset-version-
bound split whose co-assignment unit is the registry family, with an independent
leakage lint that refuses any sibling (family / control-twin / variant) straddle.
Structural only — no labels, no training."""
import os

import pytest

from coliseum.textlab import partition as P
from coliseum.textlab.dataset_export import build_dataset, dataset_card
from coliseum.textlab.runner import run_scenario

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "configs", "registry", "scenarios.yaml")
SCEN = lambda name: os.path.join(ROOT, "configs", "scenarios", f"{name}.yaml")


@pytest.fixture()
def siblings():
    return P.load_scenario_siblings(REGISTRY)


# ------------------------------------------------------------- group identity

def test_partition_group_id_is_family_bound(siblings):
    # every scenario in a family shares one group id; different families differ
    fam_of = {s: m["family"] for s, m in siblings.items()}
    by_family = {}
    for sid, fam in fam_of.items():
        by_family.setdefault(fam, set()).add(P.partition_group_id(fam))
    for fam, ids in by_family.items():
        assert len(ids) == 1, f"family {fam} not single-id"
    all_ids = {P.partition_group_id(f) for f in set(fam_of.values())}
    assert len(all_ids) == len(set(fam_of.values()))       # distinct per family


def test_partition_group_id_missing_family_fails_closed():
    with pytest.raises(ValueError, match="no registry family"):
        P.partition_group_id("")


# ------------------------------------------------- deterministic assignment

def test_all_family_members_share_a_split(siblings):
    m = P.partition_manifest(list(siblings), siblings, dataset_schema_version="1")
    for g in m["groups"]:
        splits = {m["assignment"][s] for s in g["members"]}
        assert len(splits) == 1, f"group {g['family']} straddles {splits}"
    # exactly one group per distinct family present
    assert m["group_count"] == len({v["family"] for v in siblings.values()})


def test_assignment_is_deterministic(siblings):
    a = P.partition_manifest(list(siblings), siblings, dataset_schema_version="1")
    b = P.partition_manifest(list(siblings), siblings, dataset_schema_version="1")
    assert a == b


def test_assignment_is_dataset_version_and_spec_bound(siblings):
    default = P.partition_manifest(list(siblings), siblings,
                                   dataset_schema_version="1")
    # a different split SPEC yields a different (still deterministic) partition
    one = P.partition_manifest(list(siblings), siblings,
                               splits=(("everything", 1.0),),
                               dataset_schema_version="1")
    assert one["assignment"] != default["assignment"]
    assert set(one["assignment"].values()) == {"everything"}
    # the manifest carries the exact version/spec provenance that seeds it
    assert default["partition_scheme_version"] == P.PARTITION_SCHEME_VERSION
    assert default["dataset_schema_version"] == "1"
    assert default["splits"] == [{"name": n, "weight": w}
                                 for n, w in P.DEFAULT_SPLITS]


def test_split_weights_validated(siblings):
    for bad in [(), (("a", 0.5), ("a", 0.5)), (("a", 0.5), ("b", 0.6)),
                (("a", 1.0), ("b", 0.0))]:
        with pytest.raises(ValueError):
            P.partition_manifest(list(siblings), siblings, splits=bad,
                                 dataset_schema_version="1")


def test_unknown_scenario_fails_closed(siblings):
    with pytest.raises(ValueError, match="absent from the registry"):
        P.partition_manifest(["not_a_scenario"], siblings,
                             dataset_schema_version="1")


# ------------------------------------------------ independent leakage lint

def test_leakage_lint_clean_on_valid_assignment(siblings):
    m = P.partition_manifest(list(siblings), siblings, dataset_schema_version="1")
    assert P.leakage_lint(m["assignment"], siblings) == []


def test_leakage_lint_catches_family_and_twin_straddle(siblings):
    m = P.partition_manifest(list(siblings), siblings, dataset_schema_version="1")
    bad = dict(m["assignment"])
    other = "validation" if bad["corrupt_king"] != "validation" else "train"
    bad["corrupt_king_harmless"] = other        # split the twin from its primary
    violations = P.leakage_lint(bad, siblings)
    assert any("family 'authority' straddles" in v for v in violations)
    assert any("control twin 'corrupt_king_harmless'" in v for v in violations)


def test_manifest_raises_when_lint_reports_leakage(monkeypatch, siblings):
    # family-granularity assignment cannot straddle by construction (the point),
    # so drive the fail-closed raise path via the independent lint boundary.
    monkeypatch.setattr(P, "leakage_lint", lambda a, s: ["synthetic straddle"])
    with pytest.raises(ValueError, match="leakage"):
        P.partition_manifest(list(siblings), siblings, dataset_schema_version="1")


# ---------------------------------------------- build_dataset integration

def _runs_two_regimes(base):
    a = run_scenario(SCEN("corrupt_king"), "scripted:obedient", 42,
                     str(base / "a")).run_dir
    b = run_scenario(SCEN("corrupt_king"), "scripted:defiant", 42,
                     str(base / "b")).run_dir
    return [a, b]


def test_partition_folds_into_commitment_and_units(tmp_path):
    plain = build_dataset(_runs_two_regimes(tmp_path / "p"))
    part = build_dataset(_runs_two_regimes(tmp_path / "q"), partition=True,
                         registry_path=REGISTRY)
    assert plain["partition"] is None and part["partition"] is not None
    # the partition changes the content commitment
    assert plain["dataset_commitment"] != part["dataset_commitment"]
    # every unit carries its scenario's split
    assert all("split" in u for u in part["units"])


def test_retry_alternate_rendering_inherits_scenario_split(tmp_path):
    # two regimes of the SAME scenario -> two cells, but one scenario -> one split
    part = build_dataset(_runs_two_regimes(tmp_path), partition=True,
                         registry_path=REGISTRY)
    splits = {u["split"] for u in part["units"]}
    assert len(splits) == 1                    # never crosses via a new row identity


def test_partition_requires_registry_path(tmp_path):
    with pytest.raises(ValueError, match="requires registry_path"):
        build_dataset(_runs_two_regimes(tmp_path), partition=True)


def test_partition_commitment_binds_split_spec(tmp_path):
    a = build_dataset(_runs_two_regimes(tmp_path / "a"), partition=True,
                      registry_path=REGISTRY)
    b = build_dataset(_runs_two_regimes(tmp_path / "b"), partition=True,
                      registry_path=REGISTRY, splits=(("everything", 1.0),))
    assert a["dataset_commitment"] != b["dataset_commitment"]


def test_card_reports_partition(tmp_path):
    part = build_dataset(_runs_two_regimes(tmp_path), partition=True,
                         registry_path=REGISTRY)
    card = dataset_card(part)
    assert "Group-aware partition" in card
    assert "leakage lint" in card and "passed" in card
    assert "no group-aware partitioning" not in card      # claim now false
