# Rollback and recovery

## Application release rollback

Promote immutable image digests. Record the stable task definitions/digests before change, deploy
additive migrations first, and restore the prior application digest when health thresholds fail.
Do not destructively roll back a database schema. Use expand-and-contract migrations.

## Job and provider recovery

Leases, generations, heartbeats, retries, and idempotency protect durable jobs. A stale worker must
not complete a reclaimed job. Provider attempts retain sanitized evidence and move to retry or
dead-letter state according to policy.

## Remediation recovery

Each supported live action captures exact rollback state. S3 stores the previous four-value Public
Access Block configuration or explicit absence. EC2 stores the exact ingress-rule structure.
Rollback is manual and separately approved; automatic rollback is not implemented. Revalidate
account, tenant, tags, target, current state, and unrelated resources before restoration.

## Data recovery

Backups must be restored into a separate isolated database, migrated, integrity-checked, and sampled
for representative tenant boundaries before use. Never overwrite active data during rehearsal.

Implementation and local/CI tests do not prove operational rollback or restore. Both remain **Not
yet verified** for AWS staging.
