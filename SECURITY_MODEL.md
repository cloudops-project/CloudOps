# CloudOps Security Model

> How CloudOps authenticates users, isolates tenants, reaches customer AWS accounts, handles secrets,
> and constrains remediation — plus which of those controls are relaxed for the demo and what
> production additionally requires.
>
> Threat scenarios and residual risk: `docs/architecture/threat-model.md` (to be consolidated into
> `THREAT_MODEL.md`). Detailed supporting documents: `docs/architecture/trust-boundaries.md`,
> `docs/architecture/multi-tenant-design.md`, `docs/engineering/security-guidelines.md`,
> `docs/security/notification-delivery-controls.md`, `docs/operations/secrets-management.md`,
> `docs/security/phase-1-production-hardening.md`.

## Authentication

**Passwords** are hashed with Argon2. Registration and login responses avoid account enumeration.

**Access tokens** are short-lived signed JWTs. The algorithm is allowlisted, and signature, expiry,
type and subject claims are all validated. The browser holds the access token **in module memory
only** — neither `localStorage` nor `sessionStorage` is used, so a page reload deliberately loses it
and the session is restored from the refresh cookie.

**Refresh tokens** are opaque random values delivered in an `HttpOnly` cookie scoped to
`/api/v1/auth`. Only a SHA-256 hash is persisted. Rotation locks the stored session, issues a
replacement, links it, and revokes the old one. **Reuse of a rotated token revokes the whole token
family.** Logout revokes the verified session; a password change revokes all refresh sessions.

**CSRF.** The two cookie-authenticated POST routes (`/auth/refresh`, `/auth/logout`) reject a request
whose `Origin` is present but not allowlisted. Origin-less non-browser clients remain supported. See
"Demo exceptions" for the same-origin allowance.

**Rate limiting** guards registration, login and refresh, plus per-user limits on cost-bearing
operations (password change, invitation acceptance, discovery, evaluation, AI, notification delivery,
remediation execution, run-now, audit export). This is **process-local** and is defence in depth only
— a shared backend is required before running multiple API replicas.

## Application roles

Membership lives in `organization_members` and is evaluated by a **central capability map**; there is
one authorization decision point, not per-route logic. Six roles:

| Role | Scope of authority |
| --- | --- |
| `owner` | Full organization governance, including owner governance |
| `admin` | Manage members and onboarding, but cannot assign owner or govern an existing owner |
| `security_analyst` | Run evaluations, suppress findings, approve notifications and remediation |
| `cloud_engineer` | Run discovery/evaluations, propose and cancel remediation |
| `auditor` | Read organization, audit and posture data |
| `viewer` | Limited read-only |

Invariants: admins cannot assign owner or govern an existing owner; the **final active owner cannot
be demoted, suspended or removed** (enforced with PostgreSQL row locks under concurrency); suspended
and removed members are denied; **platform-administrator status never implicitly bypasses tenant
checks**.

The backend is authoritative. Hidden or disabled frontend controls are a usability aid and **never** a
security boundary.

## Tenant isolation

Every organization-owned lookup either includes an explicit organization predicate or derives scope
through an authorized membership/account relation. Cross-tenant detail lookups return
**non-disclosing** not-found responses rather than revealing existence.

The database enforces this independently of application code:

- Composite foreign keys make asset, discovery-job, finding, remediation, schedule and scan-run rows
  agree with their owning account **and** organization.
- Composite candidate keys such as `aws_accounts(id, organization_id)` make the tenant column part of
  the referenced key.
- Partial unique indexes enforce single-active invariants (one pending/running discovery job,
  evaluation, or scan run per account; one active remediation request per finding).
- Finalized evaluation summaries and compliance snapshots are immutable.

PostgreSQL row-level security is **not** enabled; it remains deferred defence in depth because the
session architecture does not yet set a complete transaction-scoped tenant context.

## AWS IAM cross-account onboarding

CloudOps never accepts, stores, or requests long-lived customer access keys.

1. The customer creates a **read-only IAM role** in their own AWS account.
2. That role's trust policy names the CloudOps principal and requires a **per-account External ID**
   issued by CloudOps.
3. CloudOps validates the connection with STS `AssumeRole` followed by `GetCallerIdentity`.
4. Discovery uses the returned **temporary credentials in memory only**; they are never persisted,
   logged, returned in responses, or written to audit metadata.

