"""H1: unforgeable human identity (S/KEY one-time token chain) and the
fail-closed control record. A caller-supplied --role/sender string is
never sufficient for human authority; log.md is cosmetic."""
import json
import os

import pytest

from tests.council_util import (TEST_CHAIN_LENGTH, TEST_ITERATIONS,
                                TEST_PASSPHRASE, append, drive_to_claimed,
                                human_token, make_cfg, make_repo, make_root)
from tools.council import cli, events, identity, locking, storage
from tools.council.schemas import CouncilError, SchemaViolation

RID = "identity-req-001"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    monkeypatch.setenv("COUNCIL_ROOT", root)
    monkeypatch.setenv("COUNCIL_REPO_ROOTS", repo)
    return root, repo, head, cfg


def _drive_to_awaiting_human(root, cfg, repo, head):
    ctx = drive_to_claimed(root, cfg, repo, head, request_id=RID)
    append(root, cfg, "AUDIT_GO", "codex", RID, repo, head)
    append(root, cfg, "HUMAN_APPROVAL_REQUIRED", "claude", RID, repo, head)
    return ctx


# ---------------------------------------------------------- chain math

def test_chain_math_roundtrip(tmp_path):
    root = str(tmp_path / "c")
    os.makedirs(root)
    verifier = identity.init_identity(root, "pw", chain_length=8,
                                      iterations=100)
    token = identity.compute_token("pw", verifier)
    assert token["counter"] == 7
    assert identity._h(bytes.fromhex(token["preimage_hex"])).hex() \
        == verifier["tip_hex"]


def test_wrong_passphrase_fails_locally(tmp_path):
    root = str(tmp_path / "c")
    os.makedirs(root)
    verifier = identity.init_identity(root, "pw", chain_length=8,
                                      iterations=100)
    with pytest.raises(identity.IdentityError):
        identity.compute_token("wrong", verifier)


def test_init_refuses_overwrite(env):
    root, *_ = env
    with pytest.raises(identity.IdentityError):
        identity.init_identity(root, "another", chain_length=8)


def test_historical_token_verifies_against_pinned_tip(env):
    root, *_ = env
    verifier = identity.read_verifier(root)
    pinned = (verifier["tip_hex"], verifier["counter"])
    t1 = identity.compute_token(TEST_PASSPHRASE, verifier)
    identity.verify_and_advance(root, dict(t1, binds="x"), "x")
    v2 = identity.read_verifier(root)
    t2 = identity.compute_token(TEST_PASSPHRASE, v2)
    identity.verify_and_advance(root, dict(t2, binds="y"), "y")
    # both spent tokens replay-verify against the ORIGINAL pinned tip
    assert identity.verify_historical_token(t1, *pinned)
    assert identity.verify_historical_token(t2, *pinned)
    forged = dict(t2, preimage_hex="0" * 64)
    assert not identity.verify_historical_token(forged, *pinned)


# ------------------------------------------------- token gate at append

def test_forged_role_without_token_is_refused(env):
    """THE H1 probe: sender='human' (the old --role string authority) is
    no longer sufficient — no token, no approval."""
    root, repo, head, cfg = env
    _drive_to_awaiting_human(root, cfg, repo, head)
    with pytest.raises(CouncilError):
        events.append_event(root, cfg, "EXPERIMENT_APPROVED", "human", RID,
                            repo, head, {"approved_by": "human"})
    types = [e["event_type"] for e in events.read_chain(root)]
    assert "EXPERIMENT_APPROVED" not in types


def test_valid_token_approves_and_burns(env):
    root, repo, head, cfg = env
    _drive_to_awaiting_human(root, cfg, repo, head)
    before = identity.read_verifier(root)["counter"]
    append(root, cfg, "EXPERIMENT_APPROVED", "human", RID, repo, head,
           {"approved_by": "human"})  # autofilled token
    after = identity.read_verifier(root)
    assert after["counter"] == before - 1  # burned
    assert events.read_chain(root)[-1]["event_type"] == "EXPERIMENT_APPROVED"


