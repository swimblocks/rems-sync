from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from src import credentials
from src.credentials import KeyringSessionStore, Login
from src.main import cli

# CliRunner input isn't a terminal, so pwinput falls back to getpass, which warns it can't hide input.
pytestmark = pytest.mark.filterwarnings("ignore::getpass.GetPassWarning")


@pytest.fixture
def runner():
    return CliRunner()


def _fake_rems_login(cookies):
    """A REMSClient stand-in whose login() stores `cookies` in the session store it was given."""
    def make(username, password, mfa_callback, session_store):
        client = MagicMock()
        client.username, client.password = username, password

        def login(use_cache=True):
            session_store.save(cookies)
            return True

        client.login.side_effect = login
        return client
    return make


# --- auth login --------------------------------------------------------------------------------

@patch('src.main.REMSClient')
def test_auth_login_verifies_then_saves_login_and_session(mock_client_class, runner):
    mock_client_class.side_effect = _fake_rems_login({"jwt": "fresh"})

    result = runner.invoke(cli, ['auth', 'login', '--team', 'row'],
                           input="a@example.org\ns3cret\n")

    assert result.exit_code == 0, result.output
    assert mock_client_class.call_args.args[:2] == ("a@example.org", "s3cret")
    assert credentials.load_saved_login("row") == Login("a@example.org", "s3cret")
    assert KeyringSessionStore("row", "a@example.org").load() == {"jwt": "fresh"}
    assert "s3cret" not in result.output


@patch('src.main.REMSClient')
def test_auth_login_does_a_fresh_login_not_the_cache(mock_client_class, runner):
    client = MagicMock()
    mock_client_class.return_value = client

    runner.invoke(cli, ['auth', 'login', '--team', 'row'], input="a@example.org\ns3cret\n")

    client.login.assert_called_once_with(use_cache=False)


@patch('src.main.REMSClient')
def test_auth_login_failure_saves_nothing(mock_client_class, runner, isolated_login):
    mock_client_class.return_value.login.side_effect = Exception("Login failed: expected 302")

    result = runner.invoke(cli, ['auth', 'login', '--team', 'row'], input="a@example.org\nwrong\n")

    assert result.exit_code != 0
    assert "Nothing saved" in result.output
    assert credentials.saved_usernames() == {}
    assert isolated_login.passwords == {}


@patch('src.main.REMSClient')
def test_auth_login_failed_save_writes_no_session(mock_client_class, runner, monkeypatch):
    # Switching `row` from A to B: if saving B fails, `row` still resolves to A and no B session
    # is written under it.
    credentials.save_login("row", Login("a@example.org", "pwA"))
    KeyringSessionStore("row", "a@example.org").save({"jwt": "A"})
    mock_client_class.side_effect = _fake_rems_login({"jwt": "B"})

    def read_only(config):
        raise PermissionError("config.toml is read-only")

    monkeypatch.setattr(credentials, "_write_config", read_only)
    result = runner.invoke(cli, ['auth', 'login', '--team', 'row'], input="b@example.org\npwB\n")

    assert result.exit_code != 0
    assert credentials.load_saved_login("row") == Login("a@example.org", "pwA")
    assert KeyringSessionStore("row", "b@example.org").load() is None
    assert KeyringSessionStore("row", "a@example.org").load() == {"jwt": "A"}


@patch('src.main.REMSClient')
def test_auth_login_prompt_defaults_to_saved_username(mock_client_class, runner):
    credentials.save_login("row", Login("a@example.org", "old"))

    result = runner.invoke(cli, ['auth', 'login', '--team', 'row'], input="\nnew\n")

    assert result.exit_code == 0, result.output
    assert credentials.load_saved_login("row") == Login("a@example.org", "new")


@patch('src.main.REMSClient')
def test_auth_login_ignores_env_vars(mock_client_class, runner, monkeypatch):
    monkeypatch.setenv("REMS_USERNAME", "env@example.org")
    monkeypatch.setenv("REMS_PASSWORD", "envpw")

    result = runner.invoke(cli, ['auth', 'login', '--team', 'row'], input="a@example.org\ns3cret\n")

    assert result.exit_code == 0, result.output
    assert credentials.load_saved_login("row") == Login("a@example.org", "s3cret")


@patch('src.main.REMSClient')
def test_session_write_failure_is_a_warning(mock_client_class, runner, isolated_login, monkeypatch):
    mock_client_class.side_effect = _fake_rems_login({"jwt": "x" * 5000})
    real_set = isolated_login.set_password

    def too_big(service, username, password):
        if service.startswith("rems-sync-session/"):
            raise OSError("The stub received bad data")  # what WinVault does past 2,560 bytes
        real_set(service, username, password)

    monkeypatch.setattr(isolated_login, "set_password", too_big)
    result = runner.invoke(cli, ['auth', 'login', '--team', 'row'], input="a@example.org\ns3cret\n")

    assert result.exit_code == 0, result.output
    assert "Warning" in result.output
    assert credentials.load_saved_login("row") == Login("a@example.org", "s3cret")


def test_top_level_login_is_gone(runner):
    result = runner.invoke(cli, ['login'])
    assert result.exit_code != 0
    assert "No such command" in result.output


