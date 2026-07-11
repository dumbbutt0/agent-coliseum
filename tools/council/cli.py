"""Council CLI.

    python3 -m tools.council.cli <subcommand> [...]

Subcommands: init, init-policy, status, show, verify-chain, rebuild-state,
publish-request, record, approve, cancel, clear-lock, milestone-status.

Human-gate operations (approve / experiment events) hard-require
--role human here AND at append time via SENDER_ALLOWED — defense in depth.
No content from any request or verdict file ever reaches a shell.
"""
from __future__ import annotations

import argparse
import json
import sys

from tools.council import (events, get_config, locking, policy, publish,
                           state_machine, storage)
from tools.council.schemas import (CouncilError, SchemaViolation,
                                   validate_commit, validate_request_id)


def _cfg(args):
    cfg = get_config(role=getattr(args, "role", None))
    return cfg, cfg.council_root


def cmd_init(args) -> int:
    _cfg_, root = _cfg(args)
    storage.ensure_layout(root)
    print(f"council layout ready at {root}")
    return 0


def cmd_init_policy(args) -> int:
    if args.role != "human":
        raise SchemaViolation("init-policy is an owner action: --role human")
    _cfg_, root = _cfg(args)
    path = policy.write_initial_policy(root)
    _pol, pol_hash = policy.load_policy(root)
    print(f"autonomy policy installed at {path}\npolicy_hash: {pol_hash}\n"
          "the file is immutable during autonomous operation — agents have "
          "no write API and hash drift pauses autonomy")
    return 0


def cmd_status(args) -> int:
    _cfg_, root = _cfg(args)
    chain = events.read_chain(root)
    requests = state_machine.project(chain)
    flags = state_machine.global_flags(requests)
    print(f"council: {root}")
    print(f"kill-switch: {storage.read_status(root)}; "
          f"STOP file: {'PRESENT' if storage.emergency_stop_reason(root) and 'STOP' in (storage.emergency_stop_reason(root) or '') else 'absent'}")
    print(f"chain: {len(chain)} events; flags: {flags}")
    for rid, req in sorted(requests.items()):
        print(f"  {rid}: {req['state']} "
              f"(commit {str(req['target_commit'])[:12]}, "
              f"cycles {req['audit_cycles']})")
    return 0


def cmd_show(args) -> int:
    _cfg_, root = _cfg(args)
    validate_request_id(args.request_id)
    request = publish.read_request(root, args.request_id)
    print(json.dumps(request, indent=2, sort_keys=True))
    return 0


def cmd_verify_chain(args) -> int:
    _cfg_, root = _cfg(args)
    report = events.verify_chain(root)
    if report.ok:
        print(f"chain OK: {report.length} events, head {report.head_hash}")
        return 0
    print(f"chain INVALID at event #{report.error_index}: {report.error}",
          file=sys.stderr)
    return 1


def cmd_rebuild_state(args) -> int:
    _cfg_, root = _cfg(args)
    chain = events.read_chain(root)
    head = chain[-1]["event_hash"] if chain else "0" * 64
    state = state_machine.rebuild(root, chain, head)
    print(f"state.json rebuilt: {state['chain_length']} events, "
          f"{len(state['requests'])} requests")
    return 0


def cmd_publish_request(args) -> int:
    cfg, root = _cfg(args)
    with open(args.file, encoding="utf-8") as fh:
        request = json.load(fh)
    event = publish.publish_request(root, cfg, request,
                                    reaudit=args.reaudit,
                                    autonomous=args.autonomous)
    print(f"published {request['request_id']} -> "
          f"requests/ready/{request['request_id']}.json "
          f"(event {event['event_id']}, {event['event_type']})")
    return 0


def cmd_record(args) -> int:
    cfg, root = _cfg(args)
    if args.role not in ("claude", "codex", "human"):
        raise SchemaViolation("--role required (claude|codex|human)")
    payload = json.loads(args.payload_json) if args.payload_json else {}
    if not isinstance(payload, dict):
        raise SchemaViolation("--payload-json must be a JSON object")
    event = events.append_event(root, cfg, args.type, args.role,
                                args.request_id, args.repository,
                                validate_commit(args.commit), payload)
    print(f"recorded {event['event_type']} (event {event['event_id']})")
    return 0


def cmd_approve(args) -> int:
    """HUMAN_APPROVAL_REQUIRED -> EXPERIMENT_APPROVED. Owner only; the
    approval binds to the exact commit and is refused on mismatch."""
    cfg, root = _cfg(args)
    if args.role != "human":
        raise SchemaViolation("approve is an owner action: --role human")
    validate_request_id(args.request_id)
    request = publish.read_request(root, args.request_id)
    if validate_commit(args.commit) != request["target_commit"]:
        raise SchemaViolation(
            f"approval commit {args.commit[:12]} does not match the "
            f"request's target_commit {request['target_commit'][:12]} — "
            "an approval for one commit must not apply to another")
    event = events.append_event(root, cfg, "EXPERIMENT_APPROVED", "human",
                                args.request_id, request["repository"],
                                request["target_commit"],
                                {"approved_by": "human",
                                 "approval_commit": args.commit})
    storage.append_log_md(root, "human", (
        f"**EXPERIMENT_APPROVED** for `{args.request_id}` at "
        f"`{args.commit}` (event `{event['event_id']}`)."))
    print(f"approved {args.request_id} at {args.commit[:12]} "
          f"(event {event['event_id']})")
    return 0


