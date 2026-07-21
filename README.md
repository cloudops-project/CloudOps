# CloudFix

## Purpose and audience

This repository is the planning and future delivery home for CloudFix; stakeholders, contributors, security reviewers, and evaluators use this index to understand scope, status, and governance.

CloudFix is a planned AWS-focused Cloud Security Posture Management (CSPM) SaaS. Version 1 will inventory Amazon EC2, Amazon S3, and AWS IAM configuration, evaluate deterministic security rules, and support controlled investigation, assignment, approval, remediation, and verification. AI is advisory only: it may explain rule-produced findings but cannot create authoritative findings or take security-sensitive action.

> Status: Stage 0 â€” planning and research. No application, AWS integration, or deployment has been implemented.

## Product principles

- Customer accounts connect through cross-account IAM roles, AWS STS, an external ID, and short-lived credentials. CloudFix never requests or stores long-lived customer AWS access keys.
- Every tenant-owned operation is authorized against an organization; tenant isolation is enforced server-side and in repositories.
- Scanning is read-only. Remediation requires an approved playbook, explicit authorization, a separate narrowly scoped permission path, and a verification scan.
- Deterministic rules decide whether evidence matches a check. AI output is redacted, validated, untrusted advice with a deterministic fallback.
- Scans, findings, approvals, exceptions, remediation attempts, verification, and administration produce auditable events.

## Documentation index

- [Portable fresh-chat repository context](NEW_CHAT_CONTEXT.md)
- [Product requirements](docs/product/prd.md), [scope](docs/product/scope.md), [personas](docs/product/personas.md), [user stories](docs/product/user-stories.md), and [success metrics](docs/product/success-metrics.md)
- [System overview](docs/architecture/system-overview.md), [components](docs/architecture/component-design.md), [data flow](docs/architecture/data-flow.md), [AWS onboarding](docs/architecture/aws-account-onboarding.md), [multi-tenancy](docs/architecture/multi-tenant-design.md), and [database design](docs/architecture/database-design.md)
- [API design](docs/architecture/api-design.md), [threat model](docs/architecture/threat-model.md), [trust boundaries](docs/architecture/trust-boundaries.md), [failure scenarios](docs/architecture/failure-scenarios.md), and [ADRs](docs/architecture/decisions/README.md)
- [Design system](docs/design/design-system.md), [information architecture](docs/design/information-architecture.md), [wireframes](docs/design/dashboard-wireframes.md), and [user flows](docs/design/user-flows.md)
- [Development rules](docs/engineering/development-rules.md), [security guidelines](docs/engineering/security-guidelines.md), [AI guidelines](docs/engineering/ai-usage-guidelines.md), [rule catalogue](docs/engineering/rule-authoring-guidelines.md), and [definition of done](docs/engineering/definition-of-done.md)
- [Phases](docs/planning/phases.md), [roadmap](docs/planning/roadmap.md), [team responsibilities](docs/planning/team-responsibilities.md), [task breakdown](docs/planning/task-breakdown.md), [risk register](docs/planning/risk-register.md), and [project memory](docs/planning/project-memory.md)
- [Operations](docs/operations/deployment-strategy.md), [environments](docs/operations/environments.md), [monitoring](docs/operations/monitoring-strategy.md), [audit logging](docs/operations/audit-log-strategy.md), [recovery](docs/operations/backup-and-recovery.md), [incident response](docs/operations/incident-response.md), and [secrets](docs/operations/secrets-management.md)

## Stage 0 review checklist

- [ ] Stakeholders approve the PRD, Version 1 scope, assumptions, and success measures.
- [ ] Architecture and security reviewers approve trust boundaries, tenancy, database model, AWS onboarding, and threat model.
- [ ] Engineering team approves development rules, Git workflow, API/database conventions, test strategy, and phased plan.
- [ ] Product/design review the information architecture, accessible design system, flows, and wireframes.
- [ ] Team confirms ownership, backup owners, initial backlog, risk treatments, and open questions.
- [ ] Approved ADR statuses are recorded and project memory is updated.
- [ ] Stage 1 is explicitly authorized; until then, application code and executable infrastructure remain prohibited.

## Repository map

`apps/`, `packages/`, `infrastructure/`, `tests/`, and `.github/workflows/` contain documentation-only Stage 0 placeholders. See [CONTRIBUTING.md](CONTRIBUTING.md) before proposing changes.

## Disclaimer

CloudFix is intended to help identify configuration risks; it does not guarantee security or compliance certification. Findings require contextual review, and some controls depend on organizational policy.
