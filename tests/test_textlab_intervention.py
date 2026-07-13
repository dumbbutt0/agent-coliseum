"""Butterfly slice 1 — intervention type, registry, and identity algebra.

Pins the load-bearing invariants: distinct treatments never pool, a control is
distinct from every intervention, re-rolling a seed within a treatment does not
fragment the cell, the realization hash binds regime+instance+payload, and the
three domain-separated hashes are mutually disjoint. Pure additive module — no
existing code is touched, so legacy regime hashes cannot change.
"""
from __future__ import annotations

import pytest

from coliseum.textlab.intervention import (
    CONTROL_TREATMENT, INTERVENTION_CLASSES, INTERVENTION_SCHEMA_VERSION,
    Intervention, InterventionError, InterventionRegistry, RunIdentity,
    intervention_realization_hash, intervention_regime_hash,
    intervention_spec_hash, realized_run_identity, validate_intervention)


def _iv(iid="iv-framing-a", cls="state", kind="framing", spec=None):
    return Intervention(intervention_id=iid, cls=cls, kind=kind,
                        canonical_spec={"strength": 1, "note": "x"} if spec is None else spec)


# ----------------------------------------------------------------- validation
def test_valid_intervention_round_trips():
    iv = _iv()
    assert iv.schema_version == INTERVENTION_SCHEMA_VERSION
    assert iv.cls in INTERVENTION_CLASSES
    assert validate_intervention(iv) is iv


@pytest.mark.parametrize("bad", [
    dict(iid=""), dict(iid="   "), dict(cls="weight"), dict(cls=""),
    dict(kind=""), dict(iid=CONTROL_TREATMENT),
])
def test_malformed_intervention_rejected(bad):
    with pytest.raises(InterventionError):
        _iv(**bad)


def test_non_dict_spec_rejected():
    with pytest.raises(InterventionError):
        Intervention("iv-x", "state", "framing", canonical_spec=["not", "a", "dict"])


def test_unsupported_schema_version_rejected():
    with pytest.raises(InterventionError):
        Intervention("iv-x", "state", "framing", {"a": 1}, schema_version="9")


# ---------------------------------------------------------------- spec hash
def test_spec_hash_is_key_order_independent():
    a = _iv(spec={"a": 1, "b": 2})
    b = _iv(spec={"b": 2, "a": 1})
    assert intervention_spec_hash(a) == intervention_spec_hash(b)


def test_spec_hash_changes_with_class_kind_and_spec():
    base = _iv()
    h = intervention_spec_hash(base)
    assert intervention_spec_hash(_iv(cls="policy")) != h
    assert intervention_spec_hash(_iv(kind="ordering")) != h
    assert intervention_spec_hash(_iv(spec={"strength": 2, "note": "x"})) != h
    assert intervention_spec_hash(_iv(iid="iv-other")) != h


# --------------------------------------------------------------- regime cell
def test_control_regime_distinct_from_any_intervention():
    base = "0" * 64
    ctrl = intervention_regime_hash(base, None)
    treated = intervention_regime_hash(base, _iv())
    assert ctrl != treated
    # control marker is stable and does not depend on any intervention
    assert intervention_regime_hash(base, None) == ctrl


def test_distinct_interventions_do_not_pool():
    base = "a" * 64
    h1 = intervention_regime_hash(base, _iv(iid="iv-1"))
    h2 = intervention_regime_hash(base, _iv(iid="iv-2"))
    assert h1 != h2


def test_same_treatment_same_cell_regardless_of_caller_repeats():
    # Re-deriving the same treatment on the same base yields the same cell — the
    # sampler seed and realized payload are NOT in this hash, so effective_n is
    # not fragmented by re-rolling seeds within a treatment.
    base = "b" * 64
    iv = _iv()
    assert intervention_regime_hash(base, iv) == intervention_regime_hash(base, iv)


