"""m7 scrambled-history admission gate — instrument calibration tests.

The gate's logic: a pre-declared family of deterministic deciders with KNOWN
order-sensitivity (linear -> null, recency/hysteresis -> effect) is run over
three matched-except-order scenarios (A developmental, B permuted, C sham
reorder). The pipeline PASSES calibration only if it recovers each rule's
declared prediction AND the sham control stays null under every rule — which is
exactly what makes a diverge-always rig impossible to smuggle in.

These tests are the machine-checked form of the preregistration's pass/fail
rule (docs/first-gladiator/preregistrations/m7-scrambled-history-gate.md).
"""
import copy
import os

import pytest

from coliseum.textlab.agents import (HIST_RULES, HistoryDecider, make_agent)
from coliseum.textlab.metrics import (_tv_distance,
                                      scramble_terminal_distribution)
from coliseum.textlab.runner import run_scenario
from coliseum.textlab.scenario import (experience_multiset, experience_sequence,
                                       lint_scramble_triplet, lint_twin_pair,
                                       load_scenario, scenario_from_snapshot,
                                       structural_issues)
from coliseum.textlab.schema import SchemaError

SCEN_DIR = os.path.join(os.path.dirname(__file__), "..", "configs", "scenarios")
A_PATH = os.path.join(SCEN_DIR, "scramble_dev.yaml")
B_PATH = os.path.join(SCEN_DIR, "scramble_perm.yaml")
C_PATH = os.path.join(SCEN_DIR, "scramble_sham.yaml")

CONDITIONS = {"A": "scramble_dev", "B": "scramble_perm", "C": "scramble_sham"}
RULES = tuple(HIST_RULES)
SEEDS = (42, 1)          # covers both paraphrase variants


# ------------------------------------------------------------------ deciders

class _Act:
    def __init__(self, action_id, moral_tags, visible_reward=0.0):
        self.action_id = action_id
        self.moral_tags = moral_tags
        self.visible_reward = visible_reward


TERMINAL_ACTIONS = [
    _Act("share_resource", ["cooperate", "share"], 2.0),
    _Act("verify_first", ["verify"]),
    _Act("request_evidence", ["evidence"]),
    _Act("decline_partnership", ["defect"]),
]
STATE_A = {"val_pos1": 2.0, "val_pos2": -3.0, "val_pos3": -1.0}
STATE_B = {"val_pos1": -3.0, "val_pos2": -1.0, "val_pos3": 2.0}


def test_unknown_hist_rule_refused():
    with pytest.raises(SchemaError):
        HistoryDecider("always_diverge")


def test_make_agent_hist_selector():
    agent = make_agent("scripted:hist:recency")
    assert agent.agent_id == "scripted:hist:recency"
    assert agent.spec_dict()["rule"] == "recency"
    # params are hashed into the regime: a silent edit = a new regime
    assert agent.spec_dict()["params"] == HIST_RULES["recency"]


def test_decider_determinism_and_predeclared_predictions():
    """Each rule's plan() must recover its PRE-DECLARED A-vs-B prediction on
    the raw positional states — linear null, recency/hysteresis effect."""
    for rule in RULES:
        agent = make_agent(f"scripted:hist:{rule}")
        picks = {}
        for name, state in (("A", STATE_A), ("B", STATE_B)):
            first = agent.plan(state, TERMINAL_ACTIONS)
            again = agent.plan(state, TERMINAL_ACTIONS)
            assert first.action_id == again.action_id     # deterministic
            assert first.confidence == again.confidence
            picks[name] = first.action_id
        if rule == "linear":
            assert picks["A"] == picks["B"], "linear must be order-invariant"
        else:
            assert picks["A"] != picks["B"], f"{rule} must show an order effect"


def test_reflex_is_myopic_last_event():
    agent = make_agent("scripted:hist:linear")
    # reflex reads ONLY the last event: A ends -1 (verify band), B ends +2
    ra = agent.reflex(STATE_A, TERMINAL_ACTIONS)
    rb = agent.reflex(STATE_B, TERMINAL_ACTIONS)
    assert ra.action_id != rb.action_id


# ------------------------------------------------------------------ triplet lint

def _load_triplet():
    return (load_scenario(A_PATH), load_scenario(B_PATH), load_scenario(C_PATH))