def test_token_replay_is_refused(env):
    root, repo, head, cfg = env
    _drive_to_awaiting_human(root, cfg, repo, head)
    payload_core = {"approved_by": "human"}
    token = human_token(root, "EXPERIMENT_APPROVED", RID, head, payload_core)
    events.append_event(root, cfg, "EXPERIMENT_APPROVED", "human", RID,
                        repo, head, dict(payload_core, human_token=token))
    # replaying the SAME token on another event (cancel) must refuse
    replay = dict(token)
    replay["binds"] = identity.binding_hash("REQUEST_CANCELED", RID, head,
                                            {"reason": "r"})
    with pytest.raises(CouncilError):
        events.append_event(root, cfg, "REQUEST_CANCELED", "human", RID,
                            repo, head,
                            {"reason": "r", "human_token": replay})


def test_token_bound_to_action_cannot_be_diverted(env):
    """An intercepted token minted for a PAUSE cannot authorize an
    UNPAUSE — the binding covers the payload."""
    root, repo, head, cfg = env
    core_pause = {"status": "paused", "paused_roles": ["all"], "reason": ""}
    token = human_token(root, "STATUS_CHANGED", "council-control", "0" * 40,
                        core_pause)
    core_active = {"status": "active", "paused_roles": [], "reason": ""}
    with pytest.raises(CouncilError):
        events.append_event(root, cfg, "STATUS_CHANGED", "human",
                            "council-control", repo, "0" * 40,
                            dict(core_active, human_token=token))


def test_out_of_order_token_refused(env):
    root, repo, head, cfg = env
    verifier = identity.read_verifier(root)
    seed = identity.derive_seed(TEST_PASSPHRASE,
                                bytes.fromhex(verifier["salt_hex"]),
                                TEST_ITERATIONS)
    # a token two steps ahead (skip) must refuse
    skip = {"counter": verifier["counter"] - 2,
            "preimage_hex": identity.chain_value(
                seed, verifier["counter"] - 2).hex()}
    skip["binds"] = identity.binding_hash("STATUS_CHANGED",
                                          "council-control", "0" * 40, {})
    with pytest.raises(identity.IdentityError):
        identity.verify_and_advance(root, skip, skip["binds"])


def test_claude_cancel_needs_no_token_but_grants_nothing(env):
    root, repo, head, cfg = env
    drive_to_claimed(root, cfg, repo, head, request_id=RID)
    before = identity.read_verifier(root)["counter"]
    append(root, cfg, "REQUEST_CANCELED", "claude", RID, repo, head,
           {"reason": "revoke"})
    assert identity.read_verifier(root)["counter"] == before  # no burn


def test_verifier_deletion_fails_closed(env):
    """Deleting the verifier cannot disable tokens once the chain pins an
    identity."""
    root, repo, head, cfg = env
    # pin the identity into the chain (as identity-init would)
    verifier = identity.read_verifier(root)
    events.append_event(root, cfg, "HUMAN_IDENTITY_INITIALIZED", "human",
                        "council-identity", repo, "0" * 40,
                        {"schema_version": "identity.v1",
                         "tip_hex": verifier["tip_hex"],
                         "counter": verifier["counter"],
                         "chain_length": verifier["chain_length"],
                         "salt_hex": verifier["salt_hex"],
                         "pbkdf2_iterations": verifier["pbkdf2_iterations"]})
    _drive_to_awaiting_human(root, cfg, repo, head)
    os.unlink(identity.verifier_path(root))
    with pytest.raises(CouncilError):
        events.append_event(root, cfg, "EXPERIMENT_APPROVED", "human", RID,
                            repo, head, {"approved_by": "human"})


