# Saved logins

Why REMS logins are saved per alias in the OS keychain, and how the pieces fit. Where each
piece is kept: [Configuration](../reference/configuration.md). The decision itself:
[design 0001](../design/0001-saved-rems-login.md).

## The problem it solves

REMS logins last about an hour, so most runs need the password again. Passing it as a flag
left it in shell history and the process list; keeping it in environment variables left it in
the terminal all day. And there was one session cache, so only one REMS account could be used,
though one person may hold several: one per club, or per club and role.

## Aliases

A login is saved under an alias you choose, such as `row`, or `row-referee` for a second login
at the same club. Every REMS command names one with `--team`. It is required even when only one
login is saved: if it defaulted to the only login, the same command would quietly switch
account once a second login was added, and commands such as `upload-deck-evals` write to REMS
as that account.

## Where things are kept

- **The username** goes in `config.toml`. It isn't secret, and you can read it there.
- **The password** goes in the OS keychain, which the OS protects with your sign-in.
- **The session** (the REMS cookies) goes in the keychain too, in an entry of its own. A live
  session is as good as a password for its hour, so it doesn't belong in a plain file.

This is the same layout as semotion-sync, plus the session, which semotion-sync doesn't need.

## A session never crosses accounts

Each session is filed under its alias *and* its account. If `REMS_USERNAME` and
`REMS_PASSWORD` override alias `row` with a different account, that run reads and writes the
other account's session, never `row`'s own; when the override is removed, `row`'s session is
still there. Sessions are kept under a different service name from passwords
(`rems-sync-session/…` rather than `rems-sync/…`), so no alias can make the two collide.

## The session is only a cache

Losing a session costs one emailed code, nothing more. So the session is always the first
thing to go, and the login is never left half-removed:

- `auth logout` removes the session, then the password, then the username. If the keychain
  refuses to remove the session, nothing is removed. If it then refuses the password, the
  login is still whole, and the error says so.
- A session the keychain refuses to save is a warning, not a failed command. The usual cause
  on Windows is the 2,560-byte limit per entry.

## Nothing is saved until it works

`auth login` always logs in afresh, ignoring any saved session, so the password is checked by
REMS before it is kept: a mistyped password is never saved. The new session is held in memory
and written only after the login itself is saved, so a failed save can't leave a session
behind for a login that doesn't exist.

## Overriding for one run

`REMS_USERNAME` and `REMS_PASSWORD` together replace the saved login, which suits a one-off
run as another account, or a machine with no keychain. One without the other is an error
rather than a quiet fall back to the saved login, so a half-set override can't act as the
wrong account.
