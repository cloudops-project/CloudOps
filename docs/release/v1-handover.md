# CloudOps V1 handover

## Implemented and CI verified

- Multi-tenant authentication/RBAC, onboarding, discovery, deterministic findings/compliance/risk,
  advisory AI, dashboard, notifications, Jira, scheduler, PostgreSQL durable jobs, audit, and
  security hardening.
- Governed mock/dry-run remediation, migration 0019 live-evidence model, a default-disabled S3/EC2
  executor, and owner-only remediation trust/sandbox administration.
- Controlled non-production sandbox Terraform and opt-in live test harness.
- Managed environment Terraform, containers, seven-job CI, immutable release workflow, self-host
  lifecycle tooling, and runbooks.

## Not yet operationally verified

- AWS SSO/account classification, saved sandbox plan/cost review/apply, EC2 deployment, instance
  profile, read-only discovery, or Cloudflare for the sandbox.
- Live Bedrock, SES, Jira, S3 remediation, EC2 security-group remediation, or rollback.
- Managed staging infrastructure, alarms, failure recovery, restore, canary, UAT, load baseline,
  production plan/apply, or post-deployment validation.

## Handover sequence

1. Verify exact main SHA, one Alembic head, and successful CI.
2. Use a short-lived non-root identity in a dedicated non-production/non-management account.
3. Review a saved external Terraform plan, hash, IAM boundary, exceptions, and costs.
4. Apply only after exact account/region/spend/hash authorization; deploy with live flags off and
   emergency stop on.
5. Validate health, workload identity, read-only discovery, audit, backups, and tenant UAT.
6. Configure remediation trust and sandbox approval only through owner APIs.
7. Obtain separate confirmations for each allowlisted action; disable immediately afterward;
   separately approve rollback and teardown.
8. Preserve sanitized evidence and qualify managed staging before production.

See [current release status](current-release-status.md), [EC2 runbook](../operations/ec2-deployment-runbook.md),
and [live remediation runbook](../operations/live-aws-remediation-runbook.md). No production-ready or
100% claim is valid while external gates remain unverified.