def test_substituted_verifier_fails_lineage(env):
    """An attacker-planted verifier (own chain) does not descend from the
    pinned tip: tokens minted from it are refused."""
    root, repo, head, cfg = env
    verifier = identity.read_verifier(root)
    events.append_event(root, cfg, "HUMAN_IDENTITY_INITIALIZED", "human",
                        "council-identity", repo, "0" * 40,
                        {"schema_version": "identity.v1",
                         "tip_hex": verifier["tip_hex"],
                         "counter": verifier["counter"],
                         "chain_length": verifier["chain_length"],
                         "salt_hex": verifier["salt_hex"],
                         "pbkdf2_iterations": verifier["pbkdf2_iterations"]})
    os.unlink(identity.verifier_path(root))
    identity.init_identity(root, "attacker-passphrase",
                           chain_length=TEST_CHAIN_LENGTH,
                           iterations=TEST_ITERATIONS)
    _drive_to_awaiting_human(root, cfg, repo, head)
    forged = identity.compute_token("attacker-passphrase",
                                    identity.read_verifier(root))
    payload_core = {"approved_by": "human"}
    forged["binds"] = identity.binding_hash("EXPERIMENT_APPROVED", RID,
                                            head, payload_core)
    with pytest.raises(CouncilError):
        events.append_event(root, cfg, "EXPERIMENT_APPROVED", "human", RID,
                            repo, head,
                            dict(payload_core, human_token=forged))


def test_burn_then_append_never_leaves_spendable_token(env, monkeypatch):
    """A crash between the burn and the append wastes exactly one token;
    the next counter value still works and the wasted one never does."""
    root, repo, head, cfg = env
    _drive_to_awaiting_human(root, cfg, repo, head)
    real_append_line = storage.append_line

    def boom(path, line):
        raise OSError("simulated crash after burn")
    monkeypatch.setattr(storage, "append_line", boom)
    payload_core = {"approved_by": "human"}
    token = human_token(root, "EXPERIMENT_APPROVED", RID, head, payload_core)
    with pytest.raises(OSError):
        events.append_event(root, cfg, "EXPERIMENT_APPROVED", "human", RID,
                            repo, head, dict(payload_core,
                                             human_token=token))
    monkeypatch.setattr(storage, "append_line", real_append_line)
    types = [e["event_type"] for e in events.read_chain(root)]
    assert "EXPERIMENT_APPROVED" not in types  # nothing appended
    # the burned token is dead ...
    with pytest.raises(CouncilError):
        events.append_event(root, cfg, "EXPERIMENT_APPROVED", "human", RID,
                            repo, head, dict(payload_core,
                                             human_token=token))
    # ... and the NEXT one works (owner retries)
    append(root, cfg, "EXPERIMENT_APPROVED", "human", RID, repo, head,
           dict(payload_core))


def test_exhausted_chain_refuses(tmp_path):
    root = str(tmp_path / "c")
    os.makedirs(root)
    verifier = identity.init_identity(root, "pw", chain_length=2,
                                      iterations=100)
    t1 = identity.compute_token("pw", verifier)
    identity.verify_and_advance(root, dict(t1, binds="a"), "a")
    t2 = identity.compute_token("pw", identity.read_verifier(root))
    identity.verify_and_advance(root, dict(t2, binds="b"), "b")
    with pytest.raises(identity.IdentityError):
        identity.compute_token("pw", identity.read_verifier(root))


# ---------------------------------------------------- control record

def test_missing_control_fails_closed(env):
    root, repo, head, cfg = env
    os.unlink(storage.control_path(root))
    assert storage.emergency_stop_reason(root) is not None
    assert not storage.status_allows(root, "claude")
    with pytest.raises(CouncilError):
        append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)


@pytest.mark.parametrize("garbage", [
    "not json", '{"schema_version":"control.v1","status":"maybe"}',
    '{"status":"active"}', '[]',
    '{"schema_version":"control.v1","status":"active","paused_roles":"x"}',
])
def test_invalid_control_fails_closed(env, garbage):
    root, *_ = env
    with open(storage.control_path(root), "w", encoding="utf-8") as fh:
        fh.write(garbage)
    assert storage.read_control(root)["status"] == "paused"
    assert storage.emergency_stop_reason(root) is not None


