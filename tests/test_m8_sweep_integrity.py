"""m8 Phase 2 sweep-integrity guards: condition-interleaved execution (F7) and
typed per-condition dropout accounting with a fail-closed balance gate (F6).

Both defects are INVISIBLE under Phase-1's scripted deterministic deciders and
only bite when the same machinery points at a live stochastic model over LAN:
blocked condition order makes wall-clock position 100% correlated with
condition, and a swallowed dropout turns a condition's survivors into a biased
subsample. Everything here runs OFFLINE — `run_scenario` is stubbed or the
fixture-backed MockLLMAgent stands in for both live seams. No network, no
model, no host is ever contacted.

The load-bearing test in this file is `test_default_behavior_is_unchanged`: the
new options are opt-in, so Phase-1 evidence must regenerate byte-for-byte."""
import json
import os

import pytest

import coliseum.textlab.runner as runner_mod
import coliseum.textlab.sweep as sweep_mod
from coliseum.textlab.agents import MockLLMAgent, make_agent as real_make_agent
from coliseum.textlab.sweep import (FAILURE_KINDS, REQUIRED_ROW_FIELDS,
                                    SweepAborted, SweepResult, SweepUnbalanced,
                                    _file_sha256, cell_order, classify_failure,
                                    run_sweep, surviving_counts_from_result,
                                    verify_pack_replay)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = "steward_obedient"
SCENARIO = "corrupt_king"
MODEL = "llama3.1:latest"
# the three Phase-2 conditions: A developmental order, B permuted, C sham
CONDITIONS = ["scramble_dev", "scramble_perm", "scramble_sham"]


def _mk_mock(model):
    a = MockLLMAgent(FIXTURE)
    a.model = model
    a.agent_id = f"llm:ollama:{model}"
    return a


def _install_offline_ollama(monkeypatch):
    """Swap the two live seams (digest probe + per-run agent factory) for the
    fixture-backed mock, exactly as the existing driver tests do."""
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


def _spec(tmp_path, *, scenarios=None, seeds=(42,), sampler_seeds=None,
          temperature=0.0, name="runs"):
    out_root = str(tmp_path / name)
    return {"models": [MODEL], "scenarios": list(scenarios or [SCENARIO]),
            "seeds": list(seeds), "sampler_seeds": sampler_seeds,
            "temperature": temperature, "arbitration": "planner_priority",
            "interaction": "independent_vignettes",
            "config_dir": os.path.join(ROOT, "configs", "scenarios"),
            "out_root": out_root,
            "manifest": os.path.join(out_root, "manifest.jsonl")}


class _StubRun:
    """The minimum `run_scenario` return surface the sweep row builder reads."""

    def __init__(self, scenario, seed, sampler_seed, regime_id):
        self.run_id = f"{scenario}-s{seed}-k{sampler_seed}"
        self.run_dir = f"/stub/{self.run_id}"
        self.final_actions = ["comply"]
        self.run = type("R", (), {})()
        self.run.comparison_regime_id = regime_id
        self.run.variant_id = f"v_{scenario}"
        self.run.sampling = {"mode": "stochastic", "temperature": 0.7}
        self.run.agent_config = {"model_digest": "sha256:stub"}
        self.run.scenario_hash = "stubhash"
        self.run.reportable = True
        self.run.stochastic_reportable = True
        self.run.interaction_mode = "sequential_history"


def _install_stub_runner(monkeypatch, calls, fail=None):
    """Replace run_scenario with a recorder. `fail(scenario, seed, sampler_seed)`
    returns an exception to raise (or None) — this is how a live-only failure
    (an HTTP timeout, a reset connection) is simulated without a network."""
    def _regime_for(path):
        # a per-scenario id the stub and the sweep both derive the same way, so
        # the sweep's mid-run regime-drift check still passes against the stub
        return "regime-" + sweep_mod.load_scenario(path).scenario_id

    def _stub(path, agent_spec, seed, **kw):
        scenario = os.path.splitext(os.path.basename(path))[0]
        ks = kw.get("sampler_seed")
        calls.append((scenario, seed, ks))
        if fail is not None:
            exc = fail(scenario, seed, ks)
            if exc is not None:
                raise exc
        return _StubRun(scenario, seed, ks, _regime_for(path))

    monkeypatch.setattr(sweep_mod, "run_scenario", _stub)
    monkeypatch.setattr(sweep_mod, "regime_hashes",
                        lambda bc: ("regime-" + bc["scenario"]["scenario_id"],
                                    "stub"))
    return _stub


