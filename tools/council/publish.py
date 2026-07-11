"""Claude-role operations: record build/fix progress and publish audit
requests through the atomic draft->ready lifecycle."""
from __future__ import annotations

import os

from tools.council import Config, events, git_state, state_machine, storage
from tools.council.schemas import (CouncilError, SchemaViolation,
                                   TransitionError,
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
    projection = state_machine.project(chain)
    # bounded loops: at most five build-audit cycles per request
    cycles = projection.get(
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

    # a refused transition must never leave an unpinned orphan in ready/
    # (2026-07-11 wart: the rename used to precede this check): verify the
    # projected state allows the publish event BEFORE any file lands
    event_type = "READY_FOR_REAUDIT" if reaudit else "AUDIT_REQUESTED"
    allowed_from, _to = state_machine.TRANSITIONS[event_type]
    projected_state = projection.get(rid, {"state": "none"})["state"]
    if projected_state not in allowed_from:
        raise TransitionError(
            f"{event_type} not allowed from state {projected_state!r} for "
            f"request {rid!r} (allowed from: {sorted(allowed_from)})")

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

    try:
        event = events.append_event(
            root, cfg, event_type, SENDER, rid, repo, target,
            {"request_payload_hash": request["request_payload_hash"],
             "request_file": f"requests/ready/{rid}.json",
             "scope": request["scope"],
             "expected_test_command": request["expected_test_command"],
             "expected_test_count": request["expected_test_count"],
             "blockers_addressed": request["blockers_addressed"]})
    except (CouncilError, OSError):
        # the append is the authority; roll the file back so no unpinned
        # request ever sits in ready/. A crash/OSError mid-append (not only a
        # CouncilError refusal) must trigger the same rollback — but ONLY if
        # the authority event did NOT land: if the event is durably in the
        # chain and a LATER step failed, the request IS published and the
        # ready file must stay (all-or-nothing, both directions).
        landed = any(e["event_type"] == event_type and e["request_id"] == rid
                     for e in events.read_chain(root))
        if not landed:
            try:
                os.unlink(ready_path)
            except OSError:
                pass
        raise

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
    from tools.council.strictjson import loads_strict
    for bucket in ("ready", "claimed", "complete"):
        path = storage.safe_request_path(root, bucket, request_id)
        if os.path.exists(path):
            with open(path, "rb") as fh:
                return loads_strict(fh.read(), max_bytes=262_144)
    raise SchemaViolation(f"request {request_id!r} not found in "
                          "ready/claimed/complete")


def verified_request(root: str, cfg: Config, request_id: str) -> tuple:
    """(request, failures, authoritative_repo, authoritative_commit).

    The request JSON in ready/claimed/complete is a MUTABLE lifecycle
    file — it is trusted only when (a) it validates against the full
    request schema including its own canonical request_payload_hash, and
    (b) that hash equals the hash pinned by the authoritative
    AUDIT_REQUESTED/READY_FOR_REAUDIT event for the same request and
    commit. Post-audit edits — with a stale OR a freshly recomputed
    self-consistent hash — fail (b). The authoritative coordinates come
    from the pinned EVENT, not the file.

    Council-level on purpose (cycle-3 audit blocker): EVERY policy
    evaluation path — the automatic claude_watch handler, manual
    policy-continue, and the runner — must obtain the request through
    this one routine; tools/autonomy delegates here rather than the
    watcher importing upward."""
    request = read_request(root, request_id)
    failures: list = []
    chain = events.read_chain(root)  # hash-verified end to end
    pins = [e for e in chain
            if e["request_id"] == request_id
            and e["event_type"] in ("AUDIT_REQUESTED", "READY_FOR_REAUDIT")]
    if not pins:
        failures.append(
            "no publish event pins this request — the file has no "
            "authoritative root of trust")
        return (request, failures, request.get("repository", ""),
                request.get("target_commit", "0" * 40))
    pin = pins[-1]
    repo = pin["repository"]
    commit = pin["target_commit"]
    try:
        validate_request(request, cfg.repo_roots)
    except CouncilError as exc:
        failures.append(f"request file no longer validates: {exc}")
    pinned_hash = pin["payload"].get("request_payload_hash")
    if request.get("request_payload_hash") != pinned_hash:
        failures.append(
            "request file payload hash "
            f"{str(request.get('request_payload_hash'))[:12]} does not "
            f"match the hash pinned by event {pin['event_id']} "
            f"({str(pinned_hash)[:12]}) — the file was modified after the "
            "audit request was published")
    if request.get("target_commit") != commit:
        failures.append(
            "request file target_commit differs from the pinned event — "
            "post-audit tampering")
    return request, failures, repo, commit
