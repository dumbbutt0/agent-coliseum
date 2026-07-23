"""The authoritative append-only, hash-chained event log.

Every append: events-lock -> emergency-stop check -> role check -> replay ->
transition check -> write one canonical line -> refresh state.json. There is
no API that edits or deletes an event, ever.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

from tools.council import Config, locking, state_machine, storage
from tools.council.schemas import (CONTROL_BOOTSTRAP_EVENT_TYPES, ChainError,
                                   CouncilError, GENESIS_HASH,
                                   HUMAN_TOKEN_REQUIRED_EVENT_TYPES,
                                   STOP_EXEMPT_EVENT_TYPES, canonical_json,
                                   compute_event_hash, protocol_version,
                                   validate_event)


import re as _re

_EVENT_ID_RE = _re.compile(r"^\d{6}-[0-9a-f]{8}$")


@dataclass
class ChainReport:
    ok: bool
    length: int
    head_hash: str
    error: str | None = None
    error_index: int | None = None
    suffix_incomplete: bool = False
    torn_bytes: int = 0

    @property
    def healthy(self) -> bool:
        """H4: a chain is healthy for AUTHORITY decisions only when it is
        fully valid AND has no torn/incomplete suffix. Reads may still use
        a valid prefix (ok), but every authority consumer requires this."""
        return self.ok and not self.suffix_incomplete


def read_chain(root: str, verify: bool = True) -> list:
    """All complete events, optionally verifying every hash, link, seq,
    and id-uniqueness. A torn trailing line makes verify=True raise (a
    valid prefix with an incomplete suffix is NOT a safe authority chain)."""
    events = []
    seen_ids = set()
    prev_hash = GENESIS_HASH
    complete, tail = storage.read_events_with_tail(storage.events_path(root))
    for event in complete:
        if verify:
            _verify_one(event, prev_hash, len(events), seen_ids)
        events.append(event)
        seen_ids.add(event.get("event_id"))
        prev_hash = event["event_hash"]
    if verify and tail["torn"]:
        raise ChainError(
            f"chain has a torn trailing line ({tail['torn_bytes']} bytes) "
            "after a valid prefix — refusing (repair-tail required)")
    return events


def _verify_one(event: dict, prev_hash: str, index: int,
                seen_ids: set = None) -> None:
    eid = event.get("event_id")
    if event.get("previous_event_hash") != prev_hash:
        raise ChainError(
            f"event #{index} ({eid!r}): previous_event_hash "
            f"{event.get('previous_event_hash')!r} does not chain to "
            f"{prev_hash!r}")
    if not isinstance(eid, str) or not _EVENT_ID_RE.match(eid):
        raise ChainError(
            f"event #{index}: event_id {eid!r} is malformed "
            "(expected NNNNNN-xxxxxxxx)")
    if int(eid[:6]) != index + 1:
        raise ChainError(
            f"event #{index}: event_id sequence {eid[:6]} does not match "
            f"chain position {index + 1}")
    if seen_ids is not None and eid in seen_ids:
        raise ChainError(f"event #{index}: duplicate event_id {eid!r}")
    if compute_event_hash(event) != event.get("event_hash"):
        raise ChainError(
            f"event #{index} ({eid!r}): event_hash does not match canonical "
            "content — chain tampered or torn")


def verify_chain(root: str) -> ChainReport:
    events = []
    seen_ids = set()
    prev_hash = GENESIS_HASH
    complete, tail = storage.read_events_with_tail(storage.events_path(root))
    try:
        for event in complete:
            _verify_one(event, prev_hash, len(events), seen_ids)
            events.append(event)
            seen_ids.add(event.get("event_id"))
            prev_hash = event["event_hash"]
    except (ChainError, ValueError, KeyError) as exc:
        return ChainReport(ok=False, length=len(events), head_hash=prev_hash,
                           error=str(exc), error_index=len(events))
    return ChainReport(ok=True, length=len(events), head_hash=prev_hash,
                       suffix_incomplete=tail["torn"],
                       torn_bytes=tail["torn_bytes"])


def head(root: str) -> tuple:
    """(sequence_length, head_hash) — GENESIS_HASH for an empty chain."""
    events = read_chain(root, verify=False)
    return len(events), (events[-1]["event_hash"] if events else GENESIS_HASH)


def build_event(event_type: str, sender: str, request_id: str,
                repository: str, target_commit: str, payload: dict,
                seq: int, previous_event_hash: str) -> dict:
    event = {
        "protocol_version": protocol_version(),
        "event_id": f"{seq:06d}-{uuid.uuid4().hex[:8]}",
        "event_type": event_type,
        "request_id": request_id,
        "sender": sender,
        "timestamp_utc": storage.utc_now(),
        "repository": repository,
        "target_commit": target_commit,
        "payload": payload,
        "previous_event_hash": previous_event_hash,
    }
    event["event_hash"] = compute_event_hash(event)
    return event


def append_event(root: str, cfg: Config, event_type: str, sender: str,
                 request_id: str, repository: str, target_commit: str,
                 payload: dict, enrollment_token: str = None) -> dict:
    """The one and only writer of events.jsonl. enrollment_token is the
    NON-PERSISTED bootstrap proof required exclusively by
    HUMAN_IDENTITY_INITIALIZED (verified against the root-owned anchor
    inside _verify_human_token; it never enters the chain)."""
    lock = locking.acquire_events_lock(root, sender, request_id)
    try:
        # emergency stop precedes every transition; only the events that
        # RECORD a stop may pass while it is engaged. Bootstrap/control
        # events (H1) pass a control-record pause — they are how the owner
        # un-pauses a fail-closed root — but NEVER the STOP file.
        if event_type in CONTROL_BOOTSTRAP_EVENT_TYPES:
            if storage.stop_file_present(root):
                raise CouncilError(
                    "council/STOP file exists — the hard emergency stop "
                    f"refuses {event_type}; the owner removes STOP first")
        elif event_type not in STOP_EXEMPT_EVENT_TYPES:
            reason = storage.emergency_stop_reason(root)
            if reason:
                raise CouncilError(
                    f"emergency stop engaged ({reason}) — refusing "
                    f"{event_type}; record AUTONOMY_PAUSED instead")
        # H4: appending after a torn trailing line would fuse two lines
        # and corrupt the chain — read_chain(verify=True) now raises on a
        # torn tail, so this fails closed before any write
        chain = read_chain(root, verify=True)
        seq = len(chain) + 1
        prev = chain[-1]["event_hash"] if chain else GENESIS_HASH
        event = build_event(event_type, sender, request_id, repository,
                            target_commit, payload, seq, prev)
        validate_event(event, for_append=True)
        requests = state_machine.project(chain)
        state_machine.check(event, requests)
        if event_type == "FIX_STARTED" and \
                request_id in state_machine.M8_CLOSURE_SOURCE_REQUESTS and \
                requests.get(request_id, {}).get("state") in (
                    state_machine.REQUESTED, state_machine.BLOCKED,
                    state_machine.GO):
            from tools.council.m8_incomplete_handoff import \
                validate_source_rewind_append
            validate_source_rewind_append(root, cfg, chain, event)
        # H3: verdict authority-context bindings verified against the chain
        from tools.council.schemas import (crosscheck_verdict_bindings,
                                           VERDICT_PAYLOAD_EVENT_TYPES)
        if event_type in VERDICT_PAYLOAD_EVENT_TYPES:
            crosscheck_verdict_bindings(event, chain, requests)
        if event_type == "EXPERIMENT_APPROVED":
            _verify_experiment_approval_binding(root, cfg, chain, event)
        if event_type == "EXPERIMENT_STARTED":
            _verify_experiment_start_binding(root, cfg, chain, event)
        if event_type == "RESULT_HANDOFF_APPROVAL_REQUIRED":
            from tools.council.m8_incomplete_handoff import \
                validate_proposal_append
            validate_proposal_append(root, cfg, chain, event)
        if event_type == "RESULT_HANDOFF_APPROVED":
            from tools.council.m8_incomplete_handoff import \
                validate_approval_binding
            validate_approval_binding(chain, event)
        if event_type in ("RESULT_HANDOFF_READY", "RESULT_FIX_READY"):
            from tools.council.m8_incomplete_handoff import \
                validate_ready_binding
            validate_ready_binding(chain, event)
        if event_type == "REQUEST_CANCELED" and \
                event["payload"].get("schema_version") == \
                "m8-budget-exhaustion-source-close.v1":
            from tools.council.m8_incomplete_handoff import \
                validate_source_close_binding
            validate_source_close_binding(chain, event)
        if event_type in ("EXPERIMENT_COMPLETE", "RESULT_AUDIT_REQUESTED"):
            _verify_result_artifact_binding(root, cfg, chain, event)
        # delegated-authority: a CONDITIONS_AUTO_SATISFIED is a claude-sender,
        # TOKENLESS event whose authority is a re-validated policy evaluation,
        # never its mere presence. Refuse the append unless the delegation holds
        # right now (mirrors the AUTO_APPROVED trust model; fail-closed).
        if event_type == "CONDITIONS_AUTO_SATISFIED":
            _verify_delegated_satisfaction(root, cfg, chain, event)
        # governance Class-C: a COUNCIL_RESOLVED is a claude-sender, TOKENLESS
        # resolution whose authority is a re-validated evaluate_class_c pass (the
        # frozen seven-gate protocol), never its presence. Fail-closed at the append
        # boundary (mirrors CONDITIONS_AUTO_SATISFIED).
        if event_type == "COUNCIL_RESOLVED":
            _verify_class_c_resolution(root, cfg, chain, event)
        # governance G4: a MATTER_ACCEPTED is a claude-sender, TOKENLESS durable record
        # of a resolved matter's `accepted` continuation. Its authority is a
        # re-validated evaluate_matter_accepted pass (authorized-under-governance +
        # accept resolution + bound resolved_event_id + exactly-once), never its
        # presence. Fail-closed at the boundary (mirrors COUNCIL_RESOLVED).
        if event_type == "MATTER_ACCEPTED":
            _verify_matter_accepted(root, cfg, chain, event)
        # H1: burn the human one-time token (if this event type requires
        # one) durably BEFORE the line lands — a crash here wastes a
        # token, it never leaves a spendable one behind an appended event
        _verify_human_token(root, chain, event, enrollment_token)
        storage.append_line(storage.events_path(root), canonical_json(event))
        try:  # state.json is best-effort cache; the append already succeeded
            state_machine.apply(event, requests)
            chain.append(event)
            state_machine.rebuild(root, chain, event["event_hash"])
        except OSError:
            pass
        return event
    finally:
        locking.release(lock)


def _verify_human_token(root: str, chain: list, event: dict,
                        enrollment_token) -> None:
    """H1: human authority is a burned one-time token (tools/council/
    identity.py), never a caller-supplied sender string. Runs INSIDE the
    events lock, immediately before the append. The FIRST identity pin
    requires a NON-PERSISTED enrollment proof verified against the
    root-owned anchor (cycle-2 blocker 1: enforcement lives HERE in the
    authoritative writer, not in any CLI). Pre-cutover chains (no
    verifier file AND no pinned identity event) stay tokenless so legacy
    roots replay; once either exists, these events fail closed."""
    from tools.council import identity
    etype = event["event_type"]
    if etype == "HUMAN_IDENTITY_INITIALIZED":
        pin, _state = identity.replay_identity(chain)
        if pin is not None:
            raise CouncilError(
                "identity already rooted — re-rooting is impossible; use "
                "rotation (old-chain token required)")
        identity.check_enrollment(enrollment_token)
        return
    if etype not in HUMAN_TOKEN_REQUIRED_EVENT_TYPES:
        return
    if etype == "REQUEST_CANCELED" and event["sender"] != "human":
        return  # agent cancels revoke authority; they never grant it
    pin, expected_state = identity.replay_identity(chain)  # raises on
    # inconsistent identity history — every consumer fails closed
    verifier_exists = identity.read_verifier(root) is not None
    if pin is None and not verifier_exists:
        return  # pre-cutover legacy behavior
    if pin is None and verifier_exists:
        # cycle-1 blocker 2: a verifier without its chain pin is NEVER
        # authority — a crashed/refused bootstrap must complete (or be
        # removed by the owner) before any token event lands
        raise CouncilError(
            "identity verifier exists without a chain pin — bootstrap "
            "incomplete; token-required events fail closed (re-run "
            "identity-init after removing the orphan verifier, or "
            "complete the pin)")
    payload = event["payload"]
    expected = identity.binding_hash(
        etype, event["request_id"], event["target_commit"],
        {k: v for k, v in payload.items() if k != "human_token"})
    identity.verify_and_advance(root, payload.get("human_token"), expected,
                                expected_state=expected_state)


def _verify_experiment_approval_binding(root: str, cfg: Config, chain: list,
                                        event: dict) -> None:
    """Require the direct v2 owner-event binding when the audited request
    declares an execution envelope.

    Legacy requests retain their historical commit-only approval shape.  The
    stronger path is opt-in at request publication, after which neither a
    legacy approval nor a post-audit request edit can open the run gate.
    """
    from tools.council import publish
    from tools.council.schemas import (EXECUTION_APPROVAL_SCHEMA,
                                       compute_execution_authorization_hash,
                                       validate_execution_approval_payload)

    publication = next((e for e in reversed(chain)
                        if e["request_id"] == event["request_id"] and
                        e["event_type"] in
                        ("AUDIT_REQUESTED", "READY_FOR_REAUDIT")), None)
    publication_marks_bound = bool(
        publication and publication["payload"].get(
            "execution_authorization_hash") is not None)
    payload_marks_bound = event["payload"].get(
        "approval_schema_version") is not None
    if not publication_marks_bound and not payload_marks_bound:
        return
    request, failures, repo, commit = publish.verified_request(
        root, cfg, event["request_id"])
    if failures:
        raise CouncilError(
            "experiment approval refused — audited request is not "
            "verifiable: " + "; ".join(failures))
    if repo != event["repository"] or commit != event["target_commit"]:
        raise CouncilError(
            "experiment approval coordinates differ from the published "
            "request")
    authorization = request.get("execution_authorization")
    if authorization is None:
        raise CouncilError(
            "bound experiment publication has no execution_authorization")
    payload = event["payload"]
    validate_execution_approval_payload(payload)
    if publication is None:
        raise CouncilError(
            "bound experiment approval has no request publication event")
    if publication["payload"].get("execution_authorization_hash") != \
            compute_execution_authorization_hash(authorization):
        raise CouncilError(
            "request publication does not bind the execution authorization")
    by_id = {e["event_id"]: e for e in chain}
    for event_id in authorization["m7_prerequisite_events"]:
        prerequisite = by_id.get(event_id)
        if prerequisite is None or prerequisite["event_type"] != "AUDIT_GO":
            raise CouncilError(
                f"bound M7 prerequisite {event_id} is not an AUDIT_GO")
    for event_id in authorization["source_integration_events"]:
        integration = by_id.get(event_id)
        if integration is None or \
                integration["event_type"] != "CHANGE_INTEGRATED" or \
                integration["target_commit"] != request["target_commit"]:
            raise CouncilError(
                f"bound source integration {event_id} does not authorize "
                "the requested implementation commit")
    expected = {
        "approval_schema_version": EXECUTION_APPROVAL_SCHEMA,
        "approved_by": "human",
        "approval_commit": request["target_commit"],
        "request_payload_hash": request["request_payload_hash"],
        "request_publication_event_id": publication["event_id"],
        "request_publication_event_hash": publication["event_hash"],
        "execution_authorization": authorization,
    }
    observed = {k: v for k, v in payload.items() if k != "human_token"}
    if observed != expected:
        raise CouncilError(
            "experiment approval payload does not exactly copy the "
            "event-pinned execution authorization")


def _verify_experiment_start_binding(root: str, cfg: Config, chain: list,
                                     event: dict) -> None:
    """Prevent a direct EXPERIMENT_STARTED append from bypassing a bound
    owner envelope or substituting a pre-existing evidence namespace."""
    from tools.council import publish
    publication = next((e for e in reversed(chain)
                        if e["request_id"] == event["request_id"] and
                        e["event_type"] in
                        ("AUDIT_REQUESTED", "READY_FOR_REAUDIT")), None)
    approval = next((e for e in reversed(chain)
                     if e["request_id"] == event["request_id"] and
                     e["event_type"] == "EXPERIMENT_APPROVED"), None)
    bound = bool(
        (publication and publication["payload"].get(
            "execution_authorization_hash") is not None) or
        (approval and approval["payload"].get(
            "approval_schema_version") is not None) or
        event["payload"].get("execution_authorization") is not None)
    if not bound:
        return
    request, failures, repo, commit = publish.verified_request(
        root, cfg, event["request_id"])
    if failures:
        raise CouncilError(
            "experiment start refused — audited request is not verifiable: "
            + "; ".join(failures))
    authorization = request.get("execution_authorization")
    if authorization is None:
        raise CouncilError(
            "bound experiment start request has no execution_authorization")
    if approval is None:
        raise CouncilError("bound experiment start has no owner approval")
    payload = event["payload"]
    required_equal = {
        "owner_approval_event_id": approval["event_id"],
        "request_payload_hash": request["request_payload_hash"],
        "execution_authorization": authorization,
        "experiment_config_hash": authorization["experiment_config_hash"],
    }
    for field, expected in required_equal.items():
        if payload.get(field) != expected:
            raise CouncilError(
                f"experiment start {field} does not match the owner-bound "
                "execution envelope")
    limits = payload.get("limits")
    budget = authorization["budget"]
    limit_fields = {"max_compute_minutes", "max_wall_minutes",
                    "max_storage_mb", "max_retries_per_unit",
                    "max_scenarios"}
    if not isinstance(limits, dict) or set(limits) != limit_fields:
        raise CouncilError(
            "bound experiment start effective limits must be the exact "
            "five-field runner limit set")
    for field in sorted(limit_fields):
        value = limits[field]
        minimum = 0 if field == "max_retries_per_unit" else 1
        if not isinstance(value, (int, float)) or isinstance(value, bool) or \
                value < minimum or value > budget[field]:
            raise CouncilError(
                f"experiment start limit {field} is invalid or exceeds the "
                "owner-bound budget")
    evidence = os.path.join(repo, authorization["evidence_root"])
    manifest = os.path.join(repo, authorization["manifest"])
    if authorization["resume_from"] is None:
        if os.path.lexists(evidence) or os.path.lexists(manifest):
            raise CouncilError(
                "bound experiment start refuses a pre-existing evidence root "
                "or manifest")
    else:
        if not os.path.isdir(evidence) or not (
                os.path.isfile(manifest) or
                os.path.isfile(manifest + ".tombstones.jsonl")):
            raise CouncilError(
                "bound resume start requires the existing evidence root and "
                "terminal ledger")
    if repo != event["repository"] or commit != event["target_commit"]:
        raise CouncilError(
            "bound experiment start coordinates differ from the published "
            "request")


def _verify_result_artifact_binding(root: str, cfg: Config, chain: list,
                                    event: dict) -> None:
    """Require one immutable artifact census across bound M8 completion and
    result-audit publication. Legacy experiment lifecycles remain unchanged."""
    if event["event_type"] == "RESULT_AUDIT_REQUESTED":
        ready = next((e for e in reversed(chain)
                      if e["request_id"] == event["request_id"] and
                      e["event_type"] in
                      ("RESULT_HANDOFF_READY", "RESULT_FIX_READY")), None)
        if ready is not None:
            request = ready["payload"].get("request", {})
            artifacts = request.get("result_artifacts")
            if artifacts is not None:
                from tools.council.schemas import validate_result_artifacts
                validate_result_artifacts(artifacts)
                if event["payload"].get("result_artifacts") != artifacts:
                    raise CouncilError(
                        "result-handoff audit must copy the ready request's "
                        "exact result_artifacts record")
            return
    publication = next((e for e in reversed(chain)
                        if e["request_id"] == event["request_id"] and
                        e["event_type"] in
                        ("AUDIT_REQUESTED", "READY_FOR_REAUDIT")), None)
    approval = next((e for e in reversed(chain)
                     if e["request_id"] == event["request_id"] and
                     e["event_type"] == "EXPERIMENT_APPROVED"), None)
    bound = bool(
        (publication and publication["payload"].get(
            "execution_authorization_hash") is not None) or
        (approval and approval["payload"].get(
            "approval_schema_version") is not None))
    if not bound:
        return

    from tools.council import publish
    from tools.council.schemas import validate_result_artifacts
    request, failures, repo, commit = publish.verified_request(
        root, cfg, event["request_id"])
    if failures:
        raise CouncilError(
            "bound result event refused — audited request is not verifiable: "
            + "; ".join(failures))
    authorization = request.get("execution_authorization")
    if authorization is None or approval is None:
        raise CouncilError(
            "bound result event lacks its execution authorization or owner "
            "approval")
    if repo != event["repository"] or commit != event["target_commit"]:
        raise CouncilError(
            "bound result event coordinates differ from the published request")
    artifacts = event["payload"].get("result_artifacts")
    if artifacts is None:
        raise CouncilError(
            "bound result event must carry the closed result_artifacts record")
    validate_result_artifacts(artifacts)
    if artifacts["owner_approval_event_id"] != approval["event_id"] or \
            artifacts["request_payload_hash"] != \
            request["request_payload_hash"]:
        raise CouncilError(
            "result_artifacts do not bind the owner approval and audited "
            "request")
    if artifacts["terminal_outcomes"] != authorization["planned_runs"]:
        raise CouncilError(
            "result_artifacts terminal census differs from the owner-bound "
            "planned run count")
    if artifacts["tombstoned_runs"] > 0 and \
            artifacts["analysis_status"] != \
            "terminal_failure_inconclusive":
        raise CouncilError(
            "a tombstoned terminal pack must be classified inconclusive")
    if artifacts["tombstoned_runs"] == 0 and \
            artifacts["analysis_status"] != "analyzed":
        raise CouncilError(
            "an all-success terminal pack must be classified analyzed")

    if event["event_type"] == "RESULT_AUDIT_REQUESTED":
        complete = next((e for e in reversed(chain)
                         if e["request_id"] == event["request_id"] and
                         e["event_type"] == "EXPERIMENT_COMPLETE"), None)
        if complete is None or complete["payload"].get(
                "result_artifacts") != artifacts:
            raise CouncilError(
                "RESULT_AUDIT_REQUESTED result_artifacts must exactly equal "
                "the EXPERIMENT_COMPLETE record")


def _verify_delegated_satisfaction(root: str, cfg: Config, chain: list,
                                   event: dict) -> None:
    """Refuse a CONDITIONS_AUTO_SATISFIED unless `policy.evaluate_delegation`
    passes right now against the request's latest conditional codex verdict —
    the delegated satisfaction's authority is the re-validated evaluation, not
    the event's presence (the AUTO_APPROVED trust model). Fail-closed: any
    failure or error refuses the append, leaving the human CONDITIONS_SATISFIED
    token as the only unlock."""
    from tools.council import policy, publish   # lazy: policy imports events
    rid = event["request_id"]
    request, failures, _repo, _commit = publish.verified_request(root, cfg, rid)
    if failures:
        raise CouncilError(
            "delegated satisfaction refused — request not verifiable: "
            + "; ".join(failures))
    verdict_event = None
    for e in chain:   # the LAST conditional codex verdict for this request wins
        if e.get("request_id") == rid \
                and e.get("event_type") == "AUDIT_GO_WITH_CONDITIONS":
            verdict_event = e
    if verdict_event is None:
        raise CouncilError(
            f"delegated satisfaction refused — no conditional verdict for {rid!r}")
    decision = policy.evaluate_delegation(root, cfg, request, verdict_event,
                                          chain)
    if not decision.auto_approve:
        raise CouncilError(
            "delegated satisfaction refused by the delegation policy: "
            + "; ".join(decision.reasons))


def _verify_class_c_resolution(root: str, cfg: Config, chain: list,
                               event: dict) -> None:
    """Refuse a COUNCIL_RESOLVED unless `policy.evaluate_class_c` passes right now
    against the verified chain — the resolution's authority is the re-validated
    seven-gate evaluation, not the event's presence. Fail-closed: any unmet gate or
    error refuses the append, leaving the matter UNRESOLVED (never escalated to the
    owner)."""
    from tools.council import policy   # lazy: policy imports events
    # evaluate_class_c self-reads + verifies the chain from root (audit 000732) —
    # it never trusts a caller-supplied chain, so the append-boundary passes only the
    # candidate resolution event; the preregistration + evidence are already on disk.
    decision = policy.evaluate_class_c(root, cfg, event)
    if not decision.auto_approve:
        raise CouncilError(
            "council resolution refused by the Class-C protocol: "
            + "; ".join(decision.reasons))


def _verify_matter_accepted(root: str, cfg: Config, chain: list,
                            event: dict) -> None:
    """Refuse a MATTER_ACCEPTED unless `policy.evaluate_matter_accepted` admits it
    right now against the self-verified chain from root — authorized-under-governance
    + accept resolution + a resolved_event_id that binds the authorizing
    COUNCIL_RESOLVED + no prior MATTER_ACCEPTED for the matter (exactly-once). Fail-
    closed: INERT under v3, and a crash-resumed re-run cannot double-record."""
    from tools.council import policy   # lazy: policy imports events
    decision = policy.evaluate_matter_accepted(root, cfg, event)
    if not decision.admit:
        raise CouncilError(
            "matter-accepted continuation refused by governance: "
            + "; ".join(decision.reasons))


def pause_autonomy(root: str, cfg: Config, sender: str, request_id: str,
                   repository: str, target_commit: str, reason: str) -> dict:
    """Record AUTONOMY_PAUSED (allowed even under emergency stop)."""
    return append_event(root, cfg, "AUTONOMY_PAUSED", sender, request_id,
                        repository, target_commit,
                        {"reason": reason, "recorded_by": sender})
