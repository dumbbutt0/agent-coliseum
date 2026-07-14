"""textlab CLI — thin over runner/metrics/graph_export.

    python3 -m coliseum.textlab.cli run     --scenario corrupt_king --agent scripted:obedient --seed 42
    python3 -m coliseum.textlab.cli replay  <run_id>          # the determinism gate as a command
    python3 -m coliseum.textlab.cli metrics <run_id> [...]    # per-run reports + aggregate
    python3 -m coliseum.textlab.cli graph   <run_id> [...]    # decision graphs (JSON + DOT)
    python3 -m coliseum.textlab.cli compare                   # aggregate cells side by side
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .graph_export import write_graphs
from .metrics import aggregate, write_aggregate, write_run_metrics
from .runner import run_scenario
from .schema import canonical_json


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
                          sampling=sampling, sampler_seed=args.sampler_seed,
                          interaction_mode=args.interaction)
    print(f"run_id : {result.run_id}")
    if args.interaction != "independent_vignettes":
        print(f"mode   : {args.interaction}")
    print(f"path   : {' -> '.join(result.final_actions)}")
    print(f"log    : {os.path.join(result.run_dir, 'decisions.jsonl')}")
    if sampling:
        print(f"stochastic_reportable: {result.run.stochastic_reportable} "
              f"{result.run.stochastic_exclusion_reasons or ''}")


def cmd_replay(args):
    """Re-run from run.json config into a temp dir and byte-compare — the gate.
    Scripted runs re-execute live; LLM runs replay from their captured raw outputs
    (the two determinism tiers — live-API determinism is never claimed). The
    verification itself lives in coliseum.textlab.sweep.verify_run_replay, shared
    with the audited ollama_local driver so both check identical bytes."""
    from coliseum.textlab.sweep import verify_run_replay
    run_dir = _run_dir(args.run_id, args.out_root)
    run = json.load(open(os.path.join(run_dir, "run.json"), encoding="utf-8"))
    ok, detail = verify_run_replay(run_dir, args.config_dir)
    if not ok:
        sys.exit(f"REPLAY FAILED: {run['run_id']}: {detail}")
    is_llm = run["agent_id"].startswith("llm:")
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
                                   include_non_reportable=args.diagnostics,
                                   interaction_mode=args.interaction))


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
    agg = aggregate(dirs, mode=args.mode, include_non_reportable=args.diagnostics,
                    interaction_mode=args.interaction)
    print(f"mode: {args.mode} | interaction: {args.interaction}")
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


def _load_held_out(registry_path):
    """Held-out (scenarios, scenario_hashes) from the experiments registry, or (None, None)."""
    if not registry_path or not os.path.exists(registry_path):
        return None, None
    from .registry import load_experiments_registry
    raw = load_experiments_registry(registry_path)
    ho = raw.get("held_out", {}) if isinstance(raw, dict) else {}
    return ho.get("scenarios") or None, ho.get("scenario_hashes") or None


def cmd_dataset_export(args):
    """T0-A: emit a provenance-complete, non-pooled dataset descriptor + card from validated evidence,
    with an optional deterministic, dataset-version-bound group-aware partition (§8).
    Structural only — no normative labels, no training."""
    from .dataset_export import build_dataset, dataset_from_manifest, dataset_card
    from . import reports
    held_ids, held_hashes = _load_held_out(args.registry)
    common = dict(mode=args.mode, interaction_mode=args.interaction,
                  held_out_scenarios=held_ids, held_out_hashes=held_hashes,
                  verify=args.verify, config_dir=args.config_dir,
                  partition=args.partition,
                  registry_path=args.scenario_registry if args.partition else None,
                  training_admission=args.training_admission,
                  require_replay_for_admission=args.admission_require_replay)
    if args.manifest:
        desc = dataset_from_manifest(args.manifest, args.out_root, **common)
    else:
        dirs = _all_run_dirs(args.out_root)
        if not dirs:
            sys.exit("no runs found")
        desc = build_dataset(dirs, **common)
    os.makedirs(args.derived_root, exist_ok=True)
    desc_path = os.path.join(args.derived_root, "dataset.t0a.json")
    with open(desc_path, "w", encoding="utf-8") as fh:
        fh.write(canonical_json(desc) + "\n")
    card_path = reports.write(dataset_card(desc), "dataset-card.t0a.md", args.repo_root)
    print("wrote", desc_path)
    print("wrote", card_path)
    print(f"effective_units {desc['effective_unit_count']} commitment {desc['dataset_commitment'][:16]}")


def cmd_spatial_run(args):
    """S2D: build + schedule + verify + observe a scripted spatial scenario; the
    run dir is experiment evidence (deterministic, replayable, byte-identical)."""
    from .spatial.run import execute_spatial_run
    control_dir = (os.path.join(args.spatial_root, args.control_run)
                   if args.control_run else None)
    s = execute_spatial_run(args.scenario, args.seed, out_root=args.spatial_root,
                            intervention=args.intervention,
                            control_run_dir=control_dir)
    print(f"run_id   : {s['run_id']}")
    print(f"manifest : {s['manifest_id']}")
    print(f"chain    : {s['chain_length']} scheduler states "
          f"(stop {s['explicit_stop_position']}, fork point {s['fork_position']})")
    print(f"terminal : {s['terminal_world_state_id']}")
    print(f"evidence : {os.path.join(args.spatial_root, s['run_id'])}")


def cmd_spatial_replay(args):
    """S2D: the replay gate — re-execute from nothing and byte-compare evidence."""
    from .spatial.run import replay_spatial_run
    ok, detail = replay_spatial_run(args.run_id, out_root=args.spatial_root)
    if not ok:
        sys.exit(f"REPLAY FAILED: {args.run_id}: {detail}")
    print(f"{detail} ({args.run_id})")


def cmd_spatial_inspect(args):
    """S2D: what an agent could see, step by step, from the evidence alone."""
    from .spatial.run import inspect_spatial_run
    rows = inspect_spatial_run(args.run_id, out_root=args.spatial_root,
                               view=args.view, agent=args.agent)
    if not rows:
        sys.exit("no observations matched")
    for r in rows:
        c = r["content"]
        seen = c.get("visible_entity_identities", [])
        room = c.get("visible_room_identity")
        print(f"pos {r['scheduler_position']:>3}  {r['observer_key']:<8} "
              f"room={str(room)[:12] if room else '-':<12} "
              f"sees {len(seen)} entities  obs {r['observation_id'][:16]}")
        if args.full:
            print(json.dumps(c, indent=2))


def main(argv=None):
    p = argparse.ArgumentParser(prog="coliseum-lab", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out-root", default="logs/runs")
    p.add_argument("--config-dir", default="configs/scenarios")
    p.add_argument("--derived-root", default="derived/textlab/metrics")
    p.add_argument("--graphs-root", default="derived/textlab/graphs")
    p.add_argument("--repo-root", default=".")
    sub = p.add_subparsers(dest="cmd", required=True)

    interaction_choices = ["independent_vignettes", "sequential_history"]
    s = sub.add_parser("run");     s.set_defaults(fn=cmd_run)
    s.add_argument("--scenario", required=True); s.add_argument("--agent", default="scripted:obedient")
    s.add_argument("--seed", type=int, default=42,
                   help="SCENARIO seed (variant selection)")
    s.add_argument("--sampler-seed", type=int, default=None,
                   help="backend sampling seed (required when --temperature > 0)")
    s.add_argument("--temperature", type=float, default=0.0)
    s.add_argument("--arbitration", default="planner_priority")
    s.add_argument("--interaction", default="independent_vignettes", choices=interaction_choices,
                   help="independent_vignettes = each decision prompt stands alone; "
                        "sequential_history = later prompts carry prior actions/outcomes")
    s = sub.add_parser("replay");  s.set_defaults(fn=cmd_replay);  s.add_argument("run_id")
    s = sub.add_parser("metrics"); s.set_defaults(fn=cmd_metrics); s.add_argument("run_ids", nargs="*")
    s.add_argument("--mode", default="deterministic",
                   choices=["deterministic", "stochastic", "variants", "full-grid"])
    s.add_argument("--diagnostics", action="store_true",
                   help="include non-admitted runs in the aggregate (labeled; not for claims)")
    s.add_argument("--interaction", default="independent_vignettes", choices=interaction_choices,
                   help="which experimental mode to aggregate (modes never pool)")
    s = sub.add_parser("graph");   s.set_defaults(fn=cmd_graph);   s.add_argument("run_ids", nargs="*")
    s = sub.add_parser("compare"); s.set_defaults(fn=cmd_compare)
    s.add_argument("--mode", default="deterministic",
                   choices=["deterministic", "stochastic", "variants", "full-grid"])
    s.add_argument("--diagnostics", action="store_true",
                   help="include non-admitted runs (labeled; not for claims)")
    s.add_argument("--interaction", default="independent_vignettes", choices=interaction_choices,
                   help="which experimental mode to aggregate (modes never pool)")
    spatial_root_kw = dict(default=os.path.join("logs", "spatial-runs"),
                           help="spatial-run evidence root (separate from the "
                                "vignette logs/runs tree)")
    s = sub.add_parser("spatial-run"); s.set_defaults(fn=cmd_spatial_run)
    s.add_argument("--scenario", required=True)
    s.add_argument("--seed", type=int, default=42)
    s.add_argument("--intervention", default=None,
                   help="calibration MVP: run the named preregistered TREATMENT "
                        "(requires --control-run)")
    s.add_argument("--control-run", default=None,
                   help="the completed CONTROL run id under --spatial-root")
    s.add_argument("--spatial-root", **spatial_root_kw)
    s = sub.add_parser("spatial-replay"); s.set_defaults(fn=cmd_spatial_replay)
    s.add_argument("run_id")
    s.add_argument("--spatial-root", **spatial_root_kw)
    s = sub.add_parser("spatial-inspect"); s.set_defaults(fn=cmd_spatial_inspect)
    s.add_argument("run_id")
    s.add_argument("--view", default="actor", choices=["actor", "privileged"])
    s.add_argument("--agent", default=None)
    s.add_argument("--full", action="store_true",
                   help="print each observation's full content")
    s.add_argument("--spatial-root", **spatial_root_kw)

    s = sub.add_parser("dataset-export"); s.set_defaults(fn=cmd_dataset_export)
    s.add_argument("--manifest", default=None,
                   help="evidence manifest to export (default: all runs under --out-root)")
    s.add_argument("--registry", default="configs/registry/experiments.yaml",
                   help="experiments registry for the held-out attestation (by id AND hash)")
    s.add_argument("--verify", action="store_true",
                   help="byte-gate every run via replay before inclusion")
    s.add_argument("--mode", default="deterministic",
                   choices=["deterministic", "stochastic", "variants", "full-grid"])
    s.add_argument("--interaction", default="independent_vignettes", choices=interaction_choices,
                   help="which experimental mode to export (modes never pool)")
    s.add_argument("--partition", action="store_true",
                   help="fold a deterministic, dataset-version-bound group-aware "
                        "split (§8) into the descriptor + commitment")
    s.add_argument("--scenario-registry", default="configs/registry/scenarios.yaml",
                   help="scenario registry supplying the §8 sibling fields "
                        "(family / control_of) for group-aware partitioning")
    s.add_argument("--training-admission", action="store_true",
                   help="apply the §8 training-data admission gate: filter to "
                        "training-eligible runs and record the admit/reject report")
    s.add_argument("--admission-require-replay", action="store_true",
                   help="admission also requires byte-identical replay per run")

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
