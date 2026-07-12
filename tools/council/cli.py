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

from tools.council import (events, get_config, identity, locking, policy,
                           publish, state_machine, storage, strictjson)
from tools.council.schemas import (CouncilError, SchemaViolation,
                                   validate_commit, validate_request_id)

# H1: the generic escape hatch may record ONLY non-authority bookkeeping.
# Approval, verdict, policy, claim, execution, integration, and milestone
# events are unreachable from `record` regardless of role — each has a
# dedicated command or tool with its own gates.
RECORD_ALLOWED_EVENT_TYPES = frozenset({
    "BUILD_STARTED", "BUILD_READY", "FIX_STARTED", "WATCHER_ERROR",
    "AUTONOMY_PAUSED",
})

CONTROL_RID = "council-control"
IDENTITY_RID = "council-identity"
NULL_COMMIT = "0" * 40


def _cfg(args):
    cfg = get_config(role=getattr(args, "role", None))
    return cfg, cfg.council_root


def _maybe_human_token(root, args, event_type: str, request_id: str,
                       commit: str, payload_core: dict):
    """Owner-side token minting for a human-authority event. Returns None
    only on a pre-cutover root (no verifier AND no chain pin) — otherwise
    a token is mandatory and the passphrase is prompted via getpass
    (never argv). --token-file supplies {counter, preimage_hex} for
    scripted use; binding is always recomputed here."""
    verifier = identity.read_verifier(root)
    pin = identity.latest_pin(events.read_chain(root))
    if verifier is None and pin is None:
        return None
    if verifier is None:
        raise SchemaViolation(
            "identity verifier missing but the chain pins one — fail "
            "closed; run identity-restore-from-pin or identity-rotate")
    token_file = getattr(args, "token_file", None)
    if token_file:
        with open(token_file, "rb") as fh:
            token = strictjson.loads_strict(fh.read(), max_bytes=16_384)
        if not isinstance(token, dict):
            raise SchemaViolation("--token-file must contain a JSON object")
    else:
        import getpass
        passphrase = getpass.getpass("owner passphrase: ")
        token = identity.compute_token(passphrase, verifier)
    token["binds"] = identity.binding_hash(event_type, request_id, commit,
                                           payload_core)
    return token


def _with_token(payload_core: dict, token) -> dict:
    payload = dict(payload_core)
    if token is not None:
        payload["human_token"] = token
    return payload


def cmd_init(args) -> int:
    _cfg_, root = _cfg(args)
    storage.ensure_layout(root)
    print(f"council layout ready at {root}")
    if not identity.read_verifier(root):
        print("bootstrap (fail-closed root): 1) identity-init  "
              "2) status-set --status active   — until then everything "
              "is paused")
    return 0


def cmd_init_policy(args) -> int:
    if args.role != "human":
        raise SchemaViolation("init-policy is an owner action: --role human")
    cfg, root = _cfg(args)
    path = policy.write_initial_policy(root)
    _pol, pol_hash = policy.load_policy(root)
    payload_core = {"policy_hash": pol_hash, "policy_file": storage.POLICY_FILE}
    token = _maybe_human_token(root, args, "POLICY_INITIALIZED",
                               CONTROL_RID, NULL_COMMIT, payload_core)
    event = events.append_event(root, cfg, "POLICY_INITIALIZED", "human",
                                CONTROL_RID, cfg.repo_roots[0], NULL_COMMIT,
                                _with_token(payload_core, token))
    print(f"autonomy policy installed at {path}\npolicy_hash: {pol_hash}\n"
          f"pinned by event {event['event_id']}; the file is immutable "
          "during autonomous operation — agents have no write API and "
          "hash drift pauses autonomy")
    return 0


