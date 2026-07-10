"""Graph export: run path shape, divergence marking, merged weights."""
import os

from coliseum.textlab.graph_export import merged_graph, run_graph, to_dot
from coliseum.textlab.runner import run_scenario

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CK = os.path.join(ROOT, "configs", "scenarios", "corrupt_king.yaml")


def test_run_graph_shape(tmp_path):
    r = run_scenario(CK, "scripted:obedient", 42, str(tmp_path))
    g = run_graph(r.run_dir)
    assert [n["dp_id"] for n in g["nodes"]] == ["d1_ledger", "d2_requisition", "d3_expulsion"]
    assert [n["diverged"] for n in g["nodes"]] == [False, True, False]   # the d2 flinch is visible
    assert g["edges"][-1]["to"] == "end"
    assert len(g["edges"]) == 3
    dot = to_dot(g)
    assert dot.startswith("digraph coliseum {") and '"end"' in dot


def test_merged_graph_weights(tmp_path):
    dirs = [run_scenario(CK, f"scripted:{p}", 42, str(tmp_path / p)).run_dir
            for p in ("obedient", "defiant", "merciful", "selfish")]
    g = merged_graph(dirs)
    w = {(e["from"], e["action"], e["to"]): e["weight"] for e in g["edges"]}
    assert w[("d1_ledger", "execute", "d2_requisition")] == 3     # all but defiant
    assert w[("d1_ledger", "refuse", "d2_requisition")] == 1
    assert w[("d2_requisition", "verify", "d3_expulsion")] == 2   # obedient + merciful
    assert w[("d3_expulsion", "refuse", "end")] == 2              # defiant + merciful
    assert sum(wt for (f, _, _), wt in w.items() if f == "d3_expulsion") == 4


def test_merged_graph_never_pools_interaction_modes(tmp_path):
    independent = run_scenario(CK, "scripted:obedient", 42, str(tmp_path / "ind"))
    sequential = run_scenario(CK, "scripted:obedient", 42, str(tmp_path / "seq"),
                              interaction_mode="sequential_history")
    g = merged_graph([independent.run_dir, sequential.run_dir])
    matching = [e for e in g["edges"]
                if (e["from"], e["action"], e["to"]) ==
                   ("d1_ledger", "execute", "d2_requisition")]
    assert {e["interaction_mode"] for e in matching} == {
        "independent_vignettes", "sequential_history"}
    assert [e["weight"] for e in matching] == [1, 1]
