# CLI

Every command is run as `python -m src.main <command>` from the repo root, with the virtual
environment active. `--help` on any command prints its flags.

| Command | Does |
|---|---|
| [`login`](#login) | Logs in to REMS and saves the session. |
| [`refresh-members`](#refresh-members) | Exports a season's members from REMS. |
| [`refresh-member-details`](#refresh-member-details) | Looks up each member's REMS identifiers. |
| [`refresh-member-credentials`](#refresh-member-credentials) | Exports each member's credentials. |
| [`upload-members`, `upload-member-details`, `upload-member-credentials`](#upload-commands) | Writes a CSV to a sheet tab. |
| [`add-deck-eval`](#add-deck-eval) | Records one deck evaluation in REMS. |
| [`upload-deck-evals`](#upload-deck-evals) | Records a meet's deck evaluations from its roster sheet. |

## REMS login

Commands that talk to REMS take:

| Flag | Environment variable | Meaning |
|---|---|---|
| `--username` | `REMS_USERNAME` | REMS username. |
| `--password` | `REMS_PASSWORD` | REMS password. |

Prefer the environment variables, set once per terminal, so the password isn't in your shell
history or on screen:

```powershell
$env:REMS_USERNAME = "<username>"
$env:REMS_PASSWORD = Read-Host "REMS password"
```

```bash
export REMS_USERNAME="<username>"
read -rs -p "REMS password: " REMS_PASSWORD; export REMS_PASSWORD
```

Both may be left out while the saved session is still live. When a login is needed, REMS may
email a six-digit code, and the command asks for it (`Please enter the MFA code`). The session
is saved to `~/.rems-sync/cookies.json`. See [Logging in to REMS](../explanation/rems-login.md).

## Seasons

`--season` is a year (`2025`) or a range (`2025-2026`); the start year picks the REMS season
([season IDs](rems.md#values)).

## Output

The refresh commands write to one of:

| Flags | Writes |
|---|---|
| `--output csv --output-file <path>` (default output) | A CSV file. |
| `--output gsheet --sheet-id <id> [--sheet-name <tab>]` | A sheet tab, replaced whole ([how](sheets.md#writing-a-tab)). |

The columns are in [Sheets and CSV files](sheets.md#the-registration-tabs).

## `login`

Logs in (using the saved session if it is live) and saves the session. Flags: the
[REMS login](#rems-login) flags.

## `refresh-members`

Downloads REMS's members export for a season.

| Flag | Default | |
|---|---|---|
| `--season` | required | |
| [Output](#output) flags | `--output csv` | Tab: `REMS Members`. |
| [REMS login](#rems-login) flags | | |

## `refresh-member-details`

```
refresh-member-details <input_file> --season <season> [output flags]
```

For each REMS ID in `<input_file>` (normally the members CSV; [which column](sheets.md#input-csv-files)),
finds the member in the season and records `member_id` and `member_season_id`. One request per
member, so this takes a while for a large club. Members not found in the season are reported
and left out.

| Flag | Default | |
|---|---|---|
| `--season` | required | |
| [Output](#output) flags | `--output csv` | Tab: `REMS Member Details`. |
| [REMS login](#rems-login) flags | | |

## `refresh-member-credentials`

```
refresh-member-credentials <member_details_file> [output flags]
```

For each row of the member details CSV, lists all the member's credentials.

| Flag | Default | |
|---|---|---|
| [Output](#output) flags | `--output csv` | Tab: `REMS Member Credentials`. |
| [REMS login](#rems-login) flags | | |

## Upload commands

```
upload-members            --input-file <csv> --sheet-id <id> [--sheet-name <tab>]
upload-member-details     --input-file <csv> --sheet-id <id> [--sheet-name <tab>]
upload-member-credentials --input-file <csv> --sheet-id <id> [--sheet-name <tab>]
```

Write a CSV to a sheet tab, replacing it ([how](sheets.md#writing-a-tab)). The default tabs are
`REMS Members`, `REMS Member Details` and `REMS Member Credentials`. They don't contact REMS.

## `add-deck-eval`

Records one deck evaluation. How it decides #1 or #2, and when it refuses: [How deck
evaluations are recorded](../explanation/deck-eval-upload.md).

| Flag | | |
|---|---|---|
| `--season` | required | e.g. `2025-2026`. |
| `--official-name` | required | The official's full name. |
| `--rems-id` | optional | The official's REMS ID; found by ID instead of by name. Recommended. |
| `--position` | required | e.g. `Inspector of Turns`; friendly names are [translated](sheets.md#position-names). |
| `--provider` | required | The evaluator's full name. |
| `--meet` | required | The meet's name. |
| `--date` | required | The session's date, `YYYY-MM-DD` or `DD/MM/YYYY` (day first). |
| `--description` | required | Free text, e.g. `Session 6`. |
| `--meet-dates` | optional | Every date of the meet, comma-separated. Default: Wednesday on or before `--date` to Sunday on or after it. |
| `--dry-run` | | Does every read but doesn't record anything. |
| [REMS login](#rems-login) flags | | |

Already recorded for this meet: says so and exits 0.

## `upload-deck-evals`

Records every pending deck evaluation in a meet's roster sheet and ticks **Deck Eval
Recorded?** for each. Sheet layout: [the meet roster sheet](sheets.md#the-meet-roster-sheet).

| Flag | Default | |
|---|---|---|
| `--season` | required | |
| `--sheet-id` | none | The roster sheet. Without it, meets are found in Drive ([how](../explanation/deck-eval-upload.md#without---sheet-id)). |
| `--season-folder-id` | the ROW shared drive | Where to look for season folders, without `--sheet-id`. |
| `--roster-name-substring` | `Officials Roster` | How to recognise a roster sheet in a meet folder. |
| `--positions-tab` | `Positions` | |
| `--grid-tab` | `Grid` | |
| `--meet-tab` | `Meet` | |
| `--officials-tab` | `Officials` | |
| `--session-col` | `Session` | The Positions column naming the session. |
| `--rems-club` | `ROW` | Only rows for this club. |
| `--meet-name` | from the Meet tab | |
| `--interactive` | off | Asks `y/n/q` before each evaluation (Enter skips, `q` stops). Without `--sheet-id`, asks which meet. |
| `--recheck` | off | Checks all passed rows against REMS, including those marked recorded ([what it reports](../explanation/deck-eval-upload.md#recheck-is-the-sheet-right)). Without `--interactive`, leaves REMS unchanged but may add missing Provider/Recorded? columns to the sheet; add `--dry-run` to prevent sheet writes too. With `--interactive`, offers to fix what it finds. |
| `--dry-run` | off | Does every read but doesn't record anything or write to the sheet. |
| [REMS login](#rems-login) flags | | |

## Exit codes

`0` on success. `1` on most errors, with a message starting `Error:`, or a Python traceback
for an unexpected one such as a failed REMS login; `2` for a usage error such as a missing
required flag. Some errors are only printed, and the command still exits 0:

- a refresh with `--output csv` but no `--output-file`, or `--output gsheet` but no `--sheet-id`;
- `refresh-member-details` when its input has no REMS ID column or can't be read;
- the upload commands when the sheet write fails (the message starts `Error uploading`).
