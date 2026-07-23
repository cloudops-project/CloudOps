# CloudOps Portable Repository Context

Use this file to resume work in a fresh AI chat. Detailed documents remain authoritative. Update this file after architectural changes and `docs/planning/project-memory.md` after each substantial coding session.

## Purpose and current status

CloudOps is an AWS-focused multi-tenant SaaS foundation for secure AWS onboarding and normalized
asset inventory. Stages 1, 2, and 3 are implemented and independently verified by the final
repository review.
Stage 3 is inventory only. Stage 4 rule evaluation and all findings, compliance, risk, AI,
notification, and remediation capabilities remain deferred.
Stage 4 has not started.

## Source-of-truth documents

- `PRD.md`: current product scope and user journey
- `architecture.md`: current executable architecture and schema
- `design.md`: current frontend and design-system behavior
- `rules.md`: development, security, database, and testing rules
- `phases.md`: stage status and future sequence
- `memory.md`: current working state and next task

Detailed documents under `docs/` provide supporting depth. Resolve any contradiction before
changing code.

## Repository map

```text
apps/api/        FastAPI application, migration, tests
apps/web/        React administration application and tests
apps/worker/     Later-stage placeholder
docs/            Product, architecture, engineering, design, planning, operations, ADRs
infrastructure/  Later-stage infrastructure placeholders
packages/        Shared-package placeholders
tests/           Cross-application test placeholders
```

## System mind map

```mermaid
mindmap
  root((CloudOps))
    Web
      React and TypeScript
      Tailwind design system
      In-memory access token
      Protected admin routes
    API
      FastAPI
      Authentication services
      Organization services
      Invitation services
      AWS onboarding service
      Discovery orchestrator
      Central RBAC
    Database
      Users
      Organizations
      Memberships
      Invitations
      Refresh sessions
      Audit events
      AWS accounts
      External ID reservations
      Assets
      Discovery jobs
    AWS
      STS AssumeRole
      EC2 discovery
      S3 discovery
      IAM discovery
      RDS discovery
    Security
      Argon2
      Signed access JWT
      Opaque rotating refresh cookie
      Tenant isolation
      Last-owner protection
      Permanent external IDs
    Future
      Deterministic rules
      Findings and risk
      Compliance and findings
      Advisory AI
      Approved remediation
```

## Application flow

```mermaid
flowchart LR
  B[React browser] -->|Bearer access JWT| R[FastAPI routes]
  B -->|HttpOnly refresh cookie| A[Auth service]
  R --> D[Dependencies]
  D --> S[Application services]
  S --> P[Central RBAC policy]
  S --> Q[Tenant-scoped repository]
  A --> Q
  Q --> DB[(PostgreSQL)]
  S --> E[Audit events]
  A --> E
  S --> STS[AWS STS AssumeRole]
  STS --> C[EC2, S3, IAM, and RDS collectors]
  C --> Q
```

Routes contain validation and HTTP mapping only. Services own transactions and invariants. Repositories own persistence and always include organization scope for tenant data.

## Main files

- `apps/api/app/main.py`: middleware, errors, CORS, trusted hosts, routes.
- `apps/api/app/services/`: authentication, organization, invitation, onboarding, and discovery
  workflows.
- `apps/api/app/security/`: Argon2, JWT/opaque-token helpers, RBAC and rate-limit abstraction.
- `apps/api/app/models/`: identity, AWS onboarding/reservations, assets, and discovery jobs.
- `apps/api/alembic/versions/0004_verification_repairs.py`: current migration head; reservation
  backfill, tenant foreign keys, lifecycle constraints, and AWS-account validation-operation
  columns.
- `apps/web/src/auth/AuthProvider.tsx`: session restoration and memory-only access token.
- `apps/web/src/api/client.ts`: credentialed API client and single-flight refresh.
- `apps/web/src/pages/`: Stage 1 administration, Stage 2 AWS onboarding, and Stage 3 inventory views.
- `docs/architecture/decisions/ADR-007...ADR-011`: active Stage 1/Stage 2 decisions.

## Data and relationships

Users have globally unique normalized email addresses. Organizations have unique slugs.
Memberships, invitations, refresh families, and audit events retain the Stage 1 design. Every
issued AWS external ID is permanently retained in `aws_external_id_reservations`. Composite
foreign keys ensure every asset and discovery job has the same organization as its AWS account.
Database checks protect asset seen-time ordering and discovery-job counters and timestamps.

## API

- Auth: register, login, refresh, logout, me, change-password.
- Organizations: create, list, get, update.
- Members: list, change role/status, remove.
- Invitations: create, list, cancel, accept.
- Audit: organization-scoped recent events.
- AWS onboarding: create, list, get, update, validate, disconnect, and delete accounts.
- Discovery: start connected-account inventory; list/detail jobs; list/filter/detail/summarize
  normalized assets.
