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

## What it does

1. Checks for `.venv` and `gcloud`, and works out the sheet and service account. A season
   without a sheet stops here, saying what to add to `config.toml`.
2. Signs in to Google, impersonating the service account, into a temporary gcloud folder
   (`CLOUDSDK_CONFIG` in `%TEMP%`), so your normal gcloud sign-in is untouched. A browser opens.
3. Runs, from the repo root, stopping at the first that fails:
   1. `refresh-members --team <Team> --season <Season>` → `members.csv`
   2. `refresh-member-details members.csv` → `member_details.csv`
   3. `refresh-member-credentials member_details.csv` → `credentials.csv`
   4. `upload-members`, `upload-member-details`, `upload-member-credentials` to the sheet
4. Always, even after a failure: revokes the temporary Google sign-in, deletes its folder, and
   restores `CLOUDSDK_CONFIG`.

A step fails if it exits non-zero, or, for the three refreshes, if it doesn't write its CSV.
REMS may ask for its emailed code during the first refresh.

## Output

`Done. CSVs are in <OutDir>` on success. The CSV files are left there and hold members'
personal details; delete them when you're done.
