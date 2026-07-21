# Environment Strategy

## Purpose and audience

Developers, QA, security, and operators use these planned boundaries to prevent test activity from affecting production or customer accounts.

| Environment | Purpose | Data and AWS boundary |
|---|---|---|
| Local | Development and deterministic fixtures | Synthetic data; no shared/customer credentials; SQLite only for isolated tests, PostgreSQL for representative work |
| Development | Shared integration | Synthetic accounts/data and low-cost services; isolated secrets and tenant IDs |
| UAT / sandbox | End-to-end AWS/security/remediation validation | Dedicated authorized AWS sandbox; destructive playbooks constrained and approved |
| Staging | Production-like release validation | Sanitized/synthetic data, separate account/database/secrets |
| Production | Approved customer service | Strongest access, monitoring, backup, residency, and change controls |

Configuration is environment-specific and validated at startup; secrets come from an approved store. Never copy production databases, credentials, external IDs, or customer evidence into lower environments. Accounts, networks, encryption keys, audit archives, integrations, and role trust must be separated.

Open questions: whether development and UAT are separate initially, region/residency, environment access matrix, data refresh, cost budget, and ephemeral preview environments.
