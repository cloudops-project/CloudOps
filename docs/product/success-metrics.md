# Success Metrics

## Purpose and audience

Stakeholders and QA use these measures to judge MVP readiness without inventing unbenchmarked guarantees.

| Outcome | MVP measure and evidence |
|---|---|
| Secure onboarding | Sandbox account connects through STS/external ID; no long-lived customer key fields or secrets exist in storage/logs |
| Supported inventory | Representative EC2, S3, and IAM assets are discovered and attributable to account, region/global scope, and scan run |
| Deterministic evaluation | A reviewed, versioned initial catalogue executes with reproducible fixture results; final rule count approved after research |
| Actionable findings | Each sample contains rule/version, resource, evidence, severity, timestamps, status, and guidance |
| Tenant isolation | Automated negative tests and review show cross-organization IDs cannot disclose or mutate records |
| Workflow completion | Finding → Jira/manual/approved sandbox playbook → verification → audit history is demonstrable |
| Resilience | Defined AI/Jira/notification outages preserve core scanning and expose retryable status without data loss |
| Usability/accessibility | Target personas complete agreed UAT scenarios; priority accessibility defects are resolved |

## Provisional targets

Scan duration, asset throughput, concurrent tenants, availability, retention, recovery objectives, and AI cost budgets require representative workloads and stakeholder approval. Baselines will be measured in Stages 12–15, then converted into service objectives; “all scans within five minutes” is not assumed.

## Reporting risks

Avoid vanity metrics such as raw finding counts. Track aged high-severity findings, verification success, expired acceptances, failed connections, and coverage gaps with denominator and scope. Metrics are decision aids, not proof of complete security or certification.
