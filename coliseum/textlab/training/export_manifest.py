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


_PROJECTION_SCALAR_KEYS = ("source_evidence", "behavior_policy_spec",
                           "trajectory_manifest")
_PROJECTION_LIST_KEYS = ("decision_records", "actor_decision_records",
                         "actor_observations", "privileged_observations",
                         "legal_action_sets")


def assert_projection_coherent(projection: dict) -> None:
    """Fail closed unless ``projection`` is an internally-consistent DAG rooted at its
    SourceEvidenceBinding — no independently-swappable record. Requires: all lists
    present and equal in length; the TrajectoryManifest rooted at source_evidence and
    listing exactly the decision-record ids in order; and, per position, the privileged
    DecisionRecord and the actor ActorDecisionRecord referencing the SAME behavior
    policy, actor/privileged observations, legal-action set, and sequence position as
    the projection's own records. Prevents a chimera (e.g. a transplanted
    source_evidence) from riding alongside unrelated included records."""
    for k in _PROJECTION_SCALAR_KEYS + _PROJECTION_LIST_KEYS:
        if k not in projection:
            raise ContentRecordError(f"projection is missing '{k}'")
    se = projection["source_evidence"]
    policy = projection["behavior_policy_spec"]
    manifest = projection["trajectory_manifest"]
    decisions = projection["decision_records"]
    n = len(decisions)
    for k in _PROJECTION_LIST_KEYS:
        if len(projection[k]) != n:
            raise ContentRecordError(
                f"projection list '{k}' has length {len(projection[k])}, expected {n}")
    if n == 0:
        raise ContentRecordError("projection has no decisions")
    # the manifest must be rooted at THIS source evidence and list THESE decisions.
    if manifest.content["run_identity"] != se.id:
        raise ContentRecordError(
            "trajectory_manifest.run_identity does not equal source_evidence.id "
            "(the manifest is not rooted at this run's evidence)")
    if manifest.content["ordered_decision_ids"] != [d.id for d in decisions]:
        raise ContentRecordError(
            "trajectory_manifest.ordered_decision_ids do not match the projection's "
            "decision_records (in order)")
    for i in range(n):
        dr = decisions[i].content
        adr = projection["actor_decision_records"][i].content
        actor_id = projection["actor_observations"][i].id
        priv_id = projection["privileged_observations"][i].id
        legal_id = projection["legal_action_sets"][i].id
        if dr["sequence_position"] != i or adr["sequence_position"] != i:
            raise ContentRecordError(f"record at position {i} has a mismatched sequence_position")
        if (dr["behavior_policy_spec_hash"] != policy.id
                or adr["behavior_policy_spec_hash"] != policy.id):
            raise ContentRecordError(f"position {i} references a foreign behavior_policy_spec")
        if dr["actor_observation_hash"] != actor_id or adr["actor_observation_hash"] != actor_id:
            raise ContentRecordError(f"position {i} references a foreign actor observation")
        if dr["privileged_observation_hash"] != priv_id:
            raise ContentRecordError(f"position {i} references a foreign privileged observation")
        if dr["legal_action_set_hash"] != legal_id or adr["legal_action_set_hash"] != legal_id:
            raise ContentRecordError(f"position {i} references a foreign legal_action_set")


def _assert_projection_matches_run_dir(projection: dict, run_dir: str) -> str:
    """Fail closed unless ``projection`` is EXACTLY the projection of ``run_dir``.

    The projection is re-derived from run_dir's authenticated bytes and every record
    id (scalar and per-position) must match. This defeats not only a direct cross-run
    call but any partial transplant — swapping in another run's authentic
    source_evidence, trajectory manifest, or a single decision record all diverge from
    the re-derived truth. Returns the bound source run_id."""
    # local import avoids an import cycle at module load.
    from coliseum.textlab.training.trajectory_projection import project_trajectory
    truth = project_trajectory(run_dir)
    # internal coherence first (precise error), then exact identity to the truth.
    assert_projection_coherent(projection)
    for k in _PROJECTION_SCALAR_KEYS:
        if k not in projection or projection[k].id != truth[k].id:
            raise ContentRecordError(
                f"projection '{k}' does not match the projection re-derived from "
                "run_dir — a forged/transplanted export binding is refused")
    for k in _PROJECTION_LIST_KEYS:
        if [r.id for r in projection[k]] != [r.id for r in truth[k]]:
            raise ContentRecordError(
                f"projection list '{k}' does not match the projection re-derived from "
                "run_dir — a forged/transplanted export binding is refused")
    return truth["source_evidence"].content["run_id"]


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

    # BIND: the supplied projection must be EXACTLY the projection of THIS run_dir
    # (every record re-derived from the authenticated bytes must match). Refuses a
    # forged cross-run export — including a partial source_evidence transplant —
    # before any record is built.
    bound_run_id = _assert_projection_matches_run_dir(projection, run_dir)

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
