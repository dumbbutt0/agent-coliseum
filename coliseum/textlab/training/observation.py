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

#: field names that carry privileged (non-actor-observable) ground truth. An
#: actor-view artifact may NEVER contain any of these, at any depth. Extend this
#: registry as new privileged carriers are introduced.
PRIVILEGED_FIELD_NAMES = frozenset({
    "facts", "hidden_effects", "state_after", "hidden_research_objective",
    # spatial S2C privileged carriers (design §2, integrated 001154) — additive,
    # backstop-strengthening only: these are the spatial privileged inner-schema
    # keys and may never appear in ANY actor content.
    "authoritative_placements", "authoritative_lifecycle",
    "closure_visible_state_commitment",
})


def assert_no_privileged_leak(content, where: str = "actor content") -> None:
    """Fail closed if any registered privileged field name appears anywhere in an
    actor-view payload (direct or nested). This is a structural backstop so an
    actor artifact can never be content-addressed with privileged data even if a
    caller bypasses ``project_by_allowlist``."""
    if isinstance(content, dict):
        for k, v in content.items():
            if k in PRIVILEGED_FIELD_NAMES:
                raise ContentRecordError(
                    f"{where} contains privileged field {k!r} — actor observations "
                    "must be built by an explicit allowlist, never carry privileged data")
            assert_no_privileged_leak(v, f"{where}.{k}")
    elif isinstance(content, list):
        for i, v in enumerate(content):
            assert_no_privileged_leak(v, f"{where}[{i}]")


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
    if view_kind == "actor":
        # fail closed: an actor artifact may never carry a registered privileged
        # field, whether or not the caller used project_by_allowlist.
        assert_no_privileged_leak(content)
    return _BY_VIEW[view_kind]({
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "view_kind": view_kind,
        "content": content,
    })


def actor_observation_artifact(source_content: dict, allowlist) -> ContentRecord:
    """The blessed actor construction path: project ``source_content`` through an
    explicit ``allowlist`` (never copy-minus-secrets) and build the actor artifact.
    The result is guaranteed leak-free (only allowlisted keys are read, and the
    factory re-checks for privileged fields)."""
    return observation_artifact("actor", project_by_allowlist(source_content, allowlist))


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
