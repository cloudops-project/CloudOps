# Risk Register

## Purpose and audience

The team and stakeholders use this living register to prioritize uncertainty and assign treatments. Likelihood/impact are initial qualitative estimates requiring review.

| Risk | L/I | Treatment / trigger | Owner |
|---|---|---|---|
| Cross-tenant disclosure | M/Critical | layered organization checks, negative tests, audit; any scope failure blocks release | M1/M2 |
| Onboarding IAM too broad/confused deputy | M/Critical | exact principal/external ID, policy review, STS-only credentials; template diff triggers review | M3 |
| Remediation causes customer impact | M/Critical | separate role, allowlisted playbook, approval, preconditions/idempotency/verification/rollback docs | M1/M3 |
| Rule false/context signals erode trust | H/High | policy qualifiers, fixtures, evidence, versioning, analyst feedback; elevated suppressions trigger review | M3 |
| Incomplete AWS inventory/throttling | H/High | pagination, coverage markers, bounded retries, benchmark; partial scan never shown complete | M3/M2 |
| AI leaks data or misleads | M/High | minimization/redaction, schema/sanitization, provider review, labeling/fallback/cost limits | M1/M5 |
| Audit trail tampering/gaps | M/Critical | transactional emission, reconciliation, separate tamper-evident archive and alerts | M5 |
| Credentials/secrets leak in logs/CI | M/Critical | secret store, redaction tests, scanning, ephemeral CI identities, incident rotation | M5 |
| Queue replay/flooding | M/High | quotas, leases, idempotency, reauthorization, monitoring/dead letter | M2/M5 |
| Compliance overclaim/licensing | M/High | reviewed mappings with provenance/caveats; legal/content approval before publishing | M1 |
| Student budget/complexity | H/Medium | PostgreSQL durable jobs avoid a second broker; retain cost budgets and managed-service decision gates | M1/M5 |
| Knowledge silo / member absence | M/High | backups, pairing, ADRs/runbooks, rotating demos and cross-review | All |
| Backup/restore not viable | M/High | defined RPO/RTO, encrypted backups, scheduled restore tests before release | M5 |
| Dependency/supply-chain compromise | M/High | pinned dependencies later, review, scanning/provenance, update policy | M5 |
| Scope creep beyond EC2/S3/IAM | H/Medium | scope gate/change issue; new service deferred unless approved displacement | M1 |

## Review process

Review at sprint planning/review, after incidents/major decisions, and before each release gate. Add date, status, residual rating, contingency, and evidence links once the team selects its tracking tool. No risk can be silently accepted; critical risk acceptance needs named authority and expiry.
