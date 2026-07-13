"""Repo-discoverable resume-checkpoint locator (generic, tools/council). Resolves the
external checkpoint strictly FROM CONFIGURATION and validates it against the live chain
+ policy pin, failing closed for resume authority on every anomaly. Covers: successful
resolution, a relocated council root, a missing checkpoint, an inaccessible external
root (UNAVAILABLE != MISSING), a malformed checkpoint, a content-hash mismatch, a stale
chain-head binding, a policy-pin mismatch, and that a repo search finds only the stable
locator string, never a duplicate artifact."""
import json
import os

import pytest

from tests.council_util import (append, make_cfg, make_repo, make_root)
from tools.council import events, policy, resume_locator, storage
from tools.council.schemas import payload_hash

CONTROL_RID = "council-control"


def _boot(tmp_path):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    policy.write_initial_policy(root)
    _p, v1 = policy.load_policy(root)
    append(root, cfg, "POLICY_INITIALIZED", "human", CONTROL_RID, repo, "0" * 40,
           {"policy_hash": v1, "policy_file": storage.POLICY_FILE})
    return root, repo, head, cfg


def _write_checkpoint(root, *, chain_over=None, pin_over=None, hash_ok=True,
                      extra=None):
    """Write a resume_checkpoint.json bound to the CURRENT live chain + pin."""
    rep = events.verify_chain(root)
    chain = events.read_chain(root, verify=False)
    ph, pv = policy.effective_policy_pin(chain)
    data = {
        "checkpoint_schema_version": "resume-checkpoint.v1",
        "chain": {"head_hash": rep.head_hash, "length": rep.length,
                  "healthy": rep.healthy},
        "effective_policy": {"hash": ph, "version": pv, "is_code_defined": True},
    }
    if chain_over:
        data["chain"].update(chain_over)
    if pin_over:
        data["effective_policy"].update(pin_over)
    if extra:
        data.update(extra)
    data["checkpoint_hash"] = payload_hash(data)
    if not hash_ok:
        data["checkpoint_hash"] = "0" * 64
    path = os.path.join(root, resume_locator.CHECKPOINT_FILENAME)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return path, data


def test_successful_resolution(tmp_path):
    root, repo, head, cfg = _boot(tmp_path)
    _write_checkpoint(root)
    loc = resume_locator.locate_resume_checkpoint(cfg)
    assert loc.status == resume_locator.RESOLVED and loc.resume_authorized
    assert loc.council_root_accessible and loc.exists
    assert loc.locator == "council-root://resume_checkpoint.json"
    assert loc.policy_pin["match"] and loc.reasons == []


def test_relocated_council_root(tmp_path):
    """Two independent roots: the locator resolves purely from the cfg it is given,
    never a hard-coded path — each cfg finds only its own checkpoint."""
    root_a, _r, _h, cfg_a = _boot(tmp_path / "a")
    root_b, _r2, _h2, cfg_b = _boot(tmp_path / "b")
    _write_checkpoint(root_a)
    assert resume_locator.locate_resume_checkpoint(cfg_a).resume_authorized
    lb = resume_locator.locate_resume_checkpoint(cfg_b)
    assert not lb.exists and lb.status == resume_locator.CHECKPOINT_MISSING
    assert lb.resolved_path.startswith(root_b)


def test_missing_checkpoint(tmp_path):
    root, repo, head, cfg = _boot(tmp_path)
    loc = resume_locator.locate_resume_checkpoint(cfg)
    assert loc.council_root_accessible and not loc.exists
    assert loc.status == resume_locator.CHECKPOINT_MISSING
    assert not loc.resume_authorized


def test_inaccessible_root_is_unavailable_not_missing(tmp_path):
    """An auditor that cannot access the configured council root reports UNAVAILABLE,
    never 'no checkpoint exists' — and resume fails closed."""
    from tools.council import Config
    missing_root = str(tmp_path / "nonexistent-root")
    cfg = Config(council_root=missing_root, repo_roots=(missing_root,), role="claude")
    loc = resume_locator.locate_resume_checkpoint(cfg)
    assert loc.status == resume_locator.CHECKPOINT_ARTIFACT_UNAVAILABLE
    assert not loc.council_root_accessible and not loc.resume_authorized
    assert loc.status != resume_locator.CHECKPOINT_MISSING


def test_malformed_checkpoint(tmp_path):
    root, repo, head, cfg = _boot(tmp_path)
    path = os.path.join(root, resume_locator.CHECKPOINT_FILENAME)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{ not json ]")
    loc = resume_locator.locate_resume_checkpoint(cfg)
    assert loc.status == resume_locator.CHECKPOINT_MALFORMED and not loc.resume_authorized


def test_content_hash_mismatch(tmp_path):
    root, repo, head, cfg = _boot(tmp_path)
    _write_checkpoint(root, hash_ok=False)
    loc = resume_locator.locate_resume_checkpoint(cfg)
    assert loc.status == resume_locator.CONTENT_HASH_MISMATCH
    assert not loc.resume_authorized
    assert loc.recorded_content_hash != loc.computed_content_hash


def test_stale_chain_binding(tmp_path):
    root, repo, head, cfg = _boot(tmp_path)
    # bind to a head that is not the live chain's head at that length
    _write_checkpoint(root, chain_over={"head_hash": "f" * 64})
    loc = resume_locator.locate_resume_checkpoint(cfg)
    assert loc.status == resume_locator.STALE_CHAIN_BINDING
    assert not loc.resume_authorized


