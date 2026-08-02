# Self-hosted deployment

The canonical detailed procedure is [self-hosted Cloudflare deployment](self-hosted-cloudflare-deployment.md).
This page summarizes its current security boundary.

- A pre-created named Cloudflare Tunnel routes only to the internal web/Nginx service.
- API and PostgreSQL ports are not published to the host.
- The controller generates persistent internal secrets, runs and verifies migrations, starts API,
  web, scheduler, and job worker, then performs health checks.
- PostgreSQL data and backups are persistent; updates require a rollback point.
- Root startup helpers drop the application runtime to UID 10001 where implemented.
- Tunnel tokens use file-secret handling and redacted diagnostics.

Configuration and automated tests are **Implemented/CI verified**. A clean-machine deployment,
named-tunnel operation, backup restore, and update rollback require retained operational evidence.
This path is not the managed AWS sandbox and does not prove production readiness.
