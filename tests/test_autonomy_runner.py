"""Runner: the full mock lifecycle end to end against a throwaway council
root + scratch repo, plus every refusal path. Covers the 2026-07-11 audit
blockers: unconditional frozen-config binding (blocker 1 — human path
included, refusal BEFORE the config is parsed or a driver selected) and
complete bounded execution (blocker 2 — all five limits, killable child,
pre-launch cardinality)."""
import argparse
import hashlib
import os
import shutil
import sys
import time

from tests.autonomy_util import (REAL_REPO, policy_doc,
                                 seed_scratch_repo_for_mock, head_of,
                                 task_fields, write_mock_config,
                                 write_roadmap)
from tests.council_util import (append, make_autonomy_block, make_cfg,
                                make_repo, make_request, make_root,
                                make_verdict)
from tools.autonomy import cli as autonomy_cli
from tools.autonomy import roadmap as rm
from tools.autonomy import runner
from tools.autonomy.drivers import RunnerRefusal
from tools.council import codex_watch, events, policy, publish, \
    state_machine, storage

RID = "autonomy-mock-test-001"

FIXTURE_SHA = hashlib.sha256(open(os.path.join(
    REAL_REPO, "tests", "fixtures", "llm", "steward_obedient.json"),
    "rb").read()).hexdigest()

GOOD_OUTCOME = {"run_id": "canned", "run_dir": "logs/runs",
                "final_actions": ["execute"],
                "validations": [{"name": "noop", "ok": True}]}


def _state(root, rid):
    return state_machine.project(events.read_chain(root)).get(
        rid, {}).get("state")


def _event_types(root):
    return [e["event_type"] for e in events.read_chain(root)]


def _drive_to_verdict(tmp_path, config_path, config_sha, roadmap_path,
                      human_gate: bool):
    """BUILD..AUDIT_GO through the REAL publish/claim/verdict paths."""
    root = make_root(tmp_path)
    repo, _initial = make_repo(tmp_path)
    seed_scratch_repo_for_mock(repo)
    head = head_of(repo)
    cfg = make_cfg(repo, root)
    policy.write_initial_policy(root)
    _doc, rm_hash = rm.load_roadmap(roadmap_path, policy.load_policy(root)[0])

    append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    append(root, cfg, "BUILD_READY", "claude", RID, repo, head)
    overrides = {
        "roadmap_hash": rm_hash,
        "experiment_config_file": config_path,  # absolute: joins verbatim
    }
    if human_gate:
        overrides["human_approval_required"] = True
        overrides["experiment_config_hash"] = config_sha
    else:
        overrides["human_approval_required"] = False
        overrides["autonomy"] = make_autonomy_block(
            experiment_config_hash=config_sha,
            model_digests={"mock:steward_obedient": FIXTURE_SHA})
    request = make_request(repo, head, RID, **overrides)
    publish.publish_request(root, cfg, request)
    codex_cfg = make_cfg(repo, root, role="codex")
    codex_watch.claim(root, codex_cfg, RID)
    codex_watch.submit_verdict(
        root, codex_cfg, make_verdict(head, RID, verdict="GO"))
    return root, repo, head, cfg


def _drive_to_auto_approved(tmp_path, config_sha, roadmap_path,
                            config_path=None):
    if config_path is None:
        config_path, config_sha = write_mock_config(tmp_path)
    root, repo, head, cfg = _drive_to_verdict(
        tmp_path, config_path, config_sha, roadmap_path, human_gate=False)
    code = autonomy_cli.cmd_policy_continue(
        cfg, argparse.Namespace(request_id=RID))
    assert code == 0
    assert _state(root, RID) == "auto_approved"
    return root, repo, head, cfg


def _drive_to_human_approved(tmp_path, config_path, config_sha,
                             roadmap_path, **request_overrides):
    root, repo, head, cfg = _drive_to_verdict(
        tmp_path, config_path, config_sha, roadmap_path, human_gate=True)
    append(root, cfg, "HUMAN_APPROVAL_REQUIRED", "claude", RID, repo, head)
    append(root, cfg, "EXPERIMENT_APPROVED", "human", RID, repo, head,
           {"approved_by": "human"})
    assert _state(root, RID) == "approved"
    return root, repo, head, cfg


# ------------------------------------------------------ the happy lifecycle

