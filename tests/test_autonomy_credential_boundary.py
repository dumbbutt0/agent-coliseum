"""Owner-confirmed auditor-access boundary.

The autonomous-attribution premise is RETIRED (audit 001760): the provider
exposes neither distinguishable exit codes — every failure exits 1 — nor a
structured, session-attributable access signal, so no agent can soundly
determine WHY an auditor session failed. Every unsuccessful launch therefore
records a failure and consumes a strike. Classification survives as an
UNTRUSTED diagnostic hint with no authority.

An access failure leaves the effective budget only via the owner's
authenticated, session-bound attestation, which never rewrites the original
failure — the immutable record keeps it, and a compensating attestation
excludes that ONE bound attempt from the effective count.

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
# A representative interruption message, written WITHOUT reproducing a
# provider's verbatim trigger text (an auditor reading this file would
# otherwise trip the provider's own filter). The property under test is
# unchanged: this class is recorded and still consumes a strike.
REAL_FILTER_STDERR = (
    "ERROR: This content was flagged for possible policy reasons. "
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


def test_retry_hint_is_recorded_verbatim_not_interpreted():
    assert "Jul 22nd, 2026 9:16 PM" in \
        codex_launcher.retry_hint(REAL_QUOTA_STDERR)
    assert codex_launcher.retry_hint("no hint here") == ""


# ------------------------------------------------- the incident replay

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


# ------------------- audit 001747: provenance + guaranteed resumption


# ---------------- owner-confirmed access boundary (audit 001760 design)

def _attest(root, cfg, failure_event_id, rid=RID, repo="", commit="",
            condition="provider reported quota exhausted on the account"):
    """The owner's authenticated attestation, bound to ONE failed attempt."""
    from tests.council_util import append
    return append(root, cfg, "ACCESS_BOUNDARY_CONFIRMED", "human", rid,
                  repo, commit,
                  payload={"bound_request_id": rid,
                           "bound_failure_event_id": failure_event_id,
                           "observed_condition": condition,
                           "observed_at_utc": "2026-07-18T19:40:00Z",
                           "disposition": "classify as auditor unavailable; "
                                          "restore effective strike capacity",
                           "attested_by": "owner"})


def test_every_failure_consumes_a_strike_by_default(env, tmp_path,
                                                    monkeypatch):
    """Item 1: no classification suppresses a strike. Even the exact quota
    stderr that motivated this slice now counts."""
    root, repo, head, cfg = env
    _install_fake_codex(tmp_path, monkeypatch, REAL_QUOTA_STDERR)
    _publish(root, cfg, repo, head)
    assert codex_launcher.main(["--once"]) == 0
    chain = events.read_chain(root)
    assert codex_launcher.effective_launcher_failures(chain, RID) == 1
    assert _last_launcher_event(root)["payload"]["failure"] is True


def test_suspicion_is_recorded_but_carries_no_authority(env, tmp_path,
                                                        monkeypatch):
    """Item 2: the diagnostic hint is kept for humans and gates nothing."""
    root, repo, head, cfg = env
    _install_fake_codex(tmp_path, monkeypatch, REAL_QUOTA_STDERR)
    _publish(root, cfg, repo, head)
    assert codex_launcher.main(["--once"]) == 0
    payload = _last_launcher_event(root)["payload"]
    assert payload["failure_class"] == "quota_exhausted"   # recorded...
    assert payload["failure"] is True                      # ...but no authority
    assert codex_launcher.AUDITOR_UNAVAILABLE_CLASSES == frozenset()


def test_repeated_unattested_failures_still_reach_the_ceiling(env, tmp_path,
                                                              monkeypatch):
    """Item 7: without an attestation the strike ceiling is authoritative,
    whatever the log says."""
    root, repo, head, cfg = env
    _install_fake_codex(tmp_path, monkeypatch, REAL_QUOTA_STDERR)
    _publish(root, cfg, repo, head)
    assert codex_launcher.main(["--once"]) == 0
    assert codex_launcher.main(["--once"]) == 0
    assert codex_launcher.main(["--once"]) == 1
    assert events.read_chain(root)[-1]["event_type"] == "AUTONOMY_PAUSED"


