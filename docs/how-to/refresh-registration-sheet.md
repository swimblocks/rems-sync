# Refresh a season's registration sheet

Bring the season's Officials Registration sheet up to date from REMS: its three REMS tabs,
**REMS Members**, **REMS Member Details** and **REMS Member Credentials**.

You need [Google access](set-up-google-access.md) to the sheet, your REMS login, the season (for
example `2026-2027`) and the sheet's ID: the part of its URL between `/d/` and `/edit`.

Each step writes a CSV, which the next step reads, so a failure part-way doesn't touch the
sheet, and a step can be rerun on its own.

0. **Give the terminal your REMS login** ([how](../reference/cli.md#rems-login)), so each
   command can log in when it needs to:
   ```powershell
   $env:REMS_USERNAME = "<your REMS username>"
   $env:REMS_PASSWORD = Read-Host "REMS password"
   ```
1. **Members.** Expect a prompt for the REMS code if you haven't logged in within the hour.
   ```bash
   python -m src.main refresh-members --season 2026-2027 --output csv --output-file members.csv
   ```
2. **Member details.** One REMS request per member; a few minutes for a large club.
   ```bash
   python -m src.main refresh-member-details members.csv --season 2026-2027 \
     --output csv --output-file member_details.csv
   ```
3. **Credentials.**
   ```bash
   python -m src.main refresh-member-credentials member_details.csv \
     --output csv --output-file credentials.csv
   ```
4. **Upload all three** to the sheet. Each replaces its tab.
   ```bash
   python -m src.main upload-members --input-file members.csv --sheet-id <sheet_id>
   python -m src.main upload-member-details --input-file member_details.csv --sheet-id <sheet_id>
   python -m src.main upload-member-credentials --input-file credentials.csv --sheet-id <sheet_id>
   ```
5. **Check** that each upload printed `Successfully wrote data to sheet`. An upload that prints
   `Error uploading …` failed, even though it exits normally.
6. **Delete the CSV files.** They hold members' personal details.

To write straight to the sheet instead of via CSV, give a refresh command
`--output gsheet --sheet-id <sheet_id>`; the next step still needs the CSV, though.
