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

The pack is generated here rather than read from `logs/runs/`, which is
gitignored — the regression must reproduce in a fresh checkout with no evidence
tree. `llm:mock:garbled` is a committed fixture that emits genuinely unparseable
output, so every terminal decision is a parse fallback. It contacts no provider.

The property under test is the one the whole slice exists for: because a fallback
resolves to the FIRST available action, and that action is identical in every
condition, wholly unreadable output does not converge to noise — it converges to
a *perfect null*. The Phase-1 comparator reports that null with confidence. The
frozen path must refuse it.
"""
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


@pytest.fixture(scope="module")
def garbled_pack(tmp_path_factory):
    """A real A/B/C pack whose every terminal decision is a parse fallback.

    Offline: the mock backend serves a committed fixture, so no provider is
    contacted and the pack is byte-reproducible.
    """
    out = tmp_path_factory.mktemp("m8_frozen_path")
    dirs = []
    for cond in ("A", "B", "C"):
        for sampler_seed in (2001, 2002, 2003, 2004):
            result = run_scenario(
                _PATH[cond], "llm:mock:garbled", 42,
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
    assert thresholds["min_detectable_effect"] == 0.25
    # the decision quantile must not be silently reusable as the reporting
    # interval, so the two live under separate frozen keys
    assert thresholds["alpha"] == 0.05
    assert thresholds["confidence"] == 0.95


def test_phase1_comparator_manufactures_a_confident_null_from_unreadable_output(
        garbled_pack):
    """The defect, on real runner output. This is not an indictment of Phase-1
    evidence — the comparator is correct for deterministic deciders that never
    parse. It is the reason it must not be the Phase-2 path."""
    old = scramble_terminal_distribution(garbled_pack, CONDITIONS)
    block = old["per_agent"]["llm:mock:garbled"]
    # every condition collapses onto the SAME first available action
    for cond in ("A", "B", "C"):
        assert block["distributions"][cond] == {"share_resource": 1.0}
    # ...so total garbage reads as a perfect null rather than as noise
    assert block["tv_distances"]["A|B"] == 0.0
    assert block["tv_distances"]["A|C"] == 0.0


def test_frozen_path_refuses_the_garbled_pack_and_emits_no_distances(
        garbled_pack):
    """The regression the auditor asked for: driven from the frozen design, the
    instrument refuses and NO distance escapes."""
    policy = load_admissibility_policy(REGISTRY, EID)
    thresholds = load_thresholds(REGISTRY, EID)

    with pytest.raises(SchemaError) as excinfo:
        order_sensitivity_report(garbled_pack, CONDITIONS,
                                 admissibility_policy=policy,
                                 thresholds=thresholds)

    message = str(excinfo.value)
    assert "non_decision_rate" in message or "admissible_effective_n" in message

    # the census is attached so an auditor can see WHY, but no number that would
    # be mistaken for a result may accompany it
    body = getattr(excinfo.value, "report", None)
    assert body is not None, "refusal must carry its census"
    for block in body["per_agent"].values():
        assert "tv_distances" not in block
        assert "permutation_null" not in block
        assert "verdict" not in block
        for cell in block["cells"].values():
            assert cell["admissible_effective_n"] == 0
            assert cell["non_decision_rate"] == 1.0
            assert cell["non_decision_reasons"] == {"parse_fallback_winner": 4}


def test_the_two_paths_disagree_and_that_disagreement_is_the_point(
        garbled_pack):
    """Pinned together deliberately: on identical evidence the Phase-1 comparator
    returns a publishable null while the frozen path refuses. A regression that
    silently re-aligned them would mean the guard had been removed."""
    policy = load_admissibility_policy(REGISTRY, EID)
    thresholds = load_thresholds(REGISTRY, EID)

    old = scramble_terminal_distribution(garbled_pack, CONDITIONS)
    assert old["per_agent"]["llm:mock:garbled"]["tv_distances"]["A|B"] == 0.0

    with pytest.raises(SchemaError):
        order_sensitivity_report(garbled_pack, CONDITIONS,
                                 admissibility_policy=policy,
                                 thresholds=thresholds)
