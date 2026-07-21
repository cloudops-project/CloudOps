# Database Engineering Guidelines

## Purpose and audience

Backend and data reviewers use these standards when turning the [conceptual model](../architecture/database-design.md) into migrations.

PostgreSQL is production intent; SQLite is limited to isolated experiments/lightweight tests. Tables are plural snake_case; UUID keys are default; timestamps are UTC; foreign keys, checks, unique constraints, and explicit indexes are mandatory. Every tenant query and relevant uniqueness rule includes `organization_id` directly or through a verified path.

Repositories accept organization context explicitly. Use parameterized SQLAlchemy, transactions for lifecycle state plus audit/outbox changes, optimistic locking for concurrent decisions, and bounded queries. Migrations are forward-reviewed, reversible where safe, backed up before destructive changes, and tested on production-like PostgreSQL. Never edit applied migrations or embed secrets.

Soft deletion fits mutable directory records such as users/accounts when history is required; findings and audit history use lifecycle/append semantics instead. Immutable rule versions and evidence must not be silently overwritten. JSONB requires versioned schemas and cannot hold ownership/security-critical relationships merely for convenience.

Open questions: PostgreSQL RLS, partitioning, outbox implementation, retention jobs, encryption/key controls, and production migration rollback policy.
