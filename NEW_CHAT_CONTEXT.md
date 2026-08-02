# CloudOps New Chat Context

> Attach this file with [PRD.md](PRD.md), [architecture.md](architecture.md),
> [design.md](design.md), [rules.md](rules.md), [phases.md](phases.md), and
> [memory.md](memory.md). Code and tests outrank documentation when evidence conflicts.

## Project and architecture

CloudOps is a multi-tenant AWS security-posture application. Customers connect read-only roles
through STS and External IDs. Deterministic rules detect findings; AI may explain them but never
detects findings or authorizes remediation. Remediation is allowlisted and approval-gated. The mock
executor remains the default; a default-disabled live executor supports only exact S3 Public Access
Block and EC2 ingress-rule actions and has not been validated against live AWS.

The stack is React/TypeScript/Vite, FastAPI/Pydantic/SQLAlchemy, PostgreSQL, and PostgreSQL-backed
durable jobs. Scheduler and job workers implement leases, heartbeats, retries, idempotency and
dead-letter behavior. Bedrock, SES and Jira adapters exist with mocked/CI-verified tests; live
provider validation remains pending for all three.

An organization-managed single-host path is being implemented on
`feat/one-command-cloudflare-selfhost`: a named Cloudflare Tunnel reaches only Nginx, while
FastAPI/PostgreSQL stay un-published; startup is migration-gated; generated secrets persist in
ignored Docker secret files; and shared PowerShell/Bash commands manage health, update,
backup/restore, and explicit destruction. Live named-tunnel and clean-machine proof remain pending.

## Demo-hardening state

Implemented and locally verified on 2026-07-30:

- Nginx serves the SPA and relative `/api/` routes from one browser origin.
- The normal demo does not publish the API container port.
- A local-demo-only forwarded-origin feature is off by default and refused in staging/production.
- Nginx overwrites the trusted forwarding headers; wildcard CORS/trusted hosts are not used.
- Invitation pathname, query and hash survive authentication; generated links use the current
  browser origin and URL-safe token encoding.
- Synthetic discovery calls no AWS and produces deterministic critical/high findings with zero rule
  evaluation errors.
- Scheduler and job workers run by default and process Run-now jobs.
- Quick Tunnel provides temporary HTTPS access to the web service only; Mailpit stays local.

Verification evidence: Ruff clean; strict Mypy clean across 160 source files; 95 focused backend
tests; 621-test full backend traversal with no failures; 9/9 focused PostgreSQL migration tests;
69 focused and 115 full frontend tests; lint, typecheck and production build; Compose rendering;
Nginx syntax; local multi-user E2E; real Quick Tunnel start/restart; and clean dependency audits.
See [memory.md](memory.md) for exact session evidence and limitations.

## Current limitations

- All demo data and provider behavior are synthetic.
- Quick Tunnel URLs are random, temporary, and subject to DNS propagation/cache behavior.
- A Mailpit-generated email uses configured `FRONTEND_URL`; remote guests should use the
  current-origin link displayed by the invitation UI.
- The controlled AWS sandbox Terraform and default-refusing live test harness are implemented but
  have not been applied or run against AWS.
- Owner-only routes configure/rotate/clear remediation trust, grant/revoke sandbox approval, and
  prepare a server-owned live request without contacting AWS or enabling execution flags.
- No live AWS/customer access, Bedrock invocation, SES delivery, staging/production deployment,
  backup restore, canary, rollback rehearsal, or formal UAT has been performed.

## Current next task

The live-remediation data model (PR #25), governed two-action executor (PR #26), controlled AWS
sandbox Terraform (PR #27), and opt-in runbook/harness (PR #28) are merged into `main`. The current
feature adds privileged database-only administration and live-request preparation. After review,
the next action is a human-reviewed sandbox plan—not an automatic deployment.

## Safety

Never commit secrets or long-lived AWS keys, weaken tenant isolation, enable live remediation,
bulk-stage files, rewrite shared history, or claim live validation without evidence. Live AWS,
provider, staging, production, email and customer-account operations require separate explicit
authorization.

Read the attached project files and treat them as the source of truth.

First, summarize your understanding of:

- the project goal
- the architecture
- the current implementation state
- known issues
- the next task

Do not modify code yet. Identify contradictions or missing information before proceeding.

Update NEW_CHAT_CONTEXT.md after major architectural changes. Update memory.md after each substantial
coding session.
