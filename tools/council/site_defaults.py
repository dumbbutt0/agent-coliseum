"""The SOLE deployment-specific module in the council framework.

Every other module under ``tools/council`` is project-independent (the import
seam forbids importing project code into the core). This module is the one
place the generic core learns a *deployment's* default filesystem locations.

To reuse the framework in another deployment, either edit the two values here,
or — without editing the package — call
``tools.council.register_site_defaults(council_root=..., repo_roots=...)`` once
at application startup. Environment variables (``COUNCIL_ROOT`` /
``COUNCIL_REPO_ROOTS``) still take precedence over both, exactly as before.

NOTE: These are ordinary *default working locations*, not security anchors. The
identity enrollment anchor and the root-owned chain-head checkpoint are a
separate, deploy-time concern and are deliberately NOT configured here (see
``docs/first-gladiator/FRAMEWORK-EXTRACTION-BOUNDARY.md`` — an agent-writable
channel must never be able to redirect those).
"""
from __future__ import annotations

# Coliseum deployment defaults (the values the generic core carried inline
# before the framework-extraction S1 slice; behavior is byte-identical).
SITE_COUNCIL_ROOT = "/mnt/c/Users/dumbb/Docs/TheBrain/Claude-Wiki/council"
SITE_REPO_ROOTS = ("/home/dummy/agent-coliseum",)
