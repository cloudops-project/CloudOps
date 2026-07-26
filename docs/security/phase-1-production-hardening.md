# Phase 1 — Production Security Hardening

## Executive summary

CloudOps has a sound application-security foundation: Argon2 password hashing, short-lived
allowlisted JWTs, opaque hashed refresh sessions with rotation and PostgreSQL row locking,
database-backed organization membership and RBAC, tenant predicates and composite tenant
constraints, temporary STS credentials, deterministic persisted-evidence rules, advisory AI,
approval-gated notification delivery, and simulated-only V1 remediation.

Phase 1 confirmed and fixed five application gaps:

1. CORS configuration accepted an out-of-range port and did not prohibit insecure production
   origins.
2. API HSTS was enabled from `APP_ENV=production` without an explicit HTTPS deployment
   guarantee.
3. Several abuse-sensitive operations lacked a per-user safeguard, rate-limit responses did not
   provide reliable retry metadata, and a test-configured limiter could remain relaxed if reused
   with production settings in the same process.
4. Durable audit metadata and user-agent fields accepted token- and credential-shaped text
   verbatim.
5. AI option keys and scalar values were count-bounded but not size/range-bounded.

The pre-existing Phase 1 working tree also added API security headers, cookie-origin checks,
CSV formula neutralization, AWS/audit-export limits, final-owner regression coverage, and the IAM
group-tag discovery repair. No release-blocking code-level vulnerability is known after
verification. Production release still depends on the infrastructure controls listed below.

## Threat model

### Assets

- User identities, password hashes, memberships, roles, invitations, and session records.
- Tenant-owned AWS accounts, assets, jobs, findings, compliance/risk snapshots, AI requests,
  notifications, remediation requests, schedules, runs, and audit events.
- Access JWTs, raw browser refresh cookies, persisted refresh hashes, invitation tokens, External
  IDs, and temporary STS credentials.
- Deterministic security evidence and audit history.

### Trust boundaries

- Browser to API: bearer access token plus cookie-authenticated refresh/logout.
- API to PostgreSQL: authoritative identity, membership, tenant, workflow, and audit state.
- CloudOps to customer AWS: External ID and STS AssumeRole into a customer role.
- API to AI and notification providers: sanitized bounded context and approved delivery.
- Scheduler to API/database: local V1 process boundary, not a distributed worker boundary.

### Threat actors and abuse cases

- Unauthenticated credential attackers: login/registration/refresh abuse and token replay.
- Cross-tenant authenticated users: UUID probing and nested-resource substitution.
- Malicious members: role escalation, final-owner removal, unauthorized approve/deliver/execute,
  oversized inputs, and CSV/XSS payloads.
- Compromised integrations: credential-bearing provider failures or hostile evidence/AI output.
- Misconfigured operators: insecure CORS/cookies/HSTS, plaintext registries, or reliance on
  process-local controls after horizontal scaling.

### Existing controls and residual risks

- Existing controls include Argon2, typed/required JWT claims, opaque token hashing/rotation,
  origin checks on cookie-authenticated mutations, centralized database RBAC, tenant predicates,
  composite tenant foreign keys, bounded pagination, Pydantic `extra="forbid"`, ORM-bound SQL,
  React escaping, evidence/provider sanitizers, AWS client timeouts/retries, and offline rules.
- PostgreSQL RLS remains future defense in depth because the current session architecture does
  not set a complete transaction-scoped tenant context.
- Process-local limiting is defense in depth only; a shared distributed limiter is required
  before multiple API replicas.
- TLS, static-host headers, WAF, managed secrets, workload identity, encryption/backup controls,
  centralized/tamper-evident logging, SIEM, distributed workers, and alerting remain deployment
  responsibilities.

## Findings

