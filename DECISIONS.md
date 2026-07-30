# CloudOps Decision Record Index

> Lightweight architecture decision records. Numbered `ADR-0xx` records live in
> [docs/architecture/decisions/](docs/architecture/decisions/) and remain authoritative for the
> decisions they cover. `ADR-Dxx` records below capture decisions made during demo hardening that did
> not previously have a written record.
>
> Never rewrite an accepted ADR to reflect a later change — supersede it with a new record so the
> reasoning stays traceable.

## Existing numbered ADRs

Statuses below mirror
[docs/architecture/decisions/README.md](docs/architecture/decisions/README.md). Note that ADR-001
through ADR-006 remain **Proposed** even though the codebase implements them — they document intent
that was never formally accepted, which is itself worth knowing.

| ADR | Decision | Status |
| --- | --- | --- |
| [ADR-001](docs/architecture/decisions/ADR-001-feature-based-monorepo.md) | Feature-based monorepo | Proposed |
| [ADR-002](docs/architecture/decisions/ADR-002-fastapi-backend.md) | FastAPI backend | Proposed |
| [ADR-003](docs/architecture/decisions/ADR-003-postgresql-database.md) | PostgreSQL as the database | Proposed |
| [ADR-004](docs/architecture/decisions/ADR-004-cross-account-iam.md) | Cross-account IAM onboarding | Proposed |
| [ADR-005](docs/architecture/decisions/ADR-005-deterministic-rule-engine.md) | Deterministic rule engine | Proposed |
| [ADR-006](docs/architecture/decisions/ADR-006-ai-assistance-boundary.md) | AI assistance boundary | Proposed |
| [ADR-007](docs/architecture/decisions/ADR-007-stage-1-foundation-authentication.md) | Stage 1 foundation/auth scope | Accepted by implementation authorization |
| [ADR-008](docs/architecture/decisions/ADR-008-stage-1-jwt-authentication.md) | Local JWT + opaque refresh sessions | Accepted; supersedes Stage 0 OIDC |
| [ADR-009](docs/architecture/decisions/ADR-009-tailwind-frontend.md) | Tailwind CSS frontend | Accepted; supersedes Material UI |
| [ADR-010](docs/architecture/decisions/ADR-010-cloudops-product-name.md) | **CloudOps** is the product name | Accepted |
| [ADR-011](docs/architecture/decisions/ADR-011-stage-2-aws-account-onboarding.md) | AWS onboarding is Stage 2 | Accepted by Stage 2 authorization |

## ADR-D01 — Same-origin proxy for the demo

**Status:** Accepted · **Date:** 2026-07-30

**Context.** The demo was served with the SPA on one origin and the API on another, and the frontend
bundle was built against an absolute API URL. Temporary public hostnames change frequently, so every
change produced browser `Failed to fetch` errors and required a rebuild plus a CORS edit.

**Decision.** Serve the SPA and the API from **one origin**. The bundle builds with an empty
`VITE_API_BASE_URL`, so the browser calls relative `/api/v1/...` paths against whatever origin loaded
the page. Nginx proxies `/api/` to `api:8000` with `proxy_pass http://api:8000` — deliberately **no
trailing slash**, which preserves the `/api` prefix. Nginx pins `Host: api` so the API's trusted-host
allowlist is satisfied without knowing the public hostname.

**Alternatives.** Rebuild the bundle per hostname (rejected: slow, error-prone, breaks on restart).
Wildcard CORS (rejected: prohibited by [rules.md](rules.md)). Disable host validation (rejected:
same).

**Consequences.** A new public hostname needs no code edit, rebuild, CORS change or API restart. Only
one port must be exposed. The API always sees `Host: api`, so proxy headers carry the
browser-facing host — see ADR-D06.

## ADR-D02 — Synthetic inventory for the demo

**Status:** Accepted · **Date:** 2026-07-30

**Context.** The demo's connected AWS account is synthetic, so real discovery would attempt STS
`AssumeRole` with placeholder credentials and fail, leaving a failed scan run. Separately, the demo
seed had invented metadata key names that no deterministic rule reads, so 17 rules per evaluation
correctly returned `invalid_or_incomplete_metadata` and the two headline CRITICAL findings never
existed.

**Decision.** Introduce `apps/api/app/services/demo_inventory.py` as the **single source of truth**
for synthetic inventory, using the exact metadata keys the real collectors emit. A new
`DEMO_SYNTHETIC_DISCOVERY` setting swaps in synthetic collectors so `DiscoveryOrchestrator` runs its
genuine normalize/upsert/stale/counter/audit pipeline without assuming any role. The setting is
refused when `APP_ENV` is `staging` or `production`, and the real discovery path is untouched when it
is off.

