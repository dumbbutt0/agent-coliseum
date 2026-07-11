"""Unforgeable human identity: S/KEY-style hash-chain one-time tokens.

The owner's passphrase (never stored) derives a seed via PBKDF2; the seed
anchors a hash chain h^0..h^N. The council stores ONLY the current chain
TIP and counter (council/identity/human-tip.json). Each human-authority
event reveals the next preimage: verification is H(preimage) == tip, then
the tip atomically advances (burn-then-append — a crash after the burn
wastes one token, it can never leave a spendable token behind an appended
event). Tokens are single-use, replay-proof, and forgeable only with the
passphrase; anyone can verify. Tokens BIND to the exact action (event
type, request, commit, payload) so an intercepted token cannot authorize
a different event.

The chain tip is additionally PINNED into the event chain by
HUMAN_IDENTITY_INITIALIZED / HUMAN_IDENTITY_ROTATED events: a substituted
or deleted verifier file no longer descends from the pinned tip and every
token-required append fails closed.

Threat model note (owner-ratified): a hostile process running as the SAME
OS user could in principle intercept a passphrase or token between
keystroke and append. That is out of scope — the boundary defends the
agents' actual API surface (CLI flags, files, events), where --role was
previously a plain string compare.
"""
from __future__ import annotations

import hashlib
import os

from tools.council import storage
from tools.council.schemas import (HUMAN_TOKEN_REQUIRED_EVENT_TYPES,
                                   SchemaViolation, canonical_json)

TOKEN_DOMAIN = b"council:human-token:v1\x00"
BINDING_DOMAIN = b"council:human-token-binding:v1\x00"

DEFAULT_CHAIN_LENGTH = 10_000
DEFAULT_ITERATIONS = 600_000

IDENTITY_DIR = "identity"
VERIFIER_FILE = "human-tip.json"

VERIFIER_REQUIRED_FIELDS = (
    "schema_version", "algo", "salt_hex", "pbkdf2_iterations",
    "chain_length", "counter", "tip_hex", "created_utc", "updated_utc",
)


class IdentityError(SchemaViolation):
    """Token or verifier failed — always fail closed."""


def _h(data: bytes) -> bytes:
    """One domain-separated chain step."""
    return hashlib.sha256(TOKEN_DOMAIN + data).digest()


def derive_seed(passphrase: str, salt: bytes,
                iterations: int = DEFAULT_ITERATIONS) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt,
                               iterations)


def chain_value(seed: bytes, index: int) -> bytes:
    """h^index(seed); index 0 is the seed itself."""
    value = seed
    for _ in range(index):
        value = _h(value)
    return value


def verifier_path(root: str) -> str:
    return os.path.join(root, IDENTITY_DIR, VERIFIER_FILE)


def read_verifier(root: str):
    """The current verifier, or None when identity is uninitialized.
    An unreadable/invalid verifier raises (fail closed) rather than
    reading as 'no identity'."""
    path = verifier_path(root)
    if not os.path.exists(path):
        return None
    import json
    try:
        with open(path, encoding="utf-8") as fh:
            verifier = json.load(fh)
    except (OSError, ValueError) as exc:
        raise IdentityError(f"identity verifier unreadable: {exc}")
    _validate_verifier(verifier)
    return verifier


def _validate_verifier(verifier) -> None:
    if not isinstance(verifier, dict):
        raise IdentityError("verifier must be an object")
    missing = [f for f in VERIFIER_REQUIRED_FIELDS if f not in verifier]
    if missing:
        raise IdentityError(f"verifier missing fields: {missing}")
    if verifier["schema_version"] != "identity.v1" or \
            verifier["algo"] != "skey-sha256-v1":
        raise IdentityError("unsupported verifier schema/algo")
    for name in ("chain_length", "counter", "pbkdf2_iterations"):
        value = verifier[name]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise IdentityError(f"verifier {name} must be a non-negative int")
    if verifier["counter"] > verifier["chain_length"]:
        raise IdentityError("verifier counter exceeds chain length")
    for name in ("salt_hex", "tip_hex"):
        value = verifier[name]
        if not isinstance(value, str) or len(value) != 64 or \
                any(c not in "0123456789abcdef" for c in value):
            raise IdentityError(f"verifier {name} must be 64 lowercase hex")


def _write_verifier(root: str, verifier: dict) -> None:
    os.makedirs(os.path.join(root, IDENTITY_DIR), exist_ok=True)
    storage.atomic_write_json(verifier_path(root), verifier)


