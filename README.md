# REMS Sync

This project is a Python-based CLI tool to synchronize data from the Swimming Canada REMS system.

## Features

- Log in to the REMS system with MFA support.
- Refresh REMS members list, outputting to CSV or Google Sheet.
- Refresh REMS member details, outputting to CSV or Google Sheet.
- Refresh REMS member credentials, outputting to CSV or Google Sheet.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your_username/rems-sync.git
    cd rems-sync
    ```
2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv .venv
    .\.venv\Scripts\activate
    ```
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

**Refresh Member Details:**

```bash
python -m src.main refresh-member-details --username <your_username> --password <your_password> --season <season> <rems_id_1> <rems_id_2> --output csv --output-file member_details.csv
python -m src.main refresh-member-details --username <your_username> --password <your_password> --season <season> <rems_id_1> --output gsheet --sheet-id <google_sheet_id> --sheet-name "REMS Member Details"
```
To refresh multiple member details from a file:
```bash
python -m src.main refresh-member-details --username <your_username> --password <your_password> --season <season> --output csv --output-file member_details.csv $(cat rems_ids.txt)
# Or for Google Sheet
python -m src.main refresh-member-details --username <your_username> --password <your_password> --season <season> --output gsheet --sheet-id <google_sheet_id> --sheet-name "REMS Member Details" $(cat rems_ids.txt)
```
(where `rems_ids.txt` contains a space-separated list of REMS IDs)

**Refresh Member Credentials:**

```bash
# Assuming member_details.csv is the output from refresh-member-details command
python -m src.main refresh-member-credentials --username <your_username> --password <your_password> member_details.csv --output csv --output-file credentials.csv
python -m src.main refresh-member-credentials --username <your_username> --password <your_password> member_details.csv --output gsheet --sheet-id <google_sheet_id> --sheet-name "REMS Member Credentials"
```

**Upload Members from CSV:**

```bash
python -m src.main upload-members --input-file C:\Users\gavbe\Downloads\rems_export.csv --sheet-id <google_sheet_id> --sheet-name "REMS Members"
```

Replace `<your_username>`, `<your_password>`, `<season>`, and `<google_sheet_id>` with your actual values.
The `<season>` argument can be either a year (e.g., "2025") or a year range (e.g., "2025-2026").