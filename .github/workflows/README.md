# GitHub Actions

Platform, security, and release engineers use these workflows for source verification and immutable release promotion.

`ci.yml` runs backend, frontend, container, dependency, migration, secret, Terraform, and IaC-security gates. `release.yml` is a manually dispatched, build-once pipeline. It publishes images with GitHub OIDC, promotes captured digests to staging, creates and preserves the exact production plan for review, and exposes plan application only through the protected `production` GitHub Environment, an explicit dispatch input, and the exact `ALLOW_PRODUCTION_DEPLOY=YES` repository variable.

Terraform initially creates ECS services at zero tasks. The release workflow runs the one-shot migration before activating the declared task counts and exact task definitions. Later releases keep task definitions and desired counts workflow-managed so infrastructure apply cannot move application code before the migration gate.

Repository and environment variables contain non-secret identifiers such as role ARNs, regions, repository URLs, backend names, and public endpoints. No AWS access-key GitHub secret is supported. Cloud-side roles and GitHub Environment approvals must exist before release execution.

Each deployment environment supplies JSON lists for availability zones, allowed origins, trusted hosts, and exact customer role ARNs, plus the public base URL, certificate ARN, approved Bedrock model ARN/ID, and SES identity ARN. The environment-specific runtime secret contains `DATABASE_URL`, `JWT_SECRET_KEY`, and `AWS_SES_FROM_EMAIL` only when SES is enabled.

The CI workflow also contains `selfhost-fast` and `selfhost-containers` gates. They exercise the
named-Cloudflare Compose path with synthetic configuration and no real tunnel credential. Live
named-tunnel qualification remains an explicit external gate and never runs for untrusted pull
requests.
