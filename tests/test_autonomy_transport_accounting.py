"""Auditor transport accounting is separate from candidate accounting.

A failed audit session means an auditor did not deliver an admissible
response. It does NOT mean the candidate is defective. The provider exposes
no attributable failure signal — every failed session exits 1 — so the
launcher cannot know WHY delivery failed, and three successive attempts to
infer it from log text were blocked by Council audit (verdicts 001747,
001760).

The resolution is not better inference. Delivery failures are charged to a
bounded ROUTING budget; candidate-attributable outcomes are ADMITTED VERDICTS
and their revision budget is the five-audit-cycles-per-request limit enforced
in publish.publish_request. This module pins that separation.

Classification is STRUCTURAL — derived from whether the session could be run
at all — never from log content. The decisive tests here are the ones showing
that stderr text cannot change any outcome.
"""
import os
import stat

import pytest

from tests.council_util import (append, make_cfg, make_repo, make_request,
                                make_root)
from tools.autonomy import codex_launcher
from tools.council import events, publish, state_machine

RID = "transport-req-001"

# Log shapes that previously drove (wrong) classifications. Under the shipped
# design NONE of them may influence any decision.
QUOTA_SHAPED = "stream error: You've hit your usage limit. try again later.\n"
FILTER_SHAPED = "ERROR: This content was flagged for policy reasons.\n"
EMPTY = ""


