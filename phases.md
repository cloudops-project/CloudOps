# CloudOps Delivery Phases

## Current status

Stages 1, 2, and 3 are merged into `main`. Stage 4 is implemented on
`feature/4-rule-engine` and awaits independent verification. Stage 5 has not started.

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

**Status: IMPLEMENTED — AWAITING INDEPENDENT VERIFICATION**

Delivered typed deterministic rules, a static registry, evaluation jobs, finding lifecycle and
suppression, PostgreSQL concurrency/tenant constraints, expanded configuration discovery,
findings/rules/evaluation APIs, structured operational logs, audit events, and frontend
findings/rule/evaluation workflows. Rules evaluate persisted data and never call AWS.

Compliance frameworks, risk scoring, AI, raw provider-event ingestion, remediation, and customer
AWS mutation are excluded.

## Stage 5

**Status: NOT STARTED**

Stage 5 scope is not authorized in this branch.

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

1. Finish Stage 4 quality gates and publish a draft pull request.
2. Run independent Stage 4 verification.
3. Correct verified findings, if any.
4. Merge only through repository policy.
5. Do not start Stage 5.
