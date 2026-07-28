# CloudOps Project Memory

> **Archived session history:** current operational memory is [../../memory.md](../../memory.md).
> All branch, migration, verification, completion, and next-task statements below are historical
> snapshots and are not current handoff evidence.

## Last updated

2026-07-26 - Stages 9-12 are implemented and committed on `feature/v1-demo-completion`, not yet
merged into `main`. The current demo-readiness work adds guarded Mailpit SMTP notification
delivery, development-only Mailpit invitation emails, migration `0013_demo_notification_delivery`,
a local PostgreSQL/Mailpit/API/web Compose stack, Docker-only helper scripts, deterministic demo
seed/reset, the root `demo_v1.md` runbook, and an 18-step V1 demo acceptance runner.

Current demo-readiness verification: Docker demo config/build/start/readiness/restart/cold-start/
reset passed; manual scheduler tick passed; Mailpit security notification and invitation email
delivery were verified; V1 acceptance completed 18 PASS, 0 FAIL; backend completed 522 passed,
0 failed, 0 skipped with 96.44% coverage; Mypy checked 144 source files; frontend TypeScript,
ESLint, 112 Vitest tests, and production build passed. Dependency audits passed after explicit
metadata-egress authorization: Python `pip-audit` checked 80 installed non-editable
distributions with 0 known vulnerabilities, and frontend `npm audit
--registry=https://registry.npmjs.org --json` checked 381 dependencies with 0 vulnerabilities
after the reviewed development-only ESLint upgrade to 10.8.0.

## Current implementation

Stages 1-8 are independently clean-room verified, merged, and regression-tested in `main` at
`889660ecb8a378d107f6737b4466b70362066793`. PR #8 merged verified Stage 7 feature SHA
`9b5f4372359a32066787060ca839d5a68c5ab490` at commit `882ff531af07276c11e0d25664fdca033e09c7c7`;
Stage 8 merged via PR #10 plus a follow-up `feature/8-dashboard-ui` merge. The current migration
head on `main` is `0009_stage7_ai_assistant`.

Stages 9-11 are complete (backend and frontend) and committed on `feature/v1-demo-completion`:
Stage 9 at commits `d0b5676`, `449e964`, `cb42db9`, `d1c8733` (migration head
`0010_stage9_notifications`); Stage 10 at commits `bf29173`, `fc8908d`, `8ab8c83`, `d1c8733`,
`8916be9` (migration head `0011_stage10_remediation`); Stage 11 at commits `24227ab`, `9fff532`,
`8c14b55`, `55c451e` (migration head `0012_stage11_scheduler`). Stage 12 is complete at
`d0d24cd` and `9314f06` across 10 files. None of Stages 9-12 are yet merged into `main`.

The active feature branch is `feature/v1-demo-completion`, created from `feature/9-notifications`
(merge-base with `main`: `889660ecb8a378d107f6737b4466b70362066793`).

### Verification commands and exact results run this effort

Stage 11 backend: `python -m ruff check app` passed; `python -m mypy app` passed (140 source
files); `python -m pytest app/tests/test_scheduler_service.py app/tests/test_scheduler_api.py`
22 passed, 0 failed; one non-blocking Starlette/httpx deprecation warning.

Stage 11 migrations (disposable PostgreSQL verification database, `compose.verify.yml`,
database `cloudops_test`, user `cloudops`, host port `5433`): `alembic upgrade head` passed
through `0010_stage9_notifications -> 0011_stage10_remediation -> 0012_stage11_scheduler`;
`alembic current` reports `0012_stage11_scheduler`; `alembic check` reports no new operations;
chain confirmed linear with a single head.

Stage 11 frontend: `npx tsc --noEmit` passed; `npx eslint ...` passed; scheduler Vitest 5
passed; `npm run build` passed.

Stage 12 backend: Ruff passed; Mypy passed (142 source files); `pytest
app/tests/test_audit_api.py` 8 passed; one non-blocking Starlette/httpx deprecation warning.

Stage 12 frontend: TypeScript passed; ESLint passed after the unused-input repair; Vitest
(`audit.test.tsx`) 4 passed; production build passed.

### Codex handoff state

Development ownership has moved to Codex. Stage 12 is committed; Codex's current demo-readiness
work implements Mailpit-backed local SMTP delivery while preserving the mock provider as the
default, builds the local demo stack, adds development-only Mailpit invitation emails, and adds
deterministic Docker-only demo seed/reset plus black-box acceptance. `CLAUDE.md` must remain
untracked; do not amend or repeat any commit listed above.

Alembic revision `0009_stage7_ai_assistant` follows `0008_stage6_risk_scoring` and adds
versioned prompt templates, tenant-scoped AI requests, typed source references, immutable
structured responses, and usage windows. Alembic revision `0008_stage6_risk_scoring` follows
`0007_stage5_compliance_engine` and adds
versioned scoring policies, bounded risk context, assessment jobs, immutable finding/account/
organization snapshots, and authorized compensating controls. Revision `0007_stage5_compliance_engine` follows
`0006_stage4_verification_repairs` and adds versioned frameworks and controls, rule mappings,
per-rule evaluation summaries, assessments, and immutable control snapshots.
Revision `0004_verification_repairs` adds immutable
external-ID reservation history, AWS-account lifecycle coordination fields, database-enforced
account/organization consistency for assets and jobs, asset timestamp checks, nonnegative job
counts, and job status/timestamp invariants. Existing account IDs and external IDs are
backfilled without change.

## Verification repairs

