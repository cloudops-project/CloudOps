# Release Migration Procedure

## Purpose and audience

Operators running a release that includes new Alembic revisions use this to avoid concurrent-migration races and unreviewable rollbacks.

## One-time release migration

Migrations run exactly once per release, from a single controlled process — never from every API replica on boot. The `migrate` service in `compose.yml` is that single controlled process: it runs `alembic upgrade head` to completion and exits, and the `api` service now depends on `migrate` finishing successfully (`condition: service_completed_successfully`) before it starts. API replicas no longer run `alembic upgrade head` themselves.

Release sequence:

1. Take a fresh, verified backup of the target database (see `backup-and-recovery.md`; do not proceed without one).
2. Run `python scripts/migration_preflight.py` against a disposable copy of the target database, restored from the same backup. It checks for a single migration head and reports the database's current revision. It must exit 0 before you continue.
3. Run the `migrate` service (or `alembic upgrade head` directly) once against the real target database.
4. Confirm `alembic current` matches `alembic heads` on the target database.
5. Start/roll the `api` and worker replicas.

## Rollback limitations

Alembic downgrades are only as safe as each revision's `downgrade()` implementation; this project does not maintain tested downgrade paths for every revision. Treat `alembic downgrade` as unverified — the supported rollback path is restoring the pre-migration backup taken in step 1, not running `downgrade` against a live database. Application code compatibility with an older schema is not guaranteed once a new revision has run, so a rollback also requires rolling the application image back to the version that matches the restored schema.

## Backup requirements

A migration must never run against a target database without a backup taken immediately beforehand, per `backup-and-recovery.md`. The preflight script does not take a backup — that step is manual and must be confirmed complete before step 2.
