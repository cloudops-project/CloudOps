# Backup and Recovery

## Purpose and audience

Operators, security, and product owners use this plan to define recoverability before production deployment.

Back up PostgreSQL through encrypted automated snapshots plus point-in-time recovery where supported; retain infrastructure state/configuration through reviewed Terraform and repositories; protect S3 audit/report artifacts through versioning/replication according to approved policy; record secret metadata and rotation procedures without exporting secret values casually. Queue contents are not the system of record—durable job state enables reconciliation.

Restore into an isolated environment, verify integrity, tenant isolation, migrations, audit-chain continuity, and application behavior before promotion. Run scheduled restore exercises and document duration, data point, exceptions, and corrective actions. Backup access uses separate least privilege, MFA readiness, encryption keys, alerts, and deletion protection; compromised backups are an incident.

RPO, RTO, retention, cross-region/cross-account copies, key recovery, and test cadence remain open until risk/cost approval. No recovery capability is claimed before a successful documented restore.
