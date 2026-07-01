"""DERIVE views from the source-of-truth logs (never the other way round).

Produces (all regenerable from logs/, which are regenerable from the seed):
  derived/social-graph.json      — gladiators as nodes; edges = matchups (win/loss/draw counts).
                                    This IS the graph that grows rivalries/alliances as the game deepens.
  derived/technique-catalog.json — per-gladiator action frequencies (its 'tendencies').

The node/edge shape mirrors the wiki's graph JSON, so the same kind of 'Eye' view can render it.
"""
from __future__ import annotations
import glob
import json
import os
from collections import Counter, defaultdict

from .logging_substrate import read_events


def build(log_dir: str = "logs", out_dir: str = "derived") -> dict:
    os.makedirs(out_dir, exist_ok=True)
    matchups: dict = defaultdict(Counter)   # (a,b) sorted -> Counter of outcomes
    techniques: dict = defaultdict(Counter)  # gid -> action counts
    fighters: set = set()

    for path in sorted(glob.glob(os.path.join(log_dir, "*.jsonl"))):
        for ev in read_events(path):
            d, kind = ev["data"], ev["kind"]
            if kind == "step":
                techniques[d["a"]][d["a_action"]] += 1
                techniques[d["b"]][d["b_action"]] += 1
            elif kind == "match_end":
                a, b, w = d["a"], d["b"], d["winner"]
                fighters.update([a, b])
                key = tuple(sorted([a, b]))
                if w is None:
                    matchups[key]["draws"] += 1
                else:
                    matchups[key][f"{w}_wins"] += 1

    nodes = [{"id": g, "type": "gladiator", "techniques": dict(techniques.get(g, {}))}
             for g in sorted(fighters)]
    edges = [{"source": a, "target": b, "matches": sum(c.values()), "detail": dict(c)}
             for (a, b), c in sorted(matchups.items())]
    social = {"nodes": nodes, "edges": edges}

    with open(os.path.join(out_dir, "social-graph.json"), "w", encoding="utf-8") as fh:
        json.dump(social, fh, indent=2)
    with open(os.path.join(out_dir, "technique-catalog.json"), "w", encoding="utf-8") as fh:
        json.dump({g: dict(t) for g, t in sorted(techniques.items())}, fh, indent=2)
    return social