def test_full_mock_lifecycle_reaches_result_approved(tmp_path):
    config_path, config_sha = write_mock_config(tmp_path)
    roadmap_path = write_roadmap(tmp_path)
    root, repo, head, cfg = _drive_to_auto_approved(
        tmp_path, config_sha, roadmap_path, config_path=config_path)

    code = runner.run_task(cfg, RID, config_path, roadmap_path=roadmap_path)
    assert code == 0
    assert _state(root, RID) == "result_audit"

    chain = events.read_chain(root)
    types = [e["event_type"] for e in chain]
    for expected in ("EXPERIMENT_STARTED", "EXPERIMENT_COMPLETE",
                     "RESULT_VALIDATION_REQUIRED", "RESULT_AUDIT_REQUESTED"):
        assert expected in types
    started = next(e for e in chain
                   if e["event_type"] == "EXPERIMENT_STARTED")
    assert started["payload"]["experiment_config_hash"] == config_sha
    assert started["payload"]["roadmap_hash"]
    # blocker 2: all five effective limits are declared at start
    assert sorted(started["payload"]["limits"]) == [
        "max_compute_minutes", "max_retries_per_unit", "max_scenarios",
        "max_storage_mb", "max_wall_minutes"]
    validated = next(e for e in chain
                     if e["event_type"] == "RESULT_VALIDATION_REQUIRED")
    assert all(v["ok"] for v in validated["payload"]["validations"])
    complete = next(e for e in chain
                    if e["event_type"] == "EXPERIMENT_COMPLETE")
    assert complete["payload"]["final_actions"] == ["execute", "verify",
                                                    "refuse"]
    run_dir = os.path.join(repo, complete["payload"]["run_dir"])
    for name in ("run.json", "decisions.jsonl", "captures.jsonl"):
        assert os.path.exists(os.path.join(run_dir, name))
    assert os.path.exists(storage.safe_request_path(root, "claimed", RID))

    # H3 dual-event evidence pinning: EXPERIMENT_COMPLETE and
    # RESULT_AUDIT_REQUESTED carry IDENTICAL evidence hashes, and the
    # sibling manifest exists + matches the pinned inventory hash
    rar = next(e for e in chain
               if e["event_type"] == "RESULT_AUDIT_REQUESTED")
    for field in ("evidence_inventory_hash", "validation_report_hash"):
        assert complete["payload"][field] == rar["payload"][field]
    manifest_path = os.path.join(repo, complete["payload"]["manifest_file"])
    assert os.path.exists(manifest_path)
    import json
    manifest = json.load(open(manifest_path))
    assert manifest["inventory_hash"] == \
        complete["payload"]["evidence_inventory_hash"]
    # recomputing the inventory over the produced bytes matches the pin
    from tools.autonomy.runner import build_evidence_manifest
    _m, recomputed = build_evidence_manifest(
        repo, rar["payload"]["run_dir"], rar["payload"]["run_id"])
    assert recomputed == complete["payload"]["evidence_inventory_hash"]

    # Codex approves the result (full schema-valid verdict — the append
    # boundary refuses anything less); claude advances.
    codex_cfg = make_cfg(repo, root, role="codex")
    append(root, codex_cfg, "RESULT_APPROVED", "codex", RID, repo, head)
    assert _state(root, RID) == "result_approved"
    append(root, cfg, "NEXT_MILESTONE_READY", "claude", RID, repo, head)
    assert _state(root, RID) == "next_milestone_ready"


def test_human_approved_path_with_binding_runs(tmp_path):
    """Blocker 1 (positive side): the human path DOES run when it carries
    the full frozen binding — same enforcement, no autonomy block needed."""
    config_path, config_sha = write_mock_config(tmp_path)
    roadmap_path = write_roadmap(tmp_path)
    root, repo, head, cfg = _drive_to_human_approved(
        tmp_path, config_path, config_sha, roadmap_path)
    code = runner.run_task(cfg, RID, config_path, roadmap_path=roadmap_path)
    assert code == 0
    assert _state(root, RID) == "result_audit"


# --------------------------------------- blocker 1: unconditional binding

