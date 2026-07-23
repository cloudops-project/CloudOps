# CloudOps Project Memory

## Last updated

2026-07-23 — documentation synchronization on `feature/3-asset-discovery`.

## Current implementation

Stage 1 is implemented and regression-tested. Stage 2 AWS onboarding and Stage 3 asset discovery
are implemented and independently verified. Stage 4 has not started.

Alembic revision `0004_verification_repairs` follows `0003_stage3`. It adds immutable
external-ID reservation history, AWS-account lifecycle coordination fields, database-enforced
account/organization consistency for assets and jobs, asset timestamp checks, nonnegative job
counts, and job status/timestamp invariants. Existing account IDs and external IDs are
backfilled without change.

## Verification repairs

- External IDs remain globally reserved after account deletion and collision handling relies on
  a PostgreSQL unique constraint.
- Account lifecycle mutations use tenant-scoped locks. Validation uses an operation token so an
  older STS result cannot overwrite a newer mutation.
- Discovery uses composite tenant foreign keys, lifecycle checks, deterministic lock ordering,
  and terminal-state guards.
- Every boto3 client receives explicit environment-driven timeouts and bounded retry policy.
- Backend tests now cover all IAM pagination, invalid account states, authenticated discovery
  APIs, filters, stable pagination, details, RBAC, tenant isolation, and PostgreSQL races.
- Frontend discovery requires an accessible confirmation and covers filters, pagination,
  states, RBAC, focus behavior, and escaped metadata.

Exact final test totals and quality-gate results belong in the repair report after all commands
have been rerun; older completion-report counts are not current evidence.

## Decisions

- ADR-007 through ADR-010 remain the Stage 1 decisions.
- ADR-011 supersedes only the reserved Stage 2 numbering and establishes AWS account onboarding as Stage 2.
- `AWS_TRUSTED_PRINCIPAL_ARN` is deployment configuration. Customers manually create `CloudOpsReadOnlyRole` and attach AWS managed `SecurityAudit` during this stage.

## Known limitations

Stage 2 validation remains synchronous and does not deliver CloudFormation/Terraform onboarding
templates, external-ID rotation, background validation, or IAM resource creation. Stage 3
discovery remains synchronous and uses an explicit configured region list. Automated provider
tests use deterministic AWS doubles; controlled live-AWS validation remains operational work.

## Next task

Commit and push the verified Stage 1–3 baseline, then open a pull request to `main` and obtain the
required independent human approval. Do not begin Stage 4 rule evaluation, findings, posture,
compliance, risk, notifications, AI, remediation, or deployment infrastructure.

## Stage 3 implementation snapshot

Alembic `0003_stage3` adds `assets` and `discovery_jobs`; `0004_verification_repairs` adds the
external-ID history and database integrity/concurrency controls. EC2, S3, IAM, and RDS
collectors normalize paginated inventory. Repeated runs preserve
first-seen history, update current values, and safely deactivate missing assets only after that
collector succeeds. The UI provides asset filters/details and discovery job status/results.
Temporary AWS credentials are not persisted, and no Stage 4 security analysis exists.