| ID | Severity | OWASP | Component | Exploitation scenario and evidence | Existing control | Verified gap | Fix and regression | Residual risk |
|---|---|---|---|---|---|---|---|---|
| P1-01 | Medium | A05 Security Misconfiguration | CORS settings | `http://localhost:99999` passed the regex; production accepted `http://app.example.com`. | Credentialed CORS used an explicit origin list. | Origin grammar and production scheme were incomplete. | Parse scheme/host/port, reject userinfo/path/query/fragment/wildcards/invalid DNS and ports, require HTTPS in production; `test_cors_allowed_origins_rejects_wildcard_and_malformed_values`. | Reverse proxy and browser-facing host configuration remain deployment-owned. |
| P1-02 | Low | A05 Security Misconfiguration | Security headers | `APP_ENV=production` alone emitted HSTS even if the request reached the app over HTTP. | Production required secure cookies. | Secure cookies do not prove HTTPS termination. | Add explicit `HSTS_ENABLED`, validate production/secure-cookie prerequisites, and gate middleware only on that guarantee; environment-aware header tests. | TLS termination and preload decisions remain infrastructure responsibilities. |
| P1-03 | Medium | A04 Insecure Design | Rate limiting | Cost-bearing operations could be repeatedly invoked; 429 errors lacked retry metadata; a testing limiter instance could remain relaxed if reused with production settings. | Auth middleware plus AWS validation/audit-export limits were process-local. | Coverage and limiter state/retry behavior were incomplete. | Raise typed rate-limit errors with bounded `Retry-After`, isolate limiters by effective configuration, and guard password change, invitation acceptance, discovery/evaluation, AI, notification delivery, remediation execution, and run-now; unit/integration rate-limit tests. | A shared backend is mandatory for multi-replica enforcement. |
| P1-04 | Medium | A09 Logging and Monitoring Failures | Durable audit writer | Credential-shaped metadata or user-agent text was stored verbatim in `audit_events`. | Operational JSON logs excluded headers and exception bodies; provider/discovery sanitizers existed. | The single durable audit writer lacked central redaction. | Reuse bounded sanitizer/redactor in `record_audit`; `test_audit_writer_redacts_sentinel_secrets`. | Audit storage immutability, retention, and SIEM forwarding are deployment controls. |
| P1-05 | Low | A04 Insecure Design | AI request validation | Ten option entries were allowed, but a key/value or integer could be arbitrarily large before hashing/provider context construction. | Option count and source count were bounded. | Scalar sizes/ranges were not bounded. | Bound option keys to 64 characters, strings to 500, and integers to ±1,000,000; parameterized regression test. | Provider-side quotas and timeouts remain necessary. |
| P1-06 | Medium | A03 Injection | Audit CSV export | Untrusted event/resource strings beginning with `=`, `+`, `-`, `@`, tab, or carriage return could execute as spreadsheet formulas. | CSV quoting only. | Quoting does not neutralize formulas. | Prefix formula-triggering values before CSV serialization; `test_export_escapes_formula_injection_prefixes`. | Consumers can still choose unsafe import settings; exported untrusted columns are neutralized. |
| P1-07 | Low | A04 Insecure Design | IAM discovery | IAM group discovery attempted the nonexistent `list_group_tags` API and could fail a scan. | Per-service error classification. | Invalid AWS operation impaired availability. | Never request group tags; assert only user, role, and policy tag operations occur. | AWS permissions and service throttling remain external. |

## Observation classification

| Observation | Classification | Outcome |
|---|---|---|
| Argon2 salts and password bounds | Already protected | Unique-salt regression added; no code change. |
| JWT algorithm/signature/expiry/type/subject/JTI validation | Already protected | Negative and algorithm-confusion regressions added. |
| Refresh randomness, hash-only persistence, rotation, replay family revocation, logout/password revocation | Already protected | SQLite and PostgreSQL concurrency/replay tests retained. |
| Refresh/logout CSRF | Already protected | Exact allowed-origin enforcement for browser requests; Origin-less non-browser clients remain supported. |
| Backend-authoritative RBAC and tenant predicates | Already protected | Route/service review and two-tenant tests retained. |
| Platform administrator tenant bypass | Not applicable | Platform-admin dependency exists but no tenant route silently bypasses membership. |
| Raw SQL/command/path/SSRF injection | Already protected / not applicable | SQL text uses bound parameters or static DDL expressions; no user-controlled subprocess, file path, or outbound URL was found. |
| Frontend token storage and XSS | Already protected | Access token remains module memory-only; React renders text; hostile-shape rendering tests pass. |
| PostgreSQL RLS | Defense in depth | Deferred until transaction-scoped tenant context can be complete. |
| IAM-user trusted principal | Defense in depth | Supported configuration preserved; workload roles are the production recommendation. |
| HSTS/TLS at frontend/CDN | Infrastructure responsibility | API code only exposes an explicit HSTS switch. |

