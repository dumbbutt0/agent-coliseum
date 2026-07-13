"""Termination taxonomy (profile §6) — never a boolean.

Termination and truncation are distinct; an infrastructure failure is never
coded as an environmental/behavioral outcome. Unknown values fail closed.
"""
from __future__ import annotations

from coliseum.textlab._content_record import ContentRecordError

TERMINATION_KINDS = (
    "continuing",
    "natural_terminal",
    "success_terminal",
    "failure_terminal",
    "time_limit_truncation",
    "externally_imposed_truncation",
    "invalid_action_termination",
    "parse_failure_termination",
    "infrastructure_failure",
    "excluded_episode",
    "quarantined_evidence",
)


def validate_termination_kind(kind: str) -> str:
    if kind not in TERMINATION_KINDS:
        raise ContentRecordError(
            f"termination_kind must be one of {TERMINATION_KINDS}, got {kind!r}")
    return kind