def test_human_approved_without_binding_refused_before_driver(
        tmp_path, monkeypatch):
    """Cycle-1 blocker 1 as a regression: a human-approved request that
    NEVER carried a binding (published that way, so the file matches its
    event pin) must refuse BEFORE any config is parsed or driver selected
    — a post-approval config never runs."""
    config_path, config_sha = write_mock_config(tmp_path)
    roadmap_path = write_roadmap(tmp_path)
    root = make_root(tmp_path)
    repo, _initial = make_repo(tmp_path)
    seed_scratch_repo_for_mock(repo)
    head = head_of(repo)
    cfg = make_cfg(repo, root)
    policy.write_initial_policy(root)
    _doc, rm_hash = rm.load_roadmap(roadmap_path,
                                    policy.load_policy(root)[0])
    append(root, cfg, "BUILD_STARTED", "claude", RID, repo, head)
    append(root, cfg, "BUILD_READY", "claude", RID, repo, head)
    # human gate, roadmap pin, but NO experiment config binding at all
    request = make_request(repo, head, RID, human_approval_required=True,
                           roadmap_hash=rm_hash)
    publish.publish_request(root, cfg, request)
    codex_cfg = make_cfg(repo, root, role="codex")
    codex_watch.claim(root, codex_cfg, RID)
    codex_watch.submit_verdict(root, codex_cfg,
                               make_verdict(head, RID, verdict="GO"))
    append(root, cfg, "HUMAN_APPROVAL_REQUIRED", "claude", RID, repo, head)
    append(root, cfg, "EXPERIMENT_APPROVED", "human", RID, repo, head,
           {"approved_by": "human"})

    created_after = str(tmp_path / "created-after-approval.json")
    shutil.copy(config_path, created_after)
    sentinel = {"called": False}

    def spy(*a, **k):
        sentinel["called"] = True
        return GOOD_OUTCOME

    monkeypatch.setattr(runner, "_run_driver_bounded", spy)
    code = runner.run_task(cfg, RID, created_after,
                           roadmap_path=roadmap_path)
    assert code == 1
    assert sentinel["called"] is False, "unaudited config reached a driver"
    last = events.read_chain(root)[-1]
    assert last["event_type"] == "AUTONOMY_PAUSED"
    assert "no frozen experiment config binding" in last["payload"]["reason"]
    assert "EXPERIMENT_STARTED" not in _event_types(root)


def test_provenance_gate_blocks_weakened_design_config(tmp_path, monkeypatch):
    """Cycle-4 blocker regression: a config that carries a design_hash must
    pass lint_experiment_config ON THE LIVE PATH — a hash-valid but
    design-weakened config is refused BEFORE any driver runs. Proves the
    provenance gate is wired into run_task, not merely unit-tested."""
    from coliseum.textlab import registry as textlab_registry
    config_path, config_sha = write_mock_config(tmp_path, design_hash="0" * 64)
    roadmap_path = write_roadmap(tmp_path)
    root, repo, head, cfg = _drive_to_auto_approved(
        tmp_path, config_sha, roadmap_path, config_path=config_path)

    seen = {"lint": False, "drove": False}

    def lint_spy(cp, rp, rr):
        seen["lint"] = True
        return ["config interaction 'independent_vignettes' != frozen "
                "'sequential_history'"]

    def drive_spy(*a, **k):
        seen["drove"] = True
        return GOOD_OUTCOME

    monkeypatch.setattr(textlab_registry, "lint_experiment_config", lint_spy)
    monkeypatch.setattr(runner, "_run_driver_bounded", drive_spy)
    code = runner.run_task(cfg, RID, config_path, roadmap_path=roadmap_path)
    assert code == 1
    assert seen["lint"] is True, "provenance gate was not on the live path"
    assert seen["drove"] is False, "weakened design config reached the driver"
    last = events.read_chain(root)[-1]
    assert last["event_type"] == "AUTONOMY_PAUSED"
    assert "frozen-design provenance gate" in last["payload"]["reason"]
    assert "EXPERIMENT_STARTED" not in _event_types(root)


def test_provenance_gate_skipped_without_design_hash(tmp_path, monkeypatch):
    """A config with NO design_hash (the mock pipeline probe) carries no
    pre-registration to bind, so the gate is correctly skipped and the run
    proceeds — the gate keys on design_hash, never on driver alone."""
    from coliseum.textlab import registry as textlab_registry
    config_path, config_sha = write_mock_config(tmp_path)   # no design_hash
    roadmap_path = write_roadmap(tmp_path)
    root, repo, head, cfg = _drive_to_auto_approved(
        tmp_path, config_sha, roadmap_path, config_path=config_path)

    called = {"lint": False}

    def lint_spy(*a, **k):
        called["lint"] = True
        return ["should never be consulted"]

    monkeypatch.setattr(textlab_registry, "lint_experiment_config", lint_spy)
    code = runner.run_task(cfg, RID, config_path, roadmap_path=roadmap_path)
    assert code == 0
    assert called["lint"] is False, "gate ran for a config with no design_hash"
    assert "EXPERIMENT_STARTED" in _event_types(root)


