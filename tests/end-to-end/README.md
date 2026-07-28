# End-to-End Verification

## Stage 7 black-box release gate

The Stage 7 gate runs one synthetic Stage 1–7 workflow through PostgreSQL-backed
FastAPI routes and rendered React behavior. It uses the deterministic mock AI
provider, test-only AWS credentials, and synthetic inventory; it must never call
real AWS or an external AI provider.

Start a disposable PostgreSQL database whose name is `cloudops_test` or begins
with `cloudops_e2e_`, then set:

```powershell
$env:APP_ENV = "testing"
# Inject DATABASE_URL and POSTGRES_TEST_DATABASE_URL with the same disposable test-database endpoint.
$env:JWT_SECRET_KEY = "replace-with-a-test-only-secret-at-least-32-characters"
$env:AWS_ACCESS_KEY_ID = "testing"
$env:AWS_SECRET_ACCESS_KEY = "testing"
$env:AWS_SESSION_TOKEN = "testing"
$env:AWS_EC2_METADATA_DISABLED = "true"
$env:AWS_DEFAULT_REGION = "us-east-1"
$env:AI_PROVIDER = "mock"
```

From the repository root, run:

```powershell
.\apps\api\.venv\Scripts\python.exe tests\end-to-end\verify_stage7_black_box.py
```

The command upgrades the disposable database, executes all 44 ordered steps,
rejects missing, duplicate, failed, or misdescribed steps, and exits nonzero
unless every step passes. It writes `stage7-black-box.json` and
`stage7-black-box.md` under `%TEMP%\cloudops-stage7-black-box` by default. Set
`STAGE7_BLACK_BOX_OUTPUT_DIR` to another temporary path when verification
evidence needs an isolated location.

Delete the disposable database, reports, coverage output, and frontend `dist`
directory after verification. Do not commit generated evidence.

## Version 1 demo acceptance gate

The V1 demo gate runs one ordered synthetic Stage 1-12 workflow through the FastAPI public
routes where available. It uses PostgreSQL, deterministic synthetic inventory, the mock AI
provider, and the configured notification provider. It must not use production data, real AWS
credentials, a live external AI provider, Jira, or real remediation execution.

Start a disposable PostgreSQL database whose name is `cloudops_test` or begins with
`cloudops_e2e_`, then set:

```powershell
$env:APP_ENV = "testing"
# Inject DATABASE_URL and POSTGRES_TEST_DATABASE_URL with the same disposable test-database endpoint.
$env:JWT_SECRET_KEY = "replace-with-a-test-only-secret-at-least-32-characters"
$env:AWS_ACCESS_KEY_ID = "testing"
$env:AWS_SECRET_ACCESS_KEY = "testing"
$env:AWS_SESSION_TOKEN = "testing"
$env:AWS_EC2_METADATA_DISABLED = "true"
$env:AWS_DEFAULT_REGION = "us-east-1"
$env:AI_PROVIDER = "mock"
```

From the repository root, run:

```powershell
.\apps\api\.venv\Scripts\python.exe tests\end-to-end\verify_v1_demo.py
```

The command upgrades the disposable database, executes all 18 ordered demo steps, verifies that
the invited analyst can drive the deterministic assessment flow, verifies owner-plus-actor
notification recipients through the configured provider, rejects missing, duplicate, failed, or
misdescribed steps, and exits nonzero unless every step passes.
It writes `v1-demo-black-box.json` and `v1-demo-black-box.md` under
`%TEMP%\cloudops-v1-demo` by default. Set `V1_DEMO_OUTPUT_DIR` to another temporary path when
verification evidence needs an isolated location. Do not commit generated evidence.

For the human-operated tomorrow-demo runbook, Docker-only startup/reset helpers, Mailpit
invitation-email path, fallback-data route, remediation/scheduling/audit presentation script,
and troubleshooting guide, see the repository-root `demo_v1.md`.
