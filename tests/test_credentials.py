"""Saved logins and sessions. The login tests are ported from swimblocks/semotion-sync."""

import json
import tomllib

import keyring
import pytest
from keyring.errors import KeyringError, PasswordDeleteError

from src import credentials
from src.credentials import KeyringSessionStore, Login, NotLoggedInError

# --- Logins (as semotion-sync) ---------------------------------------------------------------

def test_save_then_load_round_trips():
    credentials.save_login("clubone", Login("auto@example.org", "s3cret"))
    assert credentials.load_login("clubone") == Login("auto@example.org", "s3cret")


def test_password_goes_to_the_keychain_and_not_the_config_file(isolated_login):
    credentials.save_login("clubone", Login("auto@example.org", "s3cret"))
    assert isolated_login.passwords == {("rems-sync/clubone", "auto@example.org"): "s3cret"}
    text = credentials.config_file().read_text(encoding="utf-8")
    assert "s3cret" not in text
    assert tomllib.loads(text) == {"teams": {"clubone": {"username": "auto@example.org"}}}


def test_teams_are_kept_apart():
    credentials.save_login("clubone", Login("one@example.org", "pw1"))
    credentials.save_login("clubtwo", Login("two@example.org", "pw2"))
    assert credentials.load_login("clubone") == Login("one@example.org", "pw1")
    assert credentials.load_login("clubtwo") == Login("two@example.org", "pw2")


def test_saving_again_replaces_the_old_login(isolated_login):
    credentials.save_login("clubone", Login("old@example.org", "pw1"))
    credentials.save_login("clubone", Login("new@example.org", "pw2"))
    assert credentials.load_login("clubone") == Login("new@example.org", "pw2")
    assert list(isolated_login.passwords) == [("rems-sync/clubone", "new@example.org")]


def test_unknown_team_is_not_logged_in():
    with pytest.raises(NotLoggedInError, match="auth login --team clubone"):
        credentials.load_login("clubone")


def test_username_without_a_keychain_password_is_not_logged_in(isolated_login):
    credentials.save_login("clubone", Login("auto@example.org", "s3cret"))
    isolated_login.passwords.clear()
    with pytest.raises(NotLoggedInError):
        credentials.load_login("clubone")


def test_delete_removes_both_halves(isolated_login):
    credentials.save_login("clubone", Login("auto@example.org", "s3cret"))
    credentials.save_login("clubtwo", Login("two@example.org", "pw2"))
    credentials.delete_login("clubone")
    assert list(isolated_login.passwords) == [("rems-sync/clubtwo", "two@example.org")]
    assert credentials.saved_usernames() == {"clubtwo": "two@example.org"}


def test_delete_of_unknown_team_is_not_logged_in():
    with pytest.raises(NotLoggedInError):
        credentials.delete_login("clubone")


def test_saved_usernames_is_empty_with_no_config_file():
    assert credentials.saved_usernames() == {}


def test_environment_overrides_the_saved_login(monkeypatch):
    credentials.save_login("clubone", Login("saved@example.org", "saved"))
    monkeypatch.setenv("REMS_USERNAME", "env@example.org")
    monkeypatch.setenv("REMS_PASSWORD", "envpw")
    assert credentials.load_login("clubone") == Login("env@example.org", "envpw")


def test_environment_needs_no_saved_login(monkeypatch):
    monkeypatch.setenv("REMS_USERNAME", "env@example.org")
    monkeypatch.setenv("REMS_PASSWORD", "envpw")
    assert credentials.load_login("anyteam") == Login("env@example.org", "envpw")


@pytest.mark.parametrize("present", ["REMS_USERNAME", "REMS_PASSWORD"])
def test_half_set_environment_is_an_error_not_a_silent_fallback(monkeypatch, present):
    credentials.save_login("clubone", Login("saved@example.org", "saved"))
    monkeypatch.setenv(present, "x")
    with pytest.raises(NotLoggedInError, match="both"):
        credentials.load_login("clubone")


def test_delete_still_clears_the_config_when_the_keychain_entry_is_gone(isolated_login):
    credentials.save_login("clubone", Login("auto@example.org", "s3cret"))
    isolated_login.passwords.clear()
    credentials.delete_login("clubone")
    assert credentials.saved_usernames() == {}


def test_repr_hides_the_password():
    assert "s3cret" not in repr(Login("auto@example.org", "s3cret"))


def test_refused_keychain_delete_keeps_the_login_discoverable(isolated_login):
    credentials.save_login("clubone", Login("auto@example.org", "s3cret"))
    isolated_login.refuse_deletes = True
    with pytest.raises(PasswordDeleteError):
        credentials.delete_login("clubone")
    assert credentials.saved_usernames() == {"clubone": "auto@example.org"}
    assert credentials.load_saved_login("clubone") == Login("auto@example.org", "s3cret")


def test_failed_config_write_keeps_the_previous_login(monkeypatch):
    credentials.save_login("clubone", Login("old@example.org", "pw1"))

    def read_only(config):
        raise PermissionError("config.toml is read-only")

    monkeypatch.setattr(credentials, "_write_config", read_only)
    with pytest.raises(PermissionError):
        credentials.save_login("clubone", Login("new@example.org", "pw2"))
    assert credentials.load_saved_login("clubone") == Login("old@example.org", "pw1")


