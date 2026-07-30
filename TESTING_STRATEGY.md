# CloudOps Testing Strategy

The full project strategy is in
[docs/engineering/testing-strategy.md](docs/engineering/testing-strategy.md). This file records the
additional demo-hardening gates.

## Demo-specific coverage

- Compose services, profiles, ports and same-origin web/API contract.
- Nginx path preservation, forwarding-header overwrite, SPA fallback and cache boundaries.
- Forwarded-origin acceptance/rejection for HTTPS, localhost HTTP, host/scheme mismatch, missing or
  malformed values, disabled mode, staging/production refusal, direct access and spoof attempts.
- Synthetic discovery guardrails, exact collector metadata, zero deterministic-rule errors and
  expected severe findings.
- Scheduler enqueue, worker acquisition/completion, retry behavior and Run-now visibility.
- Dry-run remediation, authorization, audit evidence and live-AWS kill switches.
- Invitation current-origin URL generation, URL encoding and complete post-login redirect.
- Three-user token/session separation, role enforcement and cross-tenant denial.
- Quick Tunnel URL extraction, start/restart behavior and same-origin HTTPS flow.

## Verified 2026-07-30

- Ruff clean.
- Strict Mypy clean across 160 source files.
- 95 focused backend tests passed.
- Full backend traversal: 621 collected tests reached 100% with no failures or stderr against
  disposable PostgreSQL.
- Focused PostgreSQL notification migration/integrity tests: 9 passed.
- Frontend: clean install, lint, typecheck, 69 focused tests, 115 full tests and production build.
- Base/tunnel Compose rendering, built-image Nginx syntax, PowerShell parsing and local E2E passed.
- `pip check`, `pip-audit` and `npm audit`: clean.

No live AWS, Bedrock, SES, customer-account, staging or production test was run.
