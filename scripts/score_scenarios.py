#!/usr/bin/env python3
"""Score every shipped scenario: all scripted personas x seeds x scenarios ->
runs + per-run metrics + aggregate + the comparison table.

    python3 scripts/score_scenarios.py [--seeds 1 2 3 5 8]

Everything lands in logs/runs/ and derived/textlab/; all of it is regenerable
(delete derived/, rerun this, get identical bytes — that's the gate).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coliseum.textlab import cli  # noqa: E402
from coliseum.textlab.agents import ScriptedAgent  # noqa: E402
from coliseum.textlab.metrics import write_aggregate, write_run_metrics  # noqa: E402
from coliseum.textlab.graph_export import write_graphs  # noqa: E402
from coliseum.textlab.runner import run_scenario  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 5, 8])
    p.add_argument("--config-dir", default="configs/scenarios")
    p.add_argument("--out-root", default="logs/runs")
    args = p.parse_args()

    scenarios = sorted(f[:-5] for f in os.listdir(args.config_dir) if f.endswith(".yaml"))
    run_dirs = []
    for scen in scenarios:
        path = os.path.join(args.config_dir, f"{scen}.yaml")
        for persona in ScriptedAgent.PERSONAS:
            for seed in args.seeds:
                r = run_scenario(path, f"scripted:{persona}", seed, out_root=args.out_root)
                run_dirs.append(r.run_dir)
    run_dirs = sorted(set(run_dirs))
    print(f"{len(run_dirs)} unique runs across {len(scenarios)} scenarios "
          f"x {len(ScriptedAgent.PERSONAS)} personas x {len(args.seeds)} seeds\n")

    for d in run_dirs:
        write_run_metrics(d)
    write_aggregate(run_dirs)
    write_graphs(run_dirs)
    print("derived/textlab/ rebuilt (metrics + graphs)\n")
    cli.main(["--out-root", args.out_root, "--config-dir", args.config_dir, "compare"])


if __name__ == "__main__":
    main()
