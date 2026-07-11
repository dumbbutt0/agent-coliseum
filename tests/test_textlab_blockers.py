"""Second-round audit blockers (Codex BLOCKED verdict at ed053615), one
section per blocker:

  1  twin pair-cell identity includes the FULL agent regime — two same-display
     pairs with different regimes are two cells, never an overwrite
  2  control_of is revision-bound (scenario_id, scenario_hash, control_of) —
     conflicting metadata for one behavioral identity fails loudly
  3  canonical attempt policy — identical retries collapse; conflicting
     retries never average (refuse, or explicit manifest-selected canonical)
  4  manifest rows must carry the COMPLETE current schema; legacy rows only
     enter through scripts/migrate_manifest.py
"""
import json
import os
import sys

import pytest
import yaml

import coliseum.textlab.agents as agents_mod
from coliseum.textlab.metrics import _cell_counts, _cell_metrics, aggregate
from coliseum.textlab.runner import run_scenario
from coliseum.textlab.schema import SchemaError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCEN = lambda name: os.path.join(ROOT, "configs", "scenarios", f"{name}.yaml")
CK = SCEN("corrupt_king")
CKV = SCEN("corrupt_king_verifiable")

sys.path.insert(0, os.path.join(ROOT, "scripts"))
import migrate_manifest  # noqa: E402
import sweep_models  # noqa: E402

MOCK = "llm:mock:steward_obedient"


# ============================== blocker 1: twin full-agent-regime separation

def test_same_display_twin_pairs_with_different_regimes_never_overwrite(
        tmp_path, monkeypatch):
    out = str(tmp_path / "runs")
    p1 = run_scenario(CK, MOCK, 42, out)
    c1 = run_scenario(CKV, MOCK, 42, out)
    # second regime: identical DISPLAY fields (same fixture bytes -> same
    # digest, same agent_id/arbitration/sampling), different full agent
    # regime via a non-display behavioral knob
    orig_spec = agents_mod.MockLLMAgent.spec_dict
    monkeypatch.setattr(
        agents_mod.MockLLMAgent, "spec_dict",
        lambda self: {**orig_spec(self), "hidden_regime_knob": "b-side"})
    p2 = run_scenario(CK, MOCK, 42, out)
    c2 = run_scenario(CKV, MOCK, 42, out)

    assert p1.run.agent_regime_id != p2.run.agent_regime_id
    assert p1.run.agent_config["model_digest"] \
        == p2.run.agent_config["model_digest"]  # display-identical

    agg = aggregate([p1.run_dir, c1.run_dir, p2.run_dir, c2.run_dir])
    pairs = agg["control_twin_delta"]
    assert len(pairs) == 2, \
        f"expected 2 regime-distinct pair cells, got {list(pairs)}"
    # the full identity is preserved in the output, not just the label
    regimes = {v["agent_regime_id"] for v in pairs.values()}
    assert regimes == {p1.run.agent_regime_id, p2.run.agent_regime_id}
    for label, cell in pairs.items():
        assert "|a:" in label  # regime display segment present
        assert cell["pair_provenance"]["agent_regime_id"] \
            == cell["agent_regime_id"]
        assert label.split("|a:")[1] \
            == cell["agent_regime_id"][:12]  # prefix backed by full id


def test_single_regime_still_yields_one_pair_cell(tmp_path):
    out = str(tmp_path / "runs")
    p = run_scenario(CK, MOCK, 42, out)
    c = run_scenario(CKV, MOCK, 42, out)
    agg = aggregate([p.run_dir, c.run_dir])
    assert len(agg["control_twin_delta"]) == 1


# ============================== blocker 2: revision-bound control_of

def _twin_copy(tmp_path, name, control_of):
    raw = yaml.safe_load(open(CKV, encoding="utf-8"))
    if control_of is None:
        raw.pop("control_of", None)
    else:
        raw["control_of"] = control_of
    path = tmp_path / f"{name}.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return str(path)