def test_attestation_compensates_without_erasing_the_record(env, tmp_path,
                                                            monkeypatch):
    """Items 4 and 5: the original failure remains on the immutable chain;
    the attestation removes that ONE attempt from the EFFECTIVE count."""
    root, repo, head, cfg = env
    _install_fake_codex(tmp_path, monkeypatch, REAL_QUOTA_STDERR)
    _publish(root, cfg, repo, head)
    assert codex_launcher.main(["--once"]) == 0
    chain = events.read_chain(root)
    failure = _last_launcher_event(root)
    assert codex_launcher.effective_launcher_failures(chain, RID) == 1

    _attest(root, cfg, failure["event_id"], repo=repo, commit=head)
    chain = events.read_chain(root)
    # effective capacity restored...
    assert codex_launcher.effective_launcher_failures(chain, RID) == 0
    # ...while the original strike is still there, unrewritten
    original = [e for e in chain if e["event_id"] == failure["event_id"]]
    assert original and original[0]["payload"]["failure"] is True
    assert events.verify_chain(root).healthy


def test_attestation_binds_one_attempt_and_never_latches(env, tmp_path,
                                                         monkeypatch):
    """Item 6: an attestation excuses only the attempt it names — a LATER
    failure is not excused by an earlier outage confirmation."""
    root, repo, head, cfg = env
    _install_fake_codex(tmp_path, monkeypatch, REAL_QUOTA_STDERR)
    _publish(root, cfg, repo, head)
    assert codex_launcher.main(["--once"]) == 0
    first = _last_launcher_event(root)["event_id"]
    _attest(root, cfg, first, repo=repo, commit=head)
    assert codex_launcher.effective_launcher_failures(
        events.read_chain(root), RID) == 0

    assert codex_launcher.main(["--once"]) == 0          # a NEW failure
    chain = events.read_chain(root)
    assert codex_launcher.effective_launcher_failures(chain, RID) == 1, \
        "an earlier attestation must not excuse a later attempt"


def test_attestation_for_another_request_does_not_apply(env, tmp_path,
                                                        monkeypatch):
    """Item 6: attestations are per-request as well as per-attempt."""
    root, repo, head, cfg = env
    _install_fake_codex(tmp_path, monkeypatch, REAL_QUOTA_STDERR)
    _publish(root, cfg, repo, head)
    assert codex_launcher.main(["--once"]) == 0
    failure = _last_launcher_event(root)["event_id"]
    _attest(root, cfg, failure, rid=RID, repo=repo, commit=head)
    # a different request id is unaffected
    assert codex_launcher.attested_access_failures(
        events.read_chain(root), "some-other-request") == set()


def test_attestation_requires_human_sender():
    """Item 3: the attestation is human-only and token-gated, so no agent
    can forge it (this is what a non-token WATCHER_ERROR could not give)."""
    from tools.council import schemas
    assert schemas.SENDER_ALLOWED["ACCESS_BOUNDARY_CONFIRMED"] == \
        frozenset({"human"})
    assert "ACCESS_BOUNDARY_CONFIRMED" in \
        schemas.HUMAN_TOKEN_REQUIRED_EVENT_TYPES


def test_attestation_does_not_move_request_state(env, tmp_path, monkeypatch):
    """The attestation is about a past ATTEMPT: it must not advance the
    request toward any verdict or integration."""
    from tools.council import state_machine
    root, repo, head, cfg = env
    _install_fake_codex(tmp_path, monkeypatch, REAL_QUOTA_STDERR)
    _publish(root, cfg, repo, head)
    assert codex_launcher.main(["--once"]) == 0
    before = state_machine.project(events.read_chain(root))[RID]["state"]
    _attest(root, cfg, _last_launcher_event(root)["event_id"],
            repo=repo, commit=head)
    chain = events.read_chain(root)
    assert state_machine.project(chain)[RID]["state"] == before
    types = {e["event_type"] for e in chain if e["request_id"] == RID}
    assert not types & {"AUDIT_GO", "AUDIT_GO_WITH_CONDITIONS",
                        "CHANGE_INTEGRATED"}
