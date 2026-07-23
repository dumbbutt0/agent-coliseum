"""Experiment-specific identity adapters for generic Council admission.

Council owns request/event integrity and must not import a Coliseum driver or
claim registry.  The autonomy layer is the directional seam that resolves an
experiment's verified bundle into the small identity record Council compares.
"""
from __future__ import annotations


def verified_experiment_identity(registry_path: str,
                                 experiment_id: str) -> dict:
    from coliseum.textlab.registry import load_verified_bundle

    bundle = load_verified_bundle(registry_path, experiment_id)
    return {
        "design_hash": bundle.design_hash,
        "model_digests": bundle.planned_design.get("model_digests"),
        "planned_runs": bundle.planned_design.get("expected_run_count"),
    }

