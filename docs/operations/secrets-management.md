# Secrets Management

## Purpose and audience

Developers, platform engineers, and security reviewers use this policy to prevent secret creation, storage, logging, and transmission mistakes.

Use AWS Secrets Manager or an equivalent approved store for database, OIDC client, AI, Jira, Teams/email, signing, and application secrets. Workloads receive least-privilege identity and fetch values at runtime; GitHub Actions should later use OIDC rather than long-lived AWS keys. Customer AWS access keys are never requested or stored. STS session credentials remain memory-only and expire.

Classify external IDs as sensitive connection values: encrypt/protect them, restrict retrieval to the assume-role path, redact them everywhere, and rotate through an audited connection workflow. `.env` is local-only, ignored, and contains no shared production values; `.env.example` lists names without values.

Prohibit secrets in source, images, Terraform variables/state without protected backends, logs, errors, tickets, analytics, prompts, tests, or screenshots. Add secret scanning/push protection when GitHub is configured. Rotation/revocation has an owner, overlap strategy, provider procedure, validation, and incident trigger.

Open questions: selected store, key ownership, rotation intervals, break-glass recovery, local secret delivery, and state-backend controls.
