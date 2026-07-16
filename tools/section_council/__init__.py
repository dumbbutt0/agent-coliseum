"""Deterministic, non-authoritative Section Council validation primitives.

HSC-A deliberately contains no worker launcher and never mutates the Council.
It validates derived records that must still be submitted through the ordinary
Council source lifecycle.
"""

from .core import (
    HSCValidationError,
    compute_record_content_sha256,
    compute_record_id,
    parse_hsc_request_binding,
    validate_actual_change,
    validate_native_observation,
    validate_native_rel_path,
    validate_path,
    validate_predicted_change,
)
from .records import RECORD_TYPES, validate_record
from .store import (RecordStore, ValidationReport,
                    compute_bundle_staleness_inputs)
from .work import (
    ConflictResult,
    WorkAccess,
    classify_conflict,
    dependency_closure,
    dispatch_order,
    stale_work_items,
)

__all__ = [
    "ConflictResult",
    "HSCValidationError",
    "RECORD_TYPES",
    "RecordStore",
    "ValidationReport",
    "WorkAccess",
    "classify_conflict",
    "compute_bundle_staleness_inputs",
    "compute_record_content_sha256",
    "compute_record_id",
    "dependency_closure",
    "dispatch_order",
    "parse_hsc_request_binding",
    "stale_work_items",
    "validate_actual_change",
    "validate_native_observation",
    "validate_native_rel_path",
    "validate_path",
    "validate_predicted_change",
    "validate_record",
]
