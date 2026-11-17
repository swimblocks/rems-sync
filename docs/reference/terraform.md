# Terraform

The configuration in [`terraform/`](../../terraform/) sets up the Google Cloud project rems-sync
uses. Steps: [Set up the cloud project](../how-to/set-up-the-cloud-project.md).

## Variables

Set in `terraform/terraform.tfvars`, which is gitignored: the project ID and your email stay out
of this public repo.

| Variable | Default | Meaning |
|---|---|---|
| `project_id` | required | The Google Cloud project. |
| `user_email` | required | Your Google account, given the right to impersonate the service account. |
| `region` | `us-central1` | The region. Nothing regional is created yet. |

## Resources

| Resource | What it is |
|---|---|
| `google_project_service.sheets`, `.drive` | The Sheets and Drive APIs, turned on. |
| `google_service_account.rems_sync_sa` | The `rems-sync-sa` service account. |
| `google_project_iam_member.rems_sync_sa_service_usage` | `roles/serviceusage.serviceUsageConsumer` for the service account, so it can call the APIs. |
| `google_service_account_iam_member.token_creator` | `roles/iam.serviceAccountTokenCreator` on the service account for `user_email`, so you can impersonate it. |

## Outputs

| Output | Value |
|---|---|
| `service_account_email` | `rems-sync-sa@<project_id>.iam.gserviceaccount.com` |

## State

Local, in `terraform/terraform.tfstate` (gitignored). Only the operator runs `terraform apply`.