# ------------------------------- cycle-2 blocker: request root of trust

def _tamper_completed_request(root, new_config_path, new_sha,
                              rehash: bool):
    """Post-approval edit of the mutable request file: point the binding
    at a different config. rehash=False leaves request_payload_hash stale;
    rehash=True recomputes it so the file is self-consistent — both must
    be refused against the event-pinned hash."""
    import json as _json
    from tools.council.schemas import compute_request_payload_hash
    path = storage.safe_request_path(root, "complete", RID)
    request = _json.load(open(path, encoding="utf-8"))
    request["experiment_config_file"] = new_config_path
    if "autonomy" in request:
        request["autonomy"]["experiment_config_hash"] = new_sha
    request["experiment_config_hash"] = new_sha
    if rehash:
        request["request_payload_hash"] = \
            compute_request_payload_hash(request)
    with open(path, "w", encoding="utf-8") as fh:
        _json.dump(request, fh)


def test_post_approval_request_tamper_stale_hash_refused(tmp_path,
                                                         monkeypatch):
    """The cycle-2 Codex probe as a regression: after AUTO_APPROVED, edit
    experiment_config_file + experiment_config_hash in the completed
    request file (stale request_payload_hash) — run_task must refuse
    before EXPERIMENT_STARTED and before any driver."""
    config_path, config_sha = write_mock_config(tmp_path)
    roadmap_path = write_roadmap(tmp_path)
    root, repo, head, cfg = _drive_to_auto_approved(
        tmp_path, config_sha, roadmap_path, config_path=config_path)
    evil_path, evil_sha = write_mock_config(tmp_path / "evil",
                                            scenario_seed=1)
    _tamper_completed_request(root, evil_path, evil_sha, rehash=False)
    sentinel = {"called": False}
    monkeypatch.setattr(runner, "_run_driver_bounded",
                        lambda *a, **k: sentinel.update(called=True)
                        or GOOD_OUTCOME)
    code = runner.run_task(cfg, RID, evil_path, roadmap_path=roadmap_path)
    assert code == 1
    assert sentinel["called"] is False
    assert "EXPERIMENT_STARTED" not in _event_types(root)
    last = events.read_chain(root)[-1]
    assert last["event_type"] == "AUTONOMY_PAUSED"
    assert "pinned" in last["payload"]["reason"] or \
        "no longer validates" in last["payload"]["reason"]


def test_post_approval_request_tamper_rehash_refused(tmp_path, monkeypatch):
    """Codex's second required probe: a SELF-CONSISTENT recomputed
    request_payload_hash still differs from the event-pinned hash and must
    be refused all the same."""
    config_path, config_sha = write_mock_config(tmp_path)
    roadmap_path = write_roadmap(tmp_path)
    root, repo, head, cfg = _drive_to_auto_approved(
        tmp_path, config_sha, roadmap_path, config_path=config_path)
    evil_path, evil_sha = write_mock_config(tmp_path / "evil",
                                            scenario_seed=1)
    _tamper_completed_request(root, evil_path, evil_sha, rehash=True)
    sentinel = {"called": False}
    monkeypatch.setattr(runner, "_run_driver_bounded",
                        lambda *a, **k: sentinel.update(called=True)
                        or GOOD_OUTCOME)
    code = runner.run_task(cfg, RID, evil_path, roadmap_path=roadmap_path)
    assert code == 1
    assert sentinel["called"] is False
    assert "EXPERIMENT_STARTED" not in _event_types(root)
    last = events.read_chain(root)[-1]
    assert "pinned" in last["payload"]["reason"]


