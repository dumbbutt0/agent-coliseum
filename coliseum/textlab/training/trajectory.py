"""TrajectoryManifest + SourceEvidenceBinding (profile §4.5, Appendix A).

The episode-level manifest binds the ordered decision-record sequence and the
exact source evidence. `run_identity` is a content-addressed `SourceEvidenceBinding`
id that binds the exact `run.json` + `decisions.jsonl` content hashes (P1-S4:
"bind every derived record to the exact source run.json and decisions.jsonl
hashes"), so the source provenance roots the whole trajectory DAG without adding a
manifest key beyond Appendix A. Ordering is preserved exactly; wall-clock is never
identity material.
"""
from __future__ import annotations

from coliseum.textlab._content_record import ContentRecord, ContentRecordError

SOURCE_EVIDENCE_SCHEMA_VERSION = "1"
TRAJECTORY_MANIFEST_SCHEMA_VERSION = "1"

_SOURCE_EVIDENCE_KEYS = frozenset({
    "schema_version", "run_id", "run_json_content_hash",
    "decisions_jsonl_content_hash",
})
_TRAJECTORY_MANIFEST_KEYS = frozenset({
    "schema_version", "run_identity", "world_line_id", "ordered_decision_ids",
    "episode_boundaries",
})


def _require_hex(name: str, value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ContentRecordError(f"{name} must be a non-empty string")


class SourceEvidenceBinding(ContentRecord):
    """Content-addresses the exact source-run evidence: the run id plus the
    content hashes of run.json and decisions.jsonl. `run_id` is descriptive; the
    two hashes are the exact provenance anchor."""
    __slots__ = ()
    DOMAIN = "trs.source_evidence.v1"
    ID_FIELD = "source_evidence_id"

    def __init__(self, run_id: str, run_json_content_hash: str,
                 decisions_jsonl_content_hash: str):
        _require_hex("run_id", run_id)
        _require_hex("run_json_content_hash", run_json_content_hash)
        _require_hex("decisions_jsonl_content_hash", decisions_jsonl_content_hash)
        super().__init__({
            "schema_version": SOURCE_EVIDENCE_SCHEMA_VERSION,
            "run_id": run_id,
            "run_json_content_hash": run_json_content_hash,
            "decisions_jsonl_content_hash": decisions_jsonl_content_hash,
        })


class TrajectoryManifest(ContentRecord):
    __slots__ = ()
    DOMAIN = "trs.trajectory_manifest.v1"
    ID_FIELD = "trajectory_manifest_id"

    def __init__(self, run_identity: str, ordered_decision_ids: list,
                 episode_boundaries: dict, world_line_id=None):
        # run_identity is the SourceEvidenceBinding id (content-addressed run id
        # that binds the exact source hashes).
        _require_hex("run_identity", run_identity)
        if not isinstance(ordered_decision_ids, list) or not ordered_decision_ids:
            raise ContentRecordError("ordered_decision_ids must be a non-empty list")
        if any(not isinstance(d, str) or not d for d in ordered_decision_ids):
            raise ContentRecordError("decision ids must be non-empty strings")
        if len(set(ordered_decision_ids)) != len(ordered_decision_ids):
            raise ContentRecordError("decision ids must be unique (no duplicate positions)")
        if not isinstance(episode_boundaries, dict):
            raise ContentRecordError("episode_boundaries must be a dict")
        if world_line_id is not None and (
                not isinstance(world_line_id, str) or not world_line_id):
            raise ContentRecordError("world_line_id must be null or a non-empty string")
        super().__init__({
            "schema_version": TRAJECTORY_MANIFEST_SCHEMA_VERSION,
            "run_identity": run_identity,
            "world_line_id": world_line_id,
            "ordered_decision_ids": list(ordered_decision_ids),
            "episode_boundaries": episode_boundaries,
        })

    def sequence_integrity(self) -> dict:
        """Report structural integrity of what the manifest itself owns: the ordered
        decision-id list and the episode boundaries. Reports duplicate decision ids
        and whether ``episode_boundaries.episode_starts`` is a well-formed, in-range,
        strictly-ascending, gap-free-from-zero start list. (Cross-record reference
        validation over the full DecisionRecord set is a projector-level check —
        the manifest does not hold the referenced records.)"""
        ids = self.content["ordered_decision_ids"]
        eb = self.content["episode_boundaries"]
        starts = eb.get("episode_starts") if isinstance(eb, dict) else None
        boundaries_valid = (
            isinstance(starts, list)
            and all(isinstance(s, int) and not isinstance(s, bool) for s in starts)
            and len(set(starts)) == len(starts)          # no duplicate episode starts
            and sorted(starts) == starts                  # ascending
            and all(0 <= s < len(ids) for s in starts)    # in range
            and (len(ids) == 0 or (starts and starts[0] == 0)))  # first episode at 0
        return {
            "length": len(ids),
            "duplicates": len(ids) != len(set(ids)),
            "episode_boundaries_valid": bool(boundaries_valid),
        }
