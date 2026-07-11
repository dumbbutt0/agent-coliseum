"""H7 activation staging harness (hardening directive item 15).

Runs the ordered activation gates against DISPOSABLE staging state and
records one JSON artifact per gate under docs/hardening/activation/. The
LIVE council is never written: gate 3 COPIES its event chain into the
scratch dir for realism drills, and every mutating drill runs either on
that copy or on a freshly bootstrapped staging council whose identity
(passphrase, enrollment anchor) is generated under the scratch dir and
valid nowhere else.

Gates:
  1 suite       full test suite at the isolated commit
  2 e2e         fake-Codex end-to-end on a fresh staging council through the
                REAL codex_launcher/codex_watch: a source round (GO) and a
                result-audit round with a REAL evidence manifest produced by
                the real runner (mock driver, auto-approved policy path — no
                human token anywhere)
  3 drills      torn-tail detection + append refusal on a COPY of the live
                chain; STOP-mid-claim rollback; kill-between-journal-steps
                recovery (both directions)
  4 noservice   documented no-service check (no coliseum systemd unit or
                cron entry active anywhere)
  5 install     install-WITHOUT-enable status + exact owner commands
  6/7 runbooks  owner-attended steps (foreground --once review; enable)

Usage:
    PYTHONPATH=. python3 scripts/council_staging.py [--gates 1,2,...]
        [--out docs/hardening/activation] [--scratch <dir>]

The harness imports the suite's tested builders (tests/council_util.py,
tests/autonomy_util.py — plain helper modules, not test files) rather than
duplicating them; the staging identity they bootstrap is the TEST identity,
which the live enrollment anchor refuses, so nothing built here can ever
mint live authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import time

REAL_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REAL_REPO)

LIVE_DEFAULT = "/mnt/c/Users/dumbb/Docs/TheBrain/Claude-Wiki/council"
UNIT_NAME = "coliseum-codex-launcher.service"
UNIT_SRC = os.path.join(REAL_REPO, "tools", "systemd", UNIT_NAME)


# ------------------------------------------------------------------ helpers

def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _head() -> str:
    return subprocess.run(["git", "-C", REAL_REPO, "rev-parse", "HEAD"],
                          capture_output=True, text=True,
                          check=True).stdout.strip()


def _artifact(out_dir: str, gate: str, body: dict) -> None:
    body = dict(body)
    body["gate"] = gate
    body["commit"] = _head()
    body["generated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{gate}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(body, fh, indent=2, sort_keys=True)
        fh.write("\n")
    status = "PASS" if body.get("ok") else ("OWNER" if body.get(
        "owner_attended") else "FAIL")
    print(f"[{status}] {gate} -> {path}")


def _guard_scratch(scratch: str, live_root: str) -> None:
    """Refuse to run if the scratch dir could alias the live council."""
    s = os.path.realpath(scratch)
    live = os.path.realpath(live_root)
    if s == live or s.startswith(live + os.sep) or live.startswith(s + os.sep):
        raise SystemExit("refusing: scratch dir overlaps the live council")


# ------------------------------------------------------------------- gate 1

def gate1_suite(out_dir: str, scratch: str, live_root: str) -> bool:
    log = os.path.join(scratch, "gate1-pytest.log")
    with open(log, "w") as fh:
        rc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-q"],
            cwd=REAL_REPO, stdout=fh, stderr=subprocess.STDOUT).returncode
    tail = open(log).read().strip().splitlines()[-1:]
    ok = rc == 0
    _artifact(out_dir, "gate1-suite", {
        "ok": ok, "returncode": rc, "summary": tail,
        "command": "python3 -m pytest tests/ -q"})
    return ok


# ------------------------------------------------------------------- gate 2

_FAKE_PRELUDE = """#!/usr/bin/env python3
import json, os, sys
sys.path.insert(0, {repo!r})
from tools.council import codex_watch, get_config, publish, storage
cfg = get_config(role="codex")
root = cfg.council_root
def verdict_for(rid, commit, kind):
    return {{"request_id": rid, "audited_commit": commit,
            "audit_mode": "narrow", "working_tree_clean": True,
            "tests_observed": 147, "verdict": kind,
            "summary": "staging fake-codex canned verdict",
            "blockers": [], "conditions": [], "findings": [],
            "commands_run": ["python3 -m pytest tests/ -q"],
            "timestamp_utc": storage.utc_now(),
            "replay_result": "replayed_ok",
            "counts": {{"scenarios_run": 1, "validations_passed": 1,
                       "validations_failed": 0}},
            "conclusion_scope": "staging evidence"}}
