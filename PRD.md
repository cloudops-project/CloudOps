# CloudOps Product Requirements

## Document role

This is the implementation-aligned product source of truth for CloudOps. Detailed product
research remains under `docs/product/`. This document distinguishes delivered behavior from
future intent.

## Project overview

CloudOps is a multi-tenant SaaS application for securely connecting AWS accounts and building a
normalized inventory, deterministic security findings, and point-in-time compliance
assessments, deterministic explainable risk scoring, advisory AI explanations, an
approval-gated critical-finding notification workflow, a governed mock remediation workflow, a
scan-scheduling foundation, and an audit query/export layer. Stages 1-8 are independently
clean-room verified, merged, and regression-tested in `main`. Stages 9-11 (notifications,
remediation, scheduler, audit query/export) are implemented, independently verified, and
committed on `feature/v1-demo-completion`, not yet merged into `main`. Stage 12 is committed at
`d0d24cd` and `9314f06`; backend and frontend targeted verification are clean.

## Business goals

- Give each customer organization an isolated administrative boundary.
- Avoid long-lived customer AWS credentials by using cross-account IAM roles and AWS STS.
- Maintain an auditable record of authentication, membership, onboarding, and discovery actions.
- Build reliable inventory, deterministic evidence, and explainable bounded risk scores without
  claiming certification or unsupported compliance coverage.
- Preserve historical asset visibility when resources disappear from a later successful
  discovery.

## Target users

| User               | Current needs                                                                          |
| ------------------ | -------------------------------------------------------------------------------------- |
| Organization owner | Create and govern an organization, manage members, connect AWS accounts, run discovery |
| Organization admin | Manage non-owner members, onboard AWS accounts, run discovery                          |
| Security analyst   | View organization data and inventory, run discovery                                    |
| Cloud engineer     | View organization data and inventory, run discovery                                    |
| Auditor            | Read organization, audit, onboarding, asset, and discovery-job data                    |
| Viewer             | Limited read-only access to organization data and inventory                            |
| Platform admin     | Separate platform flag; it does not implicitly bypass tenant authorization             |

## Supported cloud provider

AWS is the only supported provider in the current product. Azure, Google Cloud, Kubernetes, and
other platforms are out of scope.

## Current functional scope

### Stage 1 — Foundation and Authentication

- Registration, login, logout, profile retrieval, and password change
- Short-lived signed access JWTs
- Opaque rotating refresh tokens in HttpOnly cookies
- Organizations, memberships, invitations, and role assignment
- Centralized organization RBAC and tenant-scoped authorization
- Last-active-owner protection
- Authentication and membership audit events
- Health and database-readiness endpoints
- Stage 1 administrative frontend

### Stage 2 — AWS Account Onboarding

- One or more AWS accounts per organization
- Globally and permanently reserved external IDs
- Generated IAM trust-policy and AWS managed `SecurityAudit` guidance
- Cross-account role ARN validation
- AWS STS `AssumeRole`, followed by `GetCallerIdentity`
- Account lifecycle states, validation, disconnect, update, and deletion
- Owner/admin onboarding controls and audit events
- No storage of long-lived or temporary AWS credentials

### Stage 3 — Asset Discovery

- Connected-account discovery using the Stage 2 role and temporary STS credentials
- Regional discovery for EC2 instances and RDS instances
- Global discovery for S3 buckets and IAM resources
- IAM users, roles, groups, and customer-managed policies
- Paginator-aware collectors and normalized asset records
- Historical `first_seen_at`/`last_seen_at` lifecycle and active/stale status
- Partial-failure isolation by service
- Discovery jobs, counts, sanitized errors, and audit events
- Bounded, filterable asset APIs and inventory frontend

### Stage 4 — Deterministic Findings

- Typed deterministic rules over persisted inventory
- Evaluation jobs and finding lifecycle
- Finding suppression, APIs, audit events, and frontend workflows

### Stage 5 — Compliance Engine

- Versioned frameworks and controls
- Rule-version-aware many-to-many mappings
- Account assessments backed by persisted Stage 4 evaluation evidence
- Immutable historical control snapshots
- PASS, FAIL, NOT_ASSESSED, and ERROR semantics
- Framework, control, finding-traceability, summary, and assessment APIs
- Tenant-scoped RBAC and compliance UI

Stage 5 does not detect findings and does not claim independent certification.

### Stage 6 — Deterministic Risk Scoring

- Versioned `CLOUDOPS_RISK_V1` policy with 0–100 CloudOps-specific, CVSS-inspired scores
- Explicit component points, reason codes, and persisted unknown-input indicators
- Deterministic LOW (0–29), MEDIUM (30–59), HIGH (60–79), and CRITICAL (80–100) priorities
- Finding, account, and organization point-in-time snapshots with stable ordering
- Account aggregation: 50% maximum, 30% mean of the top ten, and 20% mean of all active findings
- Organization aggregation: 60% maximum account score and 40% mean account score
- Explicit asset/account context for business impact, data sensitivity, and environment
- Authorized, reasoned compensating controls bounded from -15 through -1
- Tenant-scoped APIs, six-role RBAC, PostgreSQL integrity/concurrency controls, and risk dashboard