def cmd_amend_policy(args) -> int:
    """Owner-only, token-gated policy amendment (M7/SC-7). Writes the code-
    defined POLICY_VERSIONS[target] over the current file and records a
    POLICY_AMENDED event binding {prev hash, new hash, exact version, semantic
    diff, audited implementation commit, owner token}. Agents cannot mint the
    token, so they cannot amend — the amendment mechanism does not let an
    autonomous agent expand its own authority."""
    if args.role != "human":
        raise SchemaViolation("amend-policy is an owner action: --role human")
    cfg, root = _cfg(args)
    impl_commit = validate_commit(args.impl_commit)
    prev_hash, new_hash, diff = policy.amend_policy(root, args.target_version)
    payload_core = {"policy_hash": new_hash, "prev_policy_hash": prev_hash,
                    "policy_version": args.target_version,
                    "policy_diff": diff, "impl_commit": impl_commit,
                    "policy_file": storage.POLICY_FILE}
    token = _maybe_human_token(root, args, "POLICY_AMENDED",
                               CONTROL_RID, impl_commit, payload_core)
    event = events.append_event(root, cfg, "POLICY_AMENDED", "human",
                                CONTROL_RID, cfg.repo_roots[0], impl_commit,
                                _with_token(payload_core, token))
    print(f"policy amended to version {args.target_version}\n"
          f"prev_hash: {prev_hash}\nnew_hash:  {new_hash}\n"
          f"diff: {diff}\npinned by event {event['event_id']} "
          f"(impl_commit {impl_commit[:12]})")
    return 0


def cmd_status(args) -> int:
    _cfg_, root = _cfg(args)
    chain = events.read_chain(root)
    requests = state_machine.project(chain)
    flags = state_machine.global_flags(requests)
    control = storage.read_control(root)
    print(f"council: {root}")
    print(f"control: {control['status']}"
          + (f" (roles: {','.join(control.get('paused_roles', []))};"
             f" {control.get('reason', '')})"
             if control["status"] != "active" else "")
          + f"; STOP file: "
            f"{'PRESENT' if storage.stop_file_present(root) else 'absent'}"
          + f"; log.md mirror: {storage.read_status(root)} (cosmetic)")
    verifier = identity.read_verifier(root)
    pin = identity.latest_pin(chain)
    if verifier is None:
        print("identity: NOT INITIALIZED"
              + (" (chain pins one — FAIL CLOSED)" if pin else
                 " (pre-cutover: human events are legacy-tokenless)"))
    else:
        lineage = "unpinned (bootstrap)" if pin is None else (
            "descends from pinned tip" if
            identity.verify_lineage(verifier, *pin) else
            "DOES NOT DESCEND FROM PINNED TIP — fail closed")
        print(f"identity: {verifier['counter']} tokens remaining; {lineage}")
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
    with open(args.file, "rb") as fh:
        request = strictjson.loads_strict(fh.read(), max_bytes=262_144)
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
    if args.type not in RECORD_ALLOWED_EVENT_TYPES:
        raise SchemaViolation(
            f"record refuses {args.type!r} — the generic escape hatch may "
            f"emit only {sorted(RECORD_ALLOWED_EVENT_TYPES)}; authority "
            "events go through their dedicated commands (approve, "
            "approve-conditions, cancel, status-set, publish-request, "
            "codex_watch, the autonomy runner)")
    payload = strictjson.loads_strict(args.payload_json) \
        if args.payload_json else {}
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
    payload_core = {"approved_by": "human", "approval_commit": args.commit}
    token = _maybe_human_token(root, args, "EXPERIMENT_APPROVED",
                               args.request_id, request["target_commit"],
                               payload_core)
    event = events.append_event(root, cfg, "EXPERIMENT_APPROVED", "human",
                                args.request_id, request["repository"],
                                request["target_commit"],
                                _with_token(payload_core, token))
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
    payload_core = {"reviewed_by": "human", "approval_commit": args.commit,
                    "note": args.note or ""}
    token = _maybe_human_token(root, args, "CONDITIONS_SATISFIED",
                               args.request_id, request["target_commit"],
                               payload_core)
    event = events.append_event(root, cfg, "CONDITIONS_SATISFIED", "human",
                                args.request_id, request["repository"],
                                request["target_commit"],
                                _with_token(payload_core, token))
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
    payload_core = {"reason": args.reason}
    token = None
    if args.role == "human":  # agent cancels revoke, never grant — no token
        token = _maybe_human_token(root, args, "REQUEST_CANCELED",
                                   args.request_id,
                                   request["target_commit"], payload_core)
    event = events.append_event(root, cfg, "REQUEST_CANCELED", args.role,
                                args.request_id, request["repository"],
                                request["target_commit"],
                                _with_token(payload_core, token))
    print(f"canceled {args.request_id} (event {event['event_id']})")
    return 0


