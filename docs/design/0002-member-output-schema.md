# 0002 — Stable member output columns

Status: proposed (issue [#106](https://github.com/swimblocks/rems-sync/issues/106))

## Context

REMS controls the members CSV headers and their order. `refresh-members` downloads that CSV;
`upload-members` writes its columns in the same order, replacing the destination tab. When
REMS inserts a column, existing spreadsheet formulas using column letters or numeric lookup
indexes can silently read the wrong field.

In November 2026, REMS added `Account Email` before `Phone Number` and
`Description (Primary)` immediately after it. `REMS ID` moved from column 60 to column 62.
These were upstream export changes, not changes to rems-sync's upload code.

Users need an explicit output contract that survives additions, removals and reordering in
the source. It applies to member CSV files and sheet tabs, including the registration-refresh
script. No schema means the existing behaviour remains available.

## Approaches

- **An ordered schema file (chosen).** It can be reviewed, reused for
  CSV and sheet output, and restored from an earlier export's headers. The caller chooses
  whether to append unexpected columns or drop them. The registration script uses a committed
  compatibility schema automatically; direct commands select a schema explicitly.
- **The destination tab's current headers.** Convenient for subsequent uploads, but cannot
  restore an order that has already changed, requires Google access, and cannot govern a
  CSV-only run. Not chosen.
- **A hardcoded export schema.** Would impose one club's contract on every caller and need a
  code release to change it. Not chosen.

## Design

### Schema file

A UTF-8 TOML file describes column order and the default policies for unexpected and missing
columns:

```toml
columns = [
  "Member First Name",
  "Member Last Name",
  "REMS ID",
]
extra_columns = "append"
missing_columns = "warn"
```

This short example selects only three fields; a compatibility schema lists every existing
header in its original order. It contains header names only, never member rows or identifiers.
Use TOML because the application already reads it for configuration; no new dependency is
needed. Direct commands take an explicit schema path; the registration script uses the
committed schema described below. Neither discovers schemas from `config.toml`.

Rules:

- `columns` is required: a non-empty list of unique, non-empty strings. Matching is exact,
  case-sensitive and includes spaces; existing REMS headers contain significant double spaces.
  Whitespace-only names are invalid, but valid names are not trimmed or renamed.
- `extra_columns` is optional, defaults to `append`, and accepts only `append` or `drop`.
- `missing_columns` is optional, defaults to `warn`, and accepts only `warn` or `error`.
- Unknown schema keys, malformed TOML, invalid values, or an unreadable file are errors.
- This is an ordering and selection contract. Type conversion, aliases for renamed headers,
  computed columns and schema version negotiation are outside this change.

### Projection

One shared projection function serves both member commands. Given an input table and schema:

1. Emit all declared columns in schema order.
2. Collect all declared columns absent from the input. With `missing_columns = "warn"`, emit
   blank columns in their declared positions and warn with their names. With `error`, fail
   with all missing column names before replacing any output. A rename appears as a missing
   column plus an extra; rems-sync does not guess that the two are equivalent.
3. With `append`, emit unexpected input columns after the declared columns, preserving their
   relative input order. With `drop`, omit them.
4. Report added or dropped column names to stderr, without member values. The missing-column
   policy checks header presence, not whether individual members have empty cells.

Ignore the export's unnamed trailing field, consistent with the existing sheet upload.
Reject duplicate non-empty input headers when a schema is selected, before pandas can silently
rename them. Reject an empty or whitespace-only header between named fields; it cannot be
matched reliably. Without a schema, leave existing parsing behaviour unchanged.

The projection moves values with their header, preserves row order and does not deduplicate
members. Missing cells serialize as empty CSV fields or blank sheet cells. In the schema-enabled
path, preserve the source's textual values (including leading zeroes and literal `NA`) rather
than adding pandas' numeric or missing-value inference. The trailing unnamed field is ignored
only when empty in every row; reject populated unnamed fields rather than silently losing data.

For the complete November 16 header order, appending the two new REMS columns puts them at the
end and keeps `REMS ID` at column 60. Dropping them reproduces the original header list exactly.

### CLI

Add these options to `refresh-members` and `upload-members`:

| Option | Meaning |
|---|---|
| `--schema <path>` | The TOML schema file. Relative paths resolve against the caller's working directory. |
| `--extra-columns append\|drop` | Override the schema's extra-column policy for this run. Requires `--schema`. |
| `--missing-columns warn\|error` | Override its missing-column policy for this run. Requires `--schema`. |

`refresh-members` applies the projection to either `--output csv` or `--output gsheet`.
`upload-members` applies it to the input CSV before writing the tab. Applying the same schema
and policies twice gives the same columns and values. Each policy resolves independently:
CLI override, then schema setting, then its default (`append` or `warn`). An upload cannot recover columns already dropped from its input CSV.

No schema preserves the current pass-through behaviour, including the unmodified REMS CSV
download. Do not add these options to member-details, member-credentials or deck-eval commands:
their contracts are outside this issue.

Parse and validate the schema before contacting REMS or Google. Validate the input headers and
prepare the complete projected output before truncating a local destination file or calling
the sheet writer, which clears the destination tab. Invalid input must leave existing output
untouched. Errors exit nonzero. This does not add transactional guarantees for network failures
after a valid sheet write has begun.

Example:

```powershell
python -m src.main refresh-members --team row --season 2026-2027 --output csv --output-file members.csv --schema members-schema.toml
python -m src.main upload-members --input-file members.csv --sheet-id <sheet_id> --schema members-schema.toml --extra-columns drop
```

### Registration-refresh script

The script always uses `schemas/rems-members.toml`, committed in this repository. Resolve its
path from the script's repository root, independent of the caller's directory. Do not add
`-Schema`, `-ExtraColumns` or `-MissingColumns` script parameters. Its schema is a versioned
contract, changed through code review rather than per-run switches.

The committed schema sets `extra_columns = "append"` and `missing_columns = "error"`.
A new REMS column is appended without shifting old columns. A missing expected column stops
the run and names every missing header so the operator can assess whether it is still needed.
The operator can then deliberately update the committed schema; the script never silently
relaxes the contract.

Validate the committed schema before the temporary Google login. After downloading the raw
members CSV, validate its headers against that schema before running member-details or
member-credentials refreshes and before uploading any of the three tabs. Reuse the shared
validation/projection code through a small internal Python entry point, not a second schema
parser in PowerShell. A missing header leaves all three tabs unchanged.

Keep the original members CSV for the next refresh step, which needs `REMS ID`. Pass the
committed schema to `upload-members` to produce the stable tab. Intermediate CSVs retain the
upstream order; the uploaded member tab follows the committed contract. The manual six-command
instructions follow the same raw-intermediate pattern and show strict validation before the
remaining refreshes and uploads.

```powershell
.\scripts\refresh-registration.ps1 -Team row -Season 2026-2027
```

### Initial compatibility schema

Commit `schemas/rems-members.toml` using the earlier November 16 export's headers, omitting its
empty trailing field. Set `extra_columns = "append"` and `missing_columns = "error"`. Verify
that every old header retains its old index and that `REMS ID` is included. Read only the
header row; the file must contain no personal data, sheet IDs or project IDs.

This committed file is the registration script's default contract, while direct CLI callers
may supply a different schema. A new schema-generation command is outside this change.
Creating the schema does not authorize an upload to the shared sheet.

## Documentation

Update the same implementation PR's evergreen docs:

- [CLI](../reference/cli.md): options, policy precedence, missing fields and errors.
- [Script](../reference/refresh-registration-script.md): the committed schema, strict
  preflight checks and how to respond to a missing column; no new script parameters.
- [Sheets and CSV files](../reference/sheets.md): stable positions, extra and missing fields,
  and the limits of compatibility when a field is renamed.
- [Configuration](../reference/configuration.md): schema file shape and where it is supplied.
- [Refresh how-to](../how-to/refresh-registration-sheet.md): use a compatibility schema in
  both the script and manual sequence; explain the committed contract and deliberate updates.
- [First-refresh tutorial](../tutorials/first-refresh.md): a minimal schema used for the
  export and upload, so first-time users see the output contract.
- [Code layout](../reference/code-layout.md), the docs index and README: point to the shared
  schema implementation and the relevant guides where needed.

No existing sheet or saved configuration is modified as part of tests or documentation work.

## Verification

Use synthetic rows only. Header names may reflect REMS; any realistic personal values use
seeded Faker `en_CA`, with no real-to-fake mapping committed.

| Case | Expected |
|---|---|
| Source headers reordered | Declared order and associated values preserved. |
| Source adds columns in the middle, `append` | Existing positions unchanged; new columns appear at the end in source order. |
| Same input, `drop` | Only declared columns remain. |
| Declared source column disappears, `warn` | Blank column at its declared position; warning names it. |
| Declared source columns disappear, `error` | Nonzero exit naming all missing headers; output file and sheet untouched. |
| Expected header present but some member cells are empty | Allowed; missing-column policy checks headers only. |
| Header differs in case or spacing | Exact matching; reported as missing and extra, without guessing. |
| Missing, empty, duplicate or invalid schema columns; invalid policy or unknown key | Nonzero exit; output file and sheet untouched. |
| Duplicate input headers or populated unnamed field | Nonzero exit before any output replacement. |
| Empty trailing unnamed field | Ignored. |
| Leading zeroes, literal `NA`, quotes, commas and accented characters | Survive schema-enabled CSV export and upload as text. |
| No schema | Existing behaviour retained. |
| CLI policy overrides file policy | CLI wins; override alone is an error. |
| Refresh CSV, refresh gsheet, upload CSV | Same projection for equivalent input. |
| Project twice with the same schema and policy | No further change. |
| Script invoked outside the repo | Uses the committed schema relative to the repo root. |
| Committed schema | Pins the old header order, includes `REMS ID`, appends extras and fails on missing headers. |
| Script receives a CSV missing an expected header | Stops after member download, before further refreshes or any of the three uploads. |
| Invalid committed schema | Fails before Google login or a refresh step. |

Run the repository's lint and tests and review the diff before handoff. A full refresh against
a shared sheet remains an explicitly authorized manual acceptance run.

## Left to implementation

The shared module's name, internal table representation and test organization are implementation
choices. Keep projection separate from REMS network requests and Google writes so it can be
tested without either service. No additional dependencies are anticipated.

