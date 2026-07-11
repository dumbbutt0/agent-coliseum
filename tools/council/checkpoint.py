"""Root-owned chain-head checkpoint (hardening H4, carried from the H1
cycle-5 residual).

An in-place rewrite of events.jsonl by the file custodian is undetectable
by any value the agent can recompute (a rewriter who re-hashes the chain
recomputes every derived hash too). The only defense is an external
commitment OUTSIDE the custodian's write authority: a root-owned file at a
FIXED path holding {length, head_hash} at a checkpoint. The owner updates
it with sudo at chosen moments; verification confirms the live chain still
carries that exact event_hash at that position, so any historical rewrite
at or before the checkpoint fails closed.

Absent file = not yet provisioned = no checkpoint constraint (unlike the
enrollment anchor, whose absence fails bootstrap). The OS boundary is root
vs the agent user; passwordless-sudo agents have no boundary (documented).
"""
from __future__ import annotations

import os

from tools.council.schemas import SchemaViolation
from tools.council.strictjson import StrictJSONError, load_strict_file

CHECKPOINT_FILE = "/etc/coliseum/chain-head.sha256"
_SHA256_LEN = 64


def read_checkpoint():
    """{length, head_hash} or None when not provisioned. Raises on an
    unreadable/malformed file (fail closed)."""
    if not os.path.exists(CHECKPOINT_FILE):
        return None
    try:
        data = load_strict_file(CHECKPOINT_FILE, max_bytes=4_096)
    except (OSError, ValueError, StrictJSONError) as exc:
        raise SchemaViolation(f"chain-head checkpoint unreadable: {exc}")
    if not isinstance(data, dict) \
            or not isinstance(data.get("length"), int) \
            or isinstance(data.get("length"), bool) \
            or data["length"] < 1 \
            or not isinstance(data.get("head_hash"), str) \
            or len(data["head_hash"]) != _SHA256_LEN:
        raise SchemaViolation("chain-head checkpoint is malformed")
    return data


def verify_checkpoint(chain: list):
    """None if no checkpoint is provisioned or the chain still carries the
    checkpointed event_hash at the checkpointed position; a failure string
    otherwise (the prefix at/before the checkpoint was rewritten, or the
    chain is now shorter than the checkpoint — history cannot shrink)."""
    cp = read_checkpoint()
    if cp is None:
        return None
    if len(chain) < cp["length"]:
        return (f"chain is {len(chain)} events but the checkpoint pins "
                f"{cp['length']} — history cannot shrink")
    actual = chain[cp["length"] - 1]["event_hash"]
    if actual != cp["head_hash"]:
        return (f"event #{cp['length']} hash {actual[:12]} != the "
                f"checkpointed {cp['head_hash'][:12]} — the chain prefix "
                "was rewritten")
    return None


def render_checkpoint(chain: list) -> dict:
    """The {length, head_hash} an owner would write at the current head —
    printed by `cli checkpoint-status` so the owner can sudo-install it."""
    if not chain:
        raise SchemaViolation("empty chain has no head to checkpoint")
    return {"length": len(chain), "head_hash": chain[-1]["event_hash"]}
