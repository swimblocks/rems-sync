# Google access

How rems-sync gets into Google Sheets and Drive, and why it is set up this way. The steps are
in [Set up Google access](../how-to/set-up-google-access.md).

## Application Default Credentials

rems-sync doesn't hold any Google credentials of its own. It asks the Google auth library for
the machine's [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials)
(ADC), with the Sheets and Drive scopes ([src/gsheet.py](../../src/gsheet.py)). Whatever
identity ADC resolves to is the identity that reads and writes the sheets. So access is decided
outside rems-sync, by `gcloud`, and by who each sheet is shared with.

## Two ways to set up ADC

- **As yourself.** `gcloud auth application-default login` signs in with your own Google
  account. rems-sync can then reach any sheet you can.
- **As the `rems-sync-sa` service account.** The same command with
  `--impersonate-service-account=rems-sync-sa@<project>.iam.gserviceaccount.com` signs you in,
  then has Google issue short-lived tokens for the service account. rems-sync acts as the
  service account, and reaches only sheets shared with it.

Impersonation is the recommended way. The tool's reach is limited to the sheets deliberately
shared with the service account, rather than everything your account can open, and no key file
is ever downloaded: your own login is what lets you borrow the account. The
[Terraform](../reference/terraform.md) creates the service account and gives you that right.

## Why a sheet must be shared

Drive search and sheet access both answer as the ADC identity. A sheet not shared with it
looks, to rems-sync, as if it doesn't exist. When a Drive search finds nothing, the
`upload-deck-evals` error names the identity in use, so you can tell which account the folder
needs sharing with.

## Not yet: running unattended

The service account is also the first step towards running rems-sync on a schedule in Google
Cloud, without a laptop. The rest is not built: somewhere for the REMS login, a container and a
Cloud Run job, a scheduler, and a way past the REMS one-time code when nobody is there to type
it. That work is [#63](https://github.com/swimblocks/rems-sync/issues/63).