Stage 6 prioritizes existing Stage 4 findings. It performs no detection, live AWS access, or AI
work. Suppressed findings remain risk evidence, and historical snapshots are not recalculated.

Stage 3 remains the inventory foundation. Stage 4 expands bounded configuration metadata needed
for deterministic checks; it does not ingest raw logs/events or perform full IAM simulation.

### Stage 4 — Deterministic Rule Engine and Findings

- Static, trusted typed Python rule registry; rules evaluate persisted assets only
- High-confidence EC2, S3, IAM, RDS, CloudWatch, CloudWatch Logs, and CloudTrail rules
- Evaluation jobs with one active job per AWS account
- Stable findings with open, resolved, reopened, and suppressed lifecycle behavior
- Bounded evidence, tenant-safe APIs, audit events, structured logs, and frontend workflows

### Stage 9 — Notifications (implemented, committed on `feature/v1-demo-completion`)

- Organization-scoped `NotificationEvent` pipeline triggered only by a newly created `CRITICAL`
  finding
- `PENDING_APPROVAL -> APPROVED -> DELIVERED`, or `APPROVED -> FAILED` after three failed
  attempts; no `REJECTED` state
- Delivery requires explicit human approval via the `NOTIFICATIONS_APPROVE` capability
- Deterministic mock/no-op delivery provider only; no real SMTP, AWS SES, SendGrid, Gmail, or
  Microsoft Graph delivery; the provider makes no network calls
- Frontend notification history/approval page with filtering, pagination, and role-gated
  approve/deliver controls

### Stage 10 — Remediation workflow (implemented, committed on `feature/v1-demo-completion`)

- Organization-scoped `RemediationRequest` lifecycle:
  `PENDING_APPROVAL -> APPROVED -> SUCCEEDED`, `APPROVED -> FAILED` after three failed mock
  execution attempts, or rejection/cancellation from an active state
- Deterministic proposal text generated from the existing security-rule registry; no new
  detection logic
- Deterministic mock executor only; Version 1 never mutates real AWS resources
- Human authorization required for propose/approve/reject/cancel/execute transitions
- Frontend "Propose remediation" action on a finding's detail page, plus a remediation
  list/detail page with role-gated approve/reject/cancel/execute controls

### Stage 11 — Scheduler (implemented, committed on `feature/v1-demo-completion`)

- `ScanSchedule` (interval cadence, next-run calculation, enable/disable) and `ScanRun`
  (execution history, manual or scheduled trigger) persistence
- Overlap protection: a database partial unique index allows only one pending/running scan per
  AWS account
- A deterministic, synchronously invokable scheduler worker foundation that delegates every run
  to the existing discovery and evaluation orchestration; it is not a Celery/Redis/distributed
  queue or a permanent cron daemon
- Frontend schedules page with enable/disable, run-now, and recent scan-run history

### Stage 12 — Audit query/export (implemented and committed on `feature/v1-demo-completion`)

- Read/query/export layer over the existing `AuditEvent` persistence and `record_audit()` write
  path from earlier stages; adds no migration
- Filterable, paginated `GET /api/v1/audit-events` and a bounded (5,000-row) CSV
  `GET /api/v1/audit-events/export`, both reusing the existing `AUDIT_READ` capability
- Frontend audit explorer page with filters, pagination, and CSV export
- Backend and frontend targeted verification are clean

## Current user journey

1. Register or log in.
2. Create or select an organization.
3. Invite members and assign permitted organization roles.
4. Add an AWS account name and 12-digit account ID.
5. Copy the generated external ID, trust policy, and permission guidance.
6. Create `CloudOpsReadOnlyRole` manually in the customer AWS account.
7. Enter the role ARN and validate the connection through STS.
8. Run discovery on a connected account.
9. Review normalized assets and discovery-job results.
10. Run a deterministic evaluation and review findings.
11. Run a compliance assessment backed by the completed evaluation.
12. Review framework, control, mapped-finding, and immutable historical assessment details.
13. Configure bounded risk context and run a deterministic risk assessment.
14. Review score, textual priority, component reasons, unknown-input indicators, ranked
    findings, account/organization aggregates, and immutable history.
15. Where authorized, add a reasoned compensating control and compare a new assessment with the
    unchanged prior snapshot.

## Current API capabilities

All application APIs are versioned under `/api/v1`.

- Authentication: register, login, refresh, logout, current profile, change password
- Organizations: create, list, retrieve, update
- Members: list, change permitted role/status, remove
- Invitations: create, list, cancel, accept
- Audit: list recent organization events
- AWS accounts: create, list, retrieve, update, validate, disconnect, delete
- Discovery: start account discovery; list and retrieve jobs
- Assets: list with filters/pagination, summarize, retrieve details
- Rules, evaluations, and findings: catalog, execution, jobs, filters, summaries, details, and
  authorized suppression
- Compliance: frameworks, controls, rule mappings, mapped findings, summaries, assessment
  execution, history, and immutable snapshot details
