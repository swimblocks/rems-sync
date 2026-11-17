# Sheets and CSV files

What rems-sync reads from and writes to Google Sheets and CSV files.

## Writing a tab

Every command that writes a tab (`--output gsheet`, and the three `upload-*` commands) replaces
it whole: it clears the tab, then writes a header row and the data. A tab that doesn't exist is
created. Empty values are written as empty cells, and columns pandas names `Unnamed: …` (from
trailing commas in a CSV) are dropped.

## The registration tabs

The member refresh writes three tabs, by default with these names:

| Tab | Written by | Columns |
|---|---|---|
| `REMS Members` | `refresh-members`, `upload-members` | REMS's own members export, as REMS returns it. |
| `REMS Member Details` | `refresh-member-details`, `upload-member-details` | `rems_id`, `member_id`, `member_season_id`, `season_id` |
| `REMS Member Credentials` | `refresh-member-credentials`, `upload-member-credentials` | `rems_id`, `member_id`, `member_season_id`, `name`, `type`, `first_name`, `last_name`, `status`, `start_date`, `expiry_date`, `actions` |

In the credentials table, `name` and `type` are the credential's (for example a clinic, and its
type), `start_date` and `expiry_date` are REMS's `d/m/Y`, and `actions` is a comma-separated list
of the credential's REMS links.

The CSV files have the same columns.

## Input CSV files

- **`refresh-member-details`** reads any CSV with a REMS ID column, normally the members
  export. The column is found by name, ignoring case and anything but letters and digits, so
  `REMS ID`, `REMSID` and `rems_id` all work. Values that aren't valid REMS IDs are skipped,
  and duplicates are read once.
- **`refresh-member-credentials`** reads the member details CSV: it needs `rems_id`,
  `member_id` and `member_season_id`.

## The meet roster sheet

`upload-deck-evals` reads a meet's roster sheet. Each tab name can be changed with a flag.

### Positions tab (`--positions-tab`, default `Positions`)

One row per official per session, header on row 1. Required columns:

| Column | Meaning |
|---|---|
| `Official Name` | Looked up in the Officials tab. |
| `Official Position` | The position evaluated; see [position names](#position-names). |
| `Official Club` | Only rows matching `--rems-club` (default `ROW`, any case) are processed. |
| `Deck Eval Success?` | `TRUE`, `YES` or `1` (any case) for a passed evaluation. |
| `Deck Eval Provider` | The evaluator's full name. |
| `Deck Eval Recorded?` | Empty or `FALSE` until recorded; set to `TRUE` by the upload. |
| `Session` (`--session-col`) | The session the row belongs to, matched to the Grid tab. |

A row is **pending** when `Deck Eval Success?` is true, `Deck Eval Recorded?` is empty or
`FALSE`, and `Official Club` matches. `--recheck` drops the second condition.

### Grid tab (`--grid-tab`, default `Grid`)

The sessions laid out across the page. The header row is found by content: it is the row with a
cell starting `Session N`. Each such cell is several lines, for example:

```
Session 1
Friday, Apr 10
Senior Briefing: 3:55 pm
```

The session number and date are read from it. The year isn't in the cell; it comes from the
Meet tab's `Meet Start Date`, or else the end year of `--season`.

### Meet tab (`--meet-tab`, default `Meet`)

Labels in column A, values in column B. Read: `Meet Name` (or `Name`), unless `--meet-name` is
given, and `Meet Start Date`.

### Officials tab (`--officials-tab`, default `Officials`)

Name to REMS ID. The header row is found by content, the row with `Name` and `REMS ID` cells
(in the rosters seen so far it is row 3, under merged title rows), and every row after it is
read.

## Position names

Roster position names that differ from REMS's credential names, in `_POSITION_TO_CREDENTIAL_PREFIX`
in [src/utils.py](../../src/utils.py):

| Roster | REMS credential |
|---|---|
| Chief Timer | Chief Timekeeper |
| Admin Desk | Administration Desk |
| Stroke Judge | Judge of Stroke |
| Session Referee | Referee |
| Timer | Introduction to Swimming Officiating |

Any other position is used as written. The credential recorded is
`<REMS credential> Evaluation #<n>`, for example `Chief Timekeeper Evaluation #2`.
[Add a position name](../how-to/contributor/add-a-position-name.md) when a roster uses a new one.
