# Assumptions and Constraints

## Purpose and audience

Architecture, product, and delivery teams use this register to distinguish confirmed boundaries from hypotheses requiring validation.

## Confirmed constraints

- Version 1 supports AWS EC2, S3, and IAM only; PostgreSQL is the intended production database.
- Customer access uses STS temporary credentials; no long-lived customer keys are requested or stored.
- Rules are deterministic; AI is optional, advisory, redacted, schema-validated, and unable to execute actions.
- Scans are read-only; automation requires approval and separate least-privilege remediation permissions.
- Terraform will manage CloudFix-owned infrastructure later; Boto3 performs runtime discovery and approved operations.
- The project currently has five members and a student-project affordability constraint.

## Working assumptions

Customers can deploy a reviewed onboarding template and provide account metadata. MVP runs in a limited number of environments and uses Celery with Redis as the proposed understandable queue, with an adapter boundary for possible SQS migration. OIDC-compatible identity and Jira APIs are available in test tenants.

## Risks and validation

AWS API throttling, global/regional inventory semantics, compliance licensing, IAM policy analysis complexity, tenant-scale requirements, external-provider data residency, and remediation rollback expectations need discovery. Benchmark values, retention periods, RPO/RTO, and notification channel priority are unapproved.

## Decision process

Convert validated assumptions into ADRs or requirements; record invalidated assumptions in [project memory](../planning/project-memory.md) and update dependent documents.
