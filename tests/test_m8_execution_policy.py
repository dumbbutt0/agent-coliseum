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
import json
import os

import pytest
import yaml

import coliseum.textlab.registry as R
import coliseum.textlab.runner as runner_mod
import coliseum.textlab.sweep as sweep_mod
from coliseum.textlab.agents import MockLLMAgent, make_agent as real_make_agent
from coliseum.textlab.registry import (VerifiedBundle, load_verified_bundle,
                                        design_hash)
from coliseum.textlab.sweep import (ExecutionPolicy, SweepAborted,
                                     SweepUnbalanced, run_sweep)
from coliseum.textlab.schema import SchemaError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "configs", "registry", "experiments.yaml")
EID = "m8-phase2-live-order-sensitivity"
FROZEN_HASH = "431871d3266a96999ef02d0d9eb77caba7e6b317135155d3161b1eecf396d533"


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
    # the profile-checked null form travels with the verified bundle (a-006 A-0
    # re-froze it from 'distributional' to the swap-invariance null)
    assert vb.planned_design["null_form"] == "swap_invariance"


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
    """A DUCK-TYPED stand-in: it exposes the same attributes a VerifiedBundle
    would, but it is not a genuine profile-checked bundle. a-006 B-1 requires
    from_verified_bundle to refuse it at the isinstance guard."""
    experiment_id = EID

    def __init__(self, rpu, msd=2):
        self.retries_per_unit = rpu
        self.max_surviving_delta = msd


def _genuine_bundle(**pd_over):
    """A REAL registry.VerifiedBundle that PASSES the isinstance guard in
    from_verified_bundle, with its frozen planned_design optionally overridden.
    Used so the retries_per_unit / max_surviving_delta guards that fire AFTER
    the type check are the thing under test, not the type check itself."""
    vb = load_verified_bundle(REGISTRY, EID)
    pd = dict(vb.planned_design)
    pd.update(pd_over)
    return VerifiedBundle(experiment_id=vb.experiment_id,
                          design_hash=vb.design_hash, planned_design=pd,
                          thresholds=vb.thresholds,
                          admissibility_policy=vb.admissibility_policy)


def test_execution_policy_refuses_nonzero_retry():
    # a GENUINE VerifiedBundle whose frozen design carries a nonzero retry is
    # refused by the rpu guard (which fires only after the type guard passes).
    with pytest.raises(SweepAborted) as exc:
        ExecutionPolicy.from_verified_bundle(
            _genuine_bundle(retries_per_unit=1), execution_order="interleaved")
    assert "retries_per_unit" in str(exc.value)


def test_execution_policy_refuses_missing_dropout_bound():
    with pytest.raises(SweepAborted) as exc:
        ExecutionPolicy.from_verified_bundle(
            _genuine_bundle(max_surviving_delta=None),
            execution_order="interleaved")
    assert "max_surviving_delta" in str(exc.value)


def test_execution_policy_refuses_a_duck_typed_bundle():
    # a-006 B-1: only a genuine profile-checked VerifiedBundle can source the
    # frozen contract — a duck-typed stand-in is refused at the isinstance guard
    # BEFORE any of its (untrusted) attribute values are consulted.
    with pytest.raises(SweepAborted) as exc:
        ExecutionPolicy.from_verified_bundle(_FakeBundle(0),
                                             execution_order="interleaved")
    assert "requires a genuine" in str(exc.value)


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


def _poison_provider(monkeypatch, why):
    """Make every provider seam raise if constructed/called, so a test can prove
    a refusal fired BEFORE any provider contact."""
    def _boom(*_a, **_k):
        raise AssertionError(f"provider contacted but {why}")
    monkeypatch.setattr(sweep_mod, "OllamaAgent", _boom)
    monkeypatch.setattr(sweep_mod, "run_scenario", _boom)


