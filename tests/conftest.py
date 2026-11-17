import keyring
import pytest

from src import credentials
from tests.fake_keyring import MemoryKeyring


@pytest.fixture(autouse=True)
def isolated_login(tmp_path, monkeypatch):
    """Every test gets an empty keychain and config file, and no credential env vars."""
    ring = MemoryKeyring()
    keyring.set_keyring(ring)
    monkeypatch.setattr(credentials, "config_file", lambda: tmp_path / "config" / "config.toml")
    monkeypatch.delenv(credentials.USERNAME_ENV, raising=False)
    monkeypatch.delenv(credentials.PASSWORD_ENV, raising=False)
    return ring


@pytest.fixture
def saved_row_login():
    """A saved login for alias `row`, for CLI tests that only need *a* login to exist."""
    credentials.save_login("row", credentials.Login("auto@example.org", "s3cret"))
