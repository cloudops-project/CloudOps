# CloudOps

CloudOps is an AWS-focused, multi-tenant SaaS application for identity and organization
administration, secure cross-account AWS onboarding, read-only asset discovery, deterministic
security findings, and evidence-based compliance assessments. It is intended for organization
owners, administrators, security analysts, cloud engineers, auditors, and viewers.

Stages 1-8 are implemented, independently clean-room verified, merged, and regression-tested in
`main`. Stages 9-12 (notifications, remediation, scheduler, and audit query/export) are
implemented and committed on `feature/v1-demo-completion`, independently verified on that
branch, and not yet merged into `main`. Stage 4
deterministic rules detect findings from persisted inventory; Stage 5 interprets that deterministic evidence for
compliance and never performs independent detection. Stage 6 prioritizes persisted findings
using the deterministic, versioned `CLOUDOPS_RISK_V1` policy. Stage 7 explains existing
records and generates advisory drafts only. AI is not used for finding detection, compliance
decisions, risk scoring, AWS mutation, remediation execution, Jira creation, or email delivery.

CloudOps uses read-only AWS discovery with STS temporary credentials. It never requires
long-lived customer access keys and does not mutate customer AWS resources. Automated tests use
deterministic doubles and synthetic data; never point them at production or customer AWS
accounts.

## Current verified baseline

| Item                  | Verified value                                                             |
| --------------------- | -------------------------------------------------------------------------- |
| Integrated `main`     | `889660ecb8a378d107f6737b4466b70362066793`                                 |
| Stage 6 feature SHA   | `b0361b8efe9060ef6c498e1cebfede4baaa9947d`                                 |
| Stage 7 feature SHA   | `9b5f4372359a32066787060ca839d5a68c5ab490`                                 |
| Migration head (`main`) | `0009_stage7_ai_assistant`                                                |
| Backend/frontend/black-box/coverage counts on `main` | Not re-verified since Stage 7; re-run the full quality-gate sequence below before citing fresh numbers |
| Dependencies/security | `pip check`, Python audit, npm audit, and security scans passed as of Stage 7 |

PR #8 merged Stage 7 at `2026-07-24T19:19:02Z` with merge commit
`882ff531af07276c11e0d25664fdca033e09c7c7`. It had zero recorded reviews or approvals and no
automated check rollup. The exact feature SHA passed technical detached verification, and the
merge proceeded under: **Owner-authorized governance exception for PR #8.** This was not an
independent GitHub, CODEOWNER, automated CI, or repository-policy approval.

Stage 8 merged via PR #10 (`feature/8-dashboard`) plus a follow-up `feature/8-dashboard-ui`
branch merge, reaching `main` at `889660ecb8a378d107f6737b4466b70362066793`. This record does
not independently confirm PR #10's review/approval state; verify it before treating it as
equivalent governance evidence to PR #8.

### Active feature branch state (`feature/v1-demo-completion`, not yet merged into `main`)

| Item | Verified value |
| --- | --- |
| Branch | `feature/v1-demo-completion`, created from `feature/9-notifications` |
| Committed HEAD | `5a6b00f docs: reconcile CloudOps demo readiness and Codex handoff` before the current demo-readiness changes |
| Migration head | `0013_demo_notification_delivery` on the current demo-readiness worktree |
| Stage 9 commits | `d0b5676`, `449e964`, `cb42db9` (backend), `d1c8733` (frontend, combined with Stage 10) |
| Stage 10 commits | `bf29173`, `fc8908d`, `8ab8c83` (backend), `d1c8733` (frontend), `8916be9` (test fixture repair) |
| Stage 11 commits | `24227ab`, `9fff532`, `8c14b55`, `55c451e` |
| Stage 11 backend verification | Ruff passed; Mypy passed (140 source files); scheduler Pytest 22 passed; one non-blocking Starlette/httpx deprecation warning |
| Stage 11 migration verification | `0010_stage9_notifications -> 0011_stage10_remediation` and `0011_stage10_remediation -> 0012_stage11_scheduler` upgraded successfully against the disposable verification database; `alembic current` reports `0012_stage11_scheduler`; `alembic check` reports no new operations; chain is linear with a single head |
| Stage 11 frontend verification | TypeScript passed; ESLint passed; scheduler Vitest 5 passed; production build passed |
| Stage 12 | Implemented and committed at `d0d24cd` and `9314f06`; targeted backend and frontend verification clean. |
| Demo-readiness follow-up | Adds Mailpit-backed local SMTP delivery, a guarded local demo Compose stack, deterministic demo seed/reset, and an 18-step V1 demo black-box acceptance runner. |

`main` itself has not moved past Stage 8; Stages 9-12 exist only on `feature/v1-demo-completion`
until merged through normal review.

## Technology stack

- Backend: Python 3.12–3.13, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, PostgreSQL, boto3,
  Argon2, and PyJWT
- Frontend: React 19, TypeScript 5.9, Vite 7, Tailwind CSS, React Router, TanStack Query,
  React Hook Form, Zod, and Lucide
- Verification: Pytest, pytest-cov, Ruff, Mypy, Vitest, Testing Library, ESLint, Prettier,
  `pip-audit`, and `npm audit`

## Repository structure

