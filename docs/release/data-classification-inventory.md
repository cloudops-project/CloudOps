# Data-classification inventory

| Class | Examples | Storage/transfer rules | Logging/evidence rules |
|---|---|---|---|
| Public | Product docs, public rule descriptions | Source control permitted | Normal logs permitted |
| Internal | Architecture, non-sensitive configuration names, CI summaries | Repository/internal systems | Avoid unnecessary identifiers |
| Tenant confidential | Organization/user records, asset metadata, findings, risk/compliance, audit events | Tenant-scoped encrypted database; TLS; least privilege | Redact/pseudonymize; no raw operational export in Git |
| Security sensitive | Role ARN, account identifiers, resource ARN/IDs, network inventory, approval/snapshot evidence | Encrypted, scoped access; minimized provider transfer | Never metric dimensions; sanitized external evidence only |
| Secret | Passwords, JWT keys, DB/provider credentials, webhook/tunnel tokens, External IDs | Approved secret store or ignored restricted file; never frontend/source/plan | Never log, audit, prompt, ticket, screenshot, or commit |
| Ephemeral credential | AWS SSO/session/STS credentials | Memory/cache controlled by approved tooling; no application persistence | Never display or retain in qualification evidence |
| Restricted artifact | Terraform state/plan, backups, raw logs, private SBOM/provenance detail | Restricted external directories with hashes in Git | Store sanitized summary and SHA-256 only |
| Synthetic test data | Documentation-safe accounts, users, resources, recipients | Isolated non-production only | Mark synthetic; do not confuse with live customer evidence |

## AI boundary

Only one compatible persisted source is bounded and sanitized before an AI call. Authoritative risk,
severity, compliance, eligibility, approval, and execution stay local. Rule-specific evidence
allowlists remain the preferred minimization improvement.
