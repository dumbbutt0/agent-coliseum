"""Governance G4 — the Coliseum DRIVER (continue_acceptance). It drives (and resumes)
the `accepted` continuation for a resolved Class-C matter: read the claim registry,
invoke the G3 adapter, record the durable MATTER_ACCEPTED (chain first), then project
the mutation into the registry FILE. Idempotent and crash-resumable; INERT under v3;
the generic core never imports this driver."""
import hashlib
import os

import yaml

from tests.test_council_governance_g4 import (MATTER, _ratify, _resolve, env)  # noqa: F401
from coliseum.textlab import continuation
from coliseum.textlab.continuation import continue_acceptance
from coliseum.textlab.schema import canonical_json
from tools.council import events, policy


def _write_registries(tmp_path, *, claim_state="replicated"):
    claims_path = str(tmp_path / "claims.yaml")
    exp_path = str(tmp_path / "experiments.yaml")
    claims = {"registry_version": "1", "claims": [
        {"claim_id": "c1", "state": claim_state, "statement": "X holds",
         "evidence": ["exp-aa", "exp-bb"]}]}
    exp = {"registry_version": "1", "experiments": [
        {"experiment_id": "exp-aa", "status": "complete"},
        {"experiment_id": "exp-bb", "status": "complete"}]}
    with open(claims_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(claims, fh)
    with open(exp_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(exp, fh)
    return claims_path, exp_path


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _resolved(env):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    _resolve(root, repo, head, cfg, resolution="accept")
    return root, repo, head, cfg


def test_applies_records_and_projects(env, tmp_path):
    root, repo, head, cfg = _resolved(env)
    claims_path, exp_path = _write_registries(tmp_path)
    res = continue_acceptance(root, cfg, claims_path, exp_path, MATTER, "c1",
                              repo, head)
    assert res["applied"] and res["accepted_event_id"]
    # file projected: c1 is accepted, bound to the resolution
    reg = _load(claims_path)
    assert reg["claims"][0]["state"] == "accepted"
    assert reg["claims"][0]["finding_audit"]
    # durable record on-chain, bound to the projected content
    s = policy.continuation_status(root, cfg, MATTER)
    assert s.already_accepted
    assert s.result_content_hash == hashlib.sha256(
        canonical_json(reg).encode()).hexdigest()


def test_idempotent_second_call_is_noop(env, tmp_path):
    root, repo, head, cfg = _resolved(env)
    claims_path, exp_path = _write_registries(tmp_path)
    continue_acceptance(root, cfg, claims_path, exp_path, MATTER, "c1", repo, head)
    before = _load(claims_path)
    n_before = events.verify_chain(root).length
    res = continue_acceptance(root, cfg, claims_path, exp_path, MATTER, "c1",
                              repo, head)
    assert not res["applied"] and res["already_recorded"]
    assert _load(claims_path) == before                 # file unchanged
    assert events.verify_chain(root).length == n_before  # no second record


def test_resume_reprojects_when_file_behind(env, tmp_path):
    """Crash between the chain record and the file write: the durable MATTER_ACCEPTED
    exists but the registry file is still `replicated`. Resume re-derives the identical
    post-state, checks it against the recorded hash, and re-projects the file WITHOUT
    recording a second time."""
    root, repo, head, cfg = _resolved(env)
    claims_path, exp_path = _write_registries(tmp_path)
    continue_acceptance(root, cfg, claims_path, exp_path, MATTER, "c1", repo, head)
    n_after = events.verify_chain(root).length
    # simulate the crash: revert ONLY the file projection to pre-accept
    reverted = {"registry_version": "1", "claims": [
        {"claim_id": "c1", "state": "replicated", "statement": "X holds",
         "evidence": ["exp-aa", "exp-bb"]}]}
    with open(claims_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(reverted, fh)
    res = continue_acceptance(root, cfg, claims_path, exp_path, MATTER, "c1",
                              repo, head)
    assert res["applied"] and res["reprojected"]
    assert _load(claims_path)["claims"][0]["state"] == "accepted"
    assert events.verify_chain(root).length == n_after   # still no second record


def test_resume_refuses_divergent_projection(env, tmp_path):
    """If the re-derived post-state would NOT match the recorded content hash (the
    registry drifted), the driver refuses to project a divergent registry."""
    root, repo, head, cfg = _resolved(env)
    claims_path, exp_path = _write_registries(tmp_path)
    continue_acceptance(root, cfg, claims_path, exp_path, MATTER, "c1", repo, head)
    # crash-revert AND tamper: a different statement -> different post-state hash
    drifted = {"registry_version": "1", "claims": [
        {"claim_id": "c1", "state": "replicated", "statement": "TAMPERED",
         "evidence": ["exp-aa", "exp-bb"]}]}
    with open(claims_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(drifted, fh)
    res = continue_acceptance(root, cfg, claims_path, exp_path, MATTER, "c1",
                              repo, head)
    assert not res["applied"] and "hash mismatch" in res["reason"]
    assert _load(claims_path)["claims"][0]["state"] == "replicated"  # left untouched


def test_inert_under_v3_applies_nothing(env, tmp_path):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 3)      # no resolution possible; governance inert
    claims_path, exp_path = _write_registries(tmp_path)
    before = _load(claims_path)
    res = continue_acceptance(root, cfg, claims_path, exp_path, MATTER, "c1",
                              repo, head)
    assert not res["applied"] and "not authorized" in res["reason"]
    assert _load(claims_path) == before


def test_refuses_when_resolution_not_accept(env, tmp_path):
    root, repo, head, cfg = env
    _ratify(root, repo, head, cfg, 4)
    _resolve(root, repo, head, cfg, resolution="reject")
    claims_path, exp_path = _write_registries(tmp_path)
    res = continue_acceptance(root, cfg, claims_path, exp_path, MATTER, "c1",
                              repo, head)
    assert not res["applied"] and "not an accept" in res["reason"]
    assert _load(claims_path)["claims"][0]["state"] == "replicated"


def test_refuses_and_leaves_registry_when_claim_not_promotable(env, tmp_path):
    root, repo, head, cfg = _resolved(env)
    claims_path, exp_path = _write_registries(tmp_path, claim_state="speculation")
    before = _load(claims_path)
    res = continue_acceptance(root, cfg, claims_path, exp_path, MATTER, "c1",
                              repo, head)
    assert not res["applied"] and "adapter refused" in res["reason"]
    assert _load(claims_path) == before                  # nothing recorded or written
    assert not policy.continuation_status(root, cfg, MATTER).already_accepted


def test_generic_core_does_not_import_the_driver():
    """The seam is one-directional: no tools/council module may IMPORT the Coliseum
    claim registry or this driver (a policy-id string that merely contains the word is
    fine — only import statements are the coupling that matters)."""
    import tools.council as pkg
    pkg_dir = os.path.dirname(pkg.__file__)
    for fname in os.listdir(pkg_dir):
        if not fname.endswith(".py"):
            continue
        with open(os.path.join(pkg_dir, fname), encoding="utf-8") as fh:
            for line in fh:
                s = line.strip()
                if s.startswith("import ") or s.startswith("from "):
                    assert "coliseum" not in s, f"{fname}: generic core imports {s!r}"
