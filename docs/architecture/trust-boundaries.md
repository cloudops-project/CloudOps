# Trust Boundaries

## Stage 4 clarification

Boto3 and temporary credentials remain inside trusted discovery services. Persisted normalized
metadata crosses into deterministic evaluation only after bounding and redaction. Rules cannot
call AWS, the network, or the filesystem. Findings/evaluations remain tenant scoped. Browser
evidence is escaped text. Structured logs and audit events exclude credentials, tokens, full
policies, and raw provider exceptions.

## Purpose and audience

Security architects and implementers use this catalogue to place authentication, validation, minimization, and audit controls at each crossing.

| Boundary | Primary risks | Required controls |
|---|---|---|
| Browser ↔ frontend | XSS, stolen token, malicious extension | CSP, output encoding, dependency hygiene, short sessions, no secrets in client storage |
| Frontend ↔ backend | broken access, CSRF, abuse, IDOR | TLS, local JWT/session validation, organization RBAC, CSRF defenses where needed, rate/size limits, correlation IDs |
| Backend ↔ database | injection, cross-tenant query, credential theft | parameterized SQLAlchemy, scoped repositories, constraints, least-privilege DB role, TLS/encryption |
| API ↔ worker/queue | forged/replayed/flooded jobs | private authenticated channel, minimal messages, idempotency, leases, reauthorization, quotas |
| CloudOps AWS ↔ customer AWS | confused deputy, role excess, credential leakage | exact principal, external ID, STS, least privilege, CloudTrail, separate scan/remediation roles |
| Application ↔ AI provider | prompt injection, sensitive disclosure, untrusted output | minimization/redaction, provider policy, timeout/budget, schema validation, sanitization, audit metadata |
| Application ↔ Jira | token theft, webhook forgery, data oversharing | scoped OAuth/token secret, allowlisted fields, signature verification, replay protection |
| Application ↔ email/Teams | notification abuse, leakage, forged callback | destination authorization, templates, throttling, secret store, safe links, audit |
| Remediation ↔ customer resources | unintended mutation, duplicate action, compromise | approved playbook/version, separation of duties, action-specific IAM, idempotency, preconditions, verification |

## Administrative boundary

Platform administration crosses all tenant boundaries and therefore requires separate identity, MFA readiness, just-in-time access where feasible, two-person review for sensitive operations, and immutable audit evidence. Exact vendors and network topology are proposals for later stages.
