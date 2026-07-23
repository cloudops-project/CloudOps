# Implementation Phases

## Current delivery status

Stages 1–3 are merged. Stage 4 deterministic rules/findings are implemented on
`feature/4-rule-engine` and await independent verification. Stage 5 has not started.

## Purpose and audience

The five-member team and stakeholders use this dependency-ordered roadmap for planning after Stage 0 approval. Sequence is proposed; dates and performance claims require estimation and evidence.

**Owners:** M1 project/architecture, M2 backend/platform, M3 AWS/security engine, M4 frontend/design, M5 DevOps/quality/operations. “Accept” means acceptance criteria; every stage also requires the [definition of done](../engineering/definition-of-done.md).

| Stage | Objective; dependencies | Deliverables; acceptance criteria | Risks; owner / reviewer; demo milestone |
|---|---|---|---|
| 0 Planning/research | Agree scope, architecture, governance; none | PRD, scope, personas, architecture/data/threat designs, design system/wireframes, rules, Git/task/team/risk plans; substantive review and explicit approval | Unresolved assumptions; M1 / all; review walkthrough |
| 1 Foundation and authentication | Establish executable foundations plus identity and organization isolation; approved Stage 0 | FastAPI/React setup, PostgreSQL/Alembic, configuration, JWT/refresh sessions, registration/login, organizations, membership/invitations, RBAC, Stage 1 admin UI, audit-ready auth events, and quality checks; two-organization isolation and token lifecycle tests pass | Tooling drift and broken access control; M2+M5 / M1; registration-to-admin two-tenant demo |
| 2 AWS onboarding | Securely connect/disconnect organization AWS accounts; independently verified Stage 1 | Account record, unique external ID, generated trust/policy instructions, role ARN validation, STS AssumeRole + GetCallerIdentity validation, owner/admin UI and audit events; no long-lived keys and failure paths verified | IAM excess/confused deputy; M3 / M1+M5; connect/validate/disconnect demo |
| 3 Asset discovery | Build normalized EC2/S3/IAM/RDS inventory; connected Stage 2 account | Paginator-aware collectors, normalized assets, discovery jobs, safe stale lifecycle, partial failures, bounded inventory UI, tenant/RBAC/concurrency tests | Throttling/incomplete inventory; M3 / M2+M5; sandbox inventory |
| 4 Rule engine | Reproducibly evaluate versioned rules; 3 | Rule schema/loader/evaluator/versioning and approved EC2/S3/IAM initial rules; fixtures prove deterministic results | false/context signals, policy parsing; M3 / M1+M5; fixture + sandbox findings |
| 5 Findings/risk | Manage actionable lifecycle; 4 + 2 | Evidence, status/severity/risk, dedupe, suppression, exception workflow; concurrency/history/isolation verified | stale/deduped evidence; M2+M3 / M1; triage lifecycle |
| 6 Compliance | Explain reviewed control relationships; 4–5 | CIS candidate mappings after license/review, extensible framework/control model, dashboard; mapping provenance/caveat visible | licensing/overclaiming; M1+M3 / M5; control drill-down |
| 7 AI assistance | Add optional safe explanations; 4–6 | provider adapter, redaction, explanations, recommendations, report summaries, Jira drafts; invalid/outage fallback and leak tests pass | disclosure/hallucination/cost; M1+M2 / M3+M5; AI on/off comparison |
| 8 Dashboard/reporting | Make inventory and risk usable; 3–7 | assets/scans/findings/compliance/reports, filters/exports; target UAT and accessibility scenarios pass | dense data/misleading metrics; M4 / M1+M5; analyst journey |
| 9 Notifications/Jira | Coordinate external work; 5, 7–8 | email, Teams, Jira creation, feasible status sync; signed callbacks, retries, minimization verified | spam/token/webhook risk; M2 / M1+M5; finding-to-Jira |
| 10 Remediation workflow | Govern safe changes; 2, 5, 9 | approval/manual assignment, one supported Lambda playbook, verification, failure/rollback docs; separation/idempotency/sandbox proof | customer impact/duplicate action; M3 / M1+M2+M5; approve-remediate-verify |
| 11 Scheduling/background | Make jobs reliable; 3–5, 10 | manual/scheduled scans, retry, cancellation, queue monitoring; replay/partial/crash tests pass | floods/starvation; M2+M5 / M3; scheduled and recovered run |
| 12 Audit/security hardening | Strengthen traceability and abuse defenses; prior security paths | audit UI/archive, rate limits, secrets, headers, abuse detection; threat-model tests and archive reconciliation pass | gaps/tampering; M1+M5 / all; incident evidence trace |
| 13 Infrastructure/deployment | Create controlled environments; 1, mature app | Docker, Terraform, CI/CD, staging/production, monitoring/backups; peer-reviewed deploy and restore evidence | cost/drift/secrets; M5 / M1+M3; repeatable staging deployment |
| 14 Testing/UAT | Validate integrated MVP; 2–13 | unit/integration/contract/E2E/security/load suites and sandbox UAT; agreed release gates met with measured baselines | late defects/unrepresentative load; M5 / all; UAT scenario suite |
| 15 Documentation/demo | Enable use, maintenance, and evaluation; 14 | user/developer/deployment guides, presentation, live demo/video, report, future roadmap; artifacts reviewed and reproducible | stale docs/demo dependency; M1+M5 / all; final end-to-end demo |

## Governance

Do not begin a stage solely because a prior draft exists. Product and architecture gates must be explicitly accepted, security-critical dependencies cannot be waived informally, and parallel stages must document their assumptions. Estimates belong in the task board after refinement, not in this document.
