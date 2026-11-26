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

## Member output schemas

These are separate UTF-8 TOML files, not tables in `config.toml`:

```toml
columns = ["Member First Name", "Member Last Name", "REMS ID"]
extra_columns = "append"
missing_columns = "warn"
```

`columns` is a required non-empty list of unique non-empty strings. Names match exactly,
including case and spaces; double spaces in REMS headers are significant. Whitespace-only
names, unknown keys and malformed files are errors. The optional policies are `append|drop`
for extra columns (default `append`) and `warn|error` for missing columns (default `warn`).
The corresponding [CLI overrides](cli.md#member-output-schemas) take precedence over the
file settings. No schema means pass-through behaviour.

[`schemas/rems-members.toml`](../../schemas/rems-members.toml) is the registration script's
committed contract: 117 expected columns in their November 16, 2026 order, with
`extra_columns = "append"` and `missing_columns = "error"`. It keeps `REMS ID` at column 60
(BH). New columns go at the end; an absent expected header stops the script before any uploads.
The script always uses this file and has no per-run schema switches. Changes to its expected
columns go through code review.

Direct member commands can use this contract or a custom file through `--schema <path>`.
Schemas contain headers and policies only; never include member data. To recover an earlier
layout, copy only the earlier CSV's header names, in order, omitting the empty trailing field.
Review the full list before using it. A short schema with `extra_columns = "append"` still
includes all undeclared source columns, after the listed ones. To export only the listed
fields, set `extra_columns = "drop"` or pass `--extra-columns drop`.

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
