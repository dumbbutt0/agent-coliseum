#!/usr/bin/env python3
"""The first reportable cross-model sweep: pinned-digest models x all scenarios x seeds.

    OLLAMA_HOST=http://10.0.0.8:11434 python3 scripts/sweep_models.py \
        --models llama3.1:latest qwen3:8b gemma3:latest --seeds 1 2 3 5 8

Model-major order (minimal model swapping on the host). Resume-safe: completed
(model, scenario, seed) triples are recorded in the sweep manifest and skipped on
rerun. Aborts a model entirely if its digest cannot be pinned (ruling: no digest,
not reportable — and a sweep is reportable-only).
"""
import argparse
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coliseum.textlab.agents import OllamaAgent  # noqa: E402
from coliseum.textlab.graph_export import write_graphs  # noqa: E402
from coliseum.textlab.metrics import write_aggregate, write_run_metrics  # noqa: E402
from coliseum.textlab.runner import run_scenario  # noqa: E402


def manifest_load(path):
    done = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                done[(rec["model"], rec["scenario"], rec["seed"])] = rec
    return done


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--models", nargs="+",
                   default=["llama3.1:latest", "qwen3:8b", "gemma3:latest"])
    p.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 5, 8])
    p.add_argument("--config-dir", default="configs/scenarios")
    p.add_argument("--out-root", default="logs/runs")
    p.add_argument("--manifest", default="derived/textlab/sweep-manifest.jsonl")
    args = p.parse_args()

    scenarios = sorted(f[:-5] for f in os.listdir(args.config_dir) if f.endswith(".yaml"))
    os.makedirs(os.path.dirname(args.manifest), exist_ok=True)
    done = manifest_load(args.manifest)
    total = len(args.models) * len(scenarios) * len(args.seeds)
    print(f"sweep: {len(args.models)} models x {len(scenarios)} scenarios x "
          f"{len(args.seeds)} seeds = {total} runs ({len(done)} already done)", flush=True)

    manifest = open(args.manifest, "a", encoding="utf-8")
    completed = failed = 0
    for model in args.models:
        probe = OllamaAgent(model)                       # digest check before any run
        if probe.digest_status != "ok":
            print(f"!! {model}: digest could not be pinned — model SKIPPED "
                  f"(sweep is reportable-only)", flush=True)
            continue
        print(f"== {model}  digest={probe.model_digest[:20]}  family={probe.model_family} "
              f"host={probe.host}", flush=True)
        for scenario in scenarios:
            path = os.path.join(args.config_dir, f"{scenario}.yaml")
            for seed in args.seeds:
                key = (model, scenario, seed)
                if key in done:
                    continue
                try:
                    r = run_scenario(path, f"llm:ollama:{model}", seed, out_root=args.out_root)
                    ok = r.run.reportable
                    manifest.write(json.dumps({"model": model, "scenario": scenario,
                                               "seed": seed, "run_id": r.run_id,
                                               "reportable": ok,
                                               "path": r.final_actions}) + "\n")
                    manifest.flush()
                    completed += 1
                    print(f"  [{completed + len(done)}/{total}] {scenario} s{seed}: "
                          f"{' -> '.join(r.final_actions)}", flush=True)
                except Exception as e:
                    failed += 1
                    print(f"  !! {scenario} s{seed}: {e.__class__.__name__}: {e}", flush=True)
                    traceback.print_exc()
    manifest.close()

    done = manifest_load(args.manifest)
    run_dirs = sorted(os.path.join(args.out_root, rec["run_id"]) for rec in done.values())
    run_dirs = [d for d in run_dirs if os.path.exists(os.path.join(d, "run.json"))]
    print(f"\nderiving metrics + graphs for {len(run_dirs)} sweep runs...", flush=True)
    for d in run_dirs:
        write_run_metrics(d)
    write_aggregate(run_dirs)
    write_graphs(run_dirs)
    non_reportable = [rec["run_id"] for rec in done.values() if not rec["reportable"]]
    print(f"sweep complete: {len(done)} runs, {len(non_reportable)} non-reportable"
          + (f" ({non_reportable[:3]}...)" if non_reportable else ""), flush=True)


if __name__ == "__main__":
    main()
