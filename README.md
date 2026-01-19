# REMS Sync

This project is a Python-based CLI tool to synchronize data from the Swimming Canada REMS system.

## Features

- Log in to the REMS system with MFA support.
- Refresh REMS members list, outputting to CSV or Google Sheet.
- Refresh REMS member details, outputting to CSV or Google Sheet.
- Refresh REMS member credentials, outputting to CSV or Google Sheet.
- Upload members, details, or credentials from CSV to a Google Sheet

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

## Gmail API Setup (Optional - For Automated MFA)

To use automated MFA code extraction from Gmail (recommended for unattended operation), you need to enable the Gmail API and configure authentication:

1. **Enable Gmail API** in your GCP project (done automatically via Terraform when you apply the configuration)

2. **Authenticate with Gmail access**:
   - Run `gcloud auth application-default login` to authenticate with your Google account
   - This grants the application access to your Gmail inbox to retrieve MFA codes
   - The tool uses read-only access and marks emails as read after extracting codes

3. **Verify Gmail access**:
   - Ensure your Google account receives MFA codes from `noreply@sportsmanager.ie`
   - The tool searches for emails with subject "verification code" sent within the last 5 minutes

**Note**: Gmail API access is only required if you want to use `--use-gmail-mfa` flag. You can still use interactive MFA prompts without this setup.

## Authentication Caching

This tool supports caching your REMS authentication in GCP Secret Manager to avoid repeated MFA prompts. Cached sessions are valid for 8 hours.

### Initial Setup

Run the `setup-auth` command to cache your credentials:

<details open>
<summary><strong>Windows</strong></summary>

```bash
python -m src.main setup-auth --username <your_username> --password <your_password> --project-id <your_gcp_project>
```

With Gmail MFA (no manual code entry needed):
```bash
python -m src.main setup-auth --username <your_username> --password <your_password> --project-id <your_gcp_project> --use-gmail-mfa
```
</details>

<details>
<summary><strong>Linux/macOS</strong></summary>

```bash
python -m src.main setup-auth --username <your_username> --password <your_password> --project-id <your_gcp_project>
```

With Gmail MFA (no manual code entry needed):
```bash
python -m src.main setup-auth --username <your_username> --password <your_password> --project-id <your_gcp_project> --use-gmail-mfa
```
</details>

### Using Cached Authentication

Once set up, all commands automatically use cached authentication when you provide `--project-id`:

```bash
python -m src.main refresh-members --season 2025 --output csv --output-file members.csv --project-id <your_gcp_project>
```

No username, password, or MFA code required!

### Skipping Cache (for Testing)

To bypass cached authentication and use interactive prompts:

```bash
python -m src.main refresh-members --skip-cache --username <your_username> --password <your_password> --season 2025 --output csv --output-file members.csv
```

### Environment Variables

You can set these environment variables to avoid repeating common options:

- `REMS_USERNAME`: Your REMS username
- `REMS_PASSWORD`: Your REMS password
- `GCP_PROJECT_ID`: Your GCP project ID for Secret Manager

Example:
```bash
export GCP_PROJECT_ID="your-project-id"
python -m src.main refresh-members --season 2025 --output csv --output-file members.csv
```

### Migration Note

**Breaking Change**: The `login` command has been removed. Use `setup-auth` instead to configure and cache your authentication.

## Usage

### Authentication

Each command that interacts with REMS requires authentication. You have several options:

1. **Cached authentication** (recommended): Use `setup-auth` once, then provide `--project-id` to subsequent commands
2. **Command-line options**: `--username <your_username>` and `--password <your_password>`
3. **Environment variables**: `REMS_USERNAME` and `REMS_PASSWORD`

For MFA codes, you can:
- Enter them manually when prompted (default)
- Use `--use-gmail-mfa` flag for automatic extraction from Gmail (requires Gmail API setup)

### Commands

**Setup Authentication (replaces login):**

```bash
python -m src.main setup-auth --username <your_username> --password <your_password> --project-id <your_gcp_project>
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