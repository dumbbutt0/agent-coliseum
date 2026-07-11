#!/usr/bin/env python3
"""Migrate a legacy sweep manifest to the COMPLETE current row schema.

    python3 scripts/migrate_manifest.py derived/textlab/sweep-v2-manifest.jsonl

This is the ONLY path for legacy rows (audit blocker 4): manifest_load
refuses any row missing a REQUIRED_ROW_FIELDS entry, so migration backfills
every required field from the run.json + decisions.jsonl evidence and stamps
`"migrated": true`. A legacy value that CONTRADICTS its evidence aborts —
migration completes rows, it never rewrites claims.

Rules (Day-5 pre-flight finding #6): attempt suffixes are parsed NUMERICALLY,
never sorted lexicographically; a run_id with more than one attempt is
AMBIGUOUS and aborts the migration (a human must decide which attempt is the
evidence). The original manifest is preserved at <path>.pre-migration.
"""
import json
import os
import re
import shutil
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))

from sweep_models import REQUIRED_ROW_FIELDS  # noqa: E402

_ATTEMPT_RE = re.compile(r"\.a(\d+)$")


def evidence_row(run: dict, dir_name: str, run_dir: str) -> dict:
    """The complete current-schema row derived purely from evidence."""
    decision_path = []
    decisions_file = os.path.join(run_dir, "decisions.jsonl")
    if os.path.exists(decisions_file):
        with open(decisions_file, encoding="utf-8") as fh:
            for line in fh:
                event = json.loads(line)
                if event.get("kind") == "decision_node":
                    decision_path.append(event["data"]["final_action"])
    return {"regime_id": run.get("comparison_regime_id", ""),
            "model": run.get("agent_config", {}).get("model", ""),
            "scenario": run["scenario_id"],
            "scenario_seed": run.get("scenario_seed", run["seed"]),
            "sampler_seed": run.get("sampler_seed"),
            "variant_id": run["variant_id"],
            "temperature": run.get("sampling", {}).get("temperature", 0),
            "sampling_mode": run.get("sampling", {}).get("mode",
                                                         "deterministic"),
            "digest": run.get("agent_config", {}).get("model_digest", ""),
            "scenario_hash": run.get("scenario_hash", ""),
            "arbitration": run.get("arbitration", "planner_priority"),
            "run_id": run["run_id"],
            "dir": dir_name,
            "reportable": run.get("reportable", True),
            "stochastic_reportable": run.get("stochastic_reportable", False),
            "interaction_mode": run.get("interaction_mode",
                                        "independent_vignettes"),
            "path": decision_path}


def find_evidence_dir(rec: dict, existing: list, row_no: int) -> str:
    if "dir" in rec:
        return rec["dir"]
    attempts = {}
    for name in existing:
        if name == rec["run_id"]:
            attempts[0] = name
        elif name.startswith(rec["run_id"] + ".a"):
            m = _ATTEMPT_RE.search(name)
            if m and name == f"{rec['run_id']}.a{m.group(1)}":
                attempts[int(m.group(1))] = name
    if not attempts:
        sys.exit(f"row {row_no}: no evidence dir found for {rec['run_id']} — ABORT")
    if len(attempts) > 1:
        sys.exit(f"row {row_no}: AMBIGUOUS — {sorted(attempts.values())} all exist for "
                 f"{rec['run_id']}; a human must pick the evidence attempt. ABORT")
    return attempts[max(attempts)]


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    path = sys.argv[1]
    out_root = sys.argv[2] if len(sys.argv) > 2 else "logs/runs"
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    existing = os.listdir(out_root)

    migrated = 0
    for i, rec in enumerate(rows):
        if all(f in rec for f in REQUIRED_ROW_FIELDS):
            continue                       # already current schema
        name = find_evidence_dir(rec, existing, i + 1)
        run_dir = os.path.join(out_root, name)
        run = json.load(open(os.path.join(run_dir, "run.json"),
                             encoding="utf-8"))
        if run["run_id"] != rec["run_id"]:
            sys.exit(f"row {i + 1}: evidence mismatch in {name} — ABORT")
        complete = evidence_row(run, name, run_dir)
        for field, value in complete.items():
            if field in rec and rec[field] != value:
                sys.exit(f"row {i + 1}: legacy {field!r} contradicts evidence "
                         f"({rec[field]!r} vs {value!r}) — migration never "
                         "rewrites claims. ABORT")
            rec[field] = value
        rec["migrated"] = True
        migrated += 1

    shutil.copy(path, path + ".pre-migration")
    with open(path, "w", encoding="utf-8") as fh:
        for rec in rows:
            fh.write(json.dumps(rec) + "\n")
    print(f"migrated {migrated}/{len(rows)} rows; original at {path}.pre-migration")


if __name__ == "__main__":
    main()
