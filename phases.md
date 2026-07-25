# CloudOps Delivery Phases

## Current status

Stages 1-7 are independently clean-room verified, merged, and regression-tested in `main`.
Stage 8 (dashboard read model and UI) is merged in `main` at `889660ecb8a378d107f6737b4466b70362066793`
through PR #10 (`feature/8-dashboard`) and a follow-up `feature/8-dashboard-ui` branch merge.

Stages 9-12 (notifications, remediation, scheduler, audit query/export) are implemented,
independently verified, and committed on `feature/v1-demo-completion` (HEAD `9314f06`;
migration head `0012_stage11_scheduler`), not yet merged into `main`. Stage 12 backend
verification is clean (Ruff passed; Mypy passed, 142 source files; `test_audit_api.py` 8
passed); frontend TypeScript, ESLint, Vitest (4 passed), and production build are clean.
Stages 13-17 remain planning entries, with tomorrow-demo readiness as the immediate priority.

## Stage 0 — Planning and architecture

**Status: COMPLETE**

Established product scope, monorepo structure, architecture, threat model, engineering rules,
design system, planning documents, and ADR process.

## Stage 1 — Foundation and Authentication

**Status: COMPLETE**

Delivered FastAPI/React foundations, PostgreSQL/Alembic, registration/login/logout, JWT access
tokens, rotating refresh sessions, password change, organizations, membership, invitations,
central RBAC, final-owner protection, audit events, health/readiness, and the administrative UI.
Stage 1 remains regression-tested by the current suite.

## Stage 2 — AWS Account Onboarding

**Status: COMPLETE**

Delivered organization-scoped AWS accounts, permanently reserved external IDs, generated IAM
trust and permission guidance, role ARN validation, STS `AssumeRole` plus `GetCallerIdentity`,
secure account lifecycle operations, audit events, onboarding UI, PostgreSQL lifecycle
coordination, and no credential persistence.

Final independent Stage 2 verification passed.

## Stage 3 — Asset Discovery

**Status: COMPLETE**

Delivered connected-account discovery for EC2, S3, IAM users/roles/groups/customer-managed
policies, and RDS. Collectors paginate, normalize, upsert, retain history, deactivate safely,
isolate partial failures, enforce tenant integrity, and expose bounded APIs plus asset/job UI.
Discovery is inventory only.

Final independent Stage 3 verification passed.

## Stage 4 — Deterministic Rule Engine and Findings

**Status: COMPLETE AND MERGED**

Delivered typed deterministic rules, a static registry, evaluation jobs, finding lifecycle and
suppression, PostgreSQL concurrency/tenant constraints, expanded configuration discovery,
findings/rules/evaluation APIs, structured operational logs, audit events, and frontend
findings/rule/evaluation workflows. Rules evaluate persisted data and never call AWS.

Compliance frameworks, risk scoring, AI, raw provider-event ingestion, remediation, and customer
AWS mutation are excluded.

## Stage 5 — Compliance Engine

**Status: COMPLETE, INDEPENDENTLY VERIFIED, AND MERGED**

Versioned frameworks and controls, rule-version mappings, Stage 4-backed assessments, immutable
control snapshots, tenant-safe APIs, RBAC, audit events, and compliance frontend workflows are
implemented. PostgreSQL migration `0007_stage5_compliance_engine` is the current head.
Stage 5 interprets persisted Stage 4 evidence and does not independently detect security
failures. Its initial catalog contains four controls and twelve mappings; this is neither
complete framework coverage nor certification.

## Stage 6 — Deterministic Risk Scoring

**Status: COMPLETE — INDEPENDENTLY VERIFIED, MERGED, AND REGRESSION-TESTED**

Delivered a versioned deterministic scoring policy, immutable finding/account/organization
snapshots, explicit unknown-context handling, tenant-scoped context overrides, compensating
controls, PostgreSQL concurrency and integrity controls, risk APIs, structured events, and an
accessible risk dashboard. Scores are derived only from persisted Stage 4 findings. Migration
`0008_stage6_risk_scoring` follows `0007_stage5_compliance_engine`. AI does not assign scores.

## Stage 7 — AI Explanation Assistant

**Status: COMPLETE, INDEPENDENTLY VERIFIED, MERGED, AND POST-MERGE VERIFIED**

Delivered bounded tenant-scoped advisory explanations and drafts over persisted Stage 4-6
records, with immutable source references, idempotency, quota controls, prompt-injection
defenses, redaction, deterministic mock-provider verification, AI-specific audit events, API
and frontend workflows, and the 44-step black-box release gate. AI explains existing records
only. It must not detect findings, calculate or change risk or compliance, change severity,
resolve or suppress findings, modify AWS, execute remediation, create Jira issues, or send
email. Migration `0009_stage7_ai_assistant` is the current head.

## Stage 8 — Dashboard

**Status: MERGED IN `main`**

Stage 8A delivered a read-only organization dashboard summary contract over existing Stage 2-7
authoritative records. It adds no dashboard-owned persistence and does not recalculate findings,
compliance, or risk, invoke AWS or AI providers, send notifications, execute remediation, or
create Jira issues. Stage 8B delivered the dashboard UI (`SecurityDashboardPage`) and
accessibility-aware presentation over the Stage 8A contract. Both merged into `main` at
`889660ecb8a378d107f6737b4466b70362066793` via PR #10 and a follow-up UI merge.

## Stage 9 — Notifications

**Status: COMPLETE AND COMMITTED ON `feature/v1-demo-completion` — NOT MERGED TO `main`**

