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

- **An ordered schema file, selected explicitly (chosen).** It can be reviewed, reused for
  CSV and sheet output, and restored from an earlier export's headers. The caller chooses
  whether to append unexpected columns or drop them.
- **The destination tab's current headers.** Convenient for subsequent uploads, but cannot
  restore an order that has already changed, requires Google access, and cannot govern a
  CSV-only run. Not chosen.
- **A hardcoded export schema.** Would impose one club's contract on every caller and need a
  code release to change it. Not chosen.

## Design

### Schema file

A UTF-8 TOML file describes column order and the default policy for unexpected columns:

```toml
columns = [
  "Member First Name",
  "Member Last Name",
  "REMS ID",
]
extra_columns = "append"
```

This short example selects only three fields; a compatibility schema lists every existing
header in its original order. It contains header names only, never member rows or identifiers.
Use TOML because the application already reads it for configuration; no new dependency is
needed. Schema paths are supplied explicitly, not implicitly discovered from `config.toml`.

Rules:

- `columns` is required: a non-empty list of unique, non-empty strings. Matching is exact,
  case-sensitive and includes spaces; existing REMS headers contain significant double spaces.
  Whitespace-only names are invalid, but valid names are not trimmed or renamed.
- `extra_columns` is optional, defaults to `append`, and accepts only `append` or `drop`.
- Unknown schema keys, malformed TOML, invalid values, or an unreadable file are errors.
- This is an ordering and selection contract. Type conversion, aliases for renamed headers,
  computed columns and schema version negotiation are outside this change.

### Projection

One shared projection function serves both member commands. Given an input table and schema:

1. Emit all declared columns in schema order.
2. For a declared column absent from the input, emit an empty column and warn with its name.
   Never omit it or shift later columns. A rename appears as a missing column plus an extra;
   rems-sync does not guess that the two are equivalent.
3. With `append`, emit unexpected input columns after the declared columns, preserving their
   relative input order. With `drop`, omit them.
4. Report added or dropped column names to stderr, without member values. A missing column is
   a warning, not a command failure.

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

### Commands and registration script

Add `--schema <path>` to `refresh-members` and `upload-members`, and
`--extra-columns append|drop` to override the file's policy. An override without a schema is
an error. The effective policy is the CLI override, then the file setting, then `append`.
`refresh-members` applies the schema for either `csv` or `gsheet` output; `upload-members`
applies it to the CSV being uploaded. Other commands retain their existing interfaces.

Add `-Schema <path>` and `-ExtraColumns append|drop` to `refresh-registration.ps1`. Neither
is required. Resolve a relative schema path against the caller's directory before switching
to the repo root. Validate the schema and override before starting Google login or refreshes.

The script keeps the original members CSV for the next refresh step, which needs `REMS ID`.
It passes the schema options only to `upload-members`, so even a schema that selects a few
columns cannot remove an identifier needed by the rest of the pipeline. Intermediate CSVs
therefore retain the upstream order; the uploaded member tab follows the schema. Direct
`refresh-members --schema` remains available for callers who want a projected CSV. The manual
six-command instructions follow the script's pattern: raw intermediate CSV, schema at upload.

### CLI

Add these options to `refresh-members` and `upload-members`:

| Option | Meaning |
|---|---|
| `--schema <path>` | The TOML schema file. Relative paths resolve against the caller's working directory. |
| `--extra-columns append\|drop` | Override the schema's policy for this run. Requires `--schema`. |

`refresh-members` applies the projection to either `--output csv` or `--output gsheet`.
`upload-members` applies it to the input CSV before writing the tab. Applying the same schema
and policy twice gives the same columns and values, so the script can safely use it at both
steps. An upload cannot recover columns already dropped from its input CSV.

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

Add optional `-Schema <path>` and `-ExtraColumns append|drop` parameters to
`scripts/refresh-registration.ps1`. Resolve the schema path to an absolute path in the caller's
directory before the script changes to the repo root, as it already does for `-OutDir`.

Forward both to `refresh-members` and `upload-members`; the other four commands are unchanged.
Reject `-ExtraColumns` without `-Schema`. Validate the schema before the temporary Google login,
so a local configuration error does not first open the browser or start a refresh.

```powershell
.\scripts\refresh-registration.ps1 -Team row -Season 2026-2027 -Schema members-schema.toml
```

The script remains opt-in: without `-Schema`, it behaves as before. Guides recommend supplying
a complete compatibility schema when the destination sheet has formulas depending on positions.

### Initial compatibility schema

Produce a header-only TOML schema from the earlier November 16 export, omitting its empty
trailing field, with `extra_columns = "append"`. Verify that it pins every old header to its
old index. Use only the header row; do not copy personal data into the repository or schema.

The user's actual schema belongs alongside their local deployment configuration and is passed
explicitly. A small illustrative schema in the docs is sufficient; a committed club-specific
schema or a new schema-generation command is not required by this change. Creating the local
schema does not authorize an upload to the shared sheet.

## Documentation

Update the same implementation PR's evergreen docs:

- [CLI](../reference/cli.md): options, policy precedence, missing fields and errors.
- [Script](../reference/refresh-registration-script.md): parameters, path resolution and an
  example using a schema.
- [Sheets and CSV files](../reference/sheets.md): stable positions, extra and missing fields,
  and the limits of compatibility when a field is renamed.
- [Configuration](../reference/configuration.md): schema file shape and where it is supplied.
- [Refresh how-to](../how-to/refresh-registration-sheet.md): use a compatibility schema in
  both the script and manual sequence; explain how to copy an earlier header order.
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
| Declared source column disappears | Blank column at its declared position; warning names it. |
| Header differs in case or spacing | Exact matching; reported as missing and extra, without guessing. |
| Missing, empty, duplicate or invalid schema columns; invalid policy or unknown key | Nonzero exit; output file and sheet untouched. |
| Duplicate input headers or populated unnamed field | Nonzero exit before any output replacement. |
| Empty trailing unnamed field | Ignored. |
| Leading zeroes, literal `NA`, quotes, commas and accented characters | Survive schema-enabled CSV export and upload as text. |
| No schema | Existing behaviour retained. |
| CLI policy overrides file policy | CLI wins; override alone is an error. |
| Refresh CSV, refresh gsheet, upload CSV | Same projection for equivalent input. |
| Project twice with the same schema and policy | No further change. |
| Script invoked outside the repo with a relative schema path | Schema resolves correctly and is passed to the member upload. |
| Script schema omits `REMS ID` with `drop` | Raw intermediate still supplies the identifier to member-details refresh. |
| Invalid script schema | Fails before Google login or a refresh step. |

Run the repository's lint and tests and review the diff before handoff. A full refresh against
a shared sheet remains an explicitly authorized manual acceptance run.

## Left to implementation

The shared module's name, internal table representation and test organization are implementation
choices. Keep projection separate from REMS network requests and Google writes so it can be
tested without either service. No additional dependencies are anticipated.

