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
controls and transactional writes, but absolute audit immutability is not claimed. AI,
notification, durable-job, scheduler, Jira, dry-run remediation, and privileged remediation
administration events are implemented. Live provider and AWS audit correlation remain external
validation work.

Events include UTC time, organization, actor type/ID, action, target type/ID, result, reason/code, correlation and idempotency IDs, source/service, relevant version, and previous/event hash. Do not include credentials, tokens, external IDs, raw AI content, full policies, or customer application data. Events append in the business transaction via a reliable outbox pattern proposal.

Export signed/hash-chained batches to encrypted, versioned S3 with Object Lock capability considered for the required retention mode; access and deletion are separated and monitored. “Immutable” must not be claimed until configuration and reconciliation tests prove it. Authorized tenant users receive filtered read/export access; platform access is audited.

Open questions: retention/legal holds, Object Lock mode, key ownership, event schema/signing, clock source, export frequency, and privacy deletion interactions.

## Stage 6 risk events

Stage 6 adds durable accepted-transition events for `risk.assessment.started`,
`risk.assessment.completed`, `risk.assessment.failed`, `risk.context.changed`,
`risk.compensating_control.added`, and `risk.compensating_control.removed`. Operational events
may also include `risk.finding.scored` and `risk.aggregate.updated`. Only bounded identifiers,
counts, durations, policy versions, component reason codes, and sanitized error codes are
allowed; credentials, authorization headers, raw policies, raw exceptions, and unbounded
evidence are prohibited.

Risk snapshots are database-immutable; audit records are durable transactional records but are
not described as absolutely immutable. Stage 7 explanation requests use the bounded event design below.
## Stage 7 AI events

Durable events record accepted request completion or sanitized failure with
bounded organization, actor, request, task, provider-key, and error-code
metadata. Prompts, raw evidence, provider credentials, authorization headers,
raw provider errors, and generated long-form content are excluded from logs
and audit metadata.
