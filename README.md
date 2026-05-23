# REMS Sync

[![ci](https://github.com/gavinbee/rems-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/gavinbee/rems-sync/actions/workflows/ci.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

This project is a Python-based CLI tool to synchronize data from the Swimming Canada REMS system.

## Features

- Log in to the REMS system with MFA support.
- Refresh REMS members list, outputting to CSV or Google Sheet.
- Refresh REMS member details, outputting to CSV or Google Sheet.
- Refresh REMS member credentials, outputting to CSV or Google Sheet.
- Upload members, details, or credentials from CSV to a Google Sheet
- Upload deck evaluations to REMS, either one at a time or in bulk from a meet's positions sheet

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your_username/rems-sync.git
    cd rems-sync
    ```
2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv .venv
    ```

    Activate the virtual environment:

    <details open>
    <summary><strong>Windows</strong></summary>

    **Command Prompt:**
    ```cmd
    .venv\Scripts\activate
    ```

    **PowerShell:**
    ```powershell
    .venv\Scripts\Activate.ps1
    ```
    </details>

    <details>
    <summary><strong>Linux/macOS</strong></summary>

    ```bash
    source .venv/bin/activate
    ```
    </details>
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## GCP Setup with Terraform

To use this tool, you need a Google Cloud Platform (GCP) project with the necessary APIs enabled and a service account with the correct permissions. You can use the provided Terraform configuration to automate this setup.

### Prerequisites

1.  **Install Terraform:**
    Follow the instructions [here](https://learn.hashicorp.com/tutorials/terraform/install-cli) to install the Terraform CLI.
2.  **Install the Google Cloud CLI:**
    Follow the instructions [here](https://cloud.google.com/sdk/docs/install) to install the `gcloud` CLI.
3.  **Authenticate with Google Cloud:**
    Run the following command in your terminal and follow the prompts to authenticate with your Google account:
    ```bash
    gcloud auth login
    gcloud auth application-default login
    ```
4.  **Create a GCP Project:**
    If you don't already have a GCP project, create one using the `gcloud` CLI:
    ```bash
    gcloud projects create <your_project_id>
    ```
    Replace `<your_project_id>` with a unique ID for your project.

### Provisioning the Infrastructure

1.  **Navigate to the `terraform` directory:**
    ```bash
    cd terraform
    ```
2.  **Initialize Terraform:**
    ```bash
    terraform init
    ```
3.  **Create a `terraform.tfvars` file:**
    Create a file named `terraform.tfvars` in the `terraform` directory and add the following content:
    ```
    project_id = "<your_project_id>"
    ```
    Replace `<your_project_id>` with the ID of your GCP project.
4.  **Apply the Terraform configuration:**
    ```bash
    terraform apply
    ```
    Terraform will show you a plan of the resources it will create. Type `yes` to approve the plan.
5.  **Get the service account email:**
    After the `apply` command completes, Terraform will output the email address of the created service account. You will need this to share your Google Sheet with the service account.
    ```
    Outputs:

    service_account_email = "rems-sync-sa@<your_project_id>.iam.gserviceaccount.com"
    ```

### After Provisioning

Once the infrastructure is provisioned, you need to:

1.  **Share your Google Sheet:**
    Share your Google Sheet with the service account email address and give it "Editor" permissions.
2.  **Set up Application Default Credentials (ADC) with Impersonation:**
    To test with the service account's identity locally without downloading a JSON key, use service account impersonation. First, ensure your user has the `roles/iam.serviceAccountTokenCreator` role on the service account (or project). Then run:
    ```bash
    gcloud auth application-default login --impersonate-service-account=rems-sync-sa@<your_project_id>.iam.gserviceaccount.com
    ```
    This ensures that the `rems-sync` CLI runs with the exact permissions of the service account, verifying the "least privilege" setup.

## Usage

### Authentication

Each command that interacts with REMS requires your REMS username and password for authentication. You can provide these as command-line options or environment variables.

-   **Command-line options:** `--username <your_username>` and `--password <your_password>`
-   **Environment variables:** `REMS_USERNAME` and `REMS_PASSWORD`

You will also be prompted for an MFA code during the login process.

### Commands

**Login:**

```bash
python -m src.main login --username <your_username> --password <your_password>
```

**Refresh Members:**

```bash
python -m src.main refresh-members --username <your_username> --password <your_password> --season <season> --output csv --output-file members.csv
python -m src.main refresh-members --username <your_username> --password <your_password> --season <season> --output gsheet --sheet-id <google_sheet_id> --sheet-name "REMS Members"
```

Replace `<your_username>`, `<your_password>`, `<season>`, and `<google_sheet_id>` with your actual values.

The `<season>` argument can be either a year (e.g., "2025") or a year range (e.g., "2025-2026").

**Refresh Member Details:**

```bash
python -m src.main refresh-member-details members.csv --username <your_username> --password <your_password> --season <season>  --output csv --output-file member_details.csv
python -m src.main refresh-member-details members.csv --username <your_username> --password <your_password> --season <season> --output gsheet --sheet-id <google_sheet_id> --sheet-name "REMS Member Details"
```
The input CSV file (e.g., `members.csv`) must contain a column named something like "REMS ID", "REMSID", or "rems_id".

**Refresh Member Credentials:**

Given a CSV containing detailed, season-specific, identifiers members retrieve all of the credentials for those members.  The command assumes that the CSV has the same columns as the output of the refresh-member-details command.

To output the credentials to a CSV:
```bash
python -m src.main refresh-member-credentials member_details.csv --username <your_username> --password <your_password> --output csv --output-file credentials.csv
```

To write the credentials directly to Google Sheets:
```bash
python -m src.main refresh-member-credentials member_details.csv --username <your_username> --password <your_password> --output gsheet --sheet-id <google_sheet_id> --sheet-name "REMS Member Credentials"
```

**Upload Members from CSV:**

```bash
python -m src.main upload-members --input-file rems_export.csv --sheet-id <google_sheet_id> --sheet-name "REMS Members"
```

**Upload Member Details from CSV:**

```bash
python -m src.main upload-member-details --input-file rems_member_details.csv --sheet-id <google_sheet_id> --sheet-name "REMS Member Details"
```

**Upload Member Credentials from CSV:**

Given a CSV containing member credentials in the format generated by the `refresh-member-credentials` command, upload the credentials to the specified Google Sheet.

```bash
python -m src.main upload-member-credentials --input-file rems_member_credentials.csv --sheet-id <google_sheet_id> [--sheet-name "REMS Member Credentials"]
```

Unless `--sheet-name` is specified, the credentials will overwrite the contents of the sheet tab named "REMS Member Credentials".

### Deck evaluation upload

Two commands write deck evaluations to REMS: `add-deck-eval` for a single record, and `upload-deck-evals` for a meet-wide batch read from a Google Sheet. Both use the same underlying flow: resolve the official, work out whether this is their #1 or #2 evaluation for the position, check that the same meet/session isn't already recorded, then POST the credential.

#### Authentication and the cookie cache

The first authenticated command of a session triggers an MFA login. Cookies are cached to `~/.rems-sync/cookies.json` so subsequent runs reuse the session without prompting. You'll only be prompted for an MFA code when REMS actually demands one (e.g. on a new device or after a full logout). A mid-batch 403 (Authentication-JWT expired during a long interactive session) triggers an automatic re-login and retry.

Run `python -m src.main login` to do nothing but log in (useful to warm the cache before a long batch). The full auth / MFA flow is documented in [docs/auth.md](docs/auth.md).

#### `add-deck-eval` — single evaluation

Adds one deck evaluation for one official, no spreadsheet required. The tool counts existing evaluations for the position in REMS to pick #1 vs #2, then verifies that the same meet + session isn't already recorded before POSTing.

```bash
python -m src.main add-deck-eval \
  --username <user> --password <pw> \
  --season 2025-2026 \
  --official-name "Chris Fletcher" \
  --rems-id SC24176410 \
  --position "Chief Timer" \
  --provider "Kaoru Yajima" \
  --meet "Cunningham Classic 2026" \
  --date 2026-04-12 \
  --description "Session 6" \
  [--meet-dates 2026-04-10,2026-04-11,2026-04-12] \
  [--dry-run]
```

- `--rems-id` (optional but recommended): look up by REMS ID instead of name search. Avoids the "Janpreet" / single-name ambiguity.
- `--meet-dates` (optional): comma-separated list of all the meet's session dates. When provided, the duplicate check rejects an add if any existing eval for the position falls on any of these dates — enforcing "no two evals for the same position at the same meet" even if a previous eval was on a different session. **When omitted, the tool defaults to the Wed..Sun bracket around `--date`** (most recent Wed on/before, through next Sun on/after). Pass `--meet-dates` explicitly for meets that span outside this default.
- `--dry-run`: do every read (login, member lookup, existing credentials, form options) but skip the POST.

Duplicate detection uses the same logic for both commands: any existing deck eval for the same position whose `start_date` falls within the date set is treated as the same record. `upload-deck-evals` always passes the full meet's session date set from the Grid tab (the rule is fully enforced). `add-deck-eval` defaults to the Wed..Sun bracket around `--date`, or to `--meet-dates` if provided. If found, "already recorded" is reported and the command exits 0 (idempotent). If the official is at the form's maximum (#1 and #2 both exist) on dates outside the set, the command refuses with a clear message instructing you to resolve it in REMS.

#### `upload-deck-evals` — batch from a Google Sheet

Reads a meet's Google Sheet, uploads every pending deck evaluation to REMS, and writes `TRUE` back to the **Deck Eval Recorded?** column of each successful row.

```bash
python -m src.main upload-deck-evals \
  --username <user> --password <pw> \
  --season 2025-2026 \
  [--sheet-id <google_sheet_id>] \
  [--positions-tab Positions] \
  [--grid-tab Grid] \
  [--meet-tab Meet] \
  [--officials-tab Officials] \
  [--session-col Session] \
  [--rems-club ROW] \
  [--meet-name "Override"] \
  [--interactive] \
  [--recheck] \
  [--dry-run]
```

Flags:
- `--sheet-id`: the meet's roster Google Sheet ID. **Optional** — when omitted, the tool searches the configured shared Drive folder for a season subfolder matching `--season` and gathers every meet subfolder that contains an "Officials Roster" sheet. With `--interactive`, you'll be prompted to pick one meet (`a` picks all of them, `q` quits). Without `--interactive`, every discovered meet is processed in turn — handy for a season-wide `--recheck`.
- `--season-folder-id`: root Drive folder to search for season subfolders. Defaults to the hard-coded ROW shared drive. Only used when `--sheet-id` is not provided.
- `--roster-name-substring`: substring used to identify the roster sheet inside a meet folder. Default `"Officials Roster"`.
- `--rems-club`: only process rows whose `Official Club` column matches this value (case-insensitive). You can only add deck evaluations for officials registered under your own club in REMS, so the tool skips other-club rows by default. Defaults to `ROW`.
- `--interactive`: prompt `y/n/q` before POSTing each row. Default if you just press Enter is `n` (skip). `q` aborts the rest of the batch.
- `--recheck`: **verify-only** pass for new evals. Also includes rows already marked `Deck Eval Recorded? = TRUE`, confirms each one against REMS, and reports any missing from REMS as `MISSING`. Rows where REMS holds the eval but with the day and month accidentally swapped (a legacy bug from an earlier build of this tool) are flagged `SWAPPED`. With `--recheck --interactive`, each `MISSING` row prompts to add the eval to REMS now (y/N/q), and each `SWAPPED` row offers a `y/N` prompt to fix the date directly via the credential edit endpoint.
- `--dry-run`: run all reads (including the per-row REMS lookups) but skip the POST and the sheet write-back.

Expected sheet structure:

- **Positions tab** (default `Positions`) — one row per official per session. Required columns: `Official Name`, `Official Position`, `Official Club`, `Deck Eval Success?`, `Deck Eval Provider`, `Deck Eval Recorded?`, and the session-identifier column (default `Session`).
- **Grid tab** (default `Grid`) — 2D layout. Each session is a column header containing multi-line text such as `"Session 1\nFriday, Apr 10\nSenior Briefing: 3:55 pm\n..."`. The tool extracts the session number and date from this header. The year is taken from the Meet tab's `Meet Start Date`, falling back to the `--season` end year.
- **Meet tab** (default `Meet`) — key/value layout (column A label, column B value). The tool reads `Meet Name` (or `Name`) and `Meet Start Date`. Override the meet name with `--meet-name` to skip this lookup.
- **Officials tab** (default `Officials`) — name → REMS ID lookup. The tool finds the header row by looking for `Name` and `REMS ID` cells and builds the map from subsequent rows. Used to translate Positions-tab names into REMS IDs, which is more reliable than name-based REMS search.

##### Position name normalization

The Positions tab uses friendly names that don't always match REMS credential names. The tool applies a known-mismatch map before lookup:

| Positions tab | REMS credential prefix |
|---|---|
| Chief Timer | Chief Timekeeper |
| Admin Desk | Administration Desk |
| Stroke Judge | Judge of Stroke |
| Session Referee | Referee |
| Timer | Introduction to Swimming Officiating |

Other positions are used verbatim. Add new mappings in [src/utils.py](src/utils.py) (`_POSITION_TO_CREDENTIAL_PREFIX`) when you encounter a new mismatch.

##### Pending-row filter

A row is considered "pending" when all of:
- `Deck Eval Success?` is `TRUE` / `YES` / `1` (case- and whitespace-insensitive),
- `Deck Eval Recorded?` is empty or `FALSE`, AND
- `Official Club` matches `--rems-club` (default `ROW`).

`--recheck` removes the second condition but keeps the club filter.

##### Per-row outcomes

For each pending row:

1. The official's name is looked up in the Officials tab to get a REMS ID.
2. The REMS ID is resolved to `member_season_id` and `member_id` via REMS.
3. Existing deck evaluations for the position are inspected to decide eval #1 vs #2.
4. The same meet + session is checked against existing evaluation details; if already recorded, the row is treated as a success (cell ticked).
5. Otherwise the new credential is POSTed and the cell ticked on a 302 success.

Failures on individual rows are reported but do not abort the batch (unless you pick `q` in interactive mode).
## License

[MIT](LICENSE) © 2026 Gavin Bee.
