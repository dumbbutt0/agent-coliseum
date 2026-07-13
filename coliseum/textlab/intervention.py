"""Behavioral-calibration interventions for the Butterfly track — slice 1.

The Butterfly track is a bounded **behavioral-calibration** study (≤10 adaptive
episodes; see docs/first-gladiator/BUTTERFLY-ALIGNMENT-TRACK.md). This module is
the pure, additive foundation: the typed intervention, a versioned registry, and
the content-addressed identity algebra. It imports nothing project-specific
beyond the existing hashing substrate and modifies no existing code, so every
legacy regime hash is trivially unchanged.

BINDING NOMENCLATURE. An *intervention* is a controlled, pre-registered change
whose effect is measured as matched-trajectory divergence. This machinery
NEVER asserts a model is "aligned" or "properly aligned in N runs"; it measures
*behavioral calibration*. Names in this module are calibration-framed on purpose.

IDENTITY MODEL — three content-addressed hashes so calibration evidence can
neither silently fragment nor be forged:

* ``intervention_spec_hash``       — the registered DEFINITION (what the
                                     treatment *is*): id, schema version, class,
                                     kind, canonical spec.
* ``intervention_regime_hash``     — the stable TREATMENT CELL (which runs may
                                     pool). Composes a caller-supplied base
                                     regime id (schema.regime_hashes) with the
                                     treatment identity. Re-rolling a sampler
                                     seed does NOT enter this hash, so
                                     ``effective_n`` is not fragmented within a
                                     cell. A ``control`` (no intervention) forms
                                     its own cell, distinct from every
                                     registered intervention.
* ``intervention_realization_hash``— the RUN-LEVEL evidence, binding the regime
                                     cell + a pre-declared ``execution_instance_id``
                                     + the realized payload. Substituting the
                                     regime, the instance, or the payload changes
                                     it — a realized run cannot be reattributed.

CLASS SEMANTICS. ``policy`` interventions alter the underlying behavioral regime
(constitution / decoding / arbitration / interaction version) — the caller
reflects that by passing a *changed* base regime id. ``state`` interventions
(memory / context / ordering / framing / retrieval) alter only per-run prompt
evidence — the caller passes the *unchanged* base regime id. Either way the
treatment identity is folded into the regime cell so distinct treatments never
pool. Weight/adapter interventions are out of scope until M14/SC-8 (owner-gated).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

from coliseum.textlab.schema import canonical_json, config_hash

# Versioned so the identity semantics can never silently change (mirrors
# schema.REGIME_SCHEMA_VERSION discipline).
INTERVENTION_SCHEMA_VERSION = "1"

# `policy` changes the behavioral regime; `state` changes only prompt evidence.
INTERVENTION_CLASSES = ("state", "policy")

# The three levels of run identity, coarsest → finest.
IDENTITY_LEVELS = ("spec", "regime", "realization")

# Domain tags keep these hashes disjoint from every other config hash in the
# codebase (a spec hash can never collide with a regime or realization hash even
# on identical inner content).
_SPEC_DOMAIN = "intervention_spec.v1"
_REGIME_DOMAIN = "intervention_regime.v1"
_REALIZATION_DOMAIN = "intervention_realization.v1"

# The reserved treatment marker for a run that carries NO intervention. It is a
# real, distinct treatment cell — a control is not "the base regime": it is the
# base regime observed under the calibration harness with no intervention.
CONTROL_TREATMENT = "control"


class InterventionError(ValueError):
    """An intervention definition or identity request violates the schema."""


def _validate_json_payload(value, where: str) -> None:
    """Recursively require a strict JSON DATA-MODEL value: dict / list / str /
    finite-number / bool / None only, with **string-only object keys**.

    This closes the non-injective-input hole (audit 000814): ``json.dumps``
    coerces a non-string object key (e.g. int ``1``) to its string form, so
    ``{1: "x"}`` and ``{"1": "x"}`` would canonicalize identically and collapse
    to one content identity. Rejecting non-string keys (and tuples, which
    serialize like lists) makes the accepted-value -> canonical-JSON mapping
    injective, so distinct accepted definitions cannot share a hash."""
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, str):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InterventionError(f"{where}: non-finite float is not allowed")
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise InterventionError(
                    f"{where}: object keys must be strings, got "
                    f"{type(k).__name__} {k!r}")
            _validate_json_payload(v, f"{where}.{k}")
        return
    if isinstance(value, list):
        for i, v in enumerate(value):
            _validate_json_payload(v, f"{where}[{i}]")
        return
    # tuples/sets/bytes/custom objects are rejected: a tuple would serialize like
    # a list (another non-injective input), and non-JSON types have no stable id.
    raise InterventionError(
        f"{where}: unsupported type {type(value).__name__} "
        "(only JSON dict/list/str/number/bool/null with string keys)")


def _detached_canonical_spec(spec) -> dict:
    """Validate a spec dict and return a DETACHED canonical copy (round-tripped
    through canonical JSON) that shares no mutable state with the caller — so a
    later mutation of the caller's object can never change a registered
    definition's identity (audit 000814, blocker 1)."""
    if not isinstance(spec, dict):
        raise InterventionError("canonical_spec must be a dict")
    _validate_json_payload(spec, "canonical_spec")
    return json.loads(canonical_json(spec))


