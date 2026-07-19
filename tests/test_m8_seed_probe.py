"""M8 Phase-2 (B5): the seed probe must be able to FAIL for the reason it claims.

The old probe asked for one deterministic word in 8 tokens and compared same-seed
calls only. A backend that silently drops `options.seed` sailed through it, which
would have turned distinct-seed runs into anonymous randomness wearing
identified-replicate labels — `sampler_seed` is part of both the effective-unit
key and `run_hash`.

Every test here is offline: `_post` is monkeypatched and no real server is ever
contacted.
"""

import pytest

from coliseum.textlab.agents import (PLANNER_BUDGET, SEED_PROBE_ALT_SEED_OFFSET,
                                     SEED_PROBE_PROMPT, MockLLMAgent, OllamaAgent,
                                     agent_config_hash)
from coliseum.textlab.schema import SchemaError, config_hash

STOCH = {"mode": "stochastic", "temperature": 0.7}
DETERM = {"mode": "deterministic", "temperature": 0}


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


# -- invariants: nothing else moved -----------------------------------------

def test_mock_agent_remains_trivially_verified():
    agent = MockLLMAgent("steward_obedient")
    assert agent.verify_seeded_sampling() is True
    assert agent.backend_seed_supported is True
    assert agent.seed_probe["seed_probe_result"] == "verified"
    assert agent.seed_probe["backend_name"] == "mock"


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
