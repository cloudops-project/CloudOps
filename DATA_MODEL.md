# CloudOps Data Model (Index)

> Root-canonical pointer. The full conceptual and physical schema — every table, its purpose,
> retention/sensitivity notes, indexes, and the ER diagram — lives at
> [docs/architecture/database-design.md](docs/architecture/database-design.md). This file is
> intentionally a short index, not a restatement, so schema facts have exactly one place to drift.

## Authoritative schema state

PostgreSQL is production; SQLite is used only for isolated unit tests. The Alembic migration chain
is linear with one head: **`0017_remediation_json_trigger`**. `docs/architecture/database-design.md`
documents the schema through that revision, organized by the stage that introduced each table group:

| Stage | Introduces | Key entities |
| --- | --- | --- |
| 1 | Identity and tenancy | `users`, `organizations`, `organization_members`, `organization_invitations`, `refresh_token_sessions`, `audit_events` |
| 2 | AWS onboarding | `aws_accounts`, `aws_external_id_reservations` |
| 3 | Discovery | `assets`, `discovery_jobs` |
| 4–5 | Rules, findings, compliance | `evaluation_jobs`, `findings`, `evaluation_rule_results`, `compliance_frameworks`, `compliance_controls`, `rule_control_mappings`, `compliance_assessments`, `compliance_assessment_controls` |
| 6 | Risk scoring | `risk_scoring_policies`, `asset_risk_contexts`, `risk_assessments`, `finding_risk_snapshots`, `account_risk_snapshots`, `organization_risk_snapshots`, `compensating_controls` |
| 7 | AI assistant | `ai_prompt_templates`, `ai_requests`, `ai_request_sources`, `ai_responses`, `ai_usage_windows` |
| Later (per `phases.md`) | Notifications, remediation, scheduling | `notification_events`, `remediation_requests`, `platform_jobs`, scan schedules/runs |

Tenant isolation is enforced at the database level, not just in application code: composite foreign
keys tie tenant-owned rows to their owning organization **and** parent record, partial unique
indexes enforce single-active invariants (one pending/running discovery job, evaluation, or scan run
per account; one active remediation request per finding), and several snapshot tables are made
immutable by PostgreSQL triggers rather than by convention. See
[SECURITY_MODEL.md](SECURITY_MODEL.md) "Tenant isolation" for the security framing of the same
facts.

## Demo-specific data

The demo does not introduce new tables. It seeds ordinary rows through the ordinary models, using
`apps/api/app/services/demo_inventory.py` as the single source of synthetic asset metadata (five
assets: an EC2 instance, an EC2 security group, an S3 bucket, a CloudTrail trail, and an IAM user —
see `ADR-D02` for why this module exists and what it fixed). No demo-only column, table, or migration
exists; `DEMO_SYNTHETIC_DISCOVERY` only changes which service populates `assets`, not the schema.

## What this file does not do

It does not restate field lists, index names, or retention policy — those belong in
[docs/architecture/database-design.md](docs/architecture/database-design.md) alone, so a future
migration only needs one document updated.
