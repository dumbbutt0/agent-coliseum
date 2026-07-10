"""textlab CLI — thin over runner/metrics/graph_export.

    python3 -m coliseum.textlab.cli run     --scenario corrupt_king --agent scripted:obedient --seed 42
    python3 -m coliseum.textlab.cli replay  <run_id>          # the determinism gate as a command
    python3 -m coliseum.textlab.cli metrics <run_id> [...]    # per-run reports + aggregate
    python3 -m coliseum.textlab.cli graph   <run_id> [...]    # decision graphs (JSON + DOT)
    python3 -m coliseum.textlab.cli compare                   # aggregate cells side by side
"""
from __future__ import annotations

import argparse
import filecmp
import json
import os
import sys
import tempfile

from .graph_export import write_graphs
from .metrics import aggregate, write_aggregate, write_run_metrics
from .runner import run_scenario


def _run_dir(run_id: str, out_root: str) -> str:
    d = os.path.join(out_root, run_id)
    if not os.path.isdir(d):
        sys.exit(f"no such run: {d}")
    return d


def _all_run_dirs(out_root: str) -> list:
    if not os.path.isdir(out_root):
        return []
    return [os.path.join(out_root, d) for d in sorted(os.listdir(out_root))
            if os.path.isfile(os.path.join(out_root, d, "run.json"))]


def cmd_run(args):
    path = os.path.join(args.config_dir, f"{args.scenario}.yaml")
    sampling = None
    if args.temperature and args.temperature > 0:
        sampling = {"mode": "stochastic", "temperature": args.temperature}
    result = run_scenario(path, args.agent, args.seed, out_root=args.out_root,
                          arbitration=args.arbitration,
                          sampling=sampling, sampler_seed=args.sampler_seed)
    print(f"run_id : {result.run_id}")
    print(f"path   : {' -> '.join(result.final_actions)}")
    print(f"log    : {os.path.join(result.run_dir, 'decisions.jsonl')}")
    if sampling:
        print(f"stochastic_reportable: {result.run.stochastic_reportable} "
              f"{result.run.stochastic_exclusion_reasons or ''}")


def cmd_replay(args):
    """Re-run from run.json config into a temp dir and byte-compare — the gate.
    Scripted runs re-execute live; LLM runs replay from their captured raw outputs
    (the two determinism tiers — live-API determinism is never claimed)."""
    run_dir = _run_dir(args.run_id, args.out_root)
    run = json.load(open(os.path.join(run_dir, "run.json"), encoding="utf-8"))
    path = os.path.join(args.config_dir, f"{run['scenario_id']}.yaml")
    is_llm = run["agent_id"].startswith("llm:")
    replay_from = run_dir if is_llm else None
    with tempfile.TemporaryDirectory() as tmp:
        result = run_scenario(path, run["agent_id"], run["seed"], out_root=tmp,
                              arbitration=run.get("arbitration", "planner_priority"),
                              replay_from=replay_from)
        if result.run_id != run["run_id"]:
            sys.exit(f"CONFIG DRIFT: replay produced run_id {result.run_id} != {run['run_id']}\n"
                     f"(the scenario file or agent code changed since this run was recorded)")
        same = filecmp.cmp(os.path.join(run_dir, "decisions.jsonl"),
                           os.path.join(result.run_dir, "decisions.jsonl"), shallow=False)
        if not same:
            sys.exit("MISMATCH: decisions.jsonl differs between original and replay")
    tier = "replayed from captured outputs" if is_llm else "re-executed live"
    print(f"byte-identical: {run['run_id']} (decisions.jsonl, {tier})")


def cmd_metrics(args):
    dirs = ([_run_dir(r, args.out_root) for r in args.run_ids]
            if args.run_ids else _all_run_dirs(args.out_root))
    if not dirs:
        sys.exit("no runs found")
    for d in dirs:
        print("wrote", write_run_metrics(d, args.derived_root))
    print("wrote", write_aggregate(dirs, args.derived_root, mode=args.mode,
                                   include_non_reportable=args.diagnostics))


def cmd_graph(args):
    dirs = ([_run_dir(r, args.out_root) for r in args.run_ids]
            if args.run_ids else _all_run_dirs(args.out_root))
    if not dirs:
        sys.exit("no runs found")
    for p in write_graphs(dirs, args.graphs_root):
        print("wrote", p)


