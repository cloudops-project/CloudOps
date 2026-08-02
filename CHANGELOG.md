# Changelog

## [Unreleased] - current implementation baseline

### Added

- Deterministic `CLOUDOPS_RISK_V1` finding/account/organization scoring with versioned immutable
  snapshots and auditable component breakdowns.
- Advisory AI explanations and drafts with source compatibility, context minimization, sanitization,
  hashes/fingerprints, schema validation, staleness, rate limits, and audit evidence.
- Deterministic compliance, approval-gated notifications, and organization-scoped Jira integration.
- Governed remediation preview/approval, live-execution evidence model, default-disabled allowlisted
  S3/EC2 executor, controlled non-production sandbox Terraform, and default-refusing live harness.
- Owner-only remediation trust configuration/rotation/clear, sandbox approval/revocation, and
  server-owned live-request preparation with no automatic execution.

### Operational work not yet verified

- AWS SSO/account preflight, saved Terraform plan and cost review, apply, EC2 deployment, workload
  identity, read-only discovery, Cloudflare, live Bedrock/SES/Jira, controlled S3/EC2 remediation,
  manual rollback, backup restore, failure recovery, UAT, canary, and production deployment.

This section assigns no release date and does not claim deployment or production readiness.

## Unreleased — one-command Cloudflare self-hosting

- Added a production-mode private Compose topology with migration gating, durable worker/scheduler
  heartbeats, Nginx-only named-tunnel access, Docker file secrets, and persistent PostgreSQL.
- Added equivalent PowerShell/Bash commands backed by a shared Python control plane for install,
  verify, lifecycle management, update, backup/restore, and explicitly confirmed destruction.
- Added fail-closed configuration, fault-specific feature tests, CI static/container gates, and
  an operations guide.
- Live named-Cloudflare and clean-machine validation remain pending. No AWS deployment or live
  provider invocation is part of this work.

Notable user-visible and operational changes to CloudOps.

This file starts at the demo-hardening work of 2026-07-30. Earlier stage history is recorded in
[phases.md](phases.md) and [docs/planning/project-memory.md](docs/planning/project-memory.md); no
release versions or dates are invented here. There has been **no tagged release and no production
deployment**.

