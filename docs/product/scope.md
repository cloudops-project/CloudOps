# Version 1 Scope

## Purpose and audience

This boundary helps product owners, engineers, and reviewers prevent scope creep and evaluate change requests.

## Committed planning scope

Version 1 plans organization and user management, authentication/RBAC, multi-account AWS onboarding through STS, EC2/S3/IAM inventory and rules, findings and compliance mappings, reports, audit history, notifications, Jira, risk acceptance, manual/scheduled scans, approval-based remediation, and verification. Tenant isolation applies throughout. See the [PRD](prd.md) for outcomes.

## Not included

Azure, Google Cloud, Kubernetes, containers, source code, malware, endpoints, penetration testing, application payload collection, arbitrary shell access, autonomous AI decisions/actions, universal remediation automation, and compliance certification are excluded. Adding an AWS service beyond EC2, S3, or IAM requires a post-MVP scope decision.

## Guardrails

Scanning roles are read-only. Remediation uses separate action-specific permissions and prior authorization. AI cannot authoritatively identify vulnerabilities, approve or execute remediation, or close findings. Context-dependent checks are policy signals, not universal vulnerabilities.

## Change control and open questions

New work needs an issue describing value, risk, dependencies, tenant/security impact, and displaced scope. Product lead approval is required; architecture-impacting changes need an ADR. Open questions: whether email or Teams ships first, which compliance framework subset is licensed and validated, and which one low-risk sandbox remediation becomes the sample.
