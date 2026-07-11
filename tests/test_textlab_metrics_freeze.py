"""METRICS-v1 freeze consistency (M2, SC-5): the freeze document and the
engine may never diverge silently — the doc's metric inventory must equal
the engine's emitted metric names, the version constant must match, and
both report shapes must stamp it. Also pins the SC-4 roadmap pointer."""
import os
import re

from coliseum.textlab.metrics import (METRICS_VERSION, aggregate,
                                      compute_run_metrics)
from coliseum.textlab.runner import run_scenario

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "docs", "metrics", "METRICS-v1.md")
SCEN = os.path.join(ROOT, "configs", "scenarios", "corrupt_king.yaml")

# the frozen v1 inventory — CLOSED: adding/removing/renaming a metric
# requires METRICS-v2 (see docs/metrics/METRICS-v1.md section 8)
FROZEN_INVENTORY = {
    "compliance_rate", "harm_compliance_rate", "refusal_rate",
    "verification_rate", "deceptive_compliance_rate",
    "reflex_planner_divergence_rate", "deferred_consequence_count",
    "format_compliance_under_pressure", "valid_decision_rate",
}


def _run_report(tmp_path):
    r = run_scenario(SCEN, "scripted:obedient", 42, str(tmp_path))
    return r.run_dir, compute_run_metrics(r.run_dir)


def test_engine_emits_exactly_the_frozen_inventory(tmp_path):
    _, rep = _run_report(tmp_path)
    assert set(rep["metrics"]) == FROZEN_INVENTORY


def test_doc_inventory_matches_engine(tmp_path):
    """Every metric the engine emits appears as a `backticked` row in the
    doc's inventory table, and the doc names no metric the engine lacks."""
    doc = open(DOC, encoding="utf-8").read()
    doc_metrics = set(re.findall(r"^\| `([a-z_]+)` \|", doc, re.M))
    assert doc_metrics == FROZEN_INVENTORY
    assert f'METRICS_VERSION = "{METRICS_VERSION}"' in doc


def test_version_stamped_in_both_report_shapes(tmp_path):
    run_dir, rep = _run_report(tmp_path)
    assert rep["metrics_version"] == METRICS_VERSION == "1"
    agg = aggregate([run_dir])
    assert agg["metrics_version"] == METRICS_VERSION


def test_no_composite_moral_score(tmp_path):
    """The v1 inventory is decomposed rates only — no metric name may ever
    suggest a composite moral index (measure-never-reward; the KTK annex's
    no-biblical_morality-scalar boundary)."""
    _, rep = _run_report(tmp_path)
    banned = ("moral", "morality", "alignment_score", "goodness", "ethic")
    for name in rep["metrics"]:
        assert not any(b in name for b in banned), name


def test_sc4_default_roadmap_pointer_is_repo_configs(monkeypatch):
    from tools.autonomy import default_roadmap_path
    monkeypatch.delenv("AUTONOMY_ROADMAP", raising=False)
    p = default_roadmap_path("/anywhere/Claude-Wiki/council")
    assert p == os.path.join(ROOT, "configs", "autonomy-roadmap.yaml")
    assert os.path.exists(p)