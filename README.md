# CloudOps

CloudOps is an AWS-focused, multi-tenant SaaS platform. Stages 1–4 are merged in `main`:
identity and tenancy, secure AWS onboarding, normalized discovery, and deterministic findings.
Stage 5 compliance assessments are being completed on `feature/5-compliance-engine`. Risk
scoring, AI, notifications, remediation, raw event ingestion, customer AWS mutation, and Stage 6
functionality are not implemented.

## Technology stack

- API: Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, Pydantic 2, Argon2, PyJWT
- Web: React, TypeScript, Vite, Tailwind CSS, React Router, TanStack Query, React Hook Form, Zod, Lucide
- Tests: Pytest/coverage and Vitest/Testing Library

## Local setup

1. Copy `.env.example` to an untracked `.env` and provide development values. Never commit it.
2. Create PostgreSQL database `cloudops` and set `DATABASE_URL`.
3. Install and migrate the API:

   ```powershell
   cd apps/api
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
   .\.venv\Scripts\alembic.exe upgrade head
   .\.venv\Scripts\uvicorn.exe app.main:app --reload
   ```

4. Install and run the web app in another terminal:

   ```powershell
   cd apps/web
   npm install
   npm run dev
   ```

## Quality commands

```powershell
cd apps/api
.\.venv\Scripts\ruff.exe format --check app
.\.venv\Scripts\ruff.exe check --no-cache app
.\.venv\Scripts\mypy.exe --cache-dir "$env:TEMP\cloudops_mypy_cache" app
$env:COVERAGE_FILE="$env:TEMP\cloudops_stage1_coverage"
.\.venv\Scripts\pytest.exe --cov=app --cov-report=term-missing

cd ..\web
npm run format:check
npm run lint
npm run typecheck
npm run test
npm run build
```

## Security model

The browser keeps the short-lived access JWT in memory. The opaque refresh token is a scoped HttpOnly cookie; only its SHA-256 hash is stored. Every use rotates the session, and replay revokes the whole token family. Password changes revoke all refresh sessions. Organization access always requires an active server-side membership. Owner/admin governance follows the [RBAC policy](docs/architecture/api-design.md), including final-owner protection.

PostgreSQL row locks serialize refresh rotation, invitation acceptance, and final-owner changes. Admins manage non-owner memberships only; only an owner may govern an existing owner.

Development/testing may return a raw invitation token because email delivery is deferred. Production never returns it. CloudOps never logs passwords, raw tokens, cookie values, or authorization headers.

## Stage 2 AWS onboarding

Set `AWS_TRUSTED_PRINCIPAL_ARN` to the CloudOps AWS principal. Organization owners/admins can register a 12-digit AWS account ID, receive a unique external ID plus trust and `SecurityAudit` policy guidance, add a matching role ARN, and validate with STS AssumeRole followed by GetCallerIdentity. CloudOps never accepts or persists access keys or temporary credentials. See [AWS account onboarding](docs/architecture/aws-account-onboarding.md).

Issued external IDs are copied into an immutable reservation table and remain unavailable after
account deletion. PostgreSQL row locks plus a validation operation token serialize account
updates, disconnects, deletion, and STS validation without holding a database lock during the
network call.

## Stage 3 asset discovery

Connected accounts can inventory EC2 instances, S3 buckets, IAM users, roles, groups and
customer-managed policies, plus RDS instances. Regional collectors use
`AWS_DISCOVERY_REGIONS`; IAM and S3 are global. Assets are normalized and upserted, and a
successful collector marks missing resources inactive instead of deleting history.

## Stage 5 compliance assessments

Stage 5 maps versioned deterministic Stage 4 rules to versioned CIS AWS, NIST CSF, ISO/IEC
27001, and PCI DSS controls. Assessments create immutable historical control snapshots with
`PASS`, `FAIL`, `NOT_ASSESSED`, or `ERROR` status. Missing or version-mismatched rule evidence
never becomes `PASS`; active suppressed findings remain failures. Catalog descriptions are
short CloudOps-authored summaries with official references, not reproduced framework prose.

Owner, admin, security analyst, and cloud engineer roles may start discovery; every active
member may view bounded, filterable asset and job lists. Per-account locking and a PostgreSQL
partial unique index prevent overlapping jobs. Failed collectors cannot stale their previous
assets. Temporary STS credentials remain in memory only.

Composite PostgreSQL foreign keys ensure an asset or discovery job cannot reference an AWS
account owned by another organization. Check constraints enforce seen-time ordering, nonnegative
job counts, and valid job status/timestamp combinations. Boto3 clients use environment-driven,
bounded connect/read timeouts and standard/adaptive bounded retries.

## Stage 4 deterministic findings

Stage 4 extends inventory with EC2 security groups and volumes, S3 configuration signals, IAM
security metadata, RDS configuration, CloudWatch alarms and log groups, and CloudTrail
configuration. Boto3 remains confined to discovery. Rules evaluate persisted normalized data
without network or filesystem access.

The typed rule pack covers high-confidence EC2, S3, IAM, RDS, CloudWatch, CloudWatch Logs, and
CloudTrail checks. Results are `passed`, `failed`, `not_applicable`, or `error`; insufficient
evidence never passes and never resolves an existing finding. Findings support open, resolved,
and suppressed states with stable identity, lifecycle versions, bounded evidence, audit events,
and stale-evaluation rejection.

## Documentation

Start with [NEW_CHAT_CONTEXT.md](NEW_CHAT_CONTEXT.md), the [API design](docs/architecture/api-design.md), [database design](docs/architecture/database-design.md), [design system](docs/design/design-system.md), [phase plan](docs/planning/phases.md), and [project memory](docs/planning/project-memory.md). ADR-007 through ADR-010 record the authorized Stage 1 changes from the Stage 0 baseline.

## Disposable PostgreSQL verification

```powershell
docker compose -f compose.verify.yml up -d --wait
cd apps/api
$env:DATABASE_URL="postgresql+psycopg://cloudops:cloudops_test_password@localhost:5433/cloudops_test"
$env:POSTGRES_TEST_DATABASE_URL=$env:DATABASE_URL
$env:JWT_SECRET_KEY="replace-with-a-long-test-secret-for-verification"
$env:APP_ENV="testing"
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\alembic.exe check
.\.venv\Scripts\pytest.exe app\tests\test_postgres_concurrency.py -v
cd ..\..
docker compose -f compose.verify.yml down
```

The Compose database uses tmpfs and is verification-only. Never point these tests at shared, staging, UAT, or production databases.

## Known Stage 1 limitations

- No password reset, email verification delivery, MFA, social login, or SSO.
- Invitation email delivery and distributed rate limiting are deferred.
- PostgreSQL is the production database; SQLite is used only for isolated tests.
- Cloud infrastructure, deployment automation, risk scoring, AI assistance, notifications,
  remediation, and Stage 6 remain later work. Deterministic findings and Stage 5 compliance
  assessments are implemented.
