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
  `mfa-login` → `mfa-verify-otp` → `logged-in.php` → `club_home.php`. Cookies cache to
  `~/.rems-sync/cookies.json` (1-hour JWT). Don't reimplement; use [`src/rems_client.py`](src/rems_client.py).
  Why: [docs/explanation/rems-login.md](docs/explanation/rems-login.md).
- **Dates go to REMS as `d/m/Y`, not `m/d/Y`.** The form uses a flatpickr config that
  parses dates that way; getting this wrong silently records April 11 as November 4. Use
  `to_rems_date_format()` in [`src/utils.py`](src/utils.py).
- **Position names map to credentials via a hand-curated table.** See
  `_POSITION_TO_CREDENTIAL_PREFIX` in [`src/utils.py`](src/utils.py). When you encounter a
  new mismatch (a sheet uses a position name that doesn't match REMS), add a row.
- **Transient HTTP errors retry via `urllib3.util.Retry`** (mounted in `REMSClient.__init__`),
  not a hand-rolled loop. Don't add try/except retry logic to individual calls.
- **Google auth is Application Default Credentials** from `gcloud auth application-default
  login`, normally impersonating the `rems-sync-sa` service account that [terraform/](terraform/)
  creates; rems-sync holds no Google credentials itself. Running unattended in the cloud is
  epic [#63](https://github.com/swimblocks/rems-sync/issues/63). See
  [docs/explanation/google-access.md](docs/explanation/google-access.md).
- **`upload-deck-evals --recheck`** is verify-only by default — no POSTs, just compares
  REMS state to the sheet. `--recheck --interactive` is the mode that can add missing rows
  or fix swapped dates/providers. Read [docs/explanation/deck-eval-upload.md](docs/explanation/deck-eval-upload.md)
  before touching that flow.

## Documentation

[`docs/`](docs/), indexed in [`docs/README.md`](docs/README.md), is sorted by what each page
is for ([Diátaxis](https://diataxis.fr/)). **Keep it true:** a PR updates, in the same PR, every
page its change makes wrong.

- **Tutorials** ([`docs/tutorials/`](docs/tutorials/)): a newcomer's first run. A PR that
  changes setup, login or the commands it uses updates it.
- **How-to guides** ([`docs/how-to/`](docs/how-to/)): step by step, for a goal: the season
  refresh, deck evaluations, Google access, the cloud project; contributor guides under
  `how-to/contributor/`. A PR that changes a step updates its guide.
- **Reference** ([`docs/reference/`](docs/reference/)): the facts: the CLI (every command,
  flag, default and exit code), sheets and CSV files (tabs, columns, roster layout, position
  names), REMS (URLs, cookies, values), Terraform, code layout. A PR that changes one of those
  facts updates its page.
- **Explanation** ([`docs/explanation/`](docs/explanation/)): why: REMS login, deck-eval
  recording, Google access. A PR that changes the design of one updates its page.
- **Design records** ([`docs/design/`](docs/design/), indexed in its README): the reasoning for
  a piece of work, written before it is built.

Docs never carry real people's names, emails or REMS IDs, nor sheet or project IDs; use
placeholders such as `<sheet_id>`.

## Where to start reading

- [`docs/README.md`](docs/README.md) — the documentation index
- [`src/main.py`](src/main.py) — all Click commands live here
- [`src/rems_client.py`](src/rems_client.py) — REMS HTTP client
- [`src/gsheet.py`](src/gsheet.py) — Google Sheets / Drive helpers
- [`tests/`](tests/) — `pytest -q` runs the full suite (~102 tests today)
