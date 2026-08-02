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

## Stage 5 compliance

Migration `0007_stage5_compliance_engine` adds versioned frameworks and controls,
rule-version-range mappings, evaluation rule summaries, compliance assessments, and immutable
control snapshots. Per-rule counts represent deterministic rule invocations over applicable
assets (or one invocation for an account-level rule). A zero-count summary means the rule had
no applicable invocation and cannot establish compliance `PASS`.

Compliance uses persisted Stage 4 evidence only. Missing/legacy summaries and version mismatches
are `NOT_ASSESSED`; mapped rule errors are `ERROR`; active and suppressed mapped findings are
`FAIL`. PostgreSQL composite foreign keys enforce tenant and framework consistency, while
partial unique indexes coordinate active assessments and open-ended mappings.

Exact duplicate mapping ranges are forbidden. Overlapping non-identical ranges are allowed only
as declarative catalog data and use union semantics: a rule version is applicable when it
matches any range, and duplicate matches cannot improve a control result. There is no mutable
mapping-administration API in Stage 5.

## Stage 6 deterministic risk

Migration `0008_stage6_risk_scoring` adds the versioned
`CLOUDOPS_RISK_V1` policy, bounded tenant risk context, risk assessment jobs, immutable finding,
account, and organization snapshots, and authorized compensating controls. The engine reads
persisted Stage 4 findings only; it performs no discovery, live AWS calls, or AI work.

## Stage 7 AI explanation assistant

Migration `0009_stage7_ai_assistant` introduced the AI request schema. The current repository head is `0019_live_remediation_data_model`. It adds
versioned prompt templates, tenant-scoped idempotent requests, immutable source
references and structured responses, and organization-hour usage windows. The
default mock provider is deterministic and offline. AI consumes bounded
persisted evidence only and cannot detect findings, score risk, mutate status,
execute remediation, or deliver Jira/email drafts.

## Stage 8A dashboard summary API

Stage 8A adds `GET /api/v1/dashboard/summary` as a read-only, organization-scoped dashboard
contract. It derives posture from existing AWS account, asset, finding, compliance, risk, and
AI-era records without creating dashboard snapshot tables. Later stages advance the repository
Alembic head to `0019_live_remediation_data_model`.

The response includes metadata, account posture, asset type/region distributions, finding
status/severity/service/account summaries, recent critical/high findings without raw evidence,
latest completed compliance posture, latest completed risk posture, account-risk heatmap data,
bounded risk trend points, and operational freshness timestamps. Empty and partial states return
explicit `missing_sections`; zero-denominator compliance percentages are `null`.

All active tenant roles may read the summary through the normal organization membership gate.
The endpoint does not invoke AWS, AI providers, notification transports, Jira integrations, or
remediation code, and it does not recalculate findings, compliance, or risk. Later migrations
advance the repository head to `0019_live_remediation_data_model`.

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
scope and RBAC. Revisions `0005_stage4_rule_engine` and
`0006_stage4_verification_repairs` add and harden evaluation jobs and findings. Stage 5
compliance consumes that persisted evidence. Later sections describe the implemented risk, AI,
notification, job, and dry-run remediation boundaries.

## Stage 6 deterministic risk scoring

Migration `0008_stage6_risk_scoring` adds versioned scoring policies, tenant-scoped risk context,
risk assessment jobs, immutable finding/account/organization snapshots, and bounded
compensating controls. The engine evaluates persisted Stage 4 findings only and performs no AWS
or other network calls.

API routes under `/api/v1/risk` provide policy listing, assessment start/history/detail,
organization summary, risk-ranked finding listing/detail, account and asset summaries, context
read/update, and compensating-control add/remove. All list inputs are bounded and stable, every
query is tenant-scoped, and cross-tenant identifiers are non-disclosing. Owners, admins,
security analysts, and cloud engineers may assess; all active roles may view; only owners,
admins, and security analysts may change context or compensating controls.
