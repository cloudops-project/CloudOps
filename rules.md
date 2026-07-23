# CloudOps Development Rules

## Scope and authority

These rules govern current CloudOps development. More detailed policies remain under
`docs/engineering/`. When documents conflict, stop and resolve the contradiction before changing
code.

The governed baseline contains merged Stages 1–3 and Stage 4 implementation pending independent
verification. Stage 5 has not started.

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

- Route handlers remain thin.
- Services own business workflows, transaction boundaries, and audit emission.
- Repositories own database access and tenant predicates.
- Pydantic schemas explicitly control request and response fields.
- Frontend visibility is usability only; backend authorization is authoritative.
- Rules evaluate persisted normalized data only; boto3 stays in discovery.
- Do not introduce compliance, risk, AI, remediation, raw event ingestion, customer AWS mutation,
  or Stage 5 functionality.

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

- `main`: protected release baseline
- `develop`: protected integration target
- `feature/*`: stage implementation branches
- `fix/*`: narrowly scoped repair branches when needed

Use pull requests, required review, and CI. Do not push, merge, rewrite history, or start another
stage without explicit authorization.

## Definition of Done

A stage is done only when its scoped behavior, migrations, tests, security controls,
documentation, dependency audits, and independent verification pass; no later-stage executable
scope is present; and no secrets or generated artifacts are committed.

Stage 5 code must never be implemented until Stage 4 is independently verified and merged.
