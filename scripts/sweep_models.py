#!/usr/bin/env python3
"""Reportable cross-model sweep: pinned-digest models x scenarios x scenario seeds
(x sampler seeds when stochastic). Human CLI over coliseum.textlab.sweep.

    OLLAMA_HOST=http://10.0.0.8:11434 python3 scripts/sweep_models.py \
        --models llama3.1:latest --seeds 1 2 3 5 8                      # deterministic
    ... --temperature 0.7 --sampler-seeds 11 12 13 14 15                # stochastic

The sweep core lives in coliseum/textlab/sweep.py — the SAME run_sweep the
audited `ollama_local` autonomy driver calls, so a human sweep and an audited
runner sweep are byte-for-byte the same code path. Resume identity (Day-5): a
manifest row is keyed by (FULL comparison_regime_id, scenario_seed,
sampler_seed) and carries its exact evidence dir; a repulled tag changes the
digest -> new regime -> reruns.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coliseum.textlab.graph_export import write_graphs  # noqa: E402
from coliseum.textlab.metrics import (write_aggregate,  # noqa: E402
                                      write_run_metrics)
from coliseum.textlab.schema import INTERACTION_MODES  # noqa: E402
# Re-exported so scripts/tests keep importing the shared constants/loader from
# here; the single definition lives in coliseum.textlab.sweep.
from coliseum.textlab.sweep import (REQUIRED_ROW_FIELDS,  # noqa: E402,F401
                                    SweepAborted, manifest_load, run_sweep)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--models", nargs="+",
                   default=["llama3.1:latest", "qwen3:8b", "gemma3:latest"])
    p.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 5, 8],
                   help="SCENARIO seeds (variant selection)")
    p.add_argument("--sampler-seeds", type=int, nargs="+", default=None,
                   help="sampler seeds (stochastic runs; requires --temperature > 0)")
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--arbitration", default="planner_priority")
    p.add_argument("--interaction", default="independent_vignettes",
                   choices=list(INTERACTION_MODES),
                   help="interaction mode (audit item 1); part of the hashed "
                        "regime, so sequential sweeps never resume against "
                        "independent-mode manifest rows (e.g. sequential_history)")
    p.add_argument("--config-dir", default="configs/scenarios")
    p.add_argument("--out-root", default="logs/runs")
    p.add_argument("--manifest", default="derived/textlab/sweep-manifest.jsonl")
    args = p.parse_args()

    scenarios = sorted(f[:-5] for f in os.listdir(args.config_dir)
                       if f.endswith(".yaml"))
    spec = {"models": args.models, "scenarios": scenarios, "seeds": args.seeds,
            "sampler_seeds": args.sampler_seeds, "temperature": args.temperature,
            "arbitration": args.arbitration, "interaction": args.interaction,
            "config_dir": args.config_dir, "out_root": args.out_root,
            "manifest": args.manifest}
    try:
        run_sweep(spec, progress=lambda m: print(m, flush=True))
    except SweepAborted as exc:
        sys.exit(f"sweep aborted: {exc}")

    mode = "stochastic" if args.temperature and args.temperature > 0 \
        else "deterministic"
    done = manifest_load(args.manifest, args.out_root)
    run_dirs = sorted({os.path.join(args.out_root, rec["dir"])
                       for rec in done.values()})
    print(f"\nderiving metrics + graphs for {len(run_dirs)} sweep runs...",
          flush=True)
    for d in run_dirs:
        write_run_metrics(d)
    write_aggregate(run_dirs, mode=mode, interaction_mode=args.interaction)
    write_graphs(run_dirs)
    non_rep = [r["run_id"] for r in done.values()
               if not (r["stochastic_reportable"] if mode == "stochastic"
                       else r["reportable"])]
    print(f"sweep complete: {len(done)} runs, {len(non_rep)} "
          f"non-{mode}-reportable", flush=True)


if __name__ == "__main__":
    main()
