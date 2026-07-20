"""M8 Phase-2 (B5): the seed probe must be able to FAIL for the reason it claims.

The old probe asked for one deterministic word in 8 tokens and compared same-seed
calls only. A backend that silently drops `options.seed` sailed through it, which
would have turned distinct-seed runs into anonymous randomness wearing
identified-replicate labels — `sampler_seed` is part of both the effective-unit
key and `run_hash`.

Every test here is offline: `_post` is monkeypatched and no real server is ever
contacted.
"""

import json
import os

import pytest
import yaml

from coliseum.textlab.agents import (M8_DECODER_CONTROLS, PLANNER_BUDGET,
                                     SEED_PROBE_ALT_SEED_OFFSET,
                                     SEED_PROBE_PROMPT, LLMAgent, MockLLMAgent,
                                     OllamaAgent, agent_config_hash)
from coliseum.textlab.schema import (SchemaError, build_behavioral_config,
                                     config_hash, regime_hashes)

STOCH = {"mode": "stochastic", "temperature": 0.7}
DETERM = {"mode": "deterministic", "temperature": 0}
M8_SAMPLING = {"mode": "stochastic", "temperature": 0.7}


def _build(monkeypatch, responder):
    """An OllamaAgent whose every backend touch is faked. `responder(seed, call_n)`
    returns the response text. Records the options actually sent."""
    monkeypatch.setattr(OllamaAgent, "_fetch_digest",
                        lambda self: (setattr(self, "model_digest", "sha256:beef"),
                                      setattr(self, "digest_status", "ok")))
    monkeypatch.setattr(OllamaAgent, "_backend_version", lambda self: "0.9.9")
    sent = []

    def _post(self, prompt, num_predict, timeout_s, options_override=None):
        opts = options_override if options_override is not None else self._options(num_predict)
        sent.append({"prompt": prompt, "num_predict": num_predict,
                     "timeout_s": timeout_s, "options": dict(opts)})
        return {"response": responder(opts.get("seed"), len(sent) - 1)}

    monkeypatch.setattr(OllamaAgent, "_post", _post)
    agent = OllamaAgent("fake:1b")
    agent._sent = sent
    return agent


def _arms(agent):
    return {a["arm"]: a for a in agent.seed_probe["seed_probe_arms"]}


# -- the three backend behaviours -------------------------------------------

def test_seed_honoring_backend_passes_both_arms(monkeypatch):
    """Same seed -> same text; different seed -> different text. The only backend
    that can actually support seeded replication."""
    agent = _build(monkeypatch, lambda seed, n: f"lorquin brenth {seed}")
    agent.configure_sampling(STOCH, 2001)

    assert agent.verify_seeded_sampling() is True
    assert agent.backend_seed_supported is True
    assert agent.seed_probe["seed_probe_result"] == "verified"
    arms = _arms(agent)
    assert arms["same_seed_reproducibility"]["outcome"] == "pass"
    assert arms["different_seed_divergence"]["outcome"] == "pass"


def test_seed_ignoring_random_backend_fails_reproducibility_arm(monkeypatch):
    """A backend that drops options.seed and samples freshly every call cannot
    reproduce its own output — the same-seed arm catches it."""
    agent = _build(monkeypatch, lambda seed, n: f"drifting output {n}")
    agent.configure_sampling(STOCH, 2001)

    assert agent.verify_seeded_sampling() is False
    assert agent.backend_seed_supported is False
    assert agent.seed_probe["seed_probe_result"] == "failed"
    assert _arms(agent)["same_seed_reproducibility"]["outcome"] == "fail"


def test_constant_backend_is_rejected_by_divergence_arm(monkeypatch):
    """THE regression this section exists for. A backend that returns identical
    text no matter the seed passed the OLD probe (same-seed equality was its only
    test) while providing no seeded replication whatsoever. It must now fail: the
    same-seed arm still passes, and the different-seed arm rejects it."""
    agent = _build(monkeypatch, lambda seed, n: "ready")
    agent.configure_sampling(STOCH, 2001)

    assert agent.verify_seeded_sampling() is False
    assert agent.backend_seed_supported is False
    assert agent.seed_probe["seed_probe_result"] == "failed"
    arms = _arms(agent)
    assert arms["same_seed_reproducibility"]["outcome"] == "pass"   # old probe stopped here
    assert arms["different_seed_divergence"]["outcome"] == "fail"   # and this is the catch


