"""Generic, project-independent resolver + validator for the resume checkpoint.

The resume checkpoint (``resume_checkpoint.json``) is the SOLE machine-readable source
of truth for continuing an interrupted council session. It lives OUTSIDE the git repo,
in the CONFIGURED council root (``get_config().council_root``) — a repo-only search can
never discover it, and there is deliberately NO copy of it inside the repository. This
module resolves it strictly FROM CONFIGURATION (never a hard-coded user path), validates
it against the live chain and policy pin, and FAILS CLOSED for resume authority whenever
the artifact is unavailable, missing, malformed, or bound to a divergent chain or pin.

Availability vs. absence is a real distinction: an auditor that cannot even access the
configured council root reports ``CHECKPOINT_ARTIFACT_UNAVAILABLE`` (NOT "no checkpoint
exists"). Unavailability fails closed for RESUME authority only — it never claims the
checkpoint is absent, and it leaves unrelated read-only auditing untouched.

This module imports no project (Coliseum) code and assumes no project-specific registry;
it depends only on the generic council chain + policy primitives.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field

from tools.council import events as events_mod
from tools.council import policy as policy_mod
from tools.council.schemas import SchemaViolation, payload_hash
from tools.council.strictjson import load_strict_file

# The stable, project-independent locator convention. NOT an absolute machine path:
# it names the council-root-relative artifact; the concrete path is resolved from
# configuration at call time.
LOCATOR_URI = "council-root://resume_checkpoint.json"
CHECKPOINT_FILENAME = "resume_checkpoint.json"
CHECKPOINT_HASH_FIELD = "checkpoint_hash"

# Validation status codes (typed; the CLI surfaces these verbatim).
RESOLVED = "RESOLVED"
CHECKPOINT_ARTIFACT_UNAVAILABLE = "CHECKPOINT_ARTIFACT_UNAVAILABLE"
CHECKPOINT_MISSING = "CHECKPOINT_MISSING"
CHECKPOINT_MALFORMED = "CHECKPOINT_MALFORMED"
CONTENT_HASH_MISMATCH = "CONTENT_HASH_MISMATCH"
STALE_CHAIN_BINDING = "STALE_CHAIN_BINDING"
POLICY_PIN_MISMATCH = "POLICY_PIN_MISMATCH"


def resolve_checkpoint_path(cfg) -> str:
    """The configured resume-checkpoint path — council_root joined with the fixed
    filename. Uses CONFIGURATION only; never a hard-coded user path."""
    return os.path.join(cfg.council_root, CHECKPOINT_FILENAME)


@dataclass
class ResumeLocation:
    locator: str
    configured_council_root: str
    resolved_path: str
    council_root_accessible: bool
    exists: bool
    status: str
    resume_authorized: bool
    schema_version: str | None = None
    recorded_content_hash: str | None = None
    computed_content_hash: str | None = None
    checkpoint_chain: dict | None = None          # {head_hash, length} per the checkpoint
    live_chain: dict | None = None                # {head_hash, length} of the live chain
    policy_pin: dict | None = None                # {checkpoint, live, match}
    reasons: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _fail(loc: ResumeLocation, status: str, reason: str) -> ResumeLocation:
    loc.status = status
    loc.resume_authorized = False
    loc.reasons.append(reason)
    return loc


def locate_resume_checkpoint(cfg) -> ResumeLocation:
    """Resolve + validate the resume checkpoint from configuration. Deterministic and
    fail-closed: `resume_authorized` is True ONLY for a fully validated RESOLVED status
    (accessible root, present + well-formed artifact, matching content hash, a chain
    binding consistent with the live chain, and a matching policy pin). Every failure
    mode returns a typed status + reason and `resume_authorized=False`; an inaccessible
    council root is CHECKPOINT_ARTIFACT_UNAVAILABLE, never CHECKPOINT_MISSING."""
    council_root = cfg.council_root
    path = resolve_checkpoint_path(cfg)
    loc = ResumeLocation(
        locator=LOCATOR_URI, configured_council_root=council_root,
        resolved_path=path, council_root_accessible=False, exists=False,
        status=CHECKPOINT_ARTIFACT_UNAVAILABLE, resume_authorized=False)

    # (1) availability of the CONFIGURED root itself — distinct from artifact absence.
    if not (os.path.isdir(council_root)
            and os.access(council_root, os.R_OK | os.X_OK)):
        return _fail(loc, CHECKPOINT_ARTIFACT_UNAVAILABLE,
                     f"configured council_root is not accessible ({council_root!r}) "
                     "— cannot determine checkpoint state; resume fails closed while "
                     "unrelated read-only auditing remains available")
    loc.council_root_accessible = True

    # (2) artifact presence within the accessible root.
    if not os.path.isfile(path):
        loc.exists = False
        return _fail(loc, CHECKPOINT_MISSING,
                     f"no resume checkpoint at the resolved path {path!r}")
    loc.exists = True

    # (3) well-formedness (strict parse: duplicate keys, NaN/Infinity, and size/depth
    # limits are rejected — the council-wide strict-parse discipline, never a bare read).
    try:
        data = load_strict_file(path)
        if not isinstance(data, dict):
            raise SchemaViolation("checkpoint is not a JSON object")
    except (OSError, SchemaViolation) as exc:
        return _fail(loc, CHECKPOINT_MALFORMED, f"checkpoint unreadable/invalid: {exc}")

    loc.schema_version = data.get("checkpoint_schema_version")
    cp_chain = data.get("chain") if isinstance(data.get("chain"), dict) else {}
    loc.checkpoint_chain = {"head_hash": cp_chain.get("head_hash"),
                            "length": cp_chain.get("length")}

    # (4) self-referential content hash.
    recorded = data.get(CHECKPOINT_HASH_FIELD)
    computed = payload_hash({k: v for k, v in data.items()
                             if k != CHECKPOINT_HASH_FIELD})
    loc.recorded_content_hash = recorded
    loc.computed_content_hash = computed
    if recorded != computed:
        return _fail(loc, CONTENT_HASH_MISMATCH,
                     "recorded checkpoint_hash does not match the recomputed content "
                     "hash — the checkpoint has been edited out of band")

    # (5) chain binding consistency against the LIVE chain (generic council chain).
    try:
        live_report = events_mod.verify_chain(council_root)
        live_chain = events_mod.read_chain(council_root, verify=True)
    except Exception as exc:                       # root accessible but chain unreadable
        return _fail(loc, CHECKPOINT_ARTIFACT_UNAVAILABLE,
                     f"live chain unreadable under the configured root: {exc}")
    live_head = live_report.head_hash
    live_len = live_report.length
    loc.live_chain = {"head_hash": live_head, "length": live_len}
    cp_len = cp_chain.get("length")
    cp_head = cp_chain.get("head_hash")
    consistent = (isinstance(cp_len, int) and 0 < cp_len <= live_len
                  and live_chain[cp_len - 1].get("event_hash") == cp_head)
    if not consistent:
        return _fail(loc, STALE_CHAIN_BINDING,
                     "the checkpoint's recorded chain head is not a prefix of the live "
                     f"chain (checkpoint head {cp_head!r} @ length {cp_len!r}; live "
                     f"length {live_len}) — the binding is stale or divergent")

    # (6) policy-pin binding: the checkpoint's recorded effective pin must equal the
    # live effective pin (walked from the owner-authorized amendment chain).
    live_hash, live_version = policy_mod.effective_policy_pin(live_chain)
    cp_pol = data.get("effective_policy") if isinstance(
        data.get("effective_policy"), dict) else {}
    loc.policy_pin = {
        "checkpoint": {"hash": cp_pol.get("hash"), "version": cp_pol.get("version")},
        "live": {"hash": live_hash, "version": live_version},
        "match": cp_pol.get("hash") == live_hash
        and cp_pol.get("version") == live_version}
    if not loc.policy_pin["match"]:
        return _fail(loc, POLICY_PIN_MISMATCH,
                     "the checkpoint's recorded effective policy pin does not match the "
                     f"live pin (checkpoint {cp_pol.get('version')!r}/"
                     f"{str(cp_pol.get('hash'))[:12]}; live {live_version!r}/"
                     f"{str(live_hash)[:12]})")

    loc.status = RESOLVED
    loc.resume_authorized = True
    return loc
