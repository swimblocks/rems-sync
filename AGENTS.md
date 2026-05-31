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
  Full flow in [docs/auth.md](docs/auth.md).
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

## Where to start reading

- [`README.md`](README.md) — user-facing CLI overview
- [`src/main.py`](src/main.py) — all Click commands live here
- [`src/rems_client.py`](src/rems_client.py) — REMS HTTP client
- [`src/gsheet.py`](src/gsheet.py) — Google Sheets / Drive helpers
- [`tests/`](tests/) — `pytest -q` runs the full suite (~98 tests today)
