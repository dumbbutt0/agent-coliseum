"""H3: verdict authority-context bindings (verified against the chain at
the append boundary) and the evidence manifest."""
import os

import pytest

from tests.council_util import (append, drive_to_claimed, make_cfg,
                                make_repo, make_root, make_verdict)
from tools.council import codex_watch, events, locking, storage
from tools.council.schemas import (CouncilError, SchemaViolation,
                                   compute_verdict_payload_hash,
                                   crosscheck_verdict_bindings,
                                   domain_hash, EVIDENCE_INVENTORY_DOMAIN)

RID = "h3-req-001"


@pytest.fixture()
def env(tmp_path):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    return root, repo, head, make_cfg(repo, root)


def _submit_source(root, cfg, repo, head, kind="GO"):
    ctx = drive_to_claimed(root, cfg, repo, head, request_id=RID)
    v = make_verdict(head, RID, verdict=kind)
    event = codex_watch.submit_verdict(root, cfg, v)
    return event


# --------------------------------------- submit-injected source bindings

def test_submit_injects_source_bindings(env):
    root, repo, head, cfg = env
    event = _submit_source(root, cfg, repo, head)
    v = event["payload"]
    assert v["auditor"] == "codex"
    assert v["audit_cycle"] == 1
    assert v["schema_version"] == "source-verdict.v2"
    # publication_event binds the real AUDIT_REQUESTED
    pub = [e for e in events.read_chain(root)
           if e["event_type"] == "AUDIT_REQUESTED"][0]
    assert v["publication_event_id"] == pub["event_id"]
    assert v["publication_event_hash"] == pub["event_hash"]
    assert v["request_payload_hash"] == \
        pub["payload"]["request_payload_hash"]


def test_forged_publication_binding_refused(env):
    """A verdict event whose publication binding does not match the chain
    is refused at the append boundary."""
    root, repo, head, cfg = env
    ctx = drive_to_claimed(root, cfg, repo, head, request_id=RID)
    v = make_verdict(head, RID, verdict="GO")
    v["schema_version"] = "source-verdict.v2"
    v["auditor"] = "codex"
    v["audit_cycle"] = 1
    v["request_payload_hash"] = "a" * 64
    v["publication_event_id"] = "000001-deadbeef"   # not the real pub
    v["publication_event_hash"] = "b" * 64
    v["verdict_payload_hash"] = compute_verdict_payload_hash(v)
    with pytest.raises(CouncilError):
        append(root, cfg, "AUDIT_GO", "codex", RID, repo, head, v)
    locking.release(ctx["lock"])


def test_wrong_audit_cycle_refused(env):
    root, repo, head, cfg = env
    ctx = drive_to_claimed(root, cfg, repo, head, request_id=RID)
    pub = [e for e in events.read_chain(root)
           if e["event_type"] == "AUDIT_REQUESTED"][0]
    v = make_verdict(head, RID, verdict="GO")
    v["schema_version"] = "source-verdict.v2"
    v["auditor"] = "codex"
    v["audit_cycle"] = 5                       # real cycle is 1
    v["request_payload_hash"] = pub["payload"]["request_payload_hash"]
    v["publication_event_id"] = pub["event_id"]
    v["publication_event_hash"] = pub["event_hash"]
    v["verdict_payload_hash"] = compute_verdict_payload_hash(v)
    with pytest.raises(CouncilError):
        append(root, cfg, "AUDIT_GO", "codex", RID, repo, head, v)
    locking.release(ctx["lock"])


def test_auditor_must_be_codex(env):
    root, repo, head, cfg = env
    ctx = drive_to_claimed(root, cfg, repo, head, request_id=RID)
    pub = [e for e in events.read_chain(root)
           if e["event_type"] == "AUDIT_REQUESTED"][0]
    v = make_verdict(head, RID, verdict="GO")
    v["schema_version"] = "source-verdict.v2"
    v["auditor"] = "claude"                    # not the auditor
    v["audit_cycle"] = 1
    v["request_payload_hash"] = pub["payload"]["request_payload_hash"]
    v["publication_event_id"] = pub["event_id"]
    v["publication_event_hash"] = pub["event_hash"]
    v["verdict_payload_hash"] = compute_verdict_payload_hash(v)
    with pytest.raises(SchemaViolation):
        append(root, cfg, "AUDIT_GO", "codex", RID, repo, head, v)
    locking.release(ctx["lock"])


