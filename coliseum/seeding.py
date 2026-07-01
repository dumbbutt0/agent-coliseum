"""Deterministic seeding — reproducibility pillar #1.

Seed every source of randomness so a run replays identically. numpy/torch are optional here so the
substrate runs before you've installed the ML stack (the smoke test needs neither).
"""
from __future__ import annotations
import os
import random


def seed_everything(seed: int) -> int:
    """Seed stdlib random + (if present) numpy + torch. Returns the seed for logging."""
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except ImportError:
        pass
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        try:
            torch.use_deterministic_algorithms(True, warn_only=True)
        except Exception:
            pass  # some ops lack deterministic kernels; warn_only keeps it non-fatal
    except ImportError:
        pass
    return seed