```text
CloudOps/
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── api/              FastAPI routers
│   │   │   ├── models/           SQLAlchemy models
│   │   │   ├── schemas/          Pydantic request/response schemas
│   │   │   ├── services/         Transactions and application workflows
│   │   │   ├── repositories/     Tenant-scoped persistence
│   │   │   ├── security_rules/   Trusted deterministic Stage 4 rules
│   │   │   └── tests/            Backend and PostgreSQL tests
│   │   ├── alembic/              Migration environment and revisions
│   │   ├── alembic.ini
│   │   └── pyproject.toml
│   └── web/
│       ├── src/                   React application and frontend tests
│       ├── package.json
│       └── package-lock.json
├── docs/
│   ├── architecture/              Detailed designs, trust boundaries, ADRs
│   ├── engineering/               Security, testing, and development policies
│   ├── operations/                Audit and operational guidance
│   └── planning/                  Detailed phase plan and project memory
├── compose.verify.yml             Disposable PostgreSQL 16 verification service
├── compose.demo.yml               Local demo stack with PostgreSQL, Mailpit, API, web, and manual scheduler tick
├── compose.yml                    Convenience alias for the local demo stack
├── demo_v1.md                     Human-operated local Version 1 demo runbook
├── .env.example                   Environment-variable names only
└── README.md                      Primary teammate setup and operating guide
```

Generated directories such as `.venv`, `node_modules`, `dist`, coverage output, and tool caches
are ignored and intentionally omitted.

## Prerequisites

- Git
- Python `>=3.12,<3.14` (Python 3.12 is the configured Mypy/Ruff target)
- Node.js 20 LTS or 22 LTS and npm
- Docker Desktop with Docker Compose, or a separately managed PostgreSQL installation
- PowerShell for the commands below
- Optional: GitHub CLI (`gh`) for release work

Node 23 is not recommended because current tooling can emit engine and experimental
type-stripping warnings.

```powershell
git --version
python --version
node --version
npm --version
docker --version
docker compose version
```

## Clone and branch setup

```powershell
git clone https://github.com/cloudops-project/CloudOps.git
cd CloudOps
git switch main
git pull --ff-only origin main
```

`main` contains the integrated Stage 7 product and documentation baseline. Create a separate
branch for every focused task or stage. Do not commit directly to `main`, force push, or
rewrite shared history.

## Environment configuration

The API uses Pydantic Settings and loads `.env` from its current working directory. When running
commands from `apps/api`, place the untracked file at `apps/api/.env`, or set variables in the
PowerShell session. The frontend reads `VITE_API_BASE_URL` from its process environment or a
Vite environment file under `apps/web`.

Copy the example as a starting point:

```powershell
Copy-Item .env.example apps/api/.env
```

Never commit `.env` files or real secrets.

### Required API variables

| Variable         | Purpose                                                 |
| ---------------- | ------------------------------------------------------- |
| `DATABASE_URL`   | SQLAlchemy PostgreSQL URL using `postgresql+psycopg://` |
| `JWT_SECRET_KEY` | Signing secret of at least 32 characters                |

### Optional API variables and defaults

| Variable                        | Default or purpose                                             |
| ------------------------------- | -------------------------------------------------------------- |
| `APP_ENV`                       | `development`; allowed: `development`, `testing`, `production` |
| `APP_NAME`                      | `CloudOps API`                                                 |
| `API_V1_PREFIX`                 | `/api/v1`                                                      |
| `JWT_ALGORITHM`                 | `HS256`                                                        |
| `ACCESS_TOKEN_EXPIRE_MINUTES`   | `15`, maximum 60                                               |
| `REFRESH_TOKEN_EXPIRE_DAYS`     | `14`                                                           |
| `INVITATION_TOKEN_EXPIRE_HOURS` | `72`                                                           |
| `CORS_ALLOWED_ORIGINS`          | `http://localhost:5173`                                        |
| `TRUSTED_HOSTS`                 | `localhost,127.0.0.1,testserver`                               |
| `COOKIE_SECURE`                 | `false`; must be true in production                            |
| `COOKIE_SAMESITE`               | `lax`                                                          |
| `COOKIE_DOMAIN`                 | Unset                                                          |
| `LOG_LEVEL`                     | `INFO`                                                         |
| `FRONTEND_URL`                  | `http://localhost:5173`                                        |
| `AUTH_RATE_LIMIT_PER_MINUTE`    | `10`                                                           |
| `AWS_TRUSTED_PRINCIPAL_ARN`     | CloudOps role principal used in generated trust guidance       |
| `AWS_ROLE_SESSION_NAME`         | `CloudOpsConnectionValidation`                                 |
| `AWS_DISCOVERY_REGIONS`         | `us-east-1,us-west-2,eu-west-1,ap-south-1`                     |
| `AWS_CONNECT_TIMEOUT_SECONDS`   | `5`                                                            |
| `AWS_READ_TIMEOUT_SECONDS`      | `30`                                                           |
| `AWS_MAX_RETRY_ATTEMPTS`        | `3`                                                            |
| `AWS_RETRY_MODE`                | `standard`; `adaptive` is also accepted                        |
| `AI_PROVIDER`                   | `mock`; deterministic no-network AI provider for local/test    |
| `NOTIFICATION_PROVIDER`         | `mock`; use `smtp` only for the local Mailpit demo             |
| `SMTP_HOST`                     | SMTP host for local Mailpit demo                               |
| `SMTP_PORT`                     | SMTP port for local Mailpit demo                               |
| `SMTP_USERNAME`                 | Optional SMTP username; keep empty for Mailpit                 |
| `SMTP_PASSWORD`                 | Optional SMTP password; keep empty for Mailpit                 |
| `SMTP_FROM_EMAIL`               | Sender address for SMTP demo messages                          |
| `SMTP_FROM_NAME`                | Sender display name for SMTP demo messages                     |
| `SMTP_USE_TLS`                  | `false` for local Mailpit                                      |

