# Product Requirements Document

## Purpose and audience

This PRD aligns product, security, engineering, design, and stakeholders on the intended
CloudOps Version 1 outcome. It is a future planning baseline, not evidence of implementation.
The root [`PRD.md`](../../PRD.md) is the authoritative description of current functionality.

## Vision and problem

CloudOps will provide organizations with centralized visibility into AWS misconfigurations and a controlled process for investigating, assigning, approving, remediating, and verifying security findings. Teams commonly lack a consistent inventory, contextual evidence, ownership, and auditable follow-through across AWS accounts.

## Users and outcomes

Organization Administrators manage tenants, users, roles, integrations, and AWS connections. Security Analysts triage findings and exceptions. Cloud and DevOps Engineers remediate or implement approved playbooks. Auditors review evidence and histories. Read-only Stakeholders consume posture and risk reports. Detailed needs are in [personas](personas.md).

## Future Version 1 roadmap

Stages 1–3 currently implement the identity/organization foundation, secure AWS onboarding, and
inventory-only EC2/S3/IAM/RDS discovery. All rule, finding, compliance, notification, AI, and
remediation bullets below remain future scope.

- Organization/user management, Stage 1 local JWT authentication, RBAC, and organization-scoped authorization, with future OIDC federation readiness.
- Multi-account AWS onboarding, cross-account role and external-ID validation, manual/scheduled read-only scans, and connection revocation.
- EC2, S3, and IAM asset discovery; normalized inventory; deterministic versioned rules; evidence, severity, status, and compliance mappings.
- Finding dashboards, reports, audit history, email or Microsoft Teams notifications, and Jira ticket creation.
- Advisory AI explanations, remediation suggestions, Jira drafts, compliance explanations, and report summaries after redaction and schema validation.
- Manual remediation, risk acceptance with justification/expiry, and approval-based scoped Lambda remediation for an explicitly supported sample playbook, followed by verification.

## Explicit exclusions

Azure, Google Cloud, Kubernetes, container-image and source-code scanning, malware scanning, runtime endpoint protection, penetration testing, autonomous AI remediation, arbitrary shell execution, customer application-data collection, and guaranteed compliance certification are outside Version 1.

## Intended future functional lifecycle

Connect account → validate role → discover assets → evaluate deterministic rules → create/deduplicate findings → triage → explain/assign/accept/approve → remediate → rescan → record audit evidence. All tenant resources are organization-owned and authorization is evaluated server-side.

## Non-functional requirements

Least privilege, encryption in transit/at rest, redacted structured logs, traceability, accessibility aligned with WCAG 2.2 AA as a target, recoverability, bounded retries, idempotency for retried actions, and observable background work are mandatory design qualities. Performance and scale targets remain provisional until representative benchmarking.

## Future Version 1 success criteria

- Connect a sandbox customer account without storing long-lived AWS access keys; discover supported EC2, S3, and IAM assets.
- Evaluate a reviewed initial deterministic rule set and emit findings with evidence, severity, resource, rule ID/version, and guidance.
- Generate a Jira ticket from a finding and demonstrate one approved sample remediation safely in sandbox, then verify by rescan.
- Record sensitive actions in an audit trail and demonstrate that users cannot access another organization's data.
- Demonstrate the MVP safely in a dedicated AWS sandbox/UAT account with recovery and revocation procedures.

## Assumptions, risks, and open questions

Assumptions and constraints are tracked [here](assumptions-and-constraints.md); material risks are in the [risk register](../planning/risk-register.md). Approval is needed for the OIDC provider, worker choice (proposed Celery/Redis), compliance content licensing, notification option priority, retention periods, and first automated remediation playbook.