def _run_stubbed(tmp_path, monkeypatch, *, fail=None, name="runs", **kw):
    """A 3-condition x 2-scenario-seed x 2-sampler-seed stubbed sweep."""
    _install_offline_ollama(monkeypatch)
    calls = []
    _install_stub_runner(monkeypatch, calls, fail=fail)
    spec = _spec(tmp_path, scenarios=CONDITIONS, seeds=(42, 1),
                 sampler_seeds=[2001, 2002], temperature=0.7, name=name)
    result = run_sweep(spec, **kw)
    return result, calls, spec


# ----------------------------------------------------------- F7: cell ordering

def test_blocked_cell_order_is_the_historical_nesting():
    """The default must reproduce scenario -> scenario_seed -> sampler_seed
    exactly — the nesting every previous sweep used."""
    scenarios, seeds, ks = ["a", "b", "c"], [42, 1], [2001, 2002]
    expected = [(sc, ss, k) for sc in scenarios for ss in seeds for k in ks]
    assert cell_order(scenarios, seeds, ks) == expected
    assert cell_order(scenarios, seeds, ks, "blocked") == expected


def test_interleaved_cell_order_draws_conditions_adjacently():
    scenarios, seeds, ks = ["a", "b", "c"], [42, 1], [2001, 2002]
    got = cell_order(scenarios, seeds, ks, "interleaved")
    # same cells, no cell gained or lost — only the order changes
    assert sorted(got) == sorted(cell_order(scenarios, seeds, ks))
    # every consecutive block of len(scenarios) is one unit's full A/B/C
    for i in range(0, len(got), len(scenarios)):
        block = got[i:i + len(scenarios)]
        assert [c[0] for c in block] == scenarios
        assert len({(c[1], c[2]) for c in block}) == 1, \
            f"block {block} spans more than one (scenario_seed, sampler_seed)"


def test_unknown_execution_order_is_refused():
    with pytest.raises(SweepAborted, match="unknown execution_order"):
        cell_order(["a"], [1], [None], "round_robin")


def test_interleaved_sweep_executes_conditions_adjacently(tmp_path, monkeypatch):
    """End to end: the realized run_scenario call sequence, not just the plan."""
    result, calls, _ = _run_stubbed(tmp_path, monkeypatch,
                                    execution_order="interleaved")
    assert result.rows_written == 12
    for i in range(0, len(calls), 3):
        block = calls[i:i + 3]
        assert [c[0] for c in block] == CONDITIONS
        assert len({(c[1], c[2]) for c in block}) == 1


def test_blocked_sweep_executes_in_blocks(tmp_path, monkeypatch):
    result, calls, _ = _run_stubbed(tmp_path, monkeypatch)
    assert result.rows_written == 12
    assert [c[0] for c in calls] == [sc for sc in CONDITIONS for _ in range(4)]
    assert result.execution_order == "blocked"


# ------------------------------------------------------- F7: execution index

def test_execution_index_is_recorded_and_monotonic(tmp_path, monkeypatch):
    result, calls, spec = _run_stubbed(tmp_path, monkeypatch,
                                       execution_order="interleaved")
    idx = [e["execution_index"] for e in result.execution_log]
    assert idx == list(range(len(calls))), "execution index is not monotonic"
    # the log records the REALIZED order, so it can be replayed against calls
    assert [(e["scenario"], e["scenario_seed"], e["sampler_seed"])
            for e in result.execution_log] == calls
    # and it is persisted, so the order is auditable from evidence alone
    rows = [json.loads(l) for l in open(spec["manifest"], encoding="utf-8")]
    assert [r["execution_index"] for r in rows] == list(range(12))
    assert {r["execution_order"] for r in rows} == {"interleaved"}


