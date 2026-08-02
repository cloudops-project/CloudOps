# CI pipeline

`.github/workflows/ci.yml` runs on pushes and pull requests with read-only repository contents
permission and concurrency cancellation. Its seven major jobs are:

| Job ID | Display name | Principal checks |
|---|---|---|
| `selfhost-fast` | Self-host static and unit gate | Self-host scripts/configuration, Ruff, focused tests |
| `selfhost-containers` | Self-host container gate | Generated configuration, container topology, migration/current-head and health behavior |
| `backend` | Backend | Ruff, strict Mypy, dependencies, full tests, PostgreSQL, Alembic upgrade/current/check/preflight |
| `frontend` | Frontend | `npm ci`, lint, typecheck, tests, build, high-severity audit |
| `containers` | Containers | API/web builds and Compose configuration |
| `secret-scan` | Secret scan | Redacted Gitleaks scan |
| `infrastructure` | Terraform and IaC security | Terraform format/init/validate/tests and Checkov/static assertions |

The release workflow is separate. It builds/scans/publishes once, deploys and verifies staging only
under its explicit gate, creates a reviewable production plan, and requires protected production
approval before promotion of the exact digests. Workflow presence does not mean it has deployed.

For commit `bec5753ad127d8ed8968d539ee625130c6a2e06f`, all seven jobs completed successfully in
[GitHub Actions run 30733971880](https://github.com/cloudops-project/CloudOps/actions/runs/30733971880).
Retain its artifacts when using the run as release evidence.
