# Implementation Phases

## Current delivery status

Stages 1-8 are independently clean-room verified, merged, and regression-tested in `main` at
`889660ecb8a378d107f6737b4466b70362066793`. Stages 9-12 (notifications, remediation,
scheduler, audit query/export) are implemented, independently verified, and committed on
`feature/v1-demo-completion` (migration head `0013_demo_notification_delivery` after the
demo-readiness migration), not yet merged into `main`. Stages 13-17 remain planning entries,
with tomorrow-demo readiness as the immediate priority.

## Purpose and audience

The five-member team and stakeholders use this dependency-ordered roadmap for planning after Stage 0 approval. Sequence is proposed; dates and performance claims require estimation and evidence.

**Owners:** M1 project/architecture, M2 backend/platform, M3 AWS/security engine, M4 frontend/design, M5 DevOps/quality/operations. “Accept” means acceptance criteria; every stage also requires the [definition of done](../engineering/definition-of-done.md).

| Stage                           | Objective; dependencies                                                                     | Deliverables; acceptance criteria                                                                                                                                                                                                                                       | Risks; owner / reviewer; demo milestone                                                    |
| ------------------------------- | ------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| 0 Planning/research             | Agree scope, architecture, governance; none                                                 | PRD, scope, personas, architecture/data/threat designs, design system/wireframes, rules, Git/task/team/risk plans; substantive review and explicit approval                                                                                                             | Unresolved assumptions; M1 / all; review walkthrough                                       |
| 1 Foundation and authentication | Establish executable foundations plus identity and organization isolation; approved Stage 0 | FastAPI/React setup, PostgreSQL/Alembic, configuration, JWT/refresh sessions, registration/login, organizations, membership/invitations, RBAC, Stage 1 admin UI, audit-ready auth events, and quality checks; two-organization isolation and token lifecycle tests pass | Tooling drift and broken access control; M2+M5 / M1; registration-to-admin two-tenant demo |
| 2 AWS onboarding                | Securely connect/disconnect organization AWS accounts; independently verified Stage 1       | Account record, unique external ID, generated trust/policy instructions, role ARN validation, STS AssumeRole + GetCallerIdentity validation, owner/admin UI and audit events; no long-lived keys and failure paths verified                                             | IAM excess/confused deputy; M3 / M1+M5; connect/validate/disconnect demo                   |
| 3 Asset discovery               | Build normalized EC2/S3/IAM/RDS inventory; connected Stage 2 account                        | Paginator-aware collectors, normalized assets, discovery jobs, safe stale lifecycle, partial failures, bounded inventory UI, tenant/RBAC/concurrency tests                                                                                                              | Throttling/incomplete inventory; M3 / M2+M5; sandbox inventory                             |
| 4 Rule engine                   | Reproducibly evaluate versioned rules; 3                                                    | Rule schema/loader/evaluator/versioning and approved EC2/S3/IAM initial rules; fixtures prove deterministic results                                                                                                                                                     | false/context signals, policy parsing; M3 / M1+M5; fixture + sandbox findings              |
| 5 Compliance                    | Explain reviewed control relationships; verified Stage 4                                    | **Complete, independently verified, and merged.** Versioned catalogs, rule-version mappings, immutable assessments, traceability, API/UI, PostgreSQL and accessibility verification; no certification claim                                                             | licensing/overclaiming; M1+M3 / M5; control drill-down                                     |
| 6 Deterministic risk scoring    | **Complete, independently verified, merged, and regression-tested**                         | Versioned deterministic scoring of persisted Stage 4 findings, immutable snapshots, bounded context and compensating controls; AI does not assign risk                                                                                                                  | scope drift/misleading scores; M1+M3 / all; verification gate                              |
| 7 AI explanation assistant      | **Complete, independently verified, merged, and post-merge verified**                       | Explain existing findings and business impact; draft remediation, executive, Jira, and email text. AI never detects, scores, mutates, executes, sends, or creates external tickets                                                                                      | disclosure/hallucination/cost; M1+M2 / M3+M5; AI on/off comparison                         |
| 8 Dashboard                     | **Complete and merged**; Stage 7 product/docs synchronized and owner-authorized             | Read-only dashboard summary API and UI over existing AWS account, asset, finding, compliance, risk, and AI-era records                                                                                                                                                     | dense data/misleading metrics; M4 / M1+M5; analyst journey                                 |
| 9 Notifications                 | **Complete, independently verified, and committed on `feature/v1-demo-completion` (not merged into `main`)**; 5, 7–8 | Approval-gated critical-finding notification pipeline with a deterministic mock/no-op provider only; bounded retries; no real email/collaboration/ticketing delivery                                                                                                    | spam/token/webhook risk; M2 / M1+M5; finding-to-notification                               |
| 10 Remediation workflow         | **Complete, independently verified, and committed on `feature/v1-demo-completion` (not merged into `main`)**; 2, 5, 9 | Approval-governed mock remediation lifecycle and deterministic mock execution; no real customer-resource mutation in Version 1                                                                                                                                          | customer impact/duplicate action; M3 / M1+M2+M5; approve-remediate-verify                  |
| 11 Scheduler                    | **Complete, independently verified, and committed on `feature/v1-demo-completion` (not merged into `main`)**; 3–5, 10 | Deterministic single-tick scheduler foundation delegating to existing discovery/evaluation; overlap protection; not a distributed queue or cron daemon                                                                                                                 | floods/starvation; M2+M5 / M3; scheduled and recovered run                                 |
| 12 Audit Logs                   | **Complete, independently verified, and committed on `feature/v1-demo-completion` (not merged into `main`)**; prior security paths | Read/query/export layer over the existing `AuditEvent` table; no new migration; current controls must not be called absolutely immutable                                                                                                                                | gaps/tampering; M1+M5 / all; incident evidence trace                                       |
| 13 Security Hardening           | **Not started**; prior security paths                                                       | Additional application, dependency, infrastructure, and operational hardening                                                                                                                                                                                           | missed controls; M1+M3+M5 / all; hardening review                                          |
| 14 DevOps and IaC               | **Started for local demo only**; mature app baseline                                         | Local Docker demo stack, Mailpit SMTP demo path, deterministic seed/reset helpers, and `demo_v1.md`; production Docker/Terraform/CI/CD/staging/monitoring/backups remain future work                                                                                    | cost/drift/secrets; M5 / M1+M3; repeatable staging deployment                              |
| 15 Testing                      | **Not started**; 2-14                                                                       | unit/integration/contract/E2E/security/load suites and sandbox UAT; agreed release gates met with measured baselines                                                                                                                                                    | late defects/unrepresentative load; M5 / all; UAT scenario suite                           |
| 16 Deployment                   | **Not started**; 14-15                                                                      | Controlled deployment workflow and production-readiness evidence                                                                                                                                                                                                        | environment drift; M5 / all; deployment rehearsal                                          |
| 17 Documentation and Demo       | **Not started**; 16                                                                         | user/developer/deployment guides, presentation, live demo/video, report, future roadmap; artifacts reviewed and reproducible                                                                                                                                            | stale docs/demo dependency; M1+M5 / all; final end-to-end demo                             |

