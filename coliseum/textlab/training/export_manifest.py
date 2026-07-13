"""DatasetExportManifest — the governed view+partition export gate (profile §7).

A training export is never implicit. This manifest wraps the existing, hardened
run-level exporter (:func:`dataset_export.build_dataset`) ADDITIVELY and binds the
view-filtered training records to it. Two gates are mandatory and fail closed:

* **view_kind** — every export must declare ``actor`` or ``privileged``. An actor
  export carries ONLY actor-safe records (policy / manifest / source-evidence /
  actor observations / legal-action sets / actor decisions); the privileged
  observations and privileged DecisionRecords are physically excluded, and every
  included record is re-checked leak-free. A privileged export (research / eval) is
  a superset and is never mislabeled as actor.
* **partition** — the export MUST be partitioned. ``build_dataset`` is invoked with
  ``partition=True`` (so a missing ``registry_path`` fails closed), which folds the
  deterministic, dataset-version-bound GROUP-AWARE split (§8) into the commitment and
  refuses any held-out scenario (by id OR scenario_hash) and any sibling straddle.

Determinism: same source run + same view + same held-out set + same registry ->
same ``build_dataset`` commitment and same ordered record ids -> same manifest id.
No labels, no training, no weight surface — this is the governed DATA export record.
"""
from __future__ import annotations

import hashlib
import json
import os

from coliseum.textlab._content_record import ContentRecord, ContentRecordError
from coliseum.textlab.dataset_export import DEFAULT_SPLITS, build_dataset
from coliseum.textlab.training.observation import assert_no_privileged_leak
from coliseum.textlab.training.trajectory import SourceEvidenceBinding

DATASET_EXPORT_MANIFEST_SCHEMA_VERSION = "1"
VIEW_KINDS = ("actor", "privileged")

# projection keys whose records are actor-safe (may appear in an actor export).
_ACTOR_SAFE_KEYS = ("source_evidence", "behavior_policy_spec", "trajectory_manifest",
                    "actor_observations", "legal_action_sets", "actor_decision_records")
# projection keys that carry the privileged view — NEVER in an actor export.
_PRIVILEGED_KEYS = ("privileged_observations", "decision_records")


def _sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _recompute_source_evidence(run_dir: str) -> SourceEvidenceBinding:
    """Rebuild the SourceEvidenceBinding directly from run_dir's exact bytes — the
    ground-truth identity the supplied projection must match."""
    with open(os.path.join(run_dir, "run.json"), "rb") as fh:
        run_json = json.loads(fh.read())
    return SourceEvidenceBinding(
        run_id=run_json["run_id"],
        run_json_content_hash=_sha256_file(os.path.join(run_dir, "run.json")),
        decisions_jsonl_content_hash=_sha256_file(
            os.path.join(run_dir, "decisions.jsonl")))


def _assert_projection_binds_run_dir(projection: dict, run_dir: str) -> str:
    """Fail closed unless ``projection`` was genuinely derived from ``run_dir``: the
    projection's SourceEvidenceBinding must equal the binding recomputed from
    run_dir's exact run.json + decisions.jsonl bytes. Prevents a forged export that
    binds run A's records/source-evidence to run B's scenario/partition/commitment.
    Returns the bound source run_id."""
    supplied = projection.get("source_evidence")
    if supplied is None:
        raise ContentRecordError("projection is missing its source_evidence binding")
    truth = _recompute_source_evidence(run_dir)
    if supplied.id != truth.id:
        raise ContentRecordError(
            "projection is not derived from run_dir (source-evidence mismatch): the "
            "supplied projection's run.json/decisions.jsonl identity does not match "
            "run_dir's exact bytes — a cross-run export binding is refused")
    return truth.content["run_id"]


def _ordered_records(projection: dict, view_kind: str) -> list:
    """Collect the projection's records for ``view_kind`` in a deterministic order.

    Actor: the three trajectory-level records, then per decision position the actor
    observation, legal-action set, and actor decision. Privileged: the same, plus the
    privileged observation and privileged DecisionRecord interleaved per position."""
    records = [projection["source_evidence"], projection["behavior_policy_spec"],
               projection["trajectory_manifest"]]
    n = len(projection["decision_records"])
    for i in range(n):
        records.append(projection["actor_observations"][i])
        records.append(projection["legal_action_sets"][i])
        records.append(projection["actor_decision_records"][i])
        if view_kind == "privileged":
            records.append(projection["privileged_observations"][i])
            records.append(projection["decision_records"][i])
    return records


