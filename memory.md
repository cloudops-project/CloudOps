# CloudOps Working Memory

## Last updated

2026-07-24

## Current repository and documentation release

- Integration branch: `main`
- Documentation release branch: `docs/stage5-merge-sync`
- Documentation PR: PR #5, open for review and not merged
- Initial documentation synchronization commit: `65d95a6d717556c70ede25900e9daf01dcb90dd4`
- The current documentation branch SHA is the result of `git rev-parse HEAD`; the final pushed
  SHA is recorded in PR #5 and the release report.
- Current main baseline SHA: `9811aeb881a1386c1dfba7e3e1641a2b765430f2`
- Verified Stage 5 feature SHA: `ff69a4ff5fd48a3e64581fadb284d9845cfcbc8f`
- Integrated Alembic head: `0007_stage5_compliance_engine`
- Stage 6 feature migration: `0008_stage6_risk_scoring`
- PR #4 is merged. Stage 5 is independently clean-room verified and regression-verified on main.

## Current implementation status

- Stage 1 Foundation and Authentication: complete and regression-tested
- Stage 2 AWS Account Onboarding: complete and independently verified
- Stage 3 Asset Discovery: complete and independently verified
- Stage 4 Deterministic Rule Engine and Findings: verified and merged
- Stage 5 Compliance Engine: complete, independently verified, and merged
- Stage 6 Deterministic Risk Scoring: implemented on `feature/6-risk-scoring`, verification pending

### Stage 6

Deterministic scoring uses persisted Stage 4 finding state plus explicit bounded context. Policy
key/version, component points, unknown inputs, source versions, and evaluation time are captured
in immutable snapshots. Suppression alone does not reduce risk. A compensating adjustment is
applied only through a separately authorized, reasoned, bounded control record. Account and
organization aggregates are derived from immutable finding snapshots. No rule performs network
or filesystem access, and AI is not part of detection or scoring.

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

## Completed verification evidence

The exact Stage 5 feature SHA was independently clean-room verified and the merged main commit
was regression-tested:

- Backend: 162 passed, 0 failed, 0 skipped; 95.88% coverage
- Frontend: 56 passed, 0 failed
- Ruff, Mypy (93 source files), startup/import, Prettier, ESLint, TypeScript, and Vite passed
- Empty and populated `0006 -> 0007` migration, downgrade/re-upgrade, drift, integrity,
  independent-session concurrency, rollback, and immutability checks passed
- `pip check`, `pip-audit`, and `npm audit` passed
- Secret, private-key, AWS-key, bearer/JWT, environment-file, unsafe-HTML, mojibake, local
  database, and Stage 6 executable-code scans found no blocker

## Known issues and limitations

- Live AWS validation/discovery is intentionally not part of deterministic automated tests.
- Discovery is synchronous and uses a configured explicit region list.
- Production email delivery, MFA, OIDC/SSO, password reset, distributed rate limiting,
  background scheduling, and deployment infrastructure are deferred.
- A Starlette multipart parsing deprecation warning may appear in backend tests.
- Supported Node 20 LTS or Node 22 LTS is recommended.
- Python uses `pyproject.toml` without a committed Python lockfile.
- The initial compliance catalog contains four controls and twelve mappings. It is not complete
  framework coverage or certification; mappings require human compliance review.
- Compliance export is not implemented, and GitHub reported no automated check rollup for PR #4.
- Risk scoring, AI, raw event ingestion, remediation, and Stage 6 functionality are absent by
  design. Stage 5 compliance is implemented without live AWS access or independent detection.

## Repository state

Stage 5 is integrated in `main` through PR #4 at
`68785b0138eaecf84850887a3d4005c40e9761c0`. Documentation synchronization is isolated on
`docs/stage5-merge-sync` in PR #5. Generated output remains ignored.

## Governance record

PR #2 was merged to `main` at `0849e75d...` with no recorded GitHub approval. The repository
owner explicitly accepted that fact as a governance exception after technical gates passed and
authorized Stage 4. PR #3 subsequently merged the verified Stage 4 baseline at
`04807de270bf1eeb152b67ab197d97f961e52179`.

PR #4 had zero recorded GitHub reviews and approvals and no automated check rollup. After
technical clean-room verification passed, the repository owner provided an
**Owner-authorized governance exception for PR #4**. This is not an independent GitHub,
CODEOWNER, automated CI, or repository-policy approval.

## Next immediate task

1. Review and explicitly authorize PR #5 as required by repository governance.
2. Merge PR #5 and synchronize local `main`.
3. Reconfirm the Stage 1–5 regression baseline and a clean worktree.
4. Authorize Stage 6 — deterministic risk scoring.
5. Create the Stage 6 feature branch only from the synchronized clean main baseline.
6. Keep AI out of finding detection and deterministic risk scoring.
