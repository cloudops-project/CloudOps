# CloudOps Working Memory

## Last updated

2026-07-26 — Stages 9-12 are committed on `feature/v1-demo-completion`. The current
demo-readiness work adds guarded Mailpit SMTP notification delivery, development-only Mailpit
invitation emails, a local PostgreSQL/Mailpit/API/web Compose stack, Docker-only helper scripts,
deterministic demo seed/reset, the root `demo_v1.md` runbook, and an 18-step V1 demo acceptance
runner.

Current demo-readiness verification: Docker demo config/build/start/readiness/restart/cold-start/
reset passed; manual scheduler tick passed; Mailpit security notification and invitation email
delivery were verified; V1 acceptance completed 18 PASS, 0 FAIL; backend completed 522 passed,
0 failed, 0 skipped with 96.44% coverage; Mypy checked 144 source files; frontend TypeScript,
ESLint, 112 Vitest tests, and production build passed. Online npm audit is blocked pending
explicit metadata-egress authorization.

## Current repository and documentation release

- Integration branch: `main`
- Active feature branch: `feature/v1-demo-completion` (based on `feature/9-notifications`)
- Current committed HEAD on the feature branch: `9314f06 feat(web): add audit log explorer`
- Current authoritative main SHA: `889660ecb8a378d107f6737b4466b70362066793` (unchanged; `main`
  has not advanced past Stage 8)
- Verified Stage 6 feature SHA: `b0361b8efe9060ef6c498e1cebfede4baaa9947d`
- Stage 6 merge commit: `f23e124813b5f65a8f85957c1dce57d95b9cf038`
- Verified Stage 7 feature SHA: `9b5f4372359a32066787060ca839d5a68c5ab490`
- Stage 7 merge commit: `882ff531af07276c11e0d25664fdca033e09c7c7`
- Stage 8 merge commit: `889660ecb8a378d107f6737b4466b70362066793` (PR #10 plus a follow-up
  `feature/8-dashboard-ui` merge)
- Stage 9 commits (committed on `feature/v1-demo-completion`, not yet merged to `main`):
  `d0b5676` (persistence), `449e964` (service), `cb42db9` (API), `d1c8733` (frontend, combined
  with Stage 10)
- Stage 10 commits: `bf29173` (persistence), `fc8908d` (service), `8ab8c83` (API), `d1c8733`
  (frontend), `8916be9` (test fixture repair)
- Stage 11 commits: `24227ab` (persistence), `9fff532` (service/worker), `8c14b55` (API),
  `55c451e` (frontend)
- Stage 12 commits: `d0d24cd` (audit API/query/export), `9314f06` (audit explorer UI)
- Documentation reconciliation commit for this handoff: see the bottom of this file's "Repository
  state" section, or `git log -1` on `feature/v1-demo-completion` at the time this file is read
- Current Alembic head on `feature/v1-demo-completion`: `0013_demo_notification_delivery`
- PR #8 merged at `2026-07-24T19:19:02Z`.
- `.git/index.lock` has recurred repeatedly and self-cleared or been cleared from Windows
  multiple times this effort. Check `Test-Path .git\index.lock` before any mutating Git command;
  never remove it automatically or retry blindly.

## Current implementation status

- Stage 1 Foundation and Authentication: complete and regression-tested
- Stage 2 AWS Account Onboarding: complete and independently verified
- Stage 3 Asset Discovery: complete and independently verified
- Stage 4 Deterministic Rule Engine and Findings: verified and merged
- Stage 5 Compliance Engine: complete, independently verified, and merged
- Stage 6 Deterministic Risk Scoring: independently clean-room verified, merged, and
  regression-tested
- Stage 7 AI Explanation Assistant: independently verified, merged, and post-merge verified
- Stage 8 Dashboard (read model and UI): merged in `main`
- Stage 9 Notifications: complete (model, service, API, frontend), independently verified,
  committed on `feature/v1-demo-completion`; not yet merged into `main`