def test_run_sweep_refuses_a_forged_execution_policy(tmp_path, monkeypatch):
    # a directly-constructed policy that weakens EVERY frozen bound. run_sweep
    # re-verifies it against a freshly loaded frozen authority and refuses it
    # BEFORE any provider contact (the poisoned seams never fire).
    _poison_provider(monkeypatch, "a forged policy must be refused first")
    forged = ExecutionPolicy(retries_per_unit=0, max_surviving_delta=999,
                             execution_order="blocked",
                             record_execution_index=False)
    spec = _min_spec(tmp_path, registry_path=REGISTRY,
                     models=["llama3.1:latest"])
    with pytest.raises(SweepAborted) as exc:
        run_sweep(spec, execution_policy=forged)
    msg = str(exc.value)
    assert "forged" in msg and "frozen authority" in msg
    # the weakened dropout bound is what the re-verification caught
    assert "max_surviving_delta" in msg


def test_run_sweep_refuses_an_anonymous_protected_scenario(tmp_path,
                                                           monkeypatch):
    # a-006 E-1/B-0: a protected M8 scenario may not run without its registered
    # experiment identity — an anonymous / YAML-auto-discovery spec is refused
    # before any provider contact.
    _poison_provider(monkeypatch, "an anonymous protected sweep must be refused")
    spec = _min_spec(tmp_path, registry_path=REGISTRY,
                     scenarios=["scramble_dev_m8"], models=["llama3.1:latest"])
    del spec["experiment_id"]
    with pytest.raises(SweepAborted) as exc:
        run_sweep(spec)
    msg = str(exc.value)
    assert "scramble_dev_m8" in msg and "anonymous" in msg


def test_run_sweep_fails_closed_when_protected_resolution_raises(tmp_path,
                                                                 monkeypatch):
    """b-006 (fail-closed): if protected-scenario resolution RAISES (the caller-
    selected registry cannot resolve protection), an anonymous M8-scenario sweep
    must fail CLOSED before any provider contact — it may never be swallowed into
    an empty map and silently reclassified as an ordinary non-policy sweep that
    reaches the provider boundary without an ExecutionPolicy. Before the fix the
    `except Exception: protmap = {}` did exactly that (fail-open); now the
    exception aborts the sweep."""
    _poison_provider(monkeypatch,
                     "a sweep that cannot prove non-protection must refuse first")

    def _boom(_registry_path):
        raise RuntimeError("registry cannot resolve protected scenarios")

    # run_sweep imports protected_scenarios from the registry module at call
    # time, so patching the source name is what the local import resolves.
    monkeypatch.setattr(R, "protected_scenarios", _boom)

    # anonymous (no experiment_id) sweep that names a real M8 scenario
    spec = _min_spec(tmp_path, registry_path=REGISTRY,
                     scenarios=["scramble_dev_m8"], models=["llama3.1:latest"])
    del spec["experiment_id"]
    with pytest.raises(SweepAborted) as exc:
        run_sweep(spec)
    msg = str(exc.value)
    assert "cannot resolve protected scenarios" in msg
    assert "provider" in msg and "closed" in msg.lower()


def test_run_sweep_allows_a_benign_empty_protected_map(tmp_path, monkeypatch):
    """The other side of b-006: a benign EMPTY protected map (a registry that
    simply has no policy-required designs) must STILL be allowed — only an
    EXCEPTION fails closed. An anonymous non-protected sweep gets past the
    protected-scenario gate and fails (if at all) for an unrelated reason, never
    with the fail-closed resolution abort."""
    monkeypatch.setattr(R, "protected_scenarios", lambda _p: {})
    # a non-protected scenario, anonymous; provider seams left intact so any
    # downstream failure is a normal execution error, not the resolution gate.
    spec = _min_spec(tmp_path, registry_path=REGISTRY,
                     scenarios=["corrupt_king"], models=[], seeds=[],
                     sampler_seeds=[])
    spec["config_dir"] = os.path.join(ROOT, "configs", "scenarios")
    spec.pop("experiment_id", None)
    try:
        run_sweep(spec)
    except SweepAborted as e:
        # whatever it aborts on, it is NOT the protected-resolution fail-closed
        assert "cannot resolve protected scenarios" not in str(e)
    except Exception:
        pass  # a non-abort execution error is acceptable; the gate did not fire


