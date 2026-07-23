# CloudOps Delivery Phases

## Current status

Stages 1–4 are verified and merged into `main`. Stage 5 is implemented in the dirty
`feature/5-compliance-engine` worktree and is undergoing PostgreSQL, API, frontend, and
clean-room verification. Stage 6 has not started.

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

**Status: IMPLEMENTED — VERIFICATION IN PROGRESS**

Versioned frameworks and controls, rule-version mappings, Stage 4-backed assessments, immutable
control snapshots, tenant-safe APIs, RBAC, audit events, and compliance frontend workflows are
implemented. PostgreSQL migration `0007_stage5_compliance_engine` is the candidate head.

## Stage 6

**Status: NOT STARTED**

No Stage 6 executable code is authorized or present.

## Later planned stages

The detailed roadmap under `docs/planning/` currently reserves later work for:

1. Compliance and risk
2. Optional advisory AI
3. Extended reporting
4. Notifications and Jira
5. Governed remediation
6. Scheduling and background workers
7. Audit/security hardening
8. Infrastructure and deployment
9. Integrated testing/UAT
10. Final documentation and demonstration

These are plans, not completed functionality. Sequence and scope require approval before work.

## Immediate gate

1. Finish every Stage 5 quality and migration gate.
2. Commit and push the Stage 5 branch only after all gates pass.
3. Open a draft pull request and run independent clean-room verification.
4. Do not start Stage 6.
