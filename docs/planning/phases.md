# Implementation Phases

## Purpose and audience

The five-member team and stakeholders use this dependency-ordered roadmap for planning after Stage 0 approval. Sequence is proposed; dates and performance claims require estimation and evidence.

**Owners:** M1 project/architecture, M2 backend/platform, M3 AWS/security engine, M4 frontend/design, M5 DevOps/quality/operations. â€œAcceptâ€ means acceptance criteria; every stage also requires the [definition of done](../engineering/definition-of-done.md).

| Stage | Objective; dependencies | Deliverables; acceptance criteria | Risks; owner / reviewer; demo milestone |
|---|---|---|---|
| 0 Planning/research | Agree scope, architecture, governance; none | PRD, scope, personas, architecture/data/threat designs, design system/wireframes, rules, Git/task/team/risk plans; substantive review and explicit approval | Unresolved assumptions; M1 / all; review walkthrough |
| 1 Platform foundation | Establish executable foundations; approved Stage 0 | Repo initialization, FastAPI/React worker skeletons, local environment, PostgreSQL, configuration, basic CI; clean setup and checks on supported workstation | Tooling/cross-platform drift; M2+M5 / M1; local health/API shell only |
| 2 Authentication/tenancy | Enforce identity and organization isolation; 1 | Login, organization, membership, RBAC, session, user admin; cross-tenant negatives and audit pass | Broken access/control complexity; M2 / M1+M5; two-org isolation demo |
| 3 AWS onboarding | Securely connect/revoke accounts; 2 | Reviewed customer template, role ARN/external ID, STS validation, states/revocation; no long-lived keys and failure paths verified | IAM excess/confused deputy; M3 / M1+M5; sandbox connect/revoke |
| 4 Asset discovery | Build normalized EC2/S3/IAM inventory; 3 + jobs | Collectors, normalized assets, scan job/run tracking; representative coverage and partial failures visible | Throttling/incomplete inventory; M3 / M2+M5; sandbox inventory |
| 5 Rule engine | Reproducibly evaluate versioned rules; 4 | Rule schema/loader/evaluator/versioning and approved EC2/S3/IAM initial rules; fixtures prove deterministic results | false/context signals, policy parsing; M3 / M1+M5; fixture + sandbox findings |
| 6 Findings/risk | Manage actionable lifecycle; 5 + 2 | Evidence, status/severity/risk, dedupe, suppression, exception workflow; concurrency/history/isolation verified | stale/deduped evidence; M2+M3 / M1; triage lifecycle |
| 7 Compliance | Explain reviewed control relationships; 5â€“6 | CIS candidate mappings after license/review, extensible framework/control model, dashboard; mapping provenance/caveat visible | licensing/overclaiming; M1+M3 / M5; control drill-down |
| 8 AI assistance | Add optional safe explanations; 5â€“7 | provider adapter, redaction, explanations, recommendations, report summaries, Jira drafts; invalid/outage fallback and leak tests pass | disclosure/hallucination/cost; M1+M2 / M3+M5; AI on/off comparison |
| 9 Dashboard/reporting | Make inventory and risk usable; 4â€“8 | assets/scans/findings/compliance/reports, filters/exports; target UAT and accessibility scenarios pass | dense data/misleading metrics; M4 / M1+M5; analyst journey |
| 10 Notifications/Jira | Coordinate external work; 6, 8â€“9 | email, Teams, Jira creation, feasible status sync; signed callbacks, retries, minimization verified | spam/token/webhook risk; M2 / M1+M5; finding-to-Jira |
| 11 Remediation workflow | Govern safe changes; 3, 6, 10 | approval/manual assignment, one supported Lambda playbook, verification, failure/rollback docs; separation/idempotency/sandbox proof | customer impact/duplicate action; M3 / M1+M2+M5; approve-remediate-verify |
| 12 Scheduling/background | Make jobs reliable; 4â€“6, 11 | manual/scheduled scans, retry, cancellation, queue monitoring; replay/partial/crash tests pass | floods/starvation; M2+M5 / M3; scheduled and recovered run |
| 13 Audit/security hardening | Strengthen traceability and abuse defenses; prior security paths | audit UI/archive, rate limits, secrets, headers, abuse detection; threat-model tests and archive reconciliation pass | gaps/tampering; M1+M5 / all; incident evidence trace |
| 14 Infrastructure/deployment | Create controlled environments; 1, mature app | Docker, Terraform, CI/CD, staging/production, monitoring/backups; peer-reviewed deploy and restore evidence | cost/drift/secrets; M5 / M1+M3; repeatable staging deployment |
| 15 Testing/UAT | Validate integrated MVP; 2â€“14 | unit/integration/contract/E2E/security/load suites and sandbox UAT; agreed release gates met with measured baselines | late defects/unrepresentative load; M5 / all; UAT scenario suite |
| 16 Documentation/demo | Enable use, maintenance, and evaluation; 15 | user/developer/deployment guides, presentation, live demo/video, report, future roadmap; artifacts reviewed and reproducible | stale docs/demo dependency; M1+M5 / all; final end-to-end demo |

## Governance

Do not begin a stage solely because a prior draft exists. Product and architecture gates must be explicitly accepted, security-critical dependencies cannot be waived informally, and parallel stages must document their assumptions. Estimates belong in the task board after refinement, not in this document.
