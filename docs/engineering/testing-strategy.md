# Testing Strategy

## Stage 1 executable suite

Backend tests inject a disposable SQLite database and cover password/JWT/token primitives, configuration and role policy, health/readiness, registration/login, token rotation/reuse/logout/password change, ownership, tenant isolation, invitations, idempotent acceptance, role/status/removal lifecycle, final-owner protection, audit creation, and sensitive response exclusion. Migration verification uses a separate disposable database and performs upgrade/current/schema inspection/downgrade/re-upgrade.

Frontend Vitest/Testing Library tests cover registration/login validation, keyboard-operable forms, protected redirects, unauthorized/not-found views, organization/profile pages, dashboard loading/empty data, member role controls, invitation form, and token population. Required gates are Prettier, ESLint, TypeScript, Vitest, and a Vite production build.

The disposable PostgreSQL 16 suite validates upgrade/downgrade/re-upgrade, schema/model drift, partial pending-invitation uniqueness, concurrent refresh rotation, concurrent invitation acceptance, and concurrent final-owner demotion/suspension/removal using two independent sessions at PostgreSQL `read committed` isolation. A live browser E2E and distributed rate limiting remain follow-up verification.

## Purpose and audience

Engineering, QA, security, and product use this staged strategy to verify behavior without claiming tests already exist or pass.

Unit tests cover state machines, redaction, normalization, deterministic rules, permission policy, fingerprinting, and retry decisions. Integration tests use PostgreSQL and provider adapters for repository tenancy, transactions, STS/Jira/notification contracts, queue leases, and audit outbox. Contract tests pin OpenAPI/provider assumptions. End-to-end tests cover onboarding, scan, finding, Jira/manual/approved sandbox remediation, verification, acceptance expiry, and audit.

The implemented Stage 4 suite covers collector configuration metadata, deterministic rule
positive/negative/error behavior, finding detect/update/resolve/reopen/suppress lifecycles, all
six roles, bounded APIs, escaped frontend evidence, and PostgreSQL active-job,
finding-identity, tenant-integrity, migration, and concurrency behavior. Jira, notifications,
risk, and remediation remain future test strategy.

## Stage 5 executable coverage

Stage 5 tests verify versioned catalogs, inclusive rule-version mapping ranges, deterministic
overlap-union behavior, per-rule invocation summaries, PASS/FAIL/NOT_ASSESSED/ERROR semantics,
suppression remaining failure evidence, legacy evaluations receiving no synthetic PASS, and
immutable historical snapshots. Public HTTP tests cover all six roles, authentication failures,
tenant probing, filters, bounded pagination, and sanitized errors. PostgreSQL tests cover an
empty upgrade, populated `0006` to `0007` preservation, downgrade/re-upgrade, transactional DDL
rollback, composite foreign keys, partial indexes, triggers, independent-session races, and
evaluation finalization rollback. Frontend tests exercise protected compliance routes,
framework/control/assessment workflows, accessible confirmation, safe text rendering, pagination,
and role-aware controls.

Security testing includes cross-tenant negatives, IDOR/mass assignment, session/CSRF, injection/XSS/SSRF, rate/replay/idempotency, IAM policy review, prompt injection, secret/log leakage, webhook forgery, dependency/secret/static scans, dynamic tests, and authorized manual penetration testing in sandbox/UAT. Performance tests establish baselines for representative assets and queue load; no target is asserted before measurement.

Use deterministic fixtures with no customer data or credentials. Automated remediation is tested only in a dedicated sandbox with explicit approval and cleanup/rollback documentation. Restore drills verify backups. Accessibility includes automated, keyboard, and screen-reader checks.

Release gates, coverage thresholds, supported matrix, performance targets, and test-data lifecycle require team approval in later stages.

## Stage 2 executable coverage

Backend tests cover permanent external-ID reservation, deletion retention and collision retry,
account/role validation, duplicate constraints, mocked STS success/failure/account mismatch,
tenant isolation, owner/admin RBAC, audit events, and absence of temporary credentials.
PostgreSQL two-session tests exercise concurrent generation, validation, idempotent disconnect,
validation-versus-update/disconnect/delete, and independent-tenant mutation. Frontend tests
cover account-form validation, status display, role ARN validation, and protected onboarding
routes. Alembic lifecycle and model-diff checks run against the root tmpfs PostgreSQL compose
service. Live AWS calls are intentionally excluded; production integration requires a
controlled sandbox account.

## Stage 3 executable coverage

Deterministic AWS doubles verify multi-page pagination and normalization for EC2, S3, every
used IAM list operation, and RDS, including empty pages and duplicate markers. Authenticated API
integration coverage includes complete/partial/failed discovery, repeated upserts, first-seen
preservation, safe stale marking, account states, the complete RBAC matrix, tenant isolation,
audit redaction, details, filters, summaries, and pagination bounds.

PostgreSQL verifies migration drift, composite tenant foreign keys, lifecycle checks, permanent
external-ID history, actual repository upserts, concurrent discovery starts, terminal-state
races, and rollback behavior with independent sessions. Frontend tests cover inventory states,
combined filters, pagination, details, accessible discovery confirmation, duplicate-click
prevention, job states, escaped metadata, and role visibility. Live AWS remains a
controlled-sandbox verification step.
## Stage 6 verification

Stage 6 tests cover every component and priority boundary, exact maximum, age buckets,
unknown-input behavior, suppression, compensating controls, aggregate formulas, stable API
ordering, all-role authorization, tenant isolation, PostgreSQL constraints, immutable snapshots,
independent-session uniqueness races, migration lifecycle, escaped frontend rendering, dialog
focus, and Stage 1–5 regression. Release gates remain at least 95% backend coverage, zero
mandatory PostgreSQL skips, complete frontend tests/build, dependency audits, and
credential/security scans.
