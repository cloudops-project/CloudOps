# Local development

Use synthetic values and local provider modes. Do not place AWS keys, provider tokens, External
IDs, or production data in repository files.

## Services

The standard Compose topology includes PostgreSQL, migration, API, web, scheduler worker, and job
worker. Demo/local profiles may add Mailpit and synthetic seed helpers. PostgreSQL is the durable
job backend; Redis and Celery are not required.

```powershell
Set-Location <repository-root>
docker compose -f compose.yml config --quiet
docker compose -f compose.demo.yml config
docker compose -f compose.demo.yml up --build
```

Backend commands run from `apps/api`; frontend commands run from `apps/web`. Use the repository's
existing virtual environment and lockfile. Typical safe gates are documented in
[test strategy](../testing/test-strategy.md).

The current Alembic head is `0019_live_remediation_data_model`. Do not modify historical migrations
or use a development database as proof of PostgreSQL production compatibility.
