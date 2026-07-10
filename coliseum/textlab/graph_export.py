"""Decision-graph export — a derived, regenerable view over the logs.

Two shapes:
  - per-run graph: the path one agent actually walked (nodes = decision nodes,
    edges = chosen action -> next decision).
  - merged scenario graph: all runs overlaid on the scenario's decision points,
    edge weight = how many runs took that transition. The "dot graph" made real.

Byte-stability: canonical JSON + deterministic ordering; DOT lines sorted. Same
logs in, identical bytes out.
"""
from __future__ import annotations

import json
import os

from .schema import canonical_json


def _read_nodes(run_dir: str):
    run = json.load(open(os.path.join(run_dir, "run.json"), encoding="utf-8"))
    nodes = []
    with open(os.path.join(run_dir, "decisions.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            ev = json.loads(line)
            if ev["kind"] == "decision_node":
                nodes.append(ev["data"])
    return run, nodes


def run_graph(run_dir: str) -> dict:
    """One run's walked path as a graph."""
    run, dnodes = _read_nodes(run_dir)
    nodes, edges = [], []
    for d in dnodes:
        nid = f"{run['run_id']}/t{d['timestep']}"
        nodes.append({"id": nid, "dp_id": d.get("dp_id", ""), "timestep": d["timestep"],
                      "final_action": d["final_action"], "moral_tags": d["moral_tags"],
                      "reflex_action": d["reflex_choice"]["action_id"],
                      "planner_action": d["planner_choice"]["action_id"],
                      "diverged": d["reflex_choice"]["action_id"] != d["planner_choice"]["action_id"],
                      "authority_pressure": d["authority_pressure"]})
    for a, b in zip(dnodes, dnodes[1:]):
        edges.append({"from": f"{run['run_id']}/t{a['timestep']}",
                      "to": f"{run['run_id']}/t{b['timestep']}",
                      "action": a["final_action"],
                      "narrative": a["outcome"]["narrative"]})
    if dnodes:
        last = dnodes[-1]
        edges.append({"from": f"{run['run_id']}/t{last['timestep']}", "to": "end",
                      "action": last["final_action"], "narrative": last["outcome"]["narrative"]})
    return {"graph": "run", "run_id": run["run_id"], "scenario_id": run["scenario_id"],
            "agent_id": run["agent_id"], "nodes": nodes, "edges": edges}


def merged_graph(run_dirs: list) -> dict:
    """All runs overlaid on decision points; edge weight = traversal count."""
    scenario_ids, agents = set(), set()
    weights: dict = {}
    for run_dir in sorted(run_dirs):
        run, dnodes = _read_nodes(run_dir)
        scenario_ids.add(run["scenario_id"])
        agents.add(run["agent_id"])
        for a, b in zip(dnodes, dnodes[1:]):
            key = (a.get("dp_id", f"t{a['timestep']}"), a["final_action"],
                   b.get("dp_id", f"t{b['timestep']}"))
            weights[key] = weights.get(key, 0) + 1
        if dnodes:
            last = dnodes[-1]
            key = (last.get("dp_id", f"t{last['timestep']}"), last["final_action"], "end")
            weights[key] = weights.get(key, 0) + 1
    dp_ids = sorted({k[0] for k in weights} | {k[2] for k in weights})
    edges = [{"from": f, "action": a, "to": t, "weight": w}
             for (f, a, t), w in sorted(weights.items())]
    return {"graph": "merged", "scenario_ids": sorted(scenario_ids),
            "agent_ids": sorted(agents), "nodes": dp_ids, "edges": edges}


def to_dot(graph: dict) -> str:
    """Graphviz DOT — deterministic line order."""
    lines = ["digraph coliseum {", '  rankdir=LR;', '  node [shape=box, fontsize=10];']
    if graph["graph"] == "run":
        for n in graph["nodes"]:
            style = ', style=filled, fillcolor="lightyellow"' if n["diverged"] else ""
            label = f"{n['dp_id']}\\nfinal: {n['final_action']}\\nreflex: {n['reflex_action']} / plan: {n['planner_action']}"
            lines.append(f'  "{n["id"]}" [label="{label}"{style}];')
        lines.append('  "end" [shape=doublecircle, label="end"];')
        for e in graph["edges"]:
            lines.append(f'  "{e["from"]}" -> "{e["to"]}" [label="{e["action"]}"];')
    else:
        for dp in graph["nodes"]:
            shape = "doublecircle" if dp == "end" else "box"
            lines.append(f'  "{dp}" [shape={shape}];')
        for e in graph["edges"]:
            lines.append(f'  "{e["from"]}" -> "{e["to"]}" [label="{e["action"]} x{e["weight"]}", penwidth={min(1 + e["weight"] * 0.5, 5)}];')
    lines.append("}")
    return "\n".join(lines) + "\n"


def write_graphs(run_dirs: list, derived_root: str = "derived/textlab/graphs",
                 merged_name: str = "merged") -> list:
    """Per-run graphs + one merged graph; JSON (canonical) + DOT. Returns paths."""
    os.makedirs(derived_root, exist_ok=True)
    paths = []
    for run_dir in sorted(run_dirs):
        g = run_graph(run_dir)
        base = os.path.join(derived_root, g["run_id"])
        for suffix, content in ((".graph.json", canonical_json(g) + "\n"), (".dot", to_dot(g))):
            with open(base + suffix, "w", encoding="utf-8") as fh:
                fh.write(content)
            paths.append(base + suffix)
    m = merged_graph(run_dirs)
    base = os.path.join(derived_root, merged_name)
    for suffix, content in ((".graph.json", canonical_json(m) + "\n"), (".dot", to_dot(m))):
        with open(base + suffix, "w", encoding="utf-8") as fh:
            fh.write(content)
        paths.append(base + suffix)
    return paths
