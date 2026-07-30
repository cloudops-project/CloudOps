# CloudOps V1 handover

## Implemented and locally verified

- Multi-tenant authentication/RBAC, AWS onboarding, discovery, deterministic rules, compliance, risk, AI advisory, dashboard, notifications, Jira integration, simulated remediation, scheduler, audit, security hardening, workload identity, durable jobs, provider adapters, and tenant isolation.
- Bedrock/SES/Jira adapters with synthetic/CI-verified tests.
- Governed dry-run remediation and immutable PostgreSQL migration.
- Terraform source for staging/production and immutable OIDC release workflows.
- Structured operational logs, worker heartbeat, queue telemetry, CloudWatch resources, alarms, and runbooks.

## Implemented but awaiting live AWS validation

- Terraform bootstrap and environment plans/applies.
- ECS/RDS/ALB/WAF/KMS/Secrets Manager/CloudWatch resources.
- GitHub OIDC role assumption, ECR publishing, migration tasks, and deployment workflow.
- Bedrock model invocation, SES sandbox delivery, and Jira Cloud connection/issue creation.
- alarm delivery, restore rehearsal, staging UAT, load testing, and rollback rehearsal.
- AWS bootstrap infrastructure state (state bucket, lock table, KMS key, OIDC provider,
  publish/staging-deploy roles) was reported applied in a prior session; this is user-reported
  historical information, not independently verified with AWS CLI access in this environment.

## Deferred

- Live AWS mutation remediation.
- Weighted 5/25/50/100 canary or ECS CodeDeploy.
- cross-region/cross-account backups.
- provider production-volume tuning and cost baselines.

## Handover checklist

- [ ] Cloud account/region/cost owner approved.
- [ ] State backend and permissions boundary established.
- [ ] OIDC roles and protected GitHub Environments reviewed.
- [ ] Secrets populated through an approved channel.
- [ ] SES/Bedrock/ACM/DNS prerequisites complete.
- [ ] Terraform validates and staging plan has no secret values.
- [ ] staging deploy/smoke/UAT/load/restore/rollback rehearsals pass.
- [ ] threat model and residual risks accepted.
- [ ] production plan, exact digests, approval, alarms, and rollback are ready.

No production-ready or 100% claim is valid until every unchecked external gate passes.
