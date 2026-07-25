# CloudOps

CloudOps is an AWS-focused, multi-tenant SaaS application for identity and organization
administration, secure cross-account AWS onboarding, read-only asset discovery, deterministic
security findings, and evidence-based compliance assessments. It is intended for organization
owners, administrators, security analysts, cloud engineers, auditors, and viewers.

Stages 1-8 are implemented, independently clean-room verified, merged, and regression-tested.
Stage 9 (notifications) has a complete backend on `feature/9-notifications`
(persistence, service, and API layer); its frontend and merge into `main` remain outstanding.
Stage 4 deterministic rules detect findings from persisted inventory; Stage 5 interprets that deterministic evidence for
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
| Stage 9 backend (unmerged, `feature/9-notifications`) | `d0b5676`, `449e964`, `cb42db9` |
| Migration head (`main`) | `0009_stage7_ai_assistant`                                                |
| Migration head (`feature/9-notifications`) | `0010_stage9_notifications`                            |
| Backend/frontend/black-box/coverage counts | Not re-verified since Stage 7; re-run the full quality-gate sequence below before citing fresh numbers |
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

There must be one head: `0009_stage7_ai_assistant`. Never edit a reviewed migration merely
to make a stale local database agree; recreate only a disposable database.

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
- Stage 9 notification delivery uses a deterministic mock/no-op provider only; no real email,
  Slack, Teams, or webhook delivery is implemented. Delivery requires explicit human approval.

## Safety summary

- Never commit secrets or `.env`.
- Never use production/customer AWS accounts or credentials for tests.
- Never persist STS credentials.
- Never bypass backend tenant/RBAC checks.
- Never treat missing compliance evidence as `PASS`.
- Never use AI to detect findings or determine risk scores.
- Never allow notification delivery to bypass explicit human approval.
- Stage 9 backend (persistence, service, API) is complete on `feature/9-notifications`; its
  frontend and merge into `main` remain outstanding.

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
`NOTIFICATIONS_APPROVE` capability. The only delivery provider implemented is a deterministic
mock/no-op provider; no real email, Slack, Teams, or webhook delivery exists. Migration head on
`feature/9-notifications`: `0010_stage9_notifications`. The frontend notification history/
approval page is not yet implemented.