# -- what the probe actually sends ------------------------------------------

def test_probe_uses_planner_budget_and_high_entropy_prompt(monkeypatch):
    """Realistic budget, not 8 tokens; neutral high-entropy prompt, never a
    scenario prompt (that would contaminate)."""
    agent = _build(monkeypatch, lambda seed, n: f"w{seed}")
    agent.configure_sampling(STOCH, 2001)
    agent.verify_seeded_sampling()

    assert len(agent._sent) == 3               # two same-seed + one different-seed
    for call in agent._sent:
        assert call["prompt"] == SEED_PROBE_PROMPT
        assert call["num_predict"] == PLANNER_BUDGET["num_predict"] == 350
        assert call["timeout_s"] == PLANNER_BUDGET["timeout_s"]
        assert call["options"]["temperature"] == 0.7
    seeds = [c["options"]["seed"] for c in agent._sent]
    assert seeds == [2001, 2001, 2001 + SEED_PROBE_ALT_SEED_OFFSET]
    assert agent.seed_probe["seed_probe_prompt_hash"] == config_hash(SEED_PROBE_PROMPT)
    assert agent.seed_probe["seed_probe_num_predict"] == 350


def test_both_arms_recorded_with_seeds_and_result_hashes(monkeypatch):
    """An auditor must see what was tested, not a bare boolean."""
    agent = _build(monkeypatch, lambda seed, n: f"w{seed}")
    agent.configure_sampling(STOCH, 2001)
    agent.verify_seeded_sampling()
    arms = _arms(agent)

    same = arms["same_seed_reproducibility"]
    assert same["seeds"] == [2001, 2001]
    assert same["expectation"] == "identical"
    assert same["response_hashes"] == [config_hash("w2001")] * 2

    diff = arms["different_seed_divergence"]
    alt = 2001 + SEED_PROBE_ALT_SEED_OFFSET
    assert diff["seeds"] == [2001, alt]
    assert diff["expectation"] == "different"
    assert diff["response_hashes"] == [config_hash("w2001"), config_hash(f"w{alt}")]
    assert len(set(diff["response_hashes"])) == 2

    # scoping honesty preserved: never a universal claim
    assert "only" in agent.seed_probe["seed_probe_scope"]
    assert agent.seed_probe["backend_name"] == "ollama"
    assert agent.seed_probe["backend_version"] == "0.9.9"
    assert agent.seed_probe["model_digest"] == "sha256:beef"
    assert agent.seed_probe["seed_probe_timestamp"]


def test_divergence_arm_not_applicable_under_deterministic_decoding(monkeypatch):
    """At temperature 0 a correct backend SHOULD ignore the seed, so divergence is
    not a defect — it is recorded not_applicable, and the probe still verifies."""
    agent = _build(monkeypatch, lambda seed, n: "ready")
    agent.configure_sampling(DETERM, None)
    agent.sampler_seed = 42                     # temp-0 pilot style: seeded anyway

    assert agent.verify_seeded_sampling() is True
    arms = _arms(agent)
    assert arms["same_seed_reproducibility"]["outcome"] == "pass"
    assert arms["different_seed_divergence"]["outcome"] == "not_applicable"
    assert len(agent._sent) == 2                # no third call


def test_unseeded_probe_runs_nothing_and_stays_unverified(monkeypatch):
    """No seed set: both arms not_run, no backend calls, and the agent reports
    unverified so the runner still emits backend_seed_unverified."""
    agent = _build(monkeypatch, lambda seed, n: "x")
    agent.configure_sampling(DETERM, None)

    assert agent.verify_seeded_sampling() is False
    assert agent.backend_seed_supported is False
    assert agent._sent == []
    arms = _arms(agent)
    assert arms["same_seed_reproducibility"]["outcome"] == "not_run"
    assert arms["different_seed_divergence"]["outcome"] == "not_run"


# -- the generic (non-Ollama) path fails closed (audit c-001, finding 1) -----