## Route authorization matrix

All paths below are prefixed by `/api/v1` unless shown otherwise. `OrgService` means active
database membership plus centralized capability evaluation; resource lookups additionally include
an organization predicate or are protected by a composite tenant constraint.

| Method | Route | Authentication / capability | Tenant scope | Representative test evidence |
|---|---|---|---|---|
| GET | `/health`, `/ready` | Public | None; readiness checks DB only | `test_health_and_readiness` |
| POST | `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout` | Public or refresh cookie; auth rate limit; origin check on refresh/logout | User/session | `test_registration_duplicate_login_and_safe_response`, refresh/replay/origin tests |
| GET | `/auth/me` | Active user | Membership list from DB | auth restoration and disabled-user tests |
| POST | `/auth/change-password` | Active user; per-user limit | User and all active refresh sessions | password-change revocation tests |
| POST/GET | `/organizations` | Active user | Created/listed memberships only | organization lifecycle tests |
| GET/PATCH | `/organizations/{organization_id}` | `organization.read` / `organization.update` | OrgService | tenant/RBAC tests |
| GET | `/organizations/{organization_id}/members` | `members.read` | OrgService | six-role/member tests |
| PATCH/DELETE | `/organizations/{organization_id}/members/{membership_id}/role`, `/status`, and member delete | `members.manage` plus owner governance | Parent and membership organization must match | admin-owner and final-owner tests, PostgreSQL owner races |
| POST/GET/DELETE | `/organizations/{organization_id}/invitations[/{invitation_id}]` | `invitations.manage` | OrgService and scoped invitation lookup | invitation lifecycle/tenant tests |
| POST | `/invitations/accept` | Active user; per-user limit | Hashed invitation token binds target org/email | expiry, cancellation, concurrent acceptance tests |
| GET | `/organizations/{organization_id}/audit-events` | `audit.read` | OrgService | organization audit tests |
| POST/GET | `/aws/accounts`, `/aws/accounts/{account_id}` | `aws_accounts.manage` / `aws_accounts.read` | Account organization and OrgService | `test_tenant_isolation_and_rbac` |
| PATCH/DELETE | `/aws/accounts/{account_id}` | `aws_accounts.manage` | Scoped account | onboarding lifecycle tests |
| POST | `/aws/accounts/{account_id}/validate`, `/disconnect` | `aws_accounts.manage`; validate is per-user limited | Scoped account and lifecycle lock | STS, redaction, concurrency tests |
| POST | `/aws/accounts/{account_id}/discover` | `discovery.start`; per-user limit | Account organization | discovery RBAC/two-tenant/concurrency tests |
| GET | `/discovery/jobs`, `/discovery/jobs/{job_id}` | `assets.read` | Organization predicate | discovery repair tests |
| GET | `/assets`, `/assets/summary`, `/assets/{asset_id}` | `assets.read` | Organization predicate | cross-tenant asset probes |
| GET | `/rules`, `/rules/{rule_key}` | `rules.read` | Membership-gated global deterministic catalog | rule API RBAC tests |
| POST | `/aws/accounts/{account_id}/evaluate` | `evaluations.start`; per-user limit | Account organization | evaluation RBAC/concurrency tests |
| GET | `/evaluations`, `/evaluations/{evaluation_id}` | `findings.read` | Organization predicate | finding API tests |
| GET | `/findings`, `/findings/summary`, `/findings/{finding_id}` | `findings.read` | Organization predicate | finding tenant/RBAC tests |
| POST | `/findings/{finding_id}/suppress`, `/unsuppress` | `findings.suppress` | Organization and finding predicates | suppression/RBAC/race tests |
| GET | `/compliance/frameworks[/{framework_key}]`, framework controls | `compliance.read` | Membership-gated catalog | compliance catalog tests |
| POST | `/aws/accounts/{account_id}/compliance/assess` | `compliance.assess` | Account organization | compliance tenant/evidence tests |
| GET | `/compliance/assessments[...]`, controls, summary, findings | `compliance.read` | Organization predicates and immutable scoped snapshots | compliance tenant and PostgreSQL constraint tests |
| GET/POST | `/risk/policies`, `/risk/assess` | `risk.read` / `risk.assess` | Organization and optional scoped account | risk RBAC/cross-tenant tests |
| GET | `/risk/assessments[...]`, `/risk/summary`, `/risk/findings[...]`, account/asset risk | `risk.read` | Organization predicates | risk tenant and snapshot tests |
| GET/PUT | `/risk/context` | `risk.read` / `risk.context.manage` | Organization/account/asset consistency | risk context tests |
| POST/DELETE | `/risk/findings/{finding_id}/compensating-controls`, `/risk/compensating-controls/{control_id}` | `risk.controls.manage` | Organization predicates | risk control tests |
| POST/GET | `/ai/generate`, `/ai/requests[...]` | `ai.generate` / `ai.read`; all AI POSTs per-user limited | Organization plus typed source tenant validation | six-role, source probing, request detail tests |
| POST | finding/risk/compliance `/ai/*` shortcuts | `ai.generate`; per-user limit | Source and payload organization must match | shortcut and cross-tenant source tests |
| GET | `/notifications`, `/notifications/{event_id}` | `notifications.read` | Organization predicate | notification tenant tests |
| POST | `/notifications/{event_id}/approve`, `/deliver` | `notifications.approve`; delivery per-user limited | Organization predicate; approval required before delivery | notification RBAC/cross-tenant/provider tests |
| GET/POST | `/remediations`, finding remediation proposal | `remediation.read` / `remediation.request` | Organization/finding predicates | remediation tenant tests |
| POST | remediation approve/reject/cancel/execute | corresponding remediation capability; execute per-user limited | Organization predicate; V1 executor remains simulated | remediation RBAC/state-machine tests |
| POST/GET/DELETE | `/schedules[...]` | `schedule.manage` / `schedule.read` | Organization/account/schedule predicates | scheduler RBAC/tenant tests |
| POST | `/schedules/{schedule_id}/run` | `schedule.manage`; per-user limit | Scoped schedule/account | run-now/overlap tests |
| GET | `/scan-runs`, `/scan-runs/{run_id}` | `schedule.read` | Organization predicate | scheduler API tests |
| GET | `/audit-events`, `/audit-events/export` | `audit.read`; export per-user limited | Organization predicate | audit RBAC/filter/export tests |
| GET | `/summary` | `organization.read` | All aggregates include organization predicates | dashboard two-tenant and six-role tests |

