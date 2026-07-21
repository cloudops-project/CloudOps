# Worker Application Area â€” Stage 0 Placeholder

## Purpose and audience

Future backend/AWS contributors will use this area for background scanning, rule evaluation, integration delivery, and approved remediation orchestration.

Celery with Redis is the proposed MVP worker, behind portable job interfaces that allow later SQS adoption. Jobs contain opaque identifiers, reauthorize tenant ownership, obtain temporary STS credentials in memory, enforce leases/idempotency, and expose partial failure. Scanning is read-only; remediation uses separate approved permissions.

No queue, Python package, collector, rule, or executable worker exists yet. Worker choice remains a Stage 0 approval item.
