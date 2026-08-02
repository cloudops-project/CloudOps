# Production acceptance checklist

Unchecked items are blockers unless explicitly marked not applicable through reviewed evidence.

## Software and security

- [x] Baseline commit has successful mandatory CI.
- [x] One Alembic head and disposable PostgreSQL migration gates pass in CI.
- [x] Tenant/RBAC and remediation governance automated tests pass in CI.
- [ ] Current release images have retained SBOM, provenance, digest, and vulnerability disposition.
- [ ] Zero unresolved Critical and zero unaccepted High findings are independently confirmed.
- [ ] Owned staging DAST and deployed tenant-isolation tests pass.

## Infrastructure and identity

- [ ] Dedicated non-production SSO identity/account/region is verified.
- [ ] Sandbox saved plan/hash/cost/security inventory is approved and applied exactly.
- [ ] Workload identity, IMDSv2, encryption, private DB/admin surfaces, and least privilege are proven.
- [ ] Managed staging plan/apply and qualification pass.
- [ ] Dedicated production account, reviewed plan, budget, DNS/TLS, and approvals are complete.

## Reliability and operations

- [ ] Successful encrypted backup and isolated restore establish RPO/RTO.
- [ ] Release rollback or safe forward recovery is exercised.
- [ ] Host, database, API, workers, dependencies, leases, and soak recovery pass thresholds.
- [ ] Dashboards and health checks are operational.
- [ ] Controlled alerts reach and are acknowledged by the on-call path.
- [ ] Incident, rollback, backup, credential rotation, and account offboarding ownership is accepted.

## Providers and remediation

- [ ] Bedrock live qualification passes or Bedrock is removed from production scope.
- [ ] SES live qualification passes or SES is removed from production scope.
- [ ] Jira live qualification passes or Jira is removed from production scope.
- [ ] Controlled non-production S3 and EC2 remediations pass separate approvals and verification.
- [ ] Emergency stop and disabled-state refusal are operationally verified.
- [ ] Rollback state is safely restored in a separately approved rehearsal.
- [ ] Live remediation remains disabled in production.

## UAT and release

- [ ] All seven personas complete recorded UAT with no blocking defect.
- [ ] Product, security, operations, data, and release owners sign off.
- [ ] Canary passes thresholds and explicit promotion is authorized.
- [ ] Production smoke, health, monitoring, backup, and tenant checks pass.
- [ ] Final ledger reaches 100/100 with zero hard blockers.
- [ ] Separate production-release authorization is recorded before tagging.

Current decision: **NO-GO**. Current evidence-based score: **55/100**.
