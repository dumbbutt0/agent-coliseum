"""Doc/CLI-contract guard for the governance activation package (audit 000789). Every
post-activation observation the runbook annotates must be present in the referenced
command's actual output schema — in particular the effective policy pin comes ONLY from
`locate-resume-checkpoint --json` (`policy_pin.live.version`), never from `status`."""
import os

from tests.council_util import (append, make_cfg, make_repo, make_root)
from tools.council import cli, policy, resume_locator, storage

DOC = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                   "docs", "first-gladiator", "GOVERNANCE-ACTIVATION-PACKAGE.md")


def _doc_text():
    with open(DOC, encoding="utf-8") as fh:
        return fh.read()


def test_locator_output_actually_carries_the_referenced_pin_field():
    """The runbook points the effective-pin check at policy_pin.live.version — that
    field must exist in the locator's output schema."""
    fields = resume_locator.ResumeLocation.__dataclass_fields__
    assert "policy_pin" in fields
    # a real resolution surfaces policy_pin.live.version
    from tools.council import Config
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        loc = resume_locator.locate_resume_checkpoint(
            Config(council_root=d, repo_roots=(d,), role="claude"))
        # even a not-found resolution returns the structured dict with the key
        assert "policy_pin" in loc.to_dict()


def test_status_command_does_not_emit_the_policy_pin(tmp_path, capsys):
    """Grounds the runbook's claim that `status` does NOT display the policy pin."""
    root = make_root(tmp_path)
    repo, head = make_repo(tmp_path)
    cfg = make_cfg(repo, root)
    policy.write_initial_policy(root)
    _p, v1 = policy.load_policy(root)
    append(root, cfg, "POLICY_INITIALIZED", "human", "council-control", repo,
           "0" * 40, {"policy_hash": v1, "policy_file": storage.POLICY_FILE})
    os.environ["COUNCIL_ROOT"] = root
    os.environ["COUNCIL_REPO_ROOTS"] = repo
    try:
        cli.cmd_status(type("A", (), {"role": "claude"})())
    finally:
        os.environ.pop("COUNCIL_ROOT", None)
        os.environ.pop("COUNCIL_REPO_ROOTS", None)
    out = capsys.readouterr().out
    # status prints control/identity/chain, never the effective policy pin/version/hash
    assert "policy_pin" not in out and v1 not in out
    assert "policy version" not in out.lower()


def test_doc_does_not_claim_status_shows_the_pin():
    text = _doc_text().lower()
    # no line annotates `status` as showing the v4 pin
    for line in text.splitlines():
        if "cli --role claude status" in line:
            assert "pin shows" not in line and "pin v4" not in line, \
                f"runbook falsely annotates status with a pin claim: {line!r}"
    # the corrected pin check references the field the locator actually emits
    assert "policy_pin.live.version == 4" in _doc_text()
    # the transient mismatch is documented
    assert "POLICY_PIN_MISMATCH" in _doc_text()
