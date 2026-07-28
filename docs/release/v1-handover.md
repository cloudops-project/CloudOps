# CloudOps V1 handover

## Implemented and locally verified

- Multi-tenant authentication/RBAC, AWS onboarding, discovery, deterministic rules, compliance, risk, AI advisory, dashboard, notifications, simulated remediation, scheduler, audit, security hardening, workload identity, durable jobs, provider adapters, and tenant isolation.
- Bedrock/SES adapters with synthetic AWS tests.
- Governed dry-run remediation and immutable PostgreSQL migration.
- Terraform source for staging/production and immutable OIDC release workflows.
- Structured operational logs, worker heartbeat, queue telemetry, CloudWatch resources, alarms, and runbooks.

## Implemented but awaiting live AWS validation

- Terraform bootstrap and environment plans/applies.
- ECS/RDS/ALB/WAF/KMS/Secrets Manager/CloudWatch resources.
- GitHub OIDC role assumption, ECR publishing, migration tasks, and deployment workflow.
- Bedrock model invocation and SES sandbox delivery.
- alarm delivery, restore rehearsal, staging UAT, load testing, and rollback rehearsal.

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
