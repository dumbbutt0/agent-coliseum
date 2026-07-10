#!/usr/bin/env python3
"""Run one textlab scenario and print where the log landed.

    python3 scripts/run_scenario.py --scenario corrupt_king --agent scripted:obedient --seed 42

The run directory (logs/runs/<run_id>/) holds decisions.jsonl (append-only source of
truth) and run.json (the manifest). Re-running with the same arguments reproduces the
run byte-identically — that's the determinism gate, not an accident.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coliseum.textlab.runner import run_scenario  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scenario", required=True, help="scenario_id (file stem under --config-dir)")
    p.add_argument("--agent", default="scripted:obedient",
                   help="agent spec: scripted:<persona> | ollama:<model> | api:<model>")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--config-dir", default="configs/scenarios")
    p.add_argument("--out-root", default="logs/runs")
    args = p.parse_args()

    path = os.path.join(args.config_dir, f"{args.scenario}.yaml")
    if not os.path.exists(path):
        p.error(f"no such scenario file: {path}")

    result = run_scenario(path, args.agent, args.seed, out_root=args.out_root)
    print(f"run_id : {result.run_id}")
    print(f"log    : {os.path.join(result.run_dir, 'decisions.jsonl')}")
    print(f"variant: {result.run.variant_id}   seed: {result.run.seed}   agent: {result.run.agent_id}")
    print(f"path   : {' -> '.join(result.final_actions)}")


if __name__ == "__main__":
    main()