- Risk: policies, assessment execution/history/details, summaries, ranked findings,
  account/asset views, context read/update, and compensating-control lifecycle
- Notifications: list/detail, approve, deliver (Stage 9)
- Remediation: list/detail, propose, approve, reject, cancel, execute (Stage 10)
- Scheduler: create/list/detail schedules, enable, disable, delete, run-now, list/detail scan
  runs (Stage 11)
- Audit: paginated/filtered query and bounded CSV export over existing audit events (Stage 12,
  committed on `feature/v1-demo-completion`)
- Operations: `/health` and database-backed `/ready`

## Current dashboard capabilities

The frontend provides organization identity and role context, member and invitation counts,
recent authentication/membership activity, member administration, AWS onboarding, asset
inventory, discovery jobs, findings, rule catalog, evaluation jobs, compliance frameworks,
control details, assessment history, deterministic risk summaries, component explanations,
ranked findings, contexts, compensating controls, historical risk snapshots, advisory AI
draft workflows, a notification history/approval page, a remediation list/detail workflow, a
scan-schedule page with run-now, and (pending commit) an audit explorer page with CSV export.
Jira and email outputs remain drafts; remediation execution is mock/simulated only.

## Out of scope and not implemented

- Complete framework coverage or compliance certification
- Security recommendations
- Real notification delivery (email, Slack, Teams, webhook) and ticketing; Stage 9 ships a
  deterministic mock/no-op provider only that makes no network calls; AWS SES is a possible
  future production provider, not yet implemented
- Real AWS remediation/mutation; Stage 10 ships a deterministic mock executor only
- A Celery/Redis/distributed-queue or permanent cron-daemon scheduler; Stage 11 ships a
  deterministic, synchronously invokable worker foundation only
- Raw CloudWatch log or CloudTrail event ingestion, EventBridge, or deployment infrastructure
- MFA, SSO/OIDC, password reset, and production invitation email delivery
- Production deployment/IaC. A guarded local Docker demo stack, Docker-only seed/reset helpers,
  Mailpit SMTP demo delivery, and `demo_v1.md` are implemented on
  `feature/v1-demo-completion`; final rehearsal evidence is still being completed.
- Stage 13 security hardening; full regression and black-box V1 acceptance; deployment
  preparation; final documentation; and
  the pull request integrating this branch into `main`

## Security and test boundaries

- Every tenant-owned operation requires active membership, centralized RBAC, and organization
  scope; cross-tenant detail probes use non-disclosing behavior.
- AWS integration is read-only and uses STS temporary credentials only.
- Automated tests use synthetic data and deterministic AWS mocks. Production and customer AWS
  accounts or credentials must never be used.
- Stage 4 rules are the only implemented detection boundary. Stage 5 interprets persisted
  deterministic evidence and cannot infer `PASS` from missing evidence.
- AI must not detect findings or determine risk scores.

## Acceptance criteria for the current baseline

- Stage 1 identity, tenant administration, and regression tests remain functional.
- AWS accounts are accessed only with cross-account STS temporary credentials.
- External IDs are globally unique and remain reserved after account deletion.
- Only connected accounts can run discovery.
- EC2, S3, IAM, and RDS inventory is normalized, paginated, and tenant scoped.
- Repeated discovery upserts assets without changing `first_seen_at`.
- Missing assets become inactive only after their collector succeeds.
- Partial failures preserve successful results and prior assets for failed collectors.
- PostgreSQL enforces account/organization consistency and lifecycle constraints.
- All authorization is enforced by the backend.
- No credentials are persisted or exposed.
- Rule errors cannot falsely pass or resolve findings.
- Stage 5 assessments require affirmative Stage 4 evidence and preserve immutable snapshots.
- Stage 6 scores are deterministic, versioned, bounded from 0–100, and preserve immutable
  historical snapshots; unknown inputs are explicit and suppression alone never lowers risk.

## Delivery status

Stages 1-8 are independently clean-room verified and merged in `main` at
`889660ecb8a378d107f6737b4466b70362066793`. Stage 7 feature SHA
`9b5f4372359a32066787060ca839d5a68c5ab490` was merged by PR #8; Stage 8 merged via PR #10 plus a
follow-up `feature/8-dashboard-ui` merge. The current migration head on `main` is
`0009_stage7_ai_assistant`.

Stages 9-12 (notifications, remediation, scheduler, audit query/export) are implemented,
independently verified, and committed on `feature/v1-demo-completion`; the current demo-readiness
work advances the branch beyond `9314f06` and uses migration head
`0013_demo_notification_delivery`, not yet merged into `main`. Stages 13 and 15-17 remain
future work; Stage 14 is started for the local demo stack only.

## Stage 7 acceptance boundary

Stage 7 provides explanation and drafting assistance for deterministic
CloudOps evidence. Supported tasks are finding explanation, business-impact
explanation, remediation suggestion, executive summary, Jira-description
draft, and email-summary draft. Missing evidence, provider failure, invalid
structured output, quota exhaustion, and cross-tenant references must fail
safely. AI is prohibited from detection, scoring, status mutation,
authorization decisions, remediation, and external delivery.
