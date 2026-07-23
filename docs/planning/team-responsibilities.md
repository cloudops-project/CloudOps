# Five-Member Responsibility Model

## Purpose and audience

The team and stakeholders use this model for primary ownership, review routing, and resilient handoffs. Names should replace member numbers after assignment.

| Member | Primary ownership | Mandatory review areas | Backup |
|---|---|---|---|
| 1 — Project lead/architecture | PRD, architecture, security governance, AI boundaries, integration decisions, stakeholder communication | ADRs, tenancy, security-sensitive changes | M2 for delivery; M3 for security architecture |
| 2 — Backend/platform | FastAPI, auth, RBAC, organizations, APIs, database access, reporting services | API/schema/transaction changes | M1; M5 for operational code |
| 3 — AWS/security engine | STS, Boto3, onboarding, collectors, rules, mappings, Lambda remediation | IAM, AWS, rules, remediation | M1; M2 for worker plumbing |
| 4 — Frontend/product design | React, dashboard, findings, reports, design system, accessibility, responsive behavior | UI/UX/accessibility | M2 for API integration; M5 for accessibility QA |
| 5 — DevOps/quality/operations | Docker, Terraform, CI/CD, testing, monitoring, backups, doc quality, releases | infrastructure, pipelines, tests, operations | M3 for AWS IaC; M2 for CI/app setup |

## Shared ownership

Everyone owns tenant safety, secret hygiene, review quality, tests, documentation, project memory, and incident reporting. Authors cannot be sole approvers. Changes to IAM/onboarding/rules/remediation require M3 plus M1 or M5; auth/tenant/database security requires M2 plus M1; infrastructure/secrets/backups require M5 plus M1/M3; accessibility requires M4 plus M5; AI boundaries require M1 plus M3/M5.

## CODEOWNERS and silos

CODEOWNERS routes review but does not transfer accountability or replace branch protection. Each major area has a primary and backup. Use paired design sessions, rotating demos/on-call simulations, ADR walkthroughs, cross-review, concise runbooks, and one handoff issue before absence. At least one non-owner should be able to run each supported workflow by UAT.

## Open questions

Assign actual GitHub handles, escalation contact, meeting cadence, final approval authority, and capacity allocation before repository settings are applied.
