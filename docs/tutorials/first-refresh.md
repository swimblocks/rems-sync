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

## 2. Save your REMS login

```bash
python -m src.main auth login --team row
```

`row` is the alias you'll use to name this login; pick your club's. Enter your REMS username and
password (it shows `*` as you type), then the six-digit code REMS emails you. It prints
`Logged in to REMS as <username>; saved as 'row'`. The password is now in your OS keychain, and
the REMS session with it, so for the next hour the other commands won't ask for a code.

Check it:

```bash
python -m src.main auth status
```

## 3. Pull this season's members

Create `practice-members.toml` in this folder:

```toml
columns = ["Member First Name", "Member Last Name", "REMS ID"]
extra_columns = "drop"
missing_columns = "error"
```

This gives the practice output three fixed columns. A new REMS field cannot move them;
if an expected header disappears, the command stops instead of writing incomplete output.

```bash
python -m src.main refresh-members --team row --season 2026-2027 --output csv --output-file members.csv --schema practice-members.toml
```

It prints `Using cached REMS session (MFA skipped)`: the session from step 2 at work. Open
`members.csv`: one row per official registered with your club this season, with the three
declared columns in exactly that order. A message lists the other REMS columns being dropped.

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
python -m src.main upload-members --input-file members.csv --sheet-id <sheet_id> --schema practice-members.toml
```

It prints `Successfully wrote data to sheet: REMS Members`. Open the sheet: there is a new
**REMS Members** tab with the CSV in it. Applying the same schema again preserves the layout.

## 6. Tidy up

Delete `members.csv`: it holds members' personal details. You can remove `practice-members.toml`
too; it contains only headers and policies. Delete the practice tab too, if you
like.

## What you've done

You've saved a REMS login and reused its session, pulled data out of REMS to a file, and
written it to a sheet as the service account. The full season refresh is the same pattern with
two more steps, and on Windows one script does it all:
[Refresh a season's registration sheet](../how-to/refresh-registration-sheet.md).
For how the pieces fit, read [Saved logins](../explanation/saved-logins.md),
[Logging in to REMS](../explanation/rems-login.md) and
[Google access](../explanation/google-access.md).