def test_base_llm_agent_fails_closed_without_arm_evidence():
    """The base class has no falsifiable arms to run, so it must record itself
    UNVERIFIED with honest not_run arms — never a bare 'verified' stamp. This
    is the path every backend without an override now inherits."""
    agent = LLMAgent("anything")
    agent.configure_sampling(STOCH, 2001)
    assert agent.verify_seeded_sampling() is False
    assert agent.backend_seed_supported is False
    assert agent.seed_probe["seed_probe_result"] == "failed"
    arms = _arms(agent)
    assert arms["same_seed_reproducibility"]["outcome"] == "not_run"
    assert arms["different_seed_divergence"]["outcome"] == "not_run"
    assert "only" in agent.seed_probe["seed_probe_scope"]


def test_seed_ignoring_mock_fails_divergence_arm():
    """A mock whose fixture output genuinely ignores the seed must FAIL the
    different-seed arm — previously it inherited an unconditional 'verified'
    from the base class with zero arm evidence (the audited false pass)."""
    agent = MockLLMAgent("steward_obedient")      # no seed_probe@seed keys
    agent.configure_sampling(STOCH, 2001)
    assert agent.verify_seeded_sampling() is False
    assert agent.backend_seed_supported is False
    assert agent.seed_probe["seed_probe_result"] == "failed"
    assert agent.seed_probe["backend_name"] == "mock"
    arms = _arms(agent)
    assert arms["same_seed_reproducibility"]["outcome"] == "pass"   # deterministic lookup reproduces
    assert arms["different_seed_divergence"]["outcome"] == "fail"   # ...but never diverges
    assert arms["different_seed_divergence"]["seeds"] == \
        [2001, 2001 + SEED_PROBE_ALT_SEED_OFFSET]
    assert len(set(arms["different_seed_divergence"]["response_hashes"])) == 1


def test_seed_honoring_mock_fixture_verifies_with_recorded_arms():
    """Fixture-declared seed sensitivity (seed_probe@seed<k> keys) is the ONLY
    way a mock verifies now — and the arms carry inspectable hash evidence."""
    agent = MockLLMAgent("steward_obedient_seeded")
    agent.configure_sampling(STOCH, 2001)
    assert agent.verify_seeded_sampling() is True
    assert agent.backend_seed_supported is True
    assert agent.seed_probe["seed_probe_result"] == "verified"
    arms = _arms(agent)
    assert arms["same_seed_reproducibility"]["outcome"] == "pass"
    assert arms["different_seed_divergence"]["outcome"] == "pass"
    assert len(set(arms["different_seed_divergence"]["response_hashes"])) == 2
    assert agent.seed_probe["seed_probe_prompt_hash"] == config_hash(SEED_PROBE_PROMPT)


def test_mock_probe_never_touches_captures_and_unseeded_stays_unverified():
    """Probe responses resolve directly from fixture data — never through the
    capture path — and a seedless mock records not_run arms, unverified."""
    agent = MockLLMAgent("steward_obedient_seeded")
    agent.configure_sampling(STOCH, 2001)
    agent.verify_seeded_sampling()
    assert agent.captures == []
    unseeded = MockLLMAgent("steward_obedient_seeded")
    assert unseeded.verify_seeded_sampling() is False
    arms = _arms(unseeded)
    assert arms["same_seed_reproducibility"]["outcome"] == "not_run"
    assert arms["different_seed_divergence"]["outcome"] == "not_run"
    assert unseeded.captures == []


# -- invariants: nothing else moved -----------------------------------------


def test_mock_spec_dict_is_byte_identical_to_pre_change_baseline():
    """Lineage pin: spec_dict() feeds behavioral_config -> run_hash -> run_id.
    These literals are the values produced by the code BEFORE the probe rewrite;
    if any of them moves, Phase-1 evidence stops regenerating and run_ids shift."""
    agent = MockLLMAgent("garbled")
    assert agent.spec_dict() == {
        "kind": "llm",
        "backend": "mock",
        "agent_id": "llm:mock:garbled",
        "model": "garbled",
        "model_digest": "sha256:66fd3a3419d102b2f7dd1841",
        "sampling": {"mode": "deterministic", "temperature": 0},
        "constitution": "",
        "reflex_budget": {"num_predict": 80, "timeout_s": 30},
        "planner_budget": {"num_predict": 350, "timeout_s": 120},
        "prompt_template_version": "1",
        "prompt_template_hash":
            "df04572d8adc3b710668e6d2df1a6bd8a293ffd773d666bce62260625e8a7f03",
        "parser_version": "3",
        "think_requested": "off",
        "effective_think_mode": "n/a",
        "backend_version": "n/a",
    }
    assert agent_config_hash(agent) == \
        "4cc3c95c0ac2b423799831929f8a4d053c38e9217c45a73d60b1114ac7b80370"


