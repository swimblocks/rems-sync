# Configuration

Where rems-sync keeps its settings and saved logins. Why it is split this way:
[Saved logins](../explanation/saved-logins.md). The code is [src/credentials.py](../../src/credentials.py).

## `config.toml`

In the user config directory:

| OS | Path |
|---|---|
| Windows | `%LOCALAPPDATA%\rems-sync\config.toml` |
| macOS | `~/Library/Application Support/rems-sync/config.toml` |
| Linux | `~/.config/rems-sync/config.toml` (or under `$XDG_CONFIG_HOME`) |

Nothing secret is kept in it.

```toml
[teams.row]
username = "<REMS username>"

[sheets]
"2026-2027" = "<sheet_id>"
```

| Table | Written by | Meaning |
|---|---|---|
| `[teams.<alias>]` | `auth login`, `auth logout` | `username`: the REMS username saved for the alias. |
| `[sheets]` | You, by hand | Each season's registration sheet ID, read by [`refresh-registration.ps1`](refresh-registration-script.md) when it isn't given `-SheetId`. |

`auth login` and `auth logout` rewrite the file, keeping every other table but not comments.

## OS keychain

Through [`keyring`](https://pypi.org/project/keyring/): Windows Credential Manager, macOS
Keychain, or Linux Secret Service.

| Service | Account | Holds |
|---|---|---|
| `rems-sync/<alias>` | the REMS username | The password. |
| `rems-sync-session/<alias>` | the REMS username | The REMS session: the cookie jar as a JSON object. |

The session entry belongs to the account that made it: under an environment override (below)
the session is read and written under the override's username.

Windows Credential Manager holds at most 2,560 bytes per entry. A session measured 2,324 bytes
(5 cookies) in November 2026. If a session can't be saved, the run warns
(`could not save the REMS session`) and carries on; the next run asks for a code.

A machine without an OS keychain can be given another keyring backend with
`PYTHON_KEYRING_BACKEND` or a `keyringrc.cfg` ([keyring's docs](https://pypi.org/project/keyring/#configuring)).

## Environment variables

| Variable | Meaning |
|---|---|
| `REMS_USERNAME`, `REMS_PASSWORD` | When **both** are set, used instead of the saved login for every REMS command run in that environment. Setting only one is an error. `auth status` shows when they are set. |
| `PYTHON_KEYRING_BACKEND` | Which keyring backend to use (keyring's own setting). |
| `GOOGLE_APPLICATION_CREDENTIALS`, `CLOUDSDK_CONFIG` | Google's own settings, which change where [Google access](../explanation/google-access.md) comes from. |