### Test-only variables

| Variable                     | Purpose                                      |
| ---------------------------- | -------------------------------------------- |
| `POSTGRES_TEST_DATABASE_URL` | Disposable database used by PostgreSQL tests |
| `AWS_EC2_METADATA_DISABLED`  | Set to `true` to prevent metadata lookups    |
| `AWS_ACCESS_KEY_ID`          | Dummy value only for mocked tests            |
| `AWS_SECRET_ACCESS_KEY`      | Dummy value only for mocked tests            |
| `AWS_SESSION_TOKEN`          | Dummy value only for mocked tests            |
| `AWS_DEFAULT_REGION`         | Test region such as `us-east-1`              |

### Frontend variable

| Variable            | Default or purpose                                  |
| ------------------- | --------------------------------------------------- |
| `VITE_API_BASE_URL` | Backend origin; defaults to `http://localhost:8000` |

Example disposable-test session:

```powershell
$env:DATABASE_URL="postgresql+psycopg://cloudops:cloudops_test_password@localhost:5433/cloudops_test"
$env:POSTGRES_TEST_DATABASE_URL=$env:DATABASE_URL
$env:JWT_SECRET_KEY="replace-with-a-test-secret-at-least-32-characters"
$env:APP_ENV="testing"
$env:AWS_EC2_METADATA_DISABLED="true"
$env:AWS_ACCESS_KEY_ID="test-only"
$env:AWS_SECRET_ACCESS_KEY="test-only"
$env:AWS_SESSION_TOKEN="test-only"
$env:AWS_DEFAULT_REGION="us-east-1"
```

These AWS values are deliberately fake. Never substitute production or customer credentials.

## Start PostgreSQL

The repository provides one Compose service, `postgres`, using `postgres:16-alpine`. It is a
**disposable verification database** backed by tmpfs:

- Host: `localhost`
- Host port: `5433`
- Container port: `5432`
- Database: `cloudops_test`
- User: `cloudops`
- Password: the test-only value in `compose.verify.yml`

```powershell
docker compose -f compose.verify.yml up -d
docker compose -f compose.verify.yml ps
docker compose -f compose.verify.yml logs postgres
```

Stop and remove only the disposable service:

```powershell
docker compose -f compose.verify.yml down
```

The repository does not currently provide a persistent development-database Compose file. For a
persistent local database, provision PostgreSQL separately and point `DATABASE_URL` at it.
Never run `down -v` or delete a development volume unless you intentionally accept data loss.
Use a fresh Compose project name, such as `-p cloudops-clean-verify`, when an isolated
clean-room database is required.

## Local Version 1 demo stack

The root `compose.demo.yml` starts a guarded local demo stack:

- PostgreSQL `cloudops_demo` on `localhost:5432`
- Mailpit SMTP on `localhost:1025`
- Mailpit inbox UI on <http://localhost:8025>
- API on <http://localhost:8000>
- Web UI on <http://localhost:5173>
- Manual scheduler tick via `docker compose -f compose.demo.yml --profile manual run --rm scheduler-worker`

The API container applies Alembic migrations before starting. Its default demo configuration uses
the deterministic mock AI provider, dummy AWS credentials with metadata lookup disabled, and the
Mailpit-only SMTP notification provider. It must not be pointed at production or customer AWS
resources.

```powershell
.\scripts\demo_start.ps1
.\scripts\demo_reset.ps1
```

The helper scripts validate Compose configuration, build and start the stack, check API/web/
Mailpit readiness, and run the deterministic seed inside the API container. The Docker demo does
not require a host Python virtual environment or host Node installation.

The seed command refuses production mode and refuses database names outside `cloudops_demo*`.
Generated demo output is deterministic and synthetic; no AWS discovery client is invoked by the
seed script. The seeded credentials include an owner (`owner@cloudops-demo.testmail.com`) and a security
analyst (`analyst@cloudops-demo.testmail.com`) plus a cloud engineer
(`engineer@cloudops-demo.testmail.com`) using the printed demo password. When
`--deliver-email` is used with Mailpit SMTP, the latest Mailpit message should show both the
owner and the analyst/evaluation actor as recipients.

For the full tomorrow-demo path, including invitation emails in Mailpit, browser profiles,
fallback data, remediation, scheduling, audit export, troubleshooting, and the speaker script,
see `demo_v1.md`.

Latest local demo verification on `feature/v1-demo-completion`:

- Docker: `compose.demo.yml config`, manual profile config, build, start, readiness check,
  restart rehearsal, cold start with demo volume reset, deterministic reseed, and manual
  scheduler tick all passed.
