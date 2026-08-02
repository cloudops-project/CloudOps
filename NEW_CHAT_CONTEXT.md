# CloudOps New Chat Context

## Source of truth

Use current code, models/migrations, tests, workflows, and scripts before documentation. The
canonical documentation index is [docs/README.md](docs/README.md). Product requirements,
architecture, status, and operational memory are [PRD.md](PRD.md), [architecture.md](architecture.md),
[docs/product/current-status.md](docs/product/current-status.md), and [memory.md](memory.md).

## Project and architecture

CloudOps is a multi-tenant AWS security-posture application built with React/Vite, FastAPI, and
PostgreSQL. STS role assumption provides temporary in-memory AWS credentials. Deterministic rules
detect findings and `CLOUDOPS_RISK_V1` computes authoritative risk. PostgreSQL durable jobs power
discovery, evaluation, schedules, notifications, and remediation. AI is advisory and receives one
bounded sanitized persisted source; it cannot detect, score, approve, or execute.

## Current implementation

At audited main commit `bec5753ad127d8ed8968d539ee625130c6a2e06f`, implementation includes
authentication/RBAC, tenant isolation, onboarding/discovery, findings/compliance/risk, AI, dashboard,
notifications, Jira, scheduler/jobs, audit, governed remediation, separate remediation trust,
owner-only sandbox administration, a default-disabled two-action AWS executor, controlled sandbox
Terraform, and opt-in runbooks/harness. Alembic has one head:
`0019_live_remediation_data_model`.

The executor only supports `s3.enable_public_access_block` and
`ec2.revoke_approved_public_ingress` on approved tagged sandbox resources. Mock/dry-run remains the
default. Automatic rollback is not implemented; exact rollback state is captured.

## Verification and blockers

The repository's seven CI jobs passed for the audited commit. Automated AWS/provider tests use
fakes or Botocore Stubber. Operator-reported AWS SSO setup is incomplete; identity preflight,
Terraform plan/apply, EC2 deployment, Cloudflare, workload-identity proof, live discovery,
Bedrock/SES/Jira, live remediation, rollback, restore, UAT, and production deployment are not yet
verified. Do not infer deployment from Terraform or workflows.

## Next safe task

Complete short-lived identity setup for a dedicated non-production, non-root, non-management
account; stop for explicit account classification; then obtain separate authorization for a saved
Terraform plan and cost review. Do not apply or enable remediation from documentation context.

## Safety constraints

Never commit secrets or long-lived AWS keys, edit approval state directly, weaken tenant isolation,
enable arbitrary AWS operations, let AI authorize anything, bulk-stage, rewrite shared history, or
claim external validation without retained evidence. AWS, Terraform apply/destroy, Cloudflare,
provider, remediation, rollback, staging, and production actions require separate exact approval.

“Read the attached project files and treat them as the source of truth.

First, summarize your understanding of:
- the project goal
- the architecture
- the current implementation state
- known issues
- the next task

Do not modify code yet. Identify contradictions or missing information before proceeding.”

“Update NEW_CHAT_CONTEXT.md after major architectural changes. Update memory.md after each substantial coding session.”
