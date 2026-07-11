"""Shared builders for the council test suites. NOT a test module.

Every helper works against throwaway tmp_path roots and scratch git repos —
the real council directory is never touched by tests."""
from __future__ import annotations

import os
import subprocess

from tools.council import Config, events, identity, storage

TEST_COMMAND = "python3 -m pytest tests/ -q"

# H1 test identity: tiny chain + cheap KDF so token minting is fast; the
# math under test is identical to production parameters
TEST_PASSPHRASE = "test-owner-passphrase"
TEST_ENROLLMENT_TOKEN = "test-enrollment-secret"
TEST_CHAIN_LENGTH = 64
TEST_ITERATIONS = 1_000


def make_root(tmp_path) -> str:
    root = str(tmp_path / "council")
    os.makedirs(root, exist_ok=True)
    storage.ensure_layout(root)
    with open(os.path.join(root, "log.md"), "w", encoding="utf-8") as fh:
        fh.write("STATUS: active\n\n# test council log\n")
    # H1: control.json is the authoritative run state (fail-closed when
    # absent) and human events require identity tokens — every test root
    # gets a FULLY bootstrapped identity (pin event #1 + verifier),
    # matching production: an unpinned verifier grants no authority.
    verifier = identity.prepare_identity(TEST_PASSPHRASE,
                                         chain_length=TEST_CHAIN_LENGTH,
                                         iterations=TEST_ITERATIONS)
    boot_cfg = Config(council_root=root, repo_roots=(root,), role="human")
    events.append_event(
        root, boot_cfg, "HUMAN_IDENTITY_INITIALIZED", "human",
        "council-identity", root, "0" * 40,
        {"schema_version": "identity.v1", "tip_hex": verifier["tip_hex"],
         "counter": verifier["counter"],
         "chain_length": verifier["chain_length"],
         "salt_hex": verifier["salt_hex"],
         "pbkdf2_iterations": verifier["pbkdf2_iterations"]},
        enrollment_token=TEST_ENROLLMENT_TOKEN)
    identity.install_verifier(root, verifier)
    # activate through the REAL bound path: a token-burned STATUS_CHANGED
    # event, then the control record derived from it (an unbound "active"
    # file would fail closed — cycle-2 blocker 2)
    core = {"status": "active", "paused_roles": [], "reason": "test root"}
    token = human_token(root, "STATUS_CHANGED", "council-control",
                        "0" * 40, core)
    event = events.append_event(root, boot_cfg, "STATUS_CHANGED", "human",
                                "council-control", root, "0" * 40,
                                dict(core, human_token=token))
    storage.write_control(root, "active", [], "test root",
                          event["event_id"])
    return root


def human_token(root: str, event_type: str, request_id: str,
                target_commit: str, payload_core: dict) -> dict:
    """A bound, spendable one-time token for the NEXT counter value."""
    verifier = identity.read_verifier(root)
    token = identity.compute_token(TEST_PASSPHRASE, verifier)
    token["binds"] = identity.binding_hash(event_type, request_id,
                                           target_commit, payload_core)
    return token


def make_repo(tmp_path, name: str = "repo") -> tuple:
    """(repo_path, head_commit) — a one-commit scratch git repo."""
    repo = str(tmp_path / name)
    os.makedirs(repo, exist_ok=True)
    subprocess.run(["git", "-C", repo, "init", "-q"], check=True)
    with open(os.path.join(repo, "f.txt"), "w", encoding="utf-8") as fh:
        fh.write("content\n")
    subprocess.run(["git", "-C", repo, "add", "f.txt"], check=True)
    subprocess.run(["git", "-C", repo, "-c", "user.email=t@t",
                    "-c", "user.name=t", "commit", "-qm", "init"],
                   check=True)
    head = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                          capture_output=True, text=True,
                          check=True).stdout.strip()
    return repo, head


def make_cfg(repo: str, root: str, role: str = "claude") -> Config:
    return Config(council_root=root, repo_roots=(repo,), role=role)


