# Failure Scenarios

## Purpose and audience

Engineers, operators, and QA use these scenarios to design explicit failure states instead of silent or unsafe retries.

| Scenario | Safe behavior | Recovery / evidence |
|---|---|---|
| STS denied or role removed | Mark connection degraded/invalid; stop scans; never ask for keys | Sanitized reason, retry guidance, audit event, revalidation |
| AWS throttling/partial pagination | Bounded jittered retry; mark run partial, not successful | Checkpoints and per-service coverage |
| Queue duplicate/replay | Lease and idempotency prevent duplicate run/effect | Attempt record and replay metric |
| Worker crash | Temporary credentials expire; incomplete run cannot publish complete snapshot | Lease timeout and resumable/restarted attempt |
| Database unavailable | Fail closed for authorization and durable state | No external action without persisted intent; operational alert |
| AI unavailable/invalid | Omit explanation and use deterministic guidance | Status metadata; bounded retry; no scan failure |
| Jira/notification outage | Durable integration event, bounded retry/dead letter | Visible delivery state; manual retry with authorization |
| Approval races or duplicate remediation | Optimistic lock and unique idempotency key permit one valid transition | Conflict response and audit history |
| Remediation partial failure | Stop playbook, record changed/unchanged resources; do not mark resolved | Document rollback/manual recovery, verification scan |
| Audit archive failure | Keep durable outbox/local event and alert; do not discard | Replay export and reconcile hashes |
| Tenant-scope ambiguity | Deny access/work | Security alert with redacted context |
| Backup restore failure | Do not promote unverified restore | Escalate incident; test on approved schedule |

## Open questions

Approve retry budgets, dead-letter ownership, cancellation semantics, rollback support per playbook, incident thresholds, and RPO/RTO after cost and risk analysis.
