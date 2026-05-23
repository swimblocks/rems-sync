# Authentication and MFA

How `REMSClient` logs in to Swimming Canada's REMS / SportLomo platform.

REMS uses a CakePHP-era admin shell (`/maint.php`, `/Maint-Login.php`) wrapping the SportLomo SaaS (`/sportlomo/...`). Authentication is multi-step and surprisingly state-dependent — most of the failure modes that bit us during development came from "almost-right" sequences that REMS handles silently differently from a browser. This document captures the working flow and the gotchas.

## The browser flow

Observed in Chrome Incognito with no cookies:

| Hop | Method | URL | Notes |
|---|---|---|---|
| 1 | GET | `/maint.php` | 200, renders the login form. Sets `PHPSESSID`. |
| 2 | POST | `/Maint-Login.php` | Form-encoded `username` + `password`. 302 → `/sportlomo/users/mfa-login/`. |
| 3 | GET | `/sportlomo/users/mfa-login/` (note trailing slash) | 302 → `/sportlomo/users/mfa-verify-otp`. **Sends the OTP email.** Sets `mfa_token`, `mfa_tokens`. |
| 4 | GET | `/sportlomo/users/mfa-verify-otp` | 200, renders the 6-digit OTP form. |
| 5 | POST | `/sportlomo/users/mfa-verify-otp` | Form fields: `digit_1`…`digit_6` plus any hidden fields from the form HTML (CSRF, etc.). 302 → `/logged-in.php`. Sets/refreshes `mfa_token`, `mfa_tokens`, `mfa_uuid`. |
| 6 | GET | `/logged-in.php` | 302 → `/club_home.php` (regular users) or `/maint.php` (admins). Initialises the SportLomo session and the `Authentication-JWT` cookie. |
| 7 | GET | `/club_home.php` | 200, landing page. |

If REMS recognises the device via valid `mfa_*` cookies, hop 3's redirect goes straight to `/logged-in.php` and hops 4-5 are skipped (no OTP prompt).

## Our implementation

`REMSClient.login()` (in [src/rems_client.py](../src/rems_client.py)) is the only entry point. It tries three strategies in order of cost:

### 1. Cached cookies + probe

The session cookies from the most recent successful login are kept in `~/.rems-sync/cookies.json`. On every login attempt the cache is loaded and we POST a no-op search to `/sportlomo/user/MembershipManagement/members` (the probe). If the response is 200, the session is alive — no network login is needed.

The probe must mirror real auth-requiring calls (POST with the standard XHR/Referer headers), because a GET on that URL returns 200 even with a stale `Authentication-JWT` (it serves the search form HTML). A POST actually exercises the JWT and returns 403 when it has lapsed.

### 2. Walk the redirect chain manually

If the probe fails we do the full login flow. To match the browser flow above without sending extra OTP emails:

- **Clear all cookies first.** Stale `mfa_*` "remember device" cookies from a prior session cause REMS to loop between `/sportlomo/users/mfa-login` and `/mfa-verify-otp` instead of rendering the OTP form. The simplest working answer is to start each fresh login from an empty cookie jar.
- **`GET /maint.php`** to seed `PHPSESSID`.
- **`POST /Maint-Login.php`** with `allow_redirects=False`.
- **Walk the redirect chain one hop at a time.** Each `GET` is `allow_redirects=False` so we can stop on the right page. Auto-following the chain blindly is dangerous: each GET on `/sportlomo/users/mfa-login` that REMS doesn't already recognise as MFA'd triggers a fresh OTP email. An earlier version of this code accidentally sent ~10 emails per attempt.
- Stop when we hit either (a) `/sportlomo/users/mfa-verify-otp` returning **200** — the OTP form has been rendered, prompt the user — or (b) any other 200, meaning we're authenticated (probe to confirm).

### 3. OTP submission

When we land on the OTP form, `_do_mfa` does the rest:

- Parse the form HTML with BeautifulSoup, pull every `<input type="hidden">` (including any CSRF token). Without these REMS rejects the POST silently — the redirect goes to `/sportlomo/users/mfa-login` instead of `/logged-in.php`.
- Prompt the user for the 6-digit code via `mfa_callback` (the CLI uses an interactive `click.prompt`).
- POST `/sportlomo/users/mfa-verify-otp` with `digit_1`…`digit_6`, the hidden fields, and a `Referer` of the form URL.
- On 302, walk the post-OTP chain (`/logged-in.php` → `/club_home.php`) and probe to confirm.

## Cookie cache

After a successful login, `_save_cookies()` writes the entire `requests.Session().cookies` jar to `~/.rems-sync/cookies.json` as a flat name → value JSON dict. Future runs load these via `_load_cookies()` and skip the entire login dance when the probe still passes.

## Auto-reauth on 403

The `Authentication-JWT` cookie has a 1-hour `Max-Age`, so a long-running interactive batch can outlive it mid-call. `REMSClient._request()` wraps the data-fetching/posting methods: on a 403 response, it clears the cookies and cache, runs a fresh full login (which will prompt for an OTP if needed), and retries the original request once. The `upload-deck-evals` batch flow can therefore survive a JWT expiry without losing the row's progress.

## Cookies REMS uses

| Cookie | Lifetime | Set by | Purpose |
|---|---|---|---|
| `PHPSESSID` | session | Almost any GET to a REMS page | PHP session id. Tied to a single login attempt; carrying a stale one from a previous session breaks logins (REMS bounces back to the form). |
| `mfa_token`, `mfa_tokens` | days/weeks (server-controlled) | `/sportlomo/users/mfa-login/` first hop | Used by REMS to determine whether the device has already passed MFA recently. Cached in our cookie file. |
| `mfa_uuid` | days/weeks | Set on successful OTP POST | "Known device" id. Honoring this lets future logins skip OTP. |
| `Authentication-JWT` | 1 hour | Every authenticated sportlomo response refreshes it | JWT used by sportlomo endpoints. Slides forward on activity; lapses on idle. |

## Logout

`logout()` GETs `/Maint-Logout.php`, clears the session jar, and removes `~/.rems-sync/cookies.json`. After logout the next command will need a fresh OTP.

## Failure modes seen during development

For future reference — each of these was tracked down to one of the issues above:

- **`MFA verification failed: Unexpected status code on MFA redirect`** — strict check expected the chain to redirect through one specific URL. REMS varies the chain by user role; relaxed to walk-and-probe.
- **Redirect loop between `/sportlomo/users/mfa-login` and `/mfa-verify-otp`** after OTP submission — caused by carrying stale `mfa_*` cookies into a fresh login.
- **Email storm (~10 OTP codes)** — caused by `allow_redirects=True` on the POST or follow-up GETs; each GET on `/mfa-login` re-sends the OTP.
- **`probe says not authenticated` after a successful-looking OTP POST** — the OTP form has hidden CSRF inputs that we weren't sending; without them REMS treats the POST as invalid and redirects to `/mfa-login` instead of `/logged-in.php`.
- **`403 Forbidden` mid-batch** — JWT lapsed during a long interactive run; auto-reauth handles it.

## Open question

When the `Authentication-JWT` has lapsed but the `mfa_*` cookies are still valid server-side, we currently re-run the full login. Whether a cheaper "refresh JWT" endpoint exists is unknown — could save an OTP in long-running sessions. Tracked in code comments.