**External IDs** are generated with secure randomness, are globally unique, and are **permanently
reserved** — they are retained even after an account is deleted and are never reissued, so a stale
trust policy cannot be replayed against a different tenant.

Discovery uses only read/list/get/describe operations. Deterministic rules never call boto3. AWS SDK
connect/read timeouts and retry counts are explicit and bounded. IAM group tag operations are
prohibited by regression test, because AWS does not support them and attempting them degrades a scan.

## Application roles versus AWS IAM roles

These are different things and are deliberately never conflated:

| | CloudOps application role | AWS IAM onboarding role |
| --- | --- | --- |
| Created by | CloudOps, per membership | The **customer**, in their own AWS account |
| Stored in | `organization_members` | The customer's AWS IAM |
| Grants | In-app permissions in one organization | Read-only access to that AWS account |
| Requires | An invitation and login | A trust policy naming the CloudOps principal + External ID |
| Credentials | Session JWT + refresh cookie | STS temporary credentials, in memory only |

**Inviting somebody to CloudOps grants them no AWS access whatsoever.** Changing an application role
never alters AWS trust, and changing an AWS trust policy never alters application permissions. See
[DECISIONS.md](DECISIONS.md) ADR-D08.

## Secrets

Sensitive settings are typed `SecretStr` (database URL, JWT signing keys, SMTP password, AI provider
key, Slack/Teams webhook URLs, notification provider key), so accidental logging or `repr()` renders
`**********`. The **only** sanctioned reveal points are explicit properties such as `database_dsn` —
which exists precisely because passing a `SecretStr` to SQLAlchemy's `make_url` raises
`Expected string or URL object, got SecretStr('**********')`.

Rules: never commit real secrets or `.env`; never log plaintext passwords, raw refresh or invitation
tokens, authorization or cookie headers, or AWS credentials; production secrets are injected by
infrastructure, with Pydantic Settings as the single configuration boundary. `.env.example` carries
**names and comments only**.

The durable audit writer applies central redaction, so credential-shaped metadata and user-agent text
cannot be stored verbatim.

## Cookies and transport

| Setting | Demo | Production requirement |
| --- | --- | --- |
| `COOKIE_SECURE` | `false` | **`true`** — validated at startup |
| `COOKIE_SAMESITE` | `lax` | `lax` or stricter; `none` requires `secure` |
| `HSTS_ENABLED` | `false` | `true` only when HTTPS is guaranteed by deployment |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | Real browser-facing origin, **HTTPS**, never `*` |
| `TRUSTED_HOSTS` | `localhost,127.0.0.1,api,testserver` | Real hostnames, never `*` |

Settings validation refuses production-like environments that set static AWS credentials, leave
`COOKIE_SECURE` false, use non-HTTPS CORS origins, enable HSTS without the secure-cookie guarantee, or
configure SMTP without STARTTLS/implicit TLS.

