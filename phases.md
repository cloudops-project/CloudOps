# CloudOps delivery phases

Labels distinguish repository implementation from external evidence. See
[current status](docs/product/current-status.md) for the capability matrix.

| Stage | Scope | Current label | Evidence and remaining gate |
|---|---|---|---|
| 0 Planning | Product, architecture, ADRs, safety | Complete and locally verified | Maintained source-of-truth package exists |
| 1 Authentication/RBAC | Auth, organizations, invitations, capabilities | Complete and locally verified | Automated tenant/RBAC tests; operational UAT pending |
| 2 AWS onboarding | Separate role trust, External ID, STS validation | Implemented, external validation pending | Mocked/Stubber tests; live STS pending |
| 3 Discovery | EC2/S3/IAM/RDS/CloudWatch/CloudTrail inventory | Implemented, external validation pending | Synthetic tests; live service compatibility pending |
| 4 Rule engine | Versioned deterministic findings | Complete and locally verified | Deterministic regression tests |
| 5 Compliance | Framework/control mappings and assessments | Complete and locally verified | No certification claim; content review remains |
| 6 Risk | Versioned deterministic snapshots | Complete and locally verified | `CLOUDOPS_RISK_V1`; immutable snapshot tests |
| 7 AI assistant | Explanations/summaries/drafts | Implemented, external validation pending | Safety/Stubber tests; live Bedrock pending |
| 8 Dashboard | Tenant UI and summaries | Complete and locally verified | Automated frontend gates; browser UAT pending |
| 9 Notifications/Jira | Approval-gated delivery and issue workflow | Implemented, external validation pending | Mocked adapters; live SES/Jira pending |
| 10 Remediation | Preview/approval/admin/two-action executor | Implemented, external validation pending | Default-disabled; no live mutation or rollback proof |
| 11 Scheduler/jobs | Durable jobs, leases, retries, dead-letter | Complete and locally verified | Concurrency tests; deployed multi-replica proof pending |
| 12 Audit | Structured events, query/export | Complete and locally verified | Redaction/tenant tests; external retention/SIEM pending |
| 13 Security hardening | Secrets, workload identity, tenant defense | Complete and locally verified | CI/security scans; live IAM/rotation exercises pending |
| 14 DevOps/IaC | Containers, CI/release, managed and sandbox Terraform | Implemented, external validation pending | Validation/Checkov/tests; identity/plan/apply pending |
| 15 Testing | Automated gates plus operational qualification | Partially implemented | Seven CI jobs pass; UAT/load/live-provider/recovery pending |
| 16 Deployment | Sandbox, staging, production, promotion | Not started | No verified sandbox plan/apply, EC2, staging, or production deployment |
| 17 Documentation/demo | Canonical docs, handoff, guide demo | Partially implemented | This refresh prepares review; live guide/UAT evidence pending |

No completion percentage is assigned because external deployment and recovery gates have materially
different risk and scope. Terraform/workflow presence is not deployment.

## Next sequence

1. Complete short-lived non-production identity verification and account classification.
2. Generate and review an external saved Terraform plan and cost inventory under separate approval.
3. Apply only the reviewed plan under exact authorization; deploy with live flags disabled.
4. Verify workload identity, read-only discovery, health, logs, backups, and tenant UAT.
5. Configure trust and sandbox approval through the owner API, never direct SQL.
6. Separately approve controlled S3 and EC2 tests, disable flags immediately afterward, rehearse
   manual rollback, and tear down the sandbox.
7. Qualify managed staging before any production plan or authorization.
