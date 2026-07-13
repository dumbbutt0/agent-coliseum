"""Council protocol — durable shared-index workflow between Claude and Codex.

Two CLI agents on one machine exchange structured events through the
filesystem at the council root (append-only, hash-chained events.jsonl is
authoritative; log.md is a human-readable mirror). The owner is the
man-in-the-middle: only a human-role command can open the experiment gate.

Stdlib-only by design.

Deployment defaults (the council root and repo roots) live in the single
``site_defaults`` module — the generic core carries no baked-in project path.
An embedding application may inject its own defaults at startup via
``register_site_defaults(...)``; environment variables still win over both.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from tools.council import site_defaults as _site

PROTOCOL_VERSION = "2.0"

# Runtime-registered deployment defaults (application startup). Empty until an
# embedding app calls register_site_defaults(); the site_defaults module then
# supplies the fallback. Env vars take precedence over everything below.
_site_overrides: dict = {}


def register_site_defaults(council_root: str | None = None,
                           repo_roots=None) -> None:
    """Inject deployment defaults at application startup without editing the
    package, so the generic core needs no project literal in its source. Only
    the arguments that are provided are overridden; ``COUNCIL_ROOT`` /
    ``COUNCIL_REPO_ROOTS`` environment variables still take precedence."""
    if council_root is not None:
        _site_overrides["council_root"] = council_root
    if repo_roots is not None:
        _site_overrides["repo_roots"] = tuple(repo_roots)


def _default_council_root() -> str:
    return _site_overrides.get("council_root", _site.SITE_COUNCIL_ROOT)


def _default_repo_roots() -> tuple:
    return _site_overrides.get("repo_roots", _site.SITE_REPO_ROOTS)


@dataclass(frozen=True)
class Config:
    council_root: str
    repo_roots: tuple
    role: str | None = None


def get_config(role: str | None = None) -> Config:
    """Resolve config from env at entry points only; library code takes
    explicit paths so tests never touch the real council root. Resolution
    order (unchanged): environment, then the registered/site default."""
    root = os.environ.get("COUNCIL_ROOT", _default_council_root())
    roots_env = os.environ.get("COUNCIL_REPO_ROOTS")
    repo_roots = tuple(p for p in roots_env.split(os.pathsep) if p) \
        if roots_env else _default_repo_roots()
    return Config(council_root=root, repo_roots=repo_roots,
                  role=role or os.environ.get("COUNCIL_ROLE"))
