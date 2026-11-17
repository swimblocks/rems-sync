# Your first refresh

From a fresh copy of rems-sync to a list of your club's officials pulled from REMS, then
written to a Google Sheet tab of your own. About fifteen minutes, most of it one-time setup.

You'll need:

- Python 3.12 or later, and Git;
- the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install);
- your REMS login for your club's officials, and access to its email for the login code;
- a Google Sheet you can edit, to practise on, and the `rems-sync-sa` service account's email
  from whoever [set up the cloud project](../playbooks/cloud-setup.md).

## 1. Install

```bash
git clone https://github.com/swimblocks/rems-sync.git
cd rems-sync
python -m venv .venv
source .venv/bin/activate    # Git Bash on Windows: source .venv/Scripts/activate; PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m src.main --help
```

The last command lists rems-sync's commands. Every command in this tutorial runs from this
folder with the environment active.

## 2. Log in to REMS

Give this terminal your REMS login, so later commands can log in again when they need to:

```powershell
$env:REMS_USERNAME = "<your REMS username>"
$env:REMS_PASSWORD = Read-Host "REMS password"
```

(In bash, see [REMS login](../reference/cli.md#rems-login).)

Then log in:

```bash
python -m src.main login
```

It asks for the six-digit code REMS emails you, and prints `Login successful`. The session is saved, so for the next hour the other commands won't ask
again.

## 3. Pull this season's members

```bash
python -m src.main refresh-members --season 2026-2027 --output csv --output-file members.csv
```

It prints `Using cached REMS session (MFA skipped)`: the session from step 2 at work. Open
`members.csv`: one row per official registered with your club this season, in REMS's own
export format.

## 4. Let rems-sync into your sheet

Share your practice sheet with the service account's email, as Editor. Then sign in to Google
as the service account:

```bash
gcloud auth application-default login \
  --impersonate-service-account=rems-sync-sa@<project_id>.iam.gserviceaccount.com
```

A browser opens; sign in with your own Google account.

## 5. Write the members to the sheet

Copy the sheet's ID from its URL, the part between `/d/` and `/edit`, then:

```bash
python -m src.main upload-members --input-file members.csv --sheet-id <sheet_id>
```

It prints `Successfully wrote data to sheet: REMS Members`. Open the sheet: there is a new
**REMS Members** tab with the CSV in it.

## 6. Tidy up

Delete `members.csv`: it holds members' personal details. Delete the practice tab too, if you
like.

## What you've done

You've logged in to REMS once and reused the session, pulled data out of REMS to a file, and
written it to a sheet as the service account. The full season refresh is the same pattern with
two more steps: [Refresh a season's registration sheet](../how-to/refresh-registration-sheet.md).
For how the pieces fit, read [Logging in to REMS](../explanation/rems-login.md) and
[Google access](../explanation/google-access.md).
