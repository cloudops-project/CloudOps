# CloudOps Threat Model

> See [THREAT_MODEL.md](../../../THREAT_MODEL.md) at the repository root for the demo-specific
> addition (the forwarded-host same-origin trust boundary). This document remains authoritative
> for the general product threat register below.

## Purpose and audience

Security, architecture, engineering, and operations teams use this initial threat model to prioritize controls and security tests. It is a living model, not a claim that controls are implemented.

## Stage 5 compliance trust considerations

Compliance accepts only tenant-scoped persisted Stage 4 evaluations, per-rule summaries, and
findings. Composite database relationships prevent assessments and snapshots from referencing
another tenant or framework. Missing, legacy, malformed, or version-mismatched evidence cannot
establish PASS. Catalog descriptions are bounded CloudOps summaries with official references,
not official framework prose or certification. Frontend content is escaped React text; raw
policies, provider errors, tokens, and credentials are excluded.

## Assets and adversaries

Protect tenant configuration/evidence, identities and sessions, role/external-ID metadata, integration secrets, approval intent, remediation paths, audit integrity, database/backups, and service availability. Adversaries include external attackers, malicious/compromised tenant users, compromised organization or platform administrators, supply-chain actors, and compromised workers/providers.

## Threat/control register

| Threats                                                    | Planned controls and validation                                                                                                                                                                            |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Multi-tenant leakage, IDOR, broken access, mass assignment | Stage 1 local JWT identity; organization membership/RBAC; deny-by-default services and scoped repositories; response allowlists; negative cross-tenant tests; optional PostgreSQL RLS; future OIDC adapter |
| Compromised org admin / platform admin / insider           | MFA readiness, least privilege, separation of duties, time-bound support access, sensitive-action confirmation, independent review, behavioral alerts, immutable audit                                     |
| Stolen session, brute force, CSRF                          | short-lived access JWTs, secure HttpOnly/SameSite refresh cookies, row-locked rotation/revocation, rate limits, and origin checks for cookie writes                                                        |
| XSS, SQL injection, SSRF, malicious uploads                | output encoding/CSP, parameterized ORM, Pydantic allowlists, outbound destination allowlists and no arbitrary fetches, strict file type/size scanning or omit uploads in MVP                               |
| API abuse, rate-limit bypass, DDoS                         | per-subject/tenant/IP quotas, request-size/concurrency bounds, backpressure, caching, provider protections, monitoring/runbooks; WAF is only one layer and budget/platform limits remain                   |
| Queue flooding, job replay, duplicate remediation          | quotas, authenticated private queue, opaque payloads, idempotency keys, nonces/leases, optimistic locks, reauthorization, deduplication and dead-letter monitoring                                         |
| Confused deputy / permissive IAM / credential exposure     | exact CloudOps principal, per-connection external ID, STS temporary credentials, minimal session duration, read-only scan role, separate action-specific remediation role, policy review and CloudTrail    |
| Compromised worker                                         | isolated runtime identity/network, no credential persistence, minimal job data, egress controls, patched images, workload limits, secrets manager, rapid revocation                                        |
| Leaked AI key, prompt injection in metadata, AI disclosure | secret store/rotation, treat metadata and output as untrusted, delimit/minimize/redact inputs, never send credentials/full policies, schema validate/sanitize, provider retention review, cost/time limits |
| Jira webhook forgery / email or Teams abuse                | signature and timestamp verification, replay cache, scoped integration identity, destination allowlist, content minimization, throttling, delivery audit                                                   |
| Audit tampering, backup compromise, sensitive logs         | append-only events, hash chaining/export to versioned Object Lock-capable S3 design, separate access, encryption, redaction, restore tests, alerts on gaps; retention approval required                    |
| Dependency/CI compromise and CI secret exposure            | lockfiles later, review, dependency/secret/static scanning, least-privilege ephemeral CI identities/OIDC, protected environments, provenance and update policy                                             |

## Security requirements

Encrypt in transit and at rest; store application/provider secrets in Secrets Manager or equivalent; never log credentials/tokens or unredacted evidence. Use structured audit and operational logs with correlation IDs. Apply security headers, explicit exception mapping, bounded retries, alerting, backup testing, static and dynamic testing, dependency and secret scanning, and authorized manual penetration testing in sandbox/UAT.

## High-risk misuse cases

An attacker tries a valid finding ID from another tenant; the repository's organization predicate returns indistinguishable not-found/forbidden behavior and logs a redacted denial. A malicious S3 tag contains prompt instructions; it is treated as data, minimized/redacted, and cannot alter the structured prompt or call tools. A replayed approval request hits a unique idempotency key and current-version precondition. A compromised administrator cannot silently erase history.

Stage 4 rules have no network/filesystem access and cannot dynamically execute untrusted
content. A rule error cannot resolve a finding. Evaluation sequences reject stale results,
PostgreSQL uniqueness prevents duplicate active jobs/findings, suppression is capability
controlled, and React renders evidence as escaped text.

## Residual risks and open questions

No control guarantees complete security. OIDC vendor, MFA enforcement, WAF/CDN/hosting protections, RLS, data residency, archive immutability mode, penetration-test scope, upload exclusion, and incident/recovery objectives require approval. Revisit this model at every architecture boundary or new integration.

## Stage 6 risk-scoring threats

- Score manipulation is constrained by fixed policy versions, component bounds, immutable
  snapshots, optimistic context versions, and audited compensating controls.
- Cross-tenant substitution is rejected by composite PostgreSQL foreign keys and tenant-scoped
  queries.

## AI assistance boundary

Prompt injection, sensitive-data disclosure, hallucinated remediation, provider retention, and tool-use escalation remain active risks. The implemented mock and Bedrock provider paths use bounded persisted evidence, strict schemas, and redaction. AI output is advisory, cannot detect findings or calculate risk, cannot call arbitrary tools, and cannot approve remediation. Live Bedrock invocation is pending.

- Missing data is an explicit unknown input with a conservative neutral value; it is never
  silently treated as zero or success.
- Stale workers cannot mutate historical snapshots or create a second active assessment for the
  same scope.
- Evidence is bounded to reason codes and numeric components; credentials, raw policies, and raw
  provider errors are excluded.
## Stage 7 AI threats

Controls address indirect prompt injection, cross-tenant context retrieval,
credential leakage, oversized evidence, unstructured output, provider error
leakage, duplicate requests, quota races, stale source ambiguity, and unsafe
rendering. Evidence never becomes executable instructions, provider
credentials are not stored, and outputs have no mutation or delivery path.