- Mailpit: security notification delivery and invitation-email delivery were verified through
  the Mailpit API.
- V1 acceptance: `tests/end-to-end/verify_v1_demo.py` completed 18 PASS, 0 FAIL.
- Backend: 522 tests passed, 0 failed, 0 skipped; coverage 96.44%; Ruff, Mypy (144 source
  files), startup/import, Alembic current/check, and `pip check` passed.
- Frontend: TypeScript, ESLint, 112 Vitest tests, and production build passed.
- Dependency audits: online `npm audit` was blocked by environment policy pending explicit
  npm-audit metadata-egress authorization; do not record it as passed.

## Backend setup

From the repository root:

```powershell
cd apps/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip check
```

Set `DATABASE_URL` and `JWT_SECRET_KEY`, then migrate and start FastAPI:

```powershell
alembic upgrade head
alembic current
alembic check
uvicorn app.main:app --reload
```

If activation is disabled, use the executables directly:

```powershell
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\uvicorn.exe app.main:app --reload
```

Local endpoints:

- API: <http://localhost:8000>
- Health: <http://localhost:8000/health>
- Database readiness: <http://localhost:8000/ready>
- Swagger UI: <http://localhost:8000/docs>
- OpenAPI document: <http://localhost:8000/openapi.json>

Stop Uvicorn with `Ctrl+C`.

## Frontend setup

In another PowerShell terminal:

```powershell
cd apps/web
npm ci
$env:VITE_API_BASE_URL="http://localhost:8000"
npm run dev
```

Open <http://localhost:5173>. The default backend origin is already
`http://localhost:8000`. If either port is occupied, stop the conflicting process or start Vite
with an explicit temporary port:

```powershell
npm run dev -- --port 5174
```

When changing the frontend origin, add the same origin to `CORS_ALLOWED_ORIGINS` before starting
the API.

Build and preview:

```powershell
npm run build
npx vite preview
```

The production build is written to ignored `apps/web/dist`.

## First-run workflow

1. Start PostgreSQL, migrate the API, and start the backend and frontend.
2. Open the frontend and register a synthetic local user.
3. Create or select an organization and sign in.
4. Invite synthetic teammates if role testing is needed.
5. Review the six-role permissions below.
6. Add an AWS account only through an approved test procedure.
7. For automated/local acceptance, seed normalized synthetic assets or use the repository’s AWS
   mocks; real AWS access is not required.
8. Run discovery through mocked or explicitly approved sandbox mechanisms.
9. Run the Stage 4 deterministic evaluation.
10. View findings and their lifecycle.
11. Run a Stage 5 compliance assessment.
12. Review frameworks, controls, mapped findings, and immutable historical assessments.
13. Configure bounded Stage 6 asset or account risk context.
14. Run a Stage 6 risk assessment and review its score, textual priority, component reasons,
    unknown-input indicators, aggregates, and deterministically ranked findings.
15. Where authorized, add a reasoned compensating control bounded from -15 through -1.
16. Run a new assessment and compare it with the unchanged historical snapshot.

Actual STS validation requires an approved sandbox role and trusted principal configuration.
Never use a production account or customer credentials for local testing.

## Roles and permissions

| Capability                  | Owner |                        Admin | Security Analyst | Cloud Engineer | Auditor | Viewer |
| --------------------------- | ----: | ---------------------------: | ---------------: | -------------: | ------: | -----: |
| Read organization           |   Yes |                          Yes |              Yes |            Yes |     Yes |    Yes |
| Manage organization/members |   Yes | Yes, except owner governance |               No |             No |      No |     No |
| Manage invitations          |   Yes |                          Yes |               No |             No |      No |     No |
| Read audit events           |   Yes |                          Yes |               No |             No |     Yes |     No |
| Manage AWS onboarding       |   Yes |                          Yes |               No |             No |      No |     No |
| Start discovery             |   Yes |                          Yes |              Yes |            Yes |      No |     No |
| View assets                 |   Yes |                          Yes |              Yes |            Yes |     Yes |    Yes |
| Run evaluations             |   Yes |                          Yes |              Yes |            Yes |      No |     No |
| View rules/findings         |   Yes |                          Yes |              Yes |            Yes |     Yes |    Yes |
| Suppress findings           |   Yes |                          Yes |              Yes |             No |      No |     No |
| View compliance             |   Yes |                          Yes |              Yes |            Yes |     Yes |    Yes |
| Run compliance assessments  |   Yes |                          Yes |              Yes |            Yes |      No |     No |
| View notifications          |   Yes |                          Yes |              Yes |            Yes |     Yes |    Yes |
| Approve/deliver notifications |  Yes |                          Yes |              Yes |             No |      No |     No |
| View remediation requests   |   Yes |                          Yes |              Yes |            Yes |     Yes |    Yes |
| Propose/cancel remediation  |   Yes |                          Yes |              Yes |            Yes |      No |     No |
| Approve/reject/execute remediation | Yes |                    Yes |              Yes |             No |      No |     No |
| View schedules/scan runs    |   Yes |                          Yes |              Yes |            Yes |     Yes |    Yes |
| Manage schedules/run-now    |   Yes |                          Yes |              Yes |            Yes |      No |     No |
| Query/export audit events   |   Yes |                          Yes |               No |             No |     Yes |     No |

