# CloudOps production-readiness ledger

Baseline source commit: `7926ab0f81daeca4234a13b5d92218b67f09defa`

Baseline CI: [run 30769052611](https://github.com/cloudops-project/CloudOps/actions/runs/30769052611)

Qualification environment: repository and CI only; no AWS or deployed environment was contacted.

Scores are additive within the mandated categories and are never rounded upward. A partial score
means the control combines verified implementation with missing operational evidence. The allowed
status describes the strongest evidence currently retained.

Supporting baseline records: [qualification plan](production-qualification-plan.md),
[evidence index](test-evidence-index.md), [risk register](production-risk-register.md),
[deployment decision](deployment-decision-record.md),
[operational dependencies](operational-dependency-inventory.md),
[external services](external-service-inventory.md),
[data classification](data-classification-inventory.md), and
[acceptance checklist](production-acceptance-checklist.md).

| Control | Weight | Required evidence | Current evidence | Status | Score |
|---|---:|---|---|---|---:|
| 1.1 Backend quality, tests, and migrations | 6 | Ruff, strict Mypy, full tests, disposable PostgreSQL, one head, upgrade/current/check/preflight | Backend CI job passed all named gates on the baseline commit | CI verified | 6 |
| 1.2 Frontend quality | 3 | Lockfile install, lint, typecheck, tests, production build, audit | Frontend CI job passed all gates | CI verified | 3 |
| 1.3 Containers and Compose | 2 | API/web builds, Compose render, migration-gated startup, self-host health | Containers and self-host container CI jobs passed | CI verified | 2 |
| 1.4 Dependency consistency and vulnerability checks | 2 | Backend/frontend dependency audits with no blocking finding | Backend and frontend CI audits passed | CI verified | 2 |
| 1.5 Reproducible immutable release artifacts | 2 | Retained image digests, SBOMs, provenance, release-manifest reproduction | Workflow is implemented; no baseline release artifacts retained | Implemented | 0 |
| 2.1 Authentication, RBAC, and tenant isolation | 6 | Positive/negative authorization, object isolation, tenant constraints | Source tests and Backend CI cover authorization and tenant paths | CI verified | 6 |
| 2.2 Application security controls | 4 | Validation, rate limits, headers/origin, SSRF, injection/XSS, safe errors, audit | Control implementations and automated tests passed in Backend CI | CI verified | 4 |
| 2.3 Secret and supply-chain scanning | 4 | Gitleaks, dependency/container/IaC scan, no blocking findings | Secret scan and Terraform/IaC jobs passed; dependency audits passed | CI verified | 4 |
| 2.4 AWS workload identity and role separation | 3 | No static keys, STS/External ID, IMDSv2, least privilege, deployed identity proof | Code/Terraform/static tests pass; deployed identity is unverified | CI verified | 2 |
| 2.5 AI safety boundary | 2 | Minimization, compatibility, one source, sanitization, bounds, hashes, audit | Unit/integration tests and Backend CI passed | CI verified | 2 |
| 2.6 Operational DAST and vulnerability closure | 1 | Owned staging DAST and retained Critical/High disposition | No deployed target or retained operational report | Not started | 0 |
| 3.1 Terraform static qualification | 4 | Pinned tool/provider, fmt, validate, tests, Checkov | Terraform/IaC CI job passed bootstrap, environments, sandbox, and Checkov | CI verified | 4 |
| 3.2 Controlled sandbox plan and apply | 4 | Verified identity, reviewed saved plan/hash/cost, exact apply, resource verification | Identity, plan, and apply have not occurred | Not started | 0 |
| 3.3 Managed staging deployment | 4 | Reviewed staging plan, apply, migration, smoke/security/load/recovery evidence | Not deployed | Not started | 0 |
| 3.4 Production deployment | 3 | Reviewed plan, canary, promotion, health and post-deploy evidence | Not deployed | Not started | 0 |
| 4.1 Durable-job recovery logic | 3 | Lease, heartbeat, idempotency, retry/dead-letter/concurrency tests | Backend and self-host CI cover these paths | CI verified | 3 |
| 4.2 Backup implementation | 2 | Encrypted backup procedure and safe tooling | Self-host backup/restore tooling and tests exist; no production backup | Automated-test verified | 1 |
| 4.3 Restore, RPO, and RTO | 4 | Successful isolated restore and measured RPO/RTO | No staging or production restore evidence | Not started | 0 |
| 4.4 Release rollback or safe forward recovery | 3 | Exercised application rollback/forward-fix with additive schema | Workflow/runbook exists; no operational exercise | Implemented | 0 |
| 4.5 Failure recovery and resilience | 3 | Host/DB/API/worker/provider outage and soak evidence | Automated component tests only; no deployed exercise | Automated-test verified | 0 |
| 5.1 Structured logs, correlation, and audit | 3 | Redacted structured logs and end-to-end correlation | Implemented and exercised by automated tests/CI | CI verified | 3 |
| 5.2 Metrics and alarm definitions | 2 | Reviewed metrics/alarms with safe dimensions | Terraform and application definitions exist; no live signals | Implemented | 1 |
| 5.3 Operational dashboards | 2 | Deployed dashboards showing API/DB/jobs/providers/host | Not deployed | Not started | 0 |
| 5.4 Alert routing and delivery | 2 | Controlled alert delivery and clear evidence | Not tested | Not started | 0 |
| 5.5 Incident and operations runbooks | 1 | Reviewed incident, rollback, backup, credential, offboarding guidance | Repository runbooks exist | Implemented | 1 |
| 6.1 Amazon Bedrock | 3 | Live authorized success/failure/timeout/rate/sanitization evidence | Adapter has Stubber tests only | CI verified | 0 |
| 6.2 Amazon SES | 3 | Live test-recipient delivery/failure/sanitization evidence | Adapter has mocked/Stubber tests only | CI verified | 0 |
| 6.3 Jira | 2 | Live test-project connection/create/idempotency/failure evidence | Adapter has mocked tests only | CI verified | 0 |
| 6.4 Provider failure-handling regression | 2 | Mocked timeout/retry/error/redaction/audit tests | Automated provider tests passed in CI | CI verified | 2 |
| 7.1 Governance, administration, and execution gates | 3 | Owner-only trust/approval, tenant checks, flags, emergency stop, lease/idempotency | Automated administration/service/API tests passed | CI verified | 3 |
| 7.2 S3 allowlisted executor | 2 | Exact-action, tag, drift, evidence, verification regression tests | Stubber/fake executor tests passed | CI verified | 2 |
| 7.3 EC2 allowlisted executor | 2 | Exact-rule, ingress-only, unrelated-rule, rollback evidence tests | Stubber/fake executor tests passed | CI verified | 2 |
| 7.4 Controlled live remediation | 2 | Separately approved non-production S3 and EC2 executions | No live AWS mutation occurred | Not started | 0 |
| 7.5 Emergency-stop and rollback operation | 1 | Operational refusal, state capture, separately approved restoration | State capture tested; no operational rollback | Automated-test verified | 0 |
| 8.1 Canonical governance documentation | 1 | Current product/architecture/security/operations/release docs | PR #30 merged and post-merge CI passed | CI verified | 1 |
| 8.2 Ledger, evidence index, and risk ownership | 1 | Reviewed baseline documents with external evidence references | Created in this Phase 1 branch; review pending | Implemented | 1 |
| 8.3 Persona UAT | 2 | Recorded scenarios and explicit acceptance | No UAT execution or sign-off | Not started | 0 |
| 8.4 Production acceptance and handover | 1 | Approved go/no-go, ownership, on-call and handover | Not approved | Not started | 0 |
| **Total** | **100** |  |  |  | **55** |

## Category totals

| Category | Earned | Maximum |
|---|---:|---:|
| Software quality and CI | 13 | 15 |
| Security and tenant isolation | 18 | 20 |
| Infrastructure and deployment | 4 | 15 |
| Reliability, backup and recovery | 4 | 15 |
| Observability and operations | 5 | 10 |
| Live provider integrations | 2 | 10 |
| Governed remediation safety | 7 | 10 |
| Governance, documentation and UAT | 2 | 5 |
| **Total** | **55** | **100** |

## Hard blockers

The score is below the 79-point hard-blocker cap. Confirmed blockers are:

1. No retained current full vulnerability/provenance disposition proving zero open Critical and
   acceptable High findings for release artifacts.
2. Operational security/exposure validation is missing.
3. Managed staging is not deployed or qualified.
4. Production is not deployed and production health checks are unavailable.
5. Production backup restore has not been tested and RPO/RTO are unmeasured.
6. Deployment rollback or safe forward recovery has not been exercised.
7. Monitoring dashboards and controlled alert delivery are unverified.
8. Advertised Bedrock, SES, and Jira integrations lack live qualification.
9. Persona UAT and explicit acceptance are missing.
10. Required operational evidence for discovery, resilience, remediation, and production is absent.

`PRODUCTION_QUALIFICATION_SCORE=55`

`PRODUCTION_QUALIFICATION_STATUS=FAILED`

`HARD_BLOCKERS=10`
