# CloudOps Project Memory

## Last updated

2026-07-24 — Stage 5 compliance merged and regression-verified on `main`; documentation
synchronization is open as PR #5.

## Current implementation

Stages 1–5 are independently verified, merged, and regression-tested. PR #4 merged verified
feature SHA `ff69a4ff5fd48a3e64581fadb284d9845cfcbc8f` at main commit
`9811aeb881a1386c1dfba7e3e1641a2b765430f2`. Stage 6 is implemented on
`feature/6-risk-scoring` with migration `0008_stage6_risk_scoring`; independent verification is
pending.

The active integration branch is `main`. Documentation synchronization is isolated on
`docs/stage5-merge-sync` and published as PR #5. Its initial synchronization commit is
`65d95a6d717556c70ede25900e9daf01dcb90dd4`; the current PR head is authoritative until merge.

Alembic revision `0007_stage5_compliance_engine` follows
`0006_stage4_verification_repairs` and adds versioned frameworks and controls, rule mappings,
per-rule evaluation summaries, assessments, and immutable control snapshots.
Revision `0004_verification_repairs` adds immutable
external-ID reservation history, AWS-account lifecycle coordination fields, database-enforced
account/organization consistency for assets and jobs, asset timestamp checks, nonnegative job
counts, and job status/timestamp invariants. Existing account IDs and external IDs are
backfilled without change.

## Verification repairs

- External IDs remain globally reserved after account deletion and collision handling relies on
  a PostgreSQL unique constraint.
- Account lifecycle mutations use tenant-scoped locks. Validation uses an operation token so an
  older STS result cannot overwrite a newer mutation.
- Discovery uses composite tenant foreign keys, lifecycle checks, deterministic lock ordering,
  and terminal-state guards.
- Every boto3 client receives explicit environment-driven timeouts and bounded retry policy.
- Backend tests now cover all IAM pagination, invalid account states, authenticated discovery
  APIs, filters, stable pagination, details, RBAC, tenant isolation, and PostgreSQL races.
- Frontend discovery requires an accessible confirmation and covers filters, pagination,
  states, RBAC, focus behavior, and escaped metadata.

Current release evidence is 162 backend tests passed with 0 failures and 0 skips at 95.88%
coverage, plus 56 frontend tests passed with 0 failures. Migration lifecycle, populated
`0006 -> 0007` upgrade, PostgreSQL integrity/concurrency, dependency audits, security scans, and
merged-main regression verification passed.

## Decisions

- ADR-007 through ADR-010 remain the Stage 1 decisions.
- ADR-011 supersedes only the reserved Stage 2 numbering and establishes AWS account onboarding as Stage 2.
- `AWS_TRUSTED_PRINCIPAL_ARN` is deployment configuration. Customers manually create `CloudOpsReadOnlyRole` and attach AWS managed `SecurityAudit` during this stage.

## Known limitations

Stage 2 validation remains synchronous and does not deliver CloudFormation/Terraform onboarding
templates, external-ID rotation, background validation, or IAM resource creation. Stage 3
discovery remains synchronous and uses an explicit configured region list. Automated provider
tests use deterministic AWS doubles; controlled live-AWS validation remains operational work.

## Next task

Review and explicitly authorize PR #5 where required, merge it, synchronize `main`, reconfirm
the Stage 1–5 baseline and clean worktree, then obtain separate authorization for Stage 6 —
deterministic risk scoring. Do not create Stage 6 code before that gate; AI must not perform
detection or risk scoring.

## Stage 3 implementation snapshot

Alembic `0003_stage3` adds `assets` and `discovery_jobs`; `0004_verification_repairs` adds the
external-ID history and database integrity/concurrency controls. EC2, S3, IAM, and RDS
collectors normalize paginated inventory. Repeated runs preserve
first-seen history, update current values, and safely deactivate missing assets only after that
collector succeeds. The UI provides asset filters/details and discovery job status/results.
Temporary AWS credentials are not persisted. Stage 4 rules evaluate persisted normalized data;
Risk, AI, remediation, and raw event ingestion remain absent. Compliance interprets Stage 4
evidence and never performs detection or live AWS calls.

## Governance exception

PR #2 merged Stages 1–3 to `main` at `0849e75d...` without a recorded GitHub approval. The
repository owner explicitly accepted the missing approval as a governance exception and
authorized Stage 4. This is not a claim that an independent GitHub approval occurred.

PR #4 had zero recorded GitHub reviews/approvals and no automated check rollup. The exact feature
SHA passed independent technical clean-room verification, after which the owner recorded an
**Owner-authorized governance exception for PR #4**. This is not an independent GitHub,
CODEOWNER, automated CI, or repository-policy approval.

## Stage 5 limitations

The initial catalog contains four controls and twelve mappings. It is not complete framework
coverage or certification, mappings require human compliance review, and compliance export is
not implemented. The Starlette TestClient/httpx deprecation warning remains; Node 20 LTS or 22
LTS is recommended.

## Teammate and AI handoff

The root `README.md` is the complete teammate run guide. A new AI session must be given the
seven root source-of-truth files: `NEW_CHAT_CONTEXT.md`, `PRD.md`, `architecture.md`,
`design.md`, `rules.md`, `phases.md`, and `memory.md`. It must summarize the project goal,
architecture, implementation state, known issues, and next task before editing. Contradictions
must be resolved against current repository evidence. Automated verification uses synthetic
data and deterministic AWS doubles; never use real customer AWS credentials or resources.