def cmd_approve_conditions(args) -> int:
    """Owner sign-off that a conditional verdict's conditions are met —
    the ONLY thing that unlocks CHANGE_INTEGRATED after
    AUDIT_GO_WITH_CONDITIONS. Binds to the exact commit."""
    cfg, root = _cfg(args)
    if args.role != "human":
        raise SchemaViolation(
            "approve-conditions is an owner action: --role human")
    validate_request_id(args.request_id)
    request = publish.read_request(root, args.request_id)
    if validate_commit(args.commit) != request["target_commit"]:
        raise SchemaViolation(
            f"approval commit {args.commit[:12]} does not match the "
            f"request's target_commit {request['target_commit'][:12]} — "
            "a condition sign-off for one commit must not apply to another")
    event = events.append_event(root, cfg, "CONDITIONS_SATISFIED", "human",
                                args.request_id, request["repository"],
                                request["target_commit"],
                                {"reviewed_by": "human",
                                 "approval_commit": args.commit,
                                 "note": args.note or ""})
    storage.append_log_md(root, "human", (
        f"**CONDITIONS_SATISFIED** for `{args.request_id}` at "
        f"`{args.commit}` (event `{event['event_id']}`)"
        + (f" — {args.note}" if args.note else "") + "."))
    print(f"conditions satisfied for {args.request_id} at {args.commit[:12]} "
          f"(event {event['event_id']}); integration is now unlocked")
    return 0


def cmd_cancel(args) -> int:
    cfg, root = _cfg(args)
    if args.role not in ("claude", "human"):
        raise SchemaViolation("cancel requires --role claude or human")
    request = publish.read_request(root, args.request_id)
    event = events.append_event(root, cfg, "REQUEST_CANCELED", args.role,
                                args.request_id, request["repository"],
                                request["target_commit"],
                                {"reason": args.reason})
    print(f"canceled {args.request_id} (event {event['event_id']})")
    return 0


def cmd_clear_lock(args) -> int:
    """The ONLY sanctioned stale-lock removal: logs first, then clears."""
    cfg, root = _cfg(args)
    if args.role not in ("claude", "codex", "human"):
        raise SchemaViolation("--role required")
    holder = locking.read_lock(root, args.name)
    if holder is None:
        print(f"no lock named {args.name!r}")
        return 0
    request_id = holder.get("request_id", args.name) \
        if isinstance(holder, dict) else args.name
    events.append_event(root, cfg, "WATCHER_ERROR", args.role, request_id,
                        cfg.repo_roots[0], "0" * 40,
                        {"operation": "clear_stale_lock",
                         "lock_name": args.name,
                         "previous_holder": holder,
                         "reason": args.reason})
    locking.clear_lock(root, args.name)
    print(f"cleared lock {args.name!r} (previous holder logged)")
    return 0


def cmd_milestone_status(args) -> int:
    _cfg_, root = _cfg(args)
    pol, _hash = policy.load_policy(root)
    chain = events.read_chain(root)
    reached, satisfied, missing = policy.milestone_status(chain, pol)
    print(f"society milestone reached: {reached}")
    for item in sorted(satisfied):
        print(f"  [x] {item}")
    for item in sorted(missing):
        print(f"  [ ] {item}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="council")
    parser.add_argument("--role", default=None,
                        help="claude|codex|human (or COUNCIL_ROLE env)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init")
    sub.add_parser("init-policy")
    sub.add_parser("status")
    sub.add_parser("verify-chain")
    sub.add_parser("rebuild-state")
    sub.add_parser("milestone-status")

    p = sub.add_parser("show")
    p.add_argument("request_id")

    p = sub.add_parser("publish-request")
    p.add_argument("--file", required=True)
    p.add_argument("--reaudit", action="store_true")
    p.add_argument("--autonomous", action="store_true")

    p = sub.add_parser("record")
    p.add_argument("--type", required=True)
    p.add_argument("--request-id", required=True)
    p.add_argument("--repository", required=True)
    p.add_argument("--commit", required=True)
    p.add_argument("--payload-json", default=None)

    p = sub.add_parser("approve")
    p.add_argument("request_id")
    p.add_argument("--commit", required=True)

    p = sub.add_parser("approve-conditions")
    p.add_argument("request_id")
    p.add_argument("--commit", required=True)
    p.add_argument("--note", default=None)

    p = sub.add_parser("cancel")
    p.add_argument("request_id")
    p.add_argument("--reason", required=True)

    p = sub.add_parser("clear-lock")
    p.add_argument("name")
    p.add_argument("--reason", required=True)

    args = parser.parse_args(argv)
    handlers = {"init": cmd_init, "init-policy": cmd_init_policy,
                "status": cmd_status, "show": cmd_show,
                "verify-chain": cmd_verify_chain,
                "rebuild-state": cmd_rebuild_state,
                "publish-request": cmd_publish_request,
                "record": cmd_record, "approve": cmd_approve,
                "approve-conditions": cmd_approve_conditions,
                "cancel": cmd_cancel, "clear-lock": cmd_clear_lock,
                "milestone-status": cmd_milestone_status}
    try:
        return handlers[args.command](args)
    except CouncilError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
