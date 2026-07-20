"""M8 Phase-2 structural production enforcement (Cycle-5, findings b-003 / c-003
/ d-003 f0). These prove the frozen contracts are STRUCTURALLY mandatory on the
production paths, not merely available:

  - a VerifiedBundle can only be produced by a load that re-checks the audited
    M8_FROZEN_PROFILE, so a self-rehashed / profile-weakened registry refuses;
  - an ExecutionPolicy sourced from that bundle carries retries_per_unit=0;
  - run_sweep REFUSES a policy-required sweep that arrives without an
    ExecutionPolicy, or whose loose kwargs conflict with the frozen one — fail
    closed, before any provider contact.

All offline: no network, no live compute. The refusals fire on construction.
"""
import copy
import os

import pytest
import yaml

import coliseum.textlab.registry as R
from coliseum.textlab.registry import (VerifiedBundle, load_verified_bundle,
                                        design_hash)
from coliseum.textlab.sweep import ExecutionPolicy, SweepAborted, run_sweep
from coliseum.textlab.schema import SchemaError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "configs", "registry", "experiments.yaml")
EID = "m8-phase2-live-order-sensitivity"
FROZEN_HASH = "ce8eff3eaa9f891029bcdc5b79ef9634145601e462b14fc9742503dea00e37bd"


def _write_registry(tmp_path, mutate):
    """Copy the real registry, apply `mutate(m8_entry)` to the m8 planned_design,
    and write it to a temp path. Returns the temp registry path."""
    with open(REGISTRY, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    entry = next(e for e in data["experiments"]
                 if e.get("experiment_id") == EID)
    mutate(entry)
    out = tmp_path / "experiments.yaml"
    out.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return str(out)


# --------------------------------------------------------------- VerifiedBundle

def test_verified_bundle_loads_the_frozen_design():
    vb = load_verified_bundle(REGISTRY, EID)
    assert isinstance(vb, VerifiedBundle)
    assert vb.design_hash == FROZEN_HASH
    assert vb.retries_per_unit == 0
    assert vb.max_surviving_delta == 2
    # the profile-checked null form travels with the verified bundle
    assert vb.planned_design["null_form"] == "distributional"


def test_verified_bundle_refuses_a_hash_mismatch(tmp_path):
    # mutate a bound WITHOUT recomputing design_hash -> reconstruction fails
    def mutate(entry):
        entry["planned_design"]["thresholds"]["min_detectable_effect"] = 0.30
    path = _write_registry(tmp_path, mutate)
    with pytest.raises(SchemaError) as exc:
        load_verified_bundle(path, EID)
    assert "design_hash" in str(exc.value) or "mutated" in str(exc.value)


def test_verified_bundle_refuses_a_self_rehashed_weakened_design(tmp_path):
    # the rehash attack: weaken a type-valid bound AND recompute design_hash so
    # reconstruction passes. The independent M8_FROZEN_PROFILE must still refuse.
    def mutate(entry):
        entry["planned_design"]["thresholds"]["min_detectable_effect"] = 0.30
        entry["design_hash"] = design_hash(entry["planned_design"])
    path = _write_registry(tmp_path, mutate)
    with pytest.raises(SchemaError) as exc:
        load_verified_bundle(path, EID)
    msg = str(exc.value)
    assert "profile" in msg.lower()
    # design_hash reconstruction is NOT what caught it (the attack defeats that)
    assert "min_detectable_effect" in msg


def test_verified_bundle_refuses_a_rehashed_nonzero_retry(tmp_path):
    def mutate(entry):
        entry["planned_design"]["retries_per_unit"] = 1
        entry["design_hash"] = design_hash(entry["planned_design"])
    path = _write_registry(tmp_path, mutate)
    with pytest.raises(SchemaError):
        load_verified_bundle(path, EID)


# -------------------------------------------------------------- ExecutionPolicy

def test_execution_policy_from_bundle_is_zero_retry():
    vb = load_verified_bundle(REGISTRY, EID)
    ep = ExecutionPolicy.from_verified_bundle(vb, execution_order="interleaved")
    assert ep.retries_per_unit == 0
    assert ep.max_surviving_delta == 2
    assert ep.execution_order == "interleaved"
    assert ep.record_execution_index is True


class _FakeBundle:
    experiment_id = EID

    def __init__(self, rpu, msd=2):
        self.retries_per_unit = rpu
        self.max_surviving_delta = msd


def test_execution_policy_refuses_nonzero_retry():
    with pytest.raises(SweepAborted) as exc:
        ExecutionPolicy.from_verified_bundle(_FakeBundle(1),
                                             execution_order="interleaved")
    assert "retries_per_unit" in str(exc.value)


def test_execution_policy_refuses_missing_dropout_bound():
    with pytest.raises(SweepAborted) as exc:
        ExecutionPolicy.from_verified_bundle(_FakeBundle(0, msd=None),
                                             execution_order="interleaved")
    assert "max_surviving_delta" in str(exc.value)


# -------------------------------------------------------------------- run_sweep

def _min_spec(tmp_path, **over):
    out = str(tmp_path)
    spec = {"experiment_id": EID, "models": [], "scenarios": [], "seeds": [],
            "config_dir": out, "out_root": out,
            "manifest": os.path.join(out, "m.jsonl")}
    spec.update(over)
    return spec


def test_run_sweep_refuses_policy_required_without_execution_policy(tmp_path):
    with pytest.raises(SweepAborted) as exc:
        run_sweep(_min_spec(tmp_path))
    assert "ExecutionPolicy" in str(exc.value)


def test_run_sweep_refuses_conflicting_kwarg(tmp_path):
    vb = load_verified_bundle(REGISTRY, EID)
    ep = ExecutionPolicy.from_verified_bundle(vb, execution_order="interleaved")
    with pytest.raises(SweepAborted) as exc:
        run_sweep(_min_spec(tmp_path), execution_policy=ep,
                  max_surviving_delta=99)
    assert "conflicts" in str(exc.value)


def test_run_sweep_nonpolicy_experiment_needs_no_policy(tmp_path):
    # a non-policy experiment id must NOT trip the mandatory-policy gate; it
    # proceeds past the gate (and fails later for ordinary reasons, never the
    # policy refusal).
    try:
        run_sweep(_min_spec(tmp_path, experiment_id="not-a-policy-experiment"))
    except SweepAborted as exc:
        assert "ExecutionPolicy" not in str(exc.value)
    except Exception:
        pass  # any non-policy failure is acceptable; the gate did not fire
