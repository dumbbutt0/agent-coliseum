"""H2 item 12 + protocol 2.0: domain-separated hashing and version-
dispatched event hashing that keeps the 1.0 chain verifying unbroken."""
import pytest

from tests.council_util import append, make_cfg, make_repo, make_root
from tools.council import events, schemas
from tools.council.schemas import (compute_event_hash, domain_hash,
                                   payload_hash)

RID = "hash-req-001"


@pytest.fixture()
def env(tmp_path):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    return root, repo, head, make_cfg(repo, root)


def test_domain_hash_is_domain_separated():
    obj = {"a": 1}
    h1 = domain_hash("council:request:v2", obj)
    h2 = domain_hash("council:source-verdict:v2", obj)
    h3 = domain_hash("council:event:v2", obj)
    assert h1 != h2 != h3 and h1 != h3
    # none equals the bare legacy hash of the same object
    assert payload_hash(obj) not in (h1, h2, h3)


def test_domain_hash_formula_pinned():
    import hashlib
    from tools.council.schemas import canonical_json
    obj = {"z": 2, "a": 1}
    want = hashlib.sha256(
        b"council:event:v2\x00" + canonical_json(obj).encode()).hexdigest()
    assert domain_hash("council:event:v2", obj) == want


def test_event_hash_dispatches_on_version():
    body = {"protocol_version": "2.0", "event_id": "x", "payload": {}}
    v2 = compute_event_hash(body)
    body1 = dict(body, protocol_version="1.0")
    v1 = compute_event_hash(body1)
    assert v2 != v1
    assert v2 == domain_hash("council:event:v2",
                             {k: v for k, v in body.items()})
    assert v1 == payload_hash({k: v for k, v in body1.items()})


def test_new_events_are_protocol_2_0(env):
    root, repo, head, cfg = env
    event = append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    assert event["protocol_version"] == "2.0"
    assert compute_event_hash(event) == event["event_hash"]


def test_v1_and_v2_events_chain_across_the_boundary(env):
    """A hand-written 1.0 event followed by real 2.0 appends verifies as
    one chain — the dispatch never recomputes a predecessor under the
    successor's formula."""
    root, repo, head, cfg = env
    from tools.council.schemas import canonical_json, GENESIS_HASH
    from tools.council import storage
    chain = events.read_chain(root)
    prev = chain[-1]["event_hash"] if chain else GENESIS_HASH
    seq = len(chain) + 1
    legacy = {"protocol_version": "1.0",
              "event_id": f"{seq:06d}-legacy00",
              "event_type": "BUILD_STARTED", "request_id": RID,
              "sender": "claude", "timestamp_utc": storage.utc_now(),
              "repository": repo, "target_commit": head, "payload": {},
              "previous_event_hash": prev}
    legacy["event_hash"] = compute_event_hash(legacy)  # 1.0 formula
    storage.append_line(storage.events_path(root), canonical_json(legacy))
    assert events.verify_chain(root).ok
    # a real 2.0 event now chains onto the 1.0 event
    nxt = append(root, cfg, "BUILD_READY", "claude", RID, repo, head)
    assert nxt["protocol_version"] == "2.0"
    assert nxt["previous_event_hash"] == legacy["event_hash"]
    assert events.verify_chain(root).ok


def test_append_refuses_non_current_protocol_version(env):
    """Only the current protocol_version may be appended; 1.0 is
    replay-only."""
    root, repo, head, cfg = env
    from tools.council.schemas import validate_event, SchemaViolation
    ev = {"protocol_version": "1.0", "event_id": "000001-aaaaaaaa",
          "event_type": "BUILD_STARTED", "request_id": RID,
          "sender": "claude", "timestamp_utc": "2026-01-01T00:00:00Z",
          "repository": repo, "target_commit": head, "payload": {},
          "previous_event_hash": "0" * 64}
    ev["event_hash"] = compute_event_hash(ev)
    validate_event(ev, for_append=False)  # replay: fine
    with pytest.raises(SchemaViolation, match="replay only"):
        validate_event(ev, for_append=True)


def test_request_hash_dispatches_on_version():
    from tools.council.schemas import compute_request_payload_hash
    r1 = {"protocol_version": "1.0", "x": 1}
    r2 = {"protocol_version": "2.0", "x": 1}
    assert compute_request_payload_hash(r1) != \
        compute_request_payload_hash(r2)
