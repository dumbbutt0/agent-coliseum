"""Autonomy CLI (claude role).

    python3 -m tools.autonomy.cli validate-roadmap [--path P]
    python3 -m tools.autonomy.cli resume [--json] [--roadmap P]
    python3 -m tools.autonomy.cli preflight [--request-id ID]
    python3 -m tools.autonomy.cli policy-continue --request-id ID
    python3 -m tools.autonomy.cli run-task --request-id ID --config FILE

Every command is deterministic; only policy-continue and run-task append
council events, and both refuse unless the exact preconditions hold.
"""
from __future__ import annotations

import argparse
import sys

from tools.autonomy import default_roadmap_path, guard, resume, runner
from tools.autonomy import roadmap as roadmap_mod
from tools.council import events, get_config, policy, publish, state_machine
from tools.council.schemas import CouncilError

SENDER = "claude"


def cmd_validate_roadmap(cfg, args) -> int:
    pol, _ = policy.load_policy(cfg.council_root)
    path = args.path or default_roadmap_path(cfg.council_root)
    doc, rm_hash = roadmap_mod.load_roadmap(path, pol)
    active = roadmap_mod.active_task(doc)
    print(f"roadmap OK: {path}")
    print(f"roadmap_hash: {rm_hash}")
    print(f"tasks: {len(doc['tasks'])}; active: "
          f"{active['task_id'] if active else None}; eligible: "
          f"{[t['task_id'] for t in roadmap_mod.eligible_tasks(doc)]}")
    return 0


def cmd_resume(cfg, args) -> int:
    if args.json:
        print(resume.main_json(cfg, args.roadmap))
    else:
        print(resume.render(resume.compute_resume(cfg, args.roadmap)))
    return 0


def cmd_preflight(cfg, args) -> int:
    repo = cfg.repo_roots[0]
    expect = None
    if args.request_id:
        request = publish.read_request(cfg.council_root, args.request_id)
        repo = request["repository"]
        expect = request["target_commit"]
    report = guard.preflight(cfg, repo=repo, expect_head=expect,
                             roadmap_path=args.roadmap)
    print(f"preflight: {'OK' if report.ok else 'FAILED'}")
    for f in report.failures:
        print(f"  - {f}")
    if report.roadmap_hash:
        print(f"roadmap_hash: {report.roadmap_hash}")
    if report.policy_hash:
        print(f"policy_hash: {report.policy_hash}")
    return 0 if report.ok else 1


def cmd_policy_continue(cfg, args) -> int:
    """Deterministic recovery for a request stuck at `go` (verdict consumed
    but validation never ran) or `policy_validation` (crash mid-handler).
    Replays exactly what claude_watch._handle_go would have done."""
    root = cfg.council_root
    rid = args.request_id
    chain = events.read_chain(root)
    requests = state_machine.project(chain)
    state = requests.get(rid, {}).get("state")
    if state not in ("go", "policy_validation"):
        print(f"refused: request {rid!r} is in state {state!r} — "
              "policy-continue only applies to go/policy_validation",
              file=sys.stderr)
        return 1
    verdicts = [e for e in chain
                if e["request_id"] == rid and e["event_type"] in
                ("AUDIT_GO", "AUDIT_GO_WITH_CONDITIONS")]
    if not verdicts:
        print("refused: no GO verdict event found in the chain",
              file=sys.stderr)
        return 1
    verdict_event = verdicts[-1]
    # same root of trust as the runner: the mutable request file must match
    # the event-pinned payload hash before policy evaluation reads it
    request, integrity_failures, repo, commit = runner.verified_request(
        cfg, rid)
    if integrity_failures:
        print("refused: request file failed integrity verification:",
              file=sys.stderr)
        for f in integrity_failures:
            print(f"  - {f}", file=sys.stderr)
        guard.pause(cfg, rid, repo, commit, integrity_failures)
        return 1
    if request.get("task_kind") == "source":
        print(f"refused: request {rid!r} is a source task — there is no "
              "policy path; the continuation from `go` is commit-bound "
              "CHANGE_INTEGRATED via the integration step", file=sys.stderr)
        return 1

    if state == "go":
        try:
            _pol, pol_hash = policy.load_policy(root)
        except Exception:
            pol_hash = None
        events.append_event(root, cfg, "POLICY_VALIDATION_REQUIRED", SENDER,
                            rid, repo, commit,
                            {"policy_hash": pol_hash,
                             "verdict_event_id": verdict_event["event_id"]})
        chain = events.read_chain(root)

    decision = policy.evaluate(root, cfg, request, verdict_event, chain)
    if decision.auto_approve:
        events.append_event(root, cfg, "AUTO_APPROVED", SENDER, rid, repo,
                            commit,
                            {"policy_hash": decision.policy_hash,
                             "conditions_checked": decision.checked,
                             "verdict_event_id": verdict_event["event_id"]})
        print(f"AUTO_APPROVED: {len(decision.checked)} conditions checked, "
              "all hold. Run the task via run-task.")
    else:
        events.append_event(root, cfg, "HUMAN_APPROVAL_REQUIRED", SENDER,
                            rid, repo, commit,
                            {"verdict_event_id": verdict_event["event_id"],
                             "verdict": verdict_event["payload"].get(
                                 "verdict"),
                             "outside_policy_reasons": decision.reasons})
        print("HUMAN_APPROVAL_REQUIRED — outside the safe-autonomy policy:")
        for reason in decision.reasons:
            print(f"  - {reason}")
    return 0


