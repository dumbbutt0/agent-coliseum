"""Concurrent Codex auditor workers.

Four properties make it safe to run N launcher processes at once:

* A2 — a worker reports success ONLY for a terminal verdict attributable to
  its own session, never for one another worker produced: the ordering
  anchor (its own claim event / lease position) AND the one-time session
  binding (the hash of the credential it minted, authenticated by
  submit_verdict and recorded in the terminal event) must both match.
* A3 — claimability is established BEFORE the expensive session, so the loser
  of a claim race spawns no session and records no failure.
* A4 — admission is by worker SLOT (`--workers N`), not a singleton; the
  N+1th process is refused, and `--workers 1` is the old behavior exactly.
* the claim-resume lease the launcher takes for resume/result sessions is
  released by THIS process, so a successful submit never strands it.

No live agent is ever invoked: every session runs against a fake `codex`.
"""
import json
import os

import pytest

from tests.council_util import make_cfg, make_repo, make_root, make_verdict
from tools.council.schemas import CouncilError
from tests.test_autonomy_codex_launcher import (FAKE_NOOP,
                                                FAKE_RESULT_APPROVED,
                                                FAKE_RESUME_GO, _VERDICT_BODY,
                                                _drive_to_result_audit,
                                                _install_fake_codex,
                                                _publish_requested)
from tools.autonomy import codex_launcher
from tools.council import (codex_watch, events, locking, state_machine,
                           storage)

RID = "launcher-req-001"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    monkeypatch.setenv("COUNCIL_ROOT", root)
    monkeypatch.setenv("COUNCIL_REPO_ROOTS", repo)
    return root, repo, head, cfg


# A session that audits whichever request ITS OWN prompt names — the fixed
# argv carries the request as its single opaque element, so this is how a
# real session identifies its work when several requests sit in claimed/.
FAKE_GO_FROM_PROMPT = _VERDICT_BODY + """
import re
rid = re.search(r'"request_id":"([^"]+)"', sys.argv[-1]).group(1)
req = publish.read_request(root, rid)
codex_watch.submit_verdict(root, cfg,
                           verdict_for(rid, req["target_commit"], "GO"))
"""


def _state(root, rid=RID):
    return state_machine.project(events.read_chain(root))[rid]["state"]


def _failure_events(root, rid=None):
    return [e for e in events.read_chain(root)
            if e["event_type"] == "WATCHER_ERROR"
            and e["payload"].get("failure") is True
            and (rid is None or e["request_id"] == rid)]


def _claims(root, rid):
    return [e for e in events.read_chain(root)
            if e["event_type"] == "AUDIT_CLAIMED" and e["request_id"] == rid]


# --------------------------------------------------- A3: claim before spawn

def test_two_workers_on_different_requests_do_not_interfere(
        env, tmp_path, monkeypatch):
    """The whole point of the pool: worker A holding a live claim on req-a
    must be completely undisturbed while worker B audits req-b — B never
    touches A's claim lock, A's request, or A's chain position."""
    root, repo, head, cfg = env
    marker = _install_fake_codex(tmp_path, monkeypatch, FAKE_GO_FROM_PROMPT)
    codex_cfg = make_cfg(repo, root, role="codex")
    _publish_requested(root, cfg, repo, head, rid="pool-req-a")
    _publish_requested(root, cfg, repo, head, rid="pool-req-b")

    # worker A takes req-a and is still mid-session
    _event_a, lock_a = codex_watch.claim(root, codex_cfg, "pool-req-a")

    # worker B runs a full session on req-b, concurrently
    chain = events.read_chain(root)
    requests = state_machine.project(chain)
    outcome = codex_launcher.process_one(codex_cfg, root, chain, requests,
                                         "pool-req-b", "source_audit", 60.0)
    assert outcome == "ok"
    assert os.path.exists(marker)
    assert _state(root, "pool-req-b") == "go"
    assert _failure_events(root) == []

    # A is untouched: same claim lock, same token, still claimed, one claim
    holder = locking.read_lock(root, "pool-req-a")
    assert holder is not None and holder["owner_token"] == lock_a.owner_token
    assert _state(root, "pool-req-a") == "claimed"
    assert len(_claims(root, "pool-req-a")) == 1
    assert os.path.exists(
        storage.safe_request_path(root, "claimed", "pool-req-a"))

    # and A can still finish normally afterwards
    codex_watch.submit_verdict(root, codex_cfg,
                               make_verdict(head, "pool-req-a"))
    assert _state(root, "pool-req-a") == "go"


