"""Claude-side passive watcher.

    python3 -m tools.council.claude_watch [--once] [--poll-seconds N]
                                          [--request-id ID]
                                          [--timeout-seconds N]

Sleeps between checks (default 10s); idle cost is one os.stat per poll — no
parsing until events.jsonl grows past the local cursor. Wakes only for
verdicts matching the current request, validates them hard, and then:

  AUDIT_BLOCKED           -> print the scoped findings (fixes required), stop.
                             A NEW Claude task decides to append FIX_STARTED —
                             this process never modifies source automatically.
  AUDIT_GO / _CONDITIONS  -> experiment tasks: POLICY_VALIDATION_REQUIRED,
                             evaluate the immutable autonomy policy: inside
                             policy -> AUTO_APPROVED (the sandboxed runner may
                             then start it — this watcher itself NEVER
                             launches experiments); outside policy ->
                             HUMAN_APPROVAL_REQUIRED, stop.
                             source tasks (event-pinned task_kind "source"):
                             append NOTHING — state remains `go`; the only
                             continuation is commit-bound CHANGE_INTEGRATED
                             recorded by the integration step.
  RESULT_APPROVED         -> NEXT_MILESTONE_READY (idempotent: skipped if the
                             chain already carries it), stop. The task is
                             complete; selection of the next one belongs to
                             the builder launcher, never to this watcher.
  RESULT_BLOCKED          -> print the scoped findings (fixes required), stop.

Root of trust (cycle-3 blocker): before ANY verdict is handled the mutable
request file is verified against the schema and the payload hash pinned by
its AUDIT_REQUESTED/READY_FOR_REAUDIT event via publish.verified_request —
the same routine the runner and policy-continue use. Any mismatch fails
closed: AUTONOMY_PAUSED immediately, before POLICY_VALIDATION_REQUIRED or
policy.evaluate, with coordinates from the pinned event.

Emergency stop (STATUS != active, or council/STOP exists) and the society
milestone stop the watcher safely. Three consecutive watcher errors ->
AUTONOMY_PAUSED and exit. A timeout exits cleanly (code 0).
"""
from __future__ import annotations

import argparse
import os
import sys
import time

from tools.council import (events, get_config, policy, publish,
                           state_machine, storage)
from tools.council.schemas import (CouncilError, SchemaViolation,
                                   VERDICT_EVENT_TYPES,
                                   compute_event_hash, validate_verdict)

SENDER = "claude"
MAX_CONSECUTIVE_ERRORS = 3

RESULT_VERDICT_EVENT_TYPES = frozenset({"RESULT_APPROVED", "RESULT_BLOCKED"})
WAKE_EVENT_TYPES = VERDICT_EVENT_TYPES | RESULT_VERDICT_EVENT_TYPES


class RequestIntegrityError(CouncilError):
    """The mutable request file contradicts its event-pinned root of trust.
    Unlike a malformed verdict (WATCHER_ERROR, retryable), this is treated
    as tampering: the watcher fails closed to AUTONOMY_PAUSED."""

    def __init__(self, failures: list, repository: str, target_commit: str):
        super().__init__("; ".join(failures))
        self.failures = failures
        self.repository = repository
        self.target_commit = target_commit


