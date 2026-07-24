# CloudOps Product Requirements

## Document role

This is the implementation-aligned product source of truth for CloudOps. Detailed product
research remains under `docs/product/`. This document distinguishes delivered behavior from
future intent.

## Project overview

CloudOps is a multi-tenant SaaS application for securely connecting AWS accounts and building a
normalized inventory, deterministic security findings, and point-in-time compliance
assessments and deterministic explainable risk scoring. Stages 1–5 are independently verified
and merged; Stage 6 is implemented on its feature branch and awaits independent verification.

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

Stage 5 does not detect findings and does not claim independent certification. Risk scoring,
recommendations, remediation, and Stage 6 functionality remain out of scope.

Stage 3 remains the inventory foundation. Stage 4 expands bounded configuration metadata needed
for deterministic checks; it does not ingest raw logs/events or perform full IAM simulation.

### Stage 4 — Deterministic Rule Engine and Findings

- Static, trusted typed Python rule registry; rules evaluate persisted assets only
- High-confidence EC2, S3, IAM, RDS, CloudWatch, CloudWatch Logs, and CloudTrail rules
- Evaluation jobs with one active job per AWS account
- Stable findings with open, resolved, reopened, and suppressed lifecycle behavior
- Bounded evidence, tenant-safe APIs, audit events, structured logs, and frontend workflows

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
- Operations: `/health` and database-backed `/ready`

## Current dashboard capabilities

The frontend provides organization identity and role context, member and invitation counts,
recent authentication/membership activity, member administration, AWS onboarding, asset
inventory, discovery jobs, findings, rule catalog, evaluation jobs, compliance frameworks,
control details, and assessment history. It does not display deterministic risk scores, AI
content, or remediation controls.

## Out of scope and not implemented

- Risk scoring
- Complete framework coverage or compliance certification
- Security recommendations
- AI assistance
- Notifications and ticketing
- Remediation or customer-resource mutation
- Scheduled/background discovery
- Raw CloudWatch log or CloudTrail event ingestion, EventBridge, or deployment infrastructure
- MFA, SSO/OIDC, password reset, and production invitation email delivery
- Stage 6 deterministic risk scoring; Stage 7 AI explanations; Stage 8 expanded
  dashboards/reports; Stage 9 notifications; Stage 10 remediation; Stage 11 scheduling; and
  Stage 12 extended tamper-evident audit timeline

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

## Delivery status

Stages 1–5 are independently verified and merged in `main`. Stage 6 is implemented on
`feature/6-risk-scoring` from baseline `9811aeb881a1386c1dfba7e3e1641a2b765430f2`; migration
`0008_stage6_risk_scoring` follows `0007_stage5_compliance_engine`. Independent Stage 6
verification and merge remain pending.
