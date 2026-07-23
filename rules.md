# CloudOps Development Rules

## Scope and authority

These rules govern current CloudOps development. More detailed policies remain under
`docs/engineering/`. When documents conflict, stop and resolve the contradiction before changing
code.

The governed baseline contains independently verified, merged Stages 1–5 at main commit
`68785b0138eaecf84850887a3d4005c40e9761c0`. Stage 6 deterministic risk scoring has not
started and requires its own branch, scope authorization, implementation, tests, independent
verification, review, and merge gate.

## Technology stack

### Backend

- Python 3.12+
- FastAPI
- Pydantic v2 and Pydantic Settings
- SQLAlchemy 2.x
- Alembic
- PostgreSQL in production and for database/concurrency verification
- Boto3/Botocore for AWS STS and read-only discovery
- Argon2 password hashing and signed JWT access tokens
- Ruff, Mypy, Pytest, and pytest-cov

SQLite is permitted only for isolated fast tests and is not evidence for PostgreSQL locking,
partial indexes, composite foreign keys, or concurrency.

### Frontend

- React and TypeScript
- Vite
- Tailwind CSS
- React Router
- TanStack Query
- React Hook Form and Zod
- Lucide React
- Vitest and Testing Library
- ESLint and Prettier

## Code boundaries

- Python uses strict Mypy-compatible annotations; TypeScript must pass both application and Node
  project type checks. Do not add broad type ignores to hide defects.
- Route handlers remain thin.
- Services own business workflows, transaction boundaries, and audit emission.
- Repositories own database access and tenant predicates.
- Pydantic schemas explicitly control request and response fields.
- Frontend visibility is usability only; backend authorization is authoritative.
- Rules evaluate persisted normalized data only; boto3 stays in discovery.
- Compliance consumes persisted Stage 4 results; it never performs detection or live AWS calls.
- Do not introduce risk, AI, remediation, raw event ingestion, customer AWS mutation, or Stage 6
  functionality.

## Security rules

- Never commit real secrets, credentials, account identifiers, role ARNs, or tokens.
- Never store or log plaintext passwords, raw refresh/invitation tokens, authorization headers,
  cookie headers, or AWS credentials.
- Access JWTs are short lived, algorithm restricted, signature/expiry/claims validated, and held
  only in browser memory.
- Refresh tokens are opaque, stored in HttpOnly cookies, hashed in the database, rotated, and
  family-revocable.
- Production invitation responses must not expose development tokens.
- Authentication errors must avoid account enumeration.
- All organization-owned operations require active membership and tenant scope.
- Platform admin never silently bypasses tenant isolation.
- AWS access uses cross-account IAM roles, external IDs, STS `AssumeRole`, and temporary
  credentials only.
- External IDs are permanently reserved and never reused, including after account deletion.
- Temporary AWS credentials remain in memory and are excluded from metadata, responses, logs,
  exceptions, audit events, and fixtures.
- AWS SDK connect/read timeouts and retry counts must be explicit and bounded.
- A missing finding is never sufficient evidence for compliance `PASS`.
- Rule errors become compliance `ERROR`; missing or version-mismatched evidence becomes
  `NOT_ASSESSED`; suppression does not turn a failure into a pass.
- Compliance assessment snapshots and finalized per-rule evaluation summaries are immutable.
- Automated tests must use synthetic fixtures, deterministic AWS doubles, and disposable
  PostgreSQL. Production/customer AWS accounts and credentials are forbidden.

## Structured logging and audit rules

- Operational logs use bounded structured fields and correlation IDs.
- Durable audit events record accepted user-visible lifecycle transitions.
- Never log JWTs, authorization/cookie headers, passwords, AWS credentials, full policies, raw
  provider/database exceptions, or unbounded evidence.
- Do not claim audit data is absolutely immutable; database controls and retention/archive
  guarantees must be described precisely.
- Owner governance exceptions must state the exact PR and must not be described as independent,
  CODEOWNER, CI, or repository-policy approval.

## RBAC and governance