**Alternatives.** Skip discovery and run evaluation only (rejected: does not exercise the pipeline).
Leave the failure visible (rejected: a failed scan is a poor demo). Fake boto3 clients per service
(rejected: large, brittle, and duplicates the collectors' parsing).

**Consequences.** The seed and the demo rescan produce identical inventory, so drift cannot
reappear silently — a regression test asserts zero rule errors. **Synthetic scans must never be
presented as live AWS scans.**

## ADR-D03 — Cloudflare Quick Tunnel is temporary access only

**Status:** Accepted · **Date:** 2026-07-30

**Context.** Several invited people need to reach one demo instance for two days, without
provisioning cloud infrastructure or handling Cloudflare credentials.

**Decision.** Use a **Quick Tunnel** (`cloudflared tunnel --url http://web:8080`), behind an opt-in
`tunnel` Compose profile. It requires no Cloudflare account, API token, or credential file. Treat the
URL as disposable: random hostname, changes on every restart, dies with the process, no uptime
guarantee.

**Alternatives.** Named Cloudflare Tunnel (rejected for the demo: requires an account, zone and
persistent connector credential — correct for *after* the demo). AWS ALB + ACM (rejected: requires
applying Terraform and a real domain). Port forwarding (rejected: no TLS, router-dependent).

**Consequences.** Documentation must never claim URL persistence or call this a deployment. Stability
requires a named tunnel or the AWS staging hostname — not more application code. Mailpit is
deliberately **not** tunnelled, because an open mail UI would expose invitation tokens.

## ADR-D04 — Dry-run remediation only

**Status:** Accepted · **Date:** carried forward, reaffirmed 2026-07-30

**Context.** Remediation is the highest-blast-radius capability in the product.

**Decision.** Remediation proposals are generated deterministically from the existing rule registry.
Execution is allowlisted, approval-gated, **disabled by default**, and served by a deterministic mock
executor with `dry_run = true` and `execution_mode = mock_automation`. `execute()` refuses any request
that is not `mock_automation`, refuses when the `REMEDIATION_EXECUTION_ENABLED` kill switch is off,
and refuses when `REMEDIATION_LIVE_AWS_ENABLED` is set. The demo enables only the mock switch.

**Consequences.** No code path mutates customer AWS. A live executor is out of V1 scope and needs its
own design, authorization and threat review. The UI now shows a **Dry run** badge so the safe state is
visible rather than implied.

## ADR-D05 — Mailpit instead of live SES for the demo; mock AI instead of live Bedrock

**Status:** Accepted · **Date:** carried forward, reaffirmed 2026-07-30

**Context.** The demo must show notification delivery and AI explanation without external
dependencies, spend, or identity verification.

**Decision.** Notification delivery uses **SMTP to Mailpit**; the AI provider is the deterministic
**mock**. SES and Bedrock adapter code exists and is tested with Botocore `Stubber`, but is never
invoked live.

**Consequences.** No AWS account, verified sender identity, SES production-access request, or Bedrock
model access is needed for the demo. Documentation must not claim live Bedrock or live SES validation.
Delivery evidence, bounce handling and model-access behaviour remain unverified — see
[KNOWN_ISSUES.md](KNOWN_ISSUES.md) PROVIDER-01.

## ADR-D06 — Forwarded-host same-origin allowance for cookie-authenticated routes

**Status:** Accepted · **Date:** 2026-07-30

**Context.** `CookieOriginMiddleware` rejects a present-but-not-allowlisted `Origin` on
`POST /auth/refresh` and `/auth/logout` (CSRF protection). Behind the tunnel, browsers send
`Origin: https://<random>.trycloudflare.com`, so refresh and logout would return 403 and sessions
would break. The only allowlist-based fixes were the two things explicitly prohibited: adding the
ephemeral hostname to CORS, or a wildcard.

**Decision.** Nginx forwards the browser-facing host and scheme as `X-Forwarded-Host` and
`X-Forwarded-Proto`. The middleware additionally accepts an `Origin` that **exactly equals** that
proxy-reported origin — which is genuinely same-origin and therefore not a CSRF vector. Gated by
`TRUST_FORWARDED_HOST_SAME_ORIGIN`, **off by default**, and refused when `APP_ENV` is `staging` or
`production`.

**Alternatives.** Strip `Origin` in Nginx (rejected: silently defeats the CSRF control rather than
correctly recognizing same-origin). Add the hostname to CORS (rejected: breaks on every restart, and
prohibited). Wildcard origin (rejected: prohibited). Trust forwarded headers unconditionally
(rejected: `X-Forwarded-*` is only trustworthy when every request path terminates at a trusted proxy,
and the demo also publishes port 8000 directly).

**Consequences.** With the flag off, behaviour is byte-identical to the allowlist-only check. A
mismatched Origin, mismatched scheme, or missing forwarded host is still 403. An Nginx `map` is
required so Cloudflare's `https` survives the plain-HTTP hop to Nginx. For real deployments,
configure `CORS_ALLOWED_ORIGINS` with the actual browser-facing origin and leave this off.

## ADR-D07 — No Jira integration in current scope

**Status:** Accepted · **Date:** carried forward, reaffirmed 2026-07-30

**Context.** The AI assistant can draft Jira-style descriptions, which invites the assumption that
ticket creation exists.

**Decision.** There is **no** Jira integration. AI Jira output is a **draft string only**; nothing is
transmitted and no ticket is created. No Jira configuration, credential, or endpoint exists.

**Consequences.** Documentation and demos must not imply ticketing. Adding it later requires
credential handling, outbound egress review, and its own threat review.

## ADR-D08 — Application roles are separate from AWS IAM roles

**Status:** Accepted · **Date:** carried forward, made explicit 2026-07-30

**Context.** "Role" is overloaded. Inviting a demo participant looked as though it might grant AWS
access, especially once one URL was shared with several people.

**Decision.** Keep the two concepts explicitly separate everywhere:

- **CloudOps application membership role** — `owner`, `admin`, `security_analyst`, `cloud_engineer`,
  `auditor`, `viewer`. Stored in `organization_members`, evaluated by the central capability map,
  scoped to one organization. Governs only in-app permissions.
- **AWS IAM cross-account onboarding role** — created by the *customer* in *their* AWS account, trusts
  the CloudOps principal, requires a per-account External ID, is assumed with STS temporary
  credentials, and is read-only.

**Consequences.** Inviting somebody to CloudOps grants **zero** AWS access. Documentation, the tunnel
script output and [SECURITY_MODEL.md](SECURITY_MODEL.md) state this explicitly. Changing an
application role never alters AWS trust, and vice versa.
