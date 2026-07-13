"""Coliseum DRIVER for governance G4 — durable, resumable, idempotent acceptance
continuation.

The GENERIC council core answers two questions and records one durable fact:
  - `policy.continuation_status(root, cfg, matter_id)` — is the matter authorized to
    continue, and has its `accepted` continuation ALREADY been recorded on-chain?
  - a `MATTER_ACCEPTED` event — the exactly-once, chain-anchored proof that the
    continuation was applied (admitted only by `policy.evaluate_matter_accepted` at
    the append boundary: authorized-under-governance + accept resolution + bound
    resolved_event_id + no prior record).

THIS driver — the only place that knows the Coliseum claim registry — performs the
project side: read the registry, invoke the G3 adapter (`accepted_transition`), record
the durable `MATTER_ACCEPTED`, then project the mutation into the registry FILE. The
generic core never imports this module or the claim registry (the seam stays
one-directional: adapter/driver -> core).

Crash-safety ordering: the chain event is written FIRST (it is the source of truth),
then the registry file (a projection). So a crash can only ever leave an on-chain
record whose file projection is one deterministic re-apply behind — never a silent
registry mutation with no record. On resume the driver detects the durable record,
re-derives the identical post-state (the G3 adapter is pure), checks it against the
recorded content hash, and re-projects the file WITHOUT recording again. INERT until
the owner ratifies governance_v1 (v4): under v3 the matter is never authorized, so the
driver applies nothing and the append boundary refuses a MATTER_ACCEPTED regardless.
"""
from __future__ import annotations

import hashlib
import os
import uuid

import yaml

from tools.council import events
from tools.council.policy import continuation_status

from .acceptance import accepted_transition
from .registry import (load_claims_registry, load_experiments_registry)
from .schema import canonical_json


def _content_hash(registry: dict) -> str:
    """Deterministic, formatting-independent hash of the post-state claims registry
    (the value bound into the durable MATTER_ACCEPTED as result_content_hash)."""
    return hashlib.sha256(canonical_json(registry).encode("utf-8")).hexdigest()


def _claim_state(registry: dict, claim_id: str):
    for c in registry.get("claims", []):
        if isinstance(c, dict) and c.get("claim_id") == claim_id:
            return c.get("state")
    return None


def _persist_registry(claims_path: str, registry: dict) -> None:
    """Same-directory tmp -> rename so a reader never sees a partial registry."""
    tmp = f"{claims_path}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            yaml.safe_dump(registry, fh, sort_keys=True, default_flow_style=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, claims_path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _result(*, applied, reason, already=False, reprojected=False,
            accepted_event_id=None):
    return {"applied": applied, "already_recorded": already,
            "reprojected": reprojected, "accepted_event_id": accepted_event_id,
            "reason": reason}


def continue_acceptance(root, cfg, claims_path: str, experiments_path: str,
                        matter_id: str, claim_id: str, repository: str,
                        target_commit: str):
    """Drive (or resume) the `accepted` continuation for a resolved Class-C matter.
    Returns a typed result dict; never raises on an unauthorized/malformed/absent
    input. Idempotent and crash-resumable:

      - not authorized (incl. INERT under v3) / resolution not 'accept' -> no-op refusal
      - authorized, not yet recorded -> apply via the G3 adapter, record MATTER_ACCEPTED
        (chain first), then project the registry file
      - already recorded, file already reflects it -> full no-op (already_recorded)
      - already recorded, file NOT yet projected (crash mid-continuation) -> re-derive
        the identical post-state, verify it against the recorded hash, re-project the
        file only (no second record)

    The generic core enforces authority + exactly-once at the append boundary; this
    driver additionally refuses to project any post-state that diverges from the
    durably recorded content hash."""
    status = continuation_status(root, cfg, matter_id)
    if not status.authorized:
        return _result(applied=False,
                       reason="not authorized by governance: "
                              + "; ".join(status.reasons))
    if not status.is_accept:
        return _result(applied=False,
                       reason=f"matter resolution {status.resolution!r} is not "
                              "an accept — the driver promotes nothing")
    try:
        registry = load_claims_registry(claims_path)
        exp = load_experiments_registry(experiments_path)
    except Exception as exc:                 # unreadable/malformed -> refuse untouched
        return _result(applied=False, reason=f"registry unreadable: {exc}")
    if not isinstance(exp, dict) or not isinstance(exp.get("experiments"), list):
        return _result(applied=False, reason="experiments registry is malformed")
    citable = {e.get("experiment_id") for e in exp["experiments"]
               if isinstance(e, dict) and e.get("status") == "complete"}
    new_registry, res = accepted_transition(root, cfg, registry, claim_id,
                                            matter_id, citable)

    if status.already_accepted:
        # a durable MATTER_ACCEPTED exists. The file is a projection that may already
        # reflect it (full no-op) or may be one deterministic re-apply behind (crash
        # between the chain record and the file write).
        if _claim_state(registry, claim_id) == "accepted":
            return _result(applied=False, already=True,
                           accepted_event_id=status.accepted_event_id,
                           reason="already continued — chain record and registry "
                                  "file both reflect the accepted transition")
        if not res["accepted"]:
            return _result(applied=False,
                           accepted_event_id=status.accepted_event_id,
                           reason="resume divergence: a MATTER_ACCEPTED is recorded "
                                  "but the adapter refuses re-projection: "
                                  + res["reason"])
        if _content_hash(new_registry) != status.result_content_hash:
            return _result(applied=False,
                           accepted_event_id=status.accepted_event_id,
                           reason="resume hash mismatch: the re-derived post-state "
                                  "does not match the recorded result_content_hash "
                                  "— refusing to project a divergent registry")
        _persist_registry(claims_path, new_registry)
        return _result(applied=True, reprojected=True,
                       accepted_event_id=status.accepted_event_id,
                       reason="re-projected the registry file to match the durable "
                              "MATTER_ACCEPTED (no second record)")

    # first application: the adapter must accept, then record on-chain, then project.
    if not res["accepted"]:
        return _result(applied=False,
                       reason="G3 adapter refused the transition: " + res["reason"])
    result_hash = _content_hash(new_registry)
    payload = {"matter_id": matter_id, "resolved_event_id": status.resolved_event_id,
               "subject_ref": claim_id, "result_content_hash": result_hash}
    # chain FIRST (append boundary re-validates authority + exactly-once), file SECOND
    ev = events.append_event(root, cfg, "MATTER_ACCEPTED", "claude", matter_id,
                             repository, target_commit, payload)
    _persist_registry(claims_path, new_registry)
    return _result(applied=True, accepted_event_id=ev["event_id"],
                   reason="recorded MATTER_ACCEPTED and projected the accepted "
                          "transition into the claim registry")
