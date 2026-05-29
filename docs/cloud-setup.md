# Cloud setup (optional)

> **You do not need any of this to run `rems-sync` from your laptop.** This document covers the GCP infrastructure that would let `rems-sync` run unattended (a Cloud Run job, a service-account identity, a scheduled trigger). It is scaffolding for [#63 — Epic: run rems-sync in the cloud](https://github.com/swimblocks/rems-sync/issues/63); the current CLI auths with user OAuth via `gcloud auth application-default login` and never touches the service account at runtime.
>
> If you just want to use the CLI interactively, see [Installation in the README](../README.md#installation) instead.

The Terraform configuration in [`terraform/`](../terraform/) provisions a Google Cloud project ready for a future headless / scheduled deployment: it enables the Sheets and Drive APIs, creates the `rems-sync-sa` service account, and grants the operator the rights to impersonate it.

## Prerequisites

1.  **Install Terraform.** See [the Terraform install guide](https://learn.hashicorp.com/tutorials/terraform/install-cli).
2.  **Install the Google Cloud CLI.** See [the gcloud install guide](https://cloud.google.com/sdk/docs/install).
3.  **Authenticate with Google Cloud.**
    ```bash
    gcloud auth login
    gcloud auth application-default login
    ```
4.  **Create a GCP project** (skip if you already have one):
    ```bash
    gcloud projects create <your_project_id>
    ```

## Provisioning the infrastructure

1.  **Switch to the `terraform` directory:**
    ```bash
    cd terraform
    ```
2.  **Initialise Terraform:**
    ```bash
    terraform init
    ```
3.  **Create a `terraform.tfvars` file:**
    ```hcl
    project_id = "<your_project_id>"
    ```
4.  **Apply:**
    ```bash
    terraform apply
    ```
5.  **Note the service-account email** in the Terraform output:
    ```
    Outputs:

    service_account_email = "rems-sync-sa@<your_project_id>.iam.gserviceaccount.com"
    ```

## After provisioning

1.  **Share your Google Sheet** with the service-account email address as Editor.
2.  **Test impersonation locally.** This runs the CLI under the SA's identity without ever downloading a JSON key:
    ```bash
    gcloud auth application-default login --impersonate-service-account=rems-sync-sa@<your_project_id>.iam.gserviceaccount.com
    ```
    Your user needs `roles/iam.serviceAccountTokenCreator` on the SA (the Terraform binding takes care of this for the email in `var.user_email`).

## Status

What's already done by this Terraform config:

- ✅ Sheets + Drive APIs enabled
- ✅ `rems-sync-sa` service account exists
- ✅ Operator can impersonate the SA via `gcloud auth application-default login --impersonate-service-account=...`

What's still missing for an actual cloud deployment (tracked in [#63](https://github.com/swimblocks/rems-sync/issues/63)):

- ❌ REMS credentials / cookie blob in Secret Manager
- ❌ Container image + Cloud Run job
- ❌ Cloud Scheduler trigger
- ❌ Strategy for REMS MFA under unattended runs

If you actually need a scheduled / headless deployment, follow that epic.