def test_seed_probe_is_not_part_of_the_hashed_spec(monkeypatch):
    """The probe evidence is log-only. Running it must not perturb the lineage."""
    agent = _build(monkeypatch, lambda seed, n: f"w{seed}")
    agent.configure_sampling(STOCH, 2001)
    before = agent_config_hash(agent)
    agent.verify_seeded_sampling()
    assert agent_config_hash(agent) == before
    assert "seed_probe" not in agent.spec_dict()
    assert agent.seed_probe["seed_probe_arms"]        # but it IS in llm_info
    assert agent.llm_info()["seed_probe"] == agent.seed_probe


def test_probe_calls_do_not_leak_into_captures(monkeypatch):
    """Probe is warmup-adjacent: never captured, never latency-measured."""
    agent = _build(monkeypatch, lambda seed, n: f"w{seed}")
    agent.configure_sampling(STOCH, 2001)
    agent.verify_seeded_sampling()
    assert agent.captures == []
    assert agent._warm is True


def test_replay_agent_still_cannot_contact_a_provider():
    from coliseum.textlab.agents import agent_from_manifest
    manifest = {"agent_id": "llm:ollama:fake:1b",
                "agent_config": {"backend": "ollama", "model": "fake:1b"}}
    replay = agent_from_manifest(manifest)
    with pytest.raises(SchemaError):
        replay._generate("anything", PLANNER_BUDGET)


# -- b-002 finding f0: the model regime freezes EVERY decoder control ---------
#
# f0 reproduced a hole: with only temperature, num_predict, and seed sent, two
# hosts with the same digest/backend but a different EFFECTIVE CONTEXT LENGTH
# executed and pooled under one agent_regime_id. The regime now sends and hashes
# every output-distribution knob, and resolves the effective num_ctx before the
# hash. These tests are the minimum_regression: exact emitted options + per-
# control lineage sensitivity + provenance-gate refusal of a substitution.

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REGISTRY = os.path.join(_REPO, "configs", "registry", "experiments.yaml")
_M8_CONFIG = os.path.join(
    _REPO, "configs", "experiments",
    "m8-phase2-live-order-sensitivity.experiment.json")


def _agent_regime_id(agent):
    """The agent-side regime hash the twin pairing keys on — num_ctx and every
    frozen decoder control must move it."""
    bc = build_behavioral_config(
        "scramble_dev_m8", "shash", agent.spec_dict(),
        "planner_priority", "2", M8_SAMPLING,
        interaction_mode="sequential_history",
        history_template_version="1", history_template_hash="deadbeef")
    return regime_hashes(bc)[1]


def test_scenario_request_emits_every_frozen_decoder_control(monkeypatch):
    """The EXACT options an M8 scenario request sends carry every frozen decoder
    control at its frozen value — num_ctx included. No knob is left to a backend
    default."""
    agent = _build(monkeypatch, lambda seed, n: "x")
    agent.configure_sampling(M8_SAMPLING, 2001)
    opts = agent._options(PLANNER_BUDGET["num_predict"])
    assert opts == {"temperature": 0.7, "num_predict": 350,
                    "top_p": 0.9, "top_k": 40, "repeat_penalty": 1.1,
                    "num_ctx": 8192, "stop": [], "seed": 2001}
    for k, v in M8_DECODER_CONTROLS.items():
        assert opts[k] == v, k
    # and the hashed spec carries the same controls (via sampling)
    assert agent.spec_dict()["sampling"]["num_ctx"] == 8192


def test_each_decoder_control_moves_the_agent_regime_id(monkeypatch):
    """Vary each frozen control independently: the lineage hash cannot stay
    equal across the change (this is what pooling under one regime id would
    require)."""
    agent = _build(monkeypatch, lambda seed, n: "x")
    agent.configure_sampling(M8_SAMPLING, 2001)
    base = _agent_regime_id(agent)
    for k, alt in [("num_ctx", 4096), ("top_p", 0.8), ("top_k", 50),
                   ("repeat_penalty", 1.2), ("stop", ["END"])]:
        saved = agent.sampling[k]
        agent.sampling[k] = alt
        assert _agent_regime_id(agent) != base, k
        agent.sampling[k] = saved
    assert _agent_regime_id(agent) == base           # exact restoration


