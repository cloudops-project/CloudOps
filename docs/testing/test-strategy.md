# Test strategy

CloudOps uses layered tests. A test is reported as passed only when its command or retained CI
result proves it. Local environment limitations are not converted into passes.

| Layer | Purpose | Typical environment |
|---|---|---|
| Unit | Pure rules, risk formulas, schemas, sanitizers, provider adapters, state machines | Python/Vitest; AWS fakes or Stubber |
| API/service | RBAC, tenant scoping, lifecycle, idempotency, error contracts | FastAPI test client and test database |
| PostgreSQL integration | Foreign keys, checks, triggers, migrations, concurrency, row locks | Disposable PostgreSQL only |
| Worker/concurrency | Leasing, heartbeat, stale-worker rejection, retry, dead-letter, scheduler claiming | PostgreSQL plus bounded workers |
| Frontend | Components, protected routes, role navigation, workflows, accessibility basics | Vitest/Testing Library |
| Container | Non-root runtime, health/readiness, Compose topology, migration service, smoke | Docker |
| Terraform/static security | Formatting, validation, Terraform tests, IAM/resource assertions, Checkov | Offline/no apply |
| Operational | Workload identity, providers, restore, canary, rollback, UAT | Explicitly authorized staging |

## Backend gates

From `apps/api`, use the repository virtual environment and configuration: Ruff, strict Mypy, full
Pytest, focused PostgreSQL/tenant/concurrency/worker/remediation/provider tests, `pip check`, and
dependency audit. Live AWS tests remain opt-in and disabled in normal CI.

## Frontend gates

From `apps/web`: clean lockfile installation, lint, typecheck, all tests, production build, and
dependency audit.

## Migration gates

CI verifies one head, clean upgrade, upgrade to head, `current`, `check`, and migration preflight on
PostgreSQL. Current head: `0019_live_remediation_data_model`.

## Evidence language

- **Unit tested / Integration tested:** a matching automated test exists and passed in the cited run.
- **CI verified:** a GitHub Actions job passed for the cited commit.
- **Operationally tested:** retained evidence from the authorized external environment exists.
- **Deployed:** the named environment was actually applied and verified.
