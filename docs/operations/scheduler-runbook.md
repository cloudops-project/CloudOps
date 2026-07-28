# Scheduler runbook

Run `python -m app.worker.scheduler_worker` in one or more replicas. Each tick
locks a bounded batch of due schedules with `FOR UPDATE SKIP LOCKED`, persists
one occurrence idempotency key, advances `next_run_at`, and enqueues work. It
never performs discovery inline.

Schedule timestamps are timezone-aware UTC. Interval schedules avoid local DST
ambiguity. Disabled schedules have no next run; resume calculates a fresh next
run. The V1 catch-up policy is deliberately bounded to one occurrence per
schedule per tick, preventing unbounded backlog after downtime.

Alert when the oldest due schedule exceeds twice the poll interval or the
scheduler produces no ticks. On shutdown, signals prevent another tick after
the current short transaction. During recovery, start one replica, confirm
`last_enqueued_at` advances without duplicate active runs, then restore normal
replica count.