# FIXED path (never env-driven — an env override would be agent-forgeable):
# a root-owned, agent-unwritable sha256 of the owner's enrollment token.
# Provisioned ONCE by the owner with sudo; identity bootstrap REFUSES
# without it (cycle-1 blocker 3: the first writer must not own the
# council). The OS boundary is root vs the agent user; an owner whose
# agents hold passwordless sudo has no boundary — documented requirement.
ENROLLMENT_HASH_FILE = "/etc/coliseum/enrollment.sha256"
ENROLLMENT_DOMAIN = b"council:enrollment:v1\x00"


def enrollment_hash(token: str) -> str:
    return hashlib.sha256(
        ENROLLMENT_DOMAIN + token.encode("utf-8")).hexdigest()


def check_enrollment(token: str) -> None:
    """Bootstrap trust anchor: the supplied token must hash to the value
    in the root-owned enrollment file. Missing file = enrollment not
    provisioned = fail closed (no automated path may bootstrap)."""
    try:
        with open(ENROLLMENT_HASH_FILE, encoding="utf-8") as fh:
            want = fh.read().strip().lower()
    except OSError:
        raise IdentityError(
            f"enrollment anchor {ENROLLMENT_HASH_FILE} is not provisioned "
            "— the owner creates it ONCE with sudo (see docs/AUTONOMY.md); "
            "identity bootstrap fails closed without it")
    if len(want) != 64 or any(c not in "0123456789abcdef" for c in want):
        raise IdentityError("enrollment anchor content is not a sha256")
    if enrollment_hash(token or "") != want:
        raise IdentityError("enrollment token does not match the anchor")


def prepare_identity(passphrase: str,
                     chain_length: int = DEFAULT_CHAIN_LENGTH,
                     iterations: int = DEFAULT_ITERATIONS) -> dict:
    """Compute a fresh chain IN MEMORY — nothing is written. The caller
    appends the pin event first, then install_verifier (cycle-1 blocker 2:
    a verifier must never exist without its chain pin)."""
    if not passphrase:
        raise IdentityError("empty passphrase refused")
    if chain_length < 2:
        raise IdentityError("chain_length must be at least 2")
    salt = os.urandom(32)
    seed = derive_seed(passphrase, salt, iterations)
    tip = chain_value(seed, chain_length)
    now = storage.utc_now()
    return {"schema_version": "identity.v1", "algo": "skey-sha256-v1",
            "salt_hex": salt.hex(), "pbkdf2_iterations": iterations,
            "chain_length": chain_length, "counter": chain_length,
            "tip_hex": tip.hex(), "created_utc": now, "updated_utc": now}


def install_verifier(root: str, verifier: dict,
                     allow_overwrite: bool = False) -> None:
    """Write the verifier AFTER its pin event exists in the chain."""
    _validate_verifier(verifier)
    if not allow_overwrite and os.path.exists(verifier_path(root)):
        raise IdentityError("identity already initialized — use rotation")
    _write_verifier(root, verifier)


def init_identity(root: str, passphrase: str,
                  chain_length: int = DEFAULT_CHAIN_LENGTH,
                  iterations: int = DEFAULT_ITERATIONS) -> dict:
    """TEST/legacy helper: prepare + install in one step WITHOUT a chain
    pin. Production bootstrap goes through cli identity-init (enrollment
    anchor + pin-before-install); an unpinned verifier grants NO token
    authority (events._verify_human_token refuses it)."""
    if os.path.exists(verifier_path(root)):
        raise IdentityError("identity already initialized — use rotation")
    verifier = prepare_identity(passphrase, chain_length, iterations)
    _write_verifier(root, verifier)
    return verifier


def compute_token(passphrase: str, verifier: dict) -> dict:
    """The owner-side half: derive the next preimage locally and sanity-
    check it against the tip so a wrong passphrase fails HERE, before any
    token is spent."""
    _validate_verifier(verifier)
    if verifier["counter"] < 1:
        raise IdentityError("token chain exhausted — rotate the identity")
    seed = derive_seed(passphrase, bytes.fromhex(verifier["salt_hex"]),
                       verifier["pbkdf2_iterations"])
    preimage = chain_value(seed, verifier["counter"] - 1)
    if _h(preimage).hex() != verifier["tip_hex"]:
        raise IdentityError("passphrase does not reproduce the chain tip")
    return {"counter": verifier["counter"] - 1,
            "preimage_hex": preimage.hex()}


def binding_hash(event_type: str, request_id: str, target_commit: str,
                 payload_core: dict) -> str:
    """Binds a token to the EXACT action: an intercepted token cannot be
    spent on a different event type, request, commit, or payload."""
    body = {"event_type": event_type, "request_id": request_id,
            "target_commit": target_commit, "payload_core": payload_core}
    return hashlib.sha256(
        BINDING_DOMAIN + canonical_json(body).encode("utf-8")).hexdigest()


