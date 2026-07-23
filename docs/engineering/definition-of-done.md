# Definition of Done

## Purpose and audience

Authors, reviewers, QA, and product owners use this checklist before moving an issue to Done.

- Acceptance criteria and explicit exclusions are met; linked issue and relevant stage/milestone are current.
- Design respects feature boundaries, tenant ownership, authorization, least privilege, AI limits, and read-only scan/remediation separation.
- Code (when authorized in later stages) is typed, formatted/linted, reviewed, and contains no credentials or prohibited data.
- Appropriate unit/integration/contract/end-to-end/security/accessibility tests pass with evidence; no results are invented.
- Error, retry, idempotency, concurrency, audit, logging/redaction, monitoring, and rollback/recovery implications are addressed.
- API/schema/migration changes are backward-safe or explicitly coordinated; migrations are reviewed and tested on PostgreSQL.
- User-facing behavior includes loading, empty, partial, permission, and error states; UI authorization is not trusted.
- Documentation, ADRs, threat model, rule catalogue, and project memory are updated when affected.
- At least one independent approval exists; designated owner approves security-sensitive changes; conversations are resolved.
- Demo or verification evidence is attached and no unresolved critical/high issue remains without approved exception.

Stage 0 documents are Done only after substantive review, internal-link/scope validation, open questions recorded, and stakeholder approval. Completion of this initial draft means “ready for review,” not Stage 0 approval.