def test_log_md_edits_never_resume(env):
    root, repo, head, cfg = env
    storage.write_control(root, "paused", ["all"], "owner pause", None)
    with open(os.path.join(root, "log.md"), "w", encoding="utf-8") as fh:
        fh.write("STATUS: active\n")  # forged cosmetic mirror
    assert storage.emergency_stop_reason(root) is not None
    with pytest.raises(CouncilError):
        append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)


def test_status_set_unpauses_through_token_event(env):
    root, repo, head, cfg = env
    storage.write_control(root, "paused", ["all"], "pause", None)
    rc = cli.main(["--role", "human", "status-set", "--status", "active"])
    assert rc == 0
    assert storage.emergency_stop_reason(root) is None
    last = events.read_chain(root)[-1]
    assert last["event_type"] == "STATUS_CHANGED"
    assert "human_token" in last["payload"]


def test_status_set_refused_under_stop_file(env):
    root, repo, head, cfg = env
    open(os.path.join(root, "STOP"), "w").close()
    rc = cli.main(["--role", "human", "status-set", "--status", "active"])
    assert rc == 1  # STOP is the hard emergency; only removing it helps
    assert storage.read_control(root)["status"] == "active"  # unchanged


def test_status_set_without_role_human_refused(env):
    root, *_ = env
    assert cli.main(["--role", "claude", "status-set",
                     "--status", "active"]) == 1


# ------------------------------------------------------ record allowlist

@pytest.mark.parametrize("etype", [
    "EXPERIMENT_APPROVED", "CONDITIONS_SATISFIED", "AUDIT_GO",
    "AUDIT_BLOCKED", "RESULT_APPROVED", "AUTO_APPROVED",
    "POLICY_VALIDATION_REQUIRED", "AUDIT_REQUESTED", "READY_FOR_REAUDIT",
    "AUDIT_CLAIMED", "EXPERIMENT_STARTED", "CHANGE_INTEGRATED",
    "NEXT_MILESTONE_READY", "STATUS_CHANGED", "HUMAN_IDENTITY_INITIALIZED",
    "AUTONOMY_MILESTONE_REACHED", "HUMAN_APPROVAL_REQUIRED",
])
def test_record_refuses_authority_events(env, etype):
    root, repo, head, cfg = env
    rc = cli.main(["--role", "human", "record", "--type", etype,
                   "--request-id", RID, "--repository", repo,
                   "--commit", head])
    assert rc == 1


def test_record_allows_bookkeeping(env):
    root, repo, head, cfg = env
    rc = cli.main(["--role", "claude", "record", "--type", "BUILD_STARTED",
                   "--request-id", RID, "--repository", repo,
                   "--commit", head])
    assert rc == 0


# ------------------------------------------------------------ CLI flows

def test_cli_approve_mints_and_burns_token(env):
    root, repo, head, cfg = env
    ctx = _drive_to_awaiting_human(root, cfg, repo, head)
    before = identity.read_verifier(root)["counter"]
    rc = cli.main(["--role", "human", "approve", RID, "--commit", head])
    assert rc == 0
    assert identity.read_verifier(root)["counter"] == before - 1
    last = events.read_chain(root)[-1]
    assert last["event_type"] == "EXPERIMENT_APPROVED"
    assert last["payload"]["human_token"]["counter"] == before - 1
    locking.release(ctx["lock"])


def _enrollment(tmp_path, monkeypatch, token="owner-enrollment-secret"):
    """A provisioned enrollment anchor (root-owned in production; tmp
    here) + the matching token file."""
    anchor = tmp_path / "enrollment.sha256"
    anchor.write_text(identity.enrollment_hash(token))
    monkeypatch.setattr(identity, "ENROLLMENT_HASH_FILE", str(anchor))
    token_file = tmp_path / "enrollment-token.txt"
    token_file.write_text(token)
    return str(token_file)