## Frontend review

- Access tokens remain in module memory; neither Web Storage API is used.
- Refresh uses `credentials: "include"` with an HttpOnly cookie and failed refresh clears token,
  profile state, and query cache.
- Logout clears in-memory state even if the API request fails.
- No `dangerouslySetInnerHTML` use was found. Evidence, metadata, AI, notifications, remediation,
  and audit values render through React text escaping; hostile-shape rendering tests pass.
- Navigation targets are application-controlled; no URL-query open redirect was found.
- `VITE_API_BASE_URL` is the only Vite runtime value used and contains no secret.
- Security-sensitive forms use submission state and confirmation dialogs to prevent accidental
  duplicate operations.
- Frontend role visibility is usability only; every protected operation is enforced by the API.

## AWS review

- Request schemas accept account IDs and role ARNs, not customer access keys.
- Account IDs and role ARNs are validated; External IDs use secure randomness, unique
  reservations, and permanent non-reuse constraints.
- Validation performs AssumeRole followed by GetCallerIdentity. Discovery receives temporary
  credentials in memory and does not persist or return credential dictionaries.
- Boto3 clients receive explicit connect/read timeouts and bounded standard/adaptive retries.
- Discovery uses read/list/get/describe APIs; deterministic rules never call Boto3.
- IAM user, role, and policy tags are supported; IAM group tag calls are prohibited by regression.
- IAM-user trusted principals remain supported. A workload role is the production recommendation
  to avoid long-lived CloudOps credentials.