- Stage 10 Remediation Workflow: complete (model, service, API, frontend), independently
  verified, committed on `feature/v1-demo-completion`; not yet merged into `main`
- Stage 11 Scheduler: complete (model, service, worker, API, frontend), independently verified
  (backend Ruff/Mypy/22 Pytest passed; migration chain verified through
  `0012_stage11_scheduler` on the disposable PostgreSQL verification database; frontend
  TypeScript/ESLint/5 Vitest/production build passed), committed on
  `feature/v1-demo-completion`; not yet merged into `main`
- Stage 12 Audit Query/Export: implemented and committed. Backend clean (Ruff, Mypy 142 source
  files, `test_audit_api.py` 8 passed). Frontend TypeScript, ESLint, Vitest (4 passed), and
  production build are clean. Codex is the active implementation agent for the tomorrow-demo
  readiness work.

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

### Stage 9

Organization-scoped `NotificationEvent` model and migration; `NotificationService`
(create-on-critical-finding, approve, deliver with a bounded 3-attempt retry); deterministic
mock/no-op delivery provider; API layer with `NOTIFICATIONS_READ`/`NOTIFICATIONS_APPROVE` RBAC;
frontend history/approval page with filtering, pagination, and role-gated controls.

### Stage 10

Organization-scoped `RemediationRequest` model and migration; `RemediationService` and
`MockRemediationExecutor` (propose/approve/reject/cancel/execute with a bounded 3-attempt
execution retry); deterministic proposal text from the existing rule registry; API layer with
5 dedicated RBAC capabilities; frontend remediation list/detail workflow plus a finding-detail
"Propose remediation" action.

### Stage 11