def test_cli_identity_init_and_status_and_rotate(tmp_path, monkeypatch):
    root = str(tmp_path / "fresh")
    os.makedirs(root)
    storage.ensure_layout(root)
    repo, head = make_repo(tmp_path)
    monkeypatch.setenv("COUNCIL_ROOT", root)
    monkeypatch.setenv("COUNCIL_REPO_ROOTS", repo)
    etok = _enrollment(tmp_path, monkeypatch)
    pw = tmp_path / "pw.txt"
    pw.write_text(TEST_PASSPHRASE)
    # fresh root is fail-closed; identity-init is a bootstrap event
    rc = cli.main(["--role", "human", "identity-init", "--chain-length",
                   "16", "--passphrase-file", str(pw),
                   "--enrollment-token-file", etok])
    assert rc == 0
    assert cli.main(["identity-status"]) == 0
    chain = events.read_chain(root)
    assert chain[-1]["event_type"] == "HUMAN_IDENTITY_INITIALIZED"
    # activate, then rotate (burns one old token, pins the new tip)
    assert cli.main(["--role", "human", "status-set",
                     "--status", "active"]) == 0
    before = identity.read_verifier(root)["counter"]
    rc = cli.main(["--role", "human", "identity-rotate", "--chain-length",
                   "16", "--passphrase-file", str(pw)])
    assert rc == 0
    rotated = identity.read_verifier(root)
    assert rotated["counter"] == 16 and rotated["counter"] != before - 1
    assert events.read_chain(root)[-1]["event_type"] == \
        "HUMAN_IDENTITY_ROTATED"
    assert cli.main(["identity-status"]) == 0


def test_cli_identity_restore_from_pin(env):
    root, repo, head, cfg = env
    verifier = identity.read_verifier(root)
    events.append_event(root, cfg, "HUMAN_IDENTITY_INITIALIZED", "human",
                        "council-identity", repo, "0" * 40,
                        {"schema_version": "identity.v1",
                         "tip_hex": verifier["tip_hex"],
                         "counter": verifier["counter"],
                         "chain_length": verifier["chain_length"],
                         "salt_hex": verifier["salt_hex"],
                         "pbkdf2_iterations": verifier["pbkdf2_iterations"]})
    os.unlink(identity.verifier_path(root))
    assert cli.main(["identity-status"]) == 1  # fail closed
    assert cli.main(["--role", "human", "identity-restore-from-pin"]) == 0
    assert cli.main(["identity-status"]) == 0
    restored = identity.read_verifier(root)
    assert restored["tip_hex"] == verifier["tip_hex"]


# -------------------------- cycle-2 blockers: identity lifecycle safety

def test_restore_replays_burns_and_keeps_tokens_dead(env):
    """Cycle-2 blocker 1 regression: after burns, deletion, and restore,
    the counter equals the LAST burn and every spent token stays dead."""
    root, repo, head, cfg = env
    core1 = {"status": "paused", "paused_roles": ["all"], "reason": "a"}
    t1 = human_token(root, "STATUS_CHANGED", "council-control", "0" * 40,
                     core1)
    events.append_event(root, cfg, "STATUS_CHANGED", "human",
                        "council-control", repo, "0" * 40,
                        dict(core1, human_token=t1))
    storage.write_control(root, "active", [], "test", None)  # keep active
    core2 = {"status": "active", "paused_roles": [], "reason": "b"}
    t2 = human_token(root, "STATUS_CHANGED", "council-control", "0" * 40,
                     core2)
    events.append_event(root, cfg, "STATUS_CHANGED", "human",
                        "council-control", repo, "0" * 40,
                        dict(core2, human_token=t2))
    burned_to = identity.read_verifier(root)["counter"]
    assert burned_to == TEST_CHAIN_LENGTH - 2
    os.unlink(identity.verifier_path(root))
    assert cli.main(["--role", "human", "identity-restore-from-pin"]) == 0
    restored = identity.read_verifier(root)
    assert restored["counter"] == burned_to          # NOT the pin value
    assert restored["tip_hex"] == t2["preimage_hex"]  # tip = last burn
    # both spent tokens are dead after restore
    for spent in (t1, t2):
        replay = dict(spent)
        replay["binds"] = identity.binding_hash(
            "STATUS_CHANGED", "council-control", "0" * 40, core2)
        with pytest.raises(CouncilError):
            events.append_event(root, cfg, "STATUS_CHANGED", "human",
                                "council-control", repo, "0" * 40,
                                dict(core2, human_token=replay))
    # ...and the legitimate next token still works
    append(root, cfg, "STATUS_CHANGED", "human", "council-control", repo,
           "0" * 40, dict(core2))