Backend RBAC is authoritative; hidden frontend controls are not a security boundary. Active
membership and tenant scope are required for every organization-owned operation.

## Backend quality checks

Start the disposable PostgreSQL service and set the test variables shown earlier. Then run from
`apps/api`:

```powershell
.\.venv\Scripts\ruff.exe format --check app
.\.venv\Scripts\ruff.exe check --no-cache app
.\.venv\Scripts\mypy.exe --cache-dir "$env:TEMP\cloudops_mypy_cache" app
.\.venv\Scripts\python.exe -c "from app.main import app; print(app.title)"
.\.venv\Scripts\pytest.exe
.\.venv\Scripts\pytest.exe --cov=app --cov-report=term-missing
.\.venv\Scripts\pytest.exe app\tests\test_postgres_concurrency.py app\tests\test_stage5_postgres.py
.\.venv\Scripts\pytest.exe app\tests\test_zz_postgres_repair_migration.py app\tests\test_zzz_stage5_migration.py
.\.venv\Scripts\alembic.exe heads
.\.venv\Scripts\alembic.exe current
.\.venv\Scripts\alembic.exe check
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\pip-audit.exe
```

PostgreSQL tests reject unsafe database names and must use the disposable `cloudops_test`
database. A timeout without a final exit code is not a pass. A rejected command is not a pass.
The full suite must reach its final Pytest summary.

## Frontend quality checks

From `apps/web`:

```powershell
npm run format:check
npm run lint
npm run typecheck
npm run test
npm run build
npm audit --registry=https://registry.npmjs.org
```

## Verify everything

Run in this order:

```powershell
# Repository root: disposable PostgreSQL
docker compose -f compose.verify.yml up -d

# Backend
cd apps/api
$env:DATABASE_URL="postgresql+psycopg://cloudops:cloudops_test_password@localhost:5433/cloudops_test"
$env:POSTGRES_TEST_DATABASE_URL=$env:DATABASE_URL
$env:JWT_SECRET_KEY="replace-with-a-test-secret-at-least-32-characters"
$env:APP_ENV="testing"
$env:AWS_EC2_METADATA_DISABLED="true"
$env:AWS_ACCESS_KEY_ID="test-only"
$env:AWS_SECRET_ACCESS_KEY="test-only"
$env:AWS_SESSION_TOKEN="test-only"
$env:AWS_DEFAULT_REGION="us-east-1"
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\alembic.exe current
.\.venv\Scripts\alembic.exe check
.\.venv\Scripts\ruff.exe format --check app
.\.venv\Scripts\ruff.exe check --no-cache app
.\.venv\Scripts\mypy.exe --cache-dir "$env:TEMP\cloudops_mypy_cache" app
.\.venv\Scripts\pytest.exe --cov=app --cov-report=term-missing
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\pip-audit.exe

# Frontend
cd ..\web
npm run format:check
npm run lint
npm run typecheck
npm run test
npm run build
npm audit --registry=https://registry.npmjs.org

# Repository checks and cleanup
cd ..\..
git diff --check
git status --short --branch
docker compose -f compose.verify.yml down
```

## Common troubleshooting

### PowerShell blocks virtual-environment activation

Use direct executables under `.\.venv\Scripts\` instead of changing machine-wide execution
policy. If policy changes are permitted locally, scope them to the current process only.

### Python is missing or the wrong version

Run `python --version`. Install Python 3.12 or 3.13 and recreate `.venv`; do not reuse an
environment created by an unsupported interpreter.

### PostgreSQL connection is refused

Run `docker compose -f compose.verify.yml ps` and
`docker compose -f compose.verify.yml logs postgres`. Confirm port 5433 is available and the URL
uses `postgresql+psycopg`.

### The database already exists or port 5433 is occupied

Stop the specific conflicting container or use a separate approved PostgreSQL instance and
matching URL. Do not delete persistent development data as generic troubleshooting.

### Alembic revision mismatch or drift

Run:

```powershell
alembic heads
alembic current
alembic history
alembic check
```

There must be one head. On `main` that head is `0009_stage7_ai_assistant`. On
`feature/v1-demo-completion` the linear chain continues through `0010_stage9_notifications`,
`0011_stage10_remediation`, `0012_stage11_scheduler`, and
`0013_demo_notification_delivery` (current head on this demo-readiness worktree). Stage 12 adds
no migration. Never edit a reviewed migration merely to make a stale local database agree;
recreate only a disposable database.

### A port is already in use

Stop the known local process or choose an explicit temporary Vite/Uvicorn port. Update
`VITE_API_BASE_URL`, `CORS_ALLOWED_ORIGINS`, and `FRONTEND_URL` consistently.

### The frontend cannot reach the API or reports CORS errors

Confirm the API health endpoint, `VITE_API_BASE_URL`, and the exact browser origin in
`CORS_ALLOWED_ORIGINS`. Restart both processes after changing environment variables.

### npm reports an engine warning

Use Node 20 LTS or 22 LTS. Do not rely on Node 23 experimental type-stripping behavior.

### Vite reports a temporary-file permission error

Stop other Vite/Node processes that hold the file, verify the repository is writable, remove
only ignored build output if necessary, and retry. Do not delete source files.

### Mypy behaves inconsistently or reports an internal cache error

Use a fresh temporary cache:

```powershell
.\.venv\Scripts\mypy.exe --cache-dir "$env:TEMP\cloudops_mypy_fresh" app
```

### Starlette TestClient/httpx deprecation warning

This known warning is non-blocking only when Pytest exits successfully. Do not suppress test
failures alongside it.

### Docker reports an unhealthy database

Inspect `docker compose -f compose.verify.yml ps` and `logs postgres`. Wait for the configured
health check; do not infer readiness from container creation alone.

### A test times out

Treat the result as incomplete. Rerun with a sufficient uninterrupted timeout and capture the
final process exit code and summary.

### AWS metadata lookup is slow

Set `AWS_EC2_METADATA_DISABLED=true` for mocked tests.

### Real AWS credentials may be active

Stop immediately, clear the credential environment variables/session, and use explicit dummy
values with deterministic mocks. Never print, commit, or test with the real values.

## Safe cleanup

Review exact paths before removal. These commands target ignored generated outputs only:

```powershell
Remove-Item -LiteralPath apps\api\.coverage -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath apps\api\.mypy_cache -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath apps\api\.ruff_cache -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem apps\api -Directory -Recurse -Filter __pycache__ |
  Remove-Item -Recurse -Force
