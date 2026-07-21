"""The frozen entry-to-report path, exercised end to end on REAL runner output.

Audit finding 1 (event 001803, HIGH) had a two-part minimum_regression. The first
part — assert the design-hashed analysis callable — lives with the registry
identity tests. This module is the second part, and it is the one that binds
BEHAVIOUR rather than text:

    "run the real-runner garbled pack through the frozen entry-to-report path,
     proving refusal with no distances and no old-comparator result."

Why that distinction matters. A lint can only check what a document *says*. These
tests check what the instrument *does* when driven from the frozen design: bounds
are read from the registry (which refuses to serve them unless `design_hash`
reconstructs), and the pack is produced by the real runner rather than by
synthetic fixtures.

AT ORDER_REPORT_VERSION 5 the frozen path additionally demands the clause-0
evidence admission surfaces, so this module now drives them on real runner
output too: the pack is the FULL frozen grid (3 conditions x 2 scenario seeds x
24 sampler seeds = 144 runs — a partial grid refuses at the matched-unit gate
before the policy gate is ever reached), the replay attestation is generated
inline with hashlib over the pack's actual current bytes (the Director-defined
contract the sweep-side generator emits), the frozen terminal probe identity
`d_partner` is passed explicitly, and the execution census is declared.

The pack is generated here rather than read from `logs/runs/`, which is
gitignored — the regression must reproduce in a fresh checkout with no evidence
tree. `llm:mock:garbled_m8_seeded` is a committed fixture that emits genuinely unparseable
output, so every terminal decision is a parse fallback. It contacts no provider.

The property under test is the one the whole slice exists for: because a fallback
resolves to the FIRST available action, and that action is identical in every
condition, wholly unreadable output does not converge to noise — it converges to
a *perfect null*. The Phase-1 comparator reports that null with confidence. The
frozen path must refuse it.
"""
import hashlib
import json
import os

import pytest

from coliseum.textlab.metrics import (order_sensitivity_report,
                                      scramble_terminal_distribution)
from coliseum.textlab.registry import (load_admissibility_policy,
                                       load_thresholds)
from coliseum.textlab.runner import run_scenario
from coliseum.textlab.schema import SchemaError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "configs", "registry", "experiments.yaml")
CONFIG_DIR = os.path.join(ROOT, "configs", "scenarios")
EID = "m8-phase2-live-order-sensitivity"

CONDITIONS = {"A": "scramble_dev_m8", "B": "scramble_perm_m8",
              "C": "scramble_sham_m8"}
_PATH = {c: os.path.join(CONFIG_DIR, f"{s}.yaml") for c, s in CONDITIONS.items()}
TERMINAL_DP_ID = "d_partner"
SCENARIO_SEEDS = (42, 1)                     # -> v0_caravan, v1_workshop
SAMPLER_SEEDS = tuple(range(2001, 2025))     # the 24 frozen sampler seeds
SURVIVING = {"A": 48, "B": 48, "C": 48}


def _attest(dirs):
    """The Director-defined replay attestation, generated inline with hashlib
    over each run's CURRENT run.json / decisions.jsonl / captures.jsonl bytes —
    exactly the contract the sweep-side generator emits."""
    runs = {}
    for d in dirs:
        with open(os.path.join(d, "run.json"), encoding="utf-8") as fh:
            run = json.load(fh)
        entry = {"replay_ok": True}
        for fname, key in (("run.json", "run_json_sha256"),
                           ("decisions.jsonl", "decisions_sha256"),
                           ("captures.jsonl", "captures_sha256")):
            with open(os.path.join(d, fname), "rb") as fh:
                entry[key] = hashlib.sha256(fh.read()).hexdigest()
        runs[run["run_id"]] = entry
    return {"attestation_version": "1", "runs": runs}


@pytest.fixture(scope="module")
def garbled_pack(tmp_path_factory):
    """A real FULL-GRID A/B/C pack (144 runs) whose every terminal decision is a
    parse fallback.

    Offline: the mock backend serves a committed fixture, so no provider is
    contacted and the pack is byte-reproducible.
    """
    out = tmp_path_factory.mktemp("m8_frozen_path")
    dirs = []
    for cond in ("A", "B", "C"):
        for scenario_seed in SCENARIO_SEEDS:
            for sampler_seed in SAMPLER_SEEDS:
                result = run_scenario(
                    _PATH[cond], "llm:mock:garbled_m8_seeded", scenario_seed,
                    out_root=str(out),
                    arbitration="planner_priority",
                    interaction_mode="sequential_history",
                    sampling={"mode": "stochastic", "temperature": 0.7},
                    sampler_seed=sampler_seed)
                dirs.append(result.run_dir)
    return dirs


def test_the_frozen_bounds_come_from_the_design_not_the_caller():
    """Both bounds load from the registry, which refuses to serve them unless
    design_hash reconstructs. Nothing here is caller-supplied."""
    policy = load_admissibility_policy(REGISTRY, EID)
    thresholds = load_thresholds(REGISTRY, EID)
    assert policy["on_violation"] == "refuse"
    assert policy["max_non_decision_rate"] == 0.20
    # MDE re-frozen to the MEASURED-honest value (C1 re-freeze, audit a-004
    # finding 1): the OC power study showed CP-95 lower-bound power reaches the
    # 0.8 target at TV=0.35, not 0.25 (where the point estimate was 0.800 but
    # the lower bound 0.757 fell short). 0.35 is the smallest effect this design
    # can reliably detect.
    assert thresholds["min_detectable_effect"] == 0.35
    # the decision quantile must not be silently reusable as the reporting
    # interval, so the two live under separate frozen keys
    assert thresholds["alpha"] == 0.05
    assert thresholds["confidence"] == 0.95
    # v4 REQUIRED keys, frozen in the same design-hashed bundle: the sham
    # non-rejection's equivalence warrant (held intentionally TIGHTER than the
    # MDE — the sham must exclude contamination at finer resolution than the
    # order effect we claim to detect) and the dropout bound
    assert thresholds["sham_equivalence_margin"] == 0.25
    assert thresholds["max_surviving_delta"] == 2


