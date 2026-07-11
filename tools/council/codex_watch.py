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

from tools.council import events, get_config, locking, state_machine, storage
from tools.council.schemas import (CouncilError, SchemaViolation,
                                   VERDICT_TO_EVENT, RESULT_VERDICT_TO_EVENT,
                                   compute_verdict_payload_hash,
                                   validate_verdict)

SENDER = "codex"


def list_ready(root: str) -> list:
    ready_dir = os.path.join(root, "requests", "ready")
    if not os.path.isdir(ready_dir):
        return []
    return sorted(f[:-5] for f in os.listdir(ready_dir)
                  if f.endswith(".json"))


def claim(root: str, cfg, request_id: str) -> dict:
    """Atomic: O_EXCL lock -> move ready/ -> claimed/ -> AUDIT_CLAIMED.
    A second claimant dies on the lock, never on a half-moved file."""
    ready_path = storage.safe_request_path(root, "ready", request_id)
    claimed_path = storage.safe_request_path(root, "claimed", request_id)
    if not os.path.exists(ready_path):
        raise SchemaViolation(f"request {request_id!r} is not in ready/")
    lock = locking.acquire(root, request_id, SENDER, request_id)
    with open(ready_path, encoding="utf-8") as fh:
        request = json.load(fh)
    os.rename(ready_path, claimed_path)
    return events.append_event(
        root, cfg, "AUDIT_CLAIMED", SENDER, request_id,
        request["repository"], request["target_commit"],
        {"claimed_by": SENDER, "lock_file": f"locks/{request_id}.lock",
         "lock_holder": locking.read_lock(root, request_id)}), lock


def submit_verdict(root: str, cfg, verdict: dict,
                   result_audit: bool = False) -> dict:
    """Append the verdict event (payload = the verdict), write
    verdicts/<id>.json, move claimed/ -> complete/, mirror to log.md."""
    verdict = dict(verdict)
    verdict["verdict_payload_hash"] = compute_verdict_payload_hash(verdict)
    validate_verdict(verdict, result_audit=result_audit)
    rid = verdict["request_id"]

    claimed_path = storage.safe_request_path(root, "claimed", rid)
    if not os.path.exists(claimed_path):
        raise SchemaViolation(
            f"request {rid!r} was never claimed — claim before submitting")
    with open(claimed_path, encoding="utf-8") as fh:
        request = json.load(fh)
    if verdict["audited_commit"] != request["target_commit"]:
        raise SchemaViolation(
            f"audited_commit {verdict['audited_commit'][:12]} does not match "
            f"the request's target_commit {request['target_commit'][:12]}")

    table = RESULT_VERDICT_TO_EVENT if result_audit else VERDICT_TO_EVENT
    if verdict["verdict"] not in table:
        raise SchemaViolation(
            f"verdict {verdict['verdict']!r} invalid for this audit kind")
    event = events.append_event(
        root, cfg, table[verdict["verdict"]], SENDER, rid,
        request["repository"], request["target_commit"], verdict)
    storage.atomic_write_json(storage.verdict_path(root, rid), verdict)
    os.rename(claimed_path, storage.safe_request_path(root, "complete", rid))

    blockers = "".join(f"\n  {i}. {b}" for i, b in
                       enumerate(verdict.get("blockers", []), 1))
    conditions = "".join(f"\n  - {c}" for c in verdict.get("conditions", []))
    storage.append_log_md(root, "codex", (
        f"**Verdict (structured): {verdict['verdict']}** on `{rid}` at "
        f"`{verdict['audited_commit']}` — mirror of `verdicts/{rid}.json` + "
        f"event `{event['event_id']}`.\n\n"
        f"- working_tree_clean: {verdict['working_tree_clean']}; "
        f"tests_observed: {verdict['tests_observed']}\n"
        f"- summary: {verdict['summary']}"
        + (f"\n- blockers:{blockers}" if verdict.get("blockers") else "")
        + (f"\n- conditions:{conditions}" if verdict.get("conditions")
           else "")))
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
            with open(args.submit, encoding="utf-8") as fh:
                verdict = json.load(fh)
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