def test_execution_index_is_opt_in_under_blocked(tmp_path, monkeypatch):
    """Blocked sweeps must not gain a manifest field — Phase-1 rows are frozen.
    An explicit True still turns it on for a blocked pack that wants it."""
    _, _, spec = _run_stubbed(tmp_path, monkeypatch)
    rows = [json.loads(l) for l in open(spec["manifest"], encoding="utf-8")]
    assert all("execution_index" not in r for r in rows)
    # ...but the index is always available in memory
    _, _, spec2 = _run_stubbed(tmp_path, monkeypatch,
                               record_execution_index=True, name="runs2")
    rows2 = [json.loads(l) for l in open(spec2["manifest"], encoding="utf-8")]
    assert [r["execution_index"] for r in rows2] == list(range(12))
    assert {r["execution_order"] for r in rows2} == {"blocked"}


# ------------------------------------------------ F6: typed failure classifying

def test_classify_failure_is_structural_not_textual():
    import socket
    import urllib.error

    assert classify_failure(TimeoutError("x")) == "timeout"
    assert classify_failure(socket.timeout("x")) == "timeout"
    assert classify_failure(ConnectionResetError("x")) == "connection"
    assert classify_failure(
        urllib.error.URLError(ConnectionRefusedError("x"))) == "connection"
    assert classify_failure(urllib.error.HTTPError(
        "http://h", 500, "oom", {}, None)) == "http_error"
    assert classify_failure(ValueError("x")) == "other"
    # a message that LOOKS like a timeout but is not one must not be promoted
    assert classify_failure(ValueError("read timed out after 30s")) == "other"
    # ...and a real timeout buried under a re-raise must still be found
    try:
        try:
            raise TimeoutError("underlying")
        except TimeoutError as e:
            raise RuntimeError("agent call failed") from e
    except RuntimeError as e:
        assert classify_failure(e) == "timeout"
    assert set(FAILURE_KINDS) == {"timeout", "connection", "http_error", "other"}


def test_dropout_is_charged_to_its_condition_and_never_vanishes(
        tmp_path, monkeypatch):
    """One condition times out on both sampler seeds of scenario_seed 42. The
    loss must be counted against THAT condition with the right type — the
    confound this whole guard exists for."""
    def _fail(scenario, seed, ks):
        if scenario == "scramble_perm" and seed == 42:
            return TimeoutError("planner budget 120s exceeded")
        return None

    result, calls, spec = _run_stubbed(tmp_path, monkeypatch, fail=_fail,
                                       execution_order="interleaved")
    dev = (MODEL, "scramble_dev")
    perm = (MODEL, "scramble_perm")
    sham = (MODEL, "scramble_sham")

    assert result.attempted[perm] == 4 and result.surviving[perm] == 2
    assert result.dropouts[perm]["timeout"] == 2
    assert result.dropout_total(perm) == 2
    # the untouched conditions are recorded with explicit zeros, not absent
    for other in (dev, sham):
        assert result.surviving[other] == 4
        assert result.dropouts[other] == {k: 0 for k in FAILURE_KINDS}
    # the failure is still recorded in the existing error channel, not erased
    assert len(result.errors) == 2
    assert all(e[0] == "scramble_perm" for e in result.errors)
    assert all("TimeoutError" in e[3] for e in result.errors)
    # ...and in the execution log, so the realized order stays complete
    failed = [e for e in result.execution_log if e["status"] == "failed"]
    assert len(failed) == 2
    assert {e["failure_kind"] for e in failed} == {"timeout"}
    assert [e["execution_index"] for e in result.execution_log] == \
        list(range(len(calls)))
    # the biased pack wrote only the survivors
    rows = [json.loads(l) for l in open(spec["manifest"], encoding="utf-8")]
    assert len(rows) == 10


