"""Saved REMS logins and sessions, per alias.

Username in a config file, password and session in the OS keychain. The login half is ported
from swimblocks/semotion-sync; the session store is REMS-specific. Design:
docs/design/0001-saved-rems-login.md.
"""

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

import keyring
import platformdirs
import tomli_w
from keyring.credentials import EnvironCredential
from keyring.errors import KeyringError, PasswordDeleteError

USERNAME_ENV = "REMS_USERNAME"
PASSWORD_ENV = "REMS_PASSWORD"


class NotLoggedInError(Exception):
    pass


@dataclass(frozen=True)
class Login:
    username: str
    password: str

    def __repr__(self) -> str:
        return f"Login(username={self.username!r}, password=<hidden>)"


def config_file() -> Path:
    return Path(platformdirs.user_config_dir("rems-sync", appauthor=False)) / "config.toml"


def _service(team_alias: str) -> str:
    return f"rems-sync/{team_alias}"


def _session_service(team_alias: str) -> str:
    # A different prefix from _service(), so no alias can make a password entry and a session
    # entry share a service name (alias `row/session` vs. alias `row` under a shared prefix).
    return f"rems-sync-session/{team_alias}"


def _read_config() -> dict:
    try:
        return tomllib.loads(config_file().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def _write_config(config: dict) -> None:
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomli_w.dumps(config), encoding="utf-8")


def _not_logged_in(team_alias: str) -> NotLoggedInError:
    return NotLoggedInError(f"No saved login for team {team_alias!r}; "
                            f"run `python -m src.main auth login --team {team_alias}`.")


def saved_usernames() -> dict[str, str]:
    """The saved username for each team alias."""
    return {alias: team["username"] for alias, team in _read_config().get("teams", {}).items()}


def _forget(service: str, username: str) -> None:
    """Remove a keychain entry; an entry that is already gone is not an error."""
    try:
        keyring.delete_password(service, username)
    except PasswordDeleteError:
        if keyring.get_password(service, username) is not None:
            raise  # the delete failed, e.g. access denied; the entry is still stored


def save_login(team_alias: str, login: Login) -> list[str]:
    """Save the login, replacing any other username saved for the team.

    The new password and config land before the old password is removed, so a failure part
    way leaves a working login, never neither. The old username's session is removed last and
    best-effort: it is only a cache. Returns warnings for anything left behind.
    """
    previous = saved_usernames().get(team_alias)
    keyring.set_password(_service(team_alias), login.username, login.password)
    config = _read_config()
    config.setdefault("teams", {})[team_alias] = {"username": login.username}
    _write_config(config)
    warnings = []
    if previous is not None and previous != login.username:
        try:
            _forget(_service(team_alias), previous)
        except PasswordDeleteError as e:
            raise PasswordDeleteError(
                f"Saved the login for {login.username}, but could not remove the old password "
                f"for {previous} from the OS keychain") from e
        try:
            _forget(_session_service(team_alias), previous)
        except PasswordDeleteError as e:
            warnings.append(f"Could not remove the old REMS session for {previous} from the "
                            f"OS keychain ({e}); it is unused and can be removed by hand.")
    return warnings


def environment_login() -> Login | None:
    """The login from the environment when both variables are set; None when neither is."""
    env = EnvironCredential(USERNAME_ENV, PASSWORD_ENV)
    values = []
    for read in (lambda: env.username, lambda: env.password):
        try:
            values.append(read())
        except ValueError:
            values.append(None)
    if values == [None, None]:
        return None
    if None in values:
        raise NotLoggedInError(f"Set both {USERNAME_ENV} and {PASSWORD_ENV}, or neither.")
    return Login(*values)


def load_saved_login(team_alias: str) -> Login:
    """The saved login, ignoring the environment; raises NotLoggedInError."""
    username = saved_usernames().get(team_alias)
    password = username and keyring.get_password(_service(team_alias), username)
    if not password:
        raise _not_logged_in(team_alias)
    return Login(username, password)


def load_login(team_alias: str) -> Login:
    """The environment's login if set, else the saved one; raises NotLoggedInError."""
    if (login := environment_login()) is not None:
        return login
    return load_saved_login(team_alias)


def delete_login(team_alias: str) -> None:
    """Remove the session, then the password, then the username.

    The session goes first because it is only a cache: if the keychain refuses it, nothing is
    removed; if it then refuses the password, the login is still whole and only the session is
    gone. Either way the login is never left half-removed.
    """
    config = _read_config()
    team = config.get("teams", {}).pop(team_alias, None)
    if team is None:
        raise _not_logged_in(team_alias)
    username = team["username"]
    try:
        _forget(_session_service(team_alias), username)
    except PasswordDeleteError as e:
        raise PasswordDeleteError(
            f"Could not remove the REMS session for {team_alias!r} from the OS keychain ({e}); "
            "nothing was removed") from e
    try:
        _forget(_service(team_alias), username)
    except PasswordDeleteError as e:
        raise PasswordDeleteError(
            f"The REMS session was removed, but the password for {team_alias!r} could not be "
            f"removed from the OS keychain ({e}); the login is still saved") from e
    _write_config(config)


class KeyringSessionStore:
    """The REMS cookie jar for one alias and account, kept in the OS keychain.

    Keyed by alias *and* username, so a run only ever sees the session of the account whose
    credentials it holds (an env override for another account never reuses this one).
    """

    def __init__(self, team_alias: str, username: str):
        self._service = _session_service(team_alias)
        self._username = username

    def load(self) -> dict | None:
        """The saved cookies, or None if there are none or they can't be read."""
        try:
            raw = keyring.get_password(self._service, self._username)
        except KeyringError:
            return None
        if not raw:
            return None
        try:
            cookies = json.loads(raw)
        except ValueError:
            return None
        return cookies if isinstance(cookies, dict) and cookies else None

    def save(self, cookies: dict) -> None:
        """Raises if the keychain refuses (e.g. Windows' 2,560-byte limit); callers warn."""
        keyring.set_password(self._service, self._username, json.dumps(cookies))

    def clear(self) -> None:
        _forget(self._service, self._username)
