"""Explicit availability wrapper — the no-fabrication discipline (profile §5, §14).

A field that may be absent from historical evidence (tokenizer identity, action
scores, memory-state ref, …) is recorded as an explicit typed status, NEVER as an
empty string or an invented value:

    {"status": "available", "value": <json>}   or   {"status": "unavailable"}

This makes "we do not have this" a first-class, unambiguous, content-addressed
fact rather than a silent gap a downstream consumer could misread as real data.
"""
from __future__ import annotations

from coliseum.textlab._content_record import (ContentRecordError,
                                              validate_json_payload)

AVAILABILITY_STATUSES = ("available", "unavailable")


def available(value) -> dict:
    """An explicit available field carrying a JSON value."""
    validate_json_payload(value, "available.value")
    return {"status": "available", "value": value}


def unavailable() -> dict:
    """An explicit unavailable field — the value is genuinely absent, not blank."""
    return {"status": "unavailable"}


def validate_availability(field, where: str = "field") -> dict:
    """Fail closed unless ``field`` is a well-formed availability wrapper: a dict
    whose ``status`` is one of AVAILABILITY_STATUSES, with ``value`` present iff
    available and absent iff unavailable. Rejects bare values / empty strings /
    fabricated placeholders."""
    if not isinstance(field, dict):
        raise ContentRecordError(
            f"{where} must be an availability dict {{'status': ...}}, got "
            f"{type(field).__name__}")
    status = field.get("status")
    if status not in AVAILABILITY_STATUSES:
        raise ContentRecordError(
            f"{where}.status must be one of {AVAILABILITY_STATUSES}, got {status!r}")
    if status == "available":
        if "value" not in field:
            raise ContentRecordError(f"{where}: available field must carry a value")
        if set(field) - {"status", "value"}:
            raise ContentRecordError(f"{where}: unexpected keys {sorted(set(field) - {'status', 'value'})}")
        validate_json_payload(field["value"], f"{where}.value")
    else:  # unavailable
        if set(field) - {"status"}:
            raise ContentRecordError(
                f"{where}: an unavailable field must carry no value "
                f"(got {sorted(set(field) - {'status'})}) — never fabricate one")
    return field
