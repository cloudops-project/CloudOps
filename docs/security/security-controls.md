# Security controls

## Identity and authorization

- Short-lived access tokens and rotating/revocable refresh sessions.
- Capability-based RBAC on routes and service operations.
- Tenant-scoped record loading with existence-hiding cross-tenant responses.
- Organization-owner-only remediation trust and sandbox approval.

## Data and secrets

- Fail-closed production settings and redacted secret representations.
- External IDs excluded from broad responses; remediation External ID disclosed only once on
  creation/rotation through privileged operations.
- AWS temporary credentials are memory-only and never job payloads or database records.
- Structured log and audit metadata sanitization; provider responses are not stored wholesale.

## AWS

- Default workload identity and STS role assumption; no static production AWS keys.
- Separate discovery and remediation roles and External IDs.
- Caller-account verification, bounded clients, static action dispatch, mandatory sandbox tags,
  immutable preconditions, drift checks, and exact postconditions.

## Application and supply chain

- Typed FastAPI schemas, Ruff, strict Mypy, frontend lint/typecheck/tests/build.
- Linear Alembic migrations tested on PostgreSQL in CI.
- Non-root containers, read-only runtime filesystems where configured, health/readiness checks.
- Gitleaks, dependency audits, image/IaC scans, workflow permission review, and immutable image
  promotion design.

## Status

Controls enforced by code and CI are implemented. Controls depending on AWS, Cloudflare, provider
accounts, alarms, restore, canary, or rollback remain **Not yet verified** operationally.

See [credential handling](credential-handling.md), [tenant isolation](tenant-isolation.md),
[AI minimization](ai-data-minimization.md), and [remediation governance](remediation-governance.md).