def test_policy_continue_refuses_tampered_request(tmp_path):
    """The same root of trust guards policy evaluation: policy-continue on
    a tampered request file pauses instead of evaluating."""
    config_path, config_sha = write_mock_config(tmp_path)
    roadmap_path = write_roadmap(tmp_path)
    root, repo, head, cfg = _drive_to_verdict(
        tmp_path, config_path, config_sha, roadmap_path, human_gate=False)
    evil_path, evil_sha = write_mock_config(tmp_path / "evil",
                                            scenario_seed=1)
    _tamper_completed_request(root, evil_path, evil_sha, rehash=True)
    code = autonomy_cli.cmd_policy_continue(
        cfg, argparse.Namespace(request_id=RID))
    assert code == 1
    assert _state(root, RID) == "autonomy_paused"
    assert "AUTO_APPROVED" not in _event_types(root)


def test_config_path_must_be_the_audited_file(tmp_path, monkeypatch):
    """Same bytes at a different path are refused: the binding is canonical
    (hash AND file), so a copied config cannot substitute for the audited
    one."""
    config_path, config_sha = write_mock_config(tmp_path)
    roadmap_path = write_roadmap(tmp_path)
    root, repo, head, cfg = _drive_to_auto_approved(
        tmp_path, config_sha, roadmap_path, config_path=config_path)
    elsewhere = str(tmp_path / "copy-of-config.json")
    shutil.copy(config_path, elsewhere)
    sentinel = {"called": False}
    monkeypatch.setattr(runner, "_run_driver_bounded",
                        lambda *a, **k: sentinel.update(called=True)
                        or GOOD_OUTCOME)
    code = runner.run_task(cfg, RID, elsewhere, roadmap_path=roadmap_path)
    assert code == 1
    assert sentinel["called"] is False
    last = events.read_chain(root)[-1]
    assert "not the audited config file" in last["payload"]["reason"]


def test_tampered_config_refused_and_pauses(tmp_path):
    config_path, config_sha = write_mock_config(tmp_path)
    roadmap_path = write_roadmap(tmp_path)
    root, repo, head, cfg = _drive_to_auto_approved(
        tmp_path, config_sha, roadmap_path, config_path=config_path)
    with open(config_path, "a", encoding="utf-8") as fh:
        fh.write("\n")
    code = runner.run_task(cfg, RID, config_path, roadmap_path=roadmap_path)
    assert code == 1
    assert _state(root, RID) == "autonomy_paused"
    last = events.read_chain(root)[-1]
    assert "does not match" in last["payload"]["reason"]


# ------------------------------------------- blocker 2: bounded execution

def test_limits_include_all_five_and_compose_strictest():
    pol = policy_doc()
    task = task_fields(maximum_runtime_minutes=15,
                       maximum_storage_growth_mb=1024)
    request = {"autonomy": {"limits": {
        "max_compute_minutes": 10, "max_wall_minutes": 60,
        "max_storage_mb": 512, "max_retries_per_unit": 1,
        "max_scenarios": 3}}}
    limits = runner._limits(request, task, pol)
    assert limits == {"max_wall_minutes": 15,      # task stricter than block
                      "max_storage_mb": 512,       # block stricter than task
                      "max_compute_minutes": 10,   # block stricter than cap
                      "max_retries_per_unit": 1,
                      "max_scenarios": 3}
    # human path: no block -> policy caps bound compute/retries/scenarios
    limits = runner._limits({}, task, pol)
    assert limits["max_compute_minutes"] == 240
    assert limits["max_retries_per_unit"] == 2
    assert limits["max_scenarios"] == 60


def test_execute_bounded_kills_hung_child(tmp_path):
    started = time.monotonic()
    try:
        runner._execute_bounded(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            deadline_seconds=1.0, storage_root=str(tmp_path),
            storage_cap_mb=1024, size_before_mb=0.0, cwd=str(tmp_path))
        raise AssertionError("hung child was not killed")
    except RunnerRefusal as exc:
        assert "deadline" in str(exc) and "killed" in str(exc)
    assert time.monotonic() - started < 15, \
        "kill did not happen within the cap window"


def test_execute_bounded_kills_storage_overrun(tmp_path):
    out = tmp_path / "growth"
    out.mkdir()
    script = (f"import os, time; "
              f"open(os.path.join({str(out)!r}, 'fat.bin'), 'wb')"
              f".write(b'\\0' * (3 * 1024 * 1024)); time.sleep(60)")
    started = time.monotonic()
    try:
        runner._execute_bounded(
            [sys.executable, "-c", script],
            deadline_seconds=30.0, storage_root=str(out),
            storage_cap_mb=1, size_before_mb=0.0, cwd=str(tmp_path))
        raise AssertionError("storage-overrunning child was not killed")
    except RunnerRefusal as exc:
        assert "storage growth" in str(exc) and "killed" in str(exc)
    assert time.monotonic() - started < 15


