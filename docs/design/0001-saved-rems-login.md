# 0001 — Saved REMS logins in the OS keychain

Status: accepted (issue #97)

## Context

Every REMS command takes `--username`/`--password`, or reads `REMS_USERNAME`/`REMS_PASSWORD`.
They are only *used* when the cached REMS session (`~/.rems-sync/cookies.json`, a ~1-hour JWT)
has expired, but that happens on most runs, so the user retypes the password, leaves it in
shell history, or keeps it in the environment. And there is one cookie cache, so only one
REMS account can be used at a time, though one person may hold several REMS logins (one per
club, or per club and role).

`semotion-sync` solved the same problem with saved logins keyed by alias: username in a
config file, password in the OS keychain via `keyring`, managed by `auth login/status/logout`
([its design doc](https://github.com/swimblocks/semotion-sync/blob/main/docs/design/0001-account-sync.md#authentication)).
This brings that design here unchanged except where REMS differs, so both tools behave the
same way.

### Constraints

- REMS login has an **emailed MFA code** and a cookie cache ([auth.md](../auth.md)); semotion
  has neither. A saved password does not remove the MFA prompt; it removes the retyping.
- Tests and CI must never touch a real keychain.

## Design

### Commands

```
python -m src.main auth login --team <alias>    prompt for username and password, log in to REMS (with MFA), save
python -m src.main auth status                  the saved username per alias
python -m src.main auth logout --team <alias>   remove the saved login
```

- `--team ALIAS` names a saved login: a club (`row`), or a club and role (`row-referee`) when
  one person holds several REMS logins for a club. Aliases are lowercase letters, digits and
  `-` (`^[a-z0-9][a-z0-9-]{0,62}$`); anything else is rejected. They become config keys and
  keychain service names, so a narrow alphabet keeps them unambiguous everywhere.
- `auth login` always prompts; it does not read options or env vars. It does a **fresh** REMS
  login (not the cookie cache), so a mistyped password is never saved. The session it gets is
  written to that *account's* cookie cache (below), never the alias's, so a save that fails
  part way can't leave one account's session behind another account's saved login.
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
- `auth logout` removes the password before the username; if the keychain refuses, nothing is
  removed.

REMS-specific:

- **Cookie cache per account, not per alias:** a REMS session belongs to the account that
  logged in, so the cache is keyed by the username a run actually resolved (saved login or
  env vars): `~/.rems-sync/cookies/<sha256(normalized username)[:16]>.json`, replacing the
  single `~/.rems-sync/cookies.json`. Normalized means trimmed and lowercased.
  - A run only ever loads the session of the account whose credentials it holds, so an env
    var override for account B never reuses account A's session under the same alias, and
    A's session is untouched for when the override is removed.
  - Two aliases with the same username share one session, which is correct: it's one account.
  - The filename is derived only from a hash, so no alias or username text reaches the
    filesystem: no path traversal, no case-folding collisions, no usernames in filenames.

### Where a command's credentials come from

As semotion-sync:

1. `REMS_USERNAME` and `REMS_PASSWORD`, when both are set, override the saved login for the
   alias the run names (for a machine with no keychain). Read through keyring's
   `EnvironCredential`.
2. Otherwise, the alias's saved login.

- Setting only one of the two env vars is an error, not a silent fall back to the saved login.
- With neither, the command exits non-zero telling the user to run `auth login --team <alias>`.
  It never prompts mid-run (an MFA code excepted).

The login is only *used* on a cookie-cache miss, as today.

### Interaction with `scripts/refresh-registration.ps1`

The script stops prompting for REMS credentials and takes `-Team <alias>`, passed through to
each REMS command.

## Differences from semotion-sync

| | semotion-sync | rems-sync | Why |
|---|---|---|---|
| Alias | Motion team slug, used in URLs | Label (`row`, `row-referee`), `[a-z0-9-]` | REMS URLs don't name the club |
| Login check | Fresh login | Fresh login **with MFA** | REMS requires it |
| Session cache | None | Cookie cache per account (hashed username) | REMS has one; must never cross accounts |

## Verification

`ruff check` and `pytest -q`, green locally and in CI. Tests use an in-memory keychain
(`tests/fake_keyring.py`, copied from semotion-sync) installed by an autouse fixture, which
also clears the env vars and redirects the config file and cookie directory.

| Case | Expected |
|---|---|
| `auth login` with a wrong password | Error; nothing saved; password never printed |
| `auth login` succeeds | Fresh login (not cache); login saved under the alias |
| `auth login` switches alias from A to B, then saving fails | Alias still resolves to A, and A's cache is untouched |
| Two aliases, different accounts | Each run uses only its own account's login and cookie cache |
| Two aliases, same account | They share one cookie cache |
| Env override A → B → A with live caches | Each run uses only the resolved account's cache; A's session survives B's run |
| Username differs only in case or surrounding spaces | Same cache file |
| Alias `../cookies`, `ROW`, `a/b`, empty | Rejected before any file or keychain access |
| Command with no saved login for the alias | Non-zero exit naming `auth login --team <alias>` |
| Both env vars set and login saved | Env vars win |
| Only one env var set | Error, not a fall back to the saved login |
| `--username` / `--password` passed | Rejected as unknown options |
| An alias's password missing from the keychain | `auth status` flags it, exits non-zero |
| Change an alias's username | Old password removed; refused delete reported, new login kept |
| `auth logout` for an unknown alias | Error, non-zero |
| `auth logout`, keychain refuses delete | Login unchanged, error reported |

Acceptance: after one `auth login --team row`, the full registration refresh runs with no
username or password typed (an MFA code may still be asked for).

## Decisions

1. **`auth logout` and the cookie cache.** semotion-sync has no cache, so there is no
   precedent. Logout also deletes the cookie file of the alias's account, so "logged out"
   means the tool can no longer act as that login. If another alias uses the same account,
   its next run simply logs in afresh.
2. **Existing `~/.rems-sync/cookies.json`.** Ignored (it expires within the hour); the first
   run per account logs in afresh.
3. **Breaking change.** Removing `--username`/`--password` and top-level `login` breaks
   existing commands and docs. README, `docs/auth.md`, `docs/deck-eval-upload.md` and the
   script are updated in the implementation PR.

## Open items

None.