class DatasetExportManifest(ContentRecord):
    __slots__ = ()
    DOMAIN = "trs.dataset_export_manifest.v1"
    ID_FIELD = "dataset_export_manifest_id"

    def __init__(self, view_kind: str, split: str, dataset_commitment: str,
                 source_evidence_id: str, scenario_id: str,
                 included_record_ids: list):
        if view_kind not in VIEW_KINDS:
            raise ContentRecordError(
                f"view_kind must be one of {VIEW_KINDS}, got {view_kind!r}")
        for name, val in (("split", split),
                          ("dataset_commitment", dataset_commitment),
                          ("source_evidence_id", source_evidence_id),
                          ("scenario_id", scenario_id)):
            if not isinstance(val, str) or not val:
                raise ContentRecordError(f"{name} must be a non-empty string")
        if not isinstance(included_record_ids, list) or not included_record_ids:
            raise ContentRecordError("included_record_ids must be a non-empty list")
        if any(not isinstance(r, str) or not r for r in included_record_ids):
            raise ContentRecordError("included_record_ids must be non-empty strings")
        if len(set(included_record_ids)) != len(included_record_ids):
            raise ContentRecordError("included_record_ids must be unique")
        super().__init__({
            "schema_version": DATASET_EXPORT_MANIFEST_SCHEMA_VERSION,
            "view_kind": view_kind,
            "split": split,
            "dataset_commitment": dataset_commitment,
            "source_evidence_id": source_evidence_id,
            "scenario_id": scenario_id,
            "included_record_ids": list(included_record_ids),
        })


def build_training_export(projection: dict, *, view_kind: str, run_dir: str,
                          registry_path: str,
                          held_out_scenarios=None, held_out_hashes=None,
                          config_dir: str = "configs/scenarios",
                          verify: bool = False, splits=DEFAULT_SPLITS):
    """Build the governed :class:`DatasetExportManifest` for ``projection`` over its
    source ``run_dir``. Returns ``(manifest, descriptor)`` where ``descriptor`` is the
    underlying ``build_dataset`` output (commitment + partition + held-out attestation
    + training-admission report).

    Fails closed on: an unknown/missing ``view_kind``; a missing ``registry_path``
    (partition is mandatory); a held-out scenario; a partition leakage straddle; or —
    for an actor export — any privileged content in an included record."""
    if view_kind not in VIEW_KINDS:
        raise ContentRecordError(
            f"view_kind must be explicitly one of {VIEW_KINDS}, got {view_kind!r} "
            "(an export may not omit its view)")

    # BIND: the supplied projection must be the projection of THIS run_dir (exact
    # source bytes). Refuses a forged cross-run export before any record is built.
    bound_run_id = _assert_projection_binds_run_dir(projection, run_dir)

    # governed run-level export: partition REQUIRED (missing registry_path fails
    # closed inside build_dataset), held-out refusal + §8 group-aware split +
    # training-admission gate + deterministic dataset_commitment.
    descriptor = build_dataset(
        [run_dir], partition=True, registry_path=registry_path,
        held_out_scenarios=held_out_scenarios, held_out_hashes=held_out_hashes,
        training_admission=True, verify=verify, config_dir=config_dir, splits=splits)

    units = descriptor["units"]
    # the dataset descriptor must describe the SAME run the projection is bound to.
    descriptor_run_ids = {rid for u in units for rid in u.get("run_ids", [])}
    if bound_run_id not in descriptor_run_ids:
        raise ContentRecordError(
            f"bound source run_id {bound_run_id!r} is absent from the dataset "
            f"descriptor's units {sorted(descriptor_run_ids)} — export refused")
    scenario_ids = {u["scenario_id"] for u in units}
    splits_seen = {u["split"] for u in units}
    if len(scenario_ids) != 1:
        raise ContentRecordError(
            f"single-run export must resolve to exactly one scenario, got {sorted(scenario_ids)}")
    if len(splits_seen) != 1:
        raise ContentRecordError(
            f"single-run export must resolve to exactly one split, got {sorted(splits_seen)}")
    scenario_id = next(iter(scenario_ids))
    split = next(iter(splits_seen))

    records = _ordered_records(projection, view_kind)
    if view_kind == "actor":
        # defence in depth: no actor-export record may carry any privileged field.
        for rec in records:
            assert_no_privileged_leak(rec.content, "actor export record")

    manifest = DatasetExportManifest(
        view_kind=view_kind,
        split=split,
        dataset_commitment=descriptor["dataset_commitment"],
        source_evidence_id=projection["source_evidence"].id,
        scenario_id=scenario_id,
        included_record_ids=[r.id for r in records],
    )
    return manifest, descriptor
