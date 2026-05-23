# Deck Evaluation Upload

How the `add-deck-eval` and `upload-deck-evals` commands write Swimming Canada deck evaluations to REMS from either a single CLI invocation or a meet's Google Sheet.

The user-facing docs (commands, flags, sheet layout) live in [README.md](../README.md). This document covers the underlying flow, the REMS endpoints involved, and the non-obvious behaviors.

## REMS endpoints

| Step | Method | URL | Notes |
|---|---|---|---|
| Login | `POST` | `/Maint-Login.php` | Form-encoded `username` + `password`. With a valid `mfa_*` cookie REMS skips OTP. |
| MFA OTP | `POST` | `/sportlomo/users/mfa-verify-otp` | Six `digit_N` form fields. Only when REMS doesn't honor the device. |
| Sportlomo session init | `GET` | `/logged-in.php` | Visited as part of the login redirect chain; sets the `Authentication-JWT` cookie. |
| Probe (is the session still good?) | `POST` | `/sportlomo/user/MembershipManagement/members` | Empty filter form. 200 ⇒ authenticated; 403 ⇒ JWT lapsed. |
| Resolve REMS ID → `member_season_id` | `POST` | `/sportlomo/user/MembershipManagement/members` | Filter by `FilterForm[primary_identifier]`. Parses the actions cell of the result row. |
| Resolve `member_id` | `GET` | `/sportlomo/user/membership-management/member-detail/{msid}` | Parses the `member-credentials-details/{msid}/{mid}` link out of the member detail page. |
| Existing credentials | `POST` | `/sportlomo/user/credentials/member-credentials-details/{msid}/{mid}` | Paginated. Includes `actions` URLs to each individual credential. |
| Existing credential detail | `GET` | `/sportlomo/user/credentials/view-from-member-profile/{msid}/{mid}/{cid}` | Used to compare an existing credential's meet + session against the one being added. |
| Available credentials for a type | `GET` then `POST` | `/sportlomo/user/credentials/add-member-credential/{msid}/{mid}` + `/sportlomo/user/credentials/update-credential-form` | The form has a Type dropdown (Deck Evaluation = type 127). Selecting a type triggers an XHR to `update-credential-form` with the full form payload and `nextStep=credential-name`, which returns JSON `{credentials: [{id, name, ...}]}`. |
| Add credential | `POST` | `/sportlomo/user/credentials/add-member-credential/{msid}/{mid}` | Multipart form. Success = HTTP 302 to `member-credentials-details/...`. |

## Login flow

The login routine in `REMSClient.login()` tries strategies in order of cost:

1. **Cookie cache hit + probe.** Load `~/.rems-sync/cookies.json`, POST the probe endpoint. If 200, return immediately — no network login.
2. **Known-device login.** Drop everything except the `mfa_*` cookies (a stale `PHPSESSID` causes REMS to bounce the request to the login page), then POST `/Maint-Login.php`. REMS recognises the device and the redirect chain proceeds:
   `Maint-Login → mfa-login/ → logged-in.php → /club_home.php`. After the chain the probe is re-run to confirm.
3. **Full MFA.** Only if REMS routes us to `mfa-verify-otp` does the tool prompt for an OTP.

If any authenticated call returns 403 mid-batch (the `Authentication-JWT` cookie has a 1-hour `Max-Age` and can lapse during long interactive sessions), `REMSClient._request` triggers a single full re-login and retries the original call.

## Per-row flow in `upload-deck-evals`