# --------- launcher audit blocker 2: the bound covers the WHOLE process tree

def _grandchild_spawner(marker: str, occupy: str = "time.sleep(60)") -> str:
    """A child that spawns a detached-feeling grandchild which would write
    a marker after 2.5s, then occupies itself — if the group kill misses
    the grandchild, the marker appears after _execute_bounded returns."""
    return (
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c',\n"
        f"    \"import time; time.sleep(2.5); open({marker!r}, 'w')"
        ".write('leaked')\"])\n"
        f"{occupy}\n")


def test_timeout_kills_entire_process_group(tmp_path):
    marker = str(tmp_path / "leaked-by-timeout.marker")
    try:
        runner._execute_bounded(
            [sys.executable, "-c", _grandchild_spawner(marker)],
            deadline_seconds=1.0, storage_root=str(tmp_path),
            storage_cap_mb=1024, size_before_mb=0.0, cwd=str(tmp_path))
        raise AssertionError("hung child was not killed")
    except RunnerRefusal as exc:
        assert "process group killed" in str(exc)
    time.sleep(3.0)  # past the grandchild's write time
    assert not os.path.exists(marker), \
        "a descendant outlived the declared hard bound"


def test_storage_overrun_kills_entire_process_group(tmp_path):
    out = tmp_path / "growth"
    out.mkdir()
    marker = str(tmp_path / "leaked-by-storage.marker")
    occupy = (f"open(os.path.join({str(out)!r}, 'fat.bin'), 'wb')"
              f".write(b'\\0' * (3 * 1024 * 1024)); time.sleep(60)")
    body = "import os\n" + _grandchild_spawner(marker, occupy=occupy)
    try:
        runner._execute_bounded(
            [sys.executable, "-c", body],
            deadline_seconds=30.0, storage_root=str(out),
            storage_cap_mb=1, size_before_mb=0.0, cwd=str(tmp_path))
        raise AssertionError("storage-overrunning child was not killed")
    except RunnerRefusal as exc:
        assert "process group killed" in str(exc)
    time.sleep(3.0)
    assert not os.path.exists(marker), \
        "a descendant outlived the storage kill"


def test_scenario_cardinality_over_limit_refused_before_start(tmp_path,
                                                              monkeypatch):
    config_path, config_sha = write_mock_config(tmp_path, scenario_count=20)
    roadmap_path = write_roadmap(tmp_path)
    root, repo, head, cfg = _drive_to_auto_approved(
        tmp_path, config_sha, roadmap_path, config_path=config_path)
    sentinel = {"called": False}
    monkeypatch.setattr(runner, "_run_driver_bounded",
                        lambda *a, **k: sentinel.update(called=True)
                        or GOOD_OUTCOME)
    code = runner.run_task(cfg, RID, config_path, roadmap_path=roadmap_path)
    assert code == 1
    assert sentinel["called"] is False
    assert "EXPERIMENT_STARTED" not in _event_types(root)
    last = events.read_chain(root)[-1]
    assert "scenario_count" in last["payload"]["reason"]


def test_retry_cardinality_over_limit_refused_before_start(tmp_path,
                                                           monkeypatch):
    config_path, config_sha = write_mock_config(tmp_path, retries_per_unit=3)
    roadmap_path = write_roadmap(tmp_path)
    root, repo, head, cfg = _drive_to_auto_approved(
        tmp_path, config_sha, roadmap_path, config_path=config_path)
    sentinel = {"called": False}
    monkeypatch.setattr(runner, "_run_driver_bounded",
                        lambda *a, **k: sentinel.update(called=True)
                        or GOOD_OUTCOME)
    code = runner.run_task(cfg, RID, config_path, roadmap_path=roadmap_path)
    assert code == 1
    assert sentinel["called"] is False
    assert "EXPERIMENT_STARTED" not in _event_types(root)
    last = events.read_chain(root)[-1]
    assert "retries_per_unit" in last["payload"]["reason"]


