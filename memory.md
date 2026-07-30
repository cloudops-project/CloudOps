# CloudOps Working Memory

> Update after every substantial coding session. The repository map in
> [architecture.md](architecture.md) explains organization; this file records where work stopped.

## Session state

- Date: 2026-07-31 (Asia/Kolkata)
- Worktree: `D:\learn\cdac\cloudfix-main-release`
- Baseline branch: `main`
- Baseline HEAD: `09cf6d456f615b1d1892e5e18aecd7c42bc1fe54`
- Current documentation branch: `docs/current-project-state`
- Current Alembic head: `0018_jira_integration`
- PRs #18, #19, #20 and #21 merged into `main`
- Working tree state before this session's edits: clean
- Merge, deployment, live AWS, live Bedrock, live SES and live Jira authorization: none
- Product name: CloudOps; CloudFix remains the repository/legacy identifier

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
- No live AWS account, customer account, Bedrock, SES, Jira Cloud, staging deployment, production
  deployment, backup/restore drill, canary, rollback rehearsal or formal UAT has been run.
- Node 23 emits an engine warning locally; the container/CI toolchain uses Node 22.
- This sandbox environment has no working `gh`/`aws`/`terraform`/`docker` CLI and no outbound
  network access to GitHub or PyPI (proxy returns 403 for both) — see the handoff section below.

## Next operational milestone

Run the full baseline and live infrastructure phases from an environment with working GitHub,
Python package, Docker, Terraform and AWS connectivity.

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