def test_conflicting_control_of_for_same_identity_fails_loudly(tmp_path):
    out = str(tmp_path / "runs")
    prim = run_scenario(CK, MOCK, 42, out)
    twin_a = run_scenario(_twin_copy(tmp_path, "twin_a", "corrupt_king"),
                          MOCK, 42, out)
    twin_b = run_scenario(_twin_copy(tmp_path, "twin_b", None), MOCK, 42, out)
    # byte-identical behavioral identity: control_of is NOT in the hash
    assert twin_a.run.scenario_hash == twin_b.run.scenario_hash
    with pytest.raises(SchemaError, match="conflicting control_of"):
        aggregate([prim.run_dir, twin_a.run_dir, twin_b.run_dir])


def test_consistent_control_of_still_pairs(tmp_path):
    out = str(tmp_path / "runs")
    prim = run_scenario(CK, MOCK, 42, out)
    twin = run_scenario(CKV, MOCK, 42, out)
    agg = aggregate([prim.run_dir, twin.run_dir])
    pair = next(iter(agg["control_twin_delta"].values()))
    assert pair["pair_provenance"]["control_of"] == "corrupt_king"


def test_control_binding_is_revision_exact(tmp_path):
    """A revised twin (new hash) binds only its own revision's runs — the
    other revision keeps its own pair cell (no cross-revision pooling)."""
    out = str(tmp_path / "runs")
    prim = run_scenario(CK, MOCK, 42, out)
    twin_a = run_scenario(CKV, MOCK, 42, out)
    raw = yaml.safe_load(open(CKV, encoding="utf-8"))
    for v in raw["variants"]:
        texts = v.get("decision_texts", {})
        for k in texts:
            texts[k] += " (revised wording)"
    revised = tmp_path / "corrupt_king_verifiable.yaml"
    revised.write_text(yaml.safe_dump(raw), encoding="utf-8")
    twin_b = run_scenario(str(revised), MOCK, 42, out)
    assert twin_a.run.scenario_hash != twin_b.run.scenario_hash

    agg = aggregate([prim.run_dir, twin_a.run_dir, twin_b.run_dir])
    pairs = agg["control_twin_delta"]
    assert len(pairs) == 2
    control_hashes = {p["pair_provenance"]["control_scenario_hash"]
                      for p in pairs.values()}
    assert control_hashes == {twin_a.run.scenario_hash,
                              twin_b.run.scenario_hash}


# ============================== blocker 3: canonical attempt policy

def _synth(report_id, variant, scenario_seed, sampler_seed, value):
    return {"report_id": report_id, "variant_id": variant,
            "scenario_seed": scenario_seed, "sampler_seed": sampler_seed,
            "metrics": {"compliance_rate": {"value": value, "n": 1}}}


def test_identical_retry_changes_nothing():
    single = [_synth("r1", "v0", 1, None, 0.75)]
    with_retry = single + [_synth("r2", "v0", 1, None, 0.75)]
    m_single, _ = _cell_metrics(single)
    m_retry, _ = _cell_metrics(with_retry)
    assert m_single == m_retry                      # mean untouched
    assert _cell_counts(with_retry)["effective_n"] \
        == _cell_counts(single)["effective_n"] == 1
    assert _cell_counts(with_retry)["retry_n"] == 1


def test_conflicting_retry_refuses_instead_of_averaging():
    runs = [_synth("r1", "v0", 1, None, 0.75),
            _synth("r2", "v0", 1, None, 0.25)]     # would average to 0.50
    with pytest.raises(SchemaError, match="conflicting retry attempts"):
        _cell_metrics(runs)


def test_conflicting_retry_with_canonical_selection_is_deterministic():
    runs = [_synth("r1", "v0", 1, None, 0.75),
            _synth("r2", "v0", 1, None, 0.25)]
    exclusions = {}
    metrics, _ = _cell_metrics(runs, canonical_attempts={"r1"},
                               exclusions=exclusions)
    assert metrics["compliance_rate"]["value"] == 0.75  # the evidence attempt
    record = next(iter(exclusions.values()))
    assert record["kept"] == "r1" and record["excluded"] == ["r2"]
    assert record["reason"] == "canonical_attempt_selection"
    # selecting the other attempt is equally deterministic
    metrics2, _ = _cell_metrics(runs, canonical_attempts={"r2"})
    assert metrics2["compliance_rate"]["value"] == 0.25


