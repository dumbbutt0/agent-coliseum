"""T0-A audited-trajectory substrate — dataset export (structural; no labels, no training).

This is the first bounded slice of the training-annex T0-A "evidence substrate": it turns already-
validated evidence into a provenance-complete, non-pooled, content-addressed DATASET DESCRIPTOR plus a
descriptive DATASET CARD. It introduces NO new normative labels (that is T0-B), NO group-aware
partitioning (a later slice), and NO training. Every admission / retry-collapse / effective-unit /
byte-gate / hash primitive is reused unchanged:

  - admission + retry collapse + effective-unit counting  -> metrics.aggregate (metrics.py)
  - row<->evidence manifest validation + dedup            -> sweep.manifest_load
  - byte-identical replay inclusion gate                  -> sweep.verify_run_replay
  - canonical serialization + content hashing             -> schema.canonical_json / config_hash
  - held-out contamination refusal (by id AND hash)       -> mirrors registry.py held-out gate

The dataset commitment is domain-separated + schema-versioned: same evidence -> same commitment.
"""
from __future__ import annotations

import json
import os

from .schema import canonical_json, config_hash
from .metrics import aggregate
from .sweep import manifest_load, verify_run_replay

DATASET_SCHEMA_VERSION = "1"
DATASET_COMMITMENT_DOMAIN = "dataset:commitment:v1"


def _held_out_offenders(run_dirs, held_ids, held_hashes):
    """Return [(scenario_id, run_dir_basename)] for any run whose scenario is held-out
    by id OR by scenario_hash — mirrors the registry held-out gate (registry.py:200-208)."""
    offenders = []
    for d in run_dirs:
        run = json.load(open(os.path.join(d, "run.json"), encoding="utf-8"))
        if run["scenario_id"] in held_ids or run.get("scenario_hash", "") in held_hashes:
            offenders.append((run["scenario_id"], os.path.basename(d)))
    return offenders


def build_dataset(run_dirs, *, mode="deterministic",
                  interaction_mode="independent_vignettes",
                  held_out_scenarios=None, held_out_hashes=None,
                  verify=False, config_dir="configs/scenarios"):
    """Build a canonical, non-pooled dataset descriptor from a set of run dirs.

    Reuses metrics.aggregate for admission + retry-collapse + effective-unit counting; refuses if any
    included run is a held-out scenario (by id OR scenario_hash); optionally byte-gates every run via
    verify_run_replay before inclusion. NO labels, NO partitioning, NO training.
    """
    run_dirs = sorted(run_dirs)
    if not run_dirs:
        raise ValueError("no run dirs to export")

    held_ids = set(held_out_scenarios or ())
    held_hashes = set(held_out_hashes or ())
    if held_ids or held_hashes:
        offenders = _held_out_offenders(run_dirs, held_ids, held_hashes)
        if offenders:
            names = sorted({s for s, _ in offenders})
            raise ValueError(
                "held-out scenario(s) present in dataset export — REFUSED "
                f"(a held-out scenario may never leave the M14 evaluation, SPEC E6): {names}")

    replay_verification = None
    if verify:
        failed = []
        for d in run_dirs:
            ok, detail = verify_run_replay(d, config_dir)
            if not ok:
                failed.append({"run_dir": os.path.basename(d), "detail": detail})
        if failed:
            raise ValueError(f"replay byte-gate failed for {len(failed)} run(s): {failed}")
        replay_verification = {"verified_runs": len(run_dirs), "method": "byte-identical replay"}

    agg = aggregate(run_dirs, mode=mode, interaction_mode=interaction_mode)

    # one record per NON-POOLED effective-unit cell; already retry-collapsed + effective-n counted
    units = []
    for cell_key in sorted(agg["cells"]):
        cell = agg["cells"][cell_key]
        counts = cell["counts"]
        units.append({
            "cell_key": cell_key,
            "comparison_regime_id": cell["comparison_regime_id"],
            "agent_regime_id": cell["agent_regime_id"],
            "scenario_id": cell["scenario_id"],
            "run_ids": cell["run_ids"],
            "seeds": cell["seeds"],
            "sampler_seeds": cell["sampler_seeds"],
            "effective_n": counts["effective_n"],
            "raw_attempt_n": counts["raw_attempt_n"],
            "metrics": cell["metrics"],
        })

    descriptor = {
        "dataset_schema_version": DATASET_SCHEMA_VERSION,
        "metrics_version": agg["metrics_version"],
        "mode": mode,
        "interaction_mode": interaction_mode,
        "admission": agg["admission"],
        "effective_unit_count": len(units),
        "units": units,
        "excluded": agg["excluded"],
        "attempt_exclusions": agg["attempt_exclusions"],
        "held_out_attestation": {
            "checked_ids": sorted(held_ids),
            "checked_hashes": sorted(held_hashes),
            "contamination_found": False,
        },
        "replay_verification": replay_verification,
    }
    descriptor["dataset_commitment"] = dataset_commitment(descriptor)
    return descriptor