Remove-Item -LiteralPath apps\web\dist -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath apps\web\coverage -Recurse -Force -ErrorAction SilentlyContinue
docker compose -f compose.verify.yml down
```

Do not use `git clean -fd` or `git reset --hard`. Do not delete source, migrations, uncommitted
changes, local virtual environments you still need, or persistent development database volumes.

## Development workflow

1. Fast-forward local `main` from `origin/main`.
2. Create one branch per stage or focused task.
3. Keep stages sequential and preserve the previous verified baseline.
4. Add tests with the implementation.
5. Run focused checks first, then complete regression and security gates.
6. Review every changed file and exclude secrets/generated output.
7. Commit intentionally and push normally.
8. Open a draft pull request.
9. Verify the exact pushed SHA in a detached clean-room worktree.
10. Merge only after required review or an explicitly recorded owner governance decision.
11. Never describe an owner exception as independent approval.
12. Never begin the next stage before integration and documentation gates pass.

`main` is the authoritative integrated baseline. Before release actions, fetch remote state and
compare the local branch SHA, its upstream SHA, and `origin/main`. Active feature branches must
start from current `main`, and an open pull-request branch may differ from `main` only by that
pull request's intended changes.

After a feature is merged and its tip is proven reachable from `main`, treat the old feature
branch as historical. Delete it through normal reviewed cleanup instead of repeatedly merging
`main` into it. Preserve any branch with unique unmerged commits until those commits are
investigated and intentionally integrated or retired. Never start a new stage from an old
feature branch.

Never force push, rewrite shared history, blindly delete a branch, or use destructive reset as
branch synchronization.

## Project Source-of-Truth and AI Handoff Files

Maintain these files together before starting or continuing AI-assisted development:

- `PRD.md` — product purpose, users, delivered scope, exclusions, and success criteria
- `architecture.md` — application flow, stack, components, repository/database organization,
  trust boundaries, and service communication
- `design.md` — implemented visual direction, typography, spacing, reusable patterns,
  responsiveness, and accessibility
- `rules.md` — approved stack, security, error handling, testing, Git/AWS safety, stage
  boundaries, and AI restrictions
- `phases.md` — completed, blocked, current, and future stages with acceptance gates
- `memory.md` — completed work, current repository state, decisions, warnings, last verified
  results, and immediate next task
- `NEW_CHAT_CONTEXT.md` — portable project identity, architecture/status summary, SHAs, migration
  head, safety boundaries, known issues, and handoff instructions

`memory.md` is an active working record and must be updated after every substantial coding
session.

`NEW_CHAT_CONTEXT.md` should be updated after major architectural, stage, release, or governance
changes.

The architecture or mind map explains how the repository is organized; `memory.md` explains
where the work stopped.

## Start a new AI-assisted development chat

Upload these seven files together:

1. `NEW_CHAT_CONTEXT.md`
2. `PRD.md`
3. `architecture.md`
4. `design.md`
5. `rules.md`
6. `phases.md`
7. `memory.md`

Use this exact starter instruction:

```text
Read the attached project files and treat them as the source of truth.

First, summarize your understanding of:

- the project goal
- the architecture
- the current implementation state
- known issues
- the next task

