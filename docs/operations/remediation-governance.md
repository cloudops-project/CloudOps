# Governed remediation operations

## Implementation status

CloudOps implements preview, approval, immutable snapshots, idempotency, durable job leases/heartbeats, deterministic allowlisting, bounded retries, precondition revalidation, verification/rollback evidence, audit events, and emergency switches. The mock executor remains the default. A two-action AWS executor exists but is disabled by default and has not been validated against live AWS.

## Approval

1. Confirm tenant, finding, account, rule/action version, dry-run status, exact preview, verification, and rollback.
2. Confirm the finding evidence is current.
3. Approve through the capability-protected endpoint.
4. The service binds approval to the snapshot hash; PostgreSQL prevents snapshot identity updates.

AI text is advisory and cannot choose, alter, or approve the action.

## Execution

Execution is disabled by default. For synthetic operation, set `REMEDIATION_EXECUTION_ENABLED=true`; keep `REMEDIATION_LIVE_AWS_ENABLED=false` and `REMEDIATION_EMERGENCY_STOP=true` unless a separately approved sandbox exercise is underway.

The API returns a durable job. The worker reauthorizes the actor, validates tenant ownership, checks the allowlist/version/snapshot/finding evidence, and binds the job lease. Mock requests invoke the deterministic mock executor. A `live_aws` request additionally requires both feature flags, inactive emergency stop, complete sandbox approval, separate remediation trust, exact target/snapshot, required tags, verified caller account, and unchanged AWS preconditions.

Only an organization owner may configure or rotate the separate remediation trust, clear it, or
grant/revoke sandbox approval. External IDs are generated server-side and shown only once. An owner
may prepare an already-approved immutable request for live execution; preparation derives the
allowlisted action and target from tenant-owned records, binds finding and asset evidence, resets
the request to pending approval, and never enqueues work.

## Emergency disablement

1. Set `REMEDIATION_EMERGENCY_STOP=true`.
2. Set `REMEDIATION_LIVE_AWS_ENABLED=false`, then `REMEDIATION_EXECUTION_ENABLED=false`.
3. Scale the remediation-capable worker down only if the global job worker cannot safely continue.
4. Cancel available remediation jobs through the tenant-scoped job API.
5. Investigate audit events, snapshot hashes, attempts, request IDs, and job correlations.
6. Do not alter immutable snapshots or manually mark outcomes successful.

Setting `REMEDIATION_LIVE_AWS_ENABLED=true` alone cannot enable execution; the independent emergency stop and every request/account/resource gate must also pass.

## Failure, stuck jobs, and rollback

- A worker crash leaves a lease that expires and can be safely reacquired.
- A running worker renews the lease every one-third of its lease interval.
- Retryable failures use bounded attempts and backoff; exhausted jobs dead-letter.
- Stale completions/failures are rejected.
- Simulated execution changes no AWS state, so rollback verifies that no mutation occurred.
- Live execution captures exact rollback state but does not automatically execute rollback. Follow the [live AWS remediation runbook](live-aws-remediation-runbook.md) for the separately authorized sandbox process.
