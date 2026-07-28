# Local / Staging Deployment Guide

## Purpose and audience

Operators standing up the current PostgreSQL-backed stack (API, worker processes, web) in a staging-like environment using `compose.yml`. This documents what exists today, not the longer-term cloud topology in `deployment-strategy.md`.

## Required environment variables

Names only — see `.env.example` for the full list. Set real values in an untracked `.env`; never commit secrets. Minimum required for a working stack: `APP_ENV`, `DATABASE_URL`, `JWT_SECRET_KEY` (32+ characters), `CORS_ALLOWED_ORIGINS`, `TRUSTED_HOSTS`, `FRONTEND_URL`. Notification delivery additionally needs either `NOTIFICATION_PROVIDER=smtp` with `SMTP_*`, or `NOTIFICATION_PROVIDER=slack`/`teams` with the matching `*_WEBHOOK_URL`; use `NOTIFICATION_PROVIDER=mock` in any environment that must not send real notifications (recommended for staging smoke tests).

Synthetic example values only — do not reuse these anywhere real:

```
APP_ENV=staging
DATABASE_URL=<injected-by-approved-secret-source>
JWT_SECRET_KEY=<injected-by-approved-secret-source>
CORS_ALLOWED_ORIGINS=https://staging.example.invalid
TRUSTED_HOSTS=staging.example.invalid
FRONTEND_URL=https://staging.example.invalid
NOTIFICATION_PROVIDER=mock
```

## Startup order

1. `postgres` (and `mailpit` if using the SMTP notification provider) must be healthy first — `compose.yml` encodes this via `depends_on: condition: service_healthy`.
2. `migrate` runs `alembic upgrade head` once and exits. `api` will not start until `migrate` exits 0 (`condition: service_completed_successfully`). API replicas do not run migrations themselves — do not scale `api` before `migrate` has completed at least once against the target database.
3. `api` starts.
4. `scheduler-worker` and `job-worker` (both `profiles: [manual]`, started explicitly with `--profile manual` or by name) may start any time after `api` is reachable. They poll the database independently and do not require a specific startup order relative to each other.
5. `web` starts after `api`.

Example:

```
docker compose -f compose.yml up -d postgres mailpit migrate
docker compose -f compose.yml up -d api web
docker compose -f compose.yml --profile manual up -d scheduler-worker job-worker
```

## Migration order

See `migration-safety.md` for the full procedure. In short: back up, run `scripts/migration_preflight.py` against a disposable copy, run `migrate` (or `alembic upgrade head`) once against the real target, confirm `alembic current` equals `alembic heads`, then start/roll `api` and the workers.

## Health and readiness verification

- `GET /health` — liveness only, always 200 if the process is up. Use for container/orchestrator liveness probes.
- `GET /ready` — dependency-aware; returns 503 with `{"code": "dependency_unavailable", ...}` if the database is unreachable, 200 `{"status": "ready"}` otherwise. Use for readiness probes and load-balancer target health.

```
curl -sf http://localhost:8000/health
curl -sf http://localhost:8000/ready
```

A 503 from `/ready` with a 200 from `/health` means the process is up but the database is not reachable — do not restart the container for this alone; investigate the database first.

## Smoke tests

Run `scripts/staging_smoke.py` against a running stack (see the script's docstring for required environment variables). It exercises liveness, readiness, registration/login, org creation, a queued evaluation request, worker processing to a terminal job state, and mock-provider notification delivery — no real AWS or webhook calls.

## Rollback procedure

1. Stop routing traffic to the new `api`/worker images (revert the image tag / stop the new replicas).
2. Restore the pre-migration backup if the release included a migration (see `migration-safety.md` — `alembic downgrade` is not a supported rollback path).
3. Start the previous known-good `api`/worker images against the restored database.
4. Verify `/health`, `/ready`, and the smoke test pass against the rolled-back stack before resuming traffic.

## Backup / restore checklist

See `backup-and-recovery.md` for the full policy. Before any migration: confirm a backup completed successfully within the last operational window, confirm the backup is restorable (not just written), and record the backup identifier used for this release in the release log.

## Log and alert signals to watch after a deploy

- `readiness.failed` (from `/ready`) — database unreachable.
- `platform.job.stale_completion_ignored` / `platform.job.stale_failure_ignored` — expected under normal lease contention; a sustained spike suggests worker crash-looping or lease misconfiguration.
- Sustained `DEAD_LETTERED` job growth (via job counts) — a job type is failing every retry attempt.
- SMTP/webhook notification delivery `retryable` failures — provider or network issue, not a code regression by itself.

## Common failure modes

- `/ready` returns 503 immediately after deploy: `migrate` did not complete, or `DATABASE_URL` is wrong for the `api` container's network (e.g., pointing at `localhost` instead of the `postgres` service name).
- Jobs enqueue but never process: no `job-worker` replica is running (it is `profiles: [manual]` and must be started explicitly).
- Scheduled scans never fire: no `scheduler-worker` replica is running, for the same reason.
- Notifications never deliver in staging: `NOTIFICATION_PROVIDER` is unset or pointed at a provider without valid (even if staging-scoped) credentials — use `mock` if delivery isn't under test.

## Release sign-off checklist

- [ ] Backend CI job green (Ruff, Mypy, Pytest incl. PostgreSQL, Alembic single-head + upgrade check, pip check, pip-audit)
- [ ] Frontend CI job green (lint, typecheck, tests, production build, npm audit)
- [ ] Container CI job green (API + web image build, compose config validation)
- [ ] Fresh, verified backup taken immediately before migration
- [ ] `scripts/migration_preflight.py` passed against a disposable copy of the target database
- [ ] `scripts/staging_smoke.py` passed against the staged release before promoting
- [ ] Rollback plan (previous image tag, backup identifier) recorded in the release log
