"""O_EXCL locks: exclusivity, holder metadata, logged clearance only."""
import json
import os

import pytest

from tests.council_util import make_cfg, make_repo, make_root
from tools.council import events, locking, storage
from tools.council.schemas import LockHeld


@pytest.fixture()
def env(tmp_path):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    return root, repo, head, make_cfg(repo, root)


def test_second_acquire_raises_lockheld(env):
    root, _repo, _head, _cfg = env
    lock = locking.acquire(root, "some-request-01", "codex",
                           "some-request-01")
    with pytest.raises(LockHeld):
        locking.acquire(root, "some-request-01", "codex", "some-request-01")
    locking.release(lock)
    # released -> acquirable again
    lock2 = locking.acquire(root, "some-request-01", "codex",
                            "some-request-01")
    locking.release(lock2)


def test_lock_records_holder_identity(env):
    root, _repo, _head, _cfg = env
    locking.acquire(root, "some-request-01", "codex", "some-request-01")
    holder = locking.read_lock(root, "some-request-01")
    for field in ("request_id", "role", "pid", "host", "timestamp_utc"):
        assert field in holder
    assert holder["role"] == "codex"
    assert holder["pid"] == os.getpid()
    assert holder["request_id"] == "some-request-01"


def test_events_lock_serializes_appends(env):
    root, repo, head, cfg = env
    held = locking.acquire_events_lock(root, "claude", "req-aaa")
    with pytest.raises(LockHeld):
        # bounded retry, tiny budget so the test is fast
        locking.acquire_events_lock(root, "codex", "req-aaa",
                                    attempts=2, delay=0.01)
    locking.release(held)
    event = events.append_event(root, cfg, "BUILD_STARTED", "claude",
                                "req-aaa", repo, head, {})
    assert event["event_type"] == "BUILD_STARTED"


def test_clear_lock_via_cli_logs_first(env, monkeypatch):
    root, repo, _head, _cfg = env
    locking.acquire(root, "stale-request-01", "codex", "stale-request-01")
    monkeypatch.setenv("COUNCIL_ROOT", root)
    monkeypatch.setenv("COUNCIL_REPO_ROOTS", repo)
    from tools.council import cli
    rc = cli.main(["--role", "human", "clear-lock", "stale-request-01",
                   "--reason", "codex crashed mid-audit"])
    assert rc == 0
    assert locking.read_lock(root, "stale-request-01") is None
    chain = events.read_chain(root)
    assert chain[-1]["event_type"] == "WATCHER_ERROR"
    assert chain[-1]["payload"]["operation"] == "clear_stale_lock"
    assert chain[-1]["payload"]["previous_holder"]["role"] == "codex"
    assert chain[-1]["payload"]["reason"] == "codex crashed mid-audit"


def test_lock_path_refuses_traversal(env):
    root, _repo, _head, _cfg = env
    from tools.council.schemas import SchemaViolation
    with pytest.raises(SchemaViolation):
        storage.lock_path(root, "../escape")