def test_phase1_comparator_manufactures_a_confident_null_from_unreadable_output(
        garbled_pack):
    """The defect, on real runner output. This is not an indictment of Phase-1
    evidence — the comparator is correct for deterministic deciders that never
    parse. It is the reason it must not be the Phase-2 path."""
    old = scramble_terminal_distribution(garbled_pack, CONDITIONS)
    block = old["per_agent"]["llm:mock:garbled_m8_seeded"]
    # every condition collapses onto the SAME first available action
    for cond in ("A", "B", "C"):
        assert block["distributions"][cond] == {"share_resource": 1.0}
    # ...so total garbage reads as a perfect null rather than as noise
    assert block["tv_distances"]["A|B"] == 0.0
    assert block["tv_distances"]["A|C"] == 0.0


def test_frozen_path_refuses_the_garbled_pack_and_emits_no_distances(
        garbled_pack):
    """The regression the auditor asked for: driven from the frozen design, the
    instrument refuses and NO distance escapes.

    At v4 the pack clears every clause-0 evidence gate first — the inline
    attestation verifies against the pack's actual bytes, every run carries the
    frozen `d_partner` terminal probe, the matched-unit grid is fully realized
    (48 identities per condition), and the surviving counts balance — so the
    refusal is attributable to the admissibility policy alone: a 100 %
    terminal parse-fallback rate.
    """
    policy = load_admissibility_policy(REGISTRY, EID)
    thresholds = load_thresholds(REGISTRY, EID)

    with pytest.raises(SchemaError) as excinfo:
        order_sensitivity_report(garbled_pack, CONDITIONS,
                                 admissibility_policy=policy,
                                 thresholds=thresholds,
                                 replay_attestation=_attest(garbled_pack),
                                 terminal_dp_id=TERMINAL_DP_ID,
                                 surviving_counts=SURVIVING)

    message = str(excinfo.value)
    assert "non_decision_rate" in message or "admissible_effective_n" in message

    # the census is attached so an auditor can see WHY, but no number that would
    # be mistaken for a result may accompany it
    body = getattr(excinfo.value, "report", None)
    assert body is not None, "refusal must carry its census"
    assert body["order_report_version"] == "6"
    assert body["null_form"] == "swap_invariance"
    assert body["terminal_dp_id"] == TERMINAL_DP_ID
    assert body["replay_verification"] == {"attestation_version": "1",
                                           "verified_run_n": 144}
    for block in body["per_agent"].values():
        assert "tv_distances" not in block
        assert "permutation_null" not in block
        assert "verdict" not in block
        for label, cell in block["cells"].items():
            assert cell["admissible_effective_n"] == 0
            assert cell["non_decision_rate"] == 1.0
            expected = 24 if label in ("A|S1", "A|S2") else 48
            assert cell["non_decision_reasons"] == {
                "parse_fallback_winner": expected}


def test_frozen_path_refuses_a_tampered_pack_at_the_replay_gate(garbled_pack):
    """v4 (audit 001820 finding 0) on REAL runner evidence: an attestation over
    yesterday's bytes plus one tampered captures file refuses at the replay
    gate, before any census-derived statistic."""
    policy = load_admissibility_policy(REGISTRY, EID)
    thresholds = load_thresholds(REGISTRY, EID)
    att = _attest(garbled_pack)
    victim = os.path.join(garbled_pack[0], "captures.jsonl")
    original = open(victim, "rb").read()
    try:
        with open(victim, "ab") as fh:
            fh.write(b'{"key": "forged", "raw_text": "tampered"}\n')
        with pytest.raises(SchemaError) as excinfo:
            order_sensitivity_report(garbled_pack, CONDITIONS,
                                     admissibility_policy=policy,
                                     thresholds=thresholds,
                                     replay_attestation=att,
                                     terminal_dp_id=TERMINAL_DP_ID,
                                     surviving_counts=SURVIVING)
        assert "replay_attestation_stale" in str(excinfo.value)
    finally:
        with open(victim, "wb") as fh:
            fh.write(original)


def test_the_two_paths_disagree_and_that_disagreement_is_the_point(
        garbled_pack):
    """Pinned together deliberately: on identical evidence the Phase-1 comparator
    returns a publishable null while the frozen path refuses. A regression that
    silently re-aligned them would mean the guard had been removed."""
    policy = load_admissibility_policy(REGISTRY, EID)
    thresholds = load_thresholds(REGISTRY, EID)

    old = scramble_terminal_distribution(garbled_pack, CONDITIONS)
    assert old["per_agent"]["llm:mock:garbled_m8_seeded"]["tv_distances"]["A|B"] == 0.0

    with pytest.raises(SchemaError):
        order_sensitivity_report(garbled_pack, CONDITIONS,
                                 admissibility_policy=policy,
                                 thresholds=thresholds,
                                 replay_attestation=_attest(garbled_pack),
                                 terminal_dp_id=TERMINAL_DP_ID,
                                 surviving_counts=SURVIVING)
