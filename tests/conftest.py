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
