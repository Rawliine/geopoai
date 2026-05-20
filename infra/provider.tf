# -----------------------------------------------------------------------------
# Verda provider
# -----------------------------------------------------------------------------
# Authentication uses OAuth-style API credentials from the Verda dashboard:
#   Dashboard → Keys → Cloud API Credentials → Create
#
# Export these in your shell before any Terraform command (Terraform does NOT
# read a `.env` file automatically):
#
#   export VERDA_CLIENT_ID="..."
#   export VERDA_CLIENT_SECRET="..."
#
# Optional: use `direnv` or `set -a; source ../.env; set +a` for local ergonomics.
# -----------------------------------------------------------------------------
provider "verda" {}
