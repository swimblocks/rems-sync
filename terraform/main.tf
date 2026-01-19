terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 4.0.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_project_service" "sheets" {
  service = "sheets.googleapis.com"
}

resource "google_project_service" "drive" {
  service = "drive.googleapis.com"
}

resource "google_project_service" "secretmanager" {
  service = "secretmanager.googleapis.com"
}

resource "google_project_service" "gmail" {
  service = "gmail.googleapis.com"
}

resource "google_service_account" "rems_sync_sa" {
  account_id   = "rems-sync-sa"
  display_name = "REMS Sync Service Account"
}

resource "google_project_iam_member" "rems_sync_sa_service_usage" {
  project = var.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = "serviceAccount:${google_service_account.rems_sync_sa.email}"
}

resource "google_service_account_iam_member" "token_creator" {
  service_account_id = google_service_account.rems_sync_sa.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "user:${var.user_email}"
}

resource "google_project_iam_member" "rems_sync_sa_secretmanager" {
  project = var.project_id
  role    = "roles/secretmanager.admin"
  member  = "serviceAccount:${google_service_account.rems_sync_sa.email}"
}

resource "google_secret_manager_secret" "rems_auth" {
  secret_id = "rems-auth"

  replication {
    auto {}
  }

  depends_on = [google_project_service.secretmanager]
}

resource "google_secret_manager_secret_iam_member" "rems_auth_accessor" {
  secret_id = google_secret_manager_secret.rems_auth.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.rems_sync_sa.email}"
}