def test_killed_child_pauses_with_the_kill_reason(tmp_path, monkeypatch):
    config_path, config_sha = write_mock_config(tmp_path)
    roadmap_path = write_roadmap(tmp_path)
    root, repo, head, cfg = _drive_to_auto_approved(
        tmp_path, config_sha, roadmap_path, config_path=config_path)

    def killed(*a, **k):
        raise RunnerRefusal("wall/compute deadline 900s exceeded — "
                            "child killed")

    monkeypatch.setattr(runner, "_run_driver_bounded", killed)
    code = runner.run_task(cfg, RID, config_path, roadmap_path=roadmap_path)
    assert code == 1
    last = events.read_chain(root)[-1]
    assert last["event_type"] == "AUTONOMY_PAUSED"
    assert "child killed" in last["payload"]["reason"]


def test_post_run_storage_check_still_enforced(tmp_path, monkeypatch):
    config_path, config_sha = write_mock_config(tmp_path)
    roadmap_path = write_roadmap(
        tmp_path, [task_fields(maximum_storage_growth_mb=1)])
    root, repo, head, cfg = _drive_to_auto_approved(
        tmp_path, config_sha, roadmap_path, config_path=config_path)

    def sneaky(repo_path, cfg_path, driver, limits, measure_root, before):
        os.makedirs(measure_root, exist_ok=True)
        with open(os.path.join(measure_root, "fat.bin"), "wb") as fh:
            fh.write(b"\0" * (2 * 1024 * 1024))
        return GOOD_OUTCOME

    monkeypatch.setattr(runner, "_run_driver_bounded", sneaky)
    code = runner.run_task(cfg, RID, config_path, roadmap_path=roadmap_path)
    assert code == 1
    last = events.read_chain(root)[-1]
    assert "storage growth" in last["payload"]["reason"]


def test_failed_validation_pauses_before_result_audit(tmp_path, monkeypatch):
    config_path, config_sha = write_mock_config(tmp_path)
    roadmap_path = write_roadmap(tmp_path)
    root, repo, head, cfg = _drive_to_auto_approved(
        tmp_path, config_sha, roadmap_path, config_path=config_path)
    bad = dict(GOOD_OUTCOME)
    bad["validations"] = [{"name": "offline_replay_byte_identical",
                           "ok": False}]
    monkeypatch.setattr(runner, "_run_driver_bounded",
                        lambda *a, **k: bad)
    code = runner.run_task(cfg, RID, config_path, roadmap_path=roadmap_path)
    assert code == 1
    types = _event_types(root)
    assert "RESULT_VALIDATION_REQUIRED" in types
    assert "RESULT_AUDIT_REQUESTED" not in types
    assert types[-1] == "AUTONOMY_PAUSED"


# ------------------------------------------------------- other refusals

def test_wrong_state_refused(tmp_path):
    config_path, config_sha = write_mock_config(tmp_path)
    roadmap_path = write_roadmap(tmp_path)
    root, repo, head, cfg = _drive_to_verdict(
        tmp_path, config_path, config_sha, roadmap_path, human_gate=False)
    # state is `go` — not runnable
    code = runner.run_task(cfg, RID, config_path, roadmap_path=roadmap_path)
    assert code == 1
    assert _state(root, RID) == "autonomy_paused"


def test_human_gated_task_never_runs(tmp_path):
    config_path, config_sha = write_mock_config(tmp_path)
    roadmap_path = write_roadmap(
        tmp_path, [task_fields(requires_human=True)])
    root, repo, head, cfg = _drive_to_auto_approved(
        tmp_path, config_sha, roadmap_path, config_path=config_path)
    code = runner.run_task(cfg, RID, config_path, roadmap_path=roadmap_path)
    assert code == 1
    last = events.read_chain(root)[-1]
    assert last["event_type"] == "AUTONOMY_PAUSED"
    assert "requires_human" in last["payload"]["reason"]


def test_roadmap_pin_drift_refused(tmp_path):
    config_path, config_sha = write_mock_config(tmp_path)
    roadmap_path = write_roadmap(tmp_path)
    root, repo, head, cfg = _drive_to_auto_approved(
        tmp_path, config_sha, roadmap_path, config_path=config_path)
    with open(roadmap_path, "a", encoding="utf-8") as fh:
        fh.write("# drift after the pin\n")
    code = runner.run_task(cfg, RID, config_path, roadmap_path=roadmap_path)
    assert code == 1
    last = events.read_chain(root)[-1]
    assert last["event_type"] == "AUTONOMY_PAUSED"
    assert "pinned" in last["payload"]["reason"]
