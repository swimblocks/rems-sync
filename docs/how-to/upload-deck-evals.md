# Upload a meet's deck evaluations

Record in REMS every passed deck evaluation in a meet's roster sheet, and mark each one
recorded. What it decides and why: [How deck evaluations are recorded](../explanation/deck-eval-upload.md).

You need [Google access](set-up-google-access.md) to the roster sheet, your REMS login in
`REMS_USERNAME` and `REMS_PASSWORD` ([how](../reference/cli.md#rems-login)), and the
roster filled in: for each evaluation, **Deck Eval Success?** ticked and **Deck Eval Provider**
filled ([layout](../reference/sheets.md#the-meet-roster-sheet)).

1. **Rehearse** with `--dry-run`, which does every lookup but records nothing:
   ```bash
   python -m src.main upload-deck-evals --season 2025-2026 --sheet-id <roster_sheet_id> --dry-run
   ```
   Fix anything it reports in the sheet, such as an official missing from the Officials tab or
   a position REMS doesn't know ([add a position name](contributor/add-a-position-name.md)).
2. **Upload**, confirming each one:
   ```bash
   python -m src.main upload-deck-evals --season 2025-2026 --sheet-id <roster_sheet_id> --interactive
   ```
   Answer `y` to record it, `n` (or Enter) to skip it, or `q` to stop. Each recorded row's
   **Deck Eval Recorded?** is ticked. Drop `--interactive` to record them all without asking.
3. **Deal with any row that stopped** because the official already has evaluations #1 and #2
   for the position at other meets: REMS has no #3, so sort it out in REMS by hand.

Running it again is safe: rows already recorded are skipped, and an evaluation already in REMS
for the meet is ticked rather than recorded twice.

## Without the sheet ID

Leave out `--sheet-id` and add `--interactive`, and it lists the season's meets from Drive for
you to pick from.

## Check a meet, or a whole season

```bash
python -m src.main upload-deck-evals --season 2025-2026 --recheck
```

This checks every row marked recorded against REMS, for every meet in the season, and writes
nothing. It reports rows missing from REMS (`MISSING`), dates recorded with day and month
swapped (`SWAPPED`), and evaluations with a bad evaluator. Rerun with `--interactive` (and
`--sheet-id` for one meet) to fix them one at a time.
