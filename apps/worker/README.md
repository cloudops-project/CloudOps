# Worker application

The executable worker is implemented in `apps/api/app/worker/job_worker.py`;
the replica-safe scheduler is in
`apps/api/app/worker/scheduler_worker.py`.

PostgreSQL is the durable V1 queue and job source of truth. Jobs contain bounded
opaque identifiers, reauthorize tenant ownership, obtain temporary STS
credentials in memory, enforce database idempotency and expiring leases, and
record sanitized partial failure. Discovery is read-only; remediation remains
simulated.

Run the processes with:

```text
python -m app.worker.job_worker
python -m app.worker.scheduler_worker
```

See `docs/architecture/distributed-jobs.md` and the operations runbooks. A
future SQS adapter may wake workers using job IDs only; it must not become a
second source of job state.