Security headers are applied in code: `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
a strict `Content-Security-Policy` (`default-src 'none'; frame-ancestors 'none'`),
`X-Frame-Options: DENY`, a restrictive `Permissions-Policy`, and `Cache-Control: no-store` on auth
paths. TLS termination, WAF and CDN headers remain deployment responsibilities.

## Demo exceptions (HTTP and ephemeral hostnames)

## Named-tunnel self-hosting

Organization-managed self-hosting uses a named Cloudflare Tunnel as its only public ingress.
`cloudflared` shares a dedicated network only with Nginx; FastAPI and PostgreSQL publish no host
ports. Exact HTTPS origins and trusted hosts remain enabled. Tunnel/application/database secrets
live in Git-ignored host files and are mounted as Docker file secrets. Host hardening, tunnel
policy, off-host backup custody, and edge controls remain operator responsibilities.

The demo deliberately relaxes transport, and **only** transport:

- Plain HTTP locally; `COOKIE_SECURE=false`; HSTS off.
- Public access via a Cloudflare Quick Tunnel. TLS terminates at Cloudflare's edge; the hop from
  `cloudflared` to Nginx is plain HTTP inside the Compose network.
- `TRUST_FORWARDED_HOST_SAME_ORIGIN=true` lets the API accept an `Origin` that **exactly equals** the
  proxy-reported browser-facing origin (`X-Forwarded-Host` + `X-Forwarded-Proto`) on the two
  cookie-authenticated POST routes. That is genuinely same-origin, so it is not a CSRF vector, and it
  means the random tunnel hostname never has to be added to CORS or trusted hosts.

What is **not** relaxed: no wildcard CORS origin; no wildcard trusted host; host validation stays on
(the API always sees `Host: api`); authentication stays on; there is no shared or automatic login; no
credentials appear in URLs; a mismatched Origin, mismatched scheme, or missing forwarded host is still
rejected with 403. Both demo flags are **refused outright** when `APP_ENV` is `staging` or
`production`, and both default to off.

Mailpit is intentionally not exposed through the tunnel, because an open mail UI would disclose
invitation tokens.

Consequences to state plainly: the tunnel URL is random, changes on restart, has no uptime guarantee,
and is unsuitable for sensitive data. Anyone holding it can reach the login page — they still need
valid credentials, but treat the URL as semi-public.

## Dry-run remediation controls

Remediation is the highest-blast-radius capability, so it is constrained at five independent layers:

1. **Allowlist** — only actions in the remediation action registry can be proposed.
2. **Determinism** — proposal text is generated from the existing rule registry; no new detection
   logic, and AI never authorizes a remediation.
3. **Approval gate** — every protected transition (propose, approve, reject, cancel, execute) requires
   a capability-gated authenticated actor. Proposal never self-approves.
4. **Kill switches** — `execute()` refuses unless `REMEDIATION_EXECUTION_ENABLED` is on, and refuses
   outright if `REMEDIATION_LIVE_AWS_ENABLED` is set. Execution is **disabled by default**.
5. **Mode restriction** — only `execution_mode == mock_automation` is executable, with
   `dry_run = true`. A deterministic mock executor runs; **no code path mutates customer AWS.**

Integrity: the approved snapshot hash is recompared immediately before execution, so any change to the
request after approval invalidates it. Attempts are bounded (three) with a terminal failed state. The
UI shows a **Dry run** badge so the safe state is visible rather than implied.

## Audit evidence

Four things are deliberately distinct and must not be conflated:

- **Application logs** — bounded structured operational logs with correlation IDs. Not a security
  record.
- **`audit_events`** — the durable, queryable, exportable record of accepted user-visible lifecycle
  transitions inside CloudOps: who did what, to what, with what result. `record_audit()` is the sole
  write path; the Stage 12 query/export layer is read-only.
- **AWS CloudTrail** — the customer's own AWS API history. CloudOps does **not** ingest it; discovery
  only reads trail *configuration*.
- **AWS CloudWatch** — likewise, alarm and log-group *configuration* metadata only, never log content.

Audit records exclude passwords, hashes, raw tokens, authorization and cookie headers, AWS
credentials, full policies, and unbounded evidence. Notification delivery evidence stores a masked
destination count, template version, content hash and provider message identifier — **not** the body.

Audit rows are **durable but not described as absolutely immutable**; retention, tamper-evident
storage and SIEM forwarding are deployment controls, not code guarantees.

## Production security requirements

Not satisfied today. All of these are prerequisites for a production release:

- TLS termination and redirect; HSTS with an explicit HTTPS guarantee; frontend/CDN security headers.
- Real `CORS_ALLOWED_ORIGINS` and `TRUSTED_HOSTS`; both demo flags off (they are refused anyway).
- WAF/bot controls and **distributed** rate limiting to replace the process-local limiter.
- Managed secrets with rotation, workload identity (ECS/Fargate task roles), GitHub OIDC for
  deployment, and KMS-backed encryption where required.
- PostgreSQL row-level security once a complete transaction-scoped tenant context exists.
- Encrypted backups with a **rehearsed** restore, plus tested rollback — neither has been performed.
- Centralized logs, SIEM integration, tamper-evident audit storage, alarm routing, on-call.
- Live provider validation for Bedrock and SES, including SES sender verification, sandbox exit and
  bounce/complaint handling — none of which has ever run.
- Pin GitHub Actions to immutable commit SHAs rather than mutable release tags.

Current status of these items is tracked in [KNOWN_ISSUES.md](KNOWN_ISSUES.md) (INFRA-01,
PROVIDER-01, AUDIT-01).
