# 0001 — Saved REMS logins in the OS keychain

Status: accepted (issue #97)

## Context

Every REMS command takes `--username`/`--password`, or reads `REMS_USERNAME`/`REMS_PASSWORD`.
They are only *used* when the cached REMS session (`~/.rems-sync/cookies.json`, a ~1-hour JWT)
has expired, but that happens on most runs, so the user retypes the password, leaves it in
shell history, or keeps it in the environment. And there is one cookie cache, so only one
REMS account can be used at a time, though one person may hold several REMS logins (one per
club, or per club and role). The cache itself is a live session token in a plain JSON file.

`semotion-sync` solved the same problem with saved logins keyed by alias: username in a
config file, password in the OS keychain via `keyring`, managed by `auth login/status/logout`
([its design doc](https://github.com/swimblocks/semotion-sync/blob/main/docs/design/0001-account-sync.md#authentication)).
This brings that design here unchanged, and adds the one thing REMS needs that semotion
doesn't: a session cache, kept in the keychain alongside the password.

### Constraints

- REMS login has an **emailed MFA code** and a cookie cache ([Logging in to REMS](../explanation/rems-login.md)); semotion
  has neither. A saved password does not remove the MFA prompt; it removes the retyping. The
  session cache is what keeps MFA to roughly once an hour.
- Tests and CI must never touch a real keychain.

## Design

### Commands

```
python -m src.main auth login --team <alias>    prompt for username and password, log in to REMS (with MFA), save
python -m src.main auth status                  the saved username per alias
python -m src.main auth logout --team <alias>   remove the saved login and its session
```

- `--team ALIAS` names a saved login: a club (`row`), or a club and role (`row-referee`) when
  one person holds several REMS logins for a club. As in semotion-sync it is free text; it is
  only ever a config key and part of a keychain service name, never a file path.
- `auth login` always prompts; it does not read options or env vars. It does a **fresh** REMS
  login (not the cached session), so a mistyped password is never saved. The resulting
  session is held in memory and written only after the username and password are saved.
- The username prompt defaults to the alias's saved username.
- The old top-level `login` command is removed; `auth login` replaces it.
- `--username`/`--password` are removed from every command. Credentials are never passed on
  the command line, where they land in shell history and the process list.
- Every REMS command takes `--team ALIAS` (required, as in semotion-sync), and uses that
  alias's saved login. It stays required even when only one login is saved:
  defaulting to the only login would make the same command line mean a different account
  once a second login is added, and REMS writes (deck evals) must go to the intended account.

### Storage

As semotion-sync:

- **Username:** `config.toml` in the user config directory (`platformdirs`), under
  `[teams.<alias>]`.
- **Password:** OS keychain via `keyring` (Windows Credential Manager, macOS Keychain, Linux
  Secret Service), service `rems-sync/<alias>`, keyed by username.
- Changing an alias's username saves the new password and username first, then removes the
  old password, so a failure part way leaves a working login. A refused delete is reported.
- `auth logout` removes the password before the username; if the keychain refuses, the login
  is not removed. (rems-sync also deletes the session first; see below.)

REMS-specific:

- **Session:** the REMS cookie jar, as JSON, in the keychain under service
  `rems-sync-session/<alias>`, keyed by the username the run resolved (saved login or env
  vars). It replaces `~/.rems-sync/cookies.json`; no session reaches a plain file.
  - The `rems-sync-session/` prefix is distinct from the passwords' `rems-sync/`, so no
    alias can make a password entry and a session entry share a service name (with a shared
    prefix, alias `row/session`'s password would land on alias `row`'s session).
  - Keyed by alias *and* account: an env override for account B under alias `row` reads and
    writes B's entry only, so it never reuses account A's session, and A's session is still
    there when the override is removed.
  - The session is a cache, not part of the login: losing it costs an MFA prompt, nothing
    more. So when an entry has to go, the session goes first and the login is never left
    half-removed:
    - `auth logout` deletes the session, then the password, then the username. If the
      session delete is refused, it stops with nothing removed. If the password delete is
      then refused, the login is intact (username and password both still saved), only the
      session is gone, and the error says so.
    - Changing an alias's username removes the old account's session after the old
      password, best-effort: a refused delete is a warning, not a failure.
  - Size: Windows Credential Manager holds at most 2,560 bytes per entry; keyring stores
    UTF-16, so about 1,280 characters. A cached session measured 614 bytes (2 cookies).
    If a write fails for any reason (size, keychain error), the run warns and continues
    without a cache: MFA on the next run, never a failed command.
- `REMSClient` takes a small session store (load / save / clear) instead of a cookie file
  path. The cache logic (probe, reuse, mid-run re-login on 403) is unchanged.

### Where a command's credentials come from

As semotion-sync:

1. `REMS_USERNAME` and `REMS_PASSWORD`, when both are set, override the saved login for the
   alias the run names. Read through keyring's `EnvironCredential`.
2. Otherwise, the alias's saved login.

- Setting only one of the two env vars is an error, not a silent fall back to the saved login.
- With neither, the command exits non-zero telling the user to run `auth login --team <alias>`.
  It never prompts mid-run (an MFA code excepted).

The password is only *used* when there is no live session, as today.

### Machines without an OS keychain

Everything goes through `keyring`, so a machine with no OS keychain (e.g. a future headless
deployment, #63) is given a different keyring backend, such as a file-backed one, by
configuration (`PYTHON_KEYRING_BACKEND` or `keyringrc.cfg`). No credential or session code
changes. Without one, the env vars still work, but no session can be cached, so every run
needs MFA.

### Interaction with `scripts/refresh-registration.ps1`

The script stops prompting for REMS credentials and takes `-Team <alias>`, passed through to
each REMS command.

## Differences from semotion-sync

| | semotion-sync | rems-sync | Why |
|---|---|---|---|
| Login check | Fresh login | Fresh login **with MFA** | REMS requires it |
| Session cache | None | Keychain, per alias and account | REMS has one; it is a credential, and must never cross accounts |

Everything else (commands, `--team`, storage, env vars, ordering) is the same.

## Verification

`ruff check` and `pytest -q`, green locally and in CI. Tests use an in-memory keychain
(`tests/fake_keyring.py`, copied from semotion-sync) installed by an autouse fixture, which
also clears the env vars and redirects the config file.

| Case | Expected |
|---|---|
| `auth login` with a wrong password | Error; nothing saved; password never printed |
| `auth login` succeeds | Fresh login (not cache); login and then session saved under the alias |
| `auth login` switches alias from A to B, then saving fails | Alias still resolves to A; no B session written; A's session untouched |
| Two aliases | Each run uses only its own alias's login and session |
| Env override A → B → A with live sessions | Each run uses only the resolved account's session; A's survives B's run |
| Session write refused or too large | Warning; command still succeeds; next run logs in afresh |
| Stored session unreadable or not JSON | Treated as no session; fresh login |
| Command with no saved login for the alias | Non-zero exit naming `auth login --team <alias>` |
| Both env vars set and login saved | Env vars win |
| Only one env var set | Error, not a fall back to the saved login |
| `--username` / `--password` passed | Rejected as unknown options |
| An alias's password missing from the keychain | `auth status` flags it, exits non-zero |
| Change an alias's username | Old password and session removed; refused password delete reported, refused session delete warned; new login kept |
| Aliases `row` and `row/session`, same username | Password and session entries never collide; each alias's login and session intact |
| `auth logout` for an unknown alias | Error, non-zero |
| `auth logout`, keychain refuses the session delete | Nothing removed, error reported |
| `auth logout`, session deleted but password delete refused | Username and password still saved, session gone; error says so |
| No session or password in any file | `~/.rems-sync/` gets nothing new |

Acceptance: after one `auth login --team row`, the full registration refresh runs with no
username or password typed (an MFA code may still be asked for), and a cached session saved
by a fresh MFA login is measured against the 2,560-byte limit.

## Decisions

1. **`auth logout` and the session.** semotion-sync has no session, so there is no
   precedent. Logout also deletes the alias's session entry, so "logged out" means the tool
   can no longer act as that login.
2. **Existing `~/.rems-sync/cookies.json`.** Ignored (it expires within the hour) and no
   longer written; the first run per alias logs in afresh. The file can be deleted by hand.
3. **Breaking change.** Removing `--username`/`--password` and top-level `login` breaks
   existing commands and docs. README, `docs/auth.md`, `docs/deck-eval-upload.md`, AGENTS.md
   and the script are updated in the implementation PR.

## Open items

None.
