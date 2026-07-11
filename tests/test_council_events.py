"""Append-only hash-chained event log: canonical JSON, chaining, tamper
detection, torn-line tolerance."""
import json
import os

import pytest

from tests.council_util import append, make_cfg, make_repo, make_root
from tools.council import events, storage
from tools.council.schemas import (ChainError, CouncilError, GENESIS_HASH,
                                   SchemaViolation, canonical_json,
                                   compute_event_hash)


@pytest.fixture()
def env(tmp_path):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    return root, repo, head, make_cfg(repo, root)


def test_canonical_json_is_sorted_compact_utf8():
    obj = {"b": 1, "a": {"z": [1, 2], "y": "é"}}
    assert canonical_json(obj) == '{"a":{"y":"é","z":[1,2]},"b":1}'


def test_canonical_json_refuses_nan():
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})


def test_genesis_event_chains_from_zero_hash(env):
    root, repo, head, cfg = env
    event = append(root, cfg, "BUILD_STARTED", "claude", "req-aaa",
                   repo, head)
    assert event["previous_event_hash"] == GENESIS_HASH
    assert compute_event_hash(event) == event["event_hash"]


def test_events_chain_and_verify(env):
    root, repo, head, cfg = env
    e1 = append(root, cfg, "BUILD_STARTED", "claude", "req-aaa", repo, head)
    e2 = append(root, cfg, "BUILD_READY", "claude", "req-aaa", repo, head)
    assert e2["previous_event_hash"] == e1["event_hash"]
    report = events.verify_chain(root)
    assert report.ok and report.length == 2
    assert report.head_hash == e2["event_hash"]


def test_event_ids_are_sequential(env):
    root, repo, head, cfg = env
    e1 = append(root, cfg, "BUILD_STARTED", "claude", "req-aaa", repo, head)
    e2 = append(root, cfg, "BUILD_READY", "claude", "req-aaa", repo, head)
    assert e1["event_id"].startswith("000001-")
    assert e2["event_id"].startswith("000002-")


def test_every_required_field_present(env):
    root, repo, head, cfg = env
    event = append(root, cfg, "BUILD_STARTED", "claude", "req-aaa",
                   repo, head, {"k": "v"})
    from tools.council.schemas import EVENT_REQUIRED_FIELDS
    for field in EVENT_REQUIRED_FIELDS:
        assert field in event


def test_tampered_payload_detected(env):
    root, repo, head, cfg = env
    append(root, cfg, "BUILD_STARTED", "claude", "req-aaa", repo, head)
    append(root, cfg, "BUILD_READY", "claude", "req-aaa", repo, head)
    path = storage.events_path(root)
    lines = open(path, encoding="utf-8").read().splitlines()
    doctored = json.loads(lines[0])
    doctored["payload"] = {"injected": True}  # hash NOT recomputed
    lines[0] = canonical_json(doctored)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    report = events.verify_chain(root)
    assert not report.ok and report.error_index == 0
    with pytest.raises(ChainError):
        events.read_chain(root, verify=True)


def test_torn_trailing_line_not_consumed(env):
    root, repo, head, cfg = env
    append(root, cfg, "BUILD_STARTED", "claude", "req-aaa", repo, head)
    path = storage.events_path(root)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write('{"half": "written')  # no newline: torn write
    complete = list(storage.read_events_from(path, 0))
    assert len(complete) == 1  # torn line invisible until finished
    report = events.verify_chain(root)
    assert report.ok and report.length == 1


def test_append_refused_under_emergency_stop(env):
    root, repo, head, cfg = env
    append(root, cfg, "BUILD_STARTED", "claude", "req-aaa", repo, head)
    open(os.path.join(root, "STOP"), "w").close()
    with pytest.raises(CouncilError):
        append(root, cfg, "BUILD_READY", "claude", "req-aaa", repo, head)
    # ...but the stop itself is recordable
    event = events.pause_autonomy(root, cfg, "claude", "req-aaa", repo,
                                  head, "operator stop")
    assert event["event_type"] == "AUTONOMY_PAUSED"


def test_append_refused_when_status_not_active(env):
    root, repo, head, cfg = env
    storage.write_control(root, "paused", ["claude"], "test", None)
    with pytest.raises(CouncilError):
        append(root, cfg, "BUILD_STARTED", "claude", "req-aaa", repo, head)


def test_abbreviated_commit_refused(env):
    root, repo, head, cfg = env
    with pytest.raises(SchemaViolation):
        append(root, cfg, "BUILD_STARTED", "claude", "req-aaa", repo,
               head[:12])
