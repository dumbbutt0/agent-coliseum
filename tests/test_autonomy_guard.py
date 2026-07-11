"""Guard preflight: every condition trips, failures collect, pause records."""
import os

from tests.autonomy_util import write_roadmap
from tests.council_util import append, make_cfg, make_repo, make_root
from tools.autonomy import guard
from tools.council import events, policy, storage


def _setup(tmp_path):
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    policy.write_initial_policy(root)
    roadmap_path = write_roadmap(tmp_path)
    return root, repo, head, cfg, roadmap_path


def test_clean_preflight_passes(tmp_path):
    root, repo, head, cfg, rm_path = _setup(tmp_path)
    report = guard.preflight(cfg, repo=repo, expect_head=head,
                             roadmap_path=rm_path)
    assert report.ok, report.failures
    assert report.policy_hash and report.roadmap_hash


def test_stop_file_trips_and_pause_records(tmp_path):
    root, repo, head, cfg, rm_path = _setup(tmp_path)
    with open(storage.stop_file_path(root), "w", encoding="utf-8") as fh:
        fh.write("owner stop\n")
    report = guard.preflight(cfg, repo=repo, roadmap_path=rm_path)
    assert not report.ok
    assert any("emergency_stop" in f for f in report.failures)
    # AUTONOMY_PAUSED is allowed even while the stop is engaged
    guard.pause(cfg, "guard-test-req", repo, head, report.failures)
    chain = events.read_chain(root)
    assert chain[-1]["event_type"] == "AUTONOMY_PAUSED"
    assert "emergency_stop" in chain[-1]["payload"]["reason"]


def test_status_paused_trips(tmp_path):
    root, repo, head, cfg, rm_path = _setup(tmp_path)
    storage.write_control(root, "paused", ["all"], "owner pause", None)
    report = guard.preflight(cfg, roadmap_path=rm_path)
    assert not report.ok and any("emergency_stop" in f
                                 for f in report.failures)


def test_log_md_status_edit_is_cosmetic(tmp_path):
    """H1: forging the log.md STATUS line changes nothing — control.json
    is the only authority, and deleting IT fails closed."""
    root, repo, head, cfg, rm_path = _setup(tmp_path)
    log = os.path.join(root, "log.md")
    body = open(log, encoding="utf-8").read().split("\n", 1)[1]
    with open(log, "w", encoding="utf-8") as fh:
        fh.write("STATUS: paused all\n" + body)
    report = guard.preflight(cfg, roadmap_path=rm_path)
    assert report.ok  # the mirror has no authority
    os.unlink(storage.control_path(root))
    report = guard.preflight(cfg, roadmap_path=rm_path)
    assert not report.ok and any("fail closed" in f for f in report.failures)


def test_dirty_tree_and_wrong_head_trip(tmp_path):
    root, repo, head, cfg, rm_path = _setup(tmp_path)
    with open(os.path.join(repo, "f.txt"), "a", encoding="utf-8") as fh:
        fh.write("dirty\n")
    report = guard.preflight(cfg, repo=repo, expect_head="f" * 40,
                             roadmap_path=rm_path)
    assert not report.ok
    assert any("dirty" in f for f in report.failures)
    assert any("not the bound commit" in f for f in report.failures)


def test_policy_drift_trips(tmp_path):
    root, repo, head, cfg, rm_path = _setup(tmp_path)
    # pin the current policy hash into the chain, then tamper the file
    _pol, pol_hash = policy.load_policy(root)
    append(root, cfg, "BUILD_STARTED", "claude", "guard-drift-req", repo,
           head, {"policy_hash": pol_hash})
    path = storage.policy_path(root)
    os.chmod(path, 0o644)
    with open(path, encoding="utf-8") as fh:
        body = fh.read()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body.replace("2048", "999999"))
    report = guard.preflight(cfg, roadmap_path=rm_path)
    assert not report.ok
    assert any("policy" in f and "pinned" in f for f in report.failures)


def test_roadmap_pin_drift_trips(tmp_path):
    root, repo, head, cfg, rm_path = _setup(tmp_path)
    report = guard.preflight(cfg, roadmap_path=rm_path,
                             pinned_roadmap_hash="0" * 64)
    assert not report.ok
    assert any("roadmap" in f and "pinned" in f for f in report.failures)


def test_paused_flag_trips(tmp_path):
    root, repo, head, cfg, rm_path = _setup(tmp_path)
    append(root, cfg, "AUTONOMY_PAUSED", "claude", "guard-flag-req", repo,
           head, {"reason": "test"})
    report = guard.preflight(cfg, roadmap_path=rm_path)
    assert not report.ok
    assert any("autonomy_paused" in f for f in report.failures)
