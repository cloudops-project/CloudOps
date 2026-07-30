# CloudOps Operations (Index)

> Root-canonical pointer. The full operational surface — monitoring/alerting strategy, environment
> boundaries, migration safety, secrets management, backup/recovery, canary/rollback, and the
> scheduler/dead-letter/job-worker runbooks — lives under `docs/operations/`. This file adds only
> the day-to-day operator commands for the local two-day demo; it does not restate the general
> operations strategy.

Detailed sources: [docs/operations/monitoring-strategy.md](docs/operations/monitoring-strategy.md),
[docs/operations/environments.md](docs/operations/environments.md),
[docs/operations/migration-safety.md](docs/operations/migration-safety.md),
[docs/operations/secrets-management.md](docs/operations/secrets-management.md),
[docs/operations/backup-and-recovery.md](docs/operations/backup-and-recovery.md),
[docs/operations/canary-and-rollback.md](docs/operations/canary-and-rollback.md),
[docs/operations/scheduler-runbook.md](docs/operations/scheduler-runbook.md),
[docs/operations/job-worker-runbook.md](docs/operations/job-worker-runbook.md),
[docs/operations/dead-letter-runbook.md](docs/operations/dead-letter-runbook.md).

## Demo operations (the only thing this file adds)

Day-to-day commands, credentials, service list, and troubleshooting for the local demo are
canonical in [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md) — this file does not duplicate them. In summary,
operating the demo means:

- Starting/stopping: `scripts/demo_bootstrap.ps1`, `docker compose -f compose.demo.yml down`.
- Observing: `docker compose -f compose.demo.yml logs --tail=100 <service>` for `api`, `web`,
  `scheduler-worker`, `job-worker`, and (when the `tunnel` profile is active) `cloudflared`.
- Health: `scripts/demo_check.ps1` (add `-IncludeUserChecks` for the multi-user/role/session
  assertions).
- Temporary public access: `scripts/demo_tunnel.ps1` (`-Restart` for a fresh URL, `-NoFollow` to
  background it).

## What demo operations deliberately does not include

No monitoring stack, alerting, dashboard, or synthetic check runs against the demo — it is a
single-operator local stack, not a monitored service. No backup or restore procedure applies to
`cloudops_demo_postgres` (the named Compose volume); resetting is `--reset`, not a restore. No
migration-safety concern beyond `alembic upgrade head` running once in the `api` service's startup
command applies, because the demo database starts empty every time the volume is removed. None of
`docs/operations/monitoring-strategy.md`'s alarms, thresholds, or dashboards are wired to the demo
stack, and none should be inferred to exist from this file.

## Operational blocker carried into this session

The sandbox shell used to author and review this repository has been unavailable in every attempt
this session (`git`, `docker`, `pwsh`, `node`, `python3` all returned "Workspace unavailable... VM
service not running"). This is an operational fact about the authoring environment, not the demo
stack itself, but it means no command in this file or in `DEMO_RUNBOOK.md` has been executed here —
see `KNOWN_ISSUES.md` VAL-01.