def test_checkpoint_behind_but_consistent_is_resolved(tmp_path):
    """A checkpoint bound to an earlier PREFIX of the live chain (more events appended
    since) is still consistent and RESOLVED — being behind is not being stale."""
    root, repo, head, cfg = _boot(tmp_path)
    _write_checkpoint(root)                       # bound to the current prefix
    append(root, cfg, "WATCHER_ERROR", "claude", "diag-1", repo, head,
           {"failure": False, "note": "n"})       # grow the live chain past it
    loc = resume_locator.locate_resume_checkpoint(cfg)
    assert loc.status == resume_locator.RESOLVED and loc.resume_authorized
    assert loc.live_chain["length"] > loc.checkpoint_chain["length"]


def test_policy_pin_mismatch(tmp_path):
    root, repo, head, cfg = _boot(tmp_path)
    _write_checkpoint(root, pin_over={"hash": "a" * 64, "version": 99})
    loc = resume_locator.locate_resume_checkpoint(cfg)
    assert loc.status == resume_locator.POLICY_PIN_MISMATCH
    assert not loc.resume_authorized and not loc.policy_pin["match"]


def test_missing_schema_version_is_malformed(tmp_path):
    """Strict JSON syntax is not enough — a checkpoint without the supported
    checkpoint_schema_version is CHECKPOINT_MALFORMED, never RESOLVED (audit 000777)."""
    root, repo, head, cfg = _boot(tmp_path)
    _write_checkpoint(root, extra={"checkpoint_schema_version": None})
    loc = resume_locator.locate_resume_checkpoint(cfg)
    assert loc.status == resume_locator.CHECKPOINT_MALFORMED
    assert not loc.resume_authorized


def test_wrong_schema_version_is_malformed(tmp_path):
    root, repo, head, cfg = _boot(tmp_path)
    _write_checkpoint(root, extra={"checkpoint_schema_version": "resume-checkpoint.v2"})
    loc = resume_locator.locate_resume_checkpoint(cfg)
    assert loc.status == resume_locator.CHECKPOINT_MALFORMED
    assert not loc.resume_authorized


def test_boolean_chain_length_is_malformed(tmp_path):
    """A JSON boolean (an int subclass) must never masquerade as chain.length
    (audit 000777)."""
    root, repo, head, cfg = _boot(tmp_path)
    _write_checkpoint(root, chain_over={"length": True})
    loc = resume_locator.locate_resume_checkpoint(cfg)
    assert loc.status == resume_locator.CHECKPOINT_MALFORMED
    assert not loc.resume_authorized


def test_boolean_policy_version_is_malformed(tmp_path):
    root, repo, head, cfg = _boot(tmp_path)
    _write_checkpoint(root, pin_over={"version": True})
    loc = resume_locator.locate_resume_checkpoint(cfg)
    assert loc.status == resume_locator.CHECKPOINT_MALFORMED
    assert not loc.resume_authorized


def test_malformed_schema_cli_exit_nonzero(tmp_path, monkeypatch):
    """The CLI must exit nonzero (resume refused) for a schema-malformed checkpoint."""
    from tools.council import cli
    root, repo, head, cfg = _boot(tmp_path)
    _write_checkpoint(root, chain_over={"length": True})
    monkeypatch.setenv("COUNCIL_ROOT", root)          # CLI resolves cfg from env
    monkeypatch.setenv("COUNCIL_REPO_ROOTS", repo)
    rc = cli.cmd_locate_resume_checkpoint(
        type("A", (), {"role": "claude", "json": True})())
    assert rc == 1


def test_valid_checkpoint_cli_exit_zero(tmp_path, monkeypatch):
    from tools.council import cli
    root, repo, head, cfg = _boot(tmp_path)
    _write_checkpoint(root)
    monkeypatch.setenv("COUNCIL_ROOT", root)
    monkeypatch.setenv("COUNCIL_REPO_ROOTS", repo)
    rc = cli.cmd_locate_resume_checkpoint(
        type("A", (), {"role": "claude", "json": True})())
    assert rc == 0


def test_repo_search_finds_only_the_stable_locator(tmp_path):
    """The repository carries only the stable locator STRING (in this generic module),
    never a duplicate checkpoint artifact. A repo-only search cannot discover the
    external file."""
    import tools.council as pkg
    repo_dir = os.path.dirname(os.path.dirname(os.path.dirname(pkg.__file__)))
    hits = []
    for dirpath, _dirs, files in os.walk(repo_dir):
        if ".git" in dirpath:
            continue
        for f in files:
            if f == resume_locator.CHECKPOINT_FILENAME:
                hits.append(os.path.join(dirpath, f))
    assert hits == [], f"a checkpoint artifact was duplicated into the repo: {hits}"
    # the locator URI is a relative convention, not an absolute machine path
    assert resume_locator.LOCATOR_URI.startswith("council-root://")
    assert not os.path.isabs(resume_locator.LOCATOR_URI)


def test_generic_module_imports_no_coliseum():
    src = resume_locator.__file__
    with open(src, encoding="utf-8") as fh:
        for line in fh:
            s = line.strip()
            if s.startswith("import ") or s.startswith("from "):
                assert "coliseum" not in s, f"locator imports project code: {s!r}"
