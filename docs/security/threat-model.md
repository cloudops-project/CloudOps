# CloudOps threat model

## Protected assets

Tenant data, authentication sessions, AWS trust configuration, External IDs, temporary workload
credentials, findings and snapshots, approval state, provider configuration, audit evidence, and
deployment state are protected assets.

## Principal threats and controls

| Threat | Primary controls | Residual validation |
|---|---|---|
| Cross-tenant object access | Organization-scoped queries, RBAC, hidden cross-tenant results, composite constraints, tests | Operational penetration test pending |
| Confused-deputy role assumption | Generated External IDs, account/role validation, caller verification, separate role paths | Live sandbox STS pending |
| Long-lived credential leakage | Default provider chain, temporary STS credentials in memory, redaction, secret scanning | Deployed-host inspection pending |
| AI prompt injection or disclosure | One source, compatibility checks, normalization, pattern redaction, bounds, schema validation | Provider-side live validation pending |
| Unauthorized remediation | Owner administration, approval separation, static action allowlist, flags, emergency stop, tags, drift, lease, idempotency | Controlled live test pending |
| Worker duplication or stale completion | Database idempotency, row locks, lease tokens/generations, heartbeats, postcondition checks | Deployed failure-recovery exercise pending |
| Provider replay or duplicate delivery | Approval recheck, fingerprints/idempotency, sanitized attempts | Live SES/Jira tests pending |
| Infrastructure exposure | Private service networking, narrow security groups, WAF/ALB design, managed secrets | Terraform apply and runtime review pending |
| Audit tampering or evidence loss | Append-oriented audit records, immutable snapshots/triggers, correlation IDs | Backup/restore rehearsal pending |

The detailed boundary inventory is in [trust boundaries](../architecture/trust-boundaries.md).
This threat model does not assert that external controls are deployed.
