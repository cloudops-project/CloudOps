# Governed remediation operations

## Implementation status

CloudOps implements preview, approval, immutable snapshots, idempotency, durable job leases/heartbeats, deterministic allowlisting, bounded retries, precondition revalidation, verification/rollback plans, audit events, and emergency switches. Every executable action is a simulated dry run. No real AWS mutation executor exists.

## Approval

1. Confirm tenant, finding, account, rule/action version, dry-run status, exact preview, verification, and rollback.
2. Confirm the finding evidence is current.
3. Approve through the capability-protected endpoint.
4. The service binds approval to the snapshot hash; PostgreSQL prevents snapshot identity updates.

AI text is advisory and cannot choose, alter, or approve the action.

## Execution

Execution is disabled by default. In a synthetic environment only, set `REMEDIATION_EXECUTION_ENABLED=true`; keep `REMEDIATION_LIVE_AWS_ENABLED=false`.

The API returns a durable job. The worker reauthorizes the actor, validates tenant ownership, checks the allowlist/version/snapshot/finding evidence, binds the job lease, and invokes the deterministic mock executor.

## Emergency disablement

1. Set `REMEDIATION_EXECUTION_ENABLED=false`.
2. Scale the remediation-capable worker down only if the global job worker cannot safely continue.
3. Cancel available remediation jobs through the tenant-scoped job API.
4. Investigate audit events, snapshot hashes, attempts, and job correlations.
5. Do not alter immutable snapshots or manually mark outcomes successful.

Setting `REMEDIATION_LIVE_AWS_ENABLED=true` still fails closed because live execution is unavailable.

## Failure, stuck jobs, and rollback

- A worker crash leaves a lease that expires and can be safely reacquired.
- A running worker renews the lease every one-third of its lease interval.
- Retryable failures use bounded attempts and backoff; exhausted jobs dead-letter.
- Stale completions/failures are rejected.
- Simulated execution changes no AWS state, so rollback verifies that no mutation occurred.
- Any future live action requires a separate security review, least-privilege customer mutation role, exact pre/post state capture, sandbox evidence, and a tested action-specific rollback.