def cmd_run_task(cfg, args) -> int:
    return runner.run_task(cfg, args.request_id, args.config,
                           roadmap_path=args.roadmap)


def cmd_experiment_loop(cfg, args) -> int:
    """M7d: one idempotent step of the autonomous experiment loop (propose the
    next registered experiment, or advance the in-flight one). Stops itself on
    STOP/MANUAL; the immutable policy decides whether anything auto-runs."""
    from tools.autonomy import experiment_loop
    print(experiment_loop.advance(cfg, roadmap_path=args.roadmap))
    return 0


def cmd_codex_launcher(cfg, args) -> int:
    """Delegates to the launcher's own entrypoint, which builds a
    codex-role config and holds the single-instance lock itself."""
    from tools.autonomy import codex_launcher
    argv = ["--poll-seconds", str(args.poll_seconds),
            "--audit-timeout-seconds", str(args.audit_timeout_seconds)]
    if args.once:
        argv.append("--once")
    if args.timeout_seconds is not None:
        argv += ["--timeout-seconds", str(args.timeout_seconds)]
    if args.max_launches is not None:
        argv += ["--max-launches", str(args.max_launches)]
    return codex_launcher.main(argv)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="autonomy")
    sub = parser.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("validate-roadmap")
    s.add_argument("--path", default=None)
    s.set_defaults(fn=cmd_validate_roadmap)

    s = sub.add_parser("resume")
    s.add_argument("--json", action="store_true")
    s.add_argument("--roadmap", default=None)
    s.set_defaults(fn=cmd_resume)

    s = sub.add_parser("preflight")
    s.add_argument("--request-id", default=None)
    s.add_argument("--roadmap", default=None)
    s.set_defaults(fn=cmd_preflight)

    s = sub.add_parser("policy-continue")
    s.add_argument("--request-id", required=True)
    s.set_defaults(fn=cmd_policy_continue)

    s = sub.add_parser("run-task")
    s.add_argument("--request-id", required=True)
    s.add_argument("--config", required=True,
                   help="frozen experiment config JSON (sha256 must equal "
                        "the request's experiment_config_hash)")
    s.add_argument("--roadmap", default=None)
    s.set_defaults(fn=cmd_run_task)

    s = sub.add_parser("codex-launcher")
    s.add_argument("--once", action="store_true")
    s.add_argument("--poll-seconds", type=float, default=15.0)
    s.add_argument("--timeout-seconds", type=float, default=None)
    s.add_argument("--audit-timeout-seconds", type=float, default=3600.0)
    s.add_argument("--max-launches", type=int, default=None)
    s.set_defaults(fn=cmd_codex_launcher)

    s = sub.add_parser("experiment-loop")
    s.add_argument("--roadmap", default=None)
    s.set_defaults(fn=cmd_experiment_loop)

    args = parser.parse_args(argv)
    cfg = get_config(role=SENDER)
    try:
        return args.fn(cfg, args)
    except (CouncilError, roadmap_mod.RoadmapError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
