# CloudOps Product Requirements

> **Naming:** Per [ADR-010](docs/architecture/decisions/ADR-010-cloudops-product-name.md),
> **CloudOps** is the active product, application, and UI name. CloudFix remains only the
> repository/directory name and appears in historical records. This document uses CloudOps.

This file defines product intent and release acceptance. Implementation truth comes from source
code, migrations, tests, Terraform, and workflows. See [architecture.md](architecture.md),
[phases.md](phases.md), [rules.md](rules.md), and [memory.md](memory.md). For the current two-day
demo's scope, limitations, and synthetic-only data, see [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md) and
[SECURITY_MODEL.md](SECURITY_MODEL.md) — this PRD describes the full V1 product, not the demo
subset.

## Executive summary

CloudOps is a multi-tenant AWS security-posture application. Organizations onboard customer AWS
accounts through cross-account IAM roles, inventory supported assets, apply deterministic security
rules, review findings/compliance/risk, obtain bounded AI explanations, approve notifications, and
govern remediation. Mock/dry-run remains the default; a default-disabled two-action live executor
exists for approved synthetic sandbox resources. No staging or production deployment or live AWS
remediation has been proven.

## Problem and users

Small cloud teams need consistent discovery, deterministic detection, prioritization, evidence, and
workflow controls without surrendering customer access keys or letting AI make security decisions.
Users are organization owners, security engineers, cloud operators, auditors, members/viewers, and
platform administrators.

## Primary use cases

1. Authenticate, create an organization, invite members, and enforce capability-based RBAC.
2. Onboard multiple AWS accounts with a customer role and External ID.
3. Run read-only discovery and retain normalized inventory.
4. Apply deterministic rules and produce findings.
5. Review compliance, risk, dashboard summaries, and audit history.
6. Ask AI for explanations, summaries, prioritization, and draft text.
7. Approve and deliver notifications through an enabled provider.
8. Preview, approve, enqueue, and audit deterministic dry-run remediation.
9. Schedule scans and monitor durable background jobs.

## Supported AWS scope

V1 centers on EC2, S3, and IAM evidence and rules. Collectors also exist for RDS, CloudWatch, and
CloudTrail; live compatibility remains pending AWS staging validation. The exact catalog in
`apps/api/app/services/discovery.py` and `apps/api/app/rules/` is authoritative.

- Customer access uses STS `AssumeRole`, External ID, and caller-account verification.
- Temporary STS credentials remain memory-only.
- Production runtime identity is designed for an ECS/Fargate task role.
- Static IAM-user credentials are unsuitable for production.
- Automated AWS tests use synthetic clients, fakes, or Botocore Stubber.
- A static, default-disabled executor exists only for S3 Public Access Block and exact EC2 public
  ingress-rule revocation; no live compatibility has been operationally verified.

## Functional requirements

### Identity, tenancy, and audit

- JWT access/refresh, invitation, membership, and capability-based RBAC flows.
- Every tenant-owned query is organization-scoped directly or through a verified parent.
- Cross-tenant access does not disclose existence.
- External IDs are excluded from ordinary account responses and exposed only through privileged
  onboarding operations.
- Audit evidence records actor, tenant, action, result, correlation, and sanitized metadata.

### Discovery and analysis

- Discovery runs asynchronously and preserves safe partial-failure evidence.
- **Deterministic rules detect findings; AI does not.**
- Findings update idempotently.
- Compliance and risk derive from deterministic persisted state.

### Background jobs

- PostgreSQL `platform_jobs` is the durable source of truth.
- Workers support tenant-scoped idempotency, leases/generations, heartbeats, bounded retries,
  cancellation, requeue, dead-letter state, correlation, and sanitized results.
- The scheduler transactionally claims due occurrences and enqueues durable scan orchestration.
- Celery and Redis are not part of the implemented architecture.

### Notifications

- Mock, SMTP, SES, Slack, and Teams provider contracts exist.
- Production SMTP is rejected; SES is the intended AWS email provider.
- Delivery rechecks current approval/authorization.
- Provider errors and stored evidence are sanitized.
- SES live delivery is not verified.

### AI assistant

- AI may explain findings, summarize, prioritize, and draft remediation/Jira/email content.
- AI output is untrusted advisory content.
- AI may not detect findings, authorize remediation, select executable operations, or mutate AWS.
- The Bedrock Converse adapter exists and is tested with Stubber; live invocation is pending.

