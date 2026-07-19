"""Codex-role tooling: claim published audit requests and submit structured
verdicts. Codex never modifies source, never records fixes, never opens the
human gate, never runs the sequential experiment.

Usage (run by the Codex agent):
    python3 -m tools.council.codex_watch --list
    python3 -m tools.council.codex_watch --claim <request_id>
    python3 -m tools.council.codex_watch --submit <verdict.json>
    python3 -m tools.council.codex_watch [--once] [--poll-seconds N]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from tools.council import (events, get_config, locking, state_machine,
                           storage, strictjson)
from tools.council.schemas import (CouncilError, SchemaViolation,
                                   VERDICT_TO_EVENT, RESULT_VERDICT_TO_EVENT,
                                   compute_verdict_payload_hash,
                                   validate_verdict,
                                   validate_verdict_event_payload)

SENDER = "codex"


def list_ready(root: str) -> list:
    ready_dir = os.path.join(root, "requests", "ready")
    if not os.path.isdir(ready_dir):
        return []
    return sorted(f[:-5] for f in os.listdir(ready_dir)
                  if f.endswith(".json"))


def claim(root: str, cfg, request_id: str) -> dict:
    """Crash-safe (H5): O_EXCL lock -> move ready/ -> claimed/ ->
    AUDIT_CLAIMED, under a transaction journal. If the terminal append is
    refused (STOP mid-claim) or the process dies, txn.recover rolls the
    move back and releases the lock — never a stranded lock or a
    half-moved request without its event. A second claimant dies on the
    lock, never on a half-moved file."""
    import secrets

    from tools.council import txn
    txn.recover(root, cfg)  # finish any interrupted claim first
    ready_path = storage.safe_request_path(root, "ready", request_id)
    claimed_path = storage.safe_request_path(root, "claimed", request_id)
    if not os.path.exists(ready_path):
        raise SchemaViolation(f"request {request_id!r} is not in ready/")
    # Cycle-aware recovery (H5 cycle-2 fix): record how many AUDIT_CLAIMED
    # events already exist for this request so recovery can tell THIS
    # cycle's terminal event from a prior cycle's — an interrupted re-audit
    # must roll BACK even though older AUDIT_CLAIMED events exist. The owner
    # token is minted and journalled BEFORE the lock is acquired, so a crash
    # anywhere after acquisition leaves a journal that can release exactly
    # our lock (never another claimant's).
    prior_claimed = _count_claimed(events.read_chain(root), request_id)
    token = secrets.token_hex(16)
    t = txn.Txn.begin(root, "claim", request_id,
                      steps=["locked", "moved", "event"],
                      data={"owner_token": token,
                            "prior_claimed_count": prior_claimed})
    try:
        lock = locking.acquire(root, request_id, SENDER, request_id,
                               kind="claim", owner_token=token)
        t.mark("locked")
        with open(ready_path, "rb") as fh:
            request = strictjson.loads_strict(fh.read(), max_bytes=262_144)
        # Journal the intent to move BEFORE the rename: if we crash after the
        # rename but before recording it, recovery still knows the move was
        # ours to undo. The rollback guard (claimed exists AND ready absent)
        # makes a "moved"-marked-but-not-yet-renamed crash a safe no-op.
        t.mark("moved")
        os.rename(ready_path, claimed_path)
        event = events.append_event(
            root, cfg, "AUDIT_CLAIMED", SENDER, request_id,
            request["repository"], request["target_commit"],
            {"claimed_by": SENDER, "lock_file": f"locks/{request_id}.lock",
             "lock_holder": locking.read_lock(root, request_id)})
        t.mark("event")
        t.complete()
        return event, lock
    except CouncilError:
        # STOP mid-claim (or any refusal): compensate ONLY our own
        # transaction — never a global recover that could disturb a
        # concurrent claimant's in-flight journal — then re-raise.
        txn.compensate(root, cfg, t)
        raise


def _count_claimed(chain: list, request_id: str) -> int:
    return sum(1 for e in chain if e["event_type"] == "AUDIT_CLAIMED"
               and e["request_id"] == request_id)


def proven_owner_token(root: str, request_id: str,
                       chain: list | None = None) -> str | None:
    """Recover THIS request's claim-lock owner token from AUTHENTICATED
    evidence, or ``None`` when ownership cannot be proven.

    `claim()` mints the token, journals it, acquires the lock with it, and
    then pins the resulting lock body — token included — into the
    codex-signed AUDIT_CLAIMED event's `lock_holder`. That hash-chained
    event is therefore the authenticated record of who owns the claim lock
    for the current audit cycle; the launcher already recovers the token
    the same way (`codex_launcher.process_one`). We take the LAST such
    event so a re-audit cycle proves the CURRENT claim, never a stale one,
    and we additionally require the on-disk lock to still carry exactly
    that token: if a different holder now owns the lock (a launcher resume
    lease, or another worker's claim), the token proves nothing about the
    lock sitting on disk and we must not touch it.
    """
    chain = events.read_chain(root) if chain is None else chain
    claimed = None
    for event in chain:
        if event["request_id"] == request_id and \
                event["event_type"] == "AUDIT_CLAIMED" and \
                event["sender"] == SENDER:
            claimed = event
    if claimed is None:
        return None
    holder = claimed["payload"].get("lock_holder")
    token = holder.get("owner_token") if isinstance(holder, dict) else None
    if not isinstance(token, str) or not token:
        return None
    on_disk = locking.read_lock(root, request_id)
    if not isinstance(on_disk, dict) or on_disk.get("owner_token") != token:
        return None
    return token


def release_claim_lock(root: str, request_id: str,
                       chain: list | None = None) -> tuple:
    """Release the claim lock for `request_id` ONLY with proof of ownership.

    Returns ``(released, reason)``. A blind, tokenless release would let
    whichever concurrent worker finishes first delete another LIVE worker's
    claim lock (the lock IS the single claim authority), so when ownership
    cannot be proven we leave the lock completely untouched and report why.
    The lock then remains eligible for the existing lease-expiry recovery
    paths (`locking.lease_is_expired` + the launcher's logged
    `_clear_stale_claim_lock` gate) — the sanctioned, logged clearances.
    """
    if locking.read_lock(root, request_id) is None:
        return True, "no claim lock present"
    token = proven_owner_token(root, request_id, chain=chain)
    if token is None:
        return False, ("no authenticated AUDIT_CLAIMED evidence binds this "
                       "session to the on-disk claim lock")
    locking.release(locking.Lock(path=storage.lock_path(root, request_id),
                                 name=request_id, role=SENDER, root=root,
                                 owner_token=token))
    return True, "released by proven owner token"


# The states a request occupies AFTER a terminal verdict for its current
# cycle. In none of them may the request file still sit in claimed/ or a
# claim lock survive — EXCEPT result_audit, where the runner legitimately
# moves the file back to claimed/ for the result auditor.
_POST_VERDICT_STATES = frozenset({
    "blocked", "go", "policy_validation", "auto_approved", "awaiting_human",
    "approved", "experiment_running", "experiment_complete",
    "result_validation", "result_approved", "result_blocked", "integrated",
    "next_milestone_ready",
})

_TERMINAL_VERDICT_TYPES = ("AUDIT_BLOCKED", "AUDIT_GO",
                           "AUDIT_GO_WITH_CONDITIONS", "RESULT_APPROVED",
                           "RESULT_BLOCKED")


def finalize_incomplete(root: str, cfg) -> list:
    """Idempotent artifact recovery (cycle-4 audit blocker): for every
    request whose chain says a terminal verdict is authoritative but whose
    artifacts are incomplete — verdict JSON missing/stale, request file
    still in claimed/, or a surviving claim lock — finish the cleanup FROM
    THE CHAIN without appending any event. The verdict payload is taken
    from the last terminal verdict event, so recovery can never invent or
    duplicate a verdict. Returns the healed request ids. Invoked at
    submit_verdict entry and at codex_watch startup."""
    chain = events.read_chain(root)
    requests = state_machine.project(chain)
    healed = []
    for rid, req in sorted(requests.items()):
        if req["state"] not in _POST_VERDICT_STATES:
            continue
        last_verdict = None
        for event in chain:
            if event["request_id"] == rid and \
                    event["event_type"] in _TERMINAL_VERDICT_TYPES:
                last_verdict = event
        if last_verdict is None:
            continue
        acted = False
        verdict_path = storage.verdict_path(root, rid)
        want = last_verdict["payload"]
        # AUTHORITY REQUIRES VALIDITY (cycle-5 blocker): recovery may act
        # only on a terminal event whose nested verdict is fully
        # schema-valid and bound to this request/commit/event type. A
        # hash-chained but malformed historical event is NEVER promoted
        # into artifacts or lock clearance — fail closed, mutate nothing,
        # and leave migration to the owner.
        try:
            validate_verdict_event_payload(last_verdict)
        except CouncilError as exc:
            print(f"codex_watch: NOT finalizing {rid} — terminal event "
                  f"{last_verdict['event_id']} carries an invalid verdict "
                  f"payload ({exc}); artifacts untouched, owner-led "
                  "migration required", file=sys.stderr)
            continue
        try:
            with open(verdict_path, "rb") as fh:
                have = strictjson.loads_strict(fh.read(), max_bytes=1_048_576)
        except (OSError, ValueError, SchemaViolation):
            have = None
        if have != want:
            storage.atomic_write_json(verdict_path, want)
            acted = True
        claimed_path = storage.safe_request_path(root, "claimed", rid)
        complete_path = storage.safe_request_path(root, "complete", rid)
        if os.path.exists(claimed_path) and not os.path.exists(complete_path):
            os.rename(claimed_path, complete_path)
            acted = True
        if locking.read_lock(root, rid) is not None:
            released, why = release_claim_lock(root, rid, chain=chain)
            if released:
                acted = True
            else:
                # NEVER blind-unlink: the lock may be a live worker's claim.
                # finalize_incomplete appends no events by contract, so its
                # existing stderr channel is the record.
                print(f"codex_watch: NOT clearing the claim lock for {rid} "
                      f"— {why}; leaving it for the lease-expiry / logged "
                      "stale-lock recovery path", file=sys.stderr)
        if acted:
            healed.append(rid)
    return healed


def _inject_bindings(root, verdict, request, rid, result_audit) -> None:
    """Populate the H3 derivable binding fields from the verified request
    and the chain (the auditor never forges them)."""
    chain = events.read_chain(root)
    projection = state_machine.project(chain)
    pub = None
    src_pub = None
    handoff = request.get("task_kind") == "result_handoff"
    source_types = (("RESULT_HANDOFF_READY", "RESULT_FIX_READY")
                    if handoff else
                    ("AUDIT_REQUESTED", "READY_FOR_REAUDIT"))
    for e in chain:
        if e["request_id"] != rid:
            continue
        if e["event_type"] in source_types:
            src_pub = e
        if result_audit and e["event_type"] == "RESULT_AUDIT_REQUESTED":
            pub = e
    if not result_audit or handoff:
        pub = src_pub
    if pub is None or src_pub is None:
        raise SchemaViolation(
            f"cannot bind verdict for {rid}: missing publication event")
    verdict["auditor"] = "codex"
    verdict["audit_cycle"] = projection.get(rid, {}).get("audit_cycles")
    verdict["request_payload_hash"] = \
        src_pub["payload"].get("request_payload_hash")
    verdict["publication_event_id"] = pub["event_id"]
    verdict["publication_event_hash"] = pub["event_hash"]
    if result_audit:
        result_pub = next((e for e in reversed(chain)
                           if e["request_id"] == rid and
                           e["event_type"] == "RESULT_AUDIT_REQUESTED"), None)
        if result_pub is None:
            raise SchemaViolation(
                f"cannot bind result verdict for {rid}: missing result audit")
        for field in ("experiment_config_hash", "run_id", "run_dir",
                      "evidence_inventory_hash", "validation_report_hash"):
            verdict[field] = result_pub["payload"].get(field)


def submit_verdict(root: str, cfg, verdict: dict,
                   result_audit: bool = False) -> dict:
    """Append the verdict event (payload = the verdict), write
    verdicts/<id>.json, move claimed/ -> complete/, release the claim
    lock, mirror to log.md. Any prior incomplete finalization is healed
    first, so a retry after an artifact failure repairs the artifacts and
    then refuses the duplicate."""
    finalize_incomplete(root, cfg)
    verdict = dict(verdict)
    rid = verdict["request_id"]

    claimed_path = storage.safe_request_path(root, "claimed", rid)
    if not os.path.exists(claimed_path):
        raise SchemaViolation(
            f"request {rid!r} was never claimed — claim before submitting")
    with open(claimed_path, "rb") as fh:
        request = strictjson.loads_strict(fh.read(), max_bytes=262_144)
    if verdict["audited_commit"] != request["target_commit"]:
        raise SchemaViolation(
            f"audited_commit {verdict['audited_commit'][:12]} does not match "
            f"the request's target_commit {request['target_commit'][:12]}")

    # H2 completion + H3: stamp the v2 schema_version AND the derivable
    # authority-context bindings from the verified request + chain, so the
    # auditor supplies only its JUDGMENTS (verdict, findings, and for
    # result audits replay_result/counts/conclusion_scope). The append
    # boundary then cross-checks all of it against the chain.
    verdict["schema_version"] = ("result-verdict.v2" if result_audit
                                 else "source-verdict.v2")
    _inject_bindings(root, verdict, request, rid, result_audit)
    verdict["verdict_payload_hash"] = compute_verdict_payload_hash(verdict)
    validate_verdict(verdict, result_audit=result_audit)

    table = RESULT_VERDICT_TO_EVENT if result_audit else VERDICT_TO_EVENT
    if verdict["verdict"] not in table:
        raise SchemaViolation(
            f"verdict {verdict['verdict']!r} invalid for this audit kind")
    event = events.append_event(
        root, cfg, table[verdict["verdict"]], SENDER, rid,
        request["repository"], request["target_commit"], verdict)
    # The event append above is the AUTHORITY: the state machine refuses a
    # second verdict regardless of locks or file locations, so an absent
    # lock never permits one. Everything below is finalization — the claim
    # lock is ALWAYS released once the verdict is durable (finally), and
    # any artifact failure is recorded and recoverable WITHOUT a new
    # verdict via finalize_incomplete (cycle-4 audit blocker). The release
    # is COMPARE-AND-DELETE under proven ownership — with more than one
    # concurrent worker a tokenless release would delete whichever other
    # worker's live claim lock happened to be on disk.
    finalize_error = None
    lock_released, lock_reason = True, "not attempted"
    try:
        storage.atomic_write_json(storage.verdict_path(root, rid), verdict)
        os.rename(claimed_path,
                  storage.safe_request_path(root, "complete", rid))
    except OSError as exc:
        finalize_error = exc
    finally:
        lock_released, lock_reason = release_claim_lock(root, rid)
    if not lock_released:
        print(f"codex_watch: claim lock for {rid} NOT released — "
              f"{lock_reason}; left for the lease-expiry / logged "
              "stale-lock recovery path", file=sys.stderr)
        try:
            events.append_event(
                root, cfg, "WATCHER_ERROR", SENDER, rid,
                request["repository"], request["target_commit"],
                {"phase": "claim_lock_release", "reason": lock_reason,
                 "verdict_event_id": event["event_id"]})
        except CouncilError:
            pass
    if finalize_error is not None:
        try:
            events.append_event(
                root, cfg, "WATCHER_ERROR", SENDER, rid,
                request["repository"], request["target_commit"],
                {"phase": "verdict_finalization",
                 "reason": str(finalize_error),
                 "verdict_event_id": event["event_id"]})
        except CouncilError:
            pass
        raise CouncilError(
            f"verdict event {event['event_id']} IS authoritative, but "
            f"artifact finalization failed ({finalize_error}); recovery is "
            "idempotent — finalize_incomplete runs on the next submit or "
            "codex_watch start and never appends another verdict")

    blockers = "".join(f"\n  {i}. {b}" for i, b in
                       enumerate(verdict.get("blockers", []), 1))
    conditions = "".join(f"\n  - {c}" for c in verdict.get("conditions", []))
    try:
        storage.append_log_md(root, "codex", (
            f"**Verdict (structured): {verdict['verdict']}** on `{rid}` at "
            f"`{verdict['audited_commit']}` — mirror of `verdicts/{rid}.json`"
            f" + event `{event['event_id']}`.\n\n"
            f"- working_tree_clean: {verdict['working_tree_clean']}; "
            f"tests_observed: {verdict['tests_observed']}\n"
            f"- summary: {verdict['summary']}"
            + (f"\n- blockers:{blockers}" if verdict.get("blockers") else "")
            + (f"\n- conditions:{conditions}" if verdict.get("conditions")
               else "")))
    except (CouncilError, OSError) as exc:
        # the mirror is cosmetic; the verdict and artifacts are complete —
        # record the miss, never fail the submission over it
        try:
            events.append_event(
                root, cfg, "WATCHER_ERROR", SENDER, rid,
                request["repository"], request["target_commit"],
                {"phase": "verdict_log_mirror", "reason": str(exc),
                 "verdict_event_id": event["event_id"]})
        except CouncilError:
            pass
    return event


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="codex_watch")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--claim", metavar="REQUEST_ID")
    parser.add_argument("--submit", metavar="VERDICT_JSON")
    parser.add_argument("--result-audit", action="store_true",
                        help="submit as RESULT_APPROVED/RESULT_BLOCKED")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=10.0)
    parser.add_argument("--timeout-seconds", type=float, default=None)
    args = parser.parse_args(argv)
    cfg = get_config(role=SENDER)
    root = cfg.council_root
    storage.ensure_layout(root)

    try:
        from tools.council import txn
        for txn_id, outcome in txn.recover(root, cfg):
            print(f"codex_watch: recovered transaction {txn_id} ({outcome})")
        for rid in finalize_incomplete(root, cfg):
            print(f"codex_watch: finalized incomplete verdict artifacts "
                  f"for {rid}")
    except CouncilError as exc:
        print(f"codex_watch: startup recovery skipped — {exc}",
              file=sys.stderr)

    try:
        if args.list:
            for rid in list_ready(root):
                print(rid)
            return 0
        if args.claim:
            event, _lock = claim(root, cfg, args.claim)
            print(f"claimed {args.claim} (event {event['event_id']}); "
                  "lock stays until the verdict is submitted")
            return 0
        if args.submit:
            with open(args.submit, "rb") as fh:
                verdict = strictjson.loads_strict(fh.read(),
                                                  max_bytes=1_048_576)
            event = submit_verdict(root, cfg, verdict,
                                   result_audit=args.result_audit)
            print(f"verdict recorded: {event['event_type']} "
                  f"(event {event['event_id']})")
            return 0
    except CouncilError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1

    # passive poll: announce ready requests as they appear
    started = time.monotonic()
    seen: set = set()
    while True:
        if storage.emergency_stop_reason(root) or \
                not storage.status_allows(root, SENDER):
            print("codex_watch: emergency stop / STATUS pause — stopping")
            return 0
        flags = state_machine.global_flags(
            state_machine.project(events.read_chain(root)))
        if flags["milestone_reached"]:
            print("codex_watch: society milestone reached — stopping")
            return 0
        for rid in list_ready(root):
            if rid not in seen:
                seen.add(rid)
                print(f"ready for audit: {rid} (claim with --claim {rid})")
        if args.once:
            return 0
        if args.timeout_seconds is not None and \
                time.monotonic() - started >= args.timeout_seconds:
            print("codex_watch: timeout reached — exiting cleanly")
            return 0
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    sys.exit(main())