def test_claim_race_loser_spawns_no_session_and_records_no_failure(
        env, tmp_path, monkeypatch):
    """Every worker derives the SAME work list, so two workers target the
    same oldest request. The claim (`codex_watch.claim`) arbitrates before
    the expensive session: the loser returns 'waiting' having spawned no
    Codex session and recorded no failure against the request."""
    root, repo, head, cfg = env
    marker = _install_fake_codex(tmp_path, monkeypatch, FAKE_GO_FROM_PROMPT)
    codex_cfg = make_cfg(repo, root, role="codex")
    _publish_requested(root, cfg, repo, head)

    # both workers derive the identical snapshot and pick the same item
    chain = events.read_chain(root)
    requests = state_machine.project(chain)
    assert codex_launcher.actionable(chain, requests) == [(RID,
                                                           "source_audit")]
    # worker A wins the O_EXCL claim race
    _event_a, lock_a = codex_watch.claim(root, codex_cfg, RID)

    # worker B now acts on the snapshot it had already derived
    outcome = codex_launcher.process_one(codex_cfg, root, chain, requests,
                                         RID, "source_audit", 60.0)
    assert outcome == "waiting"
    assert outcome != "ok"
    assert not os.path.exists(marker)          # NO session was spawned
    assert _failure_events(root) == []         # NO failure was recorded
    assert len(_claims(root, RID)) == 1        # exactly one worker claimed
    assert locking.read_lock(root, RID)["owner_token"] == lock_a.owner_token
    assert _state(root) == "claimed"


def test_claim_race_loser_after_the_winner_finished(env, tmp_path,
                                                    monkeypatch):
    """Same race, later: the winner has already submitted and released, so
    the request is no longer in ready/. The loser must still cost nothing —
    and must NOT report the winner's verdict as its own success."""
    root, repo, head, cfg = env
    marker = _install_fake_codex(tmp_path, monkeypatch, FAKE_GO_FROM_PROMPT)
    codex_cfg = make_cfg(repo, root, role="codex")
    _publish_requested(root, cfg, repo, head)
    chain = events.read_chain(root)
    requests = state_machine.project(chain)

    codex_watch.claim(root, codex_cfg, RID)
    codex_watch.submit_verdict(root, codex_cfg, make_verdict(head, RID))
    assert _state(root) == "go"

    outcome = codex_launcher.process_one(codex_cfg, root, chain, requests,
                                         RID, "source_audit", 60.0)
    assert outcome == "waiting"
    assert not os.path.exists(marker)
    assert _failure_events(root) == []


# ------------------------------------------- A2: verdicts belong to a session

def _chain_with_foreign_verdict(root, repo, head, cfg):
    """A completed audit by ANOTHER session: its claim event and its
    terminal verdict, both on the chain."""
    _publish_requested(root, cfg, repo, head)
    codex_cfg = make_cfg(repo, root, role="codex")
    foreign_claim, _lock = codex_watch.claim(root, codex_cfg, RID)
    codex_watch.submit_verdict(root, codex_cfg, make_verdict(head, RID))
    return events.read_chain(root), foreign_claim