def test_load_verified_bundle_refuses_a_rehashed_primary_event(tmp_path):
    # a-006 B-2: the decision rule / analysis identity is anchored by its
    # sha256; a self-rehash that alters primary_event (recomputing design_hash so
    # reconstruction passes) is refused on the verified-bundle load path.
    def mutate(entry):
        # a trailing newline changes the sha while leaving every required marker
        # and phrase intact, so it is the sha anchor — not a content lint — that
        # catches it.
        entry["planned_design"]["primary_event"] += "\n"
        entry["design_hash"] = design_hash(entry["planned_design"])
    path = _write_registry(tmp_path, mutate)
    with pytest.raises(SchemaError) as exc:
        load_verified_bundle(path, EID)
    assert "primary_event sha256" in str(exc.value)


def test_load_verified_bundle_refuses_a_rehashed_interaction_mode(tmp_path):
    # a-006 B-2: interaction_mode is a load-bearing regime dimension pinned in
    # the audited profile; a self-rehash that switches it is refused against the
    # profile (independently of the self-derived design_hash).
    def mutate(entry):
        entry["planned_design"]["interaction_mode"] = "independent_vignettes"
        entry["design_hash"] = design_hash(entry["planned_design"])
    path = _write_registry(tmp_path, mutate)
    with pytest.raises(SchemaError) as exc:
        load_verified_bundle(path, EID)
    msg = str(exc.value)
    assert "interaction_mode" in msg and "profile" in msg.lower()


# ---------------- C-1 (a-006): provider-free resume of a fully-resolved grid ---
#
# Resuming a grid whose every planned unit is already a recorded success or a
# durable tombstone must NOT construct an OllamaAgent or touch the network. A
# partial grid (>=1 unresolved unit) must still enter the fleet preflight before
# any genuinely-new generation. Both run OFFLINE — the fixture-backed mock stands
# in for the two live seams, and the fully-resolved case poisons them to prove
# zero contact.

_FIXTURE = "steward_obedient"
_CONDITIONS = ["scramble_dev", "scramble_perm", "scramble_sham"]
_MODEL = "llama3.1:latest"
_SCEN_DIR = os.path.join(ROOT, "configs", "scenarios")


def _mk_mock(model):
    a = MockLLMAgent(_FIXTURE)
    a.model = model
    a.agent_id = f"llm:ollama:{model}"
    return a


def _install_offline_ollama(monkeypatch):
    """Swap the digest probe and the per-run agent factory for the fixture mock
    — exactly the two live seams, and nothing else (run_scenario stays REAL so a
    genuine resumable manifest with real evidence dirs is produced)."""
    def _fake_probe(model, host=None):
        p = _mk_mock(model)
        p.host = host or "http://mock"
        return p

    def _fake_make_agent(spec):
        if spec.startswith("llm:ollama:"):
            return _mk_mock(spec.split("llm:ollama:", 1)[1])
        return real_make_agent(spec)

    monkeypatch.setattr(sweep_mod, "OllamaAgent", _fake_probe)
    monkeypatch.setattr(runner_mod, "make_agent", _fake_make_agent)


def _c1_spec(tmp_path, *, sampler_seeds, name="runs"):
    out_root = str(tmp_path / name)
    return {"models": [_MODEL], "scenarios": list(_CONDITIONS),
            "seeds": [42, 1], "sampler_seeds": list(sampler_seeds),
            "temperature": 0.7, "arbitration": "planner_priority",
            "interaction": "independent_vignettes", "config_dir": _SCEN_DIR,
            "out_root": out_root,
            "manifest": os.path.join(out_root, "manifest.jsonl")}


def _install_failing_real_runner(monkeypatch, calls, target):
    """Wrap the REAL fixture-backed run_scenario so ONE cell fails (a live-only
    timeout, durably tombstoned under retries_per_unit=0) while every other cell
    writes a genuine evidence dir — yielding a FULLY-resolved grid."""
    real_run_scenario = sweep_mod.run_scenario

    def _failing(path, agent_spec, seed, **kw):
        scenario = os.path.splitext(os.path.basename(path))[0]
        ks = kw.get("sampler_seed")
        calls.append((scenario, seed, ks))
        if (scenario, seed, ks) == target:
            raise TimeoutError("planner budget 120s exceeded")
        return real_run_scenario(path, agent_spec, seed, **kw)

    monkeypatch.setattr(sweep_mod, "run_scenario", _failing)