def make_request(repo: str, head: str, request_id: str = "test-req-001",
                 **overrides) -> dict:
    request = {
        "request_id": request_id,
        "protocol_version": "1.0",
        "repository": repo,
        "target_commit": head,
        "require_clean_tree": True,
        "expected_test_command": TEST_COMMAND,
        "expected_test_count": 147,
        "scope": ["scope item"],
        "questions": ["question?"],
        "allowed_actions": ["read source", "run allowlisted tests"],
        "forbidden_actions": ["destructive_tools", "cloud_apis",
                              "website_automation", "weight_training"],
        "requested_verdicts": ["AUDIT_BLOCKED", "AUDIT_GO",
                               "AUDIT_GO_WITH_CONDITIONS"],
        "live_experiment_allowed": False,
        "human_approval_required": True,
        "originating_blocked_commit": head,
        "blockers_addressed": ["blocker one"],
    }
    request.update(overrides)
    return request


def make_verdict(head: str, request_id: str = "test-req-001",
                 verdict: str = "GO", **overrides) -> dict:
    body = {
        "request_id": request_id,
        "audited_commit": head,
        "audit_mode": "narrow",
        "working_tree_clean": True,
        "tests_observed": 147,
        "verdict": verdict,
        "summary": "test verdict",
        "blockers": [],
        "conditions": [],
        "findings": [],
        "commands_run": [TEST_COMMAND],
        "timestamp_utc": storage.utc_now(),
    }
    body.update(overrides)
    return body


def make_finding(**overrides) -> dict:
    """A canonical structured finding (the strict schema requires every
    finding to be an object with the ten protocol fields)."""
    finding = {
        "claim": "the probed property holds",
        "evidence": "probe transcript",
        "failure_mode": "none reproduced",
        "file": "tools/council/schemas.py",
        "line_range": "1-1",
        "minimum_fix": "none",
        "minimum_regression": "retain the probe",
        "reproduced": False,
        "severity": "INFO",
        "blocks_requested_action": False,
    }
    finding.update(overrides)
    return finding


def make_autonomy_block(**overrides) -> dict:
    block = {
        "experiment_class": "sandbox_local",
        "experiment_config_hash": "a" * 64,
        "data_sources": ["synthetic"],
        "model_digests": {"model-a": "sha256:" + "b" * 64},
        "limits": {"max_compute_minutes": 60, "max_wall_minutes": 60,
                   "max_storage_mb": 512, "max_retries_per_unit": 2,
                   "max_scenarios": 10},
        "offline_replay_supported": True,
    }
    block.update(overrides)
    return block


_EVENT_TO_VERDICT = {"AUDIT_BLOCKED": "BLOCKED", "AUDIT_GO": "GO",
                     "AUDIT_GO_WITH_CONDITIONS": "GO_WITH_CONDITIONS",
                     "RESULT_APPROVED": "APPROVED",
                     "RESULT_BLOCKED": "BLOCKED"}


def append(root: str, cfg: Config, event_type: str, sender: str,
           request_id: str, repo: str, commit: str, payload=None) -> dict:
    """Raw append helper. Verdict events must carry a schema-valid nested
    verdict, and human-authority events a spendable one-time token (H1) —
    both autofilled when a test passes no explicit payload/token, so
    drive-style sequences stay terse. Tests probing either boundary pass
    their own (invalid) payloads explicitly."""
    if not payload and event_type in _EVENT_TO_VERDICT:
        from tools.council.schemas import compute_verdict_payload_hash
        payload = make_verdict(commit, request_id,
                               verdict=_EVENT_TO_VERDICT[event_type])
        payload["verdict_payload_hash"] = \
            compute_verdict_payload_hash(payload)
    from tools.council.schemas import HUMAN_TOKEN_REQUIRED_EVENT_TYPES
    payload = dict(payload or {})
    if event_type in HUMAN_TOKEN_REQUIRED_EVENT_TYPES \
            and sender == "human" and "human_token" not in payload \
            and identity.read_verifier(root) is not None:
        payload["human_token"] = human_token(root, event_type, request_id,
                                             commit, payload)
    return events.append_event(root, cfg, event_type, sender, request_id,
                               repo, commit, payload)


def drive_to_claimed(root, cfg, repo, head, request_id="test-req-001",
                     **request_overrides) -> dict:
    """BUILD_STARTED..AUDIT_CLAIMED via the real publish/claim paths."""
    from tools.council import codex_watch, publish
    append(root, cfg, "BUILD_STARTED", "claude", request_id, repo, head)
    append(root, cfg, "BUILD_READY", "claude", request_id, repo, head)
    request = make_request(repo, head, request_id, **request_overrides)
    publish.publish_request(root, cfg, request, reaudit=False)
    _event, lock = codex_watch.claim(root, cfg, request_id)
    return {"request": request, "lock": lock}