def test_verdict_of_another_session_is_not_this_workers_success(env):
    """A2: presence of a codex-signed terminal verdict in a chain suffix is
    NOT attribution. Only the session whose own claim precedes the verdict
    may call it a success."""
    root, repo, head, cfg = env
    chain, foreign_claim = _chain_with_foreign_verdict(root, repo, head, cfg)

    # the session that actually claimed it -> success
    assert codex_launcher._terminal_verdict_in(
        chain, RID, "source_audit", head, 0,
        claim_event_id=foreign_claim["event_id"]) is True

    # a worker holding a DIFFERENT claim (one not on this chain at all) can
    # prove nothing -> fail closed, never someone else's success
    assert codex_launcher._terminal_verdict_in(
        chain, RID, "source_audit", head, 0,
        claim_event_id="999999-deadbeef") is False

    # and a worker whose claim landed AFTER the verdict must not adopt it
    later_claim = dict(chain[-1])
    later_claim["event_id"] = "999998-cafebabe"
    later_claim["event_type"] = "AUDIT_CLAIMED"
    assert codex_launcher._terminal_verdict_in(
        chain + [later_claim], RID, "source_audit", head, 0,
        claim_event_id=later_claim["event_id"]) is False


def test_resume_worker_binds_the_verdict_to_its_own_lease_position(env):
    """A resume/result session has no AUDIT_CLAIMED of its own, so its
    binding is the chain position at which it took the exclusive
    claim-resume lease: a verdict that already existed before the lease
    belongs to the earlier session."""
    root, repo, head, cfg = env
    chain, _foreign = _chain_with_foreign_verdict(root, repo, head, cfg)

    # lease taken before the verdict landed -> ours
    assert codex_launcher._terminal_verdict_in(
        chain, RID, "source_audit_resume", head, 0) is True
    # lease taken after it landed -> another session's verdict
    assert codex_launcher._terminal_verdict_in(
        chain, RID, "source_audit_resume", head, len(chain)) is False


def test_stale_snapshot_worker_cannot_claim_another_sessions_verdict(
        env, tmp_path, monkeypatch):
    """End to end: worker B, whose session produces nothing while worker A's
    verdict for the SAME request is already on the chain, records a failure
    — it never reports 'ok' on A's work."""
    root, repo, head, cfg = env
    _drive_to_result_audit(root, cfg, repo, head)
    # the result auditor (session A) submits...
    _install_fake_codex(tmp_path, monkeypatch, FAKE_RESULT_APPROVED)
    assert codex_launcher.main(["--once"]) == 0
    assert _state(root) == "result_approved"
    verdicts = [e for e in events.read_chain(root)
                if e["event_type"] == "RESULT_APPROVED"]
    assert len(verdicts) == 1

    # ...and a second worker, starting its own result-audit session now,
    # must not treat A's RESULT_APPROVED as its own success
    chain = events.read_chain(root)
    assert codex_launcher._terminal_verdict_in(
        chain, RID, "result_audit", head, len(chain)) is False


# ------------- A2 end to end: session binding (pool-split attribution-001)

def _expire_lock(root, rid):
    lock_file = storage.lock_path(root, rid)
    with open(lock_file, encoding="utf-8") as fh:
        holder = json.load(fh)
    holder["lease_expires_utc"] = "2000-01-01T00:00:00.000Z"
    with open(lock_file, "w", encoding="utf-8") as fh:
        json.dump(holder, fh)


def _foreign_submit(root, codex_cfg, head, result_audit=False):
    """This worker's bounded session, in which the CHILD emits nothing at
    all while an independent session B bare-submits the same request (no
    session credential) AFTER the worker's anchor — the verdict's neutral
    concurrent fixture, made deterministic."""
    def _run(*_args, **_kwargs):
        codex_watch.submit_verdict(
            root, codex_cfg,
            make_verdict(head, RID,
                         verdict="APPROVED" if result_audit else "GO"),
            result_audit=result_audit)
    return _run


def _process_one(codex_cfg, root, kind):
    chain = events.read_chain(root)
    requests = state_machine.project(chain)
    return codex_launcher.process_one(codex_cfg, root, chain, requests,
                                      RID, kind, 60.0)