- External IDs remain globally reserved after account deletion and collision handling relies on
  a PostgreSQL unique constraint.
- Account lifecycle mutations use tenant-scoped locks. Validation uses an operation token so an
  older STS result cannot overwrite a newer mutation.
- Discovery uses composite tenant foreign keys, lifecycle checks, deterministic lock ordering,
  and terminal-state guards.
- Every boto3 client receives explicit environment-driven timeouts and bounded retry policy.
- Backend tests now cover all IAM pagination, invalid account states, authenticated discovery
  APIs, filters, stable pagination, details, RBAC, tenant isolation, and PostgreSQL races.
- Frontend discovery requires an accessible confirmation and covers filters, pagination,
  states, RBAC, focus behavior, and escaped metadata.

Current release evidence is 343 backend tests passed with 0 failures and 0 skips, 96% reported
coverage, Mypy over 111 source files, 81 frontend tests passed with 0 failures and 0 skips, and
the Stage 7 black-box workflow at 44 PASS, 0 FAIL, 0 missing, and 0 duplicate. Migration
lifecycle, PostgreSQL integrity/concurrency, dependency audits, security scans, and merged-main
regression verification passed.

## Decisions

- ADR-007 through ADR-010 remain the Stage 1 decisions.
- ADR-011 supersedes only the reserved Stage 2 numbering and establishes AWS account onboarding as Stage 2.
- `AWS_TRUSTED_PRINCIPAL_ARN` is deployment configuration. Customers manually create `CloudOpsReadOnlyRole` and attach AWS managed `SecurityAudit` during this stage.

## Known limitations

Stage 2 validation remains synchronous and does not deliver CloudFormation/Terraform onboarding
templates, external-ID rotation, background validation, or IAM resource creation. Stage 3
discovery remains synchronous and uses an explicit configured region list. Automated provider
tests use deterministic AWS doubles; controlled live-AWS validation remains operational work.

## Next task

Stage 12 is now committed and verified on `feature/v1-demo-completion`. Continue Version 1 demo
completion by finishing verification of Mailpit-backed local SMTP notification and invitation
delivery, the local DevOps/demo stack, deterministic demo seed/reset, the black-box V1
acceptance flow, `demo_v1.md`, full regression testing, deployment preparation, final documentation, and eventually a pull request
merging `feature/v1-demo-completion` into `main`. Notification delivery remains approval-gated;
the mock provider remains default/no-network and Mailpit SMTP is local-demo-only. Remediation
execution remains mock-only, and the scheduler must keep delegating to existing discovery/
evaluation services rather than duplicating their logic.

## Stage 3 implementation snapshot

Alembic `0003_stage3` adds `assets` and `discovery_jobs`; `0004_verification_repairs` adds the
external-ID history and database integrity/concurrency controls. EC2, S3, IAM, and RDS
collectors normalize paginated inventory. Repeated runs preserve
first-seen history, update current values, and safely deactivate missing assets only after that
collector succeeds. The UI provides asset filters/details and discovery job status/results.
Temporary AWS credentials are not persisted. Stage 4 rules evaluate persisted normalized data;
Risk, AI, remediation, and raw event ingestion remain absent. Compliance interprets Stage 4
evidence and never performs detection or live AWS calls.

## Governance exception

PR #2 merged Stages 1–3 to `main` at `0849e75d...` without a recorded GitHub approval. The
repository owner explicitly accepted the missing approval as a governance exception and
authorized Stage 4. This is not a claim that an independent GitHub approval occurred.

PR #4 had zero recorded GitHub reviews/approvals and no automated check rollup. The exact feature
SHA passed independent technical clean-room verification, after which the owner recorded an
**Owner-authorized governance exception for PR #4**. This is not an independent GitHub,
CODEOWNER, automated CI, or repository-policy approval.

PR #6 also had zero recorded reviews/approvals and no automated check rollup. Its exact feature
SHA passed technical clean-room verification, after which the owner recorded:
**Owner-authorized governance exception for PR #6.** This is not an independent GitHub,
CODEOWNER, automated CI, or repository-policy approval.

PR #8 also had zero recorded reviews/approvals and no automated check rollup. Its exact feature
SHA passed technical detached verification, after which the owner recorded:
**Owner-authorized governance exception for PR #8.** This is not an independent GitHub,
CODEOWNER, automated CI, or repository-policy approval.

## Stage 5 limitations

The initial catalog contains four controls and twelve mappings. It is not complete framework
coverage or certification, mappings require human compliance review, and compliance export is
not implemented. The Starlette TestClient/httpx deprecation warning remains; Node 20 LTS or 22
LTS is recommended.

## Teammate and AI handoff

The root `README.md` is the complete teammate run guide. A new AI session must be given the
seven root source-of-truth files: `NEW_CHAT_CONTEXT.md`, `PRD.md`, `architecture.md`,
`design.md`, `rules.md`, `phases.md`, and `memory.md`. It must summarize the project goal,
architecture, implementation state, known issues, and next task before editing. Contradictions
must be resolved against current repository evidence. Automated verification uses synthetic
data and deterministic AWS doubles; never use real customer AWS credentials or resources.

## Stage 7 boundary

Stage 7 explains persisted deterministic Stage 4–6 evidence through six
bounded drafting tasks. It uses a deterministic offline mock provider by
default, strict schemas, central redaction, versioned prompts, immutable source
references/responses, tenant isolation, quota controls, and human-review
labels. It has no authority to detect, score, mutate, remediate, or deliver.
