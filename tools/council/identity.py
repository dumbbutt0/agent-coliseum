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
from tools.council.schemas import SchemaViolation, canonical_json

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


def init_identity(root: str, passphrase: str,
                  chain_length: int = DEFAULT_CHAIN_LENGTH,
                  iterations: int = DEFAULT_ITERATIONS) -> dict:
    """Create the chain and store the tip verifier. Refuses to overwrite —
    rotation is the only sanctioned replacement (identity-rotate)."""
    if os.path.exists(verifier_path(root)):
        raise IdentityError("identity already initialized — use rotation")
    if not passphrase:
        raise IdentityError("empty passphrase refused")
    if chain_length < 2:
        raise IdentityError("chain_length must be at least 2")
    salt = os.urandom(32)
    seed = derive_seed(passphrase, salt, iterations)
    tip = chain_value(seed, chain_length)
    now = storage.utc_now()
    verifier = {"schema_version": "identity.v1", "algo": "skey-sha256-v1",
                "salt_hex": salt.hex(), "pbkdf2_iterations": iterations,
                "chain_length": chain_length, "counter": chain_length,
                "tip_hex": tip.hex(), "created_utc": now,
                "updated_utc": now}
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
                       pinned_tip_hex: str = None,
                       pinned_counter: int = None) -> None:
    """Verify one token and BURN it (advance the tip) — the caller must
    hold the events lock and must append the event only AFTER this
    returns. When the chain has a pinned tip (HUMAN_IDENTITY_INITIALIZED/
    ROTATED), the current verifier must descend from it — a substituted
    verifier file fails closed here."""
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
    if pinned_tip_hex is not None:
        if not verify_lineage(verifier, pinned_tip_hex, pinned_counter):
            raise IdentityError(
                "verifier does not descend from the chain-pinned tip — "
                "possible verifier substitution; fail closed")
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


def latest_pin(chain: list):
    """(tip_hex, counter) from the most recent identity-pinning event in
    the chain, or None before the cutover."""
    pin = None
    for event in chain:
        if event["event_type"] in ("HUMAN_IDENTITY_INITIALIZED",
                                   "HUMAN_IDENTITY_ROTATED"):
            payload = event["payload"]
            pin = (payload["tip_hex"], payload["counter"])
    return pin
