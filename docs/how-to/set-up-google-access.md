# Set up Google access

Let rems-sync read and write your sheets, as the `rems-sync-sa` service account. Why it works
this way: [Google access](../explanation/google-access.md).

You need the Google Cloud CLI, the service account's email (from
[Set up the cloud project](set-up-the-cloud-project.md)), and the right to impersonate it.

1. **Share each sheet** rems-sync writes to (the season's registration sheet, the meet roster
   sheets, or the Drive folder holding them) with the service account's email, as Editor.
2. **Sign in**, borrowing the service account:
   ```bash
   gcloud auth application-default login \
     --impersonate-service-account=rems-sync-sa@<project_id>.iam.gserviceaccount.com
   ```
   A browser opens for your own Google account.

The sign-in lasts until you revoke it (`gcloud auth application-default revoke`) and is used by
every program on the machine that uses Application Default Credentials.

## If a sheet can't be found

The error for a sheet or folder that isn't shared looks like one that doesn't exist. Check:

- the sheet is shared with the service account, not only with you;
- `gcloud auth application-default print-access-token` works, so the sign-in is live;
- you signed in with `--impersonate-service-account`: without it, rems-sync acts as you.