@pytest.fixture()
def env(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    monkeypatch.setenv("COUNCIL_ROOT", root)
    monkeypatch.setenv("COUNCIL_REPO_ROOTS", repo)
    return root, repo, head, cfg


def _fake_codex(tmp_path, monkeypatch, stderr_text="", exit_code=1,
                missing=False, nonexec=False):
    script = tmp_path / "bin" / "codex"
    script.parent.mkdir(parents=True, exist_ok=True)
    if missing:
        monkeypatch.setattr(codex_launcher, "CODEX_BIN",
                            str(tmp_path / "bin" / "does-not-exist"))
        return
    script.write_text("#!/usr/bin/env python3\n"
                      "import sys\n"
                      f"sys.stderr.write({stderr_text!r})\n"
                      f"sys.exit({exit_code})\n")
    if not nonexec:
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(codex_launcher, "CODEX_BIN", str(script))


def _publish(root, cfg, repo, head, rid=RID):
    append(root, cfg, "BUILD_STARTED", "claude", rid, repo, head)
    append(root, cfg, "BUILD_READY", "claude", rid, repo, head)
    publish.publish_request(root, cfg, make_request(repo, head, rid))


def _failures(root, rid=RID):
    return [e for e in events.read_chain(root)
            if e["request_id"] == rid
            and e["payload"].get("phase") == "codex_launcher"
            and e["payload"].get("failure") is True]


# ------------------------------------------------ the separation itself

def test_routing_failures_never_touch_candidate_revision_budget(
        env, tmp_path, monkeypatch):
    """Acceptance #3: repeated delivery failures exhaust ONLY the routing
    budget. The request's audit_cycles — the candidate revision budget
    enforced by publish_request — is untouched."""
    root, repo, head, cfg = env
    _fake_codex(tmp_path, monkeypatch, QUOTA_SHAPED)
    _publish(root, cfg, repo, head)
    before = state_machine.project(events.read_chain(root))[RID]["audit_cycles"]

    codex_launcher.main(["--once"])
    codex_launcher.main(["--once"])
    chain = events.read_chain(root)
    assert codex_launcher.routing_failures(chain, RID) == 2
    after = state_machine.project(chain)[RID]["audit_cycles"]
    assert after == before, "delivery failures must not consume audit cycles"
    for event in _failures(root):
        assert event["payload"]["accounting"] == "routing"
        assert event["payload"]["candidate_attributable"] is False


def test_no_stderr_content_can_change_any_outcome(env, tmp_path, monkeypatch):
    """Acceptance #4: diagnostic text cannot suppress, compensate, or
    reclassify an attempt. A quota-shaped log, a filter-shaped log and an
    empty log must produce IDENTICAL accounting."""
    outcomes = []
    for text in (QUOTA_SHAPED, FILTER_SHAPED, EMPTY):
        root = make_root(tmp_path / f"r{len(outcomes)}")
        repo, head = make_repo(tmp_path / f"w{len(outcomes)}")
        cfg = make_cfg(repo, root)
        monkeypatch.setenv("COUNCIL_ROOT", root)
        monkeypatch.setenv("COUNCIL_REPO_ROOTS", repo)
        _fake_codex(tmp_path / f"b{len(outcomes)}", monkeypatch, text)
        _publish(root, cfg, repo, head)
        codex_launcher.main(["--once"])
        payload = _failures(root)[-1]["payload"]
        outcomes.append((payload["failure_kind"], payload["accounting"],
                         payload["candidate_attributable"],
                         codex_launcher.routing_failures(
                             events.read_chain(root), RID)))
    assert len(set(outcomes)) == 1, f"stderr content changed the outcome: {outcomes}"


def test_source_has_no_stderr_classifier():
    """The guarantee is structural: nothing parses auditor log CONTENT."""
    import inspect
    source = inspect.getsource(codex_launcher)
    for banned in ("classify_session_failure", "AUDITOR_UNAVAILABLE_CLASSES",
                   "SESSION_FAILURE_CLASSES", "ACCESS_BOUNDARY_CONFIRMED",
                   "probe_auditor_access", "retry_hint"):
        assert banned not in source, f"retired mechanism present: {banned}"


# ------------------------------------------------ structural classification

def test_unrunnable_session_classifies_as_transport(env, tmp_path,
                                                    monkeypatch):
    """A session that could not be run at all is transport — derived from
    the refusal, not from any message."""
    root, repo, head, cfg = env
    _fake_codex(tmp_path, monkeypatch, missing=True)
    _publish(root, cfg, repo, head)
    codex_launcher.main(["--once"])
    payload = _failures(root)[-1]["payload"]
    assert payload["failure_kind"] == "transport"
    assert payload["candidate_attributable"] is False


def test_timeout_classifies_as_transport(env, tmp_path, monkeypatch):
    root, repo, head, cfg = env
    script = tmp_path / "bin" / "codex"
    script.parent.mkdir(exist_ok=True)
    script.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(30)\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(codex_launcher, "CODEX_BIN", str(script))
    _publish(root, cfg, repo, head)
    codex_launcher.main(["--once", "--audit-timeout-seconds", "1"])
    assert _failures(root)[-1]["payload"]["failure_kind"] == "transport"


def test_ran_but_delivered_nothing_classifies_separately(env, tmp_path,
                                                         monkeypatch):
    """A session that ran and returned nothing admissible is its own kind —
    still routing, still not candidate-attributable."""
    root, repo, head, cfg = env
    _fake_codex(tmp_path, monkeypatch, EMPTY, exit_code=0)
    _publish(root, cfg, repo, head)
    codex_launcher.main(["--once"])
    payload = _failures(root)[-1]["payload"]
    assert payload["failure_kind"] == "no_admissible_response"
    assert payload["accounting"] == "routing"
    assert payload["candidate_attributable"] is False


# ------------------------------------------------ candidate outcomes survive

def test_admitted_blocked_verdict_is_a_candidate_finding_not_a_failure(
        env, tmp_path, monkeypatch):
    """Acceptance #5: a genuine candidate finding is a launcher SUCCESS and
    is charged to candidate accounting, not routing. A later provider outage
    cannot hide it."""
    root, repo, head, cfg = env
    _publish(root, cfg, repo, head)
    from tools.council import codex_watch
    codex_watch.claim(root, cfg, RID)
    append(root, cfg, "AUDIT_BLOCKED", "codex", RID, repo, head)
    chain = events.read_chain(root)
    assert codex_launcher.routing_failures(chain, RID) == 0
    assert state_machine.project(chain)[RID]["state"] == "blocked"
    # a subsequent outage adds routing failures but cannot erase the finding
    assert any(e["event_type"] == "AUDIT_BLOCKED" for e in chain)


def test_admitted_verdict_resets_the_routing_budget(env, tmp_path,
                                                    monkeypatch):
    """Delivery succeeding proves the route works, so earlier delivery
    failures are no longer consecutive. This also stops one dead process
    burning two strikes via the resume path."""
    root, repo, head, cfg = env
    _fake_codex(tmp_path, monkeypatch, QUOTA_SHAPED)
    _publish(root, cfg, repo, head)
    codex_launcher.main(["--once"])
    assert codex_launcher.routing_failures(events.read_chain(root), RID) == 1

    from tools.council import codex_watch
    codex_watch.claim(root, cfg, RID)
    append(root, cfg, "AUDIT_BLOCKED", "codex", RID, repo, head)
    assert codex_launcher.routing_failures(events.read_chain(root), RID) == 0


def test_publish_resets_the_routing_budget():
    """A newly published cycle starts with a clean routing budget."""
    def ev(etype, sender="codex", failure=None):
        payload = {"phase": "codex_launcher"} if failure is not None else {}
        if failure is not None:
            payload["failure"] = failure
        return {"request_id": RID, "event_type": etype, "sender": sender,
                "payload": payload}

    chain = [ev("WATCHER_ERROR", failure=True),
             ev("WATCHER_ERROR", failure=True)]
    assert codex_launcher.routing_failures(chain, RID) == 2
    for republish in ("AUDIT_REQUESTED", "READY_FOR_REAUDIT",
                      "RESULT_AUDIT_REQUESTED"):
        assert codex_launcher.routing_failures(
            chain + [ev(republish, sender="claude")], RID) == 0, republish


def test_bookkeeping_events_never_count_as_routing_failures():
    """Stale-lock clearances carry no failure flag and must not count."""
    chain = [{"request_id": RID, "event_type": "WATCHER_ERROR",
              "sender": "codex",
              "payload": {"phase": "codex_launcher",
                          "operation": "clear_stale_lock"}}]
    assert codex_launcher.routing_failures(chain, RID) == 0


# ------------------------------------------------ exhaustion semantics

def test_routing_exhaustion_pauses_and_disclaims_candidate_judgement(
        env, tmp_path, monkeypatch):
    """At N=1 there is one route, so exhausting it IS 'every authorized
    route unavailable'. The pause must say so — and must state plainly that
    the candidate is unjudged."""
    root, repo, head, cfg = env
    _fake_codex(tmp_path, monkeypatch, QUOTA_SHAPED)
    _publish(root, cfg, repo, head)
    assert codex_launcher.main(["--once"]) == 0
    assert codex_launcher.main(["--once"]) == 0
    assert codex_launcher.main(["--once"]) == 1
    paused = events.read_chain(root)[-1]
    assert paused["event_type"] == "AUTONOMY_PAUSED"
    reason = paused["payload"]["reason"]
    assert "ROUTING EXHAUSTED" in reason
    assert "NOTHING about the candidate" in reason
    assert "no candidate revision budget was consumed" in reason
    # and the candidate genuinely was not judged: no verdict of any kind
    # was ever admitted for it
    chain = events.read_chain(root)
    verdicts = {e["event_type"] for e in chain if e["request_id"] == RID}
    assert not verdicts & {"AUDIT_GO", "AUDIT_GO_WITH_CONDITIONS",
                           "AUDIT_BLOCKED"}


def test_every_attempt_stays_immutably_recorded(env, tmp_path, monkeypatch):
    """Nothing is erased, compensated, reclassified, or attested — the
    change is which budget an attempt is charged to, not whether it
    happened. Replay stays deterministic."""
    root, repo, head, cfg = env
    _fake_codex(tmp_path, monkeypatch, QUOTA_SHAPED)
    _publish(root, cfg, repo, head)
    codex_launcher.main(["--once"])
    codex_launcher.main(["--once"])
    recorded = _failures(root)
    assert len(recorded) == 2
    for event in recorded:
        assert event["payload"]["failure"] is True     # never downgraded
        assert event["payload"]["stdout_log"]          # evidence pointers kept
        assert event["payload"]["stderr_log"]
    assert events.verify_chain(root).healthy