def test_restore_refuses_inconsistent_history(env):
    """A hash-chained but cryptographically inconsistent burn history
    refuses recovery without writing anything."""
    from tools.council.schemas import canonical_json, compute_event_hash
    root, repo, head, cfg = env
    chain = events.read_chain(root)
    bogus = {"protocol_version": "1.0",
             "event_id": f"{len(chain) + 1:06d}-deadbeef",
             "event_type": "STATUS_CHANGED", "request_id": "council-control",
             "sender": "human", "timestamp_utc": storage.utc_now(),
             "repository": repo, "target_commit": "0" * 40,
             "payload": {"status": "active", "paused_roles": [],
                         "reason": "", "human_token": {
                             "counter": TEST_CHAIN_LENGTH - 7,
                             "preimage_hex": "0" * 64, "binds": "x"}},
             "previous_event_hash": chain[-1]["event_hash"]}
    bogus["event_hash"] = compute_event_hash(bogus)
    storage.append_line(storage.events_path(root), canonical_json(bogus))
    os.unlink(identity.verifier_path(root))
    assert cli.main(["--role", "human", "identity-restore-from-pin"]) == 1
    assert identity.read_verifier(root) is None  # nothing was written


def test_failed_init_leaves_no_verifier(tmp_path, monkeypatch):
    """Cycle-2 blocker 2 regression: every init failure — STOP file,
    refused append, write fault — leaves NO verifier behind."""
    root = str(tmp_path / "fresh")
    os.makedirs(root)
    storage.ensure_layout(root)
    repo, head = make_repo(tmp_path)
    monkeypatch.setenv("COUNCIL_ROOT", root)
    monkeypatch.setenv("COUNCIL_REPO_ROOTS", repo)
    etok = _enrollment(tmp_path, monkeypatch)
    pw = tmp_path / "pw.txt"
    pw.write_text(TEST_PASSPHRASE)
    argv = ["--role", "human", "identity-init", "--chain-length", "16",
            "--passphrase-file", str(pw), "--enrollment-token-file", etok]
    # STOP file: the pin append refuses; no verifier may exist
    open(os.path.join(root, "STOP"), "w").close()
    assert cli.main(argv) == 1
    assert identity.read_verifier(root) is None
    assert events.read_chain(root) == []
    os.unlink(os.path.join(root, "STOP"))
    # injected append fault: same guarantee
    def boom(*a, **k):
        raise CouncilError("simulated append failure")
    with monkeypatch.context() as m:
        m.setattr(events, "append_event", boom)
        assert cli.main(argv) == 1
    assert identity.read_verifier(root) is None
    # and after the faults clear, init succeeds cleanly
    assert cli.main(argv) == 0
    assert identity.read_verifier(root) is not None


