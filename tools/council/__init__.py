"""Council protocol — durable shared-index workflow between Claude and Codex.

Two CLI agents on one machine exchange structured events through the
filesystem at the council root (append-only, hash-chained events.jsonl is
authoritative; log.md is a human-readable mirror). The owner is the
man-in-the-middle: only a human-role command can open the experiment gate.

Stdlib-only by design.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

PROTOCOL_VERSION = "1.0"

DEFAULT_COUNCIL_ROOT = "/mnt/c/Users/dumbb/Docs/TheBrain/Claude-Wiki/council"
DEFAULT_REPO_ROOTS = ("/home/dummy/agent-coliseum",)


@dataclass(frozen=True)
class Config:
    council_root: str
    repo_roots: tuple
    role: str | None = None


def get_config(role: str | None = None) -> Config:
    """Resolve config from env at entry points only; library code takes
    explicit paths so tests never touch the real council root."""
    root = os.environ.get("COUNCIL_ROOT", DEFAULT_COUNCIL_ROOT)
    roots_env = os.environ.get("COUNCIL_REPO_ROOTS")
    repo_roots = tuple(p for p in roots_env.split(os.pathsep) if p) \
        if roots_env else DEFAULT_REPO_ROOTS
    return Config(council_root=root, repo_roots=repo_roots,
                  role=role or os.environ.get("COUNCIL_ROLE"))