Delivered: an organization-scoped `NotificationEvent` persistence model and migration
(`0010_stage9_notifications`, commit `d0b5676`); a deterministic mock/no-op delivery provider and
`NotificationService` implementing create-on-critical-finding, approve, and deliver with a
bounded 3-attempt retry state machine (commit `449e964`); an API layer
(`GET /notifications`, `GET /notifications/{id}`, `POST /notifications/{id}/approve`,
`POST /notifications/{id}/deliver`) with dedicated `NOTIFICATIONS_READ`/`NOTIFICATIONS_APPROVE`
RBAC capabilities (commit `cb42db9`); and a frontend notification history/approval page with
filtering, pagination, and role-gated approve/deliver controls (commit `d1c8733`, combined with
Stage 10 frontend). No notification is delivered without explicit human approval; the mock
provider makes no real external delivery and no network calls. AWS SES is a possible future
production provider, not yet implemented. Not yet done: merge into `main`.

## Stage 10 — Remediation Workflow

**Status: COMPLETE AND COMMITTED ON `feature/v1-demo-completion` — NOT MERGED TO `main`**

Delivered: an organization-scoped `RemediationRequest` persistence model and migration
(`0011_stage10_remediation`, commit `bf29173`); `RemediationService` and
`MockRemediationExecutor` implementing propose/approve/reject/cancel/execute with a bounded
3-attempt execution retry state machine (commit `fc8908d`); an API layer with dedicated
`REMEDIATION_READ`/`REMEDIATION_REQUEST`/`REMEDIATION_APPROVE`/`REMEDIATION_REJECT`/
`REMEDIATION_EXECUTE` RBAC capabilities (commit `8ab8c83`); a frontend remediation list/detail
workflow and a finding-detail "Propose remediation" action (commit `d1c8733`); and a later test
fixture repair (commit `8916be9`). Execution is mock/simulated only and never mutates real AWS
resources. Proposal text is generated deterministically from the existing security-rule
registry; no new detection logic exists. Not yet done: merge into `main`.

## Stage 11 — Scheduler

**Status: COMPLETE AND COMMITTED ON `feature/v1-demo-completion` — NOT MERGED TO `main`**

Delivered: `ScanSchedule`/`ScanRun` persistence and migration (`0012_stage11_scheduler`, commit
`24227ab`); `SchedulerService` and a deterministic single-tick worker
(`app/worker/scheduler_worker.py`) that delegates every run to the existing
`DiscoveryOrchestrator`/`EvaluationService` (commit `9fff532`); an API layer with dedicated
`SCHEDULE_READ`/`SCHEDULE_MANAGE` RBAC capabilities (commit `8c14b55`); and a frontend schedules
page with enable/disable, run-now, and scan-run history (commit `55c451e`). A database partial
unique index provides overlap protection (one active scan per AWS account). The worker is
explicitly not a Celery/Redis/distributed-queue or cron-daemon implementation; that
infrastructure choice remains deferred. Verified: Ruff passed; Mypy passed (140 source files);
scheduler Pytest 22 passed; migration chain upgraded cleanly to this head against the disposable
PostgreSQL verification database (`alembic check`: no new operations); frontend TypeScript,
ESLint, Vitest (5 passed), and production build all passed. Not yet done: merge into `main`.

## Stage 12 — Audit Query/Export

**Status: COMPLETE AND COMMITTED ON `feature/v1-demo-completion` — NOT MERGED TO `main`**

Adds a read/query/export layer over the existing `AuditEvent` persistence and `record_audit()`
write path; introduces no migration. Adds `GET /api/v1/audit-events` (filterable, paginated) and
`GET /api/v1/audit-events/export` (same filters, CSV, capped at 5,000 rows, synchronous) reusing
the existing `AUDIT_READ` capability, plus a frontend audit explorer page with filters,
pagination, and CSV export.

Committed in `d0d24cd` (backend query/export API and tests) and `9314f06` (frontend audit
explorer). Current verification: backend Ruff passed, Mypy passed (142 source files),
`test_audit_api.py` 8 passed, one non-blocking Starlette/httpx deprecation warning; frontend
TypeScript, ESLint, Vitest (`audit.test.tsx`) 4 passed, and production build passed.

## Stage 13 — Security Hardening

**Status: NOT STARTED**

Additional security hardening remains planned.

## Stage 14 — DevOps and IaC

**Status: NOT STARTED**

Deployment automation and infrastructure-as-code remain planned.

## Stage 15 — Testing

**Status: NOT STARTED**

Expanded release, UAT, load, and integrated testing work remains planned.

## Stage 16 — Deployment

**Status: NOT STARTED**

Production deployment remains planned.

## Stage 17 — Documentation and Demo

**Status: NOT STARTED**

Final user/developer documentation and demo materials remain planned.

## Immediate gate

1. Commit the documentation reconciliation that records Stage 12 as committed.
2. Audit the exact tomorrow-demo journey and close P0 demo gaps.
3. Add Mailpit-backed SMTP notification delivery while preserving mock delivery as the default
   for tests and ordinary local development.
4. Build the local demo stack, deterministic seed/reset flow, and black-box demo acceptance
   workflow before merging to `main`.
5. Keep deterministic detection, compliance interpretation, risk scoring, advisory AI
   explanation, dashboard visualization, mock notification delivery, mock remediation
   execution, and the scheduler's delegation-only design separate and unchanged by later stages.
6. Merging `feature/v1-demo-completion` into `main` is tracked separately from stage
   implementation and requires its own explicit review/authorization step.