def test_effective_context_length_is_resolved_before_hashing(monkeypatch):
    """Two hosts with the SAME digest and backend version but different model
    context capabilities resolve to different EFFECTIVE num_ctx before the
    regime is hashed, so the one that must clamp can never pool with the one
    that honors the full request — resolved exactly like think-mode/
    backend_version, before the hash."""
    def resolved_host(cap):
        agent = _build(monkeypatch, lambda seed, n: "x")
        agent.configure_sampling(M8_SAMPLING, 2001)
        # same requested num_ctx (8192) for both; only the backend capability
        # differs, so any regime-id split is due to the RESOLVED context length
        monkeypatch.setattr(OllamaAgent, "_effective_num_ctx",
                            lambda self, req, _cap=cap: min(req, _cap))
        agent.resolve_effective_config()
        return agent

    full_host = resolved_host(32768)     # capability >= request -> stays 8192
    small_host = resolved_host(4096)     # capability < request  -> clamped 4096
    assert full_host.sampling["num_ctx"] == 8192
    assert small_host.sampling["num_ctx"] == 4096
    # same backend_version on both (0.9.9), so the ONLY difference is num_ctx
    assert full_host.backend_version == small_host.backend_version == "0.9.9"
    assert _agent_regime_id(full_host) != _agent_regime_id(small_host)


def test_effective_num_ctx_falls_back_to_requested_when_unreachable(monkeypatch):
    """An unreachable /api/show never silently drops num_ctx — it resolves to
    the requested value, which the agent still sends explicitly (never a backend
    default)."""
    import urllib.request
    agent = _build(monkeypatch, lambda seed, n: "x")
    agent.configure_sampling(M8_SAMPLING, 2001)
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("down")))
    assert agent._effective_num_ctx(8192) == 8192


def test_provenance_lint_refuses_a_decoder_control_substitution(tmp_path):
    """Vary a control in the committed config: the provenance gate refuses it —
    both because the config no longer realizes the frozen design and because the
    audited code profile pins num_ctx independently of design_hash."""
    from coliseum.textlab.registry import lint_experiment_config
    cfg = json.load(open(_M8_CONFIG))
    cfg["decoder_controls"] = dict(cfg["decoder_controls"], num_ctx=4096)
    p = tmp_path / "substituted.experiment.json"
    p.write_text(json.dumps(cfg))
    issues = lint_experiment_config(str(p), _REGISTRY, _REPO)
    assert any("decoder_controls" in i for i in issues), issues
    assert any("num_ctx" in i and "4096" in i for i in issues), issues


def test_mutate_rehash_mirror_attack_on_decoder_controls_is_refused(tmp_path):
    """The strongest form: weaken num_ctx in BOTH the design and the config,
    recompute design_hash, and mirror it so every pairwise equality passes. The
    audited-code profile (registry.M8_FROZEN_PROFILE) still refuses, because it
    is not derived from the artifact being checked."""
    from coliseum.textlab.registry import (design_hash, lint_experiment_config,
                                           lint_experiments_registry)
    raw = yaml.safe_load(open(_REGISTRY))
    e = next(x for x in raw["experiments"]
             if x["experiment_id"] == "m8-phase2-live-order-sensitivity")
    e["planned_design"]["decoder_controls"]["num_ctx"] = 4096   # weaken
    e["design_hash"] = design_hash(e["planned_design"])         # attacker rehash
    reg = tmp_path / "experiments.yaml"
    reg.write_text(yaml.safe_dump(raw))
    cfg = json.load(open(_M8_CONFIG))
    cfg["decoder_controls"]["num_ctx"] = 4096                   # mirror
    cfg["design_hash"] = e["design_hash"]
    cfgp = tmp_path / "mirrored.experiment.json"
    cfgp.write_text(json.dumps(cfg))
    # hash reconstruction now passes; the audited-code profile does not
    issues = lint_experiment_config(str(cfgp), str(reg), _REPO)
    assert any("audited frozen" in i and "num_ctx" in i for i in issues), issues
    reg_issues = [i for i in lint_experiments_registry(str(reg), _REPO)
                  if "m8-phase2" in i]
    assert any("audited frozen" in i and "num_ctx" in i for i in reg_issues), \
        reg_issues
