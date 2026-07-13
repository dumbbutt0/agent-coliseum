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

#: the integrated support-field status domain (profile §4.1). ``unavailable`` = we
#: do not have this (e.g. a historical run never recorded it); ``not_applicable`` =
#: this field has no meaning for this producer. Both carry NO value.
AVAILABILITY_STATUSES = ("available", "unavailable", "not_applicable")
_VALUELESS = ("unavailable", "not_applicable")


def available(value) -> dict:
    """An explicit available field carrying a JSON value."""
    validate_json_payload(value, "available.value")
    return {"status": "available", "value": value}


def unavailable() -> dict:
    """An explicit unavailable field — the value is genuinely absent, not blank."""
    return {"status": "unavailable"}


def not_applicable() -> dict:
    """An explicit not-applicable field — the field has no meaning here."""
    return {"status": "not_applicable"}


def validate_availability(field, where: str = "field",
                          nonempty: bool = False) -> dict:
    """Fail closed unless ``field`` is a well-formed availability wrapper: a dict
    whose ``status`` is one of AVAILABILITY_STATUSES, with ``value`` present iff
    ``available`` and absent for ``unavailable``/``not_applicable``. Rejects bare
    values / fabricated placeholders. When ``nonempty`` is set, an *available*
    value may not be an empty string / list / dict (so a blank string can never
    masquerade as a known identity — the empty-placeholder hole)."""
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
        if nonempty:
            v = field["value"]
            if (isinstance(v, (str, list, dict)) and len(v) == 0):
                raise ContentRecordError(
                    f"{where}: an available value may not be empty — use "
                    "unavailable()/not_applicable() rather than a blank placeholder")
    else:  # unavailable / not_applicable -> no value
        if set(field) - {"status"}:
            raise ContentRecordError(
                f"{where}: a {status} field must carry no value "
                f"(got {sorted(set(field) - {'status'})}) — never fabricate one")
    return field
