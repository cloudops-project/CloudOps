# CloudFix Threat Model

## Purpose and audience

Security, architecture, engineering, and operations teams use this initial threat model to prioritize controls and security tests. It is a living model, not a claim that controls are implemented.

## Assets and adversaries

Protect tenant configuration/evidence, identities and sessions, role/external-ID metadata, integration secrets, approval intent, remediation paths, audit integrity, database/backups, and service availability. Adversaries include external attackers, malicious/compromised tenant users, compromised organization or platform administrators, supply-chain actors, and compromised workers/providers.

## Threat/control register

| Threats | Planned controls and validation |
|---|---|
| Multi-tenant leakage, IDOR, broken access, mass assignment | OIDC identity; organization membership/RBAC; deny-by-default services and scoped repositories; response allowlists; negative cross-tenant tests; optional PostgreSQL RLS |
| Compromised org admin / platform admin / insider | MFA readiness, least privilege, separation of duties, time-bound support access, sensitive-action confirmation, independent review, behavioral alerts, immutable audit |
| Stolen session, brute force, CSRF | short-lived sessions, secure HttpOnly/SameSite cookies where applicable, rotation/revocation, OIDC protections, rate limits, CSRF tokens/origin checks for cookie writes |
| XSS, SQL injection, SSRF, malicious uploads | output encoding/CSP, parameterized ORM, Pydantic allowlists, outbound destination allowlists and no arbitrary fetches, strict file type/size scanning or omit uploads in MVP |
| API abuse, rate-limit bypass, DDoS | per-subject/tenant/IP quotas, request-size/concurrency bounds, backpressure, caching, provider protections, monitoring/runbooks; WAF is only one layer and budget/platform limits remain |
| Queue flooding, job replay, duplicate remediation | quotas, authenticated private queue, opaque payloads, idempotency keys, nonces/leases, optimistic locks, reauthorization, deduplication and dead-letter monitoring |
| Confused deputy / permissive IAM / credential exposure | exact CloudFix principal, per-connection external ID, STS temporary credentials, minimal session duration, read-only scan role, separate action-specific remediation role, policy review and CloudTrail |
| Compromised worker | isolated runtime identity/network, no credential persistence, minimal job data, egress controls, patched images, workload limits, secrets manager, rapid revocation |
| Leaked AI key, prompt injection in metadata, AI disclosure | secret store/rotation, treat metadata and output as untrusted, delimit/minimize/redact inputs, never send credentials/full policies, schema validate/sanitize, provider retention review, cost/time limits |
| Jira webhook forgery / email or Teams abuse | signature and timestamp verification, replay cache, scoped integration identity, destination allowlist, content minimization, throttling, delivery audit |
| Audit tampering, backup compromise, sensitive logs | append-only events, hash chaining/export to versioned Object Lock-capable S3 design, separate access, encryption, redaction, restore tests, alerts on gaps; retention approval required |
| Dependency/CI compromise and CI secret exposure | lockfiles later, review, dependency/secret/static scanning, least-privilege ephemeral CI identities/OIDC, protected environments, provenance and update policy |

## Security requirements

Encrypt in transit and at rest; store application/provider secrets in Secrets Manager or equivalent; never log credentials/tokens or unredacted evidence. Use structured audit and operational logs with correlation IDs. Apply security headers, explicit exception mapping, bounded retries, alerting, backup testing, static and dynamic testing, dependency and secret scanning, and authorized manual penetration testing in sandbox/UAT.

## High-risk misuse cases

An attacker tries a valid finding ID from another tenant; the repository's organization predicate returns indistinguishable not-found/forbidden behavior and logs a redacted denial. A malicious S3 tag contains prompt instructions; it is treated as data, minimized/redacted, and cannot alter the structured prompt or call tools. A replayed approval request hits a unique idempotency key and current-version precondition. A compromised administrator cannot silently erase history.

## Residual risks and open questions

No control guarantees complete security. OIDC vendor, MFA enforcement, WAF/CDN/hosting protections, RLS, data residency, archive immutability mode, penetration-test scope, upload exclusion, and incident/recovery objectives require approval. Revisit this model at every architecture boundary or new integration.
