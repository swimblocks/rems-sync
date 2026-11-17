# Refresh a season's registration sheet

Bring the season's Officials Registration sheet up to date from REMS: its three REMS tabs,
**REMS Members**, **REMS Member Details** and **REMS Member Credentials**.

You need:

- a [saved REMS login](manage-saved-logins.md), such as `row`;
- the season's sheet shared with the service account ([Google access](set-up-google-access.md));
- the sheet's ID: the part of its URL between `/d/` and `/edit`.

## With the script (Windows)

1. **Once per season, record the sheet** in your [`config.toml`](../reference/configuration.md#configtoml):
   ```toml
   [sheets]
   "2026-2027" = "<sheet_id>"
   ```
2. **Run it:**
   ```powershell
   .\scripts\refresh-registration.ps1 -Team row -Season 2026-2027
   ```
   A browser opens for the Google sign-in. REMS may ask for its emailed code. Member details
   take a few minutes for a large club.
3. **Check** it ended with `Done. CSVs are in …`. If a step failed, the script stopped there
   and said which; the sheet's tabs before that step were already replaced.
4. **Delete the CSV folder** it names. The files hold members' personal details.

What the script does, and its other parameters: [`refresh-registration.ps1`](../reference/refresh-registration-script.md).

## By hand

The same steps, one command at a time, on any OS. Each refresh writes a CSV, which the next one
reads, so a step can be rerun on its own.

1. Sign in to Google as the service account ([how](set-up-google-access.md)).
2. **Members:**
   ```bash
   python -m src.main refresh-members --team row --season 2026-2027 --output csv --output-file members.csv
   ```
3. **Member details:**
   ```bash
   python -m src.main refresh-member-details members.csv --team row --season 2026-2027 \
     --output csv --output-file member_details.csv
   ```
4. **Credentials:**
   ```bash
   python -m src.main refresh-member-credentials member_details.csv --team row \
     --output csv --output-file credentials.csv
   ```
5. **Upload all three.** Each replaces its tab.
   ```bash
   python -m src.main upload-members --input-file members.csv --sheet-id <sheet_id>
   python -m src.main upload-member-details --input-file member_details.csv --sheet-id <sheet_id>
   python -m src.main upload-member-credentials --input-file credentials.csv --sheet-id <sheet_id>
   ```
6. **Delete the CSV files.**
