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
              "event_id": f"{seq:06d}-deadbeef",
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


# -------------------------- cycle-2 blockers (H2 audit)

def test_unsupported_version_event_fails_verify_chain(env):
    """Cycle-2 blocker 3: a 3.0 event with a valid BARE hash must NOT
    verify — the legacy formula no longer covers unsupported versions."""
    root, repo, head, cfg = env
    from tools.council.schemas import (canonical_json, compute_event_hash,
                                       payload_hash, ChainError)
    from tools.council import storage
    append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    chain = events.read_chain(root)
    seq = len(chain) + 1
    ev = {"protocol_version": "3.0", "event_id": f"{seq:06d}-deadbeef",
          "event_type": "BUILD_READY", "request_id": RID, "sender": "claude",
          "timestamp_utc": storage.utc_now(), "repository": repo,
          "target_commit": head, "payload": {},
          "previous_event_hash": chain[-1]["event_hash"]}
    ev["event_hash"] = payload_hash(  # attacker uses the bare formula
        {k: v for k, v in ev.items() if k != "event_hash"})
    storage.append_line(storage.events_path(root), canonical_json(ev))
    report = events.verify_chain(root)
    assert not report.ok and "unsupported" in report.error
    with pytest.raises(ChainError):
        events.read_chain(root)  # verify=True fails closed
    with pytest.raises(ChainError):
        compute_event_hash(ev)


@pytest.mark.parametrize("falsy", ["", None, False, 0])
def test_explicit_falsy_version_fails_closed(env, falsy):
    """Cycle-3 blocker: an explicit empty/null/false/0 protocol_version
    must NOT coerce to legacy 1.0 — it is a present, unsupported value and
    fails verify_chain/read_chain closed."""
    root, repo, head, cfg = env
    from tools.council.schemas import (canonical_json, payload_hash,
                                       ChainError)
    from tools.council import storage
    append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    chain = events.read_chain(root)
    seq = len(chain) + 1
    ev = {"protocol_version": falsy, "event_id": f"{seq:06d}-deadbee0",
          "event_type": "BUILD_READY", "request_id": RID, "sender": "claude",
          "timestamp_utc": storage.utc_now(), "repository": repo,
          "target_commit": head, "payload": {},
          "previous_event_hash": chain[-1]["event_hash"]}
    ev["event_hash"] = payload_hash(  # legacy bare hash, as the probe did
        {k: v for k, v in ev.items() if k != "event_hash"})
    storage.append_line(storage.events_path(root), canonical_json(ev))
    assert not events.verify_chain(root).ok
    with pytest.raises(ChainError):
        events.read_chain(root)


def test_v2_verdict_domain_is_unambiguous():
    """Cycle-2 blocker 1: a known schema_version drives the v2 domain; an
    unknown one raises; absent = legacy bare hash (no silent fallback)."""
    from tools.council.schemas import (compute_verdict_payload_hash,
                                       domain_hash, payload_hash,
                                       SOURCE_VERDICT_DOMAIN_V2,
                                       SchemaViolation)
    from tests.council_util import make_verdict
    v = make_verdict("a" * 40, verdict="GO",
                     schema_version="source-verdict.v2")
    body = {k: val for k, val in v.items() if k != "verdict_payload_hash"}
    assert compute_verdict_payload_hash(v) == \
        domain_hash(SOURCE_VERDICT_DOMAIN_V2, body)
    assert compute_verdict_payload_hash(v) != payload_hash(body)
    v["schema_version"] = "made-up.v9"
    with pytest.raises(SchemaViolation):
        compute_verdict_payload_hash(v)
    del v["schema_version"]  # legacy
    body2 = {k: val for k, val in v.items() if k != "verdict_payload_hash"}
    assert compute_verdict_payload_hash(v) == payload_hash(body2)


def test_v2_verdict_schema_version_must_match_kind():
    from tools.council.schemas import (validate_verdict,
                                       compute_verdict_payload_hash,
                                       SchemaViolation)
    from tests.council_util import make_verdict
    # source audit carrying the RESULT schema_version is refused
    v = make_verdict("a" * 40, verdict="GO",
                     schema_version="result-verdict.v2")
    v["verdict_payload_hash"] = compute_verdict_payload_hash(v)
    with pytest.raises(SchemaViolation):
        validate_verdict(v, result_audit=False)


@pytest.mark.parametrize("bad", ["2026-99-99T99:99:99Z",
                                 "2026-02-30T00:00:00Z",
                                 "2026-01-01T25:00:00Z",
                                 "2026-00-01T00:00:00Z"])
def test_impossible_calendar_timestamps_refused(bad):
    """Cycle-2 blocker 2: grammar-valid but calendar-impossible timestamps
    are refused by real datetime parsing."""
    from tools.council.schemas import (validate_verdict,
                                       compute_verdict_payload_hash,
                                       SchemaViolation)
    from tests.council_util import make_verdict
    v = make_verdict("a" * 40)
    v["timestamp_utc"] = bad
    v["verdict_payload_hash"] = compute_verdict_payload_hash(v)
    with pytest.raises(SchemaViolation):
        validate_verdict(v)


def test_request_hash_dispatches_on_version():
    from tools.council.schemas import compute_request_payload_hash
    r1 = {"protocol_version": "1.0", "x": 1}
    r2 = {"protocol_version": "2.0", "x": 1}
    assert compute_request_payload_hash(r1) != \
        compute_request_payload_hash(r2)
