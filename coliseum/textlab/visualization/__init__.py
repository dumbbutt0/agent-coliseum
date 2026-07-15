"""Read-only Agent Coliseum replay visualization.

The package consumes validated spatial evidence and emits perspective-scoped
presentation models. It never drives the scheduler, invokes a model, or writes
to a run directory.
"""

from .evidence import (EvidenceLimits, ReplayVerification, RunRoot,
                       ValidatedRun, load_validated_run, verify_replay)
from .view_model import build_view_model

__all__ = [
    "EvidenceLimits", "ReplayVerification", "RunRoot", "ValidatedRun",
    "build_view_model", "load_validated_run", "verify_replay",
]
