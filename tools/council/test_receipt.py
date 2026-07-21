"""Commit-bound tamper-evident test receipts (audit-throughput slice 1).

A SOURCE audit round runs N independent section audits over the SAME commit.
Forcing every section to re-run the whole `pytest tests/ -q` suite is redundant:
the code is identical, so the suite result is identical. Instead, ONE full-suite
run at the commit records a `TEST_RECEIPT_RECORDED` event whose content digest
binds it to that exact commit; the other sections VERIFY the receipt — recompute
its digest, check the commit binding and the green count — instead of re-running.

This preserves the anti-fabrication guarantee: a section VERIFIES a
content-addressed record, it does not TRUST a mutable claim. It is at least as
strong as re-running, which trusts the section's own self-reported count.

It is NOT "signed" — there are no keys. Tamper-evidence is the content digest
(`domain_hash(TEST_RECEIPT_DOMAIN, content)`) plus the chain's own hash-linking.
"""
from __future__ import annotations

from tools.council import events
from tools.council.schemas import (
    FULL_TEST_COMMAND, TEST_RECEIPT_DOMAIN, domain_hash,
    test_receipt_content, validate_test_receipt_payload)


def compute_receipt_digest(content: dict) -> str:
    """The tamper-evidence: a domain-separated hash over the receipt content
    (the payload minus the digest field)."""
    return domain_hash(TEST_RECEIPT_DOMAIN, content)


def build_receipt_payload(*, target_commit: str, test_command: str,
                          tests_passed: int, tests_skipped: int,
                          tree_clean: bool, env_fingerprint: str) -> dict:
    """Assemble a receipt payload with its digest. The caller RUNS the suite and
    passes the observed counts; this module only records the tamper-evident
    binding, so it stays deterministic and unit-testable offline."""
    content = {
        "target_commit": target_commit,
        "test_command": test_command,
        "tests_passed": tests_passed,
        "tests_skipped": tests_skipped,
        "tree_clean": tree_clean,
        "env_fingerprint": env_fingerprint,
    }
    payload = dict(content)
    payload["receipt_digest"] = compute_receipt_digest(content)
    return payload


def _receipt_slug(target_commit: str) -> str:
    # synthetic control request_id: the receipt is stateless and carries its
    # authoritative commit in the payload; this only namespaces the record.
    return f"test-receipt-{target_commit[:12]}"


def record_test_receipt(root: str, cfg, *, target_commit: str, repository: str,
                        tests_passed: int, tests_skipped: int,
                        tree_clean: bool, env_fingerprint: str,
                        test_command: str = FULL_TEST_COMMAND,
                        sender: str = "codex") -> dict:
    """Record a commit-bound tamper-evident test receipt as a council event.

    The digest is computed here and re-validated at the append boundary, so a
    receipt whose digest does not match its content is refused on the way in.
    """
    payload = build_receipt_payload(
        target_commit=target_commit, test_command=test_command,
        tests_passed=tests_passed, tests_skipped=tests_skipped,
        tree_clean=tree_clean, env_fingerprint=env_fingerprint)
    return events.append_event(
        root, cfg, "TEST_RECEIPT_RECORDED", sender,
        _receipt_slug(target_commit), repository, target_commit, payload)


def find_test_receipt(chain_or_root, target_commit: str,
                      test_command: str = FULL_TEST_COMMAND):
    """The first TEST_RECEIPT_RECORDED payload for this commit+command, or None.
    (Used to make receipt recording idempotent per commit.)"""
    chain = (events.read_chain(chain_or_root, verify=False)
             if isinstance(chain_or_root, str) else chain_or_root)
    for event in chain:
        if event.get("event_type") != "TEST_RECEIPT_RECORDED":
            continue
        payload = event.get("payload") or {}
        if payload.get("target_commit") == target_commit \
                and payload.get("test_command") == test_command:
            return payload
    return None


def verify_test_receipt(chain_or_root, target_commit: str, expected_count: int,
                        *, test_command: str = FULL_TEST_COMMAND,
                        expected_digest: str = None) -> tuple:
    """(ok, reason). ok is True only when the chain carries a
    TEST_RECEIPT_RECORDED that:
      * names EXACTLY `target_commit` (commit binding),
      * names `test_command` (default the full suite),
      * whose receipt_digest RECOMPUTES from its content (tamper-evidence),
      * was recorded green: tree_clean True and tests_passed == expected_count,
      * and, when `expected_digest` is given, whose digest equals it (so a caller
        can pin the EXACT receipt it verified, not merely some receipt).

    Fail-closed: no receipt, wrong commit, digest mismatch, red, or count
    mismatch -> False.
    """
    chain = (events.read_chain(chain_or_root, verify=False)
             if isinstance(chain_or_root, str) else chain_or_root)

    if not (isinstance(expected_count, int)
            and not isinstance(expected_count, bool) and expected_count > 0):
        return (False,
                f"expected_count must be a positive int, got {expected_count!r}")

    saw_commit = False
    for event in chain:
        if event.get("event_type") != "TEST_RECEIPT_RECORDED":
            continue
        payload = event.get("payload") or {}
        if payload.get("target_commit") != target_commit:
            continue
        saw_commit = True
        if payload.get("test_command") != test_command:
            continue
        # re-validate defensively: a receipt that somehow reached the chain with
        # a tampered digest is caught here too.
        try:
            validate_test_receipt_payload(event)
        except Exception as exc:
            return (False, f"receipt for {target_commit[:12]} failed "
                           f"re-validation: {exc}")
        if compute_receipt_digest(test_receipt_content(payload)) \
                != payload.get("receipt_digest"):
            return (False, f"receipt for {target_commit[:12]} digest mismatch — "
                           "tampered or forged")
        if payload.get("tree_clean") is not True:
            return (False, f"receipt for {target_commit[:12]} was recorded with "
                           "an unclean tree")
        if payload.get("tests_passed") != expected_count:
            return (False, f"receipt for {target_commit[:12]} recorded "
                           f"{payload.get('tests_passed')} passed, not the "
                           f"expected {expected_count}")
        if expected_digest is not None \
                and payload.get("receipt_digest") != expected_digest:
            return (False, f"receipt for {target_commit[:12]} exists but its "
                           "digest does not match the pinned expected_digest")
        return (True, f"verified commit-bound receipt for {target_commit[:12]}: "
                      f"{payload['tests_passed']} passed / "
                      f"{payload['tests_skipped']} skipped under "
                      f"{test_command!r}")

    if saw_commit:
        return (False, f"a receipt exists for {target_commit[:12]} but none "
                       f"matches test_command {test_command!r}")
    return (False, f"no TEST_RECEIPT_RECORDED for commit {target_commit[:12]}")
