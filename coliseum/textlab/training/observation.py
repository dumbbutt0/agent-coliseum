"""ObservationArtifact — a per-view observation (profile §4.2, §7; Appendix A).

ONE canonical preimage `{schema_version, view_kind, content}` for every producer;
`view_kind` participates in the literal `_domain` (`trs.observation.<view>.v1`) so
an actor artifact can never share an id with the privileged artifact of the same
decision. The actor artifact is built by an explicit ALLOWLIST projector, never
by copying the privileged content and removing known secret fields.
"""
from __future__ import annotations

from coliseum.textlab._content_record import ContentRecord, ContentRecordError

OBSERVATION_SCHEMA_VERSION = "1"
VIEW_KINDS = ("actor", "privileged")


class _ActorObservationArtifact(ContentRecord):
    __slots__ = ()
    DOMAIN = "trs.observation.actor.v1"
    ID_FIELD = "observation_id"


class _PrivilegedObservationArtifact(ContentRecord):
    __slots__ = ()
    DOMAIN = "trs.observation.privileged.v1"
    ID_FIELD = "observation_id"


_BY_VIEW = {"actor": _ActorObservationArtifact,
            "privileged": _PrivilegedObservationArtifact}


def observation_artifact(view_kind: str, content: dict) -> ContentRecord:
    """Build the ObservationArtifact for ``view_kind`` over ``content``.

    Unknown/omitted ``view_kind`` fails closed. ``content`` is the observation
    payload (a strict-JSON dict) — for a spatial producer it is the perception
    projection; for a vignette it is the actor-visible or privileged state."""
    if view_kind not in _BY_VIEW:
        raise ContentRecordError(
            f"view_kind must be one of {VIEW_KINDS}, got {view_kind!r}")
    if not isinstance(content, dict):
        raise ContentRecordError("observation content must be a dict")
    return _BY_VIEW[view_kind]({
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "view_kind": view_kind,
        "content": content,
    })


def project_by_allowlist(source: dict, allowlist) -> dict:
    """Build an actor-view content by an EXPLICIT allowlist of keys — the only
    permitted way to derive an actor observation. A key in the allowlist that is
    absent from ``source`` is simply not included; NO privileged key can appear
    because only allowlisted keys are ever read (this is not copy-minus-secrets).
    """
    if not isinstance(source, dict):
        raise ContentRecordError("source content must be a dict")
    allow = tuple(allowlist)
    if any(not isinstance(k, str) or not k for k in allow):
        raise ContentRecordError("allowlist entries must be non-empty strings")
    return {k: source[k] for k in allow if k in source}
