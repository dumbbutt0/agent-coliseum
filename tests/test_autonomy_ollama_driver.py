"""The ollama_local live-experiment driver (tools/autonomy/drivers.py) and the
shared sweep core (coliseum/textlab/sweep.py).

Everything here runs OFFLINE: the two live seams — the digest-pinning probe
(`OllamaAgent`) and the per-run executor (`run_scenario`) — are monkeypatched to
the fixture-backed MockLLMAgent, so the full driver pipeline (digest gate, sweep,
manifest, byte-identical replay of every run) is exercised with zero network. The
security-critical refusals (a repulled/served digest that differs from the frozen
one, an unreachable endpoint, a wall-clock deadline) are asserted directly."""
import json
import os

import pytest

import coliseum.textlab.runner as runner_mod
import coliseum.textlab.sweep as sweep_mod
from coliseum.textlab.agents import MockLLMAgent, make_agent as real_make_agent
from coliseum.textlab.sweep import (SweepAborted, resolve_sampling, run_sweep,
                                    verify_run_replay)
from tools.autonomy.drivers import DRIVERS, RunnerRefusal, _drive_ollama_local

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = "steward_obedient"     # covers corrupt_king (execute -> verify -> refuse)
SCENARIO = "corrupt_king"
MODEL = "llama3.1:latest"


def _fixture_digest():
    return MockLLMAgent(FIXTURE).model_digest


def _mk_mock(model):
    """A fixture-backed agent that reports the REAL model name — so the sweep's
    probe and the per-run agent (both built from this) share one hashed identity
    and the manifest row's model/digest agree with the run.json evidence."""
    a = MockLLMAgent(FIXTURE)
    a.model = model
    a.agent_id = f"llm:ollama:{model}"
    return a


def _install_offline_ollama(monkeypatch, *, digest=None, reachable=True):
    """Swap both live seams for the fixture-backed mock: the digest-pinning probe
    (sweep.OllamaAgent) and the per-run executor's agent factory
    (runner.make_agent). Replay uses agent_from_manifest, which never touches the
    network, so no seam is needed there."""
    served = digest if digest is not None else _fixture_digest()

    def _fake_probe(model, host=None):
        probe = _mk_mock(model)
        probe.host = host or "http://mock"
        if not reachable:
            probe.digest_status = "missing"
            probe.model_digest = ""
        elif digest is not None:      # deliberately force a served-digest mismatch
            probe.model_digest = served
        return probe

    def _fake_make_agent(spec):
        if spec.startswith("llm:ollama:"):
            return _mk_mock(spec.split("llm:ollama:", 1)[1])
        return real_make_agent(spec)

    monkeypatch.setattr(sweep_mod, "OllamaAgent", _fake_probe)
    monkeypatch.setattr(runner_mod, "make_agent", _fake_make_agent)
    return served


def _config(tmp_path, **over):
    out_root = str(tmp_path / "runs")
    cfg = {"task_id": "m6-sequential-baseline",
           "models": [MODEL], "scenarios": [SCENARIO], "seeds": [42],
           "sampler_seeds": None, "temperature": 0.0,
           "arbitration": "planner_priority",
           "interaction": "independent_vignettes",
           "config_dir": "configs/scenarios",
           "out_root": out_root,
           "manifest": os.path.join(out_root, "manifest.jsonl"),
           "model_digests": {MODEL: _fixture_digest()},
           "expected_run_count": 1}
    cfg.update(over)
    return cfg


def _far_deadline():
    import time
    return time.monotonic() + 600


# --------------------------------------------------------------- registration

def test_ollama_local_is_registered():
    assert DRIVERS.get("ollama_local") is _drive_ollama_local


# ------------------------------------------------------------------ happy path

def test_full_pipeline_offline(tmp_path, monkeypatch):
    _install_offline_ollama(monkeypatch)
    cfg = _config(tmp_path)
    outcome = _drive_ollama_local(ROOT, cfg, _far_deadline())

    assert outcome["run_dir"] == os.path.relpath(cfg["out_root"], ROOT)
    assert outcome["run_id"] == "m6-sequential-baseline"
    val = {v["name"]: v for v in outcome["validations"]}
    assert val["fleet_digests_match_pinned"]["ok"]
    assert val["sweep_completed_without_errors"]["ok"]
    assert val["manifest_run_count"]["ok"]
    assert val["manifest_run_count"]["got"] == 1
    assert val["offline_replay_byte_identical"]["ok"]
    assert val["offline_replay_byte_identical"]["runs_checked"] == 1
    # the evidence really exists under the pinned out_root
    rows = [json.loads(l) for l in open(cfg["manifest"], encoding="utf-8")]
    assert len(rows) == 1 and rows[0]["model"] == MODEL


