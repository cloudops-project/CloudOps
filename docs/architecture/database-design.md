# Database design

PostgreSQL is the authoritative datastore and durable-job backend. Alembic has one linear head:
`0019_live_remediation_data_model`, whose down revision is `0018_jira_integration`.

## Domain groups

| Domain | Principal tables |
|---|---|
| Identity and tenancy | `users`, `organizations`, `organization_members`, `organization_invitations`, `refresh_token_sessions` |
| AWS inventory | `aws_accounts`, `aws_external_id_reservations`, `discovery_jobs`, `assets` |
| Analysis | `evaluation_jobs`, `findings`, compliance framework/control/assessment tables |
| Risk | policies, contexts, assessments, finding/account/organization snapshots, compensating controls |
| AI | prompt templates, requests, request sources, responses, usage windows |
| Workflow | notifications and delivery attempts, remediation requests, schedules/runs, platform jobs, Jira integrations/links |
| Audit | `audit_events` |

## Integrity model

- Tenant-owned records carry organization ownership directly or through an organization-verified
  parent. Composite foreign keys and uniqueness constraints reinforce relationship consistency.
- Repository queries retain explicit tenant predicates even where database constraints exist.
- Approval state uses checks to prevent incomplete actor/timestamp metadata.
- Remediation trust uses separate role and External ID fields from discovery.
- JSON evidence uses server-side safe defaults; services reject credential-shaped content.
- Risk snapshots and approved remediation snapshots are immutable through application controls and
  PostgreSQL triggers where implemented.
- Durable jobs enforce idempotency, lease generation/token ownership, retry/dead-letter state, and
  correlation.

## Migration rules

Historical migrations are immutable. New work appends one revision, preserves a single head, uses
expand-and-contract changes, and must pass clean upgrade, upgrade-from-previous, `current`, `check`,
and migration preflight against disposable PostgreSQL. SQLite is not a substitute for PostgreSQL
constraint verification.

See [DATA_MODEL.md](../../DATA_MODEL.md) for the concise model map and
[migration safety](../operations/migration-safety.md) for procedures.