def test_canonical_selection_must_pick_exactly_one():
    runs = [_synth("r1", "v0", 1, None, 0.75),
            _synth("r2", "v0", 1, None, 0.25)]
    with pytest.raises(SchemaError, match="exactly one"):
        _cell_metrics(runs, canonical_attempts={"r1", "r2"})
    with pytest.raises(SchemaError, match="exactly one"):
        _cell_metrics(runs, canonical_attempts={"r9"})


def _corrupt_attempt(run_dir):
    """Flip the obedience tags in one attempt's decision log so its metrics
    conflict with the first attempt (same lineage, different outcome)."""
    path = os.path.join(run_dir, "decisions.jsonl")
    text = open(path, encoding="utf-8").read()
    assert '"obedience"' in text
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.replace('"obedience"', '"defiance"'))


def test_aggregate_conflicting_retry_refuses_cells_and_pairs(tmp_path):
    out = str(tmp_path / "runs")
    first = run_scenario(CK, MOCK, 42, out)
    second = run_scenario(CK, MOCK, 42, out)        # retry: same replicate
    assert first.run_dir != second.run_dir
    control = run_scenario(CKV, MOCK, 42, out)

    baseline = aggregate([first.run_dir, control.run_dir])
    base_cellkeys = {k for k in baseline["cells"]
                     if k.startswith("corrupt_king|")}
    assert len(base_cellkeys) == 1
    base_cell = baseline["cells"][next(iter(base_cellkeys))]
    base_pair = next(iter(baseline["control_twin_delta"].values()))

    # identical retry: byte-identical numbers, nothing moves
    agg = aggregate([first.run_dir, second.run_dir, control.run_dir])
    cell = agg["cells"][next(k for k in agg["cells"]
                             if k.startswith("corrupt_king|"))]
    assert cell["metrics"] == base_cell["metrics"]
    assert cell["counts"]["effective_n"] == base_cell["counts"]["effective_n"]
    pair = next(iter(agg["control_twin_delta"].values()))
    assert pair["deltas"] == base_pair["deltas"]
    assert pair["effective_pair_n"] == base_pair["effective_pair_n"]

    # conflicting retry: REFUSE — never a silent mean shift
    _corrupt_attempt(second.run_dir)
    with pytest.raises(SchemaError, match="conflicting retry attempts"):
        aggregate([first.run_dir, second.run_dir, control.run_dir])

    # manifest-selected canonical attempt restores the baseline numbers and
    # puts the exclusion on the record
    canonical = {os.path.basename(first.run_dir)}
    fixed = aggregate([first.run_dir, second.run_dir, control.run_dir],
                      canonical_attempts=canonical)
    cell = fixed["cells"][next(k for k in fixed["cells"]
                               if k.startswith("corrupt_king|"))]
    assert cell["metrics"] == base_cell["metrics"]
    pair = next(iter(fixed["control_twin_delta"].values()))
    assert pair["deltas"] == base_pair["deltas"]
    assert fixed["attempt_exclusions"], "exclusion must be recorded"
    assert all(e["reason"] == "canonical_attempt_selection"
               for e in fixed["attempt_exclusions"])
    assert all(os.path.basename(second.run_dir) in e["excluded"]
               for e in fixed["attempt_exclusions"])


# ============================== blocker 4: complete manifest rows

