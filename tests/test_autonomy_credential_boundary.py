"""Auditor-availability boundary: an auditor that cannot RUN is not a
candidate that FAILED.

A hard credential or usage-quota boundary is an environmental fact about the
auditor's access. It says nothing about the audited commit, so it must not
consume the bounded failure budget that exists to stop a genuinely broken
build-audit loop. Everything else — content-filter interruption, crash,
malformed output, unknown error — still counts and still fails closed.

The strongest case here is the real incident replay: the exact stderr that
previously drove the loop toward the three-strike pause must now record a
credential boundary without spending a strike.
"""
import os
import stat

import pytest

from tests.council_util import (append, make_cfg, make_repo, make_request,
                                make_root)
from tools.autonomy import codex_launcher
from tools.council import events, publish

RID = "credential-boundary-req-001"
REAL_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The verbatim auditor stderr from the 2026-07-18 incident (events
# 001658 -> 001659), which previously counted toward the pause.
REAL_QUOTA_STDERR = (
    "stream error: You've hit your usage limit. "
    "try again at Jul 22nd, 2026 9:16 PM.\n"
)
REAL_FILTER_STDERR = (
    "ERROR: This content was flagged for possible cybersecurity risk. "
    "If this seems wrong, try rephrasing your request.\n"
)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    monkeypatch.setenv("COUNCIL_ROOT", root)
    monkeypatch.setenv("COUNCIL_REPO_ROOTS", repo)
    return root, repo, head, cfg


def _install_fake_codex(tmp_path, monkeypatch, stderr_text: str,
                        exit_code: int = 1) -> None:
    """A fake auditor that emits the given stderr and exits without ever
    submitting a verdict — the shape of every real failed session."""
    script = tmp_path / "bin" / "codex"
    script.parent.mkdir(exist_ok=True)
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        f"sys.stderr.write({stderr_text!r})\n"
        f"sys.exit({exit_code})\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(codex_launcher, "CODEX_BIN", str(script))


def _publish(root, cfg, repo, head, rid=RID):
    append(root, cfg, "BUILD_STARTED", "claude", rid, repo, head)
    append(root, cfg, "BUILD_READY", "claude", rid, repo, head)
    publish.publish_request(root, cfg, make_request(repo, head, rid))


def _last_launcher_event(root, rid=RID):
    for event in reversed(events.read_chain(root)):
        if event["request_id"] == rid and \
                event["payload"].get("phase") == "codex_launcher":
            return event
    raise AssertionError("no codex_launcher event on the chain")


# ------------------------------------------------- pure classification

@pytest.mark.parametrize("text,expected", [
    (REAL_QUOTA_STDERR, "quota_exhausted"),
    ("Error: rate limit reached for this account", "quota_exhausted"),
    ("insufficient_quota: billing hard limit reached", "quota_exhausted"),
    ("You are not logged in. Run `codex login`.", "credentials_missing"),
    ("401 Unauthorized: invalid api key", "credentials_missing"),
    ("expired token; authentication failed", "credentials_missing"),
    (REAL_FILTER_STDERR, "content_filter"),
    ("curl: connection refused", "network"),
    ("temporary failure in name resolution", "network"),
    ("invalid verdict: malformed json at line 3", "malformed_output"),
    ("Traceback (most recent call last): ValueError: boom", "unknown"),
    ("", "unknown"),
])
def test_classification_distinguishes_every_named_class(text, expected):
    cls, evidence = codex_launcher.classify_session_failure(text)
    assert cls == expected
    if expected != "unknown":
        assert evidence, "a recognized class must carry detection evidence"


def test_only_credential_and_quota_classes_bypass_the_budget():
    """The bypass set is deliberately narrow: a filter interruption, a
    crash, or anything unrecognized must still consume a strike."""
    assert codex_launcher.AUDITOR_UNAVAILABLE_CLASSES == frozenset(
        {"quota_exhausted", "credentials_missing"})
    for other in ("content_filter", "network", "malformed_output", "unknown"):
        assert other not in codex_launcher.AUDITOR_UNAVAILABLE_CLASSES


def test_retry_hint_is_recorded_verbatim_not_interpreted():
    assert "Jul 22nd, 2026 9:16 PM" in \
        codex_launcher.retry_hint(REAL_QUOTA_STDERR)
    assert codex_launcher.retry_hint("no hint here") == ""


# ------------------------------------------------- the incident replay

def test_real_quota_incident_records_boundary_without_a_strike(
        env, tmp_path, monkeypatch):
    """THE regression: the exact stderr that previously drove the loop
    toward the bounded-failure ceiling now records an auditor-unavailable
    boundary and spends no strike."""
    root, repo, head, cfg = env
    _install_fake_codex(tmp_path, monkeypatch, REAL_QUOTA_STDERR)
    _publish(root, cfg, repo, head)

    assert codex_launcher.main(["--once"]) == 0
    chain = events.read_chain(root)
    assert codex_launcher.launcher_failures(chain, RID) == 0

    event = _last_launcher_event(root)
    payload = event["payload"]
    assert event["event_type"] == "WATCHER_ERROR"
    assert payload["failure"] is False          # the load-bearing flag
    assert payload["auditor_unavailable"] is True
    assert payload["failure_class"] == "quota_exhausted"
    assert "usage limit" in payload["detection_evidence"]
    assert "Jul 22nd, 2026" in payload["earliest_retry_hint"]
    assert payload["provider"] == "codex"
    # the candidate keeps zero authority and still needs a real audit
    assert payload["integration_authority"] == "none"
    assert payload["requires_fresh_audit"] is True
    # identity preserved verbatim
    assert event["request_id"] == RID
    assert event["target_commit"] == head


def test_repeated_quota_exits_never_pause_autonomy(env, tmp_path,
                                                   monkeypatch):
    """Three-plus quota exits — far past MAX_CONSECUTIVE_FAILURES — must
    never reach AUTONOMY_PAUSED."""
    root, repo, head, cfg = env
    _install_fake_codex(tmp_path, monkeypatch, REAL_QUOTA_STDERR)
    _publish(root, cfg, repo, head)
    for _ in range(codex_launcher.MAX_CONSECUTIVE_FAILURES + 2):
        assert codex_launcher.main(["--once"]) == 0
    chain = events.read_chain(root)
    assert codex_launcher.launcher_failures(chain, RID) == 0
    assert not [e for e in chain if e["event_type"] == "AUTONOMY_PAUSED"]


def test_boundary_holds_the_request_from_immediate_relaunch(
        env, tmp_path, monkeypatch):
    """After a recorded boundary the launcher must not re-run straight back
    into it — the auditor's access has not changed."""
    root, repo, head, cfg = env
    _install_fake_codex(tmp_path, monkeypatch, REAL_QUOTA_STDERR)
    _publish(root, cfg, repo, head)
    assert codex_launcher.main(["--once"]) == 0
    before = len(events.read_chain(root))
    assert codex_launcher.main(["--once"]) == 0
    # held: no second boundary event, no launch, no strike
    assert len(events.read_chain(root)) == before
    assert codex_launcher.credential_boundary(
        events.read_chain(root), RID) is not None


def _ev(etype, payload=None, rid=RID):
    return {"request_id": rid, "event_type": etype, "payload": payload or {}}


def test_fresh_cycle_clears_the_boundary():
    """A new published cycle deserves a fresh probe — access may have
    returned, and that is discovered by TRYING, not assumed by a timer."""
    boundary = {"phase": "codex_launcher", "auditor_unavailable": True,
                "failure_class": "quota_exhausted"}
    held = [_ev("AUDIT_REQUESTED"), _ev("WATCHER_ERROR", boundary)]
    assert codex_launcher.credential_boundary(held, RID) is not None
    for fresh in ("AUDIT_REQUESTED", "READY_FOR_REAUDIT",
                  "RESULT_AUDIT_REQUESTED"):
        assert codex_launcher.credential_boundary(
            held + [_ev(fresh)], RID) is None, fresh


def test_recorded_clearance_lifts_the_boundary():
    """Access returning is an OBSERVATION recorded on the chain, never an
    assumption — an explicit clearance lifts the hold."""
    boundary = {"phase": "codex_launcher", "auditor_unavailable": True,
                "failure_class": "credentials_missing"}
    cleared = {"phase": "codex_launcher", "credential_boundary_cleared": True}
    chain = [_ev("AUDIT_REQUESTED"), _ev("WATCHER_ERROR", boundary)]
    assert codex_launcher.credential_boundary(chain, RID) is not None
    assert codex_launcher.credential_boundary(
        chain + [_ev("WATCHER_ERROR", cleared)], RID) is None


def test_boundary_is_per_request_not_global():
    """One request's auditor boundary must not hold unrelated work."""
    boundary = {"phase": "codex_launcher", "auditor_unavailable": True,
                "failure_class": "quota_exhausted"}
    chain = [_ev("AUDIT_REQUESTED"), _ev("WATCHER_ERROR", boundary)]
    assert codex_launcher.credential_boundary(chain, "other-request") is None


# ------------------------------------------------- everything else still counts

def test_content_filter_still_consumes_a_strike(env, tmp_path, monkeypatch):
    """A filter interruption is classified for the record but is NOT an
    access boundary — it still counts, so a genuinely stuck loop still
    reaches the owner."""
    root, repo, head, cfg = env
    _install_fake_codex(tmp_path, monkeypatch, REAL_FILTER_STDERR)
    _publish(root, cfg, repo, head)
    assert codex_launcher.main(["--once"]) == 0
    chain = events.read_chain(root)
    assert codex_launcher.launcher_failures(chain, RID) == 1
    payload = _last_launcher_event(root)["payload"]
    assert payload["failure"] is True
    assert payload["failure_class"] == "content_filter"


def test_unknown_error_fails_closed_and_still_pauses(env, tmp_path,
                                                     monkeypatch):
    """Unknown errors must NOT bypass anything: three strikes still pause."""
    root, repo, head, cfg = env
    _install_fake_codex(tmp_path, monkeypatch,
                        "Traceback: something nobody has classified\n")
    _publish(root, cfg, repo, head)
    assert codex_launcher.main(["--once"]) == 0
    assert codex_launcher.main(["--once"]) == 0
    assert codex_launcher.main(["--once"]) == 1
    chain = events.read_chain(root)
    assert chain[-1]["event_type"] == "AUTONOMY_PAUSED"
    assert codex_launcher.launcher_failures(chain, RID) == \
        codex_launcher.MAX_CONSECUTIVE_FAILURES


def test_silent_session_failure_still_counts(env, tmp_path, monkeypatch):
    """No stderr at all is not evidence of a credential boundary."""
    root, repo, head, cfg = env
    _install_fake_codex(tmp_path, monkeypatch, "", exit_code=1)
    _publish(root, cfg, repo, head)
    assert codex_launcher.main(["--once"]) == 0
    chain = events.read_chain(root)
    assert codex_launcher.launcher_failures(chain, RID) == 1
    assert _last_launcher_event(root)["payload"]["failure"] is True


def test_boundary_never_grants_integration_authority(env, tmp_path,
                                                     monkeypatch):
    """A held request must remain exactly where it was: no verdict, no
    approval, no state advance that could reach integration."""
    root, repo, head, cfg = env
    _install_fake_codex(tmp_path, monkeypatch, REAL_QUOTA_STDERR)
    _publish(root, cfg, repo, head)
    assert codex_launcher.main(["--once"]) == 0
    chain = events.read_chain(root)
    types = {e["event_type"] for e in chain if e["request_id"] == RID}
    assert not types & {"AUDIT_GO", "AUDIT_GO_WITH_CONDITIONS",
                        "CHANGE_INTEGRATED", "CONDITIONS_SATISFIED"}
    from tools.council import state_machine
    assert state_machine.project(chain)[RID]["state"] == "requested"


def test_chain_stays_verifiable_across_a_boundary(env, tmp_path, monkeypatch):
    """Recording a boundary must not corrupt the chain."""
    root, repo, head, cfg = env
    _install_fake_codex(tmp_path, monkeypatch, REAL_QUOTA_STDERR)
    _publish(root, cfg, repo, head)
    assert codex_launcher.main(["--once"]) == 0
    assert events.verify_chain(root).healthy


# ------------------------------------------- the evidence boundary
#
# The dangerous direction is a FALSE boundary: echoed text minting a
# credential class would SKIP a strike and hide a real failure. A session log
# is mostly material the auditor READ — chain events, request payloads,
# source — which routinely contains these very words (this feature's own
# commit message says "usage limit"). Only a bounded terminal region of
# unstructured diagnostic lines may be evidence about the auditor's ACCESS.

ECHOED_CHAIN_PAYLOAD = (
    '{"event_id":"001592-d791eafd","event_type":"BUILD_STARTED",'
    '"payload":{"reason":"quota exhausted; usage limit reached",'
    '"scope":["not logged in"]},"request_id":"r-1"}\n'
)


def test_echoed_payload_words_never_mint_a_boundary():
    """The exact hazard: quota/credential words inside echoed structured
    payloads must NOT be read as evidence about the auditor's access."""
    crash = ECHOED_CHAIN_PAYLOAD + "Traceback (most recent call last):\nboom\n"
    cls, _ = codex_launcher.classify_session_failure(crash)
    assert cls == "unknown", "echoed payload text minted a false class"
    assert cls not in codex_launcher.AUDITOR_UNAVAILABLE_CLASSES


def test_echoed_payload_before_a_genuine_boundary_still_classifies():
    """Bulk echoed material must not SUPPRESS a real terminal diagnostic."""
    text = ECHOED_CHAIN_PAYLOAD * 50 + REAL_QUOTA_STDERR
    cls, evidence = codex_launcher.classify_session_failure(text)
    assert cls == "quota_exhausted"
    assert "usage limit" in evidence
    assert '"event_id"' not in evidence, "evidence must be the diagnostic"


def test_buried_diagnostic_outside_the_terminal_region_is_not_evidence():
    """A provider's terminal error is terminal. A quota-shaped line buried
    thousands of lines up is echoed material, not this session's outcome."""
    buried = REAL_QUOTA_STDERR + ("noise line\n" * 200)
    assert codex_launcher.classify_session_failure(buried)[0] == "unknown"


def test_long_structured_lines_are_not_diagnostics():
    """A 500+ char line is bulk output, never a provider message."""
    long_line = "x" * 600 + " you've hit your usage limit\n"
    assert codex_launcher.classify_session_failure(long_line)[0] == "unknown"


def test_retry_hint_reads_the_same_bounded_region():
    """A hint inside echoed payload text must not be harvested."""
    echoed = '{"payload":{"note":"try again at Jan 1st, 1999"}}\nboom\n'
    assert codex_launcher.retry_hint(echoed) == ""


def test_real_stranded_session_log_is_not_a_credential_boundary():
    """Replay of the real 2026-07-18 safe-008 log: ~448KB of echoed chain
    events containing the word 'quota', from a session whose launcher died
    before accounting. It must classify as unknown and therefore fail
    closed — that incident was NOT an access boundary."""
    sample = ECHOED_CHAIN_PAYLOAD * 300      # same shape, bounded size
    cls, _ = codex_launcher.classify_session_failure(sample)
    assert cls == "unknown"
    assert cls not in codex_launcher.AUDITOR_UNAVAILABLE_CLASSES