def test_mixed_failure_kinds_are_separately_typed(tmp_path, monkeypatch):
    import urllib.error

    def _fail(scenario, seed, ks):
        if scenario != "scramble_perm":
            return None
        if ks == 2001:
            return TimeoutError("t")
        return urllib.error.HTTPError("http://h", 500, "oom", {}, None)

    result, _, _ = _run_stubbed(tmp_path, monkeypatch, fail=_fail)
    perm = (MODEL, "scramble_perm")
    assert result.dropouts[perm] == {"timeout": 2, "connection": 0,
                                     "http_error": 2, "other": 0}


# ------------------------------------------------------- F6: the balance gate

def _result_with(counts, *, attempted=None, dropouts=None):
    r = SweepResult()
    for scenario, n in counts.items():
        key = r._condition((MODEL, scenario))
        r.surviving[key] = n
        r.attempted[key] = (attempted or {}).get(scenario, n)
        for kind, c in (dropouts or {}).get(scenario, {}).items():
            r.dropouts[key][kind] = c
    return r


def test_balance_check_passes_within_the_bound():
    r = _result_with({"scramble_dev": 48, "scramble_perm": 46,
                      "scramble_sham": 47})
    assert r.check_condition_balance(2) is None


def test_balance_check_refuses_beyond_the_bound_and_names_everything():
    r = _result_with({"scramble_dev": 48, "scramble_perm": 41,
                      "scramble_sham": 47},
                     attempted={"scramble_perm": 48},
                     dropouts={"scramble_perm": {"timeout": 7}})
    with pytest.raises(SweepUnbalanced) as ei:
        r.check_condition_balance(2)
    msg = str(ei.value)
    # the offending conditions, their counts, and the bound must all be named
    assert "scramble_perm" in msg and "scramble_dev" in msg
    assert "41" in msg and "48" in msg
    assert "bound 2" in msg
    assert "'timeout': 7" in msg
    # a SweepUnbalanced is a SweepAborted, so existing callers refuse correctly
    assert isinstance(ei.value, SweepAborted)


def test_balance_check_never_pools_two_models():
    r = SweepResult()
    for model, n in (("a", 48), ("b", 10)):
        for scenario in CONDITIONS:
            key = r._condition((model, scenario))
            r.surviving[key] = n
            r.attempted[key] = n
    # each model is internally balanced; the cross-model gap is not a defect
    assert r.check_condition_balance(0) is None


def test_balance_check_requires_an_explicit_bound():
    r = _result_with({"scramble_dev": 1})
    with pytest.raises(ValueError, match="comes from the frozen design"):
        r.check_condition_balance(None)
    with pytest.raises(ValueError, match="must be >= 0"):
        r.check_condition_balance(-1)


def test_run_sweep_balance_gate_is_fail_closed(tmp_path, monkeypatch):
    """Requested from run_sweep, an unbalanced pack raises instead of returning
    an analyzable-looking result — and the evidence it did produce survives."""
    def _fail(scenario, seed, ks):
        return TimeoutError("t") if scenario == "scramble_perm" else None

    with pytest.raises(SweepUnbalanced, match="NOT analyzable"):
        _run_stubbed(tmp_path, monkeypatch, fail=_fail,
                     execution_order="interleaved", max_surviving_delta=1)
    manifest = os.path.join(str(tmp_path / "runs"), "manifest.jsonl")
    rows = [json.loads(l) for l in open(manifest, encoding="utf-8")]
    assert len(rows) == 8, "surviving evidence was discarded by the refusal"


def test_balance_gate_absent_by_default(tmp_path, monkeypatch):
    """No bound requested -> no gate. A sweep that never asks keeps today's
    behavior even when a condition loses every run."""
    def _fail(scenario, seed, ks):
        return TimeoutError("t") if scenario == "scramble_perm" else None

    result, _, _ = _run_stubbed(tmp_path, monkeypatch, fail=_fail)
    assert result.rows_written == 8 and len(result.errors) == 4


