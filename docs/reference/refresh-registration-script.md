# `refresh-registration.ps1`

[`scripts/refresh-registration.ps1`](../../scripts/refresh-registration.ps1) runs the whole
season refresh in one go, in Windows PowerShell 5.1 or PowerShell 7. How to use it:
[Refresh a season's registration sheet](../how-to/refresh-registration-sheet.md).

```powershell
.\scripts\refresh-registration.ps1 -Team <alias> -Season <season> [-SheetId <id>] [-OutDir <dir>] [-ServiceAccount <email>]
```

| Parameter | Default | Meaning |
|---|---|---|
| `-Team` | required | The [saved REMS login](cli.md#rems-login) to use. |
| `-Season` | required | e.g. `2026-2027`. |
| `-SheetId` | the season's entry in `[sheets]` in [`config.toml`](configuration.md#configtoml) | The season's registration sheet. |
| `-OutDir` | `~\Downloads\rems-sync\<Season>\<yyyyMMdd-HHmmss>\` | Where the CSV files go. A relative path is from the current directory. |
| `-ServiceAccount` | `rems-sync-sa@<project_id>.iam.gserviceaccount.com`, from `project_id` in `terraform/terraform.tfvars` | The service account to impersonate. |

PowerShell parameter names ignore case and may be shortened, e.g. `-t row -se 2026-2027`.

## Member schema

The script always uses [`schemas/rems-members.toml`](../../schemas/rems-members.toml), resolved
from the repository root. There are no schema or column-policy script parameters. The contract
pins the old positions, appends new REMS columns at the end, and rejects missing expected
headers. Empty values under existing headers are allowed. See
[Configuration](configuration.md#member-output-schemas) for the file format.

## What it does

1. Checks for `.venv` and `gcloud`, validates the committed schema, and works out the sheet and service account. A season
   without a sheet stops here, saying what to add to `config.toml`.
2. Signs in to Google, impersonating the service account, into a temporary gcloud folder
   (`CLOUDSDK_CONFIG` in `%TEMP%`), so your normal gcloud sign-in is untouched. A browser opens.
3. Runs, from the repo root, stopping at the first that fails:
   1. `refresh-members --team <Team> --season <Season>` → `members.csv`
      (the raw upstream export, without projection)
   2. Local schema preflight on `members.csv`; missing headers or malformed input stop here,
      before any further refreshes or uploads.
   3. `refresh-member-details members.csv` → `member_details.csv`
   4. `refresh-member-credentials member_details.csv` → `credentials.csv`
   5. `upload-members --schema <committed schema>`, `upload-member-details`,
      `upload-member-credentials` to the sheet
4. Always, even after a failure: revokes the temporary Google sign-in, deletes its folder, and
   restores `CLOUDSDK_CONFIG`.

A step fails if it exits non-zero, or, for the three refreshes, if it doesn't write its CSV.
REMS may ask for its emailed code during the first refresh.

If preflight reports missing expected columns, all three tabs remain unchanged. Inspect the
reported headers and determine whether downstream formulas still need those fields. If the
contract should change, update the committed schema through review; do not remove a column
merely to get past validation, since doing so shifts later columns. A rename needs the same
review. Warnings about appended columns need no action to preserve existing positions.

## Output

`Done. CSVs are in <OutDir>` on success. The CSV files are left there and hold members'
personal details; delete them when you're done.