def test_unpinned_verifier_never_authorizes(tmp_path):
    """Cycle-2 blocker 2, second half: a verifier with NO chain pin is
    not bootstrap-compatible — every token event fails closed."""
    root = str(tmp_path / "unpinned")
    os.makedirs(root)
    storage.ensure_layout(root)
    storage.write_control(root, "active", [], "test", None)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    identity.init_identity(root, TEST_PASSPHRASE, chain_length=8,
                           iterations=100)  # unpinned (test/legacy helper)
    verifier = identity.read_verifier(root)
    token = identity.compute_token(TEST_PASSPHRASE, verifier)
    core = {"status": "paused", "paused_roles": ["all"], "reason": ""}
    token["binds"] = identity.binding_hash("STATUS_CHANGED",
                                           "council-control", "0" * 40, core)
    with pytest.raises(CouncilError):
        events.append_event(root, cfg, "STATUS_CHANGED", "human",
                            "council-control", repo, "0" * 40,
                            dict(core, human_token=token))


def test_bootstrap_refused_without_enrollment_anchor(tmp_path, monkeypatch):
    """Cycle-2 blocker 3 regression: no anchor, no bootstrap — an agent
    invoking identity-init on a fresh root establishes nothing."""
    root = str(tmp_path / "fresh")
    os.makedirs(root)
    storage.ensure_layout(root)
    repo, head = make_repo(tmp_path)
    monkeypatch.setenv("COUNCIL_ROOT", root)
    monkeypatch.setenv("COUNCIL_REPO_ROOTS", repo)
    monkeypatch.setattr(identity, "ENROLLMENT_HASH_FILE",
                        str(tmp_path / "missing" / "anchor.sha256"))
    pw = tmp_path / "pw.txt"
    pw.write_text("attacker-passphrase")
    rc = cli.main(["--role", "human", "identity-init", "--chain-length",
                   "16", "--passphrase-file", str(pw),
                   "--enrollment-token-file", str(pw)])
    assert rc == 1
    assert identity.read_verifier(root) is None
    assert events.read_chain(root) == []  # no pin, nothing established


def test_bootstrap_refused_with_wrong_enrollment_token(tmp_path,
                                                       monkeypatch):
    root = str(tmp_path / "fresh")
    os.makedirs(root)
    storage.ensure_layout(root)
    repo, head = make_repo(tmp_path)
    monkeypatch.setenv("COUNCIL_ROOT", root)
    monkeypatch.setenv("COUNCIL_REPO_ROOTS", repo)
    _enrollment(tmp_path, monkeypatch, token="the-real-secret")
    wrong = tmp_path / "wrong.txt"
    wrong.write_text("attacker-guess")
    pw = tmp_path / "pw.txt"
    pw.write_text("attacker-passphrase")
    rc = cli.main(["--role", "human", "identity-init", "--chain-length",
                   "16", "--passphrase-file", str(pw),
                   "--enrollment-token-file", str(wrong)])
    assert rc == 1
    assert identity.read_verifier(root) is None
    assert events.read_chain(root) == []


def test_pre_cutover_root_stays_tokenless(tmp_path, monkeypatch):
    """A legacy root (no verifier, no pin) keeps its old behavior — the
    cutover is explicit, never implicit."""
    root = str(tmp_path / "legacy")
    os.makedirs(root)
    storage.ensure_layout(root)
    storage.write_control(root, "active", [], "legacy", None)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    ctx = drive_to_claimed(root, cfg, repo, head, request_id=RID)
    events.append_event(root, cfg, "AUDIT_GO", "codex", RID, repo, head,
                        _legacy_go(head))
    events.append_event(root, cfg, "HUMAN_APPROVAL_REQUIRED", "claude",
                        RID, repo, head, {})
    events.append_event(root, cfg, "EXPERIMENT_APPROVED", "human", RID,
                        repo, head, {"approved_by": "human"})  # no token
    assert events.read_chain(root)[-1]["event_type"] == \
        "EXPERIMENT_APPROVED"
    locking.release(ctx["lock"])


def _legacy_go(head):
    from tests.council_util import make_verdict
    from tools.council.schemas import compute_verdict_payload_hash
    verdict = make_verdict(head, RID, verdict="GO")
    verdict["verdict_payload_hash"] = compute_verdict_payload_hash(verdict)
    return verdict
