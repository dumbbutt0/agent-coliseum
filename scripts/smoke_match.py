#!/usr/bin/env python3
"""Smoke test — runs TODAY with zero ML dependencies (stdlib only).

Proves the reproducibility substrate end to end: seed -> a season of duels -> structured logs ->
derived graph -> an Elo table + rivalry ledger. When you later swap the random bodies for trained RL
policies, NONE of this scaffolding changes.

    python scripts/smoke_match.py          # default seed 42
    SEED=7 python scripts/smoke_match.py   # any seed; same seed => identical result
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coliseum.seeding import seed_everything          # noqa: E402
from coliseum.logging_substrate import RunLogger       # noqa: E402
from coliseum.agents import Gladiator                  # noqa: E402
from coliseum.arena import round_robin                 # noqa: E402
from coliseum.ratings import Ladder                    # noqa: E402
from coliseum.derive_graph import build                # noqa: E402

SEED = int(os.environ.get("SEED", "42"))
SEASONS = 5


def main():
    seed_everything(SEED)
    roster = [
        Gladiator("g_brutus", "Brutus", seed=SEED + 1, style="aggressive"),
        Gladiator("g_vela",   "Vela",   seed=SEED + 2, style="defensive"),
        Gladiator("g_kai",    "Kai",    seed=SEED + 3, style="random"),
        Gladiator("g_ono",    "Ono",    seed=SEED + 4, style="aggressive"),
    ]
    names = {g.id: g.name for g in roster}
    ladder = Ladder()

    with RunLogger(run_id=f"smoke-seed{SEED}") as logger:
        for season in range(SEASONS):
            round_robin(roster, logger, ladder, base_seed=SEED + season * 100)

    social = build()

    print(f"\n=== Coliseum smoke test (seed={SEED}, {SEASONS} seasons) ===")
    print("Elo ladder:")
    for gid, r in ladder.table():
        print(f"  {names[gid]:8s} {r:7.1f}")

    print("\nTechnique tendencies (action frequencies):")
    cat = json.load(open("derived/technique-catalog.json"))
    for g in roster:
        print(f"  {g.name:8s} {cat.get(g.id, {})}")

    brutus = next(g for g in roster if g.id == "g_brutus")
    print("\nBrutus' rivalry ledger (the 'grudge' substrate):")
    for rid in [g.id for g in roster if g.id != brutus.id]:
        print(f"  vs {names[rid]:8s} {brutus.record_vs(rid)}")

    print(f"\nsource of truth : logs/smoke-seed{SEED}.jsonl")
    print(f"derived views   : derived/social-graph.json, derived/technique-catalog.json")
    print("everything above is regenerable from the log, which is regenerable from the seed.\n")


if __name__ == "__main__":
    main()
