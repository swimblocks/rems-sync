# CLI

Every command is run as `python -m src.main <command>` from the repo root, with the virtual
environment active. `--help` on any command prints its flags.

| Command | Does |
|---|---|
| [`auth login`, `auth status`, `auth logout`](#auth) | Save, list and remove REMS logins. |
| [`refresh-members`](#refresh-members) | Exports a season's members from REMS. |
| [`refresh-member-details`](#refresh-member-details) | Looks up each member's REMS identifiers. |
| [`refresh-member-credentials`](#refresh-member-credentials) | Exports each member's credentials. |
| [`upload-members`, `upload-member-details`, `upload-member-credentials`](#upload-commands) | Writes a CSV to a sheet tab. |
| [`add-deck-eval`](#add-deck-eval) | Records one deck evaluation in REMS. |
| [`upload-deck-evals`](#upload-deck-evals) | Records a meet's deck evaluations from its roster sheet. |

## REMS login

Every command that talks to REMS takes `--team <alias>` (required): the saved login to use.
An alias is any label you chose when saving it with [`auth login`](#auth), such as `row`, or
`row-referee` if you hold several REMS logins.

| Environment variable | Meaning |
|---|---|
| `REMS_USERNAME` and `REMS_PASSWORD` | When **both** are set, used instead of the saved login, for that run. Setting only one is an error. |

When REMS needs a fresh login, it may email a six-digit code, and the command asks for it
(`Please enter the MFA code`). The session is saved in the OS keychain under the alias and
account, and reused while it lasts (about an hour). Where everything is kept:
[Configuration](configuration.md). Why: [Saved logins](../explanation/saved-logins.md).

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

### Member output schemas

`refresh-members` (CSV or gsheet output) and `upload-members` accept an optional contract:

| Flag | Default | Meaning |
|---|---|---|
| `--schema <path>` | none | An [ordered TOML schema](configuration.md#member-output-schemas). Relative paths use the caller's directory. |
| `--extra-columns append\|drop` | file setting, then `append` | Append unexpected fields after the declared columns, or omit them. Requires `--schema`. |
| `--missing-columns warn\|error` | file setting, then `warn` | Keep a blank column and warn, or fail on missing headers. Requires `--schema`. |

Overrides resolve independently. Matching includes case and spaces. Diagnostics name columns,
never member values. Missing means an absent header; an empty cell under an existing header
is allowed. Without `--schema`, these commands retain the upstream order and existing parsing.

Invalid schemas fail before network access. Invalid CSVs or missing headers under `error` fail
before truncating an output file or clearing a sheet. Errors exit nonzero. With a schema,
text such as leading zeroes and literal `NA` is preserved. Member-details, credentials and
deck-evaluation commands do not accept these flags.

## `auth`

```
auth login  --team <alias>
auth status
auth logout --team <alias>
```

| Command | Does |
|---|---|
| `auth login` | Asks for the REMS username (offering the saved one) and password (shown as `*`), logs in afresh, asking for the emailed code if REMS wants one, and saves the login and its session only if the login works. Replaces any login saved under the alias. |
| `auth status` | Lists each alias and its username, and says if `REMS_USERNAME` and `REMS_PASSWORD` are overriding them. Exits 1 if nothing is saved or a saved password is missing from the keychain. |
| `auth logout` | Removes the alias's session, password and username, in that order. Doesn't contact REMS. |

## `refresh-members`

Downloads REMS's members export for a season.

| Flag | Default | |
|---|---|---|
| `--season` | required | |
| [Output](#output) flags | `--output csv` | Tab: `REMS Members`. |
| `--team` | required | The [saved login](#rems-login). |

Also accepts the [member schema options](#member-output-schemas).

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
| `--team` | required | The [saved login](#rems-login). |

## `refresh-member-credentials`

```
refresh-member-credentials <member_details_file> [output flags]
```

For each row of the member details CSV, lists all the member's credentials.

| Flag | Default | |
|---|---|---|
| [Output](#output) flags | `--output csv` | Tab: `REMS Member Credentials`. |
| `--team` | required | The [saved login](#rems-login). |

## Upload commands

```
upload-members            --input-file <csv> --sheet-id <id> [--sheet-name <tab>]
upload-member-details     --input-file <csv> --sheet-id <id> [--sheet-name <tab>]
upload-member-credentials --input-file <csv> --sheet-id <id> [--sheet-name <tab>]
```

Write a CSV to a sheet tab, replacing it ([how](sheets.md#writing-a-tab)). The default tabs are
`REMS Members`, `REMS Member Details` and `REMS Member Credentials`. They don't contact REMS.

Only `upload-members` accepts the [member schema options](#member-output-schemas). For the
registration contract, pass `--schema schemas/rems-members.toml`; it fails on missing headers
and appends new columns without shifting the old ones.

The registration pipeline uses `python -m src.member_schema <schema> [csv]` for local preflight:
with a schema alone it validates the contract; with a CSV it also parses and projects that
input in memory. It writes no files and contacts neither REMS nor Google. An error exits
nonzero; the manual refresh sequence must stop there.

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
| `--team` | required | The [saved login](#rems-login). |

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
| `--team` | required | The [saved login](#rems-login). |

## Exit codes

`0` on success. `1` on most errors, with a message starting `Error:`, or a Python traceback
for an unexpected one; `2` for a usage error such as a missing
required flag. Some errors are only printed, and the command still exits 0:

- a refresh with `--output csv` but no `--output-file`, or `--output gsheet` but no `--sheet-id`;
- `refresh-member-details` when its input has no REMS ID column or can't be read;