def _validate_verdict_event(root: str, cfg, event: dict,
                            request_id) -> tuple:
    """Every rejection reason the protocol names, in one place. Returns
    (request, repository, target_commit) on success, where the request is
    verified against the event-pinned payload hash and the coordinates come
    from the pinned publish event (cycle-3 blocker: NEVER from the mutable
    JSON). Raises RequestIntegrityError on tampering, CouncilError
    otherwise."""
    if event["sender"] != "codex":
        raise SchemaViolation(
            f"verdict event {event['event_id']} signed by "
            f"{event['sender']!r}, not codex")
    if request_id is not None and event["request_id"] != request_id:
        raise SchemaViolation(
            f"verdict for {event['request_id']!r}, expected {request_id!r}")
    verdict = event["payload"]
    validate_verdict(
        verdict,
        result_audit=event["event_type"] in RESULT_VERDICT_EVENT_TYPES)
    if verdict["request_id"] != event["request_id"]:
        raise SchemaViolation("verdict payload request_id differs from the "
                              "event's request_id")
    request, failures, repo, commit = publish.verified_request(
        root, cfg, event["request_id"])
    if failures:
        raise RequestIntegrityError(failures, repo, commit)
    if verdict["audited_commit"] != commit:
        raise SchemaViolation(
            f"audited_commit {verdict['audited_commit'][:12]} != pinned "
            f"target_commit {commit[:12]}")
    chain = events.read_chain(root)
    claimed = any(e["event_type"] == "AUDIT_CLAIMED"
                  and e["request_id"] == event["request_id"]
                  for e in chain)
    if not claimed:
        raise SchemaViolation("request was never claimed — verdict refused")
    report = events.verify_chain(root)
    if not report.ok:
        raise CouncilError(f"event chain invalid: {report.error}")
    return request, repo, commit


def _handle_blocked(event: dict) -> None:
    verdict = event["payload"]
    print(f"\nAUDIT_BLOCKED on {event['request_id']} at "
          f"{verdict['audited_commit'][:12]} — fixes are required.")
    print(f"summary: {verdict['summary']}")
    for i, blocker in enumerate(verdict.get("blockers", []), 1):
        print(f"  blocker {i}: {blocker}")
    for finding in verdict.get("findings", []):
        print(f"  finding: {finding}")
    print("this watcher makes no source changes; start a fresh Claude task "
          "to record FIX_STARTED and implement the fixes.")


def _handle_result_blocked(event: dict) -> None:
    verdict = event["payload"]
    print(f"\nRESULT_BLOCKED on {event['request_id']} at "
          f"{verdict['audited_commit'][:12]} — evidence fixes are required.")
    print(f"summary: {verdict['summary']}")
    for i, blocker in enumerate(verdict.get("blockers", []), 1):
        print(f"  blocker {i}: {blocker}")
    for finding in verdict.get("findings", []):
        print(f"  finding: {finding}")
    print("this watcher makes no changes; a fresh Claude task decides to "
          "record FIX_STARTED and address the result findings.")


def _handle_result_approved(root: str, cfg, event: dict, request: dict,
                            repo: str, commit: str) -> None:
    """The task's evidence is codex-approved — record NEXT_MILESTONE_READY
    so selection can proceed. Idempotent across watcher restarts."""
    rid = event["request_id"]
    chain = events.read_chain(root)
    already = any(e["event_type"] == "NEXT_MILESTONE_READY"
                  and e["request_id"] == rid for e in chain)
    if already:
        print(f"\nRESULT_APPROVED on {rid} — NEXT_MILESTONE_READY already "
              "recorded; nothing to do.")
        return
    events.append_event(root, cfg, "NEXT_MILESTONE_READY", SENDER, rid,
                        repo, commit,
                        {"completed_request": rid,
                         "task_id": request.get("task_id"),
                         "result_verdict_event_id": event["event_id"]})
    print(f"\nRESULT_APPROVED on {rid} at {commit[:12]} — "
          "NEXT_MILESTONE_READY recorded. Task selection belongs to the "
          "builder launcher; this watcher stops here.")


def _handle_source_go(event: dict, commit: str) -> None:
    """Source-task GO (task_kind pinned via the verified request): the
    experiment policy path does NOT apply. The watcher appends NOTHING —
    state remains `go`, from which the only legal continuation is a
    commit-bound CHANGE_INTEGRATED recorded by the integration step
    (builder launcher or `tools.autonomy.cli integrate`)."""
    verdict = event["payload"]
    print(f"\n{event['event_type']} on {event['request_id']} at "
          f"{commit[:12]} (source task) — summary: {verdict['summary']}")
    if event["event_type"] == "AUDIT_GO_WITH_CONDITIONS":
        print("conditions attached — owner review is required before any "
              "integration:")
        for cond in verdict.get("conditions", []):
            print(f"  - {cond}")
    print("no policy evaluation for source tasks; state remains `go`. "
          "Integration (fast-forward + CHANGE_INTEGRATED, bound to "
          f"{commit[:12]}) belongs to the integration step, never to this "
          "watcher.")


