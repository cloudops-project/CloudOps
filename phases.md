# CloudOps Delivery Phases

## Current status

Stages 1-7 are independently clean-room verified, merged, and regression-tested in `main`.
Stage 8 (dashboard read model and UI) is merged in `main` at `889660ecb8a378d107f6737b4466b70362066793`
through PR #10 (`feature/8-dashboard`) and a follow-up `feature/8-dashboard-ui` branch merge.
Stage 9 (notifications) has a complete backend (persistence, service, and API layer) on
`feature/9-notifications` at commits `d0b5676`, `449e964`, and `cb42db9`, not yet merged to
`main`. Stage 9 frontend (notification history/approval UI) is not yet implemented. Stages 10-17
remain not-started planning entries.

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

**Status: BACKEND COMPLETE ON `feature/9-notifications` — NOT MERGED; FRONTEND NOT STARTED**

Delivered: an organization-scoped `NotificationEvent` persistence model and migration
(`0010_stage9_notifications`, commit `d0b5676`); a deterministic mock/no-op delivery provider and
`NotificationService` implementing create-on-critical-finding, approve, and deliver with a
bounded 3-attempt retry state machine (commit `449e964`); and an API layer
(`GET /notifications`, `GET /notifications/{id}`, `POST /notifications/{id}/approve`,
`POST /notifications/{id}/deliver`) with dedicated `NOTIFICATIONS_READ`/`NOTIFICATIONS_APPROVE`
RBAC capabilities (commit `cb42db9`). No notification is delivered without explicit human
approval; the mock provider makes no real external delivery. Not yet implemented: a frontend
notification history/approval page, and merge into `main`.

## Stage 10 — Remediation Workflow

**Status: NOT STARTED**

Governed remediation and customer-resource mutation are not implemented.

## Stage 11 — Scheduler

**Status: NOT STARTED**

Scheduling, queues, and background-worker orchestration are not implemented.

## Stage 12 — Audit Logs

**Status: NOT STARTED**

The extended audit timeline/archive is planned; current audit controls must not be described as
absolutely immutable.

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

1. Complete Stage 8A dashboard read-model verification on `feature/8-dashboard`.
2. Keep dashboard work read-only over existing Stage 2-7 records.
3. Do not begin Stage 8B UI work until Stage 8A is reviewed or separately authorized.
4. Do not begin Stage 9 notifications.
5. Keep deterministic detection, compliance interpretation, risk scoring, advisory AI
   explanation, and dashboard visualization separate.
