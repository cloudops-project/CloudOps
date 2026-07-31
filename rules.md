# CloudOps Development Rules

These rules govern AI-assisted and human changes. See [PRD.md](PRD.md),
[architecture.md](architecture.md), [phases.md](phases.md), and [memory.md](memory.md). The local
demo additionally follows the constraints in [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md) and
[SECURITY_MODEL.md](SECURITY_MODEL.md); demo-only settings are refused outside development by
`Settings.model_post_init` (see `apps/api/app/core/config.py`).

## Approved stack

- Backend: Python 3.12+, FastAPI, Pydantic Settings, SQLAlchemy 2, Alembic, PostgreSQL, Boto3.
- Frontend: React, TypeScript, Vite, Tailwind, TanStack Query, React Hook Form, Zod.
- Runtime: Docker; AWS target is ECS/Fargate, RDS PostgreSQL, ALB/WAF, KMS, Secrets Manager,
  CloudWatch, and ECR.
- Infrastructure: Terraform 1.10.5-compatible configuration.
- Durable jobs: PostgreSQL. Do not introduce a second broker/state store without an ADR.

## Coding and typing

- Keep functions cohesive, dependencies explicit, and side effects bounded.
- New Python code must pass Ruff and strict Mypy.
- New TypeScript must pass ESLint and both application/node typechecks.
- Use typed schemas at trust boundaries; do not pass unvalidated dictionaries through services.
- Preserve deterministic ordering and UTC-aware timestamps.
- Do not weaken errors, validation, or types to make tests pass.

## Testing

- Add unit tests for logic, authorization, redaction, failure, and boundary cases.
- Use PostgreSQL integration tests for constraints, concurrency, leases, and migrations.
- Use at least two organizations for tenant-isolation regressions.
- Use fakes or Botocore Stubber; automated tests must not call live AWS.
- Run affected tests before the bounded full gates.
- Never claim a test passed without current retained evidence.
- Live AWS tests require explicit opt-in and an approved sandbox.

## Migrations and database transactions

- Alembic history must remain linear with one head.
- Never modify historical migrations merely to satisfy formatting.
- Use additive expand-and-contract migrations; deploy compatible code before destructive cleanup.
- Test clean upgrade and upgrade from the prior schema.
- Runtime and migration identities must have distinct least privileges.
- Keep queue acquire/complete/fail operations transactional and short.
- Use row locks/`SKIP LOCKED` only with explicit concurrency tests.
- Never hold a database transaction open across a slow provider call unless the existing design
  explicitly proves it safe.

## Tenant isolation and RBAC

- Never weaken tenant isolation.
- Scope tenant-owned reads/writes by `organization_id` or a parent join in the same query.
- Do not rely on post-fetch tenant checks.
- Do not disclose whether another tenant's identifier exists.
- Enforce RBAC independently from tenant scoping.
- Workers must reload references with tenant scope; job payloads are not authorization.
- Platform-admin status is not an automatic tenant bypass.
- Preserve organization-consistent foreign keys, uniqueness, indexes, and cascade behavior.

## Detection, AI, and remediation boundary

- Deterministic rules detect findings.
- Never allow AI to detect or approve remediation.
- AI may explain, summarize, prioritize, and draft content only from authorized persisted sources.
- Treat provider output as untrusted; validate structured output and bound size/time/retries.
- AI output must not change finding, compliance, risk, approval, or execution state.
- Never execute arbitrary user-supplied AWS operations.
- Remediation actions must be static, typed, allowlisted, versioned, previewed, approved, and
  revalidated against an immutable snapshot.
- Current remediation remains dry-run/mock only. A live executor requires a separate threat model,
  least-privilege mutation role, sandbox proof, action-specific rollback, and explicit approval.

## AWS identity and providers

- Never store long-lived AWS access keys.
- Use the default credential provider chain and workload identity in production.
- Reject static AWS credential environment variables in production.
- Customer access uses STS AssumeRole, External ID, account verification, bounded sessions, and
  memory-only credentials.
- Cache credentials only with tenant/account-safe keys and refresh before expiry without stampedes.
- Bedrock model/region must be allowlisted and task-role permission narrowly scoped.
- Bedrock cannot become the detection or authorization engine.
- SES requires an approved identity, bounded recipients/body, header validation, approval recheck,
  sanitized errors, and bounce/complaint monitoring.
