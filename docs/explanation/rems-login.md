# Logging in to REMS

How and why `REMSClient` logs in to Swimming Canada's REMS / SportLomo the way it does. The
hop-by-hop URLs and the cookies are in the [REMS reference](../reference/rems.md#login).

REMS is an older PHP admin shell (`/maint.php`, `/Maint-Login.php`) wrapped around the
SportLomo service (`/sportlomo/...`). Logging in takes several steps, and REMS reacts to
sequences that are almost, but not quite, what a browser does by failing quietly in a different
way. Most of what follows exists because of one of those failures.

## Cheapest first

`REMSClient.login()` in [src/rems_client.py](../../src/rems_client.py) is the only way in. It
tries, in order of cost:

1. **The cached session.** The cookies from the last successful login are loaded, and a probe
   checks they still work. If they do, no login happens at all.
2. **A full login without a code.** If REMS still recognises this device from its `mfa_*`
   cookies, it skips the one-time code.
3. **A full login with a code.** REMS emails a six-digit code and the CLI asks for it.

## Why the probe is a POST

The probe is a no-op member search, sent as a POST with the same headers as the real calls. A
GET on the same URL returns 200 even when the session has lapsed, because it just serves the
search form. A POST needs the `Authentication-JWT` cookie and returns 403 once it has expired,
so it tells live from stale.

## Why the redirects are walked one at a time

Each GET of `/sportlomo/users/mfa-login/` on an unrecognised device sends a new code by email.
Following redirects automatically made an early version of this code send about ten codes per
login. So every request is made with redirects off, and the client follows the chain itself,
one hop at a time, stopping at either:

- the code form (`/sportlomo/users/mfa-verify-otp` returning 200): ask for the code; or
- any other page that returns 200: probe to confirm the session is live.

## Why a fresh login starts with no cookies

Leftover `mfa_*` cookies from an earlier session make REMS bounce between `mfa-login` and
`mfa-verify-otp` instead of showing the code form. Starting each full login from an empty
cookie jar avoids this.

## Why the code form's hidden fields are sent back

The code form carries hidden inputs, including a CSRF token. Without them REMS rejects the
code silently: it redirects back to `mfa-login` rather than on to `/logged-in.php`. The client
copies every hidden input from the form into its POST, so it needn't know their names.

## The session cache

After a successful login the whole cookie jar is handed, as a flat name → value object, to the
client's session store, and loaded from it at the start of the next login. `logout()` clears it.

The CLI's store, `KeyringSessionStore` in [src/credentials.py](../../src/credentials.py), keeps
it in the OS keychain under the alias and account, so a session is never used by another
([Saved logins](saved-logins.md)). A store that refuses a write, such as Windows Credential
Manager over its 2,560-byte limit, costs only a warning: the run carries on, and the next one
logs in afresh. `auth login` uses an in-memory `MemorySessionStore`, and keeps the session only
once the login itself is saved.

## Re-login when the session expires mid-run

The `Authentication-JWT` cookie lasts an hour, and it is renewed while the session is in use.
A long interactive run can still outlast it. Every data call goes through
`REMSClient._request()`: on a 403 it clears the cookies and the cache, logs in afresh (asking
for a code if REMS wants one), and retries the call once. A batch such as `upload-deck-evals`
therefore survives an expiry without losing its place.

## Failures seen during development

Each traced back to one of the points above:

| Symptom | Cause |
|---|---|
| `MFA verification failed: Unexpected status code on MFA redirect` | The code expected the chain to pass through one particular URL; REMS varies the chain by role. Fixed by walking the chain and probing. |
| A redirect loop between `mfa-login` and `mfa-verify-otp` after the code is sent | Stale `mfa_*` cookies carried into a fresh login. |
| About ten code emails per login | Redirects followed automatically; each GET of `mfa-login` re-sends the code. |
| `probe says not authenticated` after the code was accepted | The form's hidden CSRF inputs weren't sent. |
| `403 Forbidden` part-way through a batch | The JWT expired; the re-login above handles it. |
| `Login: landed at .../maint.php ... but probe says not authenticated` | REMS rejected the username or password and returned to its sign-in page. |

## Open question

When the JWT has lapsed but the `mfa_*` cookies are still valid, the client runs a full login.
Whether REMS has a cheaper way to renew the JWT is unknown; one would save a code in long
sessions.
