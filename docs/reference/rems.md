# REMS

The REMS / SportLomo URLs, cookies and values rems-sync relies on. All URLs are relative to
`https://swimming.canada.sportsmanager.ie` (`REMSClient.BASE_URL`). Why login works this way is
in [Logging in to REMS](../explanation/rems-login.md).

## Login

As a browser does it, from no cookies:

| Hop | Method | URL | What happens |
|---|---|---|---|
| 1 | GET | `/maint.php` | 200, the sign-in form. Sets `PHPSESSID`. |
| 2 | POST | `/Maint-Login.php` | Form fields `username`, `password`. 302 to `/sportlomo/users/mfa-login/`. Wrong credentials redirect back to `/maint.php`. |
| 3 | GET | `/sportlomo/users/mfa-login/` (trailing slash) | 302 to `/sportlomo/users/mfa-verify-otp`. **Emails the code.** Sets `mfa_token`, `mfa_tokens`. A recognised device is sent straight to `/logged-in.php`, skipping hops 4 and 5. |
| 4 | GET | `/sportlomo/users/mfa-verify-otp` | 200, the six-digit code form. |
| 5 | POST | `/sportlomo/users/mfa-verify-otp` | Fields `digit_1` … `digit_6` plus the form's hidden inputs. 302 to `/logged-in.php`. Sets `mfa_token`, `mfa_tokens`, `mfa_uuid`. |
| 6 | GET | `/logged-in.php` | 302 to `/club_home.php` (or `/maint.php` for admins). Sets `Authentication-JWT`. |
| 7 | GET | `/club_home.php` | 200, the landing page. |

Logout: GET `/Maint-Logout.php`.

**Probe** (is the session live?): POST `/sportlomo/user/MembershipManagement/members` with
`FilterForm[primary_identifier]=` and `limit=1`, headers `X-Requested-With: XMLHttpRequest` and
`Referer` set to the same URL, redirects off. Live: 200, or a redirect that isn't to
`Maint-Login` or an `mfa` page.

### Cookies

| Cookie | Lifetime | Set by | Purpose |
|---|---|---|---|
| `PHPSESSID` | Session | Most REMS pages | PHP session for one login attempt. A stale one makes REMS return to the sign-in form. |
| `mfa_token`, `mfa_tokens` | Days to weeks (set by REMS) | Hop 3 | Whether this device has passed the code check recently. |
| `mfa_uuid` | Days to weeks | Hop 5 | The known-device ID that lets later logins skip the code. |
| `Authentication-JWT` | 1 hour, renewed on use | Hop 6 and every SportLomo response | Authorises SportLomo calls. A call made after it lapses returns 403. |

## Members and credentials

| Use | Method | URL | Notes |
|---|---|---|---|
| Members export (`refresh-members`) | GET | `/sportlomo/user/membership-management/member-export?FilterForm[season_id]={season_id}&FilterForm[group_id]=50113` | REMS's own CSV, `Accept: text/csv`. |
| REMS ID → `member_season_id` | POST | `/sportlomo/user/MembershipManagement/members` | Filtered by `FilterForm[primary_identifier]`; the ID is parsed from the result row's actions. |
| Name search | POST | `/sportlomo/user/MembershipManagement/members` | Used by `add-deck-eval` without `--rems-id`. |
| `member_id` and REMS ID | GET | `/sportlomo/user/membership-management/member-detail/{member_season_id}` | `member_id` is parsed from any link to `member-credentials-details/{member_season_id}/{member_id}`. |
| A member's credentials | POST | `/sportlomo/user/credentials/member-credentials-details/{member_season_id}/{member_id}?page={n}` | Paginated, `limit` per page (100). |
| One credential | GET | `/sportlomo/user/credentials/view-from-member-profile/{member_season_id}/{member_id}/{credential_id}` | Provider, meet (`provider_identifier`), session (`description`), dates, state. |
| Edit a credential | POST | same URL as above | The whole form is sent back with changed fields. Success is a 302. Used by `upload-deck-evals --recheck --interactive` to fix swapped dates. |
| Credentials available for a type | GET, then POST | `/sportlomo/user/credentials/add-member-credential/{member_season_id}/{member_id}`, then `/sportlomo/user/credentials/update-credential-form` | Choosing a type (Deck Evaluation is type 127) posts the form with `nextStep=credential-name`; the reply is JSON `{credentials: [{id, name, ...}]}`. |
| Add a credential | POST | `/sportlomo/user/credentials/add-member-credential/{member_season_id}/{member_id}` | Multipart form. Success is a 302 to `member-credentials-details/...`. `start_date` must be **`d/m/Y`**: the form's date picker reads it that way, and `m/d/Y` silently records the wrong date. |

## Values

- **REMS ID:** `SC` followed by at least eight digits (`validate_rems_id`). Other values in a
  REMS ID column are skipped.
- **Season ID:** REMS numbers seasons. `parse_season_to_id` maps a season's start year to it:

  | Start year | Season ID |
  |---|---|
  | 2024 and later | 231 + (year − 2024) |
  | 2022, 2023 | 224 + (year − 2022) |
  | Before 2022 | 226 + (year − 2017) |

- **Dates REMS shows** are `d/m/Y`, and dates sent to it must be too
  (`to_rems_date_format`).