def test_fresh_worker_never_adopts_a_foreign_post_anchor_verdict(
        env, monkeypatch):
    """Fresh source mode: worker A holds its own claim anchor, A's bounded
    child emits nothing, session B submits the same request after the
    anchor. A must return 'failed' (B's verdict carries no session
    binding), NEVER 'ok'."""
    root, repo, head, cfg = env
    codex_cfg = make_cfg(repo, root, role="codex")
    _publish_requested(root, cfg, repo, head)
    monkeypatch.setattr(codex_launcher, "_execute_bounded",
                        _foreign_submit(root, codex_cfg, head))

    outcome = _process_one(codex_cfg, root, "source_audit")
    assert outcome != "ok"
    assert outcome == "failed"
    assert len(_failure_events(root, RID)) == 1
    # the foreign verdict landed post-anchor but is UNBOUND — that is
    # exactly why it can never be this worker's success
    verdicts = [e for e in events.read_chain(root)
                if e["event_type"] == "AUDIT_GO"]
    assert len(verdicts) == 1
    assert "session_binding" not in verdicts[0]["payload"]


def test_continuation_worker_never_adopts_a_foreign_post_anchor_verdict(
        env, monkeypatch):
    """Continuation (source resume) mode: worker A holds its exclusive
    claim-resume lease anchor, its child emits nothing, session B submits
    the same request. A returns 'failed', never 'ok', and A's own lease is
    not stranded."""
    root, repo, head, cfg = env
    codex_cfg = make_cfg(repo, root, role="codex")
    _publish_requested(root, cfg, repo, head)
    codex_watch.claim(root, codex_cfg, RID)   # a prior session that died
    _expire_lock(root, RID)                   # its lease has lapsed
    monkeypatch.setattr(codex_launcher, "_execute_bounded",
                        _foreign_submit(root, codex_cfg, head))

    outcome = _process_one(codex_cfg, root, "source_audit_resume")
    assert outcome != "ok"
    assert outcome == "failed"
    assert len(_failure_events(root, RID)) == 1
    assert locking.read_lock(root, RID) is None   # own lease released


def test_result_worker_never_adopts_a_foreign_post_anchor_verdict(
        env, monkeypatch):
    """Result mode: same property over the continuation/result lease."""
    root, repo, head, cfg = env
    codex_cfg = make_cfg(repo, root, role="codex")
    _drive_to_result_audit(root, cfg, repo, head)
    monkeypatch.setattr(
        codex_launcher, "_execute_bounded",
        _foreign_submit(root, codex_cfg, head, result_audit=True))

    outcome = _process_one(codex_cfg, root, "result_audit")
    assert outcome != "ok"
    assert outcome == "failed"
    assert len(_failure_events(root, RID)) == 1
    assert locking.read_lock(root, RID) is None   # own lease released


def test_submission_with_a_wrong_session_binding_is_rejected(env):
    """The other permitted outcome of the verdict's fixture: a session
    presenting a credential it cannot authenticate against the live claim
    lock is REFUSED outright — fail closed, nothing lands, the real
    claimant's lock survives."""
    root, repo, head, cfg = env
    codex_cfg = make_cfg(repo, root, role="codex")
    _publish_requested(root, cfg, repo, head)
    _event, lock = codex_watch.claim(root, codex_cfg, RID)

    with pytest.raises(CouncilError):
        codex_watch.submit_verdict(root, codex_cfg, make_verdict(head, RID),
                                   session_token="f" * 32)
    assert [e for e in events.read_chain(root)
            if e["event_type"] == "AUDIT_GO"] == []
    assert locking.read_lock(root, RID)["owner_token"] == lock.owner_token

    # the RIGHT one-time credential submits, and the terminal event records
    # exactly its binding — validated, hash-covered, never the raw secret
    event = codex_watch.submit_verdict(root, codex_cfg,
                                       make_verdict(head, RID),
                                       session_token=lock.owner_token)
    assert event["payload"]["session_binding"] == \
        codex_watch.session_binding_hash(RID, lock.owner_token)
    assert lock.owner_token not in json.dumps(event)
    assert locking.read_lock(root, RID) is None


