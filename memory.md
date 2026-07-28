# CloudFix Working Memory

> Update this file after every substantial coding session. The
> [repository map](architecture.md#repository-map) explains organization; this file records where
> work stopped.

## Session identity

- Date: 2026-07-29 (Asia/Calcutta)
- Repository/worktree: `D:\learn\cdac\cloudfix-integration`
- Branch: `integration/phase-1-2-3`
- Verified implementation HEAD before this memory update:
  `5bd6536cd36b259b54278bf10216220725df9464`
- HEAD summary: `5bd6536 test(security): classify synthetic scanner sentinels`
- Merge in progress: no
- Push/merge authorization: yes, subject to clean verification and non-force safety gates
- Deployment/live AWS authorization: no
- Current task: publish the verified integration branch, reconcile it with current remote `main`,
  and remove only clean, merged, obsolete worktrees

## Recent focused commits

- `5bd6536` classified synthetic scanner sentinels without broad exclusions.
- `c663c35` added the truthful project handoff context.
- `917b805` updated operations and external-validation guidance.
- `e56c1a6` reconciled the implemented architecture.
- `55b1491` hardened deployment controls and observability.
- `80a2fff` hardened immutable release workflows.
- `257377a` added deployment and load validation helpers.
- `2ce6ea4` hardened runtime images and web routing.
- `413a7b6` resolved production verification findings.
- `63c9845` Terraform staging/production platform.
- `40ff171` worker heartbeats and telemetry.
- `64bb7ec` governed dry-run remediation.
- `ca12d83` Bedrock and SES workload adapters.
- `251295c` integration of security and distributed-platform phases.
- Earlier Phase 3 commits cover CI, documentation, migration/runbooks, containers, readiness,
  tests, durable jobs, and notifications.

## Git state at audit start

### Staged

None.

### Unstaged

- `.env.example`
- `.github/workflows/README.md`
- `.github/workflows/ci.yml`
- `README.md`
- `apps/api/Dockerfile`
- `apps/api/app/core/config.py`
- `apps/api/app/main.py`
- `apps/api/app/services/aws_onboarding.py`
- `apps/api/app/tests/test_api.py`
- `apps/api/app/tests/test_aws_onboarding.py`
- `apps/api/app/tests/test_platform_jobs.py`
- `apps/api/app/tests/test_v1_demo_black_box.py`
- `apps/api/app/worker/job_worker.py`
- `apps/web/Dockerfile`
- `apps/web/src/api/client.ts`
- `apps/web/src/test/app.test.tsx`
- `apps/web/vite.config.ts`
- `docs/architecture/system-overview.md`
- `docs/operations/backup-and-recovery.md`
- `docs/operations/deployment-strategy.md`
- `docs/operations/monitoring-strategy.md`
- `infra/README.md`
- Terraform files under `infra/bootstrap`, both environment roots, and database/network/platform/
  secrets modules.
- `scripts/migration_preflight.py`

This documentation audit additionally changes documentation files; inspect final status rather than
assuming this list remains exhaustive.

### Untracked

- `.github/workflows/release.yml`
- Local verification output directories under `.verification-logs/` and `.pytest-tmp-*`; these are untracked evidence, not committed source
- `apps/api/alembic/versions/0017_remediation_json_trigger.py`
- `apps/api/app/security/trusted_host.py`
- `docs/operations/aws-provider-setup.md`
- `docs/operations/canary-and-rollback.md`
- `docs/operations/remediation-governance.md`
- `docs/release/v1-handover.md`
- `docs/testing/uat-checklist.md`
- `scripts/deployment_smoke.py`
- `scripts/load/k6-v1-smoke.js`

## Current implementation truth

- Alembic has one head: `0017_remediation_json_trigger`.
- Bedrock and SES adapters exist; automated AWS tests use Botocore Stubber.
- Deterministic rules detect findings. AI is advisory and cannot approve remediation.
- Remediation is allowlisted, approval-gated, disabled by default, and mock/dry-run only.
- PostgreSQL durable jobs implement leases, generations, heartbeats, idempotency, retry,
  cancellation, requeue, dead-letter state, and audit evidence.
- Scheduler and job worker are API-package modules; no Celery/Redis broker is implemented.
- Terraform roots exist for bootstrap, staging, and production.
- CI and immutable-release workflows exist but have not been proven live.

## Verification evidence

Final locally reproduced results:

- Backend: scoped Ruff clean; strict Mypy clean across 157 source files; 563 tests passed against
  disposable PostgreSQL with 94% combined branch coverage.
- Migrations: one Alembic head (`0017_remediation_json_trigger`); upgrade, current, check, and
  migration preflight passed.
- Frontend: clean install, lint, typecheck, 112 tests, production build, and dependency audit
  passed.
- Infrastructure: Terraform formatting and validation passed for bootstrap, staging, and
  production; Checkov 3.2.471 reported 471 passed, 0 failed, and 39 documented skips.
- Containers: API, job worker, scheduler worker, migration task, and web smoke checks passed;
  API and web run as non-root.
- Security: dependency checks passed; the final redacted Gitleaks candidate scan found no leaks.
  Docker Scout found no vulnerable packages in either final local image.
- Provider tests use synthetic mocks or Stubber. No live AWS provider call was made.

Local command output is ephemeral; retain CI and release evidence externally for durable audit.

## Failed or blocked checks

- No required local gate is currently failing.
- An additional repository-wide Ruff formatting check identified pre-existing formatting
  differences, including historical migrations. It is not the configured lint gate, made no
  changes, and historical migrations must not be reformatted merely for style.
- The host uses Node 23 and emitted an engine-support warning; project CI uses Node 22.
- Deployment/provider/UAT gates are blocked by missing approved external environment and evidence.
- The earlier Alembic invocation from repository root failed to resolve its relative script path;
  rerunning from `apps/api` correctly reported head `0017`. This was a command-directory error,
  not a migration failure.

## External blockers and risks

- No live staging or production apply.
- No live GitHub OIDC role-assumption/ECR promotion evidence.
- No live Bedrock invocation or SES delivery/bounce evidence.
- No completed UAT, load baseline, alarm-routing test, weighted canary, rollback, or restore
  rehearsal.
- Weighted canary and cross-region/cross-account backup are deferred.
- GitHub action references use release tags instead of immutable commit SHAs.
- Remote branch publication and remote-main reconciliation are not yet complete.
- Runtime/UI branding remains CloudOps while the repository handoff name is CloudFix.

## Decisions

- PostgreSQL is the durable queue and source of truth.
- ECS/Fargate task roles are the runtime identity design.
- GitHub OIDC is the deployment identity design.
- Infrastructure injection keeps Pydantic Settings as the configuration boundary.
- Detection remains deterministic; AI remains advisory.
- Live remediation mutation is outside current V1.
- Build once and promote exact image digests.
- Migrations use additive expand-and-contract deployment.

## Intentionally deferred

- Live AWS mutation executor.
- Weighted traffic canary/CodeDeploy.
- Cross-region/cross-account backup replication.
- Live provider tuning, cost baselines, UAT, restore, rollback, and production release.
- Runtime/UI rename from CloudOps to CloudFix.

## Documentation audit validation

- Audited 106 tracked or candidate documentation/text files; prohibited files were excluded.
- Verified 116 relative Markdown links with no missing targets.
- Structurally validated 26 Mermaid blocks with balanced fences and recognized diagram types.
- Parsed 21 PowerShell documentation blocks with no syntax errors; commands were not executed.
- Configuration-name review found no invalid documented application/provider flag; script-only output variables and enum/status names were classified separately.
- Redacted secret-shape scan found no AWS-key, private-key, bearer-token, JWT, provider-key, webhook-URL, or password-bearing URL shapes.
- Alembic reports one head: `0017_remediation_json_trigger`.
- `git diff --check` passes; there are no unmerged paths and no staged files.

## Next exact task

1. Validate this memory-only update and commit it explicitly.
2. Fetch the remote, inspect divergence, and push the verified integration branch without force.
3. Merge through a separate clean `main` release worktree, rerun post-merge gates, and push only
   if the remote base is unchanged.
4. Remove only clean, merged, obsolete worktrees using Git worktree commands.
5. Do not deploy or run live AWS until external gates and authorization are supplied.

## Next safe commands

Run from `D:\learn\cdac\cloudfix-integration`:

```powershell
git status --short
git diff --check
git diff --name-only --diff-filter=U
git diff -- README.md NEW_CHAT_CONTEXT.md PRD.md architecture.md design.md rules.md phases.md memory.md docs
Set-Location apps/api
alembic heads
```

If a documentation commit is later authorized, stage only explicit reviewed paths:

```powershell
git add -- README.md NEW_CHAT_CONTEXT.md PRD.md architecture.md design.md rules.md phases.md memory.md
git add -- docs/path/to/each-reviewed-file.md
```

## Commands not authorized

Do not stage, commit, merge, push, rebase, reset, clean, tag, deploy, apply Terraform, start live AWS
tests, invoke live Bedrock/SES, or send notifications. Never use `git add .` or `git add -A`.

## Files that must remain untouched

- `CLAUDE.md`
- `compose.aws.override.yml`

Do not read, summarize, modify, stage, delete, or display either file.
