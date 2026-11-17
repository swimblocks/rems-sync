# How deck evaluations are recorded

How `add-deck-eval` and `upload-deck-evals` decide what to write to REMS, and why. The flags are
in the [CLI reference](../reference/cli.md), the sheet layout in the
[sheets reference](../reference/sheets.md), and the REMS calls in the
[REMS reference](../reference/rems.md#members-and-credentials).

## One flow, two front ends

Both commands do the same thing for each evaluation:

1. **Find the official** in REMS: by REMS ID when there is one, otherwise by name.
2. **Work out #1 or #2.** REMS records deck evaluations as numbered credentials, such as
   "Chief Timekeeper Evaluation #1" and "#2". The number is one more than the evaluations
   already recorded for the position.
3. **Check it isn't already recorded** (below).
4. **Record it** as a new credential.

`add-deck-eval` does this once, from its flags. `upload-deck-evals` does it for every pending
row of a meet's roster sheet, and ticks the row's **Deck Eval Recorded?** cell when it succeeds.
The decision logic is `_resolve_deck_eval_credential` in [src/main.py](../../src/main.py), which
both share and which is unit tested.

```
read the Positions, Grid, Meet and Officials tabs
log in
for each pending row:
    REMS ID from the Officials tab
    member_season_id and member_id from REMS
    the position's existing deck evaluations from REMS
    if one is on a date of this meet       → already recorded: tick the cell, don't post
    elif #1 and #2 both exist               → stop: resolve it in REMS
    else (with --interactive, ask y/n/q)    → post it, then tick the cell
```

A failed row is reported and the batch moves on. Only `q` at an interactive prompt stops it.

## Recording is idempotent

An official can be evaluated in a position only once per meet. So an existing evaluation counts
as "this one" when it is for the same position and its date falls on one of the meet's dates.
Running the same upload twice records nothing new: the second run finds every row already
recorded and just ticks the cells.

The check is `find_existing_deck_eval_in_dates` in [src/utils.py](../../src/utils.py). It runs
on every evaluation, whatever the flags. It compares only the position and the date, and
ignores the evaluator and the meet name and session text, because evaluations entered by hand
in REMS spell those any way at all, while their dates are reliable.

The meet's dates come from:

- **`upload-deck-evals`:** every session date in the Grid tab, so the rule holds exactly.
- **`add-deck-eval`:** `--meet-dates` if given; otherwise the Wednesday on or before `--date`
  through the Sunday on or after it, which covers a normal meet weekend. Pass `--meet-dates`
  for a meet outside that window.

If the check finds nothing but #1 and #2 already exist (on other dates), the form has no #3,
so the command stops and says to sort it out in REMS.

## Why only your club's rows

REMS lets you add credentials only for officials registered under your own club. A roster
sheet lists every club's officials, so `upload-deck-evals` skips rows whose **Official Club**
isn't `--rems-club` (`ROW` by default) instead of failing on them.

## Why the Officials tab is used for REMS IDs

A name search in REMS can match several people, or miss someone registered under a different
spelling or a single name. The roster's Officials tab already maps each name to a REMS ID, so
`upload-deck-evals` looks the ID up there and finds the official by ID.

## Friendly position names

Rosters use the names people say ("Chief Timer"); REMS uses the formal credential names
("Chief Timekeeper"). A small hand-kept table translates the known differences before the
lookup ([list](../reference/sheets.md#position-names)). Any other position is used as written.

## Recheck: is the sheet right?

`--recheck` looks at rows already marked recorded as well, and checks each against REMS without
writing anything:

- **`MISSING`**: the sheet says recorded, but REMS has no matching evaluation.
- **`SWAPPED`**: REMS has it, but with day and month swapped. An early version of this tool sent
  dates as `m/d/Y` to a form that reads `d/m/Y`, so 11 April was recorded as 4 November.

- **Bad provider**: REMS has it, but its evaluator field is empty or reads `TRUE` or `FALSE`.
  An early version leaked the sheet's checkbox value into that field.

Add `--interactive` and each `MISSING` row asks whether to record it now, each `SWAPPED` row
whether to correct the date in REMS, and each bad provider for the evaluator's name to put in
REMS.

## Without `--sheet-id`

`upload-deck-evals` can find meets itself. It looks in a Drive folder (the ROW shared drive by
default) for a subfolder named for the season, then for meet subfolders holding a sheet whose
name contains "Officials Roster". With `--interactive` it asks which meet to use; without, it
processes every meet it finds, which suits a season-wide `--recheck`.