def dataset_from_manifest(manifest_path, out_root, **kwargs):
    """Resolve run dirs from a validated evidence manifest (sweep.manifest_load) then build the dataset.
    manifest_load performs full row<->evidence validation, dedup, and legacy-row refusal for free."""
    rows = manifest_load(manifest_path, out_root)
    run_dirs = [os.path.join(out_root, rec["dir"]) for rec in rows.values()]
    if not run_dirs:
        raise ValueError(f"no evidence rows in manifest {manifest_path!r}")
    return build_dataset(run_dirs, **kwargs)


def dataset_commitment(descriptor):
    """Content-addressed commitment over the descriptor (excluding the commitment field), domain-separated
    and schema-versioned. Same descriptor payload -> same commitment (no wall-clock, canonical JSON)."""
    body = {k: v for k, v in descriptor.items() if k != "dataset_commitment"}
    return config_hash({"domain": DATASET_COMMITMENT_DOMAIN,
                        "schema_version": DATASET_SCHEMA_VERSION,
                        "payload": body})


def dataset_card(descriptor):
    """Descriptive Markdown card, derived idempotently from the descriptor (no hand-edited numbers)."""
    hoa = descriptor["held_out_attestation"]
    lines = [
        "# Dataset Card — T0-A audited-trajectory substrate",
        "",
        f"- dataset schema version: `{descriptor['dataset_schema_version']}`",
        f"- metrics version: `{descriptor['metrics_version']}`",
        f"- mode / interaction: `{descriptor['mode']}` / `{descriptor['interaction_mode']}`",
        f"- admission: `{descriptor['admission']}`",
        f"- effective units: **{descriptor['effective_unit_count']}**",
        f"- excluded runs: {len(descriptor['excluded'])}",
        f"- attempt exclusions: {len(descriptor['attempt_exclusions'])}",
        (f"- held-out attestation: checked {len(hoa['checked_ids'])} id(s) / "
         f"{len(hoa['checked_hashes'])} hash(es), contamination_found={hoa['contamination_found']}"),
        f"- replay verification: {'yes' if descriptor['replay_verification'] else 'not run'}",
        f"- **dataset commitment**: `{descriptor['dataset_commitment']}`",
        "",
        "## Effective units",
        "",
        "| cell | scenario | effective_n | raw_attempts |",
        "|---|---|---|---|",
    ]
    for u in descriptor["units"]:
        lines.append(f"| `{u['cell_key']}` | `{u['scenario_id']}` | "
                     f"{u['effective_n']} | {u['raw_attempt_n']} |")
    lines += [
        "",
        "*Structural export (T0-A): no normative labels, no group-aware partitioning, no training. "
        "Every unit is retry-collapsed and effective-n counted through the audited metrics pipeline; "
        "held-out scenarios are refused by id AND scenario_hash.*",
        "",
    ]
    return "\n".join(lines)