"""

_FAKE_GO = _FAKE_PRELUDE + """
rid = codex_watch.list_ready(root)[0]
codex_watch.claim(root, cfg, rid)
req = publish.read_request(root, rid)
codex_watch.submit_verdict(root, cfg,
                           verdict_for(rid, req["target_commit"], "GO"))
"""

_FAKE_RESULT = _FAKE_PRELUDE + """
claimed = os.path.join(root, "requests", "claimed")
rid = [f[:-5] for f in os.listdir(claimed) if f.endswith(".json")][0]
req = json.load(open(os.path.join(claimed, rid + ".json")))
codex_watch.submit_verdict(
    root, cfg, verdict_for(rid, req["target_commit"], "APPROVED"),
    result_audit=True)
"""


def _install_fake(scratch: str, body: str, name: str) -> str:
    path = os.path.join(scratch, "bin", name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body.format(repo=REAL_REPO))
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path


def gate2_e2e(out_dir: str, scratch: str, live_root: str) -> bool:
    import argparse as ap

    from tests.autonomy_util import (head_of, seed_scratch_repo_for_mock,
                                     write_mock_config, write_roadmap)
    from tests.council_util import (append, make_autonomy_block, make_cfg,
                                    make_repo, make_request, make_root,
                                    make_verdict, TEST_ENROLLMENT_TOKEN)
    from tools.autonomy import cli as autonomy_cli
    from tools.autonomy import codex_launcher, runner
    from tools.council import events, identity, policy, publish, \
        state_machine

    base = pathlib.Path(scratch) / "e2e"
    base.mkdir(parents=True, exist_ok=True)
    # STAGING-ONLY identity anchor: valid only under the scratch dir; the
    # live root-owned anchor refuses the test enrollment token, so nothing
    # bootstrapped here can mint live authority.
    anchor = base / "staging-enrollment.sha256"
    anchor.write_text(identity.enrollment_hash(TEST_ENROLLMENT_TOKEN))
    saved_anchor = identity.ENROLLMENT_HASH_FILE
    saved_env = {k: os.environ.get(k) for k in
                 ("COUNCIL_ROOT", "COUNCIL_REPO_ROOTS")}
    saved_bin = codex_launcher.CODEX_BIN
    checks = {}
    try:
        identity.ENROLLMENT_HASH_FILE = str(anchor)
        root = make_root(base)
        repo, _initial = make_repo(base)
        seed_scratch_repo_for_mock(repo)
        head = head_of(repo)
        cfg = make_cfg(repo, root)
        policy.write_initial_policy(root)
        os.environ["COUNCIL_ROOT"] = root
        os.environ["COUNCIL_REPO_ROOTS"] = repo

        def state(rid):
            return state_machine.project(events.read_chain(root)).get(
                rid, {}).get("state")

        # -------- source round: publish -> REAL launcher + fake codex -> GO
        rid_src = "staging-source-001"
        append(root, cfg, "BUILD_STARTED", "claude", rid_src, repo, head)
        append(root, cfg, "BUILD_READY", "claude", rid_src, repo, head)
        publish.publish_request(root, cfg, make_request(repo, head, rid_src))
        codex_launcher.CODEX_BIN = _install_fake(scratch, _FAKE_GO, "codex-go")
        rc = codex_launcher.main(["--once"])
        checks["source_launcher_rc"] = rc
        checks["source_state"] = state(rid_src)
        src_ok = rc == 0 and state(rid_src) == "go"

        # -------- result round: auto-approved mock experiment -> REAL
        # runner (real manifest) -> REAL launcher + fake codex -> APPROVED
        rid_res = "staging-result-001"
        config_path, config_sha = write_mock_config(base)
        roadmap_path = write_roadmap(base)
        _doc, rm_hash = rm_load(roadmap_path, root)
        fixture_sha = _sha256(os.path.join(
            REAL_REPO, "tests", "fixtures", "llm", "steward_obedient.json"))
        append(root, cfg, "BUILD_STARTED", "claude", rid_res, repo, head)
        append(root, cfg, "BUILD_READY", "claude", rid_res, repo, head)
        request = make_request(
            repo, head, rid_res, roadmap_hash=rm_hash,
            experiment_config_file=config_path,
            human_approval_required=False,
            autonomy=make_autonomy_block(
                experiment_config_hash=config_sha,
                model_digests={"mock:steward_obedient": fixture_sha}))
        publish.publish_request(root, cfg, request)
        codex_launcher.CODEX_BIN = _install_fake(scratch, _FAKE_GO,
                                                 "codex-go2")
        rc = codex_launcher.main(["--once"])
        checks["result_go_rc"] = rc
        code = autonomy_cli.cmd_policy_continue(
            cfg, ap.Namespace(request_id=rid_res))
        checks["policy_continue_rc"] = code
        checks["after_policy_state"] = state(rid_res)
        code = runner.run_task(cfg, rid_res, config_path,
                               roadmap_path=roadmap_path)
        checks["run_task_rc"] = code
        checks["after_run_state"] = state(rid_res)
        # the REAL manifest the runner produced
        chain = events.read_chain(root)
        rar = [e for e in chain if e["event_type"] == "RESULT_AUDIT_REQUESTED"
               and e["request_id"] == rid_res]
        manifest_ok = False
        if rar:
            p = rar[-1]["payload"]
            manifest_path = os.path.join(repo, p["run_dir"] +
                                         ".manifest.json")
            manifest_ok = os.path.exists(manifest_path) and bool(
                p.get("evidence_inventory_hash"))
            checks["manifest_file"] = manifest_path
            checks["evidence_inventory_hash"] = p.get(
                "evidence_inventory_hash")
        codex_launcher.CODEX_BIN = _install_fake(scratch, _FAKE_RESULT,
                                                 "codex-result")
        rc = codex_launcher.main(["--once"])
        checks["result_launcher_rc"] = rc
        checks["result_state"] = state(rid_res)
        res_ok = (checks["after_policy_state"] == "auto_approved"
                  and checks["after_run_state"] == "result_audit"
                  and manifest_ok and rc == 0
                  and state(rid_res) == "result_approved")
        checks["chain_healthy"] = events.verify_chain(root).healthy
        ok = src_ok and res_ok and checks["chain_healthy"]
    finally:
        identity.ENROLLMENT_HASH_FILE = saved_anchor
        codex_launcher.CODEX_BIN = saved_bin
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    _artifact(out_dir, "gate2-e2e", {
        "ok": ok, "checks": checks,
        "note": ("full fake-Codex e2e on a fresh staging council through the "
                 "real launcher/watch/runner; result round used the "
                 "auto-approved policy path (no human token) and a real "
                 "runner-built evidence manifest")})
    return ok


def rm_load(roadmap_path: str, root: str):
    from tools.autonomy import roadmap as rm
    from tools.council import policy
    return rm.load_roadmap(roadmap_path, policy.load_policy(root)[0])


# ------------------------------------------------------------------- gate 3

def gate3_drills(out_dir: str, scratch: str, live_root: str) -> bool:
    from tests.council_util import (append, make_cfg, make_repo,
                                    make_request, make_root,
                                    TEST_ENROLLMENT_TOKEN)
    from tools.council import (codex_watch, events, identity, locking,
                               publish, storage, txn)

    checks = {}
    # ---- drill A: torn tail on a COPY of the live chain (never the live)
    clone = os.path.join(scratch, "live-clone")
    os.makedirs(clone, exist_ok=True)
    storage.ensure_layout(clone)
    shutil.copy2(os.path.join(live_root, "events.jsonl"),
                 os.path.join(clone, "events.jsonl"))
    checks["clone_events"] = len(events.read_chain(clone))
    checks["clone_healthy_before"] = events.verify_chain(clone).healthy
    with open(os.path.join(clone, "events.jsonl"), "a",
              encoding="utf-8") as fh:
        fh.write('{"torn": "half-written line with no newline')
    report = events.verify_chain(clone)
    checks["torn_reported"] = bool(report.suffix_incomplete)
    checks["torn_unhealthy"] = not report.healthy
    torn_refused = False
    try:
        cfg_clone = make_cfg(clone, clone)
        events.append_event(clone, cfg_clone, "WATCHER_ERROR", "codex",
                            "torn-drill", clone, "0" * 40, {"reason": "x"})
    except Exception:
        torn_refused = True
    checks["append_refused_on_torn"] = torn_refused
    drill_a = (checks["clone_healthy_before"] and checks["torn_reported"]
               and checks["torn_unhealthy"] and torn_refused)

    # ---- drill B: STOP mid-claim rolls back (fresh staging council)
    base = pathlib.Path(scratch) / "drills"
    base.mkdir(parents=True, exist_ok=True)
    anchor = base / "anchor.sha256"
    anchor.write_text(identity.enrollment_hash(TEST_ENROLLMENT_TOKEN))
    saved_anchor = identity.ENROLLMENT_HASH_FILE
    try:
        identity.ENROLLMENT_HASH_FILE = str(anchor)
        root = make_root(base)
        repo, head = make_repo(base)
        cfg = make_cfg(repo, root)
        rid = "stop-drill-001"
        append(root, cfg, "BUILD_STARTED", "claude", rid, repo, head)
        append(root, cfg, "BUILD_READY", "claude", rid, repo, head)
        publish.publish_request(root, cfg, make_request(repo, head, rid))
        codex_cfg = make_cfg(repo, root, role="codex")
        open(os.path.join(root, "STOP"), "w").close()
        stop_raised = False
        try:
            codex_watch.claim(root, codex_cfg, rid)
        except Exception:
            stop_raised = True
        os.unlink(os.path.join(root, "STOP"))
        checks["stop_claim_refused"] = stop_raised
        checks["stop_no_stranded_lock"] = locking.read_lock(root, rid) is None
        checks["stop_back_in_ready"] = os.path.exists(
            storage.safe_request_path(root, "ready", rid))
        checks["stop_no_journal"] = os.listdir(
            os.path.join(root, "txn")) == []
        drill_b = all((stop_raised, checks["stop_no_stranded_lock"],
                       checks["stop_back_in_ready"],
                       checks["stop_no_journal"]))

        # ---- drill C: kill between journal steps -> recover (both ways)
        # C1 rollback: lock + move + journal(moved), no event -> back
        lock = locking.acquire(root, rid, "codex", rid, kind="claim")
        os.rename(storage.safe_request_path(root, "ready", rid),
                  storage.safe_request_path(root, "claimed", rid))
        t = txn.Txn.begin(root, "claim", rid, ["locked", "moved", "event"],
                          {"owner_token": lock.owner_token,
                           "prior_claimed_count": 0})
        t.mark("locked")
        t.mark("moved")
        healed = txn.recover(root, codex_cfg)
        checks["kill_rollback"] = (t.txn_id, "back") in healed
        checks["kill_rollback_ready"] = os.path.exists(
            storage.safe_request_path(root, "ready", rid))
        checks["kill_rollback_lock_gone"] = \
            locking.read_lock(root, rid) is None
        checks["kill_recover_idempotent"] = \
            txn.recover(root, codex_cfg) == []
        # C2 roll-forward: full claim, then a leftover journal -> forward
        _event, lock2 = codex_watch.claim(root, codex_cfg, rid)
        t2 = txn.Txn.begin(root, "claim", rid, ["locked", "moved", "event"],
                           {"owner_token": lock2.owner_token,
                            "prior_claimed_count": 0})
        t2.mark("locked")
        t2.mark("moved")
        healed = txn.recover(root, codex_cfg)
        checks["kill_forward"] = (t2.txn_id, "forward") in healed
        checks["kill_forward_claimed"] = os.path.exists(
            storage.safe_request_path(root, "claimed", rid))
        locking.release(lock2)
        drill_c = all((checks["kill_rollback"], checks["kill_rollback_ready"],
                       checks["kill_rollback_lock_gone"],
                       checks["kill_recover_idempotent"],
                       checks["kill_forward"],
                       checks["kill_forward_claimed"]))
    finally:
        identity.ENROLLMENT_HASH_FILE = saved_anchor

    ok = drill_a and drill_b and drill_c
    _artifact(out_dir, "gate3-drills", {
        "ok": ok, "checks": checks,
        "note": ("torn-tail drill ran on a scratch COPY of the live chain "
                 "(live untouched); repair-tail on live remains owner-"
                 "attended (human token)")})
    return ok


# ------------------------------------------------------------------- gate 4

def gate4_noservice(out_dir: str, scratch: str, live_root: str) -> bool:
    def run(cmd):
        try:
            p = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=30)
            return p.returncode, (p.stdout + p.stderr).strip()
        except Exception as exc:
            return -1, f"unavailable: {exc}"

    rc_units, units = run(["systemctl", "list-units", "--all", "--plain",
                           "--no-legend", "*coliseum*"])
    rc_files, unit_files = run(["systemctl", "list-unit-files", "--no-legend",
                                "*coliseum*"])
    rc_cron, cron = run(["crontab", "-l"])
    no_units = units.strip() == ""
    no_files = unit_files.strip() == ""
    no_cron = rc_cron != 0 or "coliseum" not in cron
    ok = no_units and no_files and no_cron
    _artifact(out_dir, "gate4-noservice", {
        "ok": ok,
        "checks": {"systemctl_units": units or "(none)",
                   "systemctl_unit_files": unit_files or "(none)",
                   "crontab": "no coliseum entries" if no_cron else cron},
        "note": "no coliseum service or cron entry exists before activation"})
    return ok


# ------------------------------------------------------------------- gate 5

def gate5_install_status(out_dir: str, scratch: str, live_root: str) -> bool:
    installed = os.path.exists(os.path.join("/etc/systemd/system", UNIT_NAME))
    enabled = False
    if installed:
        p = subprocess.run(["systemctl", "is-enabled", UNIT_NAME],
                           capture_output=True, text=True)
        enabled = p.stdout.strip() == "enabled"
    ok = os.path.exists(UNIT_SRC) and not enabled
    _artifact(out_dir, "gate5-install-without-enable", {
        "ok": ok, "owner_attended": True,
        "checks": {"unit_in_repo": os.path.exists(UNIT_SRC),
                   "unit_sha256": _sha256(UNIT_SRC) if os.path.exists(
                       UNIT_SRC) else None,
                   "installed_at_etc": installed, "enabled": enabled},
        "owner_commands": [
            f"sudo cp {UNIT_SRC} /etc/systemd/system/{UNIT_NAME}",
            "sudo systemctl daemon-reload",
            f"systemctl is-enabled {UNIT_NAME}  # must print 'disabled'"],
        "note": ("install is owner-attended (sudo); the gate verifies the "
                 "unit exists in-repo and is NOT enabled anywhere")})
    return ok


# --------------------------------------------------------------- gates 6/7

def gate67_runbooks(out_dir: str, scratch: str, live_root: str) -> bool:
    _artifact(out_dir, "gate6-owner-foreground-review", {
        "ok": False, "owner_attended": True,
        "owner_commands": [
            "cd ~/agent-coliseum",
            "python3 -m tools.autonomy.codex_launcher --once",
            "# review the printed decision + any launched session, then",
            "python3 -m tools.council.cli chain-report"],
        "note": ("owner runs ONE foreground --once pass on the live council "
                 "and reviews it before any enablement")})
    _artifact(out_dir, "gate7-owner-enable", {
        "ok": False, "owner_attended": True,
        "owner_commands": [
            f"sudo systemctl enable --now {UNIT_NAME}",
            f"systemctl status {UNIT_NAME}"],
        "note": ("owner enables ONLY the codex launcher; builder/experiment/"
                 "society automation stay disabled and need their own "
                 "audits")})
    return True


GATES = {
    "1": gate1_suite, "2": gate2_e2e, "3": gate3_drills,
    "4": gate4_noservice, "5": gate5_install_status, "67": gate67_runbooks,
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="council_staging")
    ap.add_argument("--gates", default="1,2,3,4,5,67")
    ap.add_argument("--out", default=os.path.join(
        REAL_REPO, "docs", "hardening", "activation"))
    ap.add_argument("--scratch", default=None)
    ap.add_argument("--live-root", default=os.environ.get(
        "COUNCIL_ROOT", LIVE_DEFAULT))
    args = ap.parse_args(argv)
    scratch = args.scratch or os.path.join(
        "/tmp", f"council-staging-{os.getpid()}")
    _guard_scratch(scratch, args.live_root)
    os.makedirs(scratch, exist_ok=True)
    results = {}
    for g in args.gates.split(","):
        g = g.strip()
        if g not in GATES:
            raise SystemExit(f"unknown gate {g!r}")
        results[g] = GATES[g](args.out, scratch, args.live_root)
    automated = [g for g in results if g not in ("5", "67")]
    ok = all(results[g] for g in automated)
    print("\nautomated gates:", "ALL PASS" if ok else "FAILURES", results)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
