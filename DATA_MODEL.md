# CloudOps data model

The canonical schema overview is [database design](docs/architecture/database-design.md).
PostgreSQL is authoritative; SQLite-only tests do not prove PostgreSQL constraints.

## Current migration state

- One linear Alembic head: `0019_live_remediation_data_model`.
- Down revision: `0018_jira_integration`.
- Historical revisions are immutable.

## Principal domains

- Identity/tenancy: users, organizations, memberships, invitations, refresh sessions.
- AWS inventory: accounts, External ID reservations, discovery jobs, normalized assets.
- Analysis: evaluation jobs, findings, compliance catalog/assessments, deterministic risk policies
  and immutable finding/account/organization snapshots.
- AI: prompt templates, requests, exactly-one-source records, responses, and usage windows.
- Operations: notification events/attempts, Jira integrations/links, scan schedules/runs,
  PostgreSQL durable jobs, remediation requests, and audit events.

Migration 0019 adds separate remediation role/External ID, fail-closed sandbox approval metadata,
future live-execution mode storage, target/evidence/verification/rollback/request-ID fields, and
organization-consistent approval constraints. It does not enable live execution; service gates do.

Tenant isolation is enforced by explicit application predicates plus organization-consistent
foreign keys/checks/uniqueness. Immutable risk/remediation evidence is protected through reviewed
state transitions and PostgreSQL triggers where defined.