def test_c1_fully_resolved_resume_makes_zero_provider_contact(tmp_path,
                                                              monkeypatch):
    """THE C-1 REGRESSION: a grid whose 12 units are all a recorded success or a
    durable tombstone resumes WITHOUT constructing an OllamaAgent and WITHOUT any
    run_scenario call, and still re-registers the tombstoned unit."""
    _install_offline_ollama(monkeypatch)
    calls = []
    target = ("scramble_perm", 42, 2001)
    _install_failing_real_runner(monkeypatch, calls, target)
    spec = _c1_spec(tmp_path, sampler_seeds=[2001, 2002])

    first = run_sweep(spec, retries_per_unit=0)
    # 3 conditions x 2 scenario-seeds x 2 sampler-seeds = 12 units: 11 recorded
    # successes + 1 durable tombstone -> the grid is fully resolved.
    assert first.rows_written == 11 and first.tombstones_written == 1

    # now POISON both live seams: any provider contact on resume is a failure.
    n_after_first = len(calls)
    _poison_provider(monkeypatch, "a fully-resolved resume must not contact it")

    second = run_sweep(spec, retries_per_unit=0)
    # zero OllamaAgent construction, zero run_scenario -> calls list is unchanged
    assert calls[n_after_first:] == [], "run_scenario called on a resolved resume"
    # provider-free resume constructs no probe, so no served digest is recorded
    assert second.digests == {}
    assert second.rows_written == 0
    assert second.skipped_resumed == 11
    assert second.tombstoned_resumed == 1
    assert second.tombstones_written == 0
    perm = (_MODEL, "scramble_perm")
    assert second.dropouts[perm]["timeout"] == 1  # the typed failure survives


def test_c1_fully_resolved_resume_runs_the_balance_gate(tmp_path, monkeypatch):
    """The fast path still runs the SAME fail-closed balance gate the normal
    path runs — reconstructed entirely from the ledgers, with the seams poisoned
    so the gate's refusal cannot be an artefact of provider contact."""
    _install_offline_ollama(monkeypatch)
    calls = []
    target = ("scramble_perm", 42, 2001)
    _install_failing_real_runner(monkeypatch, calls, target)
    spec = _c1_spec(tmp_path, sampler_seeds=[2001, 2002])
    run_sweep(spec, retries_per_unit=0)  # build the resolved (imbalanced) grid

    _poison_provider(monkeypatch, "the balance gate must run provider-free")
    # scramble_perm survives 3 of 4, the others 4 of 4 -> a spread of 1; a bound
    # of 0 must fail closed on the fast path, before any provider contact.
    with pytest.raises(SweepUnbalanced):
        run_sweep(spec, retries_per_unit=0, max_surviving_delta=0)
    # a bound that admits the spread returns cleanly, still provider-free
    ok = run_sweep(spec, retries_per_unit=0, max_surviving_delta=1)
    assert ok.digests == {} and ok.tombstoned_resumed == 1


def test_c1_partial_grid_still_enters_the_preflight(tmp_path, monkeypatch):
    """A grid with >=1 unresolved unit must NOT take the provider-free fast path:
    the fleet preflight (digest probe) runs and genuinely-new generation
    proceeds. Proven by the served digest being recorded (preflight ran) and new
    rows being written for the unresolved units."""
    _install_offline_ollama(monkeypatch)
    first = run_sweep(_c1_spec(tmp_path, sampler_seeds=[2001]), retries_per_unit=0)
    assert first.rows_written == 6  # 3 x 2 x 1, all recorded

    # resume over a LARGER grid: the 2002 sampler-seed units are unresolved.
    second = run_sweep(_c1_spec(tmp_path, sampler_seeds=[2001, 2002]),
                       retries_per_unit=0)
    # preflight ran -> the served digest was probed and recorded
    assert second.digests.get(_MODEL)
    # the six already-recorded units are skipped, the six new ones generated
    assert second.skipped_resumed == 6
    assert second.rows_written == 6
