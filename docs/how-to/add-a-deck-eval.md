# Record one deck evaluation

Record a single deck evaluation in REMS, without a roster sheet. All the flags:
[`add-deck-eval`](../reference/cli.md#add-deck-eval).

You need a [saved REMS login](manage-saved-logins.md), such as `row`, and, ideally, the official's REMS ID: a search by name can match the
wrong person or no one.

1. **Rehearse** with `--dry-run`:
   ```bash
   python -m src.main add-deck-eval --team row --season 2025-2026 \
     --official-name "<official's full name>" --rems-id <REMS ID> \
     --position "Chief Timer" --provider "<evaluator's full name>" \
     --meet "<meet name>" --date 2026-04-12 --description "Session 6" \
     --dry-run
   ```
   It shows whether this would be evaluation #1 or #2, or that it is already recorded.
2. **Run it again without `--dry-run`** to record it.

If the meet doesn't run Wednesday to Sunday around `--date`, add every date of the meet, so a
second evaluation at the same meet is caught:

```bash
--meet-dates 2026-04-10,2026-04-11,2026-04-12
```