def test_refused_delete_of_the_old_password_still_saves_the_new_login(isolated_login):
    credentials.save_login("clubone", Login("old@example.org", "pw1"))
    isolated_login.refuse_deletes = True
    with pytest.raises(PasswordDeleteError, match="old@example.org"):
        credentials.save_login("clubone", Login("new@example.org", "pw2"))
    assert credentials.load_saved_login("clubone") == Login("new@example.org", "pw2")


# --- Sessions (REMS-specific) ----------------------------------------------------------------

def _session(alias, username):
    return KeyringSessionStore(alias, username)


def test_session_round_trips_through_the_keychain(isolated_login):
    _session("row", "a@example.org").save({"Authentication-JWT": "tok", "mfa_uuid": "u"})
    assert _session("row", "a@example.org").load() == {"Authentication-JWT": "tok", "mfa_uuid": "u"}
    assert ("rems-sync-session/row", "a@example.org") in isolated_login.passwords


def test_session_is_per_account_within_an_alias():
    # An env override for B under alias `row` must never see A's session, and A's must survive.
    _session("row", "a@example.org").save({"jwt": "A"})
    assert _session("row", "b@example.org").load() is None
    _session("row", "b@example.org").save({"jwt": "B"})
    assert _session("row", "a@example.org").load() == {"jwt": "A"}


def test_session_is_per_alias():
    _session("row", "a@example.org").save({"jwt": "row"})
    assert _session("row-referee", "a@example.org").load() is None


def test_password_and_session_namespaces_never_collide(isolated_login):
    # With a shared prefix, alias `row/session`'s password would land on alias `row`'s session.
    credentials.save_login("row/session", Login("a@example.org", "pw"))
    _session("row", "a@example.org").save({"jwt": "x"})
    assert credentials.load_saved_login("row/session") == Login("a@example.org", "pw")
    assert _session("row", "a@example.org").load() == {"jwt": "x"}


@pytest.mark.parametrize("stored", ["not json", "[1, 2]", ""])
def test_unreadable_session_is_treated_as_none(isolated_login, stored):
    isolated_login.passwords[("rems-sync-session/row", "a@example.org")] = stored
    assert _session("row", "a@example.org").load() is None


def test_session_load_survives_a_broken_keychain(monkeypatch):
    def broken(*_args):
        raise KeyringError("no backend")

    monkeypatch.setattr(keyring, "get_password", broken)
    assert _session("row", "a@example.org").load() is None


def test_session_clear_tolerates_a_missing_entry():
    _session("row", "a@example.org").clear()  # nothing saved; must not raise


def test_session_json_never_contains_the_password():
    credentials.save_login("row", Login("a@example.org", "s3cret"))
    _session("row", "a@example.org").save({"jwt": "tok"})
    assert "s3cret" not in json.dumps(_session("row", "a@example.org").load())


# --- Login and session together ---------------------------------------------------------------

def test_delete_login_removes_the_session_too(isolated_login):
    credentials.save_login("row", Login("a@example.org", "pw"))
    _session("row", "a@example.org").save({"jwt": "x"})
    credentials.delete_login("row")
    assert isolated_login.passwords == {}
    assert credentials.saved_usernames() == {}


def test_delete_login_refused_session_delete_removes_nothing(isolated_login):
    credentials.save_login("row", Login("a@example.org", "pw"))
    _session("row", "a@example.org").save({"jwt": "x"})
    isolated_login.refuse_deletes = True
    with pytest.raises(PasswordDeleteError, match="nothing was removed"):
        credentials.delete_login("row")
    assert credentials.load_saved_login("row") == Login("a@example.org", "pw")
    assert _session("row", "a@example.org").load() == {"jwt": "x"}


def test_delete_login_refused_password_delete_keeps_the_login_but_not_the_session(
        isolated_login, monkeypatch):
    credentials.save_login("row", Login("a@example.org", "pw"))
    _session("row", "a@example.org").save({"jwt": "x"})
    real_delete = isolated_login.delete_password

    def refuse_passwords(service, username):
        if service == "rems-sync/row":
            raise PasswordDeleteError("access denied")
        real_delete(service, username)

    monkeypatch.setattr(isolated_login, "delete_password", refuse_passwords)
    with pytest.raises(PasswordDeleteError, match="session was removed"):
        credentials.delete_login("row")
    assert credentials.load_saved_login("row") == Login("a@example.org", "pw")
    assert _session("row", "a@example.org").load() is None


def test_changing_username_removes_the_old_session(isolated_login):
    credentials.save_login("row", Login("old@example.org", "pw1"))
    _session("row", "old@example.org").save({"jwt": "old"})
    assert credentials.save_login("row", Login("new@example.org", "pw2")) == []
    assert _session("row", "old@example.org").load() is None


def test_refused_old_session_delete_is_only_a_warning(isolated_login, monkeypatch):
    credentials.save_login("row", Login("old@example.org", "pw1"))
    _session("row", "old@example.org").save({"jwt": "old"})
    real_delete = isolated_login.delete_password

    def refuse_sessions(service, username):
        if service.startswith("rems-sync-session/"):
            raise PasswordDeleteError("access denied")
        real_delete(service, username)

    monkeypatch.setattr(isolated_login, "delete_password", refuse_sessions)
    warnings = credentials.save_login("row", Login("new@example.org", "pw2"))
    assert len(warnings) == 1 and "old@example.org" in warnings[0]
    assert credentials.load_saved_login("row") == Login("new@example.org", "pw2")