## Governance

Do not begin a stage solely because a prior draft exists. Product and architecture gates must be explicitly accepted, security-critical dependencies cannot be waived informally, and parallel stages must document their assumptions. Estimates belong in the task board after refinement, not in this document.

## Stage 7 — AI explanation assistant

Stage 7 is merged in `main` with migration `0009_stage7_ai_assistant`.

## Stage 8 — Dashboard

Stage 8 is merged in `main` at `889660ecb8a378d107f6737b4466b70362066793`. Stage 8A added a
read-only `GET /api/v1/dashboard/summary` API and TypeScript response contract; Stage 8B added
the `SecurityDashboardPage` UI. Dashboard data is derived from existing Stage 2-7 authoritative
records. Stage 8 does not introduce dashboard snapshot tables, recalculate findings/compliance/
risk, call AWS, invoke AI, send notifications, execute remediation, or create Jira issues.

## Stage 9 — Notifications

Stage 9 (backend and frontend) is complete on `feature/v1-demo-completion` (commits `d0b5676`,
`449e964`, `cb42db9`, `d1c8733`; migration head `0010_stage9_notifications`), not yet merged
into `main`. It adds an approval-gated `NotificationEvent` lifecycle triggered only by newly
created `CRITICAL` findings, a deterministic mock/no-op delivery provider that makes no network
calls, RBAC-gated list/detail/approve/deliver API routes, and a frontend notification
history/approval page. No real notification delivery exists; AWS SES is a possible future
production provider, not yet implemented.

## Stage 10 — Remediation workflow

Stage 10 (backend and frontend) is complete on `feature/v1-demo-completion` (commits `bf29173`,
`fc8908d`, `8ab8c83`, `d1c8733`, `8916be9`; migration head `0011_stage10_remediation`), not yet
merged into `main`. It adds an approval-gated `RemediationRequest` lifecycle with deterministic
proposal generation from the existing rule registry, a `MockRemediationExecutor` that never
mutates real AWS resources, RBAC-gated propose/approve/reject/cancel/execute API routes, and a
frontend remediation workflow plus a finding-detail "Propose remediation" action.

## Stage 11 — Scheduler

Stage 11 (backend and frontend) is complete on `feature/v1-demo-completion` (commits `24227ab`,
`9fff532`, `8c14b55`, `55c451e`; migration head `0012_stage11_scheduler`, current head on this
branch), not yet merged into `main`. It adds `ScanSchedule`/`ScanRun` persistence with
database-enforced overlap protection, a deterministic single-tick worker
(`app/worker/scheduler_worker.py`) that delegates to the existing discovery/evaluation
services, RBAC-gated schedule/run API routes, and a frontend schedules page. Verified: backend
Ruff/Mypy (140 files)/22 Pytest passed; migration chain verified linear with a single head;
frontend TypeScript/ESLint/5 Vitest/production build passed.

## Stage 12 — Audit query/export

Stage 12 is implemented and committed on `feature/v1-demo-completion` at `d0d24cd` and
`9314f06`. It reuses the existing `AuditEvent` model and `record_audit()` write path and adds no
migration. It adds a paginated/filtered `GET /api/v1/audit-events` and a bounded CSV
`GET /api/v1/audit-events/export` (5,000-row cap, synchronous), reusing the existing
`AUDIT_READ` capability, plus a frontend audit explorer page. Backend verification is clean
(Ruff, Mypy 142 files, `test_audit_api.py` 8 passed). Frontend TypeScript, ESLint, Vitest (4
passed), and production build are clean.
