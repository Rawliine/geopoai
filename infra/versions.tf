# -----------------------------------------------------------------------------
# Terraform core settings for the GeoPoAI / Verda stack
# -----------------------------------------------------------------------------
# This file only pins provider versions. Resource definitions live in compute.tf.
# -----------------------------------------------------------------------------
terraform {
  required_version = ">= 1.5.0"

  required_providers {
    verda = {
      source  = "verda-cloud/verda"
      version = "~> 1.0"
    }
  }

  # Remote state is strongly recommended if more than one machine might run
  # `terraform apply` against the same Verda account (prevents forked state).
  #
  # Example (uncomment and fill in):
  #
  # backend "s3" {
  #   bucket         = "your-terraform-state-bucket"
  #   key            = "GeoPoAI/infra/terraform.tfstate"
  #   region         = "eu-north-1"
  #   dynamodb_table = "terraform-locks"
  # }
}
