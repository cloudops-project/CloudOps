# Monitoring Strategy

## Purpose and audience

Operators, developers, and security responders use this proposal to observe service health, security signals, and workflow correctness. No dashboards or alerts exist yet.

Monitor API latency/error/saturation, database pool/locks/storage, queue depth/age/retries/dead letters, worker leases/crashes, scan duration and coverage by service, AWS throttling/access denial, integration delivery, AI timeout/validation/cost, remediation approval/execution/verification, audit export lag/gaps, and backup outcomes. Use safe tenant-pseudonymous dimensions with correlation IDs; avoid sensitive high-cardinality resource values.

Alert on sustained user impact, tenant-scope denial anomalies, credential/role validation spikes, queue backlog, repeated remediation failure/replay, audit-chain/export gaps, secret access anomaly, and restore failure. Alerts have severity, owner, runbook, escalation, deduplication, and recovery condition. CloudWatch is the AWS baseline; exact APM/log tooling is open.

Service objectives and thresholds must be based on Stage 12–15 measurements, customer expectations, and budget. Synthetic checks must avoid real remediation and customer data.
