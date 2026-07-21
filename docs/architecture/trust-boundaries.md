# Trust Boundaries

## Purpose and audience

Security architects and implementers use this catalogue to place authentication, validation, minimization, and audit controls at each crossing.

| Boundary | Primary risks | Required controls |
|---|---|---|
| Browser â†” frontend | XSS, stolen token, malicious extension | CSP, output encoding, dependency hygiene, short sessions, no secrets in client storage |
| Frontend â†” backend | broken access, CSRF, abuse, IDOR | TLS, OIDC/session validation, organization RBAC, CSRF where needed, rate/size limits, correlation IDs |
| Backend â†” database | injection, cross-tenant query, credential theft | parameterized SQLAlchemy, scoped repositories, constraints, least-privilege DB role, TLS/encryption |
| API â†” worker/queue | forged/replayed/flooded jobs | private authenticated channel, minimal messages, idempotency, leases, reauthorization, quotas |
| CloudFix AWS â†” customer AWS | confused deputy, role excess, credential leakage | exact principal, external ID, STS, least privilege, CloudTrail, separate scan/remediation roles |
| Application â†” AI provider | prompt injection, sensitive disclosure, untrusted output | minimization/redaction, provider policy, timeout/budget, schema validation, sanitization, audit metadata |
| Application â†” Jira | token theft, webhook forgery, data oversharing | scoped OAuth/token secret, allowlisted fields, signature verification, replay protection |
| Application â†” email/Teams | notification abuse, leakage, forged callback | destination authorization, templates, throttling, secret store, safe links, audit |
| Remediation â†” customer resources | unintended mutation, duplicate action, compromise | approved playbook/version, separation of duties, action-specific IAM, idempotency, preconditions, verification |

## Administrative boundary

Platform administration crosses all tenant boundaries and therefore requires separate identity, MFA readiness, just-in-time access where feasible, two-person review for sensitive operations, and immutable audit evidence. Exact vendors and network topology are proposals for later stages.
