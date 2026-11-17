# Playbook: cloud setup

Create the Google Cloud project and the `rems-sync-sa` service account, once. Someone in your
club may already have done this; if so, ask them for the service account's email and skip to
[Set up Google access](../how-to/set-up-google-access.md). What the Terraform creates is in the
[Terraform reference](../reference/terraform.md).

You need [Terraform](https://developer.hashicorp.com/terraform/install) and the
[Google Cloud CLI](https://cloud.google.com/sdk/docs/install), and a Google account that can
create projects.

1. Sign in to Google Cloud:
   ```bash
   gcloud auth login
   gcloud auth application-default login
   ```
2. Create the project, unless you are using an existing one:
   ```bash
   gcloud projects create <project_id>
   ```
3. In `terraform/`, create `terraform.tfvars` (it is gitignored):
   ```hcl
   project_id = "<project_id>"
   user_email = "<your Google account>"
   ```
4. Apply it:
   ```bash
   cd terraform
   terraform init
   terraform apply
   ```
5. Note the service account's email from the output:
   ```
   service_account_email = "rems-sync-sa@<project_id>.iam.gserviceaccount.com"
   ```

Next: [Set up Google access](../how-to/set-up-google-access.md).
