# Audit Log Strategy

## Purpose and audience

Security, auditors, backend, and operations teams use this design to make sensitive CloudOps actions attributable and tamper-evident.

Audit authentication/security changes, organization/membership/role operations, AWS connection validation/revocation, scan request/cancel/result, finding transitions, risk acceptance, AI requests/status, reports/exports, Jira/notification actions, approvals, remediation attempts, verification, secrets/config administration, and privileged support access.

The current Stage 4 implementation persists `security.evaluation.*` and
`security.finding.*` audit events with tenant, actor, resource identifiers, safe counters,
result, and timestamp. Structured stdout/stderr operational logs are separate. Neither channel
may contain credentials, JWTs, passwords, headers, full policies, raw AWS errors, or unbounded
metadata. Stage 5 adds durable `compliance.assessment.started`,
`compliance.assessment.completed`, and sanitized failure events. Per-control status messages are
bounded operational logs rather than durable audit events. Database rows are protected by access
controls and transactional writes, but absolute audit immutability is not claimed. Risk, AI,
Jira, notification, and remediation events remain planned only.

Events include UTC time, organization, actor type/ID, action, target type/ID, result, reason/code, correlation and idempotency IDs, source/service, relevant version, and previous/event hash. Do not include credentials, tokens, external IDs, raw AI content, full policies, or customer application data. Events append in the business transaction via a reliable outbox pattern proposal.

Export signed/hash-chained batches to encrypted, versioned S3 with Object Lock capability considered for the required retention mode; access and deletion are separated and monitored. “Immutable” must not be claimed until configuration and reconciliation tests prove it. Authorized tenant users receive filtered read/export access; platform access is audited.

Open questions: retention/legal holds, Object Lock mode, key ownership, event schema/signing, clock source, export frequency, and privacy deletion interactions.
