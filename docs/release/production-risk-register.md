# Production qualification risk register

No risk acceptance is implied by inclusion. A High risk requires an owner, expiry, compensating
control, and approval before it can cease blocking release.

| ID | Risk | Severity | Evidence/state | Mitigation and owner | Due/acceptance |
|---|---|---|---|---|---|
| PQ-01 | Production deployment and health are unproven | Critical | No production environment | Complete staging, reviewed production plan, canary and health validation; release owner | No acceptance permitted |
| PQ-02 | Backup may be unusable | Critical | No production restore rehearsal or measured RPO/RTO | Encrypted backup plus isolated restore and integrity/tenant checks; database owner | No acceptance permitted |
| PQ-03 | Release recovery may fail | High | Rollback/forward recovery not exercised | Exercise immutable application rollback with additive schema; release owner | Required before production |
| PQ-04 | Alerting may not reach responders | High | Metrics/alarms defined but delivery untested | Deploy dashboards, send controlled alerts, record routing/clear; operations owner | Required before production |
| PQ-05 | Live provider behavior may differ from mocks | High | Bedrock/SES/Jira have no live evidence | Dedicated test resources and authorized qualification; integration owners | Required or remove provider from production scope |
| PQ-06 | AWS identity or IAM boundary may differ in deployment | High | Terraform/static tests only | Dedicated account, short-lived SSO, plan/IAM review, deployed instance-profile proof; security owner | Required before sandbox/staging |
| PQ-07 | Live remediation could affect the wrong state | Critical | Executor is default-disabled; no live test | Tagged synthetic lab, per-action approval, drift/lease/idempotency evidence, immediate disable; security owner | No production enablement |
| PQ-08 | Vulnerability/provenance state may be stale | High | CI dependency/secret/IaC gates pass; complete release artifact report absent | Build immutable images, SBOM, image scan/provenance and time-bound dispositions; security owner | Required before release candidate |
| PQ-09 | Tenant isolation could regress under deployed concurrency | Critical | Automated tests pass; operational DAST/load absent | Run tenant negative tests and owned staging DAST/load; application security owner | No acceptance permitted |
| PQ-10 | Sandbox cost or retained resources may exceed approval | Medium | No plan or cost inventory | Plan externally, enforce the separately approved cost ceiling, teardown verification/billing review; operator | Before apply |
| PQ-11 | AI may receive broader evidence than necessary | Medium | Generic evidence is sanitized; rule-specific allowlists are a recommendation | Add rule-specific evidence allowlists or accept bounded residual risk; AI/security owner | Before provider production scope |
| PQ-12 | UAT may reveal workflow/accessibility defects | High | No signed persona UAT | Execute all personas and resolve blockers; product owner | Required before production |

## Current decision

Production is **NO-GO**. No Critical or High item above is accepted. The ledger remains capped by
hard blockers until operational evidence closes them.