def _run_and_row(tmp_path):
    out_root = str(tmp_path / "runs")
    r = run_scenario(CK, MOCK, 42, out_root)
    run = json.load(open(os.path.join(r.run_dir, "run.json")))
    decision_path = migrate_manifest.evidence_row(
        run, os.path.basename(r.run_dir), r.run_dir)["path"]
    row = {"regime_id": run["comparison_regime_id"],
           "model": run["agent_config"]["model"],
           "scenario": run["scenario_id"],
           "scenario_seed": run["scenario_seed"],
           "sampler_seed": run["sampler_seed"],
           "variant_id": run["variant_id"],
           "temperature": run["sampling"].get("temperature", 0),
           "sampling_mode": run["sampling"]["mode"],
           "digest": run["agent_config"]["model_digest"],
           "scenario_hash": run["scenario_hash"],
           "arbitration": run["arbitration"], "run_id": run["run_id"],
           "dir": os.path.basename(r.run_dir),
           "reportable": run["reportable"],
           "stochastic_reportable": run["stochastic_reportable"],
           "interaction_mode": run["interaction_mode"],
           "path": decision_path}
    return out_root, row


def test_complete_row_loads(tmp_path):
    out_root, row = _run_and_row(tmp_path)
    path = tmp_path / "m.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    assert len(sweep_models.manifest_load(str(path), out_root)) == 1


@pytest.mark.parametrize("field", sweep_models.REQUIRED_ROW_FIELDS)
def test_row_missing_any_required_field_refuses(tmp_path, field):
    out_root, row = _run_and_row(tmp_path)
    incomplete = {k: v for k, v in row.items() if k != field}
    path = tmp_path / "m.jsonl"
    path.write_text(json.dumps(incomplete) + "\n", encoding="utf-8")
    with pytest.raises(SchemaError,
                       match="incomplete manifest row|legacy manifest row"):
        sweep_models.manifest_load(str(path), out_root)


def test_dir_only_row_refuses(tmp_path):
    """The audited defect verbatim: a row carrying ONLY a valid dir loaded."""
    out_root, row = _run_and_row(tmp_path)
    path = tmp_path / "m.jsonl"
    path.write_text(json.dumps({"dir": row["dir"]}) + "\n", encoding="utf-8")
    with pytest.raises(SchemaError, match="incomplete manifest row"):
        sweep_models.manifest_load(str(path), out_root)


def test_legacy_row_migrates_then_loads(tmp_path, monkeypatch):
    out_root, row = _run_and_row(tmp_path)
    legacy = {"run_id": row["run_id"], "model": row["model"]}
    path = tmp_path / "m.jsonl"
    path.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
    with pytest.raises(SchemaError):                # unmigrated: refused
        sweep_models.manifest_load(str(path), out_root)
    monkeypatch.setattr(sys, "argv",
                        ["migrate_manifest.py", str(path), out_root])
    migrate_manifest.main()
    loaded = sweep_models.manifest_load(str(path), out_root)
    assert len(loaded) == 1
    migrated_row = next(iter(loaded.values()))
    assert migrated_row["migrated"] is True
    for field in sweep_models.REQUIRED_ROW_FIELDS:
        assert field in migrated_row
    assert os.path.exists(str(path) + ".pre-migration")


def test_migration_never_rewrites_contradicting_claims(tmp_path, monkeypatch):
    out_root, row = _run_and_row(tmp_path)
    lying = {"run_id": row["run_id"], "model": "some-other-model"}
    path = tmp_path / "m.jsonl"
    path.write_text(json.dumps(lying) + "\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv",
                        ["migrate_manifest.py", str(path), out_root])
    with pytest.raises(SystemExit, match="contradicts evidence"):
        migrate_manifest.main()


def test_writer_emits_the_complete_schema():
    """Writer/loader share REQUIRED_ROW_FIELDS — drift is structurally
    impossible while both build from the constant."""
    emitted = {"regime_id", "model", "scenario", "scenario_seed",
               "sampler_seed", "variant_id", "temperature", "sampling_mode",
               "digest", "scenario_hash", "arbitration", "run_id", "dir",
               "reportable", "stochastic_reportable", "interaction_mode",
               "path"}
    assert emitted == set(sweep_models.REQUIRED_ROW_FIELDS)