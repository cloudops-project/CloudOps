# CloudOps Delivery Phases

## Current status

Stages 1, 2, and 3 are complete and independently verified on
`feature/3-asset-discovery`. Stage 4 has not started.

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

## Stage 4 — Security Analysis

**Status: NOT STARTED**

Planned scope may include a deterministic security-rule engine, versioned rules, findings,
misconfiguration detection, compliance mappings, risk scoring, and recommendations. No
executable Stage 4 model, service, API, worker, or frontend functionality exists.

Stage 4 must not begin until Stage 3 is independently verified and the Stage 1–3 baseline is
reviewed and merged.

## Later planned stages

The detailed roadmap under `docs/planning/` currently reserves later work for:

1. Findings and risk workflow
2. Compliance
3. Optional advisory AI
4. Security dashboard and reporting
5. Notifications and Jira
6. Governed remediation
7. Scheduling and background workers
8. Audit/security hardening
9. Infrastructure and deployment
10. Integrated testing/UAT
11. Final documentation and demonstration

These are plans, not completed functionality. Sequence and scope require approval before work.

## Immediate gate

1. Commit and push the verified Stage 1–3 baseline.
2. Open a pull request to the repository default branch.
3. Obtain independent human approval and complete required review.
4. Merge through repository policy.
5. Start Stage 4 only from an updated, approved integration baseline.
