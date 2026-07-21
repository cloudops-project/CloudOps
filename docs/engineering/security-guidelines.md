# Secure Engineering Guidelines

## Purpose and audience

All contributors use these mandatory controls alongside the [threat model](../architecture/threat-model.md).

Authenticate with an OIDC-compatible design and retain MFA readiness. Authorize server-side with RBAC, active membership, organization scope, deny-by-default, and separation of duties. Use short sessions, secure cookies where applicable, CSRF defenses for cookie writes, explicit Pydantic allowlists, parameterized ORM operations, output encoding/CSP, safe redirect/outbound allowlists, and no arbitrary server-side URL fetches.

Bound request size, rate, concurrency, scan frequency, queue depth, retries, and provider cost. Use idempotency keys, leases, replay windows, and optimistic locks. WAF/CDN controls can help but cannot alone prevent DDoS; architecture, quotas, provider protections, monitoring, runbooks, and budget limits form layered defense.

AWS connections use exact principals, external IDs, STS temporary credentials, least-privilege read-only scan roles, and separate action-specific remediation permissions. No customer keys enter the portal. Store application/integration secrets in Secrets Manager or equivalent; encrypt transit/storage and redact logs.

Sensitive operations emit audit events to a tamper-evident/immutable archive design. Add dependency, secret, static, dynamic, and authorized manual penetration testing in later stages. Review backups, CI identities/secrets, incident response, security headers, alerts, and restore tests before UAT. Never log credentials, tokens, full policies, unnecessary tags, or AI payloads.

Any security exception requires documented owner, rationale, compensating controls, expiry, and designated approval.
