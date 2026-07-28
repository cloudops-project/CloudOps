# Assumptions and Constraints

## Purpose and audience

Architecture, product, and delivery teams use this register to distinguish confirmed boundaries from hypotheses requiring validation.

## Confirmed constraints

- Version 1 centers on AWS EC2, S3, and IAM; implemented RDS/CloudWatch/CloudTrail collectors still
  require live validation. PostgreSQL is the production database and durable job store.
- Customer access uses STS temporary credentials; no long-lived customer keys are requested or stored.
- Rules are deterministic; AI is optional, advisory, redacted, schema-validated, and unable to execute actions.
- Scans are read-only. Remediation is approval-gated mock/dry-run only; no mutation role or live
  executor exists.
- Terraform defines bootstrap, staging, and production infrastructure. It validates locally but
  has not been applied to AWS.
- The project currently has five members and a student-project affordability constraint.

## Working assumptions

Customers can create the reviewed role from generated guidance and provide account metadata.
PostgreSQL `platform_jobs` is the durable queue; Celery/Redis is rejected. GitHub OIDC, Bedrock,
SES, and customer-role behavior require live staging validation.

## Risks and validation

AWS API throttling, global/regional inventory semantics, compliance licensing, IAM policy analysis complexity, tenant-scale requirements, external-provider data residency, and remediation rollback expectations need discovery. Benchmark values, retention periods, RPO/RTO, and notification channel priority are unapproved.

## Decision process

Convert validated assumptions into ADRs or requirements; record invalidated assumptions in [project memory](../planning/project-memory.md) and update dependent documents.
