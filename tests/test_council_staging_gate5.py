"""H7 condition 2 (owner-ratified 2026-07-11): the activation runbooks use
the USER-service deployment model, and the no-service/install gates FAIL
CLOSED — gate 4 probes BOTH systemd managers and treats an unreachable bus
as failure; gate 5 passes an installed unit only when `is-enabled`
genuinely prints `disabled` (enabled-runtime/linked/static/masked or an
unreachable manager all fail)."""
import json
import os
import subprocess

from scripts import council_staging


class _Proc:
    def __init__(self, rc=0, out="", err=""):
        self.returncode = rc
        self.stdout = out
        self.stderr = err


_REAL_RUN = subprocess.run


def _stub_run(responder):
    """Intercept only the gate's probe commands (systemctl/crontab); pass
    everything else (e.g. the artifact writer's git rev-parse) through."""
    def run(cmd, **kw):
        if cmd and cmd[0] in ("systemctl", "crontab"):
            return responder(cmd)
        return _REAL_RUN(cmd, **kw)
    return run


# ------------------------------------------------------------------ gate 5

def _run_gate5(tmp_path, monkeypatch, home):
    monkeypatch.setenv("HOME", str(home))
    out = tmp_path / "artifacts"
    ok = council_staging.gate5_install_status(str(out), str(tmp_path / "s"),
                                              str(tmp_path / "live"))
    with open(out / "gate5-install-without-enable.json") as fh:
        return ok, json.load(fh)


def _install_unit(home):
    unit_dir = home / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    (unit_dir / council_staging.UNIT_NAME).write_text("[Unit]\n")


def test_gate5_user_commands_no_sudo(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    ok, art = _run_gate5(tmp_path, monkeypatch, home)
    assert ok  # unit in repo, nothing installed for a fresh HOME
    assert art["checks"]["deployment_mode"].startswith("user-service")
    assert art["checks"]["is_enabled_state"] == "not-installed"
    cmds = " ".join(art["owner_commands"])
    assert "systemctl --user" in cmds
    assert ".config/systemd/user" in cmds
    assert "loginctl enable-linger" in cmds
    assert "sudo" not in cmds
    assert "/etc/systemd/system" not in cmds


def test_gate5_installed_and_disabled_passes(tmp_path, monkeypatch):
    home = tmp_path / "home"
    _install_unit(home)
    monkeypatch.setattr(subprocess, "run",
                        _stub_run(lambda cmd: _Proc(0, "disabled\n")))
    ok, art = _run_gate5(tmp_path, monkeypatch, home)
    assert art["checks"]["installed_at_user_dir"] is True
    assert art["checks"]["is_enabled_state"] == "disabled"
    assert ok


def test_gate5_enabled_runtime_fails_closed(tmp_path, monkeypatch):
    """The reproduced audit case: `is-enabled` printing `enabled-runtime`
    must NOT pass as disabled."""
    home = tmp_path / "home"
    _install_unit(home)
    monkeypatch.setattr(subprocess, "run",
                        _stub_run(lambda cmd: _Proc(0, "enabled-runtime\n")))
    ok, art = _run_gate5(tmp_path, monkeypatch, home)
    assert art["checks"]["is_enabled_state"] == "enabled-runtime"
    assert art["checks"]["confirmed_disabled"] is False
    assert not ok


def test_gate5_unreachable_manager_fails_closed(tmp_path, monkeypatch):
    home = tmp_path / "home"
    _install_unit(home)

    def boom(cmd):
        raise OSError("no user bus")

    monkeypatch.setattr(subprocess, "run", _stub_run(boom))
    ok, art = _run_gate5(tmp_path, monkeypatch, home)
    assert art["checks"]["is_enabled_state"].startswith("unavailable")
    assert not ok


# ------------------------------------------------------------------ gate 4

def _run_gate4(tmp_path, monkeypatch, responder):
    monkeypatch.setattr(subprocess, "run", _stub_run(responder))
    out = tmp_path / "artifacts"
    ok = council_staging.gate4_noservice(str(out), str(tmp_path / "s"),
                                         str(tmp_path / "live"))
    with open(out / "gate4-noservice.json") as fh:
        return ok, json.load(fh)


def test_gate4_probes_both_managers_and_passes_when_all_empty(tmp_path,
                                                              monkeypatch):
    seen = []

    def responder(cmd):
        seen.append(tuple(cmd))
        if cmd[0] == "crontab":
            return _Proc(1, "", "no crontab for dummy")
        return _Proc(0, "")

    ok, art = _run_gate4(tmp_path, monkeypatch, responder)
    assert ok
    # both managers genuinely probed
    assert any(c[:2] == ("systemctl", "--user") for c in seen)
    assert any(c[0] == "systemctl" and c[1] != "--user" for c in seen)
    assert art["checks"]["user_units"] == "(none)"
    assert art["checks"]["system_units"] == "(none)"


def test_gate4_rc1_empty_is_genuine_empty_list(tmp_path, monkeypatch):
    """systemctl list-unit-files exits 1 with NO output when the filter
    matches nothing — a genuine clean answer, distinct from a bus failure
    (rc!=0 WITH stderr), which still fails closed."""
    def responder(cmd):
        if cmd[0] == "crontab":
            return _Proc(1, "", "no crontab for dummy")
        if "list-unit-files" in cmd:
            return _Proc(1, "", "")          # empty filter answer
        return _Proc(0, "")
    ok, art = _run_gate4(tmp_path, monkeypatch, responder)
    assert ok
    assert art["checks"]["system_unit_files"] == "(none)"


def test_gate4_user_unit_present_fails(tmp_path, monkeypatch):
    def responder(cmd):
        if cmd[0] == "crontab":
            return _Proc(1, "", "no crontab for dummy")
        if "--user" in cmd and "list-units" in cmd:
            return _Proc(0, "coliseum-codex-launcher.service loaded")
        return _Proc(0, "")

    ok, art = _run_gate4(tmp_path, monkeypatch, responder)
    assert not ok
    assert "coliseum" in art["checks"]["user_units"]


def test_gate4_unreachable_bus_fails_closed(tmp_path, monkeypatch):
    """The audit-sandbox case: bus access denied must FAIL the gate, never
    read as a clean empty result."""
    def responder(cmd):
        if cmd[0] == "crontab":
            return _Proc(1, "", "no crontab for dummy")
        return _Proc(1, "", "Failed to connect to bus: Operation not "
                            "permitted")

    ok, art = _run_gate4(tmp_path, monkeypatch, responder)
    assert not ok
    assert art["checks"]["system_units"].startswith("unavailable")


# ------------------------------------------------------------------ gate 7

def test_gate7_runbook_is_user_mode(tmp_path, monkeypatch):
    out = tmp_path / "artifacts"
    council_staging.gate67_runbooks(str(out), str(tmp_path / "s"),
                                    str(tmp_path / "live"))
    with open(out / "gate7-owner-enable.json") as fh:
        art = json.load(fh)
    cmds = " ".join(art["owner_commands"])
    assert "systemctl --user enable" in cmds
    assert "sudo" not in cmds