# --------------------------------------------- the load-bearing regression test

def test_default_behavior_is_unchanged(tmp_path, monkeypatch):
    """LOAD-BEARING: with none of the new options requested, a real (fixture
    backed) sweep must produce exactly the rows it produced before — same
    schema with no added fields, same order, same bytes. Phase-1 evidence
    regenerates unchanged or the m7 gate result is void."""
    _install_offline_ollama(monkeypatch)
    spec = _spec(tmp_path, seeds=(42, 1))
    result = run_sweep(spec)

    assert result.rows_written == 2
    assert result.errors == []
    rows = [json.loads(l) for l in open(spec["manifest"], encoding="utf-8")]
    # the row schema is EXACTLY the frozen one — no new field leaked in
    for row in rows:
        assert set(row) == set(REQUIRED_ROW_FIELDS), \
            f"row schema drifted: {sorted(set(row) ^ set(REQUIRED_ROW_FIELDS))}"
    assert [r["scenario_seed"] for r in rows] == [42, 1]

    # an explicit blocked/no-index run over a fresh root is byte-identical
    spec2 = _spec(tmp_path, seeds=(42, 1), name="runs2")
    run_sweep(spec2, execution_order="blocked", record_execution_index=False)
    a = open(spec["manifest"], encoding="utf-8").read()
    b = open(spec2["manifest"], encoding="utf-8").read()
    assert a == b


def test_resume_is_unchanged_and_counted_per_condition(tmp_path, monkeypatch):
    """Resume still skips recorded rows; a resumed cell counts as a survivor of
    its condition, otherwise a resumed pack would look catastrophically
    unbalanced to the gate."""
    _install_offline_ollama(monkeypatch)
    spec = _spec(tmp_path, seeds=(42, 1))
    first = run_sweep(spec)
    assert first.rows_written == 2 and first.skipped_resumed == 0

    second = run_sweep(spec)
    assert second.rows_written == 0 and second.skipped_resumed == 2
    key = (MODEL, SCENARIO)
    assert second.resumed[key] == 2 and second.surviving[key] == 2
    assert second.attempted[key] == 0
    assert second.check_condition_balance(0) is None


# ----------------- audit b-002 finding 1: retries_per_unit=0 tombstones

def _install_failing_real_runner(monkeypatch, calls, target):
    """Wrap the REAL fixture-backed run_scenario so ONE cell fails (a live-only
    timeout) while every other cell produces genuine evidence dirs — the seam
    the finding requires the tombstone regression to exercise."""
    real_run_scenario = sweep_mod.run_scenario

    def _failing(path, agent_spec, seed, **kw):
        scenario = os.path.splitext(os.path.basename(path))[0]
        ks = kw.get("sampler_seed")
        calls.append((scenario, seed, ks))
        if (scenario, seed, ks) == target:
            raise TimeoutError("planner budget 120s exceeded")
        return real_run_scenario(path, agent_spec, seed, **kw)

    monkeypatch.setattr(sweep_mod, "run_scenario", _failing)