def cmd_identity_init(args) -> int:
    """Bootstrap the owner's S/KEY token chain. Order (cycle-1 blockers
    2+3): enrollment anchor check FIRST (a root-owned, agent-unwritable
    secret — the first writer can never be an agent), then the PIN event,
    then the verifier install. Any pre-pin failure leaves no verifier;
    a crash between pin and install fails closed and is repaired by
    identity-restore-from-pin."""
    cfg, root = _cfg(args)
    if args.role != "human":
        raise SchemaViolation("identity-init is an owner action: "
                              "--role human")
    if identity.read_verifier(root) is not None:
        raise SchemaViolation("identity already initialized — use rotation")
    import getpass
    if getattr(args, "enrollment_token_file", None):
        with open(args.enrollment_token_file, encoding="utf-8") as fh:
            enrollment_token = fh.read().strip()
    else:
        enrollment_token = getpass.getpass(
            "enrollment token (owner-provisioned anchor): ")
    # NOTE: enrollment is enforced by the authoritative writer
    # (events.append_event), not here — the CLI only collects the proof
    if getattr(args, "passphrase_file", None):
        with open(args.passphrase_file, encoding="utf-8") as fh:
            passphrase = fh.read().strip()
    else:
        passphrase = getpass.getpass("new owner passphrase: ")
        if getpass.getpass("repeat passphrase: ") != passphrase:
            raise SchemaViolation("passphrases do not match")
    verifier = identity.prepare_identity(passphrase,
                                         chain_length=args.chain_length)
    payload = {"schema_version": "identity.v1",
               "tip_hex": verifier["tip_hex"],
               "counter": verifier["counter"],
               "chain_length": verifier["chain_length"],
               "salt_hex": verifier["salt_hex"],
               "pbkdf2_iterations": verifier["pbkdf2_iterations"]}
    event = events.append_event(root, cfg, "HUMAN_IDENTITY_INITIALIZED",
                                "human", IDENTITY_RID, cfg.repo_roots[0],
                                NULL_COMMIT, payload,
                                enrollment_token=enrollment_token)
    identity.install_verifier(root, verifier)
    print(f"identity initialized: {verifier['counter']} one-time tokens; "
          f"tip pinned by event {event['event_id']}. Every human-authority "
          "event now requires a token (passphrase prompt).")
    return 0


def cmd_identity_status(args) -> int:
    _cfg_, root = _cfg(args)
    verifier = identity.read_verifier(root)
    pin = identity.latest_pin(events.read_chain(root))
    if verifier is None and pin is None:
        print("identity: not initialized (pre-cutover legacy root)")
        return 0
    if verifier is None:
        print("identity: FAIL CLOSED — chain pins a tip but the verifier "
              "file is missing; run identity-restore-from-pin",
              file=sys.stderr)
        return 1
    print(f"tokens remaining: {verifier['counter']} of "
          f"{verifier['chain_length']}")
    if pin is None:
        print("lineage: unpinned (bootstrap verifier; the next "
              "identity-init/rotate event pins it)")
        return 0
    if identity.verify_lineage(verifier, *pin):
        print("lineage: verifier descends from the chain-pinned tip")
        return 0
    print("lineage: VERIFIER DOES NOT DESCEND FROM THE PINNED TIP — "
          "possible substitution; token events fail closed", file=sys.stderr)
    return 1


def cmd_identity_restore_from_pin(args) -> int:
    """Realign the verifier FILE to what the CHAIN already pins (crash
    between a rotation's event and its verifier write, or file loss).
    Grants no new authority — the chain is the authority — so no token."""
    _cfg_, root = _cfg(args)
    if args.role != "human":
        raise SchemaViolation("identity-restore-from-pin is an owner "
                              "action: --role human")
    # cycle-1 blocker 1: NEVER restore to the pin itself — replay every
    # post-pin burn from the chain so spent tokens stay spent; any
    # inconsistent history refuses before a single byte is written
    verifier = identity.derive_current_from_chain(events.read_chain(root))
    identity.install_verifier(root, verifier, allow_overwrite=True)
    print(f"verifier restored by chain replay: counter "
          f"{verifier['counter']} (every token burned in the chain stays "
          "burned; the tip is the LAST recorded burn, not the pin)")
    return 0