def test_regime_hash_tracks_base_regime():
    iv = _iv()
    assert intervention_regime_hash("b" * 64, iv) != intervention_regime_hash("c" * 64, iv)


def test_regime_hash_rejects_empty_base():
    with pytest.raises(InterventionError):
        intervention_regime_hash("", _iv())


# ------------------------------------------------------------ realization hash
def test_realization_binds_regime_instance_and_payload():
    regime = intervention_regime_hash("d" * 64, _iv())
    base = intervention_realization_hash(regime, "exec-1", {"final": "refuse"})
    # substitute each of the three inputs -> hash must change
    assert intervention_realization_hash(regime, "exec-2", {"final": "refuse"}) != base
    assert intervention_realization_hash(regime, "exec-1", {"final": "obey"}) != base
    other_regime = intervention_regime_hash("e" * 64, _iv())
    assert intervention_realization_hash(other_regime, "exec-1", {"final": "refuse"}) != base


def test_realization_rejects_blank_instance():
    regime = intervention_regime_hash("d" * 64, _iv())
    with pytest.raises(InterventionError):
        intervention_realization_hash(regime, "  ", {"final": "refuse"})


# ------------------------------------------------------- domain separation
def test_three_hashes_are_domain_disjoint():
    # Even with structurally-identical inner content the three domains never
    # collide, because each is tagged with its own domain string.
    iv = _iv()
    spec = intervention_spec_hash(iv)
    regime = intervention_regime_hash("f" * 64, iv)
    realization = intervention_realization_hash(regime, "exec-1", {})
    assert len({spec, regime, realization}) == 3


# --------------------------------------------------------- run identity object
def test_realized_run_identity_control_vs_treated():
    base = "1" * 64
    treated = realized_run_identity(base, _iv(), "exec-1", {"final": "refuse"})
    control = realized_run_identity(base, None, "exec-1", {"final": "refuse"})
    assert isinstance(treated, RunIdentity)
    assert treated.spec_hash is not None and not treated.is_control
    assert control.spec_hash is None and control.is_control
    assert treated.regime_hash != control.regime_hash
    assert treated.realization_hash != control.realization_hash


# -------------------------------------------------------------- registry
def test_registry_register_get_and_idempotent():
    reg = InterventionRegistry()
    iv = _iv()
    h = reg.register(iv)
    assert reg.register(iv) == h            # byte-identical re-register is idempotent
    assert iv.intervention_id in reg
    assert reg.get(iv.intervention_id) is iv
    assert reg.ids() == [iv.intervention_id]
    assert len(reg) == 1


def test_registry_refuses_id_reuse_with_drift():
    reg = InterventionRegistry()
    reg.register(_iv(iid="iv-dup", spec={"strength": 1}))
    with pytest.raises(InterventionError):
        reg.register(_iv(iid="iv-dup", spec={"strength": 2}))


def test_registry_unknown_id():
    with pytest.raises(InterventionError):
        InterventionRegistry().get("nope")


# ------------------------------------------------- naming / terminology guard
def test_public_names_and_reserved_values_are_not_alignment_framed():
    # Binding terminology: the machinery measures behavioral CALIBRATION and never
    # asserts a model is 'aligned'. The concrete risk the design flags is
    # alignment-framed *identifiers / ids* (which propagate into registries,
    # metrics, and claims), not prose that explicitly disavows the term. Guard the
    # public API surface + the reserved id-bearing constants.
    import coliseum.textlab.intervention as mod
    public = [n for n in dir(mod) if not n.startswith("_")]
    for n in public:
        assert "align" not in n.lower(), f"alignment-framed public name: {n}"
    for reserved in (mod.CONTROL_TREATMENT, *mod.INTERVENTION_CLASSES,
                     *mod.IDENTITY_LEVELS):
        assert "align" not in reserved.lower(), reserved
    # positive: the module IS calibration-framed (its docstring says so)
    assert "calibrat" in (mod.__doc__ or "").lower()
