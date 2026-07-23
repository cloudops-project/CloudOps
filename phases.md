# CloudOps Delivery Phases

## Current status

Stages 1–5 are independently verified, merged, and regression-tested in `main` at
`68785b0138eaecf84850887a3d4005c40e9761c0`. Stage 6 has not started.

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

**Status: NOT STARTED**

No Stage 6 executable code is authorized or present. AI must not perform deterministic risk
scoring.

## Stage 7 — AI Explanation Assistant

**Status: NOT STARTED**

Optional advisory explanations only. AI must not detect findings or determine risk scores.

## Stage 8 — Dashboard and Reports

**Status: NOT STARTED**

Expanded dashboards, reports, and export experiences remain planned.

## Stage 9 — Notifications

**Status: NOT STARTED**

Notification and ticketing integrations remain planned.

## Stage 10 — Remediation Workflow

**Status: NOT STARTED**

Governed remediation and customer-resource mutation are not implemented.

## Stage 11 — Scheduler

**Status: NOT STARTED**

Scheduling, queues, and background-worker orchestration are not implemented.

## Stage 12 — Extended Tamper-Evident Audit Timeline

**Status: NOT STARTED**

The extended audit timeline/archive is planned; current audit controls must not be described as
absolutely immutable.

## Immediate gate

1. Review and explicitly authorize documentation PR #5 where required.
2. Merge PR #5 and synchronize local `main`.
3. Confirm a clean worktree and preserved Stage 5 regression baseline.
4. Authorize and create a separate Stage 6 branch from updated `main`.
5. Keep deterministic risk scoring separate from optional advisory AI.