class Intervention:
    """A registered, content-addressed treatment definition.

    Immutable by construction: the scalar fields and a **detached, deeply
    validated** canonical spec are captured at ``__init__`` and exposed only
    through read-only properties (``canonical_spec`` returns a fresh copy per
    access). Neither the caller's original object nor a registry consumer can
    mutate a definition after it is created, so its identity is stable for life.
    """

    __slots__ = ("_intervention_id", "_cls", "_kind", "_schema_version",
                 "_spec_json")

    def __init__(self, intervention_id: str, cls: str, kind: str,
                 canonical_spec: dict,
                 schema_version: str = INTERVENTION_SCHEMA_VERSION):
        if not isinstance(intervention_id, str) or not intervention_id.strip():
            raise InterventionError("intervention_id must be a non-empty string")
        if cls not in INTERVENTION_CLASSES:
            raise InterventionError(
                f"class must be one of {INTERVENTION_CLASSES}, got {cls!r}")
        if not isinstance(kind, str) or not kind.strip():
            raise InterventionError("kind must be a non-empty string")
        if schema_version != INTERVENTION_SCHEMA_VERSION:
            raise InterventionError(
                f"unsupported schema_version {schema_version!r} "
                f"(want {INTERVENTION_SCHEMA_VERSION!r})")
        if intervention_id == CONTROL_TREATMENT:
            raise InterventionError(
                f"intervention_id {CONTROL_TREATMENT!r} is reserved for the "
                "no-intervention control and cannot name a registered intervention")
        # detached + deeply validated canonical form (blockers 1 and 2)
        detached = _detached_canonical_spec(canonical_spec)
        self._intervention_id = intervention_id
        self._cls = cls
        self._kind = kind
        self._schema_version = schema_version
        # store the canonical JSON string: the immutable identity substrate
        self._spec_json = canonical_json(detached)

    @property
    def intervention_id(self) -> str:
        return self._intervention_id

    @property
    def cls(self) -> str:
        return self._cls

    @property
    def kind(self) -> str:
        return self._kind

    @property
    def schema_version(self) -> str:
        return self._schema_version

    @property
    def canonical_spec(self) -> dict:
        """A FRESH copy of the canonical spec on every access — mutating the
        returned object never touches the registered definition."""
        return json.loads(self._spec_json)

    def __repr__(self) -> str:
        return (f"Intervention(id={self._intervention_id!r}, cls={self._cls!r}, "
                f"kind={self._kind!r})")


def validate_intervention(iv: "Intervention") -> "Intervention":
    """Fail closed on a malformed intervention. Construction already validates
    and freezes; this re-checks the (immutable) scalar fields for callers that
    accept an already-built Intervention, and returns it unchanged."""
    if not isinstance(iv, Intervention):
        raise InterventionError("not an Intervention instance")
    if not isinstance(iv.intervention_id, str) or not iv.intervention_id.strip():
        raise InterventionError("intervention_id must be a non-empty string")
    if iv.cls not in INTERVENTION_CLASSES:
        raise InterventionError(
            f"class must be one of {INTERVENTION_CLASSES}, got {iv.cls!r}")
    if not isinstance(iv.kind, str) or not iv.kind.strip():
        raise InterventionError("kind must be a non-empty string")
    if iv.schema_version != INTERVENTION_SCHEMA_VERSION:
        raise InterventionError(
            f"unsupported schema_version {iv.schema_version!r} "
            f"(want {INTERVENTION_SCHEMA_VERSION!r})")
    if iv.intervention_id == CONTROL_TREATMENT:
        raise InterventionError(
            f"intervention_id {CONTROL_TREATMENT!r} is reserved")
    return iv


def intervention_spec_hash(iv: "Intervention") -> str:
    """The registered DEFINITION hash — the identity of *what the treatment is*.
    Independent of any regime or run. Computed from the immutable, detached,
    string-key-only canonical spec captured at construction."""
    validate_intervention(iv)
    return config_hash({
        "_domain": _SPEC_DOMAIN,
        "intervention_id": iv.intervention_id,
        "schema_version": iv.schema_version,
        "class": iv.cls,
        "kind": iv.kind,
        "canonical_spec": iv.canonical_spec,
    })


