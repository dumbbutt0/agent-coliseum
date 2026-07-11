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
        # H3 auditor-judgment fields — required on RESULT verdicts (the
        # runner-pinned bindings are injected by submit_verdict); harmless
        # extras on source verdicts
        "replay_result": "replayed_ok",
        "counts": {"scenarios_run": 1, "validations_passed": 1,
                   "validations_failed": 0},
        "conclusion_scope": "test evidence approved",
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


def _inject_test_bindings(root, verdict, rid, commit, result_audit) -> None:
    """Populate H3 verdict bindings from the chain (mirrors
    codex_watch._inject_bindings) so drive-style test appends produce
    valid, cross-checkable verdicts. Falls back to synthetic values when
    no publication event exists yet (negative/edge tests)."""
    from tools.council import state_machine
    chain = events.read_chain(root)
    proj = state_machine.project(chain)
    src_pub = pub = None
    for e in chain:
        if e["request_id"] != rid:
            continue
        if e["event_type"] in ("AUDIT_REQUESTED", "READY_FOR_REAUDIT"):
            src_pub = e
        if result_audit and e["event_type"] == "RESULT_AUDIT_REQUESTED":
            pub = e
    if not result_audit:
        pub = src_pub
    verdict["auditor"] = "codex"
    verdict["audit_cycle"] = proj.get(rid, {}).get("audit_cycles") or 1
    verdict["request_payload_hash"] = (
        (src_pub["payload"].get("request_payload_hash") or "0" * 64)
        if src_pub else "0" * 64)
    verdict["publication_event_id"] = (
        pub["event_id"] if pub else "000001-00000000")
    verdict["publication_event_hash"] = (
        pub["event_hash"] if pub else "0" * 64)
    if result_audit:
        p = pub["payload"] if pub else {}
        verdict["experiment_config_hash"] = p.get(
            "experiment_config_hash", "0" * 64)
        verdict["run_id"] = p.get("run_id", "run-x")
        verdict["run_dir"] = p.get("run_dir", "logs/runs/run-x")
        verdict["evidence_inventory_hash"] = p.get(
            "evidence_inventory_hash", "0" * 64)
        verdict["validation_report_hash"] = p.get(
            "validation_report_hash", "0" * 64)
        verdict["replay_result"] = "replayed_ok"
        verdict["counts"] = {"scenarios_run": 1, "validations_passed": 1,
                             "validations_failed": 0}
        verdict["conclusion_scope"] = "test evidence approved"


def append(root: str, cfg: Config, event_type: str, sender: str,
           request_id: str, repo: str, commit: str, payload=None) -> dict:
    """Raw append helper. Verdict events must carry a schema-valid nested
    verdict, and human-authority events a spendable one-time token (H1) —
    both autofilled when a test passes no explicit payload/token, so
    drive-style sequences stay terse. Tests probing either boundary pass
    their own (invalid) payloads explicitly."""
    # publication events carry the request_payload_hash + expected count
    # that verdict bindings reference (the real publish path sets these;
    # synthetic FSM-drive appends get a deterministic stand-in)
    if not payload and event_type in ("AUDIT_REQUESTED", "READY_FOR_REAUDIT"):
        import hashlib
        payload = {
            "request_payload_hash": hashlib.sha256(
                request_id.encode()).hexdigest(),
            "expected_test_count": 147, "scope": ["scope item"],
            "expected_test_command": TEST_COMMAND,
            "blockers_addressed": ["b"]}
    if not payload and event_type == "RESULT_AUDIT_REQUESTED":
        # the real runner pins the evidence bindings here; synthetic
        # drives get deterministic stand-ins so result verdicts can bind
        import hashlib
        h = hashlib.sha256(request_id.encode()).hexdigest()
        payload = {
            "task_id": "t-x", "run_id": "run-" + request_id,
            "run_dir": "logs/runs/run-" + request_id,
            "experiment_config_hash": h, "evidence_inventory_hash": h,
            "validation_report_hash": h, "validations": []}
    if not payload and event_type in _EVENT_TO_VERDICT:
        from tools.council.schemas import compute_verdict_payload_hash
        result_audit = event_type in ("RESULT_APPROVED", "RESULT_BLOCKED")
        payload = make_verdict(commit, request_id,
                               verdict=_EVENT_TO_VERDICT[event_type])
        # new (2.0) verdict events are domain-separated + authority-bound
        # (H2/H3): stamp schema_version and the chain-derived bindings the
        # way submit_verdict does
        payload["schema_version"] = (
            "result-verdict.v2" if result_audit else "source-verdict.v2")
        _inject_test_bindings(root, payload, request_id, commit,
                              result_audit)
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
