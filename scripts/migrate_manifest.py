#!/usr/bin/env python3
"""Migrate a legacy sweep manifest: add the exact evidence dir to each row.

    python3 scripts/migrate_manifest.py derived/textlab/sweep-v2-manifest.jsonl

Rules (Day-5 pre-flight finding #6): attempt suffixes are parsed NUMERICALLY,
never sorted lexicographically; a run_id with more than one attempt is AMBIGUOUS
and aborts the migration (a human must decide which attempt is the evidence).
The original manifest is preserved at <path>.pre-migration.
"""
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ATTEMPT_RE = re.compile(r"\.a(\d+)$")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    path = sys.argv[1]
    out_root = sys.argv[2] if len(sys.argv) > 2 else "logs/runs"
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    existing = os.listdir(out_root)

    migrated = 0
    for i, rec in enumerate(rows):
        if "dir" in rec:
            continue
        attempts = {}
        for name in existing:
            if name == rec["run_id"]:
                attempts[0] = name
            elif name.startswith(rec["run_id"] + ".a"):
                m = _ATTEMPT_RE.search(name)
                if m and name == f"{rec['run_id']}.a{m.group(1)}":
                    attempts[int(m.group(1))] = name
        if not attempts:
            sys.exit(f"row {i + 1}: no evidence dir found for {rec['run_id']} — ABORT")
        if len(attempts) > 1:
            sys.exit(f"row {i + 1}: AMBIGUOUS — {sorted(attempts.values())} all exist for "
                     f"{rec['run_id']}; a human must pick the evidence attempt. ABORT")
        name = attempts[max(attempts)]
        run = json.load(open(os.path.join(out_root, name, "run.json"), encoding="utf-8"))
        if run["run_id"] != rec["run_id"]:
            sys.exit(f"row {i + 1}: evidence mismatch in {name} — ABORT")
        rec["dir"] = name
        rec["scenario_seed"] = rec.get("scenario_seed", rec.get("seed"))
        rec["sampler_seed"] = rec.get("sampler_seed")
        rec["regime_id"] = run.get("comparison_regime_id", "")
        rec["migrated"] = True
        migrated += 1

    shutil.copy(path, path + ".pre-migration")
    with open(path, "w", encoding="utf-8") as fh:
        for rec in rows:
            fh.write(json.dumps(rec) + "\n")
    print(f"migrated {migrated}/{len(rows)} rows; original at {path}.pre-migration")


if __name__ == "__main__":
    main()
