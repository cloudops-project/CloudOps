# CloudOps Working Memory

## Last updated

2026-07-23

## Current branch and revision

- Branch: `feature/5-compliance-engine`
- Baseline SHA: `04807de270bf1eeb152b67ab197d97f961e52179`
- Current Alembic head: `0007_stage5_compliance_engine`
- Stage 5 changes are intentionally dirty and uncommitted until every mandatory gate passes.

## Current implementation status

- Stage 1 Foundation and Authentication: complete and regression-tested
- Stage 2 AWS Account Onboarding: complete and independently verified
- Stage 3 Asset Discovery: complete and independently verified
- Stage 4 Deterministic Rule Engine and Findings: verified and merged
- Stage 5 Compliance Engine: implemented, final verification in progress
- Stage 6: not started

## Completed work

### Stage 1

Authentication, short-lived JWT access tokens, rotating refresh cookies, password change,
organizations, members, invitations, RBAC, last-owner protection, audit events,
health/readiness, and Stage 1 frontend flows.

### Stage 2

AWS account lifecycle, permanent external-ID reservation, IAM setup guidance, role ARN
validation, STS `AssumeRole`/`GetCallerIdentity`, connection states, tenant authorization,
concurrency coordination, audit events, and onboarding UI.

### Stage 3

EC2, S3, IAM, and RDS collectors; normalized assets; discovery jobs; pagination; configured
regional/global handling; historical upsert/stale lifecycle; partial failures; bounded APIs;
PostgreSQL tenant/lifecycle constraints; concurrency guards; asset and discovery UI.

### Stage 4

Typed deterministic rules for EC2, S3, IAM, RDS, CloudWatch, CloudWatch Logs, and CloudTrail;
configuration-only discovery expansion; evaluation jobs; finding create/update/resolve/reopen
and suppression lifecycles; tenant-safe APIs; structured logs and audit events; PostgreSQL
active-job and finding uniqueness; and frontend dashboards, filters, detail views, dialogs, and
role-aware actions.

### Stage 5

Versioned frameworks and controls; rule-version-aware mappings; persisted per-rule Stage 4
evaluation summaries; account assessments; immutable control snapshots; PASS/FAIL/
NOT_ASSESSED/ERROR semantics; suppression-safe failure behavior; tenant-safe APIs; compliance
RBAC; structured logs and audit events; and an accessible compliance workflow.

## Architecture decisions

- ADR-007 establishes the authorized Stage 1 foundation/authentication scope.
- ADR-008 selects local JWT access plus opaque rotating refresh sessions for Stage 1.
- ADR-009 selects Tailwind CSS over the earlier Material UI proposal.
- ADR-010 establishes CloudOps as the active product name while preserving history.
- ADR-011 establishes cross-account AWS onboarding as Stage 2.
- PostgreSQL is authoritative for partial indexes, composite foreign keys, row locks, and
  concurrency behavior.
- Discovery remains synchronous in the API process; workers/scheduling are deferred.

## Security decisions

- No long-lived AWS access keys are accepted or stored.
- STS credentials exist in memory only.
- External IDs are globally unique and permanently retained after account deletion.
- Access JWTs remain in browser memory; refresh tokens are HttpOnly and hashed at rest.
- Tenant authorization is backend enforced through active membership and centralized RBAC.
- Composite foreign keys enforce asset/job organization consistency.
- AWS client timeouts and retries are explicit, bounded, and environment driven.
- Stage 3 performs inventory only and does not evaluate security.

## Database decisions

The application schema includes users, organizations, organization members,
organization invitations, refresh sessions, audit events, AWS accounts, external-ID
reservations, assets, discovery jobs, evaluation jobs, findings, evaluation rule results,
compliance frameworks, controls, mappings, assessments, and assessment-control snapshots.

Migration chain:

```text
0001_stage1 -> 0002_stage2 -> 0003_stage3 -> 0004_verification_repairs ->
0005_stage4_rule_engine -> 0006_stage4_verification_repairs ->
0007_stage5_compliance_engine
```

The repair migration backfills reservations without changing existing external IDs, adds
account lifecycle coordination, enforces composite tenant relationships, and adds asset/job
lifecycle checks.

## Completed local test evidence

The final independent repository review reproduced:

- Stage 1–3 baseline: 55 backend tests and 34 frontend tests passed at 95% coverage
- Current Stage 4 candidate: 79 backend tests and 44 frontend tests passed at 95% coverage
- Ruff format/lint, Mypy, startup/import, Prettier, ESLint, TypeScript, and Vite build passed
- PostgreSQL migration lifecycle, model drift check, and concurrency suites passed
- `pip check`, `pip-audit`, and `npm audit` passed
- Secret, private-key, AWS-key, environment-file, and conflict-marker scans found no blocker

These results satisfy the Stage 2/3 independent technical verification gate. Human pull-request
approval remains separate and required by repository policy.

## Known issues and limitations

- The Stage 4 feature branch is not yet committed, pushed, independently verified, or merged.
- Live AWS validation/discovery is intentionally not part of deterministic automated tests.
- Discovery is synchronous and uses a configured explicit region list.
- Production email delivery, MFA, OIDC/SSO, password reset, distributed rate limiting,
  background scheduling, and deployment infrastructure are deferred.
- A Starlette multipart parsing deprecation warning may appear in backend tests.
- Python uses `pyproject.toml` without a committed Python lockfile.
- Risk scoring, AI, raw event ingestion, remediation, and Stage 6 functionality are absent by
  design. Stage 5 compliance is implemented without live AWS access or independent detection.

## Repository state

The Stage 5 application, migration, tests, frontend, and documentation are local changes on
`feature/5-compliance-engine`. Generated output remains ignored. Publish only after every gate
passes.

## Governance record

PR #2 was merged to `main` at `0849e75d...` with no recorded GitHub approval. The repository
owner explicitly accepted that fact as a governance exception after technical gates passed and
authorized Stage 4. PR #3 subsequently merged the verified Stage 4 baseline at
`04807de270bf1eeb152b67ab197d97f961e52179`. This record does not fabricate an approval.

## Next immediate task

1. Complete Stage 5 gates.
2. Commit and push `feature/5-compliance-engine`.
3. Open a draft pull request to `main`.
4. Run detached clean-room Stage 5 verification.
5. Do not merge Stage 5 or start Stage 6.
