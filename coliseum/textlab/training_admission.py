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

# Provenance a run MUST carry to be training-eligible (the KEY must be present and
# the value non-None / non-empty-string — a valid integer 0 or bool False counts as
# present; only absence / null / "" is missing). reportable + digest_status are
# required so the report never claims to evaluate a criterion whose evidence is absent.
REQUIRED_PROVENANCE = ("run_id", "scenario_id", "scenario_hash", "config_hash",
                       "seed", "code_version", "schema_version", "record_type",
                       "reportable", "digest_status")

# digest_status values that REJECT a run (an unverifiable model digest). "n/a"
# (no model, e.g. scripted agents) and "verified"/"ok" are accepted; anything else
# present-but-unrecognized fails closed rather than silently passing.
_REJECTING_DIGEST = frozenset({"unverified", "failed", "mismatch"})
_ACCEPTED_DIGEST = frozenset({"n/a", "verified", "ok"})


def _present(value):
    """A provenance value is present iff it is not None and not the empty string.
    A valid integer 0 or bool False IS present (truthiness must not conflate a
    zero-valued field with absence — audit 000664 F2)."""
    return value is not None and value != ""

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


def _decision(run_dir, run_id, scenario_id, reasons):
    return {"run_dir": os.path.basename(run_dir), "run_id": run_id,
            "scenario_id": scenario_id, "admitted": not reasons,
            "rejections": sorted(reasons)}


def admit_run(run_dir, *, held_out_ids=(), held_out_hashes=(),
              config_dir="configs/scenarios", exclusions=(), require_replay=False):
    """One training-eligibility decision for a single run dir. Fail-closed: an
    unreadable run.json, a JSON value that is not an object, missing provenance, or
    a replay error is a machine-readable REJECTION, never an exception (audit
    000664 F1/F2)."""
    path = os.path.join(run_dir, "run.json")
    try:
        run = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return _decision(run_dir, None, None,
                         [f"unreadable_run_json:{str(exc)[:60]}"])
    if not isinstance(run, dict):
        # valid JSON but not a run record (null / array / scalar) — fail closed
        return _decision(run_dir, None, None,
                         [f"run_json_not_object:{type(run).__name__}"])

    reasons = []
    run_id = run.get("run_id") if _present(run.get("run_id")) else None
    scenario_id = run.get("scenario_id")

    missing = [f for f in REQUIRED_PROVENANCE
               if f not in run or not _present(run[f])]
    if missing:
        reasons.append("provenance_incomplete:" + ",".join(sorted(missing)))
    if run.get("record_type") != "run":
        reasons.append(f"not_a_run_record:{run.get('record_type')}")
    # reportable / digest_status are required above; here we type/value-check the
    # PRESENT value (absence already produced provenance_incomplete, so we never
    # silently pass an absent criterion the report claims to evaluate).
    rep = run.get("reportable")
    if _present(rep):
        if not isinstance(rep, bool):
            reasons.append(f"reportable_not_bool:{type(rep).__name__}")
        elif rep is False:
            reasons.append("non_reportable")
    ds = run.get("digest_status")
    if _present(ds):
        if not isinstance(ds, str):
            reasons.append(f"digest_status_not_str:{type(ds).__name__}")
        elif ds in _REJECTING_DIGEST:
            reasons.append(f"model_digest_unverified:{ds}")
        elif ds not in _ACCEPTED_DIGEST:
            reasons.append(f"digest_status_unknown:{ds}")
    if scenario_id in set(held_out_ids) \
            or (_present(run.get("scenario_hash"))
                and run["scenario_hash"] in set(held_out_hashes)):
        reasons.append("held_out")
    if run_id in set(exclusions) or scenario_id in set(exclusions):
        reasons.append("preregistered_exclusion")
    if require_replay:
        try:
            ok, detail = verify_run_replay(run_dir, config_dir)
        except Exception as exc:   # an unverifiable replay is a rejection, not a crash
            ok, detail = False, f"replay_error:{str(exc)[:70]}"
        if not ok:
            reasons.append(f"replay_failed:{detail[:80]}")

    return _decision(run_dir, run_id, scenario_id, reasons)


def admit_runs(run_dirs, *, held_out_ids=(), held_out_hashes=(),
               config_dir="configs/scenarios", exclusions=(), require_replay=False):
    """A deterministic admission report over a set of run dirs: the admitted set,
    the rejected set with reasons, the criteria evaluated, and the §8 criteria
    deferred (with reasons). Content-addressable via admission_commitment."""
    decisions = [admit_run(d, held_out_ids=held_out_ids,
                           held_out_hashes=held_out_hashes, config_dir=config_dir,
                           exclusions=exclusions, require_replay=require_replay)
                 for d in sorted(run_dirs)]
    # Identity is the stable per-run run_id, NOT the directory basename (audit 000664
    # F3: two dirs with the same basename must not alias). A run_id shared by two
    # admitted decisions is an ambiguous identity — reject BOTH, fail closed.
    from collections import Counter
    admitted_ids = Counter(d["run_id"] for d in decisions
                           if d["admitted"] and d["run_id"] is not None)
    ambiguous = {rid for rid, n in admitted_ids.items() if n > 1}
    for d in decisions:
        if d["admitted"] and d["run_id"] in ambiguous:
            d["admitted"] = False
            d["rejections"] = sorted(d["rejections"] + ["ambiguous_run_id"])
    admitted = [d for d in decisions if d["admitted"]]
    rejected = [d for d in decisions if not d["admitted"]]
    report = {
        "admission_version": ADMISSION_VERSION,
        "evaluated_criteria": _evaluated_criteria(require_replay),
        "deferred_criteria": DEFERRED_CRITERIA,
        "replay_required": bool(require_replay),
        "admitted_count": len(admitted),
        "rejected_count": len(rejected),
        # admitted identities are run_ids (machine-independent, unambiguous)
        "admitted": sorted(d["run_id"] for d in admitted),
        "rejected": sorted(
            ({"run_dir": d["run_dir"], "run_id": d["run_id"],
              "rejections": d["rejections"]} for d in rejected),
            key=lambda r: (r["run_id"] or "", r["run_dir"])),
    }
    report["admission_commitment"] = admission_commitment(report)
    return report


def admission_commitment(report):
    """Content-addressed, domain-separated, version-stamped commitment over the
    admission report (excluding the commitment field itself)."""
    body = {k: v for k, v in report.items() if k != "admission_commitment"}
    return config_hash({"domain": ADMISSION_DOMAIN,
                        "admission_version": ADMISSION_VERSION, "report": body})