def cmd_identity_rotate(args) -> int:
    """Replace the token chain: one OLD-chain token authorizes pinning a
    NEW chain tip; the verifier is rewritten to the new chain. A crash
    between the event and the verifier write is recovered by
    identity-restore-from-pin (the chain is the authority)."""
    cfg, root = _cfg(args)
    if args.role != "human":
        raise SchemaViolation("identity-rotate is an owner action: "
                              "--role human")
    old_verifier = identity.read_verifier(root)
    if old_verifier is None:
        raise SchemaViolation("no identity to rotate — use identity-init")
    import getpass
    import os as _os
    if getattr(args, "passphrase_file", None):
        with open(args.passphrase_file, encoding="utf-8") as fh:
            new_passphrase = fh.read().strip()
    else:
        new_passphrase = getpass.getpass("NEW owner passphrase: ")
        if getpass.getpass("repeat new passphrase: ") != new_passphrase:
            raise SchemaViolation("passphrases do not match")
    salt = _os.urandom(32)
    iterations = old_verifier["pbkdf2_iterations"]
    seed = identity.derive_seed(new_passphrase, salt, iterations)
    tip = identity.chain_value(seed, args.chain_length)
    payload_core = {"schema_version": "identity.v1", "tip_hex": tip.hex(),
                    "counter": args.chain_length,
                    "chain_length": args.chain_length,
                    "salt_hex": salt.hex(),
                    "pbkdf2_iterations": iterations}
    token = _maybe_human_token(root, args, "HUMAN_IDENTITY_ROTATED",
                               IDENTITY_RID, NULL_COMMIT, payload_core)
    event = events.append_event(root, cfg, "HUMAN_IDENTITY_ROTATED",
                                "human", IDENTITY_RID, cfg.repo_roots[0],
                                NULL_COMMIT, _with_token(payload_core, token))
    now = storage.utc_now()
    identity._write_verifier(root, {
        "schema_version": "identity.v1", "algo": "skey-sha256-v1",
        "salt_hex": salt.hex(), "pbkdf2_iterations": iterations,
        "chain_length": args.chain_length, "counter": args.chain_length,
        "tip_hex": tip.hex(), "created_utc": now, "updated_utc": now})
    print(f"identity rotated: {args.chain_length} fresh tokens; new tip "
          f"pinned by event {event['event_id']}")
    return 0


def cmd_status_set(args) -> int:
    """The ONLY sanctioned run/pause change: a human-token STATUS_CHANGED
    event, then the derived control.json. log.md edits never resume."""
    cfg, root = _cfg(args)
    if args.role != "human":
        raise SchemaViolation("status-set is an owner action: --role human")
    if args.status not in ("active", "paused"):
        raise SchemaViolation("--status must be active|paused")
    roles = [r.strip() for r in (args.roles or "all").split(",") if r.strip()]
    if args.status == "active":
        roles = []
    payload_core = {"status": args.status, "paused_roles": roles,
                    "reason": args.reason or ""}
    token = _maybe_human_token(root, args, "STATUS_CHANGED", CONTROL_RID,
                               NULL_COMMIT, payload_core)
    if token is None:
        raise SchemaViolation(
            "status-set requires an initialized identity — run "
            "identity-init first (fail closed)")
    event = events.append_event(root, cfg, "STATUS_CHANGED", "human",
                                CONTROL_RID, cfg.repo_roots[0], NULL_COMMIT,
                                _with_token(payload_core, token))
    storage.write_control(root, args.status, roles, args.reason or "",
                          event["event_id"])
    try:
        storage.append_log_md(root, "human", (
            f"**STATUS_CHANGED** to `{args.status}`"
            + (f" (paused: {','.join(roles)})" if roles else "")
            + f" — event `{event['event_id']}`."
            + (f" {args.reason}" if args.reason else "")))
    except (CouncilError, OSError):
        pass  # the mirror is cosmetic; control.json is the authority
    print(f"control: {args.status}"
          + (f" (paused roles: {','.join(roles)})" if roles else "")
          + f" — authorized by event {event['event_id']}")
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