### Remediation

- Preview, immutable snapshot, approval/rejection, idempotent enqueue, execution gating, and audit
  evidence are required.
- Only allowlisted action keys and versions may execute.
- The deterministic mock executor remains the default and is dry-run only.
- A static live executor is implemented only for S3 Public Access Block and exact EC2 public
  ingress-rule revocation; live AWS validation is pending.
- `REMEDIATION_EXECUTION_ENABLED` defaults off.
- `REMEDIATION_LIVE_AWS_ENABLED` alone cannot select live execution; emergency stop, server-owned
  request mode, sandbox approval, separate trust, tenant/target/snapshot/lease, tag, caller-account,
  drift, and verification gates must also pass.
- Dry-run remediation is not production remediation.

## Non-functional and security requirements

- Python 3.12+, strict Mypy, Ruff, typed APIs, and linear Alembic history.
- React/TypeScript lint, typecheck, tests, and production build gates.
- PostgreSQL production data path with explicit transactions and bounded pooling.
- Fail-closed production settings and dependency-aware readiness.
- Structured redacted logs with request/job correlation.
- Bounded AWS timeouts/retries; no long-lived AWS access keys.
- Secret values never appear in logs, responses, audit metadata, frontend variables, or job data.
- Managed secret injection and workload identity in production.
- Separate runtime, migration, publish, and deployment identities.
- Build once and promote immutable image digests.

## Deployment and observability requirements

- Provide an organization-managed single-host option where a named Cloudflare Tunnel reaches only
  Nginx, internal API/database ports are not published, migrations gate readiness, generated
  secrets persist securely, and normal stop/restart/update operations preserve data.
- Treat live named-tunnel, clean-machine, and restore evidence separately from implementation.

- Separate staging and production Terraform roots.
- ECS API, web, scheduler, job worker, and one-shot migration task.
- RDS PostgreSQL, ALB/WAF, KMS, Secrets Manager, CloudWatch, alarms, ECR, VPC flow logs, and access
  logs as defined under `infra/`.
- GitHub Actions OIDC with short-lived deployment sessions.
- CI gates for backend, frontend, containers, secrets, dependencies, migrations, and Terraform.
- Queue depth, dead letters, worker heartbeat, provider failures/latency, ALB, and database health.

Configuration does not prove deployment. Live alarms, routing, canary, rollback, restore, Bedrock,
and SES require retained external evidence.

## Success criteria

- Two organizations cannot access or infer each other's data.
- Discovery produces deterministic findings without storing AWS credentials.
- Jobs recover from worker loss without duplicate durable outcomes.
- AI remains advisory.
- Notifications require approval and retain sanitized evidence.
- Remediation remains allowlisted and approved; dry-run/mock is the default, while live execution
  requires independent trust, sandbox approval, human approval, flags, emergency-stop, target,
  snapshot, lease, tag, caller-account, drift, and postcondition gates.
- CI and release evidence is reproducible.
- Staging UAT, restore, rollback, provider, and observability exercises pass before production.

## Explicit non-goals

- AI detection or authorization.
- Arbitrary user-supplied AWS API calls, shell commands, or remediation code.
- Storing customer AWS keys.
- Arbitrary AWS mutation, automatic rollback, or live mutation outside the two sandbox actions.
- Universal AWS-service or compliance-framework coverage.
- A Celery/Redis broker.
- Inferring deployment from Terraform/workflow existence.

## Known limitations and live blockers

- No retained evidence of live staging or production apply.
- No live Bedrock invocation or SES delivery evidence.
- No completed UAT, weighted canary, rollback, or backup-restore rehearsal.
- Weighted traffic canary and cross-region/cross-account backup replication are deferred.
- Current runtime/UI branding still says CloudOps.
- Local test/scan summaries are **reported verification evidence; external log retention required**
  unless committed CI artifacts are supplied.

## Release acceptance

1. Clean reviewed diff and immutable commit.
2. CI gates pass from that commit.
3. Terraform plan is reviewed and contains no secret values.
4. OIDC identities, protected environments, and managed secrets are approved.
5. Staging migration, readiness, smoke, tenant-isolation, provider, UAT, load, restore, and rollback
   evidence is retained.
6. Residual risks and operational ownership are accepted.
7. Exact staging-tested image digests are promoted.
8. Production deployment has explicit authorization.

Until these gates pass, the truthful status is: **implemented and locally verified; live AWS
validation pending**.
