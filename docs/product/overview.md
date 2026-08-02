# CloudOps product overview

CloudOps is a multi-tenant AWS security-posture application. It connects to customer accounts by
AWS Security Token Service (STS) role assumption, discovers supported resources, applies
deterministic rules, persists findings, maps compliance controls, computes deterministic risk,
and provides governed notification and remediation workflows.

The product addresses a practical problem: small cloud teams need repeatable evidence and
prioritization without storing long-lived AWS keys or delegating security decisions to a language
model. The primary users are organization owners, security analysts, cloud engineers, auditors,
and read-only stakeholders. See [personas](personas.md) and [user stories](user-stories.md).

## Implemented product boundary

- Authentication, refresh sessions, organizations, invitations, membership, and capability-based
  role-based access control (RBAC).
- Cross-account onboarding with generated External IDs and temporary credentials held in memory.
- EC2, S3, IAM, RDS, CloudWatch, and CloudTrail discovery collectors, subject to live-account
  validation for actual service compatibility.
- Deterministic findings, compliance assessments, risk snapshots, dashboards, audit events,
  notifications, Jira integration, and PostgreSQL-backed durable jobs.
- Advisory AI explanations and drafts over one persisted source after bounded sanitization.
- Governed remediation preview, approval, execution evidence, a default mock executor, and a
  default-disabled live executor limited to two actions.
- Owner-only administration for remediation trust and sandbox approval.
- Terraform source for managed environments and a separate controlled non-production sandbox.

## Boundaries

AI does not detect findings, calculate authoritative risk, approve remediation, select AWS
operations, or execute changes. Arbitrary AWS API dispatch is not supported. Live remediation is
restricted to approved, tagged sandbox resources and has not been operationally verified.

See [current status](current-status.md), [system architecture](../architecture/system-architecture.md),
and the root [product requirements](../../PRD.md).
