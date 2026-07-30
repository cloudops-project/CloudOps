# CloudOps New Chat Context

> Attach this file with [PRD.md](PRD.md), [architecture.md](architecture.md),
> [design.md](design.md), [rules.md](rules.md), [phases.md](phases.md), and
> [memory.md](memory.md). Code and tests outrank documentation when evidence conflicts.

## Project and architecture

CloudOps is a multi-tenant AWS security-posture application. Customers connect read-only roles
through STS and External IDs. Deterministic rules detect findings; AI may explain them but never
detects findings or authorizes remediation. Remediation is allowlisted, approval-gated and currently
mock/dry-run only.

The stack is React/TypeScript/Vite, FastAPI/Pydantic/SQLAlchemy, PostgreSQL, and PostgreSQL-backed
durable jobs. Scheduler and job workers implement leases, heartbeats, retries, idempotency and
dead-letter behavior. Bedrock and SES adapters exist with mocked tests; live provider validation
remains pending.

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
- No live AWS/customer access, Bedrock invocation, SES delivery, staging/production deployment,
  backup restore, canary, rollback rehearsal, or formal UAT has been performed.

## Current next task

Review the demo-hardening pull request and its remote checks. Do not merge automatically. After
review, the next operational action is a clean-machine rehearsal:

```powershell
.\scripts\demo_bootstrap.ps1 -Reset
.\scripts\demo_tunnel.ps1 -NoFollow
```

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
