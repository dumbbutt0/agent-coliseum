"""The end-to-end training-readiness pipeline (profile §4-§7; P1-S6).

A single entry point that turns ONE completed modern vignette run into a governed,
view-scoped training export: project the trajectory (P1-S4), then build the governed
export manifest (P1-S5). Everything is DERIVED, deterministic, and read-only over the
source run; no runner/schema/registry/primary-evidence write, no labels, no training.

The heavy lifting (and every fail-closed gate) lives in the composed modules — this is
a thin, auditable seam so callers get one call and one coherent result bundle.
"""
from __future__ import annotations

from coliseum.textlab.dataset_export import DEFAULT_SPLITS
from coliseum.textlab.training.export_manifest import build_training_export
from coliseum.textlab.training.trajectory_projection import project_trajectory


def export_training_data_from_run(run_dir: str, *, view_kind: str,
                                  registry_path: str,
                                  held_out_scenarios=None, held_out_hashes=None,
                                  config_dir: str = "configs/scenarios",
                                  verify: bool = False, splits=DEFAULT_SPLITS) -> dict:
    """Project ``run_dir`` and build its governed ``view_kind`` training export.

    Returns ``{"projection", "manifest", "descriptor"}``. The export step re-derives
    the projection from the authenticated run bytes and requires an exact match, so
    the returned projection provably belongs to ``run_dir``. Fails closed on every
    P1-S4/P1-S5 gate (non-modern/non-completed/mis-ordered run; unknown view_kind;
    missing registry; held-out scenario; forged projection)."""
    projection = project_trajectory(run_dir)
    manifest, descriptor = build_training_export(
        projection, view_kind=view_kind, run_dir=run_dir,
        registry_path=registry_path, held_out_scenarios=held_out_scenarios,
        held_out_hashes=held_out_hashes, config_dir=config_dir,
        verify=verify, splits=splits)
    return {"projection": projection, "manifest": manifest, "descriptor": descriptor}