Format is loosely [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Dates are
`YYYY-MM-DD` in Asia/Calcutta.

## [Unreleased] - 2026-07-31 (Jira integration and cryptography security repair)

### Added

- **Jira Cloud integration** (PR #19, follow-up fixes PR #20): organization-scoped Jira
  configuration, a global fail-closed kill switch (`JIRA_ENABLED`), tenant-aware RBAC
  (`Capability.JIRA_MANAGE`/`JIRA_READ`), connection testing, AES-256-GCM encrypted API-token
  storage (`app/security/secret_box.py`), idempotent Jira issue creation, finding-to-issue links,
  optional remediation-request association, and migration `0018_jira_integration`. Focused
  automated test coverage reported passing in CI. **Implemented and locally/CI verified; live Jira
  Cloud validation pending.**

### Security

- **Cryptography dependency upgrade** (PR #21): `cryptography` upgraded from `>=43,<46` to
  `>=48.0.1,<49`. Evidenced validation: `cryptography 48.0.1` installed locally, `pip check`
  passed, `pip-audit --skip-editable` reported no known vulnerabilities, Ruff passed, Mypy passed,
  backend tests passed, and all five GitHub PR checks passed.

### Known limitations for this entry

Live Jira Cloud validation is pending. AWS bootstrap/staging infrastructure state reported in prior
sessions is user-reported historical information only, not independently verified in this
environment. No live AWS, Bedrock, SES, staging or production action was performed.

## [Unreleased] - 2026-07-30 (validated demo hardening)

- Validated the same-origin Nginx proxy, temporary Quick Tunnel, synthetic discovery, default
  scheduler/job workers, multi-user session isolation and dry-run remediation.
- Preserved complete invitation URLs across login and URL-encoded UI-generated invitation links.
- Removed normal host publishing of the API and hardened forwarded-origin trust with an overwritten
  proxy marker plus exact scheme/host comparison.
- Added worker health checks and corrected Nginx cache boundaries.
- Verification: Ruff clean; strict Mypy across 160 files; 95 focused backend tests; a 621-test full
  backend traversal; 9 focused PostgreSQL tests; 69 focused and 115 full frontend tests; frontend
  lint/typecheck/build; Compose/Nginx/PowerShell checks; local E2E; Quick Tunnel start/restart; and
  dependency audits.
- No live AWS, Bedrock, SES, customer-account, staging or production action was performed.

## [Unreleased] — 2026-07-30 (second entry, same day)

> **Not validated — same blocker as the first entry below.** The sandbox shell was re-attempted
> (`git status --short`, `python3 --version`, `docker --version`, `pwsh --version`,
> `node --version`) and returned the identical "Workspace unavailable... VM service not running"
> error on all five calls. See [KNOWN_ISSUES.md](KNOWN_ISSUES.md) VAL-01.

### Fixed

- **Retracted an incorrect readiness claim.** An earlier response in this day's work ended with the
  status `DEMO_CODE_READY_FOR_CODEX` in the same message that stated no validation command had been
  run — a direct contradiction. This entry and the accompanying final response correct that: the
  truthful status given below is `BLOCKED_BY_UNAVAILABLE_TOOLING`, not a readiness claim.
- **Invitation flow.** `apps/web/src/pages/InviteMemberPage.tsx` now builds and displays a full,
  copyable invitation URL from `window.location.origin` (works for `localhost` or the live tunnel
  origin) plus the existing `development_token`, instead of showing only the bare token.
  `scripts/demo_tunnel.ps1`'s printed instructions were updated to match, and a "CloudFix
  application role" wording inconsistency in the same script was corrected to "CloudOps."
- **`README.md` pointed at the wrong worktree.** "Local development" told an operator to
  `Set-Location D:\learn\cdac\cloudfix-integration` — a different checkout than this repository.
  Corrected to `cloudfix-main-release`, with a pointer to `DEMO_RUNBOOK.md` for the demo-specific
  startup command.

### Added

- **Pass 2 documentation.** Six new root-canonical thin-index documents — `THREAT_MODEL.md`,
  `TESTING_STRATEGY.md`, `DEPLOYMENT.md`, `OPERATIONS.md`, `DATA_MODEL.md`, `API_CONTRACTS.md` —
  each pointing into its detailed `docs/` equivalent rather than duplicating it, plus thin pointer
  blockquotes added to those six `docs/` files (and `docs/operations/monitoring-strategy.md`). The
  five pre-existing root documents (`PRD.md`, `architecture.md`, `design.md`, `rules.md`,
  `phases.md`) were corrected in place — naming alignment with ADR-010, and cross-references to
  `DEMO_RUNBOOK.md`/`SECURITY_MODEL.md` — rather than rewritten, since their existing content was
  accurate.

### Known limitations for this entry

Same as the first entry below, unchanged. This entry adds no new demo capability — it corrects
process (an incorrect status), fixes one frontend UX gap and one wrong path in documentation, and
completes documentation reconciliation. It does not make any previously-unvalidated code validated.

## [Unreleased] — 2026-07-30 (first entry, same day)

> **Not validated.** Everything in this entry was authored without executing tests, linters,
> type-checkers, Docker, or Git. See [KNOWN_ISSUES.md](KNOWN_ISSUES.md) VAL-01.

### Added

- **Temporary multi-user public demo access.** A `cloudflared` Quick Tunnel service behind an opt-in
  `tunnel` Compose profile, plus `scripts/demo_tunnel.ps1`, which starts the tunnel, extracts the
  random `*.trycloudflare.com` URL, prints the temporary-URL warning and invitation instructions, and
  keeps the tunnel running. Requires no Cloudflare account, token, or credential file.
- **One-command demo bootstrap.** `scripts/demo_bootstrap.ps1` validates the Compose file, builds,
  starts the stack, waits for health, seeds synthetic data, verifies both workers are running, and
  prints URLs and synthetic credentials. `-Reset`, `-SkipBuild` and `-Tunnel` switches.
- **`job-worker` demo service.** `compose.demo.yml` previously had no job worker at all, so a
  "Run now" scan could never leave `pending` — `run_schedule()` only enqueues a `SCHEDULED_SCAN`
  platform job and never scans inline.
- **Demo-safe synthetic discovery.** New `DEMO_SYNTHETIC_DISCOVERY` setting and
  `apps/api/app/services/demo_inventory.py`, the single source of truth for synthetic inventory.
  Discovery runs its real normalize/upsert/stale/counter/audit pipeline without assuming a customer
  role. Refused when `APP_ENV` is `staging` or `production`.
- **Forwarded-host same-origin allowance.** New `TRUST_FORWARDED_HOST_SAME_ORIGIN` setting lets the
  API recognise a genuinely same-origin request arriving through an ephemeral public hostname, so the
  tunnel URL never has to be added to CORS or trusted hosts. Off by default; refused in
  production-like environments. See [DECISIONS.md](DECISIONS.md) ADR-D06.
- **Dry-run visibility.** `dry_run` added to the frontend `RemediationRequest` type and surfaced as a
  badge alongside `mock automation`. The API already returned the field; the UI had silently dropped
  it.
- **Regression tests.** `apps/api/app/tests/test_demo_stack.py` and
  `apps/api/app/tests/test_demo_tunnel_access.py` (compose/proxy contract, seed guardrails, zero rule
  errors, expected findings, run-now enqueue, tenant isolation, dry-run, audit evidence, same-origin
  accept/reject matrix, multi-user session separation); `apps/web/src/test/demo-same-origin.test.tsx`.
- **Documentation.** A "Two-day demo" quick start and a tunnel/multi-user section in `demo_v1.md`;
  new `DEMO_RUNBOOK.md`, `SECURITY_MODEL.md`, `KNOWN_ISSUES.md`, `DECISIONS.md` and this file.

### Fixed

- **Demo web unreachable.** `compose.demo.yml` mapped `5173:5173`, but the web image serves Nginx on
  `8080`. Now `5173:8080`.
- **Demo seed crash.** `scripts/demo_seed.py` passed `settings.database_url` (a Pydantic `SecretStr`)
  to `sqlalchemy.engine.make_url`, raising
  `Expected string or URL object, got SecretStr('**********')`. Now uses the existing
  `settings.database_dsn` reveal boundary.
- **Cross-origin demo fragility.** The frontend was built against an absolute API URL, so temporary
  tunnel hostnames produced `Failed to fetch`. The demo bundle now builds with an empty
  `VITE_API_BASE_URL` and Nginx proxies `/api/` to `api:8000` with the path preserved.
- **17 rule-evaluation errors per demo evaluation.** The seed wrote metadata key names no
  deterministic rule reads (`ingress`, `public_ip`, `imds_v2_required`, `public_access_block`,
  `encryption_enabled`), so every affected rule correctly returned
  `invalid_or_incomplete_metadata` — and the two headline CRITICAL findings (open SSH, public S3
  bucket) were never created at all. The rules were correct; the seed data was wrong. Seeded metadata
  now matches the real collector contract. No exception was suppressed and partial-evaluation safety
  is unchanged.
- **Scheduler hidden behind a manual profile.** `scheduler-worker` no longer requires
  `--profile manual`, so the demo does not depend on remembering an extra command.
- **Remediation execute returned 409 in the demo.** `REMEDIATION_EXECUTION_ENABLED` was unset, so the
  operator kill switch blocked the mock executor. The demo now enables the mock switch only;
  `REMEDIATION_LIVE_AWS_ENABLED` remains false.
- **Scan-run status never refreshed.** Job processing became asynchronous, so a single query
  invalidation left the run visibly `pending`. The scan-run query now polls every 2s while a run is
  `pending` or `running`, and stops afterwards.
- **Seed silently masked rule errors.** `demo_seed.py` now reports `evaluation_status`,
  `evaluation_rules_evaluated`, `evaluation_errors` and `findings_by_severity`, and exits non-zero if
  any rule errored.
- **Seed could half-apply on re-run.** Re-running without `--reset` previously failed partway through
  on unique constraints. It now detects existing demo data and fails clearly, naming `--reset`.
- **Seed accepted staging.** The demo-database guard refused only `production`; it now refuses
  `staging` too and names the resolved database in the refusal message.
- **Stale demo instructions.** `demo_v1.md`'s `--profile manual` steps for `compose.demo.yml` were
  corrected.

### Changed

- **`/ready` distinguishes dependency failure from process failure.** A database error now returns
  `503 dependency_unavailable` instead of a generic 500, logging only the exception type — no
  connection string, driver error, or exception text reaches the client.
- **Containers run as non-root.** The API image adds a `cloudops` system user and a `HEALTHCHECK`
  against `/health`; the web image runs as `node`/`nginx` and health-checks `/healthz`.
- **Migrations run once per release.** A dedicated `migrate` service runs `alembic upgrade head` to
  completion and the API depends on it via `service_completed_successfully`, replacing the previous
  inline per-replica `alembic upgrade head`.
- **Product naming.** `memory.md` retitled from "CloudFix Working Memory" to "CloudOps Working
  Memory" to match [ADR-010](docs/architecture/decisions/ADR-010-cloudops-product-name.md). The
  repository/project name remains CloudFix; a runtime rename is deferred.

### Security

- Cookie-authenticated CSRF protection is preserved: a mismatched `Origin`, mismatched scheme, or
  missing forwarded host is still rejected with 403, and the new allowance is off by default and
  refused in production-like environments.
- No wildcard CORS origin and no wildcard trusted host were introduced; a regression test asserts
  both.
- No tunnel hostname is compiled into the frontend bundle or written into configuration; a regression
  test asserts `trycloudflare` appears nowhere in `compose.demo.yml`, the web Dockerfile, or the API
  client.
- Mailpit is intentionally not exposed through the tunnel, because an open mail UI would disclose
  invitation tokens.
- Remediation remains dry-run/mock only; no code path mutates customer AWS.
- Synthetic placeholders only. No real credential, account ID, verified domain, model ARN, or webhook
  URL was added.

### Known limitations for this entry

Synthetic AWS data only · Quick Tunnel URL is random, changes on restart and is not persistent · no
Jira · no live Bedrock · no live SES · no production deployment · no backup/restore drill · no full
rollback drill · no enterprise-grade UAT · not suitable for sensitive data.
