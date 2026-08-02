# Version 1 Scope

## Purpose and audience

This boundary helps product owners, engineers, and reviewers prevent scope creep and evaluate change requests.

## Implemented V1 scope

Version 1 includes organization and user management, authentication/RBAC, multi-account AWS
onboarding through STS, supported AWS inventory and deterministic rules, findings/compliance/risk,
reports, audit, notifications, Jira, manual/scheduled work, durable jobs, and governed remediation.
EC2, S3, and IAM are the core product scope; RDS, CloudWatch, and CloudTrail collectors also exist
but require live compatibility validation. Tenant isolation applies throughout. See the
[canonical PRD](../../PRD.md) and [current status](current-status.md).

## Not included

Azure, Google Cloud, Kubernetes scanning, source-code/malware/endpoint scanning, penetration testing,
application payload collection, arbitrary shell/AWS operations, autonomous AI decisions,
universal remediation, automatic rollback, and compliance certification are excluded. Expanding
the validated service or mutation allowlist requires explicit scope, threat modeling, and tests.

## Guardrails

Scanning roles are read-only. Remediation uses separate action-specific permissions and prior authorization. AI cannot authoritatively identify vulnerabilities, approve or execute remediation, or close findings. Context-dependent checks are policy signals, not universal vulnerabilities.

## Change control and open questions

New work needs an issue describing value, risk, dependencies, tenant/security impact, and displaced
scope. Product approval is required; architecture-impacting changes need an ADR. Provider production
selection, compliance content validation, and any expanded remediation action remain reviewed
decisions rather than assumptions.