def test_launcher_child_submits_with_the_workers_session_binding(
        env, tmp_path, monkeypatch):
    """End to end through a real bounded child: the one-time credential
    minted with the worker's claim flows through the sanitized environment
    into submit_verdict, and the terminal event carries the matching
    session binding — the full claim -> lease -> submit -> terminal-event
    -> process_one chain the verdict requires."""
    root, repo, head, cfg = env
    _install_fake_codex(tmp_path, monkeypatch, FAKE_GO_FROM_PROMPT)
    _publish_requested(root, cfg, repo, head)
    assert codex_launcher.main(["--once"]) == 0
    assert _state(root) == "go"                  # attributed success
    assert _failure_events(root) == []
    verdicts = [e for e in events.read_chain(root)
                if e["event_type"] == "AUDIT_GO"]
    assert len(verdicts) == 1
    binding = verdicts[0]["payload"]["session_binding"]
    assert isinstance(binding, str) and len(binding) == 64


# --------------------------------------------------------- A4: worker slots

def test_n_slots_admit_exactly_n_processes(env, tmp_path, monkeypatch):
    root, repo, head, cfg = env
    _install_fake_codex(tmp_path, monkeypatch, FAKE_NOOP)
    workers = 3
    names = [codex_launcher._slot_name(i) for i in range(workers)]
    assert names[0] == codex_launcher.LAUNCHER_LOCK   # slot 0 = legacy name
    assert len(set(names)) == workers

    held = []
    try:
        for index in range(workers):
            lock, refusal = codex_launcher._acquire_slot(root, workers, 60.0)
            assert lock is not None and refusal is None
            assert lock.name == names[index]     # first FREE slot each time
            held.append(lock)
        # the N+1th finds nothing free
        lock, refusal = codex_launcher._acquire_slot(root, workers, 60.0)
        assert lock is None and refusal is not None
        # ...so a real N+1th process refuses to start
        assert codex_launcher.main(["--once", "--workers",
                                    str(workers)]) == 1
        # freeing one slot readmits exactly one process
        locking.release(held[1])
        assert codex_launcher.main(["--once", "--workers",
                                    str(workers)]) == 0
    finally:
        for lock in held:
            locking.release(lock)


def test_workers_one_reproduces_the_singleton_refusal(env, tmp_path,
                                                      monkeypatch):
    """`--workers 1` (and the default) is exactly today's behavior: the
    historical `_codex_launcher` lock, and a second process refused."""
    root, repo, head, cfg = env
    _install_fake_codex(tmp_path, monkeypatch, FAKE_NOOP)
    held = locking.acquire(root, codex_launcher.LAUNCHER_LOCK, "codex",
                           "codex-launcher")
    try:
        assert codex_launcher.main(["--once", "--workers", "1"]) == 1
        assert codex_launcher.main(["--once"]) == 1          # default is 1
        # only widening the pool admits this process, on a DIFFERENT slot
        assert codex_launcher.main(["--once", "--workers", "2"]) == 0
        assert locking.read_lock(root, codex_launcher.LAUNCHER_LOCK)[
            "owner_token"] == held.owner_token
    finally:
        locking.release(held)


def test_slot_lock_is_released_when_the_process_exits(env, tmp_path,
                                                      monkeypatch):
    root, repo, head, cfg = env
    _install_fake_codex(tmp_path, monkeypatch, FAKE_NOOP)
    assert codex_launcher.main(["--once", "--workers", "2"]) == 0
    assert locking.read_lock(root, codex_launcher._slot_name(0)) is None
    assert locking.read_lock(root, codex_launcher._slot_name(1)) is None


# ------------------------------------------- the launcher-owned resume lease

