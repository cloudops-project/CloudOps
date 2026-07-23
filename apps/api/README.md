# CloudOps API

FastAPI service for identity/tenancy, cross-account onboarding, read-only discovery, and Stage 4
deterministic findings. Route handlers delegate to services; repositories own tenant-scoped
persistence.

## Commands

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\uvicorn.exe app.main:app --reload
.\.venv\Scripts\pytest.exe --cov=app --cov-report=term-missing
.\.venv\Scripts\ruff.exe format --check app
.\.venv\Scripts\ruff.exe check --no-cache app
.\.venv\Scripts\mypy.exe --cache-dir "$env:TEMP\cloudops_mypy_cache" app
```

Use `alembic downgrade base` only against a disposable development/test database. Production uses PostgreSQL. Tests inject an isolated SQLite database.

Authentication uses Argon2 passwords, 15-minute access JWTs by default, and opaque rotating refresh cookies. PostgreSQL `FOR UPDATE` locks serialize refresh rotation, invitation acceptance, and final-owner changes. Admins cannot govern owner memberships. Production invitation responses omit development tokens.

The root `compose.verify.yml` provides the disposable PostgreSQL database. Set `POSTGRES_TEST_DATABASE_URL` to its `cloudops_test` database before running `app\tests\test_postgres_concurrency.py`; the test rejects any other database name.

## Stage 2 AWS onboarding

Set `AWS_TRUSTED_PRINCIPAL_ARN` to the CloudOps AWS principal that customers may trust and
optionally override `AWS_ROLE_SESSION_NAME`. Owners/admins create an account record, receive a
permanently reserved external ID and generated trust/permission guidance, save a matching role
ARN, and validate it. Validation calls `AssumeRole` and then `GetCallerIdentity` with in-memory
temporary credentials. Row locks and a validation operation token prevent stale STS results from
overwriting update, disconnect, or deletion.

## Stage 3 discovery

Connected accounts may inventory EC2, S3, IAM, and RDS metadata. Configure regions with
`AWS_DISCOVERY_REGIONS`; configure bounded clients with `AWS_CONNECT_TIMEOUT_SECONDS`,
`AWS_READ_TIMEOUT_SECONDS`, `AWS_MAX_RETRY_ATTEMPTS`, and `AWS_RETRY_MODE`. Assets and jobs are
tenant-bound through composite PostgreSQL foreign keys. Discovery never evaluates security
posture and never mutates customer AWS resources.

## Stage 4 evaluation

Discovery also persists bounded configuration for EC2 security groups/EBS, S3, IAM, RDS,
CloudWatch alarms/log groups, and CloudTrail. Boto3 remains in discovery. Typed rules under
`app/security_rules` evaluate persisted assets only. Evaluation/finding APIs enforce tenant
scope and RBAC. Alembic head `0005_stage4_rule_engine` adds evaluation jobs and findings. Raw
provider events, compliance, risk, AI, and remediation are not implemented.