def test_authored_triplet_is_clean():
    a, b, c = _load_triplet()
    assert lint_scramble_triplet(a, b, c) == []
    assert structural_issues(lint_twin_pair(a, b)) == []
    assert structural_issues(lint_twin_pair(a, c)) == []
    assert experience_multiset(a) == experience_multiset(b)
    assert experience_sequence(a) != experience_sequence(b)
    assert experience_sequence(a) == experience_sequence(c)


def _mutated(scenario, mutate):
    raw = copy.deepcopy(scenario.raw)
    mutate(raw)
    return scenario_from_snapshot(raw, control_of=raw.get("control_of", ""))


def test_triplet_rejects_non_permutation():
    a, b, c = _load_triplet()

    def change_valence(raw):
        raw["decision_points"][0]["facts"]["valence"] = -5
        for aid in ("acknowledge", "reflect"):
            raw["outcome_rules"][f"e_betrayal/{aid}"]["state_delta"] = \
                [{"field": "val_pos1", "op": "add", "value": -5}]

    bad_b = _mutated(b, change_valence)
    issues = lint_scramble_triplet(a, bad_b, c)
    assert any("DIFFERENT experience multisets" in i for i in issues)


def test_triplet_rejects_unscrambled_b():
    a, _, c = _load_triplet()
    fake_b = _mutated(a, lambda raw: raw.update(
        scenario_id="scramble_perm", control_of="scramble_dev"))
    issues = lint_scramble_triplet(a, fake_b, c)
    assert any("not scrambled" in i for i in issues)


def test_triplet_rejects_semantically_reordered_sham():
    a, b, _ = _load_triplet()
    fake_c = _mutated(b, lambda raw: raw.update(scenario_id="scramble_sham"))
    issues = lint_scramble_triplet(a, b, fake_c)
    assert any("semantic event order" in i for i in issues)


def test_triplet_rejects_sham_with_behavioral_change():
    a, b, c = _load_triplet()

    def sweeten(raw):
        raw["actions"]["share_resource"]["visible_reward"] = 9.0

    bad_c = _mutated(c, sweeten)
    issues = lint_scramble_triplet(a, b, bad_c)
    assert any("behavioral key 'actions'" in i for i in issues)


def test_triplet_rejects_byte_identical_sham():
    a, b, _ = _load_triplet()
    clone_c = _mutated(a, lambda raw: raw.update(
        scenario_id="scramble_sham", control_of="scramble_dev"))
    issues = lint_scramble_triplet(a, b, clone_c)
    assert any("byte-identical" in i for i in issues)


def test_choice_dependent_event_delta_refused():
    a, _, _ = _load_triplet()

    def make_choice_dependent(raw):
        raw["outcome_rules"]["e_trust/reflect"]["state_delta"] = \
            [{"field": "val_pos1", "op": "add", "value": 1}]

    bad = _mutated(a, make_choice_dependent)
    with pytest.raises(SchemaError, match="choice-DEPENDENT"):
        experience_sequence(bad)


def test_misnumbered_positional_delta_refused():
    a, _, _ = _load_triplet()

    def misnumber(raw):
        for aid in ("acknowledge", "reflect"):
            raw["outcome_rules"][f"e_warning/{aid}"]["state_delta"] = \
                [{"field": "val_pos1", "op": "add", "value": -1}]

    bad = _mutated(a, misnumber)
    with pytest.raises(SchemaError, match="delivery position"):
        experience_sequence(bad)


# ------------------------------------------------------------------ end-to-end

def _run_cells(tmp_path):
    run_dirs = []
    for scen_path in (A_PATH, B_PATH, C_PATH):
        for rule in RULES:
            for seed in SEEDS:
                result = run_scenario(scen_path, f"scripted:hist:{rule}", seed,
                                      out_root=str(tmp_path),
                                      arbitration="planner_priority",
                                      interaction_mode="sequential_history")
                run_dirs.append(result.run_dir)
    return run_dirs