def test_result_audit_resume_lease_is_released_on_success(env, tmp_path,
                                                          monkeypatch):
    """The claim-resume lease is acquired by the LAUNCHER and its token
    appears in no AUDIT_CLAIMED event, so the child cannot prove ownership
    of it. This process must release it on the success path — otherwise the
    lease survives until expiry and blocks the request."""
    root, repo, head, cfg = env
    _install_fake_codex(tmp_path, monkeypatch, FAKE_RESULT_APPROVED)
    _drive_to_result_audit(root, cfg, repo, head)
    assert codex_launcher.main(["--once"]) == 0
    assert _state(root) == "result_approved"
    # not stranded
    assert locking.read_lock(root, RID) is None
    # and released as our own lease, not through the LOGGED stale-clearance
    assert [e for e in events.read_chain(root)
            if e["payload"].get("operation") == "clear_stale_lock"] == []
    assert _failure_events(root) == []


def test_source_resume_lease_is_released_on_success(env, tmp_path,
                                                    monkeypatch):
    """Same for a resumed SOURCE audit: the child's submit refuses to
    release a lock it cannot prove it owns (it records why), and the
    launcher — which does own it — clears it."""
    root, repo, head, cfg = env
    _install_fake_codex(tmp_path, monkeypatch, FAKE_RESUME_GO)
    codex_cfg = make_cfg(repo, root, role="codex")
    _publish_requested(root, cfg, repo, head)
    codex_watch.claim(root, codex_cfg, RID)      # a session that then died
    # its lease expires, so the launcher may resume (logged clearance)
    import json as _json
    lock_file = storage.lock_path(root, RID)
    holder = _json.load(open(lock_file, encoding="utf-8"))
    holder["lease_expires_utc"] = "2000-01-01T00:00:00.000Z"
    with open(lock_file, "w", encoding="utf-8") as fh:
        _json.dump(holder, fh)

    assert codex_launcher.main(["--once"]) == 0
    assert _state(root) == "go"
    # the child could not prove ownership of the launcher's resume lease...
    refusals = [e for e in events.read_chain(root)
                if e["payload"].get("phase") == "claim_lock_release"]
    assert len(refusals) == 1
    # ...and the launcher released it anyway: nothing stranded
    assert locking.read_lock(root, RID) is None
    assert _failure_events(root) == []


def test_resume_lease_is_released_when_the_session_fails(env, tmp_path,
                                                         monkeypatch):
    """The failure path must not strand it either. A result audit rests in
    `result_audit`, not `claimed`, so the logged stale-claim clearance does
    not apply — the backstop release of this process's OWN lease is what
    keeps the request unblocked for the next worker."""
    root, repo, head, cfg = env
    _install_fake_codex(tmp_path, monkeypatch, FAKE_NOOP)
    _drive_to_result_audit(root, cfg, repo, head)
    assert codex_launcher.main(["--once"]) == 0
    assert len(_failure_events(root)) == 1
    assert _state(root) == "result_audit"
    assert locking.read_lock(root, RID) is None
    assert [e for e in events.read_chain(root)
            if e["payload"].get("operation") == "clear_stale_lock"] == []
    # the next worker can therefore pick the request straight back up
    _install_fake_codex(tmp_path, monkeypatch, FAKE_RESULT_APPROVED)
    assert codex_launcher.main(["--once"]) == 0
    assert _state(root) == "result_approved"


def test_second_worker_waits_on_a_live_resume_lease(env, tmp_path,
                                                    monkeypatch):
    """Two workers recovering the same claimed request: the resume lease is
    exclusive, so the second spawns nothing and records nothing."""
    root, repo, head, cfg = env
    marker = _install_fake_codex(tmp_path, monkeypatch, FAKE_RESUME_GO)
    codex_cfg = make_cfg(repo, root, role="codex")
    _drive_to_result_audit(root, cfg, repo, head)
    # worker A holds the claim-resume lease
    held = locking.acquire(root, RID, "codex", RID, kind="claim-resume")
    try:
        chain = events.read_chain(root)
        requests = state_machine.project(chain)
        outcome = codex_launcher.process_one(codex_cfg, root, chain, requests,
                                             RID, "result_audit", 60.0)
        assert outcome == "waiting"
        assert not os.path.exists(marker)
        assert _failure_events(root) == []
        assert locking.read_lock(root, RID)["owner_token"] == held.owner_token
    finally:
        locking.release(held)