def verify_and_advance(root: str, token, expected_binding: str,
                       expected_state: dict = None) -> None:
    """Verify one token and BURN it (advance the tip) — the caller must
    hold the events lock and must append the event only AFTER this
    returns. When the chain has a replayed identity state, the verifier
    must MATCH it exactly — a substituted, stale, or diverged verifier
    file fails closed here (cycle-2: replay equality, not mere lineage)."""
    if not isinstance(token, dict) or \
            not isinstance(token.get("preimage_hex"), str) or \
            not isinstance(token.get("counter"), int) or \
            isinstance(token.get("counter"), bool):
        raise IdentityError("human_token must be {counter, preimage_hex}")
    if token.get("binds") != expected_binding:
        raise IdentityError(
            "token binding does not match this event — a token authorizes "
            "exactly one action")
    verifier = read_verifier(root)
    if verifier is None:
        raise IdentityError(
            "no identity verifier — token-required events fail closed "
            "until identity-init runs")
    if expected_state is not None:
        # the verifier must DESCEND from the chain-replayed state: equal,
        # or ahead by wasted burn-then-append tokens (whose preimages
        # never went public). A verifier BEHIND the chain would revive
        # spent tokens — refused.
        steps = expected_state["counter"] - verifier["counter"]
        if steps < 0 or chain_value(
                bytes.fromhex(verifier["tip_hex"]), steps).hex() \
                != expected_state["tip_hex"]:
            raise IdentityError(
                "verifier does not descend from the chain-replayed "
                "identity state — possible substitution or revived "
                "tokens; fail closed (identity-restore-from-pin realigns "
                "a lost verifier)")
    if token["counter"] != verifier["counter"] - 1:
        raise IdentityError(
            f"token counter {token['counter']} is not the next in "
            f"sequence (expected {verifier['counter'] - 1}) — tokens are "
            "single-use and ordered")
    try:
        preimage = bytes.fromhex(token["preimage_hex"])
    except ValueError:
        raise IdentityError("token preimage is not hex")
    if _h(preimage).hex() != verifier["tip_hex"]:
        raise IdentityError("token preimage does not hash to the tip")
    # BURN before the event is appended: advance the tip durably
    verifier["tip_hex"] = token["preimage_hex"]
    verifier["counter"] = token["counter"]
    verifier["updated_utc"] = storage.utc_now()
    _write_verifier(root, verifier)


def verify_lineage(verifier: dict, pinned_tip_hex: str,
                   pinned_counter: int) -> bool:
    """h^(pinned_counter - counter)(tip) == pinned tip: the stored
    verifier is a legitimate descendant of the chain-pinned tip."""
    steps = pinned_counter - verifier["counter"]
    if steps < 0 or steps > verifier["chain_length"]:
        return False
    return chain_value(bytes.fromhex(verifier["tip_hex"]),
                       steps).hex() == pinned_tip_hex


def verify_historical_token(token: dict, pinned_tip_hex: str,
                            pinned_counter: int) -> bool:
    """Replay verification: any past token checks against the tip pinned
    by the most recent identity event at or before it."""
    steps = pinned_counter - token["counter"]
    if steps < 1:
        return False
    return chain_value(bytes.fromhex(token["preimage_hex"]),
                       steps).hex() == pinned_tip_hex


def _validate_burn(token, tip: str, counter: int, event_id: str) -> None:
    """One historical burn must descend from the running state. Gaps are
    legal (burn-then-append: a crash between burn and append WASTES a
    token whose preimage never went public — the next recorded burn sits
    more than one counter below), but the preimage must hash back to the
    running tip in exactly the counter difference, and moving UP is
    impossible."""
    if not isinstance(token, dict):
        raise IdentityError(
            f"malformed historical token in event {event_id}")
    preimage_hex = token.get("preimage_hex")
    token_counter = token.get("counter")
    if not isinstance(preimage_hex, str) \
            or not isinstance(token_counter, int) \
            or isinstance(token_counter, bool):
        raise IdentityError(
            f"malformed historical token in event {event_id} — refused; "
            "owner review required")
    steps = counter - token_counter
    if steps < 1:
        raise IdentityError(
            f"historical burn in event {event_id} does not move the "
            f"counter down (counter {token_counter}, running {counter}) "
            "— refused")
    try:
        preimage = bytes.fromhex(preimage_hex)
    except ValueError:
        raise IdentityError(
            f"historical token in event {event_id} is not hex — refused")
    if chain_value(preimage, steps).hex() != tip:
        raise IdentityError(
            f"historical token in event {event_id} does not descend from "
            "the running tip — refused")