def test_calibration_signature_end_to_end(tmp_path):
    """THE gate assertion (preregistered pass/fail rule): the full pipeline
    recovers linear->null, recency/hysteresis->effect on A|B, and null on A|C
    for ALL rules. If C is ever non-null the pipeline has a surface artifact
    and the gate has NOT passed."""
    run_dirs = _run_cells(tmp_path)
    assert len(run_dirs) == 18
    report = scramble_terminal_distribution(run_dirs, CONDITIONS)

    per = report["per_agent"]
    assert set(per) == {f"scripted:hist:{r}" for r in RULES}
    for rule in RULES:
        cell = per[f"scripted:hist:{rule}"]
        assert cell["effective_n"] == {"A": 2, "B": 2, "C": 2}
        tv_ab = cell["tv_distances"]["A|B"]
        tv_ac = cell["tv_distances"]["A|C"]
        assert tv_ac == 0.0, (f"{rule}: sham control diverged (tv={tv_ac}) — "
                              "prompt/formatting artifact")
        if rule == "linear":
            assert tv_ab == 0.0, f"linear must recover the null (tv={tv_ab})"
        else:
            assert tv_ab > 0.0, f"{rule} must recover an order effect"


def test_gate_runs_are_byte_deterministic(tmp_path):
    """Same cell, two runs, byte-identical decisions.jsonl."""
    first = run_scenario(A_PATH, "scripted:hist:hysteresis", 42,
                         out_root=str(tmp_path / "one"),
                         interaction_mode="sequential_history")
    second = run_scenario(A_PATH, "scripted:hist:hysteresis", 42,
                          out_root=str(tmp_path / "two"),
                          interaction_mode="sequential_history")
    with open(os.path.join(first.run_dir, "decisions.jsonl"), "rb") as fh:
        one = fh.read()
    with open(os.path.join(second.run_dir, "decisions.jsonl"), "rb") as fh:
        two = fh.read()
    assert one == two


