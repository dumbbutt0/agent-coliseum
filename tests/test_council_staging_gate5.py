"""H7 condition 2 (owner-ratified 2026-07-11): the activation runbooks use
the USER-service deployment model. Gate 5 must check the user unit dir and
emit `systemctl --user` commands — no sudo, no /etc/systemd/system anywhere
in the activation surface."""
import json
import os

from scripts import council_staging


def _run_gate5(tmp_path, monkeypatch, home):
    monkeypatch.setenv("HOME", str(home))
    out = tmp_path / "artifacts"
    ok = council_staging.gate5_install_status(str(out), str(tmp_path / "s"),
                                              str(tmp_path / "live"))
    with open(out / "gate5-install-without-enable.json") as fh:
        return ok, json.load(fh)


def test_gate5_checks_user_unit_dir_and_user_commands(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    ok, art = _run_gate5(tmp_path, monkeypatch, home)
    assert ok  # unit in repo, nothing installed/enabled for a fresh HOME
    assert art["checks"]["deployment_mode"].startswith("user-service")
    assert art["checks"]["installed_at_user_dir"] is False
    cmds = " ".join(art["owner_commands"])
    assert "systemctl --user" in cmds
    assert ".config/systemd/user" in cmds
    assert "loginctl enable-linger" in cmds
    assert "sudo" not in cmds
    assert "/etc/systemd/system" not in cmds


def test_gate5_detects_user_mode_install(tmp_path, monkeypatch):
    """A unit copied into ~/.config/systemd/user is reported as installed
    (the install-without-enable state gate 5 verifies)."""
    home = tmp_path / "home"
    unit_dir = home / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    (unit_dir / council_staging.UNIT_NAME).write_text("[Unit]\n")
    ok, art = _run_gate5(tmp_path, monkeypatch, home)
    assert art["checks"]["installed_at_user_dir"] is True
    # enabled-state probe may be False in the sandbox; installed-not-enabled
    # remains a passing gate
    assert ok


def test_gate7_runbook_is_user_mode(tmp_path, monkeypatch):
    out = tmp_path / "artifacts"
    council_staging.gate67_runbooks(str(out), str(tmp_path / "s"),
                                    str(tmp_path / "live"))
    with open(out / "gate7-owner-enable.json") as fh:
        art = json.load(fh)
    cmds = " ".join(art["owner_commands"])
    assert "systemctl --user enable" in cmds
    assert "sudo" not in cmds