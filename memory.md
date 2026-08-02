# CloudOps working memory

## Session state

- Date: 2026-08-02 (Asia/Kolkata).
- Documentation worktree: `D:\learn\cdac\CloudOps-documentation-refresh`.
- Branch: `docs/comprehensive-project-documentation-refresh`.
- Base: `origin/main` at `bec5753ad127d8ed8968d539ee625130c6a2e06f`.
- Current Alembic head: `0019_live_remediation_data_model` (one head).
- This session is documentation-only; no application, migration, Terraform, workflow, or runtime
  behavior is authorized to change.

## Completed implementation represented by main

- Authentication/RBAC, invitations, tenant isolation, audit.
- STS onboarding, normalized discovery, deterministic rules, findings, compliance, deterministic
  risk, dashboard, and advisory AI.
- Approval-gated notifications, Jira, schedules, PostgreSQL durable jobs.
- Governed mock/dry-run remediation, immutable evidence, default-disabled S3/EC2 live executor.
- Separate remediation role/External ID and owner-only trust/sandbox administration.
- Controlled AWS sandbox Terraform and opt-in live-remediation runbooks/harness.
- CI, containers, managed-environment Terraform, immutable release workflow, and self-host tooling.

## Verified evidence

- Current source/migrations/tests/workflows were inspected for this documentation audit.
- GitHub Actions for the base commit reported all seven CI jobs successful.
- Automated AWS/provider behavior is synthetic/fake/Stubber-based; it is not live evidence.
- No broad test suite is rerun solely for prose changes; documentation validation is recorded in the
  eventual pull request.

## External blockers and risks

Operator-reported AWS IAM Identity Center setup is incomplete. Identity/account classification,
saved plan, cost review, apply, EC2 deployment, Cloudflare, workload identity, live discovery,
Bedrock/SES/Jira, S3/EC2 remediation, manual rollback, backup restore, failure recovery, canary,
UAT, and production deployment remain **Not yet verified**.

Residual risks include generic AI evidence minimization, unproven live IAM/provider behavior,
unrehearsed rollback/restore, cost exposure if sandbox teardown is incomplete, and misleading
production-readiness claims.

## Decisions

- PostgreSQL, not Redis/Celery, is the durable job backend.
- Deterministic rules and risk are authoritative; AI is advisory.
- Discovery and remediation trust/External IDs remain separate.
- Live dispatch is static and limited to two actions; mock/dry-run remains default.
- Rollback state is captured, but rollback execution is separately approved/manual.
- Repository implementation and CI evidence are distinct from operational/deployment evidence.

## Next exact task

After this documentation pull request is reviewed, resume operational preflight only with a
short-lived non-production SSO identity. First verify account/caller/region and stop for explicit
non-production and non-management-account confirmation. Terraform planning requires separate
authorization; apply and live remediation require later exact approvals.

## Safe next commands

```powershell
git status --short
git diff --check
python -m alembic heads
```

Do not run deployment, AWS provider, live-remediation, direct database, history-rewrite, broad
staging, or secret-displaying commands from this documentation task.
