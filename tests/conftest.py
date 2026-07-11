"""Suite-wide fixtures. H1: human-authority CLI commands prompt for the
owner passphrase via getpass — tests answer with the fixture passphrase
(tests/council_util.TEST_PASSPHRASE) so cli.main() paths mint real,
verifiable one-time tokens against the test identity."""
import getpass

import pytest

from tests.council_util import TEST_PASSPHRASE


@pytest.fixture(autouse=True)
def _test_owner_passphrase(monkeypatch):
    monkeypatch.setattr(getpass, "getpass",
                        lambda prompt="": TEST_PASSPHRASE)
