# Agent guide — rems-sync

`rems-sync` is a Python CLI that syncs data between Swimming Canada's REMS / SportLomo
officials registry and Google Sheets, and uploads deck evaluations to REMS. Specific to
Canadian swimming officials — see the org-wide scope note.

## Canonical rules

The cross-repo rules for any SwimBlocks project live in the [`swimblocks/.github`](https://github.com/swimblocks/.github)
standards repo. Read these first:

- [AGENTS.md](https://github.com/swimblocks/.github/blob/main/AGENTS.md) — distilled agent
  guide (work loop, code comments, secrets/PII, etc.)
- [CONTRIBUTING.md](https://github.com/swimblocks/.github/blob/main/CONTRIBUTING.md) —
  long-form house rules
- [development.md](https://github.com/swimblocks/.github/blob/main/docs/development.md) —
  setting up a new machine for SwimBlocks work

Everything below is **repo-specific** — quirks that the canonical guide doesn't cover.

## Repo-specific quirks

- **REMS auth is multi-step.** Login goes through `maint.php` → `Maint-Login.php` →
  `mfa-login` → `mfa-verify-otp` → `logged-in.php` → `club_home.php`. Don't reimplement; use
  [`src/rems_client.py`](src/rems_client.py). Full flow in [docs/auth.md](docs/auth.md).
- **Logins are saved per alias (`--team`), never passed as options.** `auth login --team <alias>`
  saves the username to `config.toml` and the password to the OS keychain; the REMS session
  (1-hour JWT) is also kept in the keychain, per alias *and* account. All of it lives in
  [`src/credentials.py`](src/credentials.py), ported from semotion-sync. Tests get an in-memory
  keychain from an autouse fixture in `tests/conftest.py`; never touch the real one. Design:
  [docs/design/0001-saved-rems-login.md](docs/design/0001-saved-rems-login.md).
- **Dates go to REMS as `d/m/Y`, not `m/d/Y`.** The form uses a flatpickr config that
  parses dates that way; getting this wrong silently records April 11 as November 4. Use
  `to_rems_date_format()` in [`src/utils.py`](src/utils.py).
- **Position names map to credentials via a hand-curated table.** See
  `_POSITION_TO_CREDENTIAL_PREFIX` in [`src/utils.py`](src/utils.py). When you encounter a
  new mismatch (a sheet uses a position name that doesn't match REMS), add a row.
- **Transient HTTP errors retry via `urllib3.util.Retry`** (mounted in `REMSClient.__init__`),
  not a hand-rolled loop. Don't add try/except retry logic to individual calls.
- **Google auth is user OAuth via `gcloud auth application-default login`** for normal CLI
  use. The [terraform/](terraform/) directory provisions a service account for an
  eventual headless / scheduled deployment (epic [#63](https://github.com/swimblocks/rems-sync/issues/63));
  that's not used at runtime today. See [docs/cloud-setup.md](docs/cloud-setup.md).
- **`upload-deck-evals --recheck`** is verify-only by default — no POSTs, just compares
  REMS state to the sheet. `--recheck --interactive` is the mode that can add missing rows
  or fix swapped dates/providers. Read [docs/deck-eval-upload.md](docs/deck-eval-upload.md)
  before touching that flow.

## Running rems-sync

The org rule on
[acting in the author's name](https://github.com/swimblocks/.github/blob/main/AGENTS.md#acting-in-the-authors-name)
applies to rems-sync's own commands. Which of them you may run without asking:

| Command | You may run it |
|---|---|
| `auth status` | Yes. It only reads. |
| `auth login`, `auth logout` | Only when asked. They change the saved login, and `auth login` needs the person to type the password and an MFA code. |
| `refresh-members`, `refresh-member-details`, `refresh-member-credentials` with `--output csv` to a temporary file | Yes, when the task needs the data. See below. Any REMS command may stop for an MFA code once the saved session has expired. |
| The same with `--output gsheet` | Only when asked for that run. It replaces a tab other people read. |
| `upload-members`, `upload-member-details`, `upload-member-credentials` | Only when asked for that run. They replace a tab other people read. |
| `upload-deck-evals --recheck` (without `--interactive`) | Yes. It only compares REMS with the sheet. |
| `upload-deck-evals`, `upload-deck-evals --recheck --interactive`, `add-deck-eval` | Only when asked for that run. They record or change deck evaluations in REMS. |
| `scripts/refresh-registration.ps1` | Only when asked for that run. It runs a Google sign-in and replaces three tabs of the season's registration sheet. |

REMS data is personal information wherever it lands. When a task needs a CSV:

- Write it to a temporary location outside any repository.
- Read only what the task needs from it. Keep names, emails and REMS IDs out of issues,
  pull requests, commits and logs, and out of chat unless the person explicitly asks for
  them; counts and field names are fine.
- Delete it as soon as the task is done with it.

## Where to start reading

- [`README.md`](README.md) — user-facing CLI overview
- [`src/main.py`](src/main.py) — all Click commands live here
- [`src/rems_client.py`](src/rems_client.py) — REMS HTTP client
- [`src/gsheet.py`](src/gsheet.py) — Google Sheets / Drive helpers
- [`tests/`](tests/) — `pytest -q` runs the full suite (~162 tests today)