Do not modify code yet. Identify contradictions or missing information before proceeding.
```

Operating rules:

- Do not trust one document in isolation; compare all seven for contradictions.
- Use `architecture.md` for repository and system organization.
- Use `memory.md` for the last completed work and current stop point.
- Use `phases.md` to enforce stage order.
- Use `rules.md` for implementation and safety boundaries.
- Use `PRD.md` to prevent scope drift.
- Update `memory.md` after every substantial coding session.
- Update `NEW_CHAT_CONTEXT.md` after architectural, stage, merge, or governance changes.

## Known limitations

- The initial compliance catalog contains four controls and twelve mappings.
- It is not complete framework coverage or compliance certification.
- Mappings require human compliance review.
- Compliance export is not implemented.
- GitHub reported no automated check rollup for PR #4.
- The Starlette TestClient/httpx deprecation warning remains.
- Node 20 LTS or Node 22 LTS is recommended.
- Stage 6 uses an initial CloudOps-specific, CVSS-inspired policy; it is not CVSS and does not
  predict exploitation or replace human security review.
- Business-impact accuracy depends on explicit context quality. Unknown context is recorded and
  handled conservatively.
- Compensating controls require human authorization and are bounded from -15 through -1.
- Stage 7 AI explanation is implemented as advisory drafting only; Jira/email outputs remain
  drafts and no delivery or ticket creation is implemented.
- Live AWS validation is controlled sandbox work, not a requirement for automated tests.
- Stage 9 notification delivery uses the deterministic mock/no-op provider by default. The local
  Version 1 demo may use Mailpit-backed SMTP after explicit human approval; production SMTP,
  Slack, Teams, webhook, or AWS SES delivery remains unimplemented and requires separate
  authorization.
- Stage 10 remediation execution uses a deterministic mock executor only; no real AWS mutation
  is performed. Protected transitions (approve, reject, execute) require explicit human
  authorization. Rule evaluation remains the sole authority on whether a finding exists; AI may
  explain a remediation but never decides one is needed.
- Stage 11's scheduler worker is a deterministic, synchronously invokable foundation, not a
  Celery/Redis/distributed-queue or permanent cron daemon; that infrastructure choice remains
  unapproved future work. It delegates every run to the existing discovery and evaluation
  orchestration and performs no independent boto3 or rule-evaluation logic.
- Stage 12 (audit query/export) reuses the existing `AuditEvent` persistence and
  `record_audit()` write path; it adds a read/query/export layer only and requires no migration.
  It is committed on `feature/v1-demo-completion` at `d0d24cd` and `9314f06`.
- `compose.verify.yml` provides only a disposable PostgreSQL verification database. The local
  demo stack lives in `compose.demo.yml` and is intentionally separate from production deployment
  or infrastructure-as-code.

## Safety summary

- Never commit secrets or `.env`.
- Never use production/customer AWS accounts or credentials for tests.
- Never persist STS credentials.
- Never bypass backend tenant/RBAC checks.
- Never treat missing compliance evidence as `PASS`.
- Never use AI to detect findings or determine risk scores.
- Never allow notification delivery to bypass explicit human approval.
- Never allow remediation execution to bypass explicit human approval; execution is mock/
  simulated only and never mutates real AWS resources.
- Stages 9-12 (notifications, remediation, scheduler, audit query/export) are complete and committed on
  `feature/v1-demo-completion`; merge into `main` remains outstanding.

## Stage 7 — AI explanation assistant

Stage 7 adds a bounded, tenant-scoped drafting assistant over persisted CloudOps
evidence. It can explain findings and business impact, suggest remediation text,
and draft executive summaries, Jira descriptions, and email summaries. Every
result is structured, source-referenced, versioned, redacted, labeled as a
draft, and requires human review.

The default `mock` provider is deterministic and makes no network calls.
Provider credentials are never persisted. Evidence is treated as untrusted
quoted data; prompt-like instructions inside evidence are neutralized. The
assistant cannot detect or create findings, calculate or change risk, alter
severity or compliance, execute remediation, create tickets, or send messages.

Migration head on `main`: `0009_stage7_ai_assistant`. Stage 8 (dashboard read model and UI) is
merged. Stage 9
is not complete.

Stage 7 idempotency is scoped to `(organization_id, idempotency_key)`. A replay
with the same canonical task, typed persisted source, source lifecycle/hash,
bounded options, prompt version, and response-schema version returns the
original terminal result without another provider call or quota charge. Reuse
with a different fingerprint returns `409 AI_IDEMPOTENCY_CONFLICT`. Failed
terminal results are replayed; callers must use a new key for an intentional
retry. Organization quotas use fixed UTC hourly windows, transactional locks,
and `429 AI_RATE_LIMITED`; an accepted provider attempt is charged once even
when the provider returns a safe terminal failure.

The provider-neutral contract distinguishes disabled, timeout, retryable,
permanent-failure, and invalid-response states. Only retryable failures receive
one bounded retry. Context is Unicode-normalized, control characters are
neutralized, secrets and credential-bearing URLs are redacted, and evidence is
structurally labeled as untrusted data. These controls reduce prompt-injection
risk; they do not claim absolute prevention. Every output string and collection
is schema-bounded before persistence.

## Stage 8 — dashboard

Stage 8A introduced the read-only `GET /api/v1/dashboard/summary` contract for organization
security posture. The endpoint visualizes existing Stage 2-7 authoritative records and does not
discover assets, evaluate rules, calculate compliance, calculate risk, invoke AI, call AWS, send
notifications, execute remediation, create Jira issues, or persist dashboard-owned snapshots.

The response is bounded and tenant-scoped. It includes metadata, AWS account posture, asset
inventory distributions, finding posture, latest completed compliance posture, latest completed
risk posture, account-risk heatmap data, immutable risk trend points, and operational freshness
timestamps. Empty and partial organizations return explicit missing-section metadata rather than
fabricated scores or percentages. Region/type/service/account distributions and recent finding
lists use deterministic sorting and documented caps.

Stage 8B delivered the dashboard UI (`SecurityDashboardPage`), KPI cards, and
organization-switch cache behavior over the Stage 8A contract. Both merged into `main` at
`889660ecb8a378d107f6737b4466b70362066793`.

## Stage 9 — notifications

Stage 9 introduces an organization-scoped notification event pipeline for newly created critical
findings. `NotificationEvent` records move through `PENDING_APPROVAL -> APPROVED -> DELIVERED`
or, after three failed delivery attempts, `APPROVED -> FAILED`; there is no `REJECTED` state.
Creation is triggered only by a newly created `CRITICAL` finding and is defensively re-checked
inside `NotificationService.create_for_critical_finding` regardless of the caller. No delivery
occurs without an explicit `POST /api/v1/notifications/{id}/approve` by a user holding the
`NOTIFICATIONS_APPROVE` capability. The deterministic mock/no-op provider remains the default
for tests and ordinary local development. A Mailpit-backed SMTP provider exists only for the
guarded local Version 1 demo path; it writes provider evidence without exposing raw SMTP
exceptions. AWS SES, SendGrid, Gmail, Microsoft Graph, Slack, Teams, webhook, and production
SMTP delivery remain unimplemented. The workflow is: finding/risk event -> pending-approval
notification -> authorized human approval -> provider delivery -> delivered or failed state.
Rules detect; risk scoring prioritizes; AI may draft explanatory wording but never authorizes
delivery or sends anything; humans approve; a provider delivers. The frontend notification
history/approval page
(`NotificationsPage`, filtering, pagination, role-gated approve/deliver controls, and tests) is
implemented. Backend and frontend are both committed on `feature/v1-demo-completion`; migration
`0010_stage9_notifications`.

## Stage 10 — remediation workflow

Stage 10 adds a governed, approval-gated remediation lifecycle for a finding:
`PENDING_APPROVAL -> APPROVED -> SUCCEEDED`, `APPROVED -> FAILED` after three failed mock
execution attempts, or `PENDING_APPROVAL`/`APPROVED -> REJECTED`/`CANCELLED`. Proposal text is
generated deterministically from the matching `SecurityRule` in the existing rule registry; no
new detection logic is introduced. Execution uses a deterministic `MockRemediationExecutor` only
and never mutates real AWS resources — `execution_mode` other than `mock_automation` cannot be
executed in Version 1. Every protected transition (approve, reject, cancel, execute) requires a
capability-gated authenticated actor and is tenant-isolated via a composite foreign key to the
owning finding/account/organization. The frontend exposes a "Propose remediation" action from a
finding's detail page and a dedicated remediation list/detail page with role-gated
approve/reject/cancel/execute controls. Backend and frontend are both committed on
`feature/v1-demo-completion`; migration `0011_stage10_remediation`.

## Stage 11 — scheduler

Stage 11 adds a scheduling foundation: `ScanSchedule` records an interval-based cadence for an
AWS account, and `ScanRun` records one execution (manual or scheduled). Running a schedule always
delegates to the existing `DiscoveryOrchestrator` and `EvaluationService` — it introduces no new
boto3 or rule-evaluation logic. A partial unique index enforces overlap protection: only one
pending/running scan may exist per AWS account at a time. The worker
(`app/worker/scheduler_worker.py`) is a deterministic, synchronously invokable "tick" foundation,
not a Celery/Redis/distributed-queue or permanent cron daemon; that infrastructure choice is
explicitly deferred (see `apps/worker/README.md`). The frontend `SchedulesPage` supports
enable/disable, run-now, and a recent scan-run history view, role-gated to match backend RBAC.
Backend and frontend are both committed on `feature/v1-demo-completion`; migration
`0012_stage11_scheduler` is the Stage 11 migration. The current demo-readiness worktree head is
`0013_demo_notification_delivery`.

## Stage 12 — audit query/export

Stage 12 adds a read/query/export layer over the existing `AuditEvent` persistence and
`record_audit()` write path from earlier stages; **it requires no migration**. It adds
`GET /api/v1/audit-events` (filters: event type, resource type, resource ID, actor user ID,
result, start/end time; paginated) and `GET /api/v1/audit-events/export` (same filters, CSV,
capped at 5,000 rows, kept synchronous rather than a background job). Both reuse the existing
`AUDIT_READ` capability (owner, admin, auditor). The frontend `AuditPage` provides filter
controls, pagination, and a CSV export button using a new `apiBlob()` helper that reuses the
existing authenticated request/refresh flow.

**Stage 12 is implemented and committed on `feature/v1-demo-completion` at `d0d24cd` and
`9314f06`.** Its most recent verification:

- Backend: Ruff passed; Mypy passed (142 source files); `test_audit_api.py` 8 passed; one
  non-blocking Starlette/httpx deprecation warning
- Frontend: TypeScript passed; ESLint passed; Vitest (`audit.test.tsx`) 4 passed; production
  build passed

The demo-readiness follow-up adds Mailpit-backed SMTP delivery for the local demo, development-
only Mailpit invitation emails, a guarded Compose demo stack, deterministic Docker-only
seed/reset helper scripts, `demo_v1.md`, and an 18-step V1 acceptance runner. See
`tests/end-to-end/README.md` for the automated command and `demo_v1.md` for the human demo
runbook.
