"""Scenario loading: the shipped YAMLs validate; broken definitions are rejected."""
import copy
import os

import pytest
import yaml

from coliseum.textlab.scenario import load_scenario
from coliseum.textlab.schema import SchemaError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCEN_DIR = os.path.join(ROOT, "configs", "scenarios")
SHIPPED = ["corrupt_king", "corrupt_king_harmless", "corrupt_king_verifiable"]


@pytest.mark.parametrize("name", SHIPPED)
def test_shipped_scenarios_validate(name):
    s = load_scenario(os.path.join(SCEN_DIR, f"{name}.yaml"))
    assert s.scenario_id == name
    assert len(s.variants) >= 2
    assert s.archetype == "corrupt_king"


def test_controls_declare_their_primary():
    for name in SHIPPED[1:]:
        s = load_scenario(os.path.join(SCEN_DIR, f"{name}.yaml"))
        assert s.control_of == "corrupt_king"


def _write(tmp_path, raw):
    p = tmp_path / "broken.yaml"
    p.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return str(p)


@pytest.fixture
def base_raw():
    with open(os.path.join(SCEN_DIR, "corrupt_king.yaml"), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_unknown_action_rejected(tmp_path, base_raw):
    raw = copy.deepcopy(base_raw)
    raw["decision_points"][0]["available_actions"].append("bribe")
    with pytest.raises(SchemaError, match="unknown action 'bribe'"):
        load_scenario(_write(tmp_path, raw))


def test_single_variant_rejected(tmp_path, base_raw):
    raw = copy.deepcopy(base_raw)
    raw["variants"] = raw["variants"][:1]
    with pytest.raises(SchemaError, match="paraphrase variants"):
        load_scenario(_write(tmp_path, raw))


def test_contamination_word_rejected(tmp_path, base_raw):
    raw = copy.deepcopy(base_raw)
    raw["variants"][0]["intro"] = "This is a test of your obedience."
    with pytest.raises(SchemaError, match="contamination"):
        load_scenario(_write(tmp_path, raw))


def test_missing_outcome_rule_rejected(tmp_path, base_raw):
    raw = copy.deepcopy(base_raw)
    del raw["outcome_rules"]["d1_ledger/stall"]
    with pytest.raises(SchemaError, match="no outcome rule"):
        load_scenario(_write(tmp_path, raw))


def test_dangling_next_rejected(tmp_path, base_raw):
    raw = copy.deepcopy(base_raw)
    raw["outcome_rules"]["d1_ledger/execute"]["next"] = "d9_nowhere"
    with pytest.raises(SchemaError, match="unknown dp"):
        load_scenario(_write(tmp_path, raw))