- Roles are owner, admin, security analyst, cloud engineer, auditor, and viewer.
- Central capability policy is the single source for authorization decisions.
- Admins cannot assign owner or govern an existing owner.
- The final active owner cannot be demoted, suspended, or removed.
- Discovery start is allowed for owner, admin, security analyst, and cloud engineer.
- Auditor and viewer cannot start discovery.
- Active members may view organization-scoped inventory according to the capability map.
- Owner/admin/security analyst/cloud engineer may run evaluations; auditor/viewer may not.
- All active roles may view rules/findings. Owner/admin/security analyst may suppress findings.

## Database and tenant rules

- PostgreSQL is the authoritative database behavior.
- Tenant IDs must be present in organization-owned repository predicates.
- Asset and discovery-job account/organization agreement is enforced with composite foreign keys.
- Unique constraints and partial indexes must enforce invariants subject to races.
- Asset timestamps cannot move backward.
- Discovery-job counts cannot be negative.
- Job status and timestamps must remain a valid state-machine combination.
- Historical assets are deactivated, not deleted, when absent from a successful collector.
- A failed collector must not deactivate its prior assets.
- Evaluation/finding tenant consistency, positive versions, nonnegative counters,
  status/timestamp lifecycles, and active-job/finding uniqueness are database enforced.

## Concurrency expectations

- Use PostgreSQL `SELECT ... FOR UPDATE`, an atomic conditional update, or a database uniqueness
  invariant for race-sensitive workflows.
- Locks must be tenant scoped and transactions must be as short as practical.
- Do not hold a row lock across a slow AWS call. Use operation tokens/versions and re-lock before
  applying results.
- Refresh rotation, invitation acceptance, final-owner mutation, AWS account lifecycle changes,
  discovery starts, and account-level asset lifecycle require tested concurrency behavior.
- Acquire multiple locks in deterministic order and leave no permanent deadlock.

## Migration policy

- Add a new Alembic revision; do not rewrite an already reviewed migration.
- Keep a single linear head unless an approved ADR states otherwise.
- Provide a downgrade where practical.
- Verify empty upgrade, incremental upgrade, current, check, downgrade, and re-upgrade on
  disposable PostgreSQL.
- Compare models and migration metadata.
- Preserve valid existing data; fail clearly on invalid data instead of deleting it silently.

## Testing policy

Every change must receive proportional unit, integration, security, regression, and PostgreSQL
coverage. Required gates are:

- Backend: Ruff format, Ruff lint, Mypy, import/startup, Pytest, coverage, Alembic lifecycle,
  PostgreSQL concurrency, `pip check`, and `pip-audit`
- Frontend: Prettier, ESLint, TypeScript, Vitest, production build, and `npm audit`
- Repository: secret/private-key/AWS-key/environment scans, conflict-marker scan, and
  `git diff --check`

The maintained baseline expects at least 95% backend coverage. Run focused unit/integration tests
first, then PostgreSQL integrity/concurrency and the complete regression suite. Verify the exact
pushed SHA from a separate clean detached worktree before integration.

Do not mark a check passed unless its command ran successfully. Mock AWS deterministically; live
AWS validation belongs only in a controlled sandbox and must never use customer credentials.

## Documentation policy

- `NEW_CHAT_CONTEXT.md` is the portable master context.
- `memory.md` records where the current work stopped.
- `PRD.md`, `architecture.md`, `design.md`, `rules.md`, and `phases.md` are concise sources of
  truth for fresh AI sessions.
- Update architecture documentation after material design changes and memory after substantial
  sessions.
- Clearly label implemented, verification-pending, and future behavior.
- Never treat historical ADR context as current behavior when it has been superseded.

## Branch strategy

- `main`: active integration and release baseline
- `develop`: legacy long-lived branch; do not base new work on it unless policy is explicitly
  changed
- `feature/*`: stage implementation branches
- `fix/*`: narrowly scoped repair branches when needed
- `docs/*`: documentation-only branches

Use pull requests and required review. Report absent CI checks as absent. Do not force push,
rewrite history, push directly to `main`, merge, or start another stage without explicit
authorization.

## Definition of Done

A stage is done only when its scoped behavior, migrations, tests, security controls,
documentation, dependency audits, and independent verification pass; no later-stage executable
scope is present; and no secrets or generated artifacts are committed.

No stage may begin until its predecessor is independently verified and merged. Stage 6 must
remain blocked until documentation PR #5 is reviewed/authorized, merged, and `main` is
synchronized and clean. It must branch from that baseline; AI must not perform finding
detection or deterministic risk scoring.
