# Legacy Terraform Path

Authoritative Terraform is implemented under [../../infra/README.md](../../infra/README.md), with bootstrap, staging, production, and reusable module definitions.

This legacy directory is not an active Terraform root and must not be used for plans or applies. Terraform is platform configuration, not runtime discovery. Local validation does not prove that any AWS environment has been applied.
