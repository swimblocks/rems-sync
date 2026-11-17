# rems-sync

[![ci](https://github.com/swimblocks/rems-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/swimblocks/rems-sync/actions/workflows/ci.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A Python CLI that syncs Swimming Canada's **REMS / SportLomo** officials registry with Google
Sheets. It pulls your club's members, their details and credentials out of REMS into a
season's registration sheet, and records deck evaluations from a meet's roster sheet in REMS.

- Log in to REMS, with its emailed one-time code, and reuse the session for an hour.
- Refresh members, member details and credentials, to CSV or a sheet tab.
- Record deck evaluations one at a time, or a whole meet's from its roster sheet, never
  twice; and check a meet or season's sheets against REMS.

## Quick start

You need Python 3.12+, the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install), a
REMS login for your club's officials, and a sheet shared with the `rems-sync-sa` service
account.

```bash
git clone https://github.com/swimblocks/rems-sync.git
cd rems-sync
python -m venv .venv && .venv/Scripts/activate    # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m src.main --help
```

New here? Follow [Your first refresh](docs/tutorials/first-refresh.md).

## Documentation

[docs/](docs/README.md), sorted by what each page is for:

- **Tutorial:** [your first refresh](docs/tutorials/first-refresh.md).
- **How-to:** [refresh a season's registration sheet](docs/how-to/refresh-registration-sheet.md),
  [upload a meet's deck evaluations](docs/how-to/upload-deck-evals.md),
  [record one deck evaluation](docs/how-to/add-a-deck-eval.md),
  [set up Google access](docs/how-to/set-up-google-access.md).
- **Reference:** [CLI](docs/reference/cli.md), [sheets and CSV files](docs/reference/sheets.md),
  [REMS](docs/reference/rems.md).
- **Explanation:** [logging in to REMS](docs/explanation/rems-login.md),
  [how deck evaluations are recorded](docs/explanation/deck-eval-upload.md),
  [Google access](docs/explanation/google-access.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md). One issue → one branch
(`{issue-number}-{slug}`) → one PR.

## License

[MIT](LICENSE) © 2026 Gavin Bee.
