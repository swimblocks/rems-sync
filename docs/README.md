# rems-sync documentation

Kept true in the same pull request as the change it describes, and sorted by what each page is
for ([Diátaxis](https://diataxis.fr/)).

## Tutorials

Learning by doing, start to finish.

- [Your first refresh](tutorials/first-refresh.md): install, log in to REMS, pull your club's
  members, and write them to a sheet. Start here.

## How-to guides

Step by step, for a goal.

- [Refresh a season's registration sheet](how-to/refresh-registration-sheet.md): members,
  details and credentials, from REMS to the season's sheet.
- [Manage saved logins](how-to/manage-saved-logins.md): save, check, change and remove REMS
  logins.
- [Upload a meet's deck evaluations](how-to/upload-deck-evals.md), and check a meet or season
  against REMS.
- [Record one deck evaluation](how-to/add-a-deck-eval.md), without a sheet.
- [Set up Google access](how-to/set-up-google-access.md): share sheets and sign in as the
  service account.
- For contributors: [add a position name](how-to/contributor/add-a-position-name.md).

## Playbooks

The operator's procedures, for whoever looks after the Google Cloud project.

- [Cloud setup](playbooks/cloud-setup.md): the project and the `rems-sync-sa` service account,
  once, with Terraform.

## Reference

The facts, to look up.

- [CLI](reference/cli.md): every command and flag, and exit codes.
- [Sheets and CSV files](reference/sheets.md): the tabs and columns read and written, the meet
  roster layout, and position names.
- [REMS](reference/rems.md): the login hops, cookies, URLs and values rems-sync relies on.
- [Configuration](reference/configuration.md): `config.toml`, the keychain entries and the
  environment variables; [member schemas](reference/configuration.md#member-output-schemas)
  define stable output columns and missing/extra-column policies.
- [`refresh-registration.ps1`](reference/refresh-registration-script.md): the season refresh
  script's parameters and steps.
- [Terraform](reference/terraform.md): variables, resources and outputs.
- [Code layout](reference/code-layout.md): where things are.

## Explanation

Why it is the way it is.

- [Logging in to REMS](explanation/rems-login.md): the session cache, the probe, the one-time
  code, and the failures that shaped them.
- [Saved logins](explanation/saved-logins.md): aliases, the keychain, and why a session never
  crosses accounts.
- [How deck evaluations are recorded](explanation/deck-eval-upload.md): #1 or #2, never
  twice, recheck.
- [Google access](explanation/google-access.md): Application Default Credentials and the
  service account.

## Design records

[`design/`](design/), indexed in its [README](design/README.md): the reasoning for each piece of
work, written before it is built.
