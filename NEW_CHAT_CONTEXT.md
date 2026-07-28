# CloudFix New Chat Context

## Source-of-truth hierarchy

Use evidence in this order: current source code; models/migrations; tests and retained results;
Terraform; workflows; Docker/Compose; scripts/runbooks; Git history; documentation. Existing prose
never overrides implementation.

The seven handoff files are:

- [NEW_CHAT_CONTEXT.md](NEW_CHAT_CONTEXT.md): compact entry point.
- [PRD.md](PRD.md): product requirements and release acceptance.
- [architecture.md](architecture.md): actual components, flows, and trust boundaries.
- [design.md](design.md): implemented frontend design.
- [rules.md](rules.md): development/safety rules.
- [phases.md](phases.md): stages 0–17 status.
- [memory.md](memory.md): exact stopping point and Git state.

## Project goal

CloudFix is the repository/project name for a multi-tenant AWS security-posture application whose
implemented runtime/UI name is CloudOps. It onboards customer roles, discovers assets, applies
deterministic rules, presents compliance/risk, provides bounded AI advice, delivers approved
notifications, schedules durable work, and governs dry-run remediation without storing customer
keys.

## Current architecture

- React/TypeScript/Vite web client.
- FastAPI/Pydantic/SQLAlchemy backend.
- PostgreSQL for tenant data, audit, and durable `platform_jobs`.
- Separate API, scheduler worker, job worker, and migration task entry points.
- Cross-account STS with External ID and memory-only temporary credentials.
- Deterministic detection; optional Bedrock advisory provider.
- Approval-gated mock/SMTP/SES/Slack/Teams notification providers.
- Governed mock/dry-run remediation only.
- Terraform bootstrap/staging/production roots targeting ECS/Fargate, RDS, ALB/WAF, KMS, Secrets
  Manager, CloudWatch, and ECR.
- CI and OIDC release workflows that build once and promote immutable digests.

## Implementation state

Implemented and locally verified: authentication/RBAC, tenant scoping, onboarding logic, discovery,
rules/findings, compliance, risk, dashboard, audit, durable jobs, scheduler, dry-run remediation,
provider adapters, configuration hardening, Terraform validation, and local container gates.

Implemented but external validation pending: customer-role discovery, Bedrock, SES, GitHub OIDC,
ECR publishing, Terraform plans/applies, ECS/RDS/ALB/WAF/alarms, deployment/rollback automation.

Deferred/not proven: live AWS mutation, weighted canary, cross-region backup, live restore/rollback,
UAT, load baseline, staging deployment, and production deployment.

## Verification state

Reported bounded groups A–I passed independently. Frontend reportedly passed lint/typecheck, 112
tests, and build. Checkov reportedly ended at 471 passed/0 failed; Gitleaks reported no leaks; the
final API image reported zero vulnerable packages and final web image no critical/high/medium
findings. This is **reported verification evidence; external log retention required**. Do not sum
overlapping test groups or strengthen the claim without retained artifacts.

Alembic currently has one head: `0017_remediation_json_trigger`.

## Active work

- Worktree: `D:\learn\cdac\cloudfix-integration`
- Branch: `integration/phase-1-2-3`
- HEAD at audit start: `63c9845da37abd7ba700efedebe4d155ef74f77e`
- Nothing was staged; substantial implementation and documentation changes remained unstaged or
  untracked.
- Exact state and next commands are in [memory.md](memory.md).

## Known issues and external blockers

- No live staging/production deployment, Bedrock invocation, SES delivery, UAT, canary, rollback,
  restore, or alarm-routing proof.
- Runtime/UI branding is still CloudOps.
- GitHub action references are version tags rather than immutable commit SHAs.
- External account, region, cost, IAM, DNS/ACM, provider, and protected-environment approvals are
  required before live work.

## Safety constraints

- Never commit secrets or store long-lived AWS access keys.
- Never weaken tenant isolation or let AI detect/authorize remediation.
- Never run arbitrary user-supplied AWS operations.
- Use explicit-path staging only; never use broad staging commands.
- Live AWS tests, notifications, Terraform apply, deployment, merge, and push require explicit
  authorization.
- Production deployment requires retained staging evidence and a separate explicit approval.
- `CLAUDE.md` and `compose.aws.override.yml` must not be read, summarized, modified, staged,
  deleted, or displayed.

## Documentation maintenance

“Update NEW_CHAT_CONTEXT.md after major architectural changes. Update memory.md after each substantial coding session.”

Documentation must distinguish local verification from live deployment and must validate paths,
settings, migration head, workflow names, and links against the repository.

## How to use this package

Upload all seven root files together. Start with this file, then consult PRD/architecture/rules for
scope and constraints, phases for status, design for UI facts, and memory for the exact handoff.

Use this exact new-chat instruction:

“Read the attached project files and treat them as the source of truth.

First, summarize your understanding of:
- the project goal
- the architecture
- the current implementation state
- known issues
- the next task

Do not modify code yet. Identify contradictions or missing information before proceeding.”
