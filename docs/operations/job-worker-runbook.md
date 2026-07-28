# Job worker runbook

Run `python -m app.worker.job_worker` as a service separate from the API and
scheduler. Use the same application image, database schema, workload identity,
and infrastructure-injected secrets. Never inject customer STS credentials.

The worker acquires one available or expired job with `SKIP LOCKED`, commits its
lease, reloads tenant-owned records, performs the operation, and records a
sanitized result. `SIGTERM`/`SIGINT` stop new acquisitions; the current
operation receives the platform termination grace period. Configure the
container grace period above the longest normal operation and the lease long
enough for the bounded operation. A forced stop leaves a lease that another
worker may reclaim after expiry.

Monitor queue depth, oldest age, duration, retry/dead-letter rates and lease
expirations. For an incident: stop worker scaling, preserve database evidence,
classify the failing job/provider, revoke compromised workload identity or
provider secret, rotate it through the managed secret source, then requeue only
safe jobs. Never copy payloads or provider responses into tickets.

The disposable stack is:

`docker compose -f compose.phase3.verify.yml up --build --abort-on-container-exit`

It exposes no provider endpoint publicly, uses synthetic values, and uses
tmpfs PostgreSQL storage.