def _handle_go(root: str, cfg, event: dict, request: dict, repo: str,
               commit: str) -> None:
    """repo/commit are the PINNED publish-event coordinates from
    _validate_verdict_event, not fields of any mutable file."""
    rid = event["request_id"]
    verdict = event["payload"]
    print(f"\n{event['event_type']} on {rid} at {commit[:12]} — "
          f"summary: {verdict['summary']}")

    try:
        _pol, pol_hash = policy.load_policy(root)
    except SchemaViolation:
        pol_hash = None
    events.append_event(root, cfg, "POLICY_VALIDATION_REQUIRED", SENDER, rid,
                        repo, commit,
                        {"policy_hash": pol_hash,
                         "verdict_event_id": event["event_id"]})
    chain = events.read_chain(root)
    decision = policy.evaluate(root, cfg, request, event, chain)
    if decision.auto_approve:
        events.append_event(root, cfg, "AUTO_APPROVED", SENDER, rid, repo,
                            commit,
                            {"policy_hash": decision.policy_hash,
                             "conditions_checked": decision.checked,
                             "verdict_event_id": event["event_id"]})
        print("AUTO_APPROVED: every autonomy-policy condition holds "
              f"({len(decision.checked)} checked). The sandboxed runner may "
              "start this experiment; this watcher does not launch it.")
    else:
        events.append_event(root, cfg, "HUMAN_APPROVAL_REQUIRED", SENDER,
                            rid, repo, commit,
                            {"verdict_event_id": event["event_id"],
                             "verdict": verdict["verdict"],
                             "outside_policy_reasons": decision.reasons})
        print("HUMAN_APPROVAL_REQUIRED — outside the safe-autonomy policy:")
        for reason in decision.reasons:
            print(f"  - {reason}")
        print(f"owner: python3 -m tools.council.cli approve {rid} "
              f"--commit {commit} --role human")
    print("stopping; the experiment gate is closed to this process.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="claude_watch")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=10.0)
    parser.add_argument("--request-id", default=None)
    parser.add_argument("--timeout-seconds", type=float, default=None)
    args = parser.parse_args(argv)
    cfg = get_config(role=SENDER)
    root = cfg.council_root
    storage.ensure_layout(root)

    started = time.monotonic()
    cursor = storage.read_cursor(root, SENDER)
    consecutive_errors = 0
    events_file = storage.events_path(root)

    while True:
        stop_reason = storage.emergency_stop_reason(root)
        if stop_reason:
            print(f"claude_watch: emergency stop ({stop_reason}) — "
                  "recording AUTONOMY_PAUSED and stopping")
            try:
                events.pause_autonomy(
                    root, cfg, SENDER, args.request_id or "council-global",
                    cfg.repo_roots[0], "0" * 40, stop_reason)
            except CouncilError:
                pass
            return 0

        try:
            size = os.stat(events_file).st_size
        except OSError:
            size = 0
        if size > cursor["byte_offset"]:
            try:
                new = list(storage.read_events_from(
                    events_file, cursor["byte_offset"]))
                prev_hash = cursor["last_event_hash"]
                for offset, event in new:
                    if prev_hash is not None and \
                            event["previous_event_hash"] != prev_hash:
                        raise CouncilError(
                            f"chain break at {event.get('event_id')!r}: "
                            "does not extend the cursor's last event")
                    if compute_event_hash(event) != event["event_hash"]:
                        raise CouncilError(
                            f"bad event_hash at {event.get('event_id')!r}")
                    prev_hash = event["event_hash"]

                    etype = event["event_type"]
                    if etype == "AUTONOMY_MILESTONE_REACHED":
                        storage.write_cursor(root, SENDER, offset, prev_hash,
                                             event["event_id"])
                        print("claude_watch: society milestone reached — "
                              "watchers stop; owner briefing pending")
                        return 0
                    if etype == "AUTONOMY_PAUSED":
                        storage.write_cursor(root, SENDER, offset, prev_hash,
                                             event["event_id"])
                        print("claude_watch: AUTONOMY_PAUSED recorded by "
                              f"{event['sender']} — stopping "
                              f"({event['payload'].get('reason', '')})")
                        return 0
                    if etype not in WAKE_EVENT_TYPES or (
                            args.request_id is not None
                            and event["request_id"] != args.request_id):
                        storage.write_cursor(root, SENDER, offset, prev_hash,
                                             event["event_id"])
                        continue

                    try:
                        request, pin_repo, pin_commit = \
                            _validate_verdict_event(
                                root, cfg, event, args.request_id)
                    except RequestIntegrityError as exc:
                        # fail closed (cycle-3 blocker): a tampered request
                        # must never reach policy evaluation — pause NOW,
                        # with coordinates from the pinned event
                        storage.write_cursor(root, SENDER, offset, prev_hash,
                                             event["event_id"])
                        events.pause_autonomy(
                            root, cfg, SENDER, event["request_id"],
                            exc.repository, exc.target_commit,
                            "request file failed root-of-trust "
                            f"verification: {exc}")
                        print("claude_watch: request integrity failure — "
                              "AUTONOMY_PAUSED recorded; the owner decides "
                              "next:", file=sys.stderr)
                        for failure in exc.failures:
                            print(f"  - {failure}", file=sys.stderr)
                        return 1
                    except CouncilError as exc:
                        consecutive_errors += 1
                        print(f"claude_watch: invalid verdict ignored "
                              f"({exc})", file=sys.stderr)
                        events.append_event(
                            root, cfg, "WATCHER_ERROR", SENDER,
                            event["request_id"], event["repository"],
                            event["target_commit"],
                            {"reason": str(exc),
                             "offending_event_id": event.get("event_id")})
                        storage.write_cursor(root, SENDER, offset, prev_hash,
                                             event["event_id"])
                        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                            events.pause_autonomy(
                                root, cfg, SENDER, event["request_id"],
                                event["repository"], event["target_commit"],
                                f"{consecutive_errors} consecutive watcher "
                                "errors")
                            print("claude_watch: too many consecutive "
                                  "errors — AUTONOMY_PAUSED", file=sys.stderr)
                            return 1
                        continue

                    consecutive_errors = 0
                    storage.write_cursor(root, SENDER, offset, prev_hash,
                                         event["event_id"])
                    if etype == "AUDIT_BLOCKED":
                        _handle_blocked(event)
                    elif etype == "RESULT_BLOCKED":
                        _handle_result_blocked(event)
                    elif etype == "RESULT_APPROVED":
                        _handle_result_approved(root, cfg, event, request,
                                                pin_repo, pin_commit)
                    elif request.get("task_kind") == "source":
                        # kind is inside the event-pinned payload hash the
                        # verified request just passed — tamper-evident
                        _handle_source_go(event, pin_commit)
                    else:
                        _handle_go(root, cfg, event, request, pin_repo,
                                   pin_commit)
                    return 0
                cursor = storage.read_cursor(root, SENDER)
            except CouncilError as exc:
                print(f"claude_watch: chain error — {exc}", file=sys.stderr)
                try:
                    events.append_event(
                        root, cfg, "WATCHER_ERROR", SENDER,
                        args.request_id or "council-global",
                        cfg.repo_roots[0], "0" * 40, {"reason": str(exc)})
                except CouncilError:
                    pass
                return 1

        if args.once:
            print("claude_watch: --once pass complete; no matching verdict")
            return 0
        if args.timeout_seconds is not None and \
                time.monotonic() - started >= args.timeout_seconds:
            print("claude_watch: timeout reached — exiting cleanly "
                  "(protocol state unchanged)")
            return 0
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    sys.exit(main())
