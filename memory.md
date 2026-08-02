# CloudOps Working Memory

> Update after every substantial coding session. The repository map in
> [architecture.md](architecture.md) explains organization; this file records where work stopped.

## Session state

- Date: 2026-08-02 (Asia/Kolkata)
- Worktree: `D:\learn\cdac\CloudOps-remediation-admin-workflow`
- Baseline branch and HEAD: `origin/main` at `d162949a560d9e87a5cc7a231197bb3e6f611a0d`
- Current branch: `feat/remediation-admin-workflow`
- Current Alembic head: `0019_live_remediation_data_model`
- PR #25 (data model), PR #26 (governed executor), PR #27 (controlled sandbox Terraform), and PR
  #28 (runbook and opt-in harness) are merged into `main`.
- Owner-only remediation trust, sandbox approval, and live-request preparation changes are
  implemented locally but are not yet committed, pushed, or reviewed by CI.
- Merge, deployment, live AWS, live Bedrock, live SES and live Jira authorization: none
- Product name: CloudOps; CloudFix remains the repository/legacy identifier

## Current self-host feature session

Implemented a production-mode one-command path using `compose.selfhost.yml`, a named Cloudflare
Tunnel, Docker file secrets, migration-gated startup, private API/PostgreSQL networking,
worker/scheduler heartbeat health, PowerShell/Bash wrappers, shared Python lifecycle control,
local backup/restore, focused tests, CI gates, and an operator guide.

Verification completed in this worktree:

- 39 focused self-host tests passed; self-host scripts passed strict Mypy and Ruff.
- Application Ruff passed; strict Mypy passed across 168 source files.
- Full backend traversal succeeded with 644 tests collected. The 112 PostgreSQL-dependent tests
  were then run against a disposable migrated PostgreSQL 16 container and all passed.
- Frontend `npm ci`, ESLint, typecheck, 115 tests, production build, and npm audit passed. Prettier
  initially identified three baseline files and passed after mechanical formatting.
- `pip check` and `pip-audit --skip-editable` passed in this worktree's isolated environment.
- PowerShell parsing, Bash syntax, destructive-refusal wrappers, organization/demo Compose
  rendering, workflow YAML parsing, and Alembic heads/upgrade/current/check/preflight passed.
- Disposable container acceptance passed migration gating, internal readiness, worker/scheduler
  heartbeats, Nginx-proxied registration/login, down/restart persistence, backup, restore
  integrity, post-restore migration, and restored login.
- Docker Scout found no vulnerable packages in the final API or web runtime stages. Redacted
  Gitleaks scanning of candidate files found no leaks.
- Disposable containers, networks, PostgreSQL volumes, runtime secrets, and backup artifacts
  created by this session were removed.

External validation remains pending for a real named Cloudflare Tunnel, a separately provisioned
clean host, off-host backup custody, and live optional providers. The synthetic tunnel token was
intentionally rejected and is not live Cloudflare evidence.

Focused commits created in this session:

- `a470136` — one-command self-host implementation.
- `39bbcce` — fault-isolating tests, CI gates, and required mechanical frontend formatting.

## Implemented and merged into main

- Demo hardening (PR #18): same-origin Nginx SPA/API flow, API not host-published in the standard
  demo, synthetic discovery using the real persistence/evaluation path, scheduler and job workers
  enabled by default, multi-user and tenant-isolation flow, Quick Tunnel exposing only the web
  service, Mailpit remaining local, governed mock/dry-run remediation.
- Jira integration (PR #19, follow-up fixes PR #20): organization-scoped Jira configuration, a
  global fail-closed kill switch, tenant-aware RBAC, connection testing, AES-256-GCM encrypted
  API-token storage, idempotent Jira issue creation, finding-to-issue links, optional
  remediation-request association, migration `0018_jira_integration`, and focused automated test
  coverage. Classification: **implemented and locally/CI verified; live Jira Cloud validation
  pending.**
- Cryptography security repair (PR #21): `cryptography` upgraded from `>=43,<46` to `>=48.0.1,<49`.
  Evidenced validation for that PR: `cryptography 48.0.1` installed locally, `pip check` passed,
  `pip-audit --skip-editable` reported no known vulnerabilities, Ruff passed, Mypy passed, backend
  tests passed, and all five GitHub PR checks passed.

## Bootstrap and staging infrastructure — evidence status

A prior session reported that `infra/bootstrap` (Terraform state S3 bucket, DynamoDB lock table,
KMS key, GitHub OIDC provider, GitHub publish role, staging deployment role) had already been
applied to AWS. **This is user-reported historical information, not independently verified in this
environment.** It has not been confirmed with AWS CLI access, live account/region identity, or
Terraform remote-state inspection. Treat as unproven until revalidated. Staging application
infrastructure (VPC/ALB/ECS/ECR/RDS) is not deployed, and the expected `cloudops-staging-api` /
`cloudops-staging-web` ECR repositories are not confirmed to exist.

## Known limitations

- Quick Tunnel hostnames are ephemeral and DNS propagation/cache behavior is outside the app.
- The emailed invitation uses configured `FRONTEND_URL`; for a remote Quick Tunnel guest, copy the
  UI-generated current-origin link.
- Demo inventory, users and provider behavior are synthetic.
- The live AWS executor and controlled sandbox Terraform have no live AWS validation evidence.
- Owner-only database administration for remediation trust, sandbox approval, and live-request
  preparation is implemented on `feat/remediation-admin-workflow`; it performs no AWS operation.
- Automatic rollback execution is not implemented; the executor captures exact rollback state for
  a separately approved manual procedure.
- No live AWS account, customer account, Bedrock, SES, Jira Cloud, staging deployment, production
  deployment, backup/restore drill, canary, rollback rehearsal or formal UAT has been run.
- Node 23 emits an engine warning locally; the container/CI toolchain uses Node 22.
- GitHub pull-request CI has not run for this unpushed Phase D feature branch.

## Next operational milestone

Validate and review `feat/remediation-admin-workflow`, require every remote check, and merge only
through the protected pull-request process. After merge, stop before any AWS action. The next
operational action is a human-reviewed Terraform plan only after exact account, region, cost, and
authorization are supplied.

### Next-environment handoff prerequisites

- GitHub CLI (`gh`) authenticated.
- AWS CLI authenticated through an approved role or SSO (no long-lived local access keys).
- Terraform installed.
- Docker Desktop running.
- Python 3.12 available.
- Node 22 available.
- Network access to PyPI, the npm registry, GitHub, and AWS APIs.
- Approved AWS sandbox account ID.
- Approved staging account ID.
- Approved region.
- Jira test-site credentials stored outside Git.
- Approved SES recipients.
- Approved Bedrock model and region.

Verification commands (do not include secret values in output):

```powershell
gh auth status
aws sts get-caller-identity
aws configure get region
terraform -version
docker version
python --version
node --version
```

## Safe commands

```powershell
git status --short
git diff --check
docker compose -f compose.demo.yml config
docker compose -f compose.demo.yml --profile tunnel config
```

Do not bulk-stage, rewrite history, run live provider tests, or deploy from this session.
