# Monitoring Strategy

> See [OPERATIONS.md](../../OPERATIONS.md) at the repository root for the operations document index,
> including why none of this monitoring/alerting is wired to the local demo stack.

## Current implementation (authoritative)

Implemented controls include JSON application logs with request IDs and a fixed safe-field allowlist; API duration/result events; job correlation, attempt, duration, retry, terminal, and heartbeat events; aggregate queue snapshots without tenant/resource dimensions; encrypted CloudWatch log groups; SNS routing; dashboard widgets; and alarms for ALB 5xx, unhealthy API targets, p95 latency, queue depth, dead letters, RDS CPU, storage, and connections.

Initial thresholds are p95 API latency above 1.5 seconds for 3 minutes, more than 5 ALB 5xx responses in each of 2 minutes, any unhealthy API target for 2 minutes, available queue depth above 100 for 5 minutes, any dead letter, RDS CPU above 80% for 5 minutes, storage below 10 GiB for 15 minutes, and connections above 200 for 5 minutes. These are safe starting values, not production-validated SLO evidence.

Never add tenant IDs, account IDs, resource ARNs, email addresses, bodies, or evidence as metric dimensions. On a release-correlated alarm, halt promotion, restore prior task definitions, preserve logs and plan/digest evidence, and never destructively downgrade the database.

SES bounce/complaint destinations, Bedrock service metrics, authentication anomaly thresholds, external synthetics, and production tuning require live staging validation.

The remaining historical proposal is retained for design context; where it says dashboards or alerts do not exist, this current implementation section supersedes it.

## Purpose and audience

Operators, developers, and security responders use this proposal to observe service health, security signals, and workflow correctness. No dashboards or alerts exist yet.

Monitor API latency/error/saturation, database pool/locks/storage, queue depth/age/retries/dead letters, worker leases/crashes, scan duration and coverage by service, AWS throttling/access denial, integration delivery, AI timeout/validation/cost, remediation approval/execution/verification, audit export lag/gaps, and backup outcomes. Use safe tenant-pseudonymous dimensions with correlation IDs; avoid sensitive high-cardinality resource values.

Alert on sustained user impact, tenant-scope denial anomalies, credential/role validation spikes, queue backlog, repeated remediation failure/replay, audit-chain/export gaps, secret access anomaly, and restore failure. Alerts have severity, owner, runbook, escalation, deduplication, and recovery condition. CloudWatch is the AWS baseline; exact APM/log tooling is open.

Service objectives and thresholds must be based on Stage 12–15 measurements, customer expectations, and budget. Synthetic checks must avoid real remediation and customer data.