def test_tests_observed_must_match_expected(env):
    """The deferred H2 semantic check: verdict tests_observed must equal
    the request's event-pinned expected_test_count."""
    root, repo, head, cfg = env
    ctx = drive_to_claimed(root, cfg, repo, head, request_id=RID)
    pub = [e for e in events.read_chain(root)
           if e["event_type"] == "AUDIT_REQUESTED"][0]
    v = make_verdict(head, RID, verdict="GO", tests_observed=999)
    v["schema_version"] = "source-verdict.v2"
    v["auditor"] = "codex"
    v["audit_cycle"] = 1
    v["request_payload_hash"] = pub["payload"]["request_payload_hash"]
    v["publication_event_id"] = pub["event_id"]
    v["publication_event_hash"] = pub["event_hash"]
    v["verdict_payload_hash"] = compute_verdict_payload_hash(v)
    with pytest.raises(CouncilError):
        append(root, cfg, "AUDIT_GO", "codex", RID, repo, head, v)
    locking.release(ctx["lock"])


# ------------------------------------------------- evidence manifest

def test_evidence_manifest_determinism_and_tamper(tmp_path):
    from tools.autonomy.runner import build_evidence_manifest
    repo = str(tmp_path / "repo")
    run_dir = "logs/runs/r1"
    os.makedirs(os.path.join(repo, run_dir))
    for name, data in (("a.jsonl", b"one\n"), ("b.json", b'{"x":1}')):
        with open(os.path.join(repo, run_dir, name), "wb") as fh:
            fh.write(data)
    m1, h1 = build_evidence_manifest(repo, run_dir, "r1")
    m2, h2 = build_evidence_manifest(repo, run_dir, "r1")
    assert h1 == h2                                   # content-deterministic
    assert m1["inventory_hash"] == h1
    assert m1["file_count"] == 2
    # tamper one byte -> different inventory hash
    with open(os.path.join(repo, run_dir, "a.jsonl"), "wb") as fh:
        fh.write(b"TWO\n")
    _m3, h3 = build_evidence_manifest(repo, run_dir, "r1")
    assert h3 != h1


def test_result_verdict_binds_runner_evidence(env):
    """A result verdict must bind the exact evidence hashes the runner
    pinned in RESULT_AUDIT_REQUESTED; a mismatch is refused."""
    root, repo, head, cfg = env
    # drive to result_audit with autofilled evidence bindings
    from tests.council_util import append as ap
    ap(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    ap(root, cfg, "BUILD_READY", "claude", RID, repo, head)
    from tools.council import publish
    from tests.council_util import make_request
    publish.publish_request(root, cfg, make_request(repo, head, RID))
    codex_cfg = make_cfg(repo, root, role="codex")
    codex_watch.claim(root, codex_cfg, RID)
    codex_watch.submit_verdict(root, codex_cfg, make_verdict(head, RID))
    ap(root, cfg, "POLICY_VALIDATION_REQUIRED", "claude", RID, repo, head)
    ap(root, cfg, "HUMAN_APPROVAL_REQUIRED", "claude", RID, repo, head)
    ap(root, cfg, "EXPERIMENT_APPROVED", "human", RID, repo, head)
    ap(root, cfg, "EXPERIMENT_STARTED", "claude", RID, repo, head)
    ap(root, cfg, "EXPERIMENT_COMPLETE", "claude", RID, repo, head)
    ap(root, cfg, "RESULT_VALIDATION_REQUIRED", "claude", RID, repo, head)
    os.rename(storage.safe_request_path(root, "complete", RID),
              storage.safe_request_path(root, "claimed", RID))
    ap(root, cfg, "RESULT_AUDIT_REQUESTED", "claude", RID, repo, head)
    # a result verdict whose evidence hash is forged is refused
    rar = [e for e in events.read_chain(root)
           if e["event_type"] == "RESULT_AUDIT_REQUESTED"][0]
    v = make_verdict(head, RID, verdict="APPROVED")
    v["schema_version"] = "result-verdict.v2"
    v["auditor"] = "codex"
    v["audit_cycle"] = 1
    v["request_payload_hash"] = "0" * 64
    v["publication_event_id"] = rar["event_id"]
    v["publication_event_hash"] = rar["event_hash"]
    v["experiment_config_hash"] = rar["payload"]["experiment_config_hash"]
    v["run_id"] = rar["payload"]["run_id"]
    v["run_dir"] = rar["payload"]["run_dir"]
    v["evidence_inventory_hash"] = "f" * 64        # FORGED
    v["validation_report_hash"] = rar["payload"]["validation_report_hash"]
    v["verdict_payload_hash"] = compute_verdict_payload_hash(v)
    with pytest.raises(CouncilError):
        append(root, cfg, "RESULT_APPROVED", "codex", RID, repo, head, v)
