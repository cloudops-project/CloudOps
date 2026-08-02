# CloudOps trust boundaries

| Boundary | Untrusted input | Enforced controls |
|---|---|---|
| Browser to web/API | Tokens, identifiers, request bodies, forwarded headers | TLS in secure deployments, JWT/refresh controls, CORS/host checks, schemas, rate limits |
| API to tenant data | Organization and object IDs | Capability RBAC, organization-scoped queries, parent ownership checks, composite constraints, hidden cross-tenant results |
| API/workers to PostgreSQL | Concurrent state transitions | Explicit transactions, row locks, immutable triggers, leases, idempotency, foreign keys, checks |
| CloudOps runtime to AWS | Role ARN, account, resource evidence | Default workload identity, STS External ID, caller-account verification, bounded clients, separate roles |
| Discovery role to customer AWS | Read-only inventory | Read-only role, tenant/account binding, no persisted credentials |
| Remediation role to sandbox AWS | Two mutations | Separate trust, sandbox approval, exact allowlist, mandatory tags, immutable snapshot, drift and postcondition checks |
| CloudOps to AI provider | Minimized persisted context | Compatibility checks, sanitizer, bounds, canonical JSON, hashes, schema validation, audit |
| CloudOps to notification/Jira providers | Approved delivery content | Approval recheck, recipient/destination policy, safe errors, delivery idempotency, sanitized evidence |

## Secret boundaries

External IDs, temporary STS credentials, application secrets, provider tokens, webhook URLs, and
database credentials must not appear in broad responses, logs, jobs, audit metadata, frontend
bundles, or source control. Temporary AWS credentials remain in memory. Managed deployment designs
inject secrets through references; local/self-host workflows use ignored files with restrictive
permissions.

## Residual risks

- Live AWS, Bedrock, SES, Jira, Cloudflare, restore, rollback, and alarm behavior still require
  operational evidence.
- Advisory AI can be wrong; output must not become authorization or executable operations.
- The current AI sanitizer accepts generic evidence objects after sanitization. Rule-specific
  allowlisted evidence payloads are the preferred future minimization control.
- Capturing rollback state does not prove rollback execution is safe or operationally rehearsed.
