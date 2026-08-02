# Tenant isolation

Organization ownership is the primary security boundary. Authentication alone does not authorize
access to an organization-owned record.

## Enforcement layers

- Route dependencies resolve the current user, organization membership, and required capability.
- Service/repository queries include organization predicates or load through an already verified
  tenant-owned parent.
- Cross-tenant identifiers return the same not-found behavior as absent identifiers where required,
  preventing existence disclosure.
- Organization-consistent foreign keys, uniqueness constraints, and approval checks prevent invalid
  cross-tenant relationships.
- Workers reload account, finding, asset, remediation, and provider records from PostgreSQL under the
  job's stored organization rather than trusting client or queue payloads.
- Audit events include organization, actor, action, outcome, correlation, and sanitized metadata.

Application predicates and RBAC remain mandatory even when database constraints or row-level
controls add defense in depth. Tests cover list/detail/update/delete/export/job paths and privileged
administration cross-tenant denial.
