# Secure Engineering Guidelines

## Stage 1 authentication baseline

ADR-008 replaces the Stage 0 OIDC placeholder for Stage 1. Passwords use Argon2 and a 12–128 character policy requiring upper/lowercase, number, and symbol. Login responses are generic and unknown users pass through a dummy password hash.

Access JWTs require `sub`, `type`, `iat`, `exp`, and `jti`, restrict the configured algorithm, and expire within 60 minutes (15 by default). Refresh tokens are high-entropy opaque values in an HttpOnly cookie; `Secure` is mandatory in production and with `SameSite=None`. Only hashes are persisted. Refresh rotation locks the stored session through replacement and commit; replay revokes the family and writes an audit event. Password changes revoke all refresh sessions.

Refresh/logout reject foreign origins. CORS and trusted hosts are environment allowlists. The in-process rate limiter is a Stage 1 abstraction only; distributed production limiting is deferred. Passwords, raw tokens, cookies, authorization headers, and secrets must never enter logs or audit metadata.

Tenant access requires active membership and centralized capabilities. Missing membership is returned as not-found. Admins cannot assign owner or govern an existing owner. Final-owner protection is a separate row-locked invariant. Platform admin is not an implicit tenant bypass.

Raw invitation tokens are returned only in development/testing while delivery is deferred. Production responses omit the field entirely. Invitation acceptance locks the invitation through membership creation and commit.

## Purpose and audience

All contributors use these mandatory controls alongside the [threat model](../architecture/threat-model.md).

Authenticate Stage 1 with the ADR-008 local JWT/opaque-session design while retaining future OIDC and MFA readiness. Authorize server-side with RBAC, active membership, organization scope, deny-by-default, and separation of duties. Use short sessions, secure cookies where applicable, origin/CSRF defenses for cookie writes, explicit Pydantic allowlists, parameterized ORM operations, output encoding/CSP, safe redirect/outbound allowlists, and no arbitrary server-side URL fetches.

Bound request size, rate, concurrency, scan frequency, queue depth, retries, and provider cost. Use idempotency keys, leases, replay windows, and optimistic locks. WAF/CDN controls can help but cannot alone prevent DDoS; architecture, quotas, provider protections, monitoring, runbooks, and budget limits form layered defense.

AWS connections use exact principals, external IDs, STS temporary credentials, least-privilege read-only scan roles, and separate action-specific remediation permissions. No customer keys enter the portal. Store application/integration secrets in Secrets Manager or equivalent; encrypt transit/storage and redact logs.

Sensitive operations emit audit events to a tamper-evident/immutable archive design. Add dependency, secret, static, dynamic, and authorized manual penetration testing in later stages. Review backups, CI identities/secrets, incident response, security headers, alerts, and restore tests before UAT. Never log credentials, tokens, full policies, unnecessary tags, or AI payloads.

Any security exception requires documented owner, rationale, compensating controls, expiry, and designated approval.

## Stage 2 cross-account AWS controls

- Never request, accept, log, or persist AWS access keys, secret keys, or session tokens.
- Generate a cryptographically random external ID per account and permanently reserve every
  issued value in immutable history, including after account deletion.
- Trust policies name the configured CloudOps principal and require the exact external ID.
- Validate role ARN format and ensure its account component matches the registered account.
- Keep AssumeRole credentials in local memory only and immediately call GetCallerIdentity.
- Mark connected only when the returned AWS account ID matches.
- Restrict every AWS account operation to organization owner/admin through centralized RBAC.
- Audit state transitions with safe metadata only. Resource scanning and broader permissions are Stage 3 concerns.
- Serialize lifecycle mutations with PostgreSQL row locks. STS runs outside the lock and an
  operation token prevents an older validation from overwriting a newer update, disconnect, or
  deletion.

## Stage 3 discovery controls

- Only connected, tenant-scoped accounts may be discovered.
- AssumeRole credentials live only inside the current process and are never persisted or logged.
- Collectors inventory resources only; they do not inspect posture, policy documents, ACLs,
  encryption, privilege, compliance, vulnerabilities, risk, or remediation.
- Metadata normalization drops credential-, token-, password-, and authorization-like keys;
  provider exceptions become stable sanitized codes.
- Bounded API pagination prevents unbounded output. PostgreSQL locking and a partial unique
  index prevent overlapping jobs.
- Per-service transaction boundaries ensure a failed collector cannot stale its prior assets.
- Composite account/organization foreign keys enforce tenant consistency in PostgreSQL.
- Every boto3 client uses explicit bounded connect/read timeouts and bounded standard/adaptive
  retries configured from the environment.

## Stage 5 compliance controls

- Stage 4 remains the sole detection source; compliance never calls boto3 or evaluates live AWS.
- PASS requires affirmative complete per-rule evidence. Missing or mismatched evidence is
  NOT_ASSESSED, and mapped rule errors are ERROR.
- Active and suppressed mapped findings remain FAIL; suppression never implies compliance.
- Composite tenant/framework foreign keys, partial indexes, row locking, and immutable snapshot
  triggers are mandatory PostgreSQL controls.
- Catalog text is a short CloudOps-authored summary with official references. Initial mappings
  require human compliance review and do not constitute certification.
- Frontend query keys include organization scope, logout clears protected cached data, and all
  descriptions/evidence render as escaped text without unsafe HTML.
