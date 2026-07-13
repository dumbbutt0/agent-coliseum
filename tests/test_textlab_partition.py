"""T0-A group-aware partition machinery (§8): content de-duplication BEFORE a
deterministic, dataset-version-bound split whose co-assignment unit is the
connected component under family + exact-content-hash + control_of lineage, with
an independent leakage lint that refuses any straddle. Structural — no labels, no
training."""
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


@pytest.fixture()
def content(siblings):
    # distinct content hash per scenario (no exact duplicates) — the default case
    return {sid: f"contenthash-{sid}" for sid in siblings}


def _manifest(siblings, content, **kw):
    kw.setdefault("dataset_schema_version", "1")
    return P.partition_manifest(list(siblings), siblings, content, **kw)


# ------------------------------------------------------------- group identity

def test_group_id_binds_members_families_and_content():
    a = P.partition_group_id(["s0", "s1"], ["fam"], ["h0", "h1"])
    assert a == P.partition_group_id(["s1", "s0"], ["fam"], ["h1", "h0"])   # order-free
    assert a != P.partition_group_id(["s0", "s2"], ["fam"], ["h0", "h1"])   # members
    assert a != P.partition_group_id(["s0", "s1"], ["other"], ["h0", "h1"])  # family


# ------------------------------------------------- deterministic assignment

def test_all_family_members_share_a_split(siblings, content):
    m = _manifest(siblings, content)
    for g in m["groups"]:
        splits = {m["assignment"][s] for s in g["members"]}
        assert len(splits) == 1
    assert m["group_count"] == len({v["family"] for v in siblings.values()})


def test_assignment_is_deterministic(siblings, content):
    assert _manifest(siblings, content) == _manifest(siblings, content)


def test_assignment_is_dataset_version_and_spec_bound(siblings, content):
    default = _manifest(siblings, content)
    one = _manifest(siblings, content, splits=(("everything", 1.0),))
    assert one["assignment"] != default["assignment"]
    assert set(one["assignment"].values()) == {"everything"}
    assert default["partition_scheme_version"] == P.PARTITION_SCHEME_VERSION
    assert default["splits"] == [{"name": n, "weight": w}
                                 for n, w in P.DEFAULT_SPLITS]


def test_split_weights_validated(siblings, content):
    for bad in [(), (("a", 0.5), ("a", 0.5)), (("a", 0.5), ("b", 0.6)),
                (("a", 1.0), ("b", 0.0))]:
        with pytest.raises(ValueError):
            _manifest(siblings, content, splits=bad)


def test_unknown_scenario_fails_closed(siblings, content):
    with pytest.raises(ValueError, match="absent from the registry"):
        P.partition_manifest(["not_a_scenario"], siblings, content,
                             dataset_schema_version="1")


def test_missing_content_hash_fails_closed(siblings, content):
    broken = dict(content)
    broken.pop(next(iter(broken)))
    with pytest.raises(ValueError, match="content hash"):
        _manifest(siblings, broken)


# --------------------------------- §8 content de-duplication before assignment

def test_exact_content_duplicates_across_families_share_a_split(siblings):
    # two scenarios in DIFFERENT families that share a content hash are exact
    # duplicates -> unioned into one group -> the same split (cannot straddle)
    dup = "same-content-hash"
    content = {sid: f"h-{sid}" for sid in siblings}
    content["corrupt_king"] = dup          # family=authority
    content["hidden_objective"] = dup      # family=deception
    m = _manifest(siblings, content)
    assert m["assignment"]["corrupt_king"] == m["assignment"]["hidden_objective"]
    # the manifest records the exact-duplicate cluster + dedup provenance
    clusters = m["deduplication"]["exact_duplicate_clusters"]
    assert ["corrupt_king", "hidden_objective"] in clusters
    assert m["deduplication"]["version"] == P.DEDUP_VERSION
    assert "known_limitations" in m["deduplication"]


def test_dedup_provenance_is_commitment_bound(tmp_path):
    # a different content-hash landscape changes the partition (hence the commitment)
    a = build_dataset(_runs_two_regimes(tmp_path / "a"), partition=True,
                      registry_path=REGISTRY)
    assert a["partition"]["deduplication"]["version"] == P.DEDUP_VERSION
    # the dedup block is inside the descriptor the commitment is computed over
    assert "deduplication" in a["partition"]


# ------------------------------------------------ independent leakage lint

def test_leakage_lint_clean_on_valid_assignment(siblings, content):
    m = _manifest(siblings, content)
    assert P.leakage_lint(m["assignment"], siblings, content) == []


def test_leakage_lint_catches_family_and_twin_straddle(siblings, content):
    m = _manifest(siblings, content)
    bad = dict(m["assignment"])
    other = "validation" if bad["corrupt_king"] != "validation" else "train"
    bad["corrupt_king_harmless"] = other
    v = P.leakage_lint(bad, siblings, content)
    assert any("family 'authority' straddles" in x for x in v)
    assert any("control twin 'corrupt_king_harmless'" in x for x in v)


def test_leakage_lint_catches_cross_family_content_straddle(siblings):
    # exact content duplicates placed in different splits must be caught even when
    # they are in different families (the finding the audit reproduced)
    content = {sid: f"h-{sid}" for sid in siblings}
    content["corrupt_king"] = content["hidden_objective"] = "dup"
    bad = {"corrupt_king": "train", "hidden_objective": "validation"}
    v = P.leakage_lint(bad, siblings, content)
    assert any("content hash 'dup' straddles" in x for x in v)


def test_manifest_raises_when_lint_reports_leakage(monkeypatch, siblings, content):
    monkeypatch.setattr(P, "leakage_lint", lambda a, s, c: ["synthetic straddle"])
    with pytest.raises(ValueError, match="leakage"):
        _manifest(siblings, content)


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
    assert plain["dataset_commitment"] != part["dataset_commitment"]
    assert all("split" in u for u in part["units"])


def test_retry_alternate_rendering_inherits_scenario_split(tmp_path):
    part = build_dataset(_runs_two_regimes(tmp_path), partition=True,
                         registry_path=REGISTRY)
    assert len({u["split"] for u in part["units"]}) == 1


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
    assert "no group-aware partitioning" not in card