- Do not send a notification without explicit authorization and an approved synthetic/live gate.

## Secrets and logging

- Never commit secrets.
- Secret settings use `SecretStr` or equivalent redaction.
- Never log credentials, tokens, cookies, webhook URLs, private keys, database connection strings,
  provider bodies, or secret values.
- Job payloads contain identifiers and bounded non-secret references only.
- Frontend `VITE_` variables are public build-time configuration and must never hold secrets.
- Audit metadata and API errors must be sanitized.
- Use managed secret injection; do not write generated secret files.

## API behavior

- Authenticate before authorization; authorize before mutation.
- Use stable typed error codes and non-disclosing cross-tenant responses.
- Apply bounded pagination, input sizes, timeouts, retries, and rate limits.
- Separate liveness from dependency-backed readiness.
- Do not expose internal exceptions or provider responses.

## Durable jobs

- PostgreSQL remains the durable source of truth.
- Enqueue must be tenant-scoped and idempotent.
- Acquisition uses leases and generations; completion/failure requires the active lease token.
- Workers heartbeat, reject stale ownership, use bounded retry/backoff, and dead-letter exhausted
  work.
- Requeue/cancel requires capability checks and audit evidence.
- Never share an unkeyed global credential/provider cache across tenants.

## Docker

- Use current, narrowly pinned supported bases and run final containers as non-root.
- Keep runtime images minimal; do not copy development credentials or local environments.
- Use read-only root filesystems where configured and dependency-aware health checks.
- Build once, scan, and promote immutable image digests.
- Never push an image without explicit authorization.

## Terraform

- Format and validate bootstrap, staging, and production roots.
- Keep staging and production state/configuration separated.
- Separate runtime, migration, publish, and deployment roles.
- Use least privilege, KMS, private subnets, flow/access logs, WAF, deletion protection, and managed
  secrets as defined.
- Do not apply Terraform or contact AWS without explicit authorization.
- Checkov exceptions must be resource-specific, justified, and reviewed; no broad suppressions.
- Do not place secret values in plans, examples, outputs, or state documentation.

## CI/CD

- CI must gate backend, frontend, migrations, containers, dependencies, secrets, and Terraform.
- GitHub Actions AWS access uses OIDC; no long-lived AWS secrets.
- Build once and promote immutable image digests.
- Pull requests cannot assume production roles.
- Production requires a protected environment, exact reviewed plan/digests, and explicit gate.
- Workflow existence is not deployment evidence.

## Git

- Inspect status/diff before staging.
- Stage explicit paths only, for example:
  `git add -- docs/file-one.md docs/file-two.md`
- Never use `git add .`.
- Never use `git add -A`.
- Never stage generated logs, credentials, local environments, coverage, or dependency directories.
- Never force-push shared branches.
- Do not push directly to shared branches; use reviewed branches/pull requests.
- Do not reset, clean, amend, merge, rebase, push, or tag without scope and authorization.
- Review `git diff --check`, conflicts, untracked files, and staged diff before committing.

## Protected files

- `CLAUDE.md` must remain untouched.
- `compose.aws.override.yml` must remain untouched.
- Do not read, summarize, edit, stage, delete, or display either file.

## Documentation

- Source code and migrations outrank prose.
- Distinguish implemented/local verification, implemented/external validation pending, and
  deferred work.
- Never claim external validation without evidence.
- Never claim production readiness, deployment, canary, rollback, restore, provider delivery, or
  UAT based only on definitions.
- Update `NEW_CHAT_CONTEXT.md` after major architectural changes.
- Update `memory.md` after each substantial coding session.
- Validate links, paths, commands, settings names, workflow names, and migration head.

## Production authorization gate

## Self-hosting safety

- Organization self-hosting exposes only Nginx through the named Cloudflare Tunnel; API and
  PostgreSQL never publish host ports.
- Generated self-host secrets and backups remain under ignored `.cloudops/` paths, are never
  printed, and remain stable across restart and update.
- Self-host `down` preserves data. Destruction requires the exact documented confirmation phrase.

- Never deploy production without explicit authorization.
- Required evidence includes passing CI, reviewed Terraform plan, protected environment approval,
  staging UAT, exact digests, migration proof, observability, restore/rollback rehearsal, and
  accepted residual risk.
- Live AWS tests and notifications require explicit opt-in, approved account/recipients, and
  retained audit evidence.