# --- auth status ---------------------------------------------------------------------------------

def test_auth_status_nothing_saved(runner):
    result = runner.invoke(cli, ['auth', 'status'])
    assert result.exit_code == 1
    assert "auth login --team" in result.output


def test_auth_status_lists_each_alias(runner):
    credentials.save_login("row", Login("a@example.org", "pw"))
    credentials.save_login("row-referee", Login("b@example.org", "pw"))

    result = runner.invoke(cli, ['auth', 'status'])

    assert result.exit_code == 0, result.output
    assert "row: a@example.org" in result.output
    assert "row-referee: b@example.org" in result.output
    assert "pw" not in result.output.replace("row", "")


def test_auth_status_flags_missing_password(runner, isolated_login):
    credentials.save_login("row", Login("a@example.org", "pw"))
    isolated_login.passwords.clear()

    result = runner.invoke(cli, ['auth', 'status'])

    assert result.exit_code == 1
    assert "missing" in result.output


def test_auth_status_reports_env_override(runner, monkeypatch):
    monkeypatch.setenv("REMS_USERNAME", "env@example.org")
    monkeypatch.setenv("REMS_PASSWORD", "envpw")

    result = runner.invoke(cli, ['auth', 'status'])

    assert "REMS_USERNAME" in result.output and "env@example.org" in result.output
    assert "envpw" not in result.output


# --- auth logout ---------------------------------------------------------------------------------

def test_auth_logout_removes_login_and_session(runner, isolated_login):
    credentials.save_login("row", Login("a@example.org", "pw"))
    KeyringSessionStore("row", "a@example.org").save({"jwt": "x"})

    result = runner.invoke(cli, ['auth', 'logout', '--team', 'row'])

    assert result.exit_code == 0, result.output
    assert credentials.saved_usernames() == {}
    assert isolated_login.passwords == {}


def test_auth_logout_unknown_alias(runner):
    result = runner.invoke(cli, ['auth', 'logout', '--team', 'row'])
    assert result.exit_code != 0
    assert "No saved login" in result.output


def test_auth_logout_refused(runner, isolated_login):
    credentials.save_login("row", Login("a@example.org", "pw"))
    isolated_login.refuse_deletes = True

    result = runner.invoke(cli, ['auth', 'logout', '--team', 'row'])

    assert result.exit_code != 0
    assert credentials.load_saved_login("row") == Login("a@example.org", "pw")


# --- Commands use the alias's login and session ------------------------------------------------

def _refresh_members(runner, tmp_path, *team):
    return runner.invoke(cli, ['refresh-members', *team, '--season', '2026-2027',
                               '--output', 'csv', '--output-file', str(tmp_path / 'm.csv')])


@patch('src.main.REMSClient')
def test_command_uses_the_alias_login_and_session(mock_client_class, runner, tmp_path):
    credentials.save_login("row", Login("a@example.org", "pwA"))
    credentials.save_login("row-referee", Login("b@example.org", "pwB"))
    mock_client_class.return_value.get_members_csv.return_value = "a,b\n1,2"

    result = _refresh_members(runner, tmp_path, '--team', 'row-referee')

    assert result.exit_code == 0, result.output
    args, kwargs = mock_client_class.call_args
    assert args[:2] == ("b@example.org", "pwB")
    store = kwargs["session_store"]
    store.save({"jwt": "B"})
    assert KeyringSessionStore("row-referee", "b@example.org").load() == {"jwt": "B"}


@patch('src.main.REMSClient')
def test_env_override_uses_its_own_accounts_session(mock_client_class, runner, tmp_path, monkeypatch):
    credentials.save_login("row", Login("a@example.org", "pwA"))
    KeyringSessionStore("row", "a@example.org").save({"jwt": "A"})
    monkeypatch.setenv("REMS_USERNAME", "b@example.org")
    monkeypatch.setenv("REMS_PASSWORD", "pwB")
    mock_client_class.return_value.get_members_csv.return_value = "a,b\n1,2"

    result = _refresh_members(runner, tmp_path, '--team', 'row')

    assert result.exit_code == 0, result.output
    args, kwargs = mock_client_class.call_args
    assert args[:2] == ("b@example.org", "pwB")
    assert kwargs["session_store"].load() is None  # never A's session
    kwargs["session_store"].save({"jwt": "B"})
    assert KeyringSessionStore("row", "a@example.org").load() == {"jwt": "A"}


@patch('src.main.REMSClient')
def test_command_without_saved_login_names_auth_login(mock_client_class, runner, tmp_path):
    result = _refresh_members(runner, tmp_path, '--team', 'row')

    assert result.exit_code != 0
    assert "auth login --team row" in result.output
    mock_client_class.assert_not_called()


def test_team_is_required(runner, tmp_path):
    result = _refresh_members(runner, tmp_path)
    assert result.exit_code != 0
    assert "--team" in result.output


@pytest.mark.parametrize("option", ["--username", "--password"])
def test_credential_options_are_gone(runner, tmp_path, option):
    result = _refresh_members(runner, tmp_path, '--team', 'row', option, 'x')
    assert result.exit_code != 0
    assert "No such option" in result.output