def test_retries_per_unit_zero_tombstones_a_failure_and_never_rerolls(
        tmp_path, monkeypatch):
    """THE b-002 FINDING-1 (sweep side) REGRESSION: with retries_per_unit=0 a
    unit that fails ONCE is persisted as a durable typed tombstone; the next
    sweep over the same manifest NEVER re-attempts it (no second run_scenario /
    provider call) and the typed failure survives in durable evidence."""
    _install_offline_ollama(monkeypatch)
    calls = []
    target = ("scramble_perm", 42, 2001)
    _install_failing_real_runner(monkeypatch, calls, target)
    spec = _spec(tmp_path, scenarios=CONDITIONS, seeds=(42, 1),
                 sampler_seeds=[2001, 2002], temperature=0.7)

    first = run_sweep(spec, retries_per_unit=0)
    assert len(first.errors) == 1 and first.tombstones_written == 1
    assert calls.count(target) == 1               # attempted exactly once

    # the durable tombstone is on disk, carrying the typed failure kind
    tomb_path = spec["manifest"] + ".tombstones.jsonl"
    assert os.path.exists(tomb_path)
    tombs = [json.loads(l) for l in open(tomb_path, encoding="utf-8") if l.strip()]
    assert len(tombs) == 1
    assert tombs[0]["failure_kind"] == "timeout"
    assert tombs[0]["scenario"] == "scramble_perm"
    assert tombs[0]["scenario_seed"] == 42 and tombs[0]["sampler_seed"] == 2001

    # resume: the tombstoned cell is NOT attempted a second time — no re-roll
    n_after_first = len(calls)
    second = run_sweep(spec, retries_per_unit=0)
    assert target not in calls[n_after_first:], "a tombstoned failure was re-rolled"
    assert second.tombstoned_resumed == 1
    assert second.tombstones_written == 0
    perm = (MODEL, "scramble_perm")
    assert second.dropouts[perm]["timeout"] == 1  # the typed failure survives


def test_default_resume_still_rerolls_a_failure_no_tombstone(tmp_path, monkeypatch):
    """The historical-behaviour lock: with NO opt-in a failed unit leaves no
    tombstone and IS re-attempted on the next sweep. retries_per_unit=0 is the
    only thing that changes this — Phase-1 default resume is untouched."""
    _install_offline_ollama(monkeypatch)
    calls = []
    target = ("scramble_perm", 42, 2001)
    _install_failing_real_runner(monkeypatch, calls, target)
    spec = _spec(tmp_path, scenarios=CONDITIONS, seeds=(42, 1),
                 sampler_seeds=[2001, 2002], temperature=0.7)

    first = run_sweep(spec)
    assert first.tombstones_written == 0
    assert not os.path.exists(spec["manifest"] + ".tombstones.jsonl")
    n = len(calls)
    run_sweep(spec)
    assert target in calls[n:], "default resume must still re-attempt a failure"


def test_unsupported_retries_per_unit_is_refused(tmp_path, monkeypatch):
    """Only the frozen value 0 (or None) is contract-legal; a positive retry
    budget is refused before any compute."""
    _install_offline_ollama(monkeypatch)
    spec = _spec(tmp_path, seeds=(42,))
    for bad in (1, 2, True):
        with pytest.raises(SweepAborted, match="retries_per_unit"):
            run_sweep(spec, retries_per_unit=bad)


# ------------------------- audit c-001 finding 0 (generator side): attestation

import hashlib

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def _real_pack(tmp_path, monkeypatch, name="runs"):
    """A real (fixture-backed, offline) 1-model x 1-scenario x 2-seed pack with
    genuine run dirs, captures, and a validated manifest."""
    _install_offline_ollama(monkeypatch)
    spec = _spec(tmp_path, seeds=(42, 1), name=name)
    result = run_sweep(spec)
    assert result.rows_written == 2 and result.errors == []
    return spec, result


