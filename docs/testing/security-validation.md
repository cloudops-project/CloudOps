# Security validation

Security validation combines code-level regression tests and independent scanners:

- Cross-tenant API, repository, job, export, and privileged administration denial tests.
- RBAC tests for owner, analyst/member, and unauthenticated behavior.
- Secret redaction and sentinel-secret tests across logs, responses, audit, persistence, jobs, and
  frontend bundles.
- AWS credential rejection, default-chain, STS refresh, account mismatch, provider error, and
  no-live-call tests.
- Remediation gate, immutable snapshot, drift, mandatory-tag, lease/idempotency, exact-action,
  postcondition, and unrelated-resource-preservation tests.
- PostgreSQL constraints, trigger immutability, migration, row-lock, and pool/concurrency tests.
- Container non-root/read-only/health/topology checks.
- Gitleaks, dependency audits, image vulnerability scans, Terraform static tests, Checkov, and
  workflow/IAM permission review.

Scanner output must be redacted; secret-shaped matches are investigated without printing values.
Exceptions must be resource-specific and justified. A previous clean scan is not proof for a new
diff, and a source scan does not replace deployed-environment validation.
