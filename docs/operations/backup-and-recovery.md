# Backup and Recovery

## Implemented design and launch gate

Terraform configures encrypted RDS automated backups for 7 days in staging and 35 days in production, snapshot tag copying, production Multi-AZ, deletion protection, and a required final snapshot. Terraform state is versioned, KMS-encrypted, public-blocked, lifecycle retained, and lock protected.

For the single-host named-Cloudflare path, `cloudops backup` creates a local PostgreSQL custom
dump with Git SHA, Alembic head, and SHA-256 integrity metadata. `cloudops restore` confines input
to `.cloudops/backups`, requires exact confirmation, migrates, and verifies health. This is an
initial operator workflow, not managed DR: backups must be protected and copied off-host, and a
target-host restore rehearsal remains required.

A restore rehearsal must restore into an isolated private environment, run Alembic/integrity/tenant-isolation/audit/queue/smoke verification, capture achieved recovery point and duration, and remove the isolated resources only under the approved change. Never overwrite the active database during rehearsal.

Initial design targets are RPO 24 hours and RTO 4 hours. Production launch is blocked until a documented staging restore meets or revises those targets. Cross-region/cross-account copies remain a cost/risk decision; regional disaster recovery is not yet verified.

## Purpose and audience

Operators, security, and product owners use this plan to define recoverability before production deployment.

Back up PostgreSQL through encrypted automated snapshots plus point-in-time recovery where supported; retain infrastructure state/configuration through reviewed Terraform and repositories; protect S3 audit/report artifacts through versioning/replication according to approved policy; record secret metadata and rotation procedures without exporting secret values casually. Queue contents are not the system of record—durable job state enables reconciliation.

Restore into an isolated environment, verify integrity, tenant isolation, migrations, audit-chain continuity, and application behavior before promotion. Run scheduled restore exercises and document duration, data point, exceptions, and corrective actions. Backup access uses separate least privilege, MFA readiness, encryption keys, alerts, and deletion protection; compromised backups are an incident.

RPO, RTO, retention, cross-region/cross-account copies, key recovery, and test cadence remain open until risk/cost approval. No recovery capability is claimed before a successful documented restore.
