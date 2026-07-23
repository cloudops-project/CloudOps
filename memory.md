# CloudOps Working Memory

## Last updated

2026-07-23

## Current branch and revision

- Branch: `feature/3-asset-discovery`
- HEAD before documentation synchronization: `a9d23ca8b329ffc266564d429d6faf58408b94e7`
- Current Alembic head: `0004_verification_repairs`
- No commit or push was performed during the current preparation/documentation work.

## Current implementation status

- Stage 1 Foundation and Authentication: complete and regression-tested
- Stage 2 AWS Account Onboarding: complete and independently verified
- Stage 3 Asset Discovery: complete and independently verified
- Stage 4 Security Analysis: not started

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

The current ten application tables are users, organizations, organization members,
organization invitations, refresh sessions, audit events, AWS accounts, external-ID
reservations, assets, and discovery jobs.

Migration chain:

```text
0001_stage1 -> 0002_stage2 -> 0003_stage3 -> 0004_verification_repairs
```

The repair migration backfills reservations without changing existing external IDs, adds
account lifecycle coordination, enforces composite tenant relationships, and adds asset/job
lifecycle checks.

## Completed local test evidence

The final independent repository review reproduced:

- Backend: 55 tests passed, 95% line coverage
- Frontend: 34 tests passed
- Ruff format/lint, Mypy, startup/import, Prettier, ESLint, TypeScript, and Vite build passed
- PostgreSQL migration lifecycle, model drift check, and concurrency suites passed
- `pip check`, `pip-audit`, and `npm audit` passed
- Secret, private-key, AWS-key, environment-file, and conflict-marker scans found no blocker

These results satisfy the Stage 2/3 independent technical verification gate. Human pull-request
approval remains separate and required by repository policy.

## Known issues and limitations

- The feature branch has not been committed, pushed, reviewed, or merged in the current worktree.
- Live AWS validation/discovery is intentionally not part of deterministic automated tests.
- Discovery is synchronous and uses a configured explicit region list.
- Production email delivery, MFA, OIDC/SSO, password reset, distributed rate limiting,
  background scheduling, and deployment infrastructure are deferred.
- A Starlette multipart parsing deprecation warning may appear in backend tests.
- Python uses `pyproject.toml` without a committed Python lockfile.
- Stage 4 and later security functionality is absent by design.

## Repository state

At the start of this documentation synchronization, the Stage 1–3 application, migrations,
tests, manifests, and verification support were staged for controlled review; active
documentation changes remained unstaged. Existing staged application content must be preserved.

## Current blockers

- The verified work is not yet committed or pushed.
- Repository policy requires a pull request and independent human approval before merge.
- No GitHub Actions workflow currently executes these gates remotely.

## Next immediate task

1. Commit and push the verified Stage 1–3 baseline.
2. Open a pull request to `main`.
3. Obtain independent human review and merge through repository policy.

Do not start Stage 4 as current work.