def cmd_chain_report(args) -> int:
    """H4: report chain health (torn tail, invalid authority events,
    quarantined requests) and the checkpoint status."""
    from tools.council import checkpoint
    _cfg_, root = _cfg(args)
    report = events.verify_chain(root)
    print(f"chain: {report.length} events; ok={report.ok}; "
          f"healthy={report.healthy}"
          + (f"; torn_suffix={report.torn_bytes}B"
             if report.suffix_incomplete else ""))
    if not report.ok:
        print(f"  INVALID at #{report.error_index}: {report.error}")
        return 1
    chain = events.read_chain(root, verify=False)
    status = state_machine.authority_status(chain)
    flagged = {r: s for r, s in status.items()
               if not s["authority_valid"] or s.get("quarantined")}
    if flagged:
        print("authority-invalid / quarantined requests:")
        for rid, s in sorted(flagged.items()):
            print(f"  {rid}: quarantined={s.get('quarantined')} "
                  f"invalid_events={s['invalid_events']}")
    else:
        print("all requests authority-valid")
    cp_fail = checkpoint.verify_checkpoint(chain)
    if cp_fail:
        print(f"CHECKPOINT MISMATCH: {cp_fail}", file=sys.stderr)
        return 1
    cp = checkpoint.read_checkpoint()
    print("checkpoint: "
          + (f"pinned at length {cp['length']}" if cp else "not provisioned"))
    return 0


def cmd_checkpoint_status(args) -> int:
    """Print the {length, head_hash} the owner would sudo-install at the
    current head (H4 root-owned chain-head checkpoint)."""
    from tools.council import checkpoint
    _cfg_, root = _cfg(args)
    if not events.verify_chain(root).healthy:
        print("chain is not healthy — refusing to render a checkpoint",
              file=sys.stderr)
        return 1
    chain = events.read_chain(root)
    print(json.dumps(checkpoint.render_checkpoint(chain), sort_keys=True))
    print(f"# owner: echo '<that json>' | sudo tee "
          f"{checkpoint.CHECKPOINT_FILE}", file=sys.stderr)
    return 0


def cmd_bless_event(args) -> int:
    """Owner blessing of a specific legacy/nonconforming event so
    quarantine-aware projection may treat it as authority again (H4)."""
    cfg, root = _cfg(args)
    if args.role != "human":
        raise SchemaViolation("bless-event is an owner action: --role human")
    target = None
    for e in events.read_chain(root):
        if e["event_id"] == args.event_id:
            target = e
    if target is None:
        raise SchemaViolation(f"event {args.event_id} not in the chain")
    payload_core = {"blessed_event_id": target["event_id"],
                    "blessed_event_hash": target["event_hash"],
                    "reason": args.reason}
    token = _maybe_human_token(root, args, "MIGRATION_APPROVED",
                               target["request_id"], NULL_COMMIT,
                               payload_core)
    event = events.append_event(root, cfg, "MIGRATION_APPROVED", "human",
                                target["request_id"], cfg.repo_roots[0],
                                NULL_COMMIT, _with_token(payload_core, token))
    print(f"blessed {args.event_id} (event {event['event_id']})")
    return 0


def cmd_repair_tail(args) -> int:
    """Truncate a torn trailing line so appends can resume (H4). The torn
    bytes are by definition NOT a committed event, so this is recovery,
    not history rewriting; refuses if the tail parses as a complete event."""
    cfg, root = _cfg(args)
    if args.role != "human":
        raise SchemaViolation("repair-tail is an owner action: --role human")
    path = storage.events_path(root)
    _complete, tail = storage.read_events_with_tail(path)
    if not tail["torn"]:
        print("no torn trailing line — nothing to repair")
        return 0
    # record intent first (works even while the chain is unhealthy —
    # MIGRATION_APPROVED is not stop-exempt, so we truncate then record)
    with open(path, "rb") as fh:
        data = fh.read()
    with open(path, "wb") as fh:
        fh.write(data[:tail["offset"]])
    print(f"truncated {tail['torn_bytes']} torn bytes at offset "
          f"{tail['offset']}; chain is appendable again")
    return 0