- Process: `/health` and database-backed `/ready`.

All application APIs are under `/api/v1`; health probes are root paths.

## Authentication and authorization

The API returns a short-lived signed access JWT. The web app stores it only in memory. The opaque refresh token is stored in an HttpOnly cookie scoped to `/api/v1/auth`; only SHA-256 hashes are persisted. Rotation locks the old session through replacement and commit, then revokes it and links its replacement. Reuse revokes the family. Password changes revoke all sessions. Failed browser refresh clears both the memory token and authenticated-user state.

Organization operations validate active membership and a centralized capability map. Admins cannot assign owner or govern an existing owner. The final active owner cannot be demoted, suspended, or removed; PostgreSQL row locks preserve this invariant under concurrency. Platform-admin status never implicitly bypasses tenant checks.

## Environment variable names

`APP_ENV`, `APP_NAME`, `API_V1_PREFIX`, `DATABASE_URL`, `POSTGRES_TEST_DATABASE_URL`,
`JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`,
`REFRESH_TOKEN_EXPIRE_DAYS`, `INVITATION_TOKEN_EXPIRE_HOURS`, `CORS_ALLOWED_ORIGINS`,
`TRUSTED_HOSTS`, `COOKIE_SECURE`, `COOKIE_SAMESITE`, `COOKIE_DOMAIN`, `LOG_LEVEL`,
`FRONTEND_URL`, `AUTH_RATE_LIMIT_PER_MINUTE`, `AWS_TRUSTED_PRINCIPAL_ARN`,
`AWS_ROLE_SESSION_NAME`, `AWS_DISCOVERY_REGIONS`, `AWS_CONNECT_TIMEOUT_SECONDS`,
`AWS_READ_TIMEOUT_SECONDS`, `AWS_MAX_RETRY_ATTEMPTS`, `AWS_RETRY_MODE`,
`VITE_API_BASE_URL`.

Never put values or secrets in this file.

## Commands

See the root README and app READMEs for install, migration, lint, type-check, test, and build commands.

## Completed capabilities

Registration; login/logout; access JWT; rotating/revocable refresh sessions; password change; organizations; membership; invitation create/list/cancel/accept; permitted role assignment; suspension/reactivation/removal; final-owner protection; tenant isolation; audit events; health/readiness; Stage 1 administration UI; migration; backend/frontend tests.

Stage 2 adds account lifecycle APIs, permanently reserved external IDs, trust and SecurityAudit
guidance, temporary-credential-only STS validation, serialized lifecycle transitions, audit
events, and owner/admin frontend flows. Stage 3 adds paginated EC2/S3/IAM/RDS collectors,
normalized historical inventory, partial-failure isolation, bounded APIs, PostgreSQL-safe
concurrency, and inventory/job UI.

## Known limitations and deferred work

Email delivery, password reset, email-verification delivery, MFA, OIDC/SSO, distributed rate
limiting, PostgreSQL RLS, production deployment, and live-AWS validation remain deferred.
Discovery is synchronous and automated tests use deterministic AWS doubles. Rules, findings,
compliance, risk, scheduler, AI, notifications, and remediation are Stage 4+. Development/testing
returns invitation tokens temporarily; production does not.

## Architecture decisions

- ADR-007 consolidates the historical authentication phase into authorized Stage 1.
- ADR-008 supersedes Stage 0's undecided OIDC provider for Stage 1 with local JWT plus opaque refresh sessions; OIDC remains future work.
- ADR-009 supersedes Material UI as the active frontend choice with Tailwind CSS.
- ADR-010 establishes CloudOps as the current product name while retaining CloudFix in historical records.
- ADR-011 establishes AWS Account Onboarding as Stage 2 and supersedes only ADR-007's reserved numbering.

## Current migration and worktree

The linear migration chain is `0001_stage1 -> 0002_stage2 -> 0003_stage3 ->
0004_verification_repairs`. The current branch is `feature/3-asset-discovery`. At the start of
this synchronization, the Stage 1–3 implementation candidate was staged for controlled review
but not committed or pushed; documentation synchronization remained unstaged.

The final independent review reproduced 55 passing backend tests at 95% coverage and 34 passing
frontend tests, with PostgreSQL migration/concurrency checks and all documented quality gates
passing.

## Current priorities

1. Commit and push the verified Stage 1–3 baseline.
2. Submit it to `main` through the required pull-request review.
3. Merge only after independent human approval.
4. Keep `develop` unchanged unless repository owners explicitly designate it for synchronization.

Do not begin Stage 4.

## HOW TO START A NEW AI SESSION

Read all attached project documents first and treat them as the source of truth. Before changing
code, summarize:

- the project goal;
- the architecture;
- the current implementation;
- known issues and limitations; and
- the next task.

Identify and resolve contradictions or missing information before proceeding. Do not modify code
until those contradictions are resolved.