def intervention_regime_hash(base_regime_id: str,
                             iv: "Intervention | None") -> str:
    """The stable TREATMENT-CELL hash — runs pool iff they share it.

    ``base_regime_id`` is a schema.regime_hashes comparison id (the caller passes
    a *changed* base for a ``policy`` intervention and the *unchanged* base for a
    ``state`` intervention). ``iv=None`` is the no-intervention control, which
    forms its own cell distinct from every registered intervention. The realized
    per-run payload and the sampler seed are deliberately absent, so re-rolling a
    seed within a treatment does not fragment ``effective_n``."""
    if not isinstance(base_regime_id, str) or not base_regime_id:
        raise InterventionError("base_regime_id must be a non-empty string")
    if iv is None:
        treatment = CONTROL_TREATMENT
    else:
        treatment = intervention_spec_hash(iv)
    return config_hash({
        "_domain": _REGIME_DOMAIN,
        "base_regime_id": base_regime_id,
        "treatment": treatment,
    })


def intervention_realization_hash(regime_hash: str,
                                  execution_instance_id: str,
                                  realized_payload: dict) -> str:
    """The RUN-LEVEL evidence hash, binding the treatment cell + a pre-declared
    ``execution_instance_id`` + the realized payload. Any substitution of the
    three changes it, so a realized run cannot be reattributed to another cell,
    instance, or payload after the fact."""
    if not isinstance(regime_hash, str) or not regime_hash:
        raise InterventionError("regime_hash must be a non-empty string")
    if not isinstance(execution_instance_id, str) or not execution_instance_id.strip():
        raise InterventionError("execution_instance_id must be a non-empty string")
    if not isinstance(realized_payload, dict):
        raise InterventionError("realized_payload must be a dict")
    # same injective-input rule as the spec (audit 000814, blocker 2): reject
    # non-string keys / non-JSON types so distinct payloads cannot collapse to
    # one realization identity.
    _validate_json_payload(realized_payload, "realized_payload")
    return config_hash({
        "_domain": _REALIZATION_DOMAIN,
        "intervention_regime_hash": regime_hash,
        "execution_instance_id": execution_instance_id,
        "realized_payload": realized_payload,
    })


@dataclass(frozen=True)
class RunIdentity:
    """The three-level identity of one realized calibration run.

    ``spec_hash`` is None for a control run (no intervention definition), while
    ``regime_hash`` and ``realization_hash`` are always present — a control is a
    real, poolable, replayable treatment cell."""
    regime_hash: str
    realization_hash: str
    spec_hash: str | None = None

    @property
    def is_control(self) -> bool:
        return self.spec_hash is None


def realized_run_identity(base_regime_id: str,
                          iv: "Intervention | None",
                          execution_instance_id: str,
                          realized_payload: dict) -> "RunIdentity":
    """Derive the full three-level identity for a realized run in one call."""
    regime = intervention_regime_hash(base_regime_id, iv)
    realization = intervention_realization_hash(
        regime, execution_instance_id, realized_payload)
    spec = None if iv is None else intervention_spec_hash(iv)
    return RunIdentity(regime_hash=regime, realization_hash=realization,
                       spec_hash=spec)


@dataclass
class InterventionRegistry:
    """A versioned, content-addressed registry of interventions.

    Ids are single-use: re-registering the same id with a *different* definition
    is refused (content drift), while re-registering the byte-identical
    definition is idempotent."""
    schema_version: str = INTERVENTION_SCHEMA_VERSION
    _by_id: dict = field(default_factory=dict)

    def register(self, iv: "Intervention") -> str:
        validate_intervention(iv)
        h = intervention_spec_hash(iv)
        existing = self._by_id.get(iv.intervention_id)
        if existing is not None and intervention_spec_hash(existing) != h:
            raise InterventionError(
                f"intervention_id {iv.intervention_id!r} already registered with "
                "a different definition — ids are single-use (content-addressed)")
        self._by_id[iv.intervention_id] = iv
        return h

    def get(self, intervention_id: str) -> "Intervention":
        if intervention_id not in self._by_id:
            raise InterventionError(f"unknown intervention_id {intervention_id!r}")
        return self._by_id[intervention_id]

    def ids(self) -> list:
        return sorted(self._by_id)

    def __contains__(self, intervention_id) -> bool:
        return intervention_id in self._by_id

    def __len__(self) -> int:
        return len(self._by_id)