def replay_identity(chain: list):
    """THE identity authority walk (cycle-2 blocker 1: the chain file is
    agent-writable, so pins and rotations must be validated on replay,
    never trusted by mere presence). Rules:

    - The FIRST HUMAN_IDENTITY_INITIALIZED roots the chain. Any later
      INITIALIZED is inert (re-rooting is impossible; only rotation
      succeeds it) — a directly-appended second init grants nothing.
    - Every human_token in any later event must burn strictly in
      sequence from the running state; ANY inconsistency raises
      (fail closed for every consumer).
    - HUMAN_IDENTITY_ROTATED is valid ONLY when its own token burns
      correctly from the running state; it then re-roots the state to
      the newly pinned chain. A rotation without a valid owner token
      raises.

    Returns (root_pin, state) where root_pin is (tip_hex, counter) of the
    ACTIVE pin lineage (rotations update it) or None pre-cutover, and
    state is the expected CURRENT verifier content
    {tip_hex, counter, chain_length, salt_hex, pbkdf2_iterations} or
    None pre-cutover."""
    root_pin = None
    state = None
    for event in chain:
        etype = event["event_type"]
        payload = event.get("payload", {})
        if etype == "HUMAN_IDENTITY_INITIALIZED":
            if root_pin is None:
                root_pin = (payload["tip_hex"], payload["counter"])
                state = {"tip_hex": payload["tip_hex"],
                         "counter": payload["counter"],
                         "chain_length": payload["chain_length"],
                         "salt_hex": payload["salt_hex"],
                         "pbkdf2_iterations": payload["pbkdf2_iterations"]}
            # later INITIALIZED events are inert — never a re-root
            continue
        token = payload.get("human_token") if isinstance(payload, dict) \
            else None
        if token is not None:
            # cycle-4 blocker: the burn and the ACTION it authorized are
            # inseparable on replay — recompute the binding exactly as
            # append time did; an in-place payload rewrite (same token,
            # re-hashed event) fails here
            expected_binds = binding_hash(
                etype, event["request_id"], event["target_commit"],
                {k: v for k, v in payload.items() if k != "human_token"})
            if token.get("binds") != expected_binds:
                raise IdentityError(
                    f"token binding in event {event['event_id']} does not "
                    "match the event content — history rewritten; refused")
        if etype == "HUMAN_IDENTITY_ROTATED":
            if state is None or token is None:
                raise IdentityError(
                    f"rotation event {event['event_id']} lacks a valid "
                    "owner token — identity history inconsistent; refused")
            _validate_burn(token, state["tip_hex"], state["counter"],
                           event["event_id"])
            root_pin = (payload["tip_hex"], payload["counter"])
            state = {"tip_hex": payload["tip_hex"],
                     "counter": payload["counter"],
                     "chain_length": payload["chain_length"],
                     "salt_hex": payload["salt_hex"],
                     "pbkdf2_iterations": payload["pbkdf2_iterations"]}
            continue
        if token is not None:
            if state is None:
                raise IdentityError(
                    f"event {event['event_id']} carries a human token "
                    "before any identity pin — history inconsistent")
            _validate_burn(token, state["tip_hex"], state["counter"],
                           event["event_id"])
            state = dict(state, tip_hex=token["preimage_hex"],
                         counter=token["counter"])
            continue
        # cycle-3 blocker 1: POST-CUTOVER, a token-required event without
        # a token is not "unvalidated" — it is INVALID history. A
        # hash-consistent direct write cannot make authority appear by
        # omitting the burn.
        if state is not None \
                and etype in HUMAN_TOKEN_REQUIRED_EVENT_TYPES \
                and not (etype == "REQUEST_CANCELED"
                         and event.get("sender") != "human"):
            raise IdentityError(
                f"post-cutover event {event['event_id']} ({etype}) lacks "
                "the required human token — identity history "
                "inconsistent; refused")
    return root_pin, state


def derive_current_from_chain(chain: list) -> dict:
    """Rebuild the CURRENT verifier by replaying the full identity history
    (cycle-1 blocker 1: restoring to the original pin would revive spent
    tokens). Raises on any inconsistency before a caller writes."""
    _root_pin, state = replay_identity(chain)
    if state is None:
        raise IdentityError("no identity pin in the chain — use "
                            "identity-init")
    now = storage.utc_now()
    return {"schema_version": "identity.v1", "algo": "skey-sha256-v1",
            "salt_hex": state["salt_hex"],
            "pbkdf2_iterations": state["pbkdf2_iterations"],
            "chain_length": state["chain_length"],
            "counter": state["counter"], "tip_hex": state["tip_hex"],
            "created_utc": now, "updated_utc": now}


def latest_pin(chain: list):
    """(tip_hex, counter) of the ACTIVE pin lineage (replay-validated),
    or None before the cutover. Raises IdentityError on inconsistent
    identity history — every consumer fails closed."""
    root_pin, _state = replay_identity(chain)
    return root_pin