def cmd_compare(args):
    dirs = _all_run_dirs(args.out_root)
    if not dirs:
        sys.exit("no runs found")
    agg = aggregate(dirs, mode=args.mode, include_non_reportable=args.diagnostics)
    print(f"mode: {args.mode}")
    if args.diagnostics:
        print("!! DIAGNOSTICS MODE: non-admitted runs INCLUDED — not for claims !!\n")
    elif agg["excluded"]:
        reasons = {}
        for e in agg["excluded"]:
            for why in e["reasons"]:
                reasons[why] = reasons.get(why, 0) + 1
        print(f"(excluded {len(agg['excluded'])} runs: {reasons}; --diagnostics to include)\n")
    metric_names = sorted({m for c in agg["cells"].values() for m in c["metrics"]})
    header = ["cell (…|sampling|regime-prefix)", "eff_n/att"] + \
             [m.replace("_rate", "").replace("_", " ") for m in metric_names]
    rows = [header]
    for key, cell in agg["cells"].items():
        label = key + (" [reward-control]" if cell["persona_role"] == "reward_seeking_control" else "")
        c = cell["counts"]
        row = [label, f"{c['effective_n']}/{c['raw_attempt_n']}"]
        for m in metric_names:
            v = cell["metrics"].get(m, {}).get("value")
            row.append("-" if v is None else f"{v:.2f}")
        rows.append(row)
    widths = [max(len(r[i]) for r in rows) for i in range(len(header))]
    for r in rows:
        print("  ".join(s.ljust(w) for s, w in zip(r, widths)))
    if args.mode == "full-grid":
        print("\ngrid (variant × sampler_seed -> evidence):")
        for key, cell in agg["cells"].items():
            for gkey, ids in cell.get("grid", {}).items():
                print(f"  {cell['scenario_id']}|{cell['agent_id']} {gkey}: {len(ids)} attempt(s)")
    if agg["faith_knob_sensitivity"]:
        print("\nfaith_knob_sensitivity (paired, d2-only; + = blind faith):")
        for agent, v in agg["faith_knob_sensitivity"].items():
            print(f"  {agent}: {v['value']:+.2f} (matched_pairs={v['matched_pairs']})")
    if agg["control_twin_delta"]:
        print("\ncontrol_twin_delta (paired, primary - control):")
        for pair, d in agg["control_twin_delta"].items():
            interesting = {k: v for k, v in d["deltas"].items() if v}
            un = (f", unmatched sampler seeds p:{d['unmatched_primary_sampler_seeds']}"
                  f"/c:{d['unmatched_control_sampler_seeds']}"
                  if d["unmatched_primary_sampler_seeds"] or d["unmatched_control_sampler_seeds"] else "")
            print(f"  {pair}: {interesting or 'no differences'} "
                  f"(pairs={d['matched_pairs']}{un})")


def main(argv=None):
    p = argparse.ArgumentParser(prog="coliseum-lab", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out-root", default="logs/runs")
    p.add_argument("--config-dir", default="configs/scenarios")
    p.add_argument("--derived-root", default="derived/textlab/metrics")
    p.add_argument("--graphs-root", default="derived/textlab/graphs")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("run");     s.set_defaults(fn=cmd_run)
    s.add_argument("--scenario", required=True); s.add_argument("--agent", default="scripted:obedient")
    s.add_argument("--seed", type=int, default=42,
                   help="SCENARIO seed (variant selection)")
    s.add_argument("--sampler-seed", type=int, default=None,
                   help="backend sampling seed (required when --temperature > 0)")
    s.add_argument("--temperature", type=float, default=0.0)
    s.add_argument("--arbitration", default="planner_priority")
    s = sub.add_parser("replay");  s.set_defaults(fn=cmd_replay);  s.add_argument("run_id")
    s = sub.add_parser("metrics"); s.set_defaults(fn=cmd_metrics); s.add_argument("run_ids", nargs="*")
    s.add_argument("--mode", default="deterministic",
                   choices=["deterministic", "stochastic", "variants", "full-grid"])
    s.add_argument("--diagnostics", action="store_true",
                   help="include non-admitted runs in the aggregate (labeled; not for claims)")
    s = sub.add_parser("graph");   s.set_defaults(fn=cmd_graph);   s.add_argument("run_ids", nargs="*")
    s = sub.add_parser("compare"); s.set_defaults(fn=cmd_compare)
    s.add_argument("--mode", default="deterministic",
                   choices=["deterministic", "stochastic", "variants", "full-grid"])
    s.add_argument("--diagnostics", action="store_true",
                   help="include non-admitted runs (labeled; not for claims)")

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