def test_resume_is_idempotent(tmp_path, monkeypatch):
    """A second identical run adds no rows and still passes — the manifest is
    keyed by (regime, scenario_seed, sampler_seed)."""
    _install_offline_ollama(monkeypatch)
    cfg = _config(tmp_path)
    _drive_ollama_local(ROOT, cfg, _far_deadline())
    outcome = _drive_ollama_local(ROOT, cfg, _far_deadline())
    val = {v["name"]: v for v in outcome["validations"]}
    assert val["manifest_run_count"]["written_this_call"] == 0
    assert val["manifest_run_count"]["resumed"] == 1
    assert val["manifest_run_count"]["got"] == 1


# ------------------------------------------------------------- digest integrity

def test_served_digest_mismatch_refuses(tmp_path, monkeypatch):
    """A served digest that differs from the frozen one is a NEW regime — the
    sweep aborts BEFORE any run and the driver refuses."""
    _install_offline_ollama(monkeypatch, digest="sha256:repulled-different")
    cfg = _config(tmp_path)   # model_digests still pins the ORIGINAL fixture digest
    with pytest.raises(RunnerRefusal, match="NEW regime"):
        _drive_ollama_local(ROOT, cfg, _far_deadline())
    # aborted before any run — the manifest may be an empty touched file, but
    # no evidence rows and no run dirs were produced
    rows = [l for l in open(cfg["manifest"], encoding="utf-8")] \
        if os.path.exists(cfg["manifest"]) else []
    assert rows == []
    assert not any(p not in ("manifest.jsonl",)
                   for p in os.listdir(cfg["out_root"]))


def test_unreachable_endpoint_refuses(tmp_path, monkeypatch):
    _install_offline_ollama(monkeypatch, reachable=False)
    cfg = _config(tmp_path)
    with pytest.raises(RunnerRefusal, match="could not be pinned"):
        _drive_ollama_local(ROOT, cfg, _far_deadline())


def test_deadline_already_passed_refuses(tmp_path, monkeypatch):
    import time
    _install_offline_ollama(monkeypatch)
    cfg = _config(tmp_path)
    with pytest.raises(RunnerRefusal, match="deadline"):
        _drive_ollama_local(ROOT, cfg, time.monotonic() - 1)


# ---------------------------------------------------------------- run counting

def test_expected_run_count_mismatch_flags(tmp_path, monkeypatch):
    _install_offline_ollama(monkeypatch)
    cfg = _config(tmp_path, expected_run_count=99)
    outcome = _drive_ollama_local(ROOT, cfg, _far_deadline())
    val = {v["name"]: v for v in outcome["validations"]}
    assert not val["manifest_run_count"]["ok"]
    assert val["manifest_run_count"]["got"] == 1


# --------------------------------------------------------------- sampling gate

def test_stochastic_requires_sampler_seeds():
    with pytest.raises(SweepAborted, match="requires sampler_seeds"):
        resolve_sampling(0.7, None)
    sampling, seeds, mode = resolve_sampling(0.7, [11, 12])
    assert mode == "stochastic" and seeds == [11, 12]
    sampling, seeds, mode = resolve_sampling(0.0, None)
    assert mode == "deterministic" and seeds == [None] and sampling is None


# ----------------------------------------------------------------- replay gate

def test_replay_detects_tampered_decisions(tmp_path, monkeypatch):
    """verify_run_replay is the byte-identity gate: tampering a produced
    decisions.jsonl makes it fail."""
    _install_offline_ollama(monkeypatch)
    cfg = _config(tmp_path)
    _drive_ollama_local(ROOT, cfg, _far_deadline())
    row = json.loads(open(cfg["manifest"], encoding="utf-8").readline())
    run_dir = os.path.join(cfg["out_root"], row["dir"])
    config_dir = os.path.join(ROOT, "configs", "scenarios")
    ok, _ = verify_run_replay(run_dir, config_dir)
    assert ok
    dec = os.path.join(run_dir, "decisions.jsonl")
    with open(dec, "a", encoding="utf-8") as fh:
        fh.write('{"kind":"tamper"}\n')
    ok, detail = verify_run_replay(run_dir, config_dir)
    assert not ok and "differs" in detail
