#!/usr/bin/env python3
"""Reportable cross-model sweep: pinned-digest models x scenarios x scenario seeds
(x sampler seeds when stochastic).

    OLLAMA_HOST=http://10.0.0.8:11434 python3 scripts/sweep_models.py \
        --models llama3.1:latest --seeds 1 2 3 5 8                      # deterministic
    ... --temperature 0.7 --sampler-seeds 11 12 13 14 15                # stochastic

Resume identity (Day-5): a manifest row is keyed by (FULL comparison_regime_id,
scenario_seed, sampler_seed) and must carry its exact evidence dir; rows are
validated against their run.json on load. Legacy dir-less rows are REFUSED
(migrate first). A repulled tag changes the digest -> new regime -> reruns.
"""
import argparse
import json
import os
import re
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coliseum.textlab.agents import OllamaAgent  # noqa: E402
from coliseum.textlab.graph_export import write_graphs  # noqa: E402
from coliseum.textlab.metrics import write_aggregate, write_run_metrics  # noqa: E402
from coliseum.textlab.runner import ARBITRATION_VERSION, run_scenario  # noqa: E402
from coliseum.textlab.scenario import load_scenario  # noqa: E402
from coliseum.textlab.schema import (SchemaError, build_behavioral_config,  # noqa: E402
                                     regime_hashes, validate_sampling)

_ATTEMPT_RE = re.compile(r"\.a(\d+)$")

# The complete current manifest-row schema — exactly what the sweep writer
# emits (audit blocker 4). The loader REQUIRES every field; the writer builds
# rows against the same constant so the two can never drift. Legacy rows go
# through scripts/migrate_manifest.py, never implicit acceptance.
REQUIRED_ROW_FIELDS = (
    "regime_id", "model", "scenario", "scenario_seed", "sampler_seed",
    "variant_id", "temperature", "sampling_mode", "digest", "scenario_hash",
    "arbitration", "run_id", "dir", "reportable", "stochastic_reportable",
    "interaction_mode", "path",
)