def test_verify_pack_replay_writes_bound_attestation(tmp_path, monkeypatch):
    """The receipt the frozen analysis path authenticates: EXACTLY the
    director-defined shape, hashes of the exact evidence bytes."""
    spec, _ = _real_pack(tmp_path, monkeypatch)
    att = verify_pack_replay(spec["manifest"], spec["out_root"],
                             spec["config_dir"])
    path = os.path.join(spec["out_root"], "replay_attestation.json")
    assert os.path.exists(path)
    on_disk = json.load(open(path, encoding="utf-8"))
    assert on_disk == att
    # top-level shape is exact — no extra keys, no missing keys
    assert set(att) == {"attestation_version", "verified_utc",
                        "manifest_sha256", "runs"}
    assert att["attestation_version"] == "1"
    assert att["manifest_sha256"] == hashlib.sha256(
        open(spec["manifest"], "rb").read()).hexdigest()
    rows = [json.loads(l) for l in open(spec["manifest"], encoding="utf-8")]
    assert set(att["runs"]) == {r["run_id"] for r in rows}
    for row in rows:
        rec = att["runs"][row["run_id"]]
        assert set(rec) == {"run_dir", "replay_ok", "run_json_sha256",
                            "decisions_sha256", "captures_sha256"}
        assert rec["run_dir"] == row["dir"]
        assert rec["replay_ok"] is True
        run_dir = os.path.join(spec["out_root"], row["dir"])
        for field, fname in (("run_json_sha256", "run.json"),
                             ("decisions_sha256", "decisions.jsonl"),
                             ("captures_sha256", "captures.jsonl")):
            assert rec[field] == hashlib.sha256(
                open(os.path.join(run_dir, fname), "rb").read()).hexdigest()


def test_verify_pack_replay_fails_closed_and_leaves_no_receipt(
        tmp_path, monkeypatch):
    """The audited failure mode: a pack whose captures cannot replay must
    RAISE and leave NO attestation — including removing a stale receipt from
    an earlier pass, so a failure can never sit next to a valid-looking one."""
    spec, _ = _real_pack(tmp_path, monkeypatch)
    att_path = os.path.join(spec["out_root"], "replay_attestation.json")
    verify_pack_replay(spec["manifest"], spec["out_root"], spec["config_dir"])
    assert os.path.exists(att_path)                     # stale receipt planted
    rows = [json.loads(l) for l in open(spec["manifest"], encoding="utf-8")]
    victim = os.path.join(spec["out_root"], rows[1]["dir"], "captures.jsonl")
    os.remove(victim)                                   # the auditor's fixture: no captures
    with pytest.raises(Exception):
        verify_pack_replay(spec["manifest"], spec["out_root"],
                           spec["config_dir"])
    assert not os.path.exists(att_path), \
        "a failing pack kept a valid-looking attestation"
    assert not os.path.exists(att_path + ".tmp")


def test_verify_pack_replay_refuses_missing_or_empty_manifest(tmp_path):
    with pytest.raises(SweepAborted, match="no manifest"):
        verify_pack_replay(str(tmp_path / "absent.jsonl"), str(tmp_path),
                           os.path.join(ROOT, "configs", "scenarios"))
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(SweepAborted, match="no rows"):
        verify_pack_replay(str(empty), str(tmp_path),
                           os.path.join(ROOT, "configs", "scenarios"))


def test_file_sha256_absent_captures_hash_as_empty_file(tmp_path):
    """Scripted runs write no captures.jsonl; the attestation records the
    empty-file hash for them by contract."""
    assert _file_sha256(str(tmp_path / "nope.jsonl"),
                        absent_as_empty=True) == EMPTY_SHA256
    with pytest.raises(FileNotFoundError):
        _file_sha256(str(tmp_path / "nope.jsonl"))      # default stays strict
    p = tmp_path / "some.jsonl"
    p.write_bytes(b"line\n")
    assert _file_sha256(str(p)) == hashlib.sha256(b"line\n").hexdigest()
    assert _file_sha256(str(p), absent_as_empty=True) == \
        hashlib.sha256(b"line\n").hexdigest()


# --------------------- per-condition surviving counts, the coordinated shape

def test_surviving_counts_from_result_plain_dict():
    r = _result_with({"scramble_dev": 48, "scramble_perm": 46,
                      "scramble_sham": 47})
    assert surviving_counts_from_result(r) == \
        {"scramble_dev": 48, "scramble_perm": 46, "scramble_sham": 47}


def test_surviving_counts_never_pool_two_models():
    r = SweepResult()
    for model in ("a", "b"):
        for scenario in CONDITIONS:
            key = r._condition((model, scenario))
            r.surviving[key] = 4
    with pytest.raises(SweepAborted, match="never be pooled"):
        surviving_counts_from_result(r)
