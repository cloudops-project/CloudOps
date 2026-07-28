# CloudFix Delivery Phases

This evidence-based map reconciles stages 0–17. Labels are limited to the approved vocabulary.
Configuration or workflow existence never counts as a live deployment. See
[PRD.md](PRD.md), [architecture.md](architecture.md), and [memory.md](memory.md).

Local verification totals below are **reported verification evidence; external log retention
required** unless backed by retained CI artifacts.

| Stage | Goal / expected deliverables | Implementation status | Local evidence | External validation / remaining work / blockers | Completion label |
|---|---|---|---|---|---|
| 0 Planning | Scope, architecture, ADRs, roadmap, safety boundaries | Core product/architecture decisions and planning corpus exist | Repository documents and ADRs | Reconcile branding and maintain documents as code changes | Complete and locally verified |
| 1 Authentication and RBAC | Auth, refresh, organizations, membership, invitation, capability RBAC | Implemented with tenant-aware routes, services, audit, and frontend | Backend/frontend tests reported passing | Production identity operations and real user UAT pending | Complete and locally verified |
| 2 AWS onboarding | Cross-account role, External ID, STS verification, lifecycle | Implemented; ordinary responses redact External ID; workload credential chain supported | Stubber/fake tests cover assume-role and failure paths | Live sandbox trust-policy/role validation pending | Implemented, external validation pending |
| 3 Asset discovery | Read-only collectors, normalized assets, jobs, partial failures | EC2/S3/IAM plus RDS/CloudWatch/CloudTrail collectors and durable orchestration exist | Synthetic collector/job tests reported passing | Supported APIs/permissions must be proven in live sandbox | Implemented, external validation pending |
| 4 Rule engine | Trusted deterministic rules, evaluations, finding lifecycle | Implemented; AI is excluded from detection | Deterministic rule/finding tests reported passing | Expand catalog only with evidence and tests | Complete and locally verified |
| 5 Compliance | Framework/control mappings and immutable assessments | Implemented over deterministic evidence; no certification claim | Compliance/migration tests reported passing | Content/legal coverage review and live dataset validation remain | Complete and locally verified |
| 6 Risk scoring | Versioned explainable scoring and snapshots | Implemented deterministic finding/account/organization scoring | Risk and tenant tests reported passing | Tune policy only through reviewed versions | Complete and locally verified |
| 7 AI assistant | Advisory explanations/summaries/drafts with safety bounds | Mock/external/Bedrock providers exist; AI cannot detect or authorize | Bedrock adapter uses Stubber; AI boundary tests reported passing | Live Bedrock model, quota, latency, cost, and content validation pending | Implemented, external validation pending |
| 8 Dashboard | Tenant UI for inventory, findings, compliance, risk, operations | Implemented React/Vite views and navigation | Lint/typecheck, 112 tests, and build reported passing | Browser accessibility/UAT across supported devices pending | Complete and locally verified |
| 9 Notifications | Approval-gated events and provider delivery evidence | Mock/SMTP/SES/Slack/Teams adapters; production SMTP rejected | Provider, approval-race, redaction tests reported passing | Live SES identity/delivery/bounce and optional webhook validation pending | Implemented, external validation pending |
| 10 Remediation | Preview, approval, immutable snapshot, governed execution | Governed deterministic mock/dry-run executor only; live mutation absent | Dry-run, approval, stale-evidence, job tests reported passing | Separate live executor/security review/rollback needed if scope changes | Partially implemented |
| 11 Scheduler | Persisted schedules, duplicate-safe orchestration, workers | PostgreSQL scheduler and durable job worker with leases/heartbeats/retries/dead letters | Scheduler/worker/concurrency tests reported passing | Multi-replica behavior and alarms need staging proof | Complete and locally verified |
| 12 Audit logs | Structured audit events, query, filters, safe export | Implemented across tenant workflows with bounded CSV export | Audit/tenant/redaction tests reported passing | Retention/export performance and SIEM integration need staging validation | Complete and locally verified |
| 13 Security hardening | Secret redaction, production validation, tenant defense, scans | Phase 1 controls plus workload identity/tenant safeguards are integrated | Ruff/Mypy, security tests, dependency/secret scans reported clean | Live IAM/KMS/secret rotation and incident exercises pending | Complete and locally verified |
| 14 DevOps and IaC | CI, release, Terraform, containers, observability definitions | Bootstrap/staging/production Terraform and CI/release workflows exist | Terraform validation; Checkov 471/0; container scans reported | No live plan/apply/OIDC/ECR/alarm evidence; action SHA pinning gap | Implemented, external validation pending |
| 15 Testing | Unit/integration/security/performance/UAT evidence | Extensive automated bounded groups A–I reported passing; UAT/load artifacts exist | A 198+1 skip, B 105, C 27, D 226, E 6, frontend 112 reported | Counts overlap; full retained CI run, UAT, load baseline remain | Partially implemented |
| 16 Deployment | Staging then production promotion, migration, smoke, rollback | Workflow and Terraform definitions only | Local container/readiness smoke reported | No staging/production deployment, canary, rollback, or restore proof | Not started |
| 17 Documentation and demo | Current handoff, runbooks, demo and UAT package | Documentation corpus and local demo runbook exist; truth audit in progress | Link/path/document checks from this audit | Complete review/commit and live demo/UAT evidence pending | Partially implemented |

## Current release boundary

Implemented locally does not mean operationally proven. The release remains blocked on an approved
AWS account/region, deployed OIDC and task roles, managed secrets, reviewed Terraform plan/apply,
live Bedrock/SES tests, staging UAT/load/observability, restore/rollback rehearsal, and explicit
production authorization.

No completion percentage is assigned because stages have materially different scope and external
gates; a simple average would be misleading.