```
read Positions tab (DataFrame)
read Grid tab raw rows → {session_id: "YYYY-MM-DD"} via header parsing
read Meet tab raw rows → meet name + start date (for year resolution)
read Officials tab → {Name: REMS ID}
login()
for each pending row:
    look up REMS ID via the Officials map
    REMSClient.get_member_season_id(rems_id) → member_season_id
    REMSClient.get_member_details(...)        → member_id
    REMSClient.get_member_credentials(...)    → existing credentials for this position
    REMSClient.get_add_credential_form_options → available credentials (with credential_id)
    if any existing matching credential has the same meet + session:
        → AlreadyRecordedError (idempotent success: tick the cell, no POST)
    elif count == max_for_position:
        → ClickException: max reached for a different meet, resolve in REMS
    else:
        if interactive: prompt y/n/q
        REMSClient.add_member_credential(...)  → POST, expects 302
        tick "Deck Eval Recorded?" = TRUE in the sheet
```

`_resolve_deck_eval_credential` in `src/main.py` encapsulates the decision logic and is unit-tested.

## Sheet layout quirks

The real Cunningham Classic 2026 / Dean Boles 2026 sheets revealed these layouts (others may differ):

- **Positions tab** column header is on row 1. The tab name in the real sheets is `Positions` (capital P); the CLI default reflects that.
- **Grid tab** has a multi-line title row, a blank row, then a row whose cells are multi-line strings like `"Session 1\nFriday, Apr 10\nSenior Briefing: 3:55 pm\n..."`. The parser locates the header row by looking for any `"Session N"` cell.
- **Grid year** is not in the cell text. We take it from the Meet tab's `Meet Start Date`, falling back to the season end-year.
- **Meet tab** is a flat key/value table with a blank header row. We accept either `Meet Name` or `Name` as the label.
- **Officials tab** has merged-header chrome on rows 1–2. The real header (`Name`, `REMS ID`, ...) is on row 3 — the parser finds it by content rather than position.

## Position-name normalization

The Positions tab uses friendly names that don't always match REMS credential names. Known mismatches live in `_POSITION_TO_CREDENTIAL_PREFIX` in [src/utils.py](../src/utils.py):

| Positions tab | REMS credential prefix |
|---|---|
| Chief Timer | Chief Timekeeper |
| Admin Desk | Administration Desk |
| Stroke Judge | Judge of Stroke |
| Session Referee | Referee |
| Timer | Introduction to Swimming Officiating |

`deck_eval_credential_label("Chief Timer", 2)` → `"Chief Timekeeper Evaluation #2"`. Add new mappings as you encounter them.

## Duplicate detection

A position can only be evaluated once per meet, so dedup matches on **position prefix + start_date**. The single source of truth is `find_existing_deck_eval_in_dates(credentials, position, dates)` in [src/utils.py](../src/utils.py): it returns the first existing "Deck Evaluation" credential of the right prefix whose `start_date` (parsed from REMS's d/m/Y display format) is in the given ISO date set, or `None`.

`_resolve_deck_eval_credential` calls this helper unconditionally — independent of `--recheck`, `--interactive`, or eval count. If it returns a credential, `AlreadyRecordedError` fires (idempotent success). If it returns None and the official is at the form's max (#1 + #2) for the position with no date matches, a distinct `ClickException` asks the user to resolve manually in REMS (the form allows no #3).

Both commands feed the helper the same way but with different date sets:
- `upload-deck-evals` passes `set(session_dates.values())` — all of the meet's sessions per the Grid tab. The "no two evals same position same meet" rule is fully enforced.
- `add-deck-eval` defaults to `default_meet_dates_for(--date)`, which is the most recent Wednesday on/before `--date` through the next Sunday on/after `--date`. For meets that fall outside this bracket, pass `--meet-dates 2026-04-10,2026-04-11,2026-04-12` to override.

`provider_identifier` and `description` are ignored on purpose — manually-entered REMS evaluations may have arbitrary meet-name strings, but the dates are reliable.

## Open questions

These came up during build-out and are tracked in code comments / the cookie-refresh investigation:

- **JWT-only refresh without MFA**: when only the JWT has lapsed but the `mfa_*` cookies and `PHPSESSID` are still good, the known-device login path covers it. Whether a cheaper refresh endpoint exists is unknown.
