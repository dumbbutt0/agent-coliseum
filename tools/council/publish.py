"""Claude-role operations: record build/fix progress and publish audit
requests through the atomic draft->ready lifecycle."""
from __future__ import annotations

import os

from tools.council import Config, events, git_state, state_machine, storage
from tools.council.schemas import (SchemaViolation, TransitionError,
                                   compute_request_payload_hash,
                                   validate_request)

SENDER = "claude"


def record_build_started(root: str, cfg: Config, request_id: str,
                         repository: str, target_commit: str,
                         payload: dict) -> dict:
    return events.append_event(root, cfg, "BUILD_STARTED", SENDER, request_id,
                               repository, target_commit, payload)


def record_fix_started(root: str, cfg: Config, request_id: str,
                       repository: str, target_commit: str,
                       originating_blocked_commit: str,
                       blockers_addressed: list, payload: dict = None) -> dict:
    body = dict(payload or {})
    body["originating_blocked_commit"] = originating_blocked_commit
    body["blockers_addressed"] = blockers_addressed
    return events.append_event(root, cfg, "FIX_STARTED", SENDER, request_id,
                               repository, target_commit, body)


def record_build_ready(root: str, cfg: Config, request_id: str,
                       repository: str, target_commit: str,
                       payload: dict) -> dict:
    return events.append_event(root, cfg, "BUILD_READY", SENDER, request_id,
                               repository, target_commit, payload)


def _check_scope_not_expanded(chain: list, request: dict) -> None:
    """Autonomous re-requests may narrow but never widen scope (bounded-loop
    protection: no automatic scope expansion)."""
    prior_scopes = [e["payload"].get("scope") for e in chain
                    if e["event_type"] in ("AUDIT_REQUESTED",
                                           "READY_FOR_REAUDIT")
                    and e["request_id"] == request["request_id"]
                    and e["payload"].get("scope")]
    if not prior_scopes:
        return
    new_items = set(map(str, request["scope"]))
    old_items = set(map(str, prior_scopes[-1]))
    grown = new_items - old_items
    if grown:
        raise SchemaViolation(
            f"automatic scope expansion refused: new scope items {sorted(grown)} "
            "— widening scope is an owner decision")


def publish_request(root: str, cfg: Config, request: dict,
                    reaudit: bool = False, autonomous: bool = False) -> dict:
    """Validate -> draft tmp -> fsync -> atomic rename to ready/ -> chain
    event (payload binds the file by hash) -> log.md mirror."""
    request = dict(request)
    request["request_payload_hash"] = compute_request_payload_hash(request)
    validate_request(request, cfg.repo_roots)

    repo = request["repository"]
    target = request["target_commit"]
    if not git_state.commit_exists(repo, target, cfg.repo_roots):
        raise SchemaViolation(f"target_commit {target[:12]} not in {repo}")
    if git_state.head_commit(repo, cfg.repo_roots) != target:
        raise SchemaViolation("target_commit must be the repository HEAD at "
                              "publish time")
    if request["require_clean_tree"] and not git_state.is_clean(
            repo, cfg.repo_roots):
        raise SchemaViolation("working tree is dirty — commit or stash "
                              "before publishing an audit request")

    chain = events.read_chain(root)
    if autonomous:
        _check_scope_not_expanded(chain, request)
    # bounded loops: at most five build-audit cycles per request
    cycles = state_machine.project(chain).get(
        request["request_id"], {"audit_cycles": 0})["audit_cycles"]
    if cycles >= 5:
        raise TransitionError(
            f"request {request['request_id']!r} already ran {cycles} "
            "build-audit cycles — the bounded-loop limit is five; "
            "escalate to the owner")

    storage.ensure_layout(root)
    rid = request["request_id"]
    ready_path = storage.safe_request_path(root, "ready", rid)
    claimed_path = storage.safe_request_path(root, "claimed", rid)
    complete_path = storage.safe_request_path(root, "complete", rid)
    for existing in (ready_path, claimed_path, complete_path):
        if os.path.exists(existing):
            raise SchemaViolation(
                f"request {rid!r} already exists at {existing} — request ids "
                "are single-use")

    draft_tmp = storage.safe_request_path(root, "draft", rid) + ".tmp"
    with open(draft_tmp, "w", encoding="utf-8") as fh:
        from tools.council.schemas import canonical_json
        fh.write(canonical_json(request) + "\n")
        try:
            fh.flush()
            os.fsync(fh.fileno())
        except OSError:
            pass
    os.rename(draft_tmp, ready_path)

    event = events.append_event(
        root, cfg, "READY_FOR_REAUDIT" if reaudit else "AUDIT_REQUESTED",
        SENDER, rid, repo, target,
        {"request_payload_hash": request["request_payload_hash"],
         "request_file": f"requests/ready/{rid}.json",
         "scope": request["scope"],
         "expected_test_command": request["expected_test_command"],
         "expected_test_count": request["expected_test_count"],
         "blockers_addressed": request["blockers_addressed"]})

    scope_lines = "\n".join(f"  {i}. {s}" for i, s in
                            enumerate(request["scope"], 1))
    storage.append_log_md(root, "claude", (
        f"**{'Re-audit' if reaudit else 'Audit'} request published "
        f"(structured): `{rid}`** — mirror of "
        f"`requests/ready/{rid}.json` + event `{event['event_id']}` in "
        "`events.jsonl` (authoritative).\n\n"
        f"- target_commit: `{target}` (clean tree required)\n"
        f"- expected: `{request['expected_test_command']}` -> "
        f"**{request['expected_test_count']} passed**\n"
        f"- originating blocked commit: "
        f"`{request['originating_blocked_commit']}`\n"
        f"- scope:\n{scope_lines}\n"
        f"- live_experiment_allowed: false; human_approval_required: "
        f"{str(request['human_approval_required']).lower()}\n\n"
        "Codex: claim via `python3 -m tools.council.codex_watch --claim "
        f"{rid}` (or atomically create `locks/{rid}.lock` and move the "
        "request to `requests/claimed/`), audit the exact commit, then "
        "submit a structured verdict."))
    return event


def read_request(root: str, request_id: str) -> dict:
    """Find the request JSON in ready/claimed/complete (drafts don't count)."""
    import json
    for bucket in ("ready", "claimed", "complete"):
        path = storage.safe_request_path(root, bucket, request_id)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
    raise SchemaViolation(f"request {request_id!r} not found in "
                          "ready/claimed/complete")