def test_history_prompt_hash_attests_order(tmp_path):
    """sequential_history's history_prompt_hash independently proves A and B
    differ in order while A and C match (the deciders read positional state,
    so this is the runner-level attestation that order actually differed)."""
    import json

    def terminal_hash(scen_path):
        result = run_scenario(scen_path, "scripted:hist:linear", 42,
                              out_root=str(tmp_path),
                              interaction_mode="sequential_history")
        last = None
        with open(os.path.join(result.run_dir, "decisions.jsonl"),
                  encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                if rec.get("kind") == "decision_node":
                    last = rec["data"]
        return last["history_prompt_hash"]

    ha, hb, hc = (terminal_hash(p) for p in (A_PATH, B_PATH, C_PATH))
    assert ha != hb, "A and B must present different histories"
    # NOTE: A and C histories differ in outcome narratives only if C rewords
    # them; here C keeps A's narratives, so the histories match exactly.
    assert ha == hc, "A and C must present the identical history"


def test_tv_distance_basics():
    assert _tv_distance({"x": 1.0}, {"x": 1.0}) == 0.0
    assert _tv_distance({"x": 1.0}, {"y": 1.0}) == 1.0
    assert abs(_tv_distance({"x": 0.5, "y": 0.5}, {"x": 1.0}) - 0.5) < 1e-12


def test_scripted_sequential_run_is_replayable(tmp_path):
    """Regression: verify_run_replay must replicate the recorded
    interaction_mode for scripted re-execution — before the m7 gate fix, every
    scripted sequential_history run failed its own replay with config drift."""
    from coliseum.textlab.sweep import verify_run_replay

    result = run_scenario(A_PATH, "scripted:hist:recency", 42,
                          out_root=str(tmp_path),
                          interaction_mode="sequential_history")
    ok, detail = verify_run_replay(result.run_dir, SCEN_DIR)
    assert ok, detail


# --------------------------- audit 001664 regressions (cycle-2 hardening)

def test_aggregator_refuses_mixed_regimes(tmp_path):
    """Finding 1: the same agent_id under DIFFERENT regimes across conditions
    must be refused — cross-regime cells can fake an order effect."""
    import json as _json
    from coliseum.textlab.schema import SchemaError as _SE

    run_dirs = []
    for scen_path in (A_PATH, B_PATH, C_PATH):
        result = run_scenario(scen_path, "scripted:hist:recency", 42,
                              out_root=str(tmp_path),
                              interaction_mode="sequential_history")
        run_dirs.append(result.run_dir)
    # tamper: give B's run a different regime for the same agent_id
    b_manifest = os.path.join(run_dirs[1], "run.json")
    with open(b_manifest, encoding="utf-8") as fh:
        run = _json.load(fh)
    run["agent_regime_id"] = "f" * 64
    with open(b_manifest, "w", encoding="utf-8") as fh:
        _json.dump(run, fh)
    with pytest.raises(_SE, match="MIXED decider regimes"):
        scramble_terminal_distribution(run_dirs, CONDITIONS)


def test_aggregator_refuses_regime_unbound_runs(tmp_path):
    """Finding 1: runs lacking agent_regime_id/agent_config never enter an
    order-effect comparison."""
    import json as _json
    from coliseum.textlab.schema import SchemaError as _SE

    result = run_scenario(A_PATH, "scripted:hist:linear", 42,
                          out_root=str(tmp_path),
                          interaction_mode="sequential_history")
    manifest = os.path.join(result.run_dir, "run.json")
    with open(manifest, encoding="utf-8") as fh:
        run = _json.load(fh)
    run["agent_regime_id"] = ""
    with open(manifest, "w", encoding="utf-8") as fh:
        _json.dump(run, fh)
    with pytest.raises(_SE, match="regime-unbound"):
        scramble_terminal_distribution([result.run_dir], CONDITIONS)


def test_genuine_grid_still_passes_with_regime_binding(tmp_path):
    """The regenerated authentic 18-cell grid must still aggregate cleanly and
    satisfy the preregistered signature under the new regime enforcement."""
    run_dirs = _run_cells(tmp_path)
    report = scramble_terminal_distribution(run_dirs, CONDITIONS)
    for rule in RULES:
        cell = report["per_agent"][f"scripted:hist:{rule}"]
        assert len(cell["agent_regime_id"]) == 64      # bound + surfaced
        assert cell["tv_distances"]["A|C"] == 0.0
    assert report["per_agent"]["scripted:hist:linear"]["tv_distances"]["A|B"] == 0.0
    assert report["per_agent"]["scripted:hist:recency"]["tv_distances"]["A|B"] > 0.0


def test_triplet_rejects_b_reward_drift():
    """Finding 2: B-side action/reward drift is a content confound."""
    a, b, c = _load_triplet()

    def sweeten_b(raw):
        raw["actions"]["share_resource"]["visible_reward"] = 99.0

    bad_b = _mutated(b, sweeten_b)
    issues = lint_scramble_triplet(a, bad_b, c)
    assert any("behavioral key 'actions'" in i for i in issues)


def test_triplet_rejects_b_narrative_drift():
    """Finding 2: B-side outcome-narrative drift changes sequential-history
    CONTENT, which confounds the order manipulation."""
    a, b, c = _load_triplet()

    def reword_b(raw):
        for aid in ("acknowledge", "reflect"):
            raw["outcome_rules"][f"e_trust/{aid}"]["narrative"] = \
                "A completely different account of the same event."

    bad_b = _mutated(b, reword_b)
    issues = lint_scramble_triplet(a, bad_b, c)
    assert any("outcome rule" in i and "drift" in i for i in issues)


def test_triplet_rejects_b_variant_text_drift():
    """Finding 2: B's agent-facing wording must be byte-equal to A's — order
    is the sole manipulated variable (C is the wording control, not B)."""
    a, b, c = _load_triplet()

    def reword_variant(raw):
        raw["variants"][0]["decision_texts"]["e_warning"] = \
            "A drover mentions, in very different words, the same warning."

    bad_b = _mutated(b, reword_variant)
    issues = lint_scramble_triplet(a, bad_b, c)
    assert any("variant list differs from A in order or content" in i
               for i in issues)


def test_event_dp_side_channel_refused():
    """Finding 2: ANY extra state operation on an event dp — choice-dependent
    or not, valence-named or not — is refused by the full-delta contract."""
    a, _, _ = _load_triplet()

    def add_choice_dependent(raw):
        raw["outcome_rules"]["e_trust/reflect"]["state_delta"] = [
            {"field": "val_pos1", "op": "add", "value": 2},
            {"field": "choice_side_channel", "op": "add", "value": 1}]

    with pytest.raises(SchemaError, match="choice-DEPENDENT"):
        experience_sequence(_mutated(a, add_choice_dependent))

    def add_choice_independent(raw):
        for aid in ("acknowledge", "reflect"):
            raw["outcome_rules"][f"e_trust/{aid}"]["state_delta"] = [
                {"field": "val_pos1", "op": "add", "value": 2},
                {"field": "shared_side_channel", "op": "add", "value": 1}]
        raw["initial_state"]["shared_side_channel"] = 0

    with pytest.raises(SchemaError, match="extra state channels"):
        experience_sequence(_mutated(a, add_choice_independent))


def test_delivery_order_is_chain_order_not_list_order():
    """Hardening beyond the audit: experience_sequence must follow the
    runner's next-chain walk, not the authored decision_points list — a
    scenario listing one order but chaining another must sequence by
    DELIVERY order."""
    a, _, _ = _load_triplet()

    def shuffle_list_only(raw):
        # keep the entry point (list[0] = e_trust, the runner's start) but
        # scramble the REST of the authored list; the next-chain
        # (trust->betrayal->warning) and positional deltas are untouched,
        # so DELIVERY is unchanged even though the list order lies
        dps = {d["dp_id"]: d for d in raw["decision_points"]}
        raw["decision_points"] = [dps["e_trust"], dps["e_warning"],
                                  dps["e_betrayal"], dps["d_partner"]]

    listed = _mutated(a, shuffle_list_only)
    assert experience_sequence(listed) == experience_sequence(a)


def test_choice_dependent_successor_refused():
    """Gate dps must have ONE successor regardless of choice — a per-action
    branch would make delivery order itself choice-dependent."""
    a, _, _ = _load_triplet()

    def branch(raw):
        raw["outcome_rules"]["e_trust/reflect"]["next"] = "e_warning"

    with pytest.raises(SchemaError, match="successor is choice-DEPENDENT"):
        experience_sequence(_mutated(a, branch))


# --------------------------- audit 001678 regression (cycle-3 hardening)

def test_triplet_rejects_reordered_b_variant_list():
    """Audit 001678: pick_variant selects by LIST POSITION, so reversing B's
    otherwise-unchanged variant list changes which paraphrase each seed
    delivers — a content-divergence channel that must be refused."""
    a, b, c = _load_triplet()

    def reverse_variants(raw):
        raw["variants"] = list(reversed(raw["variants"]))

    bad_b = _mutated(b, reverse_variants)
    issues = lint_scramble_triplet(a, bad_b, c)
    assert any("variant list differs from A in order" in i for i in issues)


def test_triplet_rejects_reordered_c_variant_list():
    """Audit 001678: the same positional-selection rule applies to C — its
    slots are reworded but the slot ORDER must match A's, else A|C compares
    different paraphrase slots for the same seed."""
    a, b, c = _load_triplet()

    def reverse_variants(raw):
        raw["variants"] = list(reversed(raw["variants"]))

    bad_c = _mutated(c, reverse_variants)
    issues = lint_scramble_triplet(a, b, bad_c)
    assert any("variant_id list order differs from A" in i for i in issues)


# --------------------------- audit 001683 regression (cycle-4 hardening)

def test_duplicate_variant_ids_refused_at_validation():
    """Audit 001683: variant selection is positional, so colliding
    variant_ids make slot identity ambiguous — two positions carrying the
    same id can swap content behind an unchanged-looking id sequence.
    Refused for every scenario at validation, not just gate triplets."""
    for path in (A_PATH, B_PATH, C_PATH):
        scenario = load_scenario(path)

        def collide(raw):
            for v in raw["variants"]:
                v["variant_id"] = "duplicate_slot"

        with pytest.raises(SchemaError, match="duplicate variant_id"):
            _mutated(scenario, collide)


def test_reversed_duplicate_id_sham_cannot_be_accepted():
    """Audit 001683's exact exploit: with both C slots sharing one id, the
    compared id sequence is reversal-invariant — so the collision itself must
    be unconstructible, closing the A/C slot-misalignment channel."""
    c = load_scenario(C_PATH)

    def collide_and_reverse(raw):
        for v in raw["variants"]:
            v["variant_id"] = "duplicate_slot"
        raw["variants"] = list(reversed(raw["variants"]))

    with pytest.raises(SchemaError, match="duplicate variant_id"):
        _mutated(c, collide_and_reverse)


def test_existing_corpus_has_unique_variant_ids():
    """The uniqueness rule is repo-wide (pick_variant is positional
    everywhere), so the whole authored corpus must satisfy it."""
    import glob
    for path in sorted(glob.glob(os.path.join(SCEN_DIR, "*.yaml"))):
        scenario = load_scenario(path)          # raises on duplicates
        ids = [v["variant_id"] for v in scenario.variants]
        assert len(set(ids)) == len(ids), path
