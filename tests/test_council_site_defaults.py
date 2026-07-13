"""Framework-extraction slice S1 — de-hardcode project defaults.

The generic council core must carry no baked-in deployment path; the sole
deployment-specific module is ``tools.council.site_defaults``. These tests pin
that (a) behavior is byte-identical to the pre-slice inline defaults, (b) env
still takes precedence, (c) an embedding app can inject defaults at runtime,
and (d) no generic core module hard-codes the deployment path any more.
"""
from __future__ import annotations

import ast
import os
import pathlib

import pytest

import tools.council as council
from tools.council import site_defaults


# The exact values the generic core carried inline before S1 (byte-identical
# behavior guarantee for the Coliseum deployment).
_LEGACY_COUNCIL_ROOT = "/mnt/c/Users/dumbb/Docs/TheBrain/Claude-Wiki/council"
_LEGACY_REPO_ROOTS = ("/home/dummy/agent-coliseum",)

_COUNCIL_ENV = ("COUNCIL_ROOT", "COUNCIL_REPO_ROOTS", "COUNCIL_ROLE")


@pytest.fixture(autouse=True)
def _clean_env_and_overrides(monkeypatch):
    """Every test runs with a clean env and a clean runtime-override table so
    ordering never leaks state."""
    for var in _COUNCIL_ENV:
        monkeypatch.delenv(var, raising=False)
    saved = dict(council._site_overrides)
    council._site_overrides.clear()
    try:
        yield
    finally:
        council._site_overrides.clear()
        council._site_overrides.update(saved)


def test_site_defaults_hold_the_legacy_values():
    assert site_defaults.SITE_COUNCIL_ROOT == _LEGACY_COUNCIL_ROOT
    assert site_defaults.SITE_REPO_ROOTS == _LEGACY_REPO_ROOTS


def test_no_env_resolves_to_site_defaults_byte_identical():
    cfg = council.get_config()
    assert cfg.council_root == _LEGACY_COUNCIL_ROOT
    assert cfg.repo_roots == _LEGACY_REPO_ROOTS
    assert cfg.role is None


def test_env_takes_precedence_over_site_default(monkeypatch):
    monkeypatch.setenv("COUNCIL_ROOT", "/tmp/other/council")
    monkeypatch.setenv("COUNCIL_REPO_ROOTS",
                       os.pathsep.join(["/tmp/repoA", "/tmp/repoB"]))
    cfg = council.get_config(role="claude")
    assert cfg.council_root == "/tmp/other/council"
    assert cfg.repo_roots == ("/tmp/repoA", "/tmp/repoB")
    assert cfg.role == "claude"


def test_repo_roots_env_drops_empty_segments(monkeypatch):
    monkeypatch.setenv("COUNCIL_REPO_ROOTS",
                       os.pathsep.join(["/tmp/repoA", "", "/tmp/repoB"]))
    assert council.get_config().repo_roots == ("/tmp/repoA", "/tmp/repoB")


def test_register_site_defaults_overrides_fallback():
    council.register_site_defaults(council_root="/srv/otherproj/council",
                                   repo_roots=["/srv/otherproj/repo"])
    cfg = council.get_config()
    assert cfg.council_root == "/srv/otherproj/council"
    assert cfg.repo_roots == ("/srv/otherproj/repo",)


def test_register_site_defaults_is_partial():
    council.register_site_defaults(council_root="/srv/only/root")
    cfg = council.get_config()
    assert cfg.council_root == "/srv/only/root"
    # repo_roots untouched -> still the site default
    assert cfg.repo_roots == _LEGACY_REPO_ROOTS


def test_env_still_wins_over_runtime_override(monkeypatch):
    council.register_site_defaults(council_root="/srv/registered/root")
    monkeypatch.setenv("COUNCIL_ROOT", "/env/wins/root")
    assert council.get_config().council_root == "/env/wins/root"


def test_generic_core_modules_carry_no_deployment_path():
    """The deployment path may appear ONLY in site_defaults.py. Every other
    module under tools/council must be free of the baked-in literal — the
    framework seam this slice establishes."""
    core = pathlib.Path(council.__file__).parent
    needles = ("/mnt/c/Users/dumbb", "/home/dummy/agent-coliseum")
    offenders = []
    for py in sorted(core.glob("*.py")):
        if py.name == "site_defaults.py":
            continue
        text = py.read_text(encoding="utf-8")
        # ignore matches inside comments/docstrings by scanning string+code
        # literally: the guarantee is the raw literal is absent from source.
        for needle in needles:
            if needle in text:
                offenders.append(f"{py.name}: {needle}")
    assert not offenders, f"deployment path leaked into generic core: {offenders}"


def test_site_defaults_module_is_import_light():
    """site_defaults must not import project code (keeps the seam one-way)."""
    src = pathlib.Path(site_defaults.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("coliseum"), alias.name
        elif isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("coliseum"), node.module
