"""T0-A training-data admission gate (§8 of the training-annex, BLOCKER 3, first part).

Section 8 rejects a run from training if: provenance is incomplete · replay fails · the data
partition is hidden evaluation (held-out) · a preregistered exclusion is violated · a retry is
counted as an independent example · the model digest is unverified · the record is non-reportable
· (for interventions/environments) intervention realization / environment trace / random-stream
registration is unverifiable · the scenario/model license does not permit training use.

This gate makes that decision EXPLICIT and auditable: one admit/reject record per run, with
machine-readable rejection reasons, reusing the audited primitives (never reimplementing them):

  - byte-identical replay              -> sweep.verify_run_replay
  - held-out refusal (id AND hash)     -> mirrors the dataset_export / registry held-out gate
  - retry-as-independent               -> structurally prevented upstream: admission consumes
                                          effective units after metrics retry-collapse; raw
                                          attempts are never admitted as independent examples

**Honesty over coverage.** Several §8 criteria require evidence the current single-agent vignette
corpus does not carry (intervention realization, environment trace / realization hash, random-stream
registration, training-use license). Those are recorded as **deferred** — never silently passed —
so an admission report never over-claims. They activate when the evidence exists. No labels, no
training: this is structural T0-A machinery.
"""
from __future__ import annotations

import json
import os

from .schema import config_hash
from .sweep import verify_run_replay

ADMISSION_VERSION = "1"
ADMISSION_DOMAIN = "dataset:training_admission:v1"

# Provenance a run MUST carry to be training-eligible (present and non-empty).
REQUIRED_PROVENANCE = ("run_id", "scenario_id", "scenario_hash", "config_hash",
                       "seed", "code_version", "schema_version", "record_type")

# digest_status values that REJECT a run (an unverifiable model digest). "n/a"
# (no model, e.g. scripted agents) and "verified"/"ok" are accepted.
_REJECTING_DIGEST = frozenset({"unverified", "failed", "mismatch"})

# §8 criteria that require evidence absent from single-agent vignette runs. Recorded
# as DEFERRED (not passed) so admission never over-claims; each activates when its
# evidence exists.
DEFERRED_CRITERIA = {
    "intervention_realization": "requires intervention execution evidence "
    "(execution_instance_id + realization hash); absent in non-intervention runs",
    "environment_trace": "requires an environment/multi-agent trace + "
    "environment_realization_hash + reconstructable random draws; absent in "
    "single-agent vignettes",
    "random_stream_registration": "requires a registered, correctly-bound stochastic "
    "stream; evaluated only for stochastic/environment runs",
    "license_permits_training": "requires a scenario/model license field + a "
    "training-use license policy; not yet attached to the corpus",
}


def _evaluated_criteria(require_replay):
    base = ["provenance_complete", "record_is_run", "reportable",
            "model_digest_verified", "held_out_excluded", "preregistered_exclusion"]
    return base + (["replay_verified"] if require_replay else [])


def admit_run(run_dir, *, held_out_ids=(), held_out_hashes=(),
              config_dir="configs/scenarios", exclusions=(), require_replay=False):
    """One training-eligibility decision for a single run dir. Fail-closed: any
    unreadable run.json or missing provenance is a rejection, not an exception."""
    reasons = []
    path = os.path.join(run_dir, "run.json")
    try:
        run = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"run_dir": os.path.basename(run_dir), "run_id": None,
                "scenario_id": None, "admitted": False,
                "rejections": [f"unreadable_run_json:{str(exc)[:60]}"]}

    missing = [f for f in REQUIRED_PROVENANCE if not run.get(f)]
    if missing:
        reasons.append("provenance_incomplete:" + ",".join(missing))
    if run.get("record_type") != "run":
        reasons.append(f"not_a_run_record:{run.get('record_type')}")
    if run.get("reportable") is False:
        reasons.append("non_reportable")
    if run.get("digest_status") in _REJECTING_DIGEST:
        reasons.append(f"model_digest_unverified:{run.get('digest_status')}")
    if run.get("scenario_id") in set(held_out_ids) \
            or run.get("scenario_hash", "") in set(held_out_hashes):
        reasons.append("held_out")
    if run.get("run_id") in set(exclusions) \
            or run.get("scenario_id") in set(exclusions):
        reasons.append("preregistered_exclusion")
    if require_replay:
        try:
            ok, detail = verify_run_replay(run_dir, config_dir)
        except Exception as exc:   # an unverifiable replay is a rejection, not a crash
            ok, detail = False, f"replay_error:{str(exc)[:70]}"
        if not ok:
            reasons.append(f"replay_failed:{detail[:80]}")

    return {"run_dir": os.path.basename(run_dir), "run_id": run.get("run_id"),
            "scenario_id": run.get("scenario_id"), "admitted": not reasons,
            "rejections": sorted(reasons)}


def admit_runs(run_dirs, *, held_out_ids=(), held_out_hashes=(),
               config_dir="configs/scenarios", exclusions=(), require_replay=False):
    """A deterministic admission report over a set of run dirs: the admitted set,
    the rejected set with reasons, the criteria evaluated, and the §8 criteria
    deferred (with reasons). Content-addressable via admission_commitment."""
    decisions = [admit_run(d, held_out_ids=held_out_ids,
                           held_out_hashes=held_out_hashes, config_dir=config_dir,
                           exclusions=exclusions, require_replay=require_replay)
                 for d in sorted(run_dirs)]
    admitted = [d for d in decisions if d["admitted"]]
    rejected = [d for d in decisions if not d["admitted"]]
    report = {
        "admission_version": ADMISSION_VERSION,
        "evaluated_criteria": _evaluated_criteria(require_replay),
        "deferred_criteria": DEFERRED_CRITERIA,
        "replay_required": bool(require_replay),
        "admitted_count": len(admitted),
        "rejected_count": len(rejected),
        "admitted": [d["run_dir"] for d in admitted],
        "rejected": [{"run_dir": d["run_dir"], "run_id": d["run_id"],
                      "rejections": d["rejections"]} for d in rejected],
    }
    report["admission_commitment"] = admission_commitment(report)
    return report


def admission_commitment(report):
    """Content-addressed, domain-separated, version-stamped commitment over the
    admission report (excluding the commitment field itself)."""
    body = {k: v for k, v in report.items() if k != "admission_commitment"}
    return config_hash({"domain": ADMISSION_DOMAIN,
                        "admission_version": ADMISSION_VERSION, "report": body})