def cmd_verify_evidence(args) -> int:
    """Recompute the evidence inventory for a request's run_dir and compare
    it to the hash pinned in RESULT_AUDIT_REQUESTED — detects any tamper
    of the produced evidence after the result audit was requested."""
    from tools.autonomy.runner import build_evidence_manifest
    _cfg_, root = _cfg(args)
    chain = events.read_chain(root)
    rar = None
    for e in chain:
        if e["request_id"] == args.request_id \
                and e["event_type"] == "RESULT_AUDIT_REQUESTED":
            rar = e
    if rar is None:
        print(f"no RESULT_AUDIT_REQUESTED for {args.request_id}",
              file=sys.stderr)
        return 1
    repo = rar["repository"]
    pinned = rar["payload"].get("evidence_inventory_hash")
    _m, recomputed = build_evidence_manifest(
        repo, rar["payload"]["run_dir"], rar["payload"].get("run_id"))
    if recomputed == pinned:
        print(f"evidence OK: {args.request_id} inventory matches the "
              f"pinned hash {pinned[:12]}")
        return 0
    print(f"EVIDENCE TAMPERED: {args.request_id} recomputed "
          f"{recomputed[:12]} != pinned {str(pinned)[:12]}", file=sys.stderr)
    return 1


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
    p = sub.add_parser("amend-policy")
    p.add_argument("--target-version", type=int, required=True)
    p.add_argument("--impl-commit", required=True,
                   help="the audited commit that introduced this policy version")
    p.add_argument("--token-file", default=None)
    sub.add_parser("status")
    sub.add_parser("verify-chain")
    sub.add_parser("rebuild-state")
    sub.add_parser("milestone-status")

    p = sub.add_parser("verify-evidence")
    p.add_argument("request_id")

    sub.add_parser("chain-report")
    sub.add_parser("checkpoint-status")

    p = sub.add_parser("bless-event")
    p.add_argument("event_id")
    p.add_argument("--reason", required=True)
    p.add_argument("--token-file", dest="token_file", default=None)

    sub.add_parser("repair-tail")

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
    p.add_argument("--token-file", dest="token_file", default=None)

    p = sub.add_parser("approve-conditions")
    p.add_argument("request_id")
    p.add_argument("--commit", required=True)
    p.add_argument("--note", default=None)
    p.add_argument("--token-file", dest="token_file", default=None)

    p = sub.add_parser("identity-init")
    p.add_argument("--chain-length", type=int, default=10_000)
    p.add_argument("--passphrase-file", dest="passphrase_file", default=None,
                   help="tests/scripting only; interactive getpass otherwise")
    p.add_argument("--enrollment-token-file", dest="enrollment_token_file",
                   default=None,
                   help="tests/scripting only; interactive getpass otherwise")

    sub.add_parser("identity-status")

    sub.add_parser("identity-restore-from-pin")

    p = sub.add_parser("identity-rotate")
    p.add_argument("--chain-length", type=int, default=10_000)
    p.add_argument("--passphrase-file", dest="passphrase_file", default=None)
    p.add_argument("--token-file", dest="token_file", default=None)

    p = sub.add_parser("status-set")
    p.add_argument("--status", required=True, choices=("active", "paused"))
    p.add_argument("--roles", default=None,
                   help="comma list for paused (default all)")
    p.add_argument("--reason", default=None)
    p.add_argument("--token-file", dest="token_file", default=None)

    p = sub.add_parser("cancel")
    p.add_argument("request_id")
    p.add_argument("--reason", required=True)
    p.add_argument("--token-file", dest="token_file", default=None)

    p = sub.add_parser("clear-lock")
    p.add_argument("name")
    p.add_argument("--reason", required=True)

    args = parser.parse_args(argv)
    handlers = {"init": cmd_init, "init-policy": cmd_init_policy,
                "amend-policy": cmd_amend_policy,
                "status": cmd_status, "show": cmd_show,
                "verify-chain": cmd_verify_chain,
                "rebuild-state": cmd_rebuild_state,
                "publish-request": cmd_publish_request,
                "record": cmd_record, "approve": cmd_approve,
                "approve-conditions": cmd_approve_conditions,
                "identity-init": cmd_identity_init,
                "identity-status": cmd_identity_status,
                "identity-restore-from-pin": cmd_identity_restore_from_pin,
                "identity-rotate": cmd_identity_rotate,
                "status-set": cmd_status_set,
                "cancel": cmd_cancel, "clear-lock": cmd_clear_lock,
                "milestone-status": cmd_milestone_status,
                "verify-evidence": cmd_verify_evidence,
                "chain-report": cmd_chain_report,
                "checkpoint-status": cmd_checkpoint_status,
                "bless-event": cmd_bless_event,
                "repair-tail": cmd_repair_tail}
    try:
        return handlers[args.command](args)
    except CouncilError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