- No automated test contacted a real AWS account.

## Dependency, supply-chain, and secret-scan notes

- Backend `pip check` is clean. `pip-audit --local` reports no known vulnerability; the local
  `cloudops-api` package is not on PyPI and is explicitly skipped.
- Frontend `npm audit` over an explicit HTTPS registry reports zero vulnerabilities.
- The machine-level npm registry is configured with plaintext HTTP. The first audit was rejected
  with HTTP 426; the successful audit used a command-local HTTPS override. This machine setting
  must be corrected outside the repository.
- Node 23 is outside ESLint 10's supported engine range. CI/production builds should use a
  supported Node 20.19+, 22.13+, or 24+ release.
- No executable GitHub Actions workflow exists, so excessive workflow permissions,
  `pull_request_target`, untrusted checkout execution, and mutable action tags are not applicable.
- Redacted Gitleaks source scan found five test-only fixtures/false positives:
  - `apps/api/app/tests/test_security.py:279` — generic API-key sentinel fixture.
  - `apps/api/app/tests/test_security.py:287` — generic AWS-secret sentinel fixture.
  - `apps/api/app/tests/test_stage5_postgres.py:404` — `rule_key` false positive.
  - `apps/api/app/tests/test_stage7_black_box.py:518` — synthetic AWS access-token sentinel.
  - `apps/api/app/tests/test_ai_assistant.py:154` — synthetic JWT fixture.
  No real secret was identified.

## Deferred production controls

- TLS termination and redirects; frontend/static-host CSP, frame, referrer, and permissions headers.
- WAF/bot controls and distributed rate limiting.
- Managed secrets, workload identity, key rotation, and KMS-backed encryption where required.
- Encrypted backups, retention, restore drills, and disaster-recovery objectives.
- Centralized operational logs, SIEM integration, tamper-evident audit storage, and production
  alerting/on-call procedures.
- Distributed queues/workers, scheduler leader election, retries, dead-letter handling, and
  idempotent production job orchestration.
- PostgreSQL RLS after complete transaction-scoped tenant context is available.

## Verification record

Verification completed on 2026-07-26:

- Ruff completed with no findings; strict Mypy reported no issues in 143 source files.
- The full backend suite completed with `510 passed` against disposable PostgreSQL, including
  concurrency/constraint suites and V1 black-box acceptance. Branch-aware application coverage was
  90% (6,396 statements and 1,174 branches). The only warning was Starlette's test-client
  deprecation notice.
- Alembic upgraded a new disposable database from empty through revision
  `0013_demo_notification_delivery`; `current`, `heads`, and `check` confirmed a single current
  head and no new upgrade operations.
- Frontend TypeScript checks, ESLint, all 112 Vitest tests, and the production Vite build passed.
- `pip check` found no broken requirements. `pip-audit --local` found no known vulnerabilities
  (the unpublished local package was not auditable through PyPI).
- `npm audit --registry=https://registry.npmjs.org --audit-level=low` reported zero
  vulnerabilities. The explicit HTTPS registry bypassed the insecure machine-level HTTP registry
  setting noted above.
- Redacted Gitleaks scanning found five reviewed test-only fixtures or false positives and no
  production credential. Generated dependencies, caches, build output, and the untouched
  user-owned `CLAUDE.md` were excluded.
- Final Git whitespace, staged-file, secret-shape, and scope checks are part of the commit
  handoff; `compose.aws.override.yml` remains untouched.
