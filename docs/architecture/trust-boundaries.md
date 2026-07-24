# Trust Boundaries

## Stage 4 clarification

Boto3 and temporary credentials remain inside trusted discovery services. Persisted normalized
metadata crosses into deterministic evaluation only after bounding and redaction. Rules cannot
call AWS, the network, or the filesystem. Findings/evaluations remain tenant scoped. Browser
evidence is escaped text. Structured logs and audit events exclude credentials, tokens, full
policies, and raw provider exceptions.

## Stage 5 compliance boundary

Compliance begins after Stage 4 persistence. It performs no AWS or network calls and cannot
mutate customer resources. Tenant-scoped queries and composite foreign keys govern evaluations,
summaries, findings, accounts, assessments, and snapshots. Only authenticated bounded API
responses cross into the browser. Operational logs contain bounded identifiers and counters;
durable audit events record accepted assessment lifecycle transitions without raw evidence.

## Purpose and audience

Security architects and implementers use this catalogue to place authentication, validation, minimization, and audit controls at each crossing.

| Boundary                         | Primary risks                                            | Required controls                                                                                                   |
| -------------------------------- | -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Browser ↔ frontend               | XSS, stolen token, malicious extension                   | CSP, output encoding, dependency hygiene, short sessions, no secrets in client storage                              |
| Frontend ↔ backend               | broken access, CSRF, abuse, IDOR                         | TLS, local JWT/session validation, organization RBAC, CSRF defenses where needed, rate/size limits, correlation IDs |
| Backend ↔ database               | injection, cross-tenant query, credential theft          | parameterized SQLAlchemy, scoped repositories, constraints, least-privilege DB role, TLS/encryption                 |
| API ↔ worker/queue               | forged/replayed/flooded jobs                             | private authenticated channel, minimal messages, idempotency, leases, reauthorization, quotas                       |
| CloudOps AWS ↔ customer AWS      | confused deputy, role excess, credential leakage         | exact principal, external ID, STS, least privilege, CloudTrail, separate scan/remediation roles                     |
| Application ↔ AI provider        | prompt injection, sensitive disclosure, untrusted output | minimization/redaction, provider policy, timeout/budget, schema validation, sanitization, audit metadata            |
| Application ↔ Jira               | token theft, webhook forgery, data oversharing           | scoped OAuth/token secret, allowlisted fields, signature verification, replay protection                            |
| Application ↔ email/Teams        | notification abuse, leakage, forged callback             | destination authorization, templates, throttling, secret store, safe links, audit                                   |
| Remediation ↔ customer resources | unintended mutation, duplicate action, compromise        | approved playbook/version, separation of duties, action-specific IAM, idempotency, preconditions, verification      |

## Administrative boundary

Platform administration crosses all tenant boundaries and therefore requires separate identity, MFA readiness, just-in-time access where feasible, two-person review for sensitive operations, and durable audit evidence. Exact vendors and network topology are proposals for later stages.

## Stage 6 scoring boundary

The risk engine is inside the trusted application boundary but has no AWS, network, filesystem,
plugin, or dynamic-code capability. Its inputs are persisted tenant-scoped findings and bounded
operator context. PostgreSQL is authoritative for identity, tenant relationships, concurrency,
bounded score state, historical immutability, and immutable snapshots. The browser receives
sanitized numeric components and reason codes, never credentials or unbounded provider
documents. Authorized context and compensating-control
changes cross a user-input boundary and require capability checks, bounded schemas, tenant
predicates, optimistic versions or row locks, reasons, and durable audit events. Stage 7 AI is
outside the implemented boundary and must not be represented as active.
