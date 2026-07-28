# Secrets Management

## Purpose and audience

Developers, platform engineers, and security reviewers use this policy to prevent secret creation, storage, logging, and transmission mistakes.

Use AWS Secrets Manager or an approved equivalent for database, provider, signing, and application
secrets. Terraform defines ECS secret injection, and the release workflow uses GitHub OIDC. These
definitions are locally validated but not deployed. Customer AWS keys are never requested or
stored; STS credentials remain memory-only.

Classify external IDs as sensitive connection values: encrypt/protect them, restrict retrieval to the assume-role path, redact them everywhere, and rotate through an audited connection workflow. `.env` is local-only, ignored, and contains no shared production values; `.env.example` lists names without values.

Prohibit secrets in source, images, Terraform variables/state without protected backends, logs, errors, tickets, analytics, prompts, tests, or screenshots. Add secret scanning/push protection when GitHub is configured. Rotation/revocation has an owner, overlap strategy, provider procedure, validation, and incident trigger.

External work: provision stores/keys, populate secrets out of band, exercise rotation/break glass,
and retain state-backend/IAM evidence. Terraform existence does not prove operation.