`ScanSchedule`/`ScanRun` models and migration; `SchedulerService` and a deterministic
single-tick worker delegating to the existing discovery/evaluation services; database-enforced
overlap protection; API layer with `SCHEDULE_READ`/`SCHEDULE_MANAGE` RBAC; frontend schedules
page with enable/disable, run-now, and scan-run history.

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
0007_stage5_compliance_engine -> 0008_stage6_risk_scoring -> 0009_stage7_ai_assistant
```

The repair migration backfills reservations without changing existing external IDs, adds
account lifecycle coordination, enforces composite tenant relationships, and adds asset/job
lifecycle checks.

## Completed verification evidence

The exact Stage 7 feature SHA was independently clean-room verified and the merged main commit
was regression-tested:

- Backend: 343 passed, 0 failed, 0 skipped; 96% reported coverage
- Frontend: 81 passed, 0 failed, 0 skipped
- Black-box workflow: 44 PASS, 0 FAIL, 0 missing, 0 duplicate
- Ruff, Mypy (111 source files), startup/import, Prettier, ESLint, TypeScript, and Vite passed
- Empty and populated `0007 -> 0008` migration, downgrade/re-upgrade, drift, integrity,
  independent-session concurrency, rollback, and immutability checks passed
- `pip check`, exact installed-environment Python audit, and `npm audit` passed
- Secret, private-key, AWS-key, bearer/JWT, environment-file, unsafe-HTML, mojibake, local
  database, and Stage 7 executable-code scans found no blocker

## Known issues and limitations

- Live AWS validation/discovery is intentionally not part of deterministic automated tests.
- Discovery is synchronous and uses a configured explicit region list.
- Production email delivery, MFA, OIDC/SSO, password reset, distributed rate limiting,
  background scheduling, and deployment infrastructure are deferred.
- A Starlette multipart parsing deprecation warning may appear in backend tests.
- Supported Node 20 LTS, Node 22 LTS, or a compatible 24+ release is recommended; Node may emit
  an experimental type-stripping warning.
- Python uses `pyproject.toml` without a committed Python lockfile.
- The initial compliance catalog contains four controls and twelve mappings. It is not complete
  framework coverage or certification; mappings require human compliance review.
- Compliance export is not implemented.
- Stage 6 uses an initial CloudOps-specific, CVSS-inspired policy. It is not CVSS, does not
  predict exploitation, and does not replace human review.
- Business-impact accuracy depends on explicit context quality. Unknown inputs are persisted and
  conservatively handled; compensating controls require authorization.
- AI explanation is implemented as advisory drafting only. Jira and email outputs are drafts;
  no Jira creation, email delivery, remediation execution, raw event ingestion, or customer AWS
  mutation is implemented.

## Repository state

Stage 7 is integrated in `main` through PR #8 at
`882ff531af07276c11e0d25664fdca033e09c7c7`. Documentation synchronization is isolated on
`docs/stage7-completion`. Stage 8 (dashboard read model and UI) is integrated in `main` at
`889660ecb8a378d107f6737b4466b70362066793` through PR #10 and a follow-up
`feature/8-dashboard-ui` merge; this record does not independently confirm PR #10's exact
review/approval state and that should be verified before treating it as equivalent governance
evidence to PRs #2/#4/#6/#8 below.

Stages 9-12 (notifications, remediation, scheduler, audit query/export) are fully implemented
and committed on `feature/v1-demo-completion`. The current worktree adds the V1 demo-readiness
follow-up: Mailpit SMTP delivery metadata, development-only Mailpit invitation emails, local
demo Compose/Docker files, deterministic Docker-only seed/reset helper scripts, the root
`demo_v1.md` runbook, and the 18-step V1 demo black-box runner. `CLAUDE.md` has remained
untracked throughout every commit on this branch and must stay that way. Generated output
remains ignored.

## Governance record

PR #2 was merged to `main` at `0849e75d...` with no recorded GitHub approval. The repository
owner explicitly accepted that fact as a governance exception after technical gates passed and
authorized Stage 4. PR #3 subsequently merged the verified Stage 4 baseline at
`04807de270bf1eeb152b67ab197d97f961e52179`.

PR #4 had zero recorded GitHub reviews and approvals and no automated check rollup. After
technical clean-room verification passed, the repository owner provided an
**Owner-authorized governance exception for PR #4**. This is not an independent GitHub,
CODEOWNER, automated CI, or repository-policy approval.

PR #6 likewise had zero recorded reviews/approvals and no automated check rollup. Its exact SHA
passed technical clean-room verification, after which the owner recorded:
**Owner-authorized governance exception for PR #6.** This was not an independent GitHub,
CODEOWNER, automated CI, or repository-policy approval.

PR #8 had zero recorded reviews/approvals and no automated check rollup. Its exact SHA passed
technical detached verification, after which the owner recorded:
**Owner-authorized governance exception for PR #8.** This was not an independent GitHub,
CODEOWNER, automated CI, or repository-policy approval.

## Next immediate task

Development ownership has moved from Claude Code to Codex. Stage 12 is committed; the exact
demo-readiness plan is recorded in `NEW_CHAT_CONTEXT.md`; this section is a short pointer, not a
duplicate of that detail.

1. Verify branch, HEAD, working-tree status, and `.git/index.lock` state before any Git
   mutation.
2. Commit this documentation reconciliation safely, keeping `CLAUDE.md` untracked and never
   using `git add .`/`git add -A`.
3. Finish verification and documentation for the tomorrow-demo journey: Mailpit-backed SMTP
   notification and invitation delivery, local demo stack, deterministic seed/reset,
   `demo_v1.md`, and V1 acceptance runner.
4. Continue the Version 1 demo-completion effort per `docs/planning/roadmap.md`: Stage 13
   security hardening, Stage 14 local DevOps/demo stack, deterministic demo seed/reset, full
   regression testing, the black-box V1 acceptance flow, deployment preparation, final
   documentation, and eventually a pull request merging `feature/v1-demo-completion` into
   `main`.
6. Keep dashboard visualization separate from detection, compliance calculation, risk scoring,
   AI explanation, AWS mutation, Jira creation, email delivery, and remediation execution.
7. Keep notification delivery approval-gated. The mock provider remains default/no-network;
   Mailpit SMTP is local-demo-only. Remediation remains mock-only; the scheduler worker must keep
   delegating to existing discovery/evaluation services rather than duplicating their logic.
