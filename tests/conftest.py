"""Suite-wide fixtures. H1: human-authority CLI commands prompt for the
owner passphrase via getpass — tests answer with the fixture passphrase
(tests/council_util.TEST_PASSPHRASE) so cli.main() paths mint real,
verifiable one-time tokens against the test identity. The enrollment
anchor (root-owned in production) points at a per-test file so the
authoritative writer's bootstrap enforcement is exercised for real;
tests probing a MISSING/wrong anchor override it themselves."""
import getpass

import pytest

from tests.council_util import TEST_ENROLLMENT_TOKEN, TEST_PASSPHRASE
from tools.council import identity

# --- progress observability under redirection --------------------------------
# The allowlisted audit command is `python3 -m pytest tests/ -q > log 2>&1`.
# When stdout is a FILE (not a TTY) pytest's `[N%]` markers are block-buffered
# and emitted only every ~80 tests, so the FIRST marker ("[ 8%]") does not
# reach the file until ~40s in and then sits unchanged for tens of seconds
# while the slow early council/mock tests run. An auditor tailing the file
# early misreads that stale "8%" as a hang. Flushing the terminal writer after
# every test makes the redirected file update continuously (real-time progress,
# correct completion + exit status), so the suite's completion is always
# observable. Pure observability — it changes no test outcome.
_TERMINAL_WRITER = None


def pytest_configure(config):
    global _TERMINAL_WRITER
    try:
        _TERMINAL_WRITER = config.get_terminal_writer()
    except Exception:
        _TERMINAL_WRITER = None


def pytest_runtest_logreport(report):
    if _TERMINAL_WRITER is not None:
        try:
            _TERMINAL_WRITER.flush()
        except Exception:
            pass


@pytest.fixture(autouse=True)
def _test_owner_passphrase(monkeypatch):
    monkeypatch.setattr(getpass, "getpass",
                        lambda prompt="": TEST_PASSPHRASE)


@pytest.fixture(autouse=True)
def _test_enrollment_anchor(tmp_path, monkeypatch):
    anchor = tmp_path / "test-enrollment-anchor.sha256"
    anchor.write_text(identity.enrollment_hash(TEST_ENROLLMENT_TOKEN))
    monkeypatch.setattr(identity, "ENROLLMENT_HASH_FILE", str(anchor))


@pytest.fixture(autouse=True)
def _test_checkpoint_isolation(tmp_path, monkeypatch):
    """The root-owned chain-head checkpoint (H4) is a GLOBAL fixed path.
    Once the owner provisions the real /etc/coliseum/chain-head.sha256,
    every test chain (a handful of events) would fail 'history cannot
    shrink' against the live pin. Point tests at a per-test path that does
    not exist (absent = no constraint); checkpoint tests override it
    themselves, exactly like the enrollment anchor fixture above."""
    from tools.council import checkpoint
    monkeypatch.setattr(checkpoint, "CHECKPOINT_FILE",
                        str(tmp_path / "test-chain-head.sha256"))