def manifest_load(path: str, out_root: str) -> dict:
    """(regime_id, scenario_seed, sampler_seed) -> validated row.

    Full-row validation (audit item 6 + blocker 4, closes ISSUES.md #1):
    every row must carry the COMPLETE current schema (REQUIRED_ROW_FIELDS) and
    every field must agree with its run.json evidence — a manifest can neither
    assert anything its evidence contradicts nor omit its way past validation.
    Duplicate resume keys are REFUSED outright (no last-row-wins); so are
    dir/attempt mismatches and legacy dir-less rows."""
    done = {}
    if not os.path.exists(path):
        return done
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            rec = json.loads(line)
            where = f"{path}:{i + 1}"
            if "dir" not in rec:
                raise SchemaError(
                    f"{where}: legacy manifest row without an exact evidence dir — "
                    "REFUSED (run scripts/migrate_manifest.py or use a fresh manifest)")
            missing = [f for f in REQUIRED_ROW_FIELDS if f not in rec]
            if missing:
                raise SchemaError(
                    f"{where}: incomplete manifest row — missing required "
                    f"current-schema fields {missing}; legacy rows must go "
                    "through scripts/migrate_manifest.py, never implicit "
                    "acceptance")
            run_dir = os.path.join(out_root, rec["dir"])
            manifest_file = os.path.join(run_dir, "run.json")
            if not os.path.exists(manifest_file):
                raise SchemaError(f"{where}: evidence dir missing run.json: {run_dir}")
            run = json.load(open(manifest_file, encoding="utf-8"))
            decision_path = []
            decisions_file = os.path.join(run_dir, "decisions.jsonl")
            if os.path.exists(decisions_file):
                with open(decisions_file, encoding="utf-8") as decisions:
                    for decision_line in decisions:
                        event = json.loads(decision_line)
                        if event.get("kind") == "decision_node":
                            decision_path.append(event["data"]["final_action"])
            expected = {
                "run_id": run["run_id"],
                "regime_id": run.get("comparison_regime_id", ""),
                "model": run.get("agent_config", {}).get("model", ""),
                "digest": run.get("agent_config", {}).get("model_digest", ""),
                "scenario": run["scenario_id"],
                "scenario_hash": run.get("scenario_hash", ""),
                "seed": run["seed"],
                "scenario_seed": run.get("scenario_seed", run["seed"]),
                "sampler_seed": run.get("sampler_seed"),
                "variant_id": run["variant_id"],
                "temperature": run.get("sampling", {}).get("temperature", 0),
                "sampling_mode": run.get("sampling", {}).get("mode", "deterministic"),
                "arbitration": run.get("arbitration", "planner_priority"),
                "reportable": run.get("reportable", True),
                "stochastic_reportable": run.get("stochastic_reportable", False),
                "interaction_mode": run.get("interaction_mode", "independent_vignettes"),
                "path": decision_path,
            }
            for field_name, want in expected.items():
                # every REQUIRED_ROW_FIELDS entry is guaranteed present above;
                # this guard only skips loader-side extras (e.g. 'seed') that
                # rows legitimately never carry
                if field_name in rec and rec[field_name] != want:
                    raise SchemaError(f"{where}: {field_name} mismatch vs evidence "
                                      f"({rec[field_name]!r} vs {want!r})")
            # dir <-> run_id/attempt coherence (numeric parse only; finding: .a10 < .a2)
            m = _ATTEMPT_RE.search(rec["dir"])
            dir_attempt = int(m.group(1)) if m else 0
            if _ATTEMPT_RE.sub("", rec["dir"]) != run["run_id"]:
                raise SchemaError(f"{where}: dir {rec['dir']!r} does not name its run_id "
                                  f"{run['run_id']!r}")
            if run.get("attempt", 0) != dir_attempt:
                raise SchemaError(f"{where}: dir attempt .a{dir_attempt} disagrees with "
                                  f"run.json attempt {run.get('attempt', 0)}")
            # Resume identity comes only from validated evidence, never optional
            # row fields. Omitting a field therefore cannot create a second key
            # for the same run and bypass duplicate refusal.
            key = (run.get("comparison_regime_id", ""),
                   run.get("scenario_seed", run["seed"]),
                   run.get("sampler_seed"))
            if key in done:
                raise SchemaError(f"{where}: duplicate resume key {key} — REFUSED "
                                  "(no last-row-wins; deduplicate the manifest)")
            done[key] = rec
    return done


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
    p.add_argument("--config-dir", default="configs/scenarios")
    p.add_argument("--out-root", default="logs/runs")
    p.add_argument("--manifest", default="derived/textlab/sweep-manifest.jsonl")
    args = p.parse_args()

    if args.temperature > 0:
        sampling = {"mode": "stochastic", "temperature": args.temperature}
        sampler_seeds = args.sampler_seeds or []
        if not sampler_seeds:
            sys.exit("stochastic sweep requires --sampler-seeds")
        mode = "stochastic"
    else:
        sampling = None
        sampler_seeds = [None]
        mode = "deterministic"
    validate_sampling(sampling, sampler_seeds[0])

    scenarios = sorted(f[:-5] for f in os.listdir(args.config_dir) if f.endswith(".yaml"))
    os.makedirs(os.path.dirname(args.manifest), exist_ok=True)
    done = manifest_load(args.manifest, args.out_root)
    total = len(args.models) * len(scenarios) * len(args.seeds) * len(sampler_seeds)
    print(f"sweep[{mode}]: {len(args.models)} models x {len(scenarios)} scenarios x "
          f"{len(args.seeds)} scenario-seeds x {len(sampler_seeds)} sampler-seeds "
          f"= {total} runs ({len(done)} already done)", flush=True)

    manifest = open(args.manifest, "a", encoding="utf-8")
    completed = 0
    for model in args.models:
        probe = OllamaAgent(model)
        if probe.digest_status != "ok":
            print(f"!! {model}: digest could not be pinned — model SKIPPED", flush=True)
            continue
        probe.configure_sampling(sampling, sampler_seeds[0])
        # resolve backend version + effective think mode BEFORE computing the resume
        # regime — the probe's spec must hash exactly like the runtime agents' (item 8)
        probe.resolve_effective_config()
        print(f"== {model}  digest={probe.model_digest[:20]}  family={probe.model_family} "
              f"host={probe.host}  backend={probe.backend_version}  mode={mode}", flush=True)
        for scenario_name in scenarios:
            path = os.path.join(args.config_dir, f"{scenario_name}.yaml")
            scen = load_scenario(path)
            # pre-run regime (probe spec == runtime spec: same code, digest, sampling)
            bc = build_behavioral_config(scen.scenario_id, scen.behavioral_hash(),
                                         probe.spec_dict(), args.arbitration,
                                         ARBITRATION_VERSION, validate_sampling(sampling, sampler_seeds[0]))
            regime_id, _ = regime_hashes(bc)
            for scenario_seed in args.seeds:
                for sampler_seed in sampler_seeds:
                    if (regime_id, scenario_seed, sampler_seed) in done:
                        continue
                    try:
                        r = run_scenario(path, f"llm:ollama:{model}", scenario_seed,
                                         out_root=args.out_root, arbitration=args.arbitration,
                                         sampling=sampling, sampler_seed=sampler_seed)
                        if r.run.comparison_regime_id != regime_id:
                            print(f"  !! regime drift mid-sweep for {model}/{scenario_name} "
                                  f"— digest or config changed; aborting model", flush=True)
                            break
                        row = {"regime_id": r.run.comparison_regime_id,
                               "model": model, "scenario": scenario_name,
                               "scenario_seed": scenario_seed, "sampler_seed": sampler_seed,
                               "variant_id": r.run.variant_id,
                               "temperature": r.run.sampling.get("temperature", 0),
                               "sampling_mode": r.run.sampling["mode"],
                               "digest": r.run.agent_config.get("model_digest", ""),
                               "scenario_hash": r.run.scenario_hash,
                               "arbitration": args.arbitration,
                               "run_id": r.run_id,
                               "dir": os.path.basename(r.run_dir),
                               "reportable": r.run.reportable,
                               "stochastic_reportable": r.run.stochastic_reportable,
                               "interaction_mode": r.run.interaction_mode,
                               "path": r.final_actions}
                        # writer and loader share one schema constant — a row
                        # this sweep emits always reloads (blocker 4)
                        assert set(REQUIRED_ROW_FIELDS) <= set(row), \
                            sorted(set(REQUIRED_ROW_FIELDS) - set(row))
                        manifest.write(json.dumps(row) + "\n")
                        manifest.flush()
                        completed += 1
                        k = f" k{sampler_seed}" if sampler_seed is not None else ""
                        print(f"  [{completed + len(done)}/{total}] {scenario_name} "
                              f"s{scenario_seed}{k}: {' -> '.join(r.final_actions)}", flush=True)
                    except Exception as e:
                        print(f"  !! {scenario_name} s{scenario_seed} k{sampler_seed}: "
                              f"{e.__class__.__name__}: {e}", flush=True)
                        traceback.print_exc()
    manifest.close()

    done = manifest_load(args.manifest, args.out_root)
    run_dirs = sorted({os.path.join(args.out_root, rec["dir"]) for rec in done.values()})
    print(f"\nderiving metrics + graphs for {len(run_dirs)} sweep runs...", flush=True)
    for d in run_dirs:
        write_run_metrics(d)
    write_aggregate(run_dirs, mode=mode)
    write_graphs(run_dirs)
    non_rep = [r["run_id"] for r in done.values()
               if not (r["stochastic_reportable"] if mode == "stochastic" else r["reportable"])]
    print(f"sweep complete: {len(done)} runs, {len(non_rep)} non-{mode}-reportable", flush=True)


if __name__ == "__main__":
    main()
