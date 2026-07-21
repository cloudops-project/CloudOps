# CloudFix Project Memory

## Purpose and audience

All team members use this living handoff record to understand the current state, decisions, active work, risks, and safest next task.

**Last updated:** 2026-07-20
**Current stage:** Stage 0 â€” Planning and research (in progress)
**Current sprint:** Stage 0 documentation initialization (planning label; cadence not approved)
**Current objective:** Obtain stakeholder and team review of the completed Stage 0 documentation draft and resolve proposed decisions.

## Status

| Area | State |
|---|---|
| Stage 0 documentation | Draft created; review/approval pending |
| Application code | Not started |
| AWS integration | Not started |
| Rule engine | Not started |
| AI integration | Not started |
| Deployment | Not started |
| Testing | Strategy documented; no tests executed |

## Completed work

Initial product, architecture, database, threat, design, engineering, planning, operations, governance, ADR, rule-catalogue, and template drafts; documentation-only repository areas; root index and Stage 0 checklist. Structural validation confirmed all 82 required files, substantive Markdown content, local link integrity, 39 proposed rule specifications, 17 phase rows, eight Mermaid documents, and no executable Stage 1 artifacts. Added root `NEW_CHAT_CONTEXT.md` as the portable fresh-chat handoff artifact.

## Work in progress and next work

No implementation work is in progress. Planned next work is stakeholder/team review of PRD, scope, architecture, database design, threat model, development rules, team responsibilities, and phases; then resolve open decisions and update ADR statuses. Do not start Stage 1 before explicit approval.

## Active files

Primary review set: `NEW_CHAT_CONTEXT.md`, `docs/product/prd.md`, `docs/product/scope.md`, `docs/architecture/system-overview.md`, `docs/architecture/database-design.md`, `docs/architecture/threat-model.md`, `docs/engineering/development-rules.md`, `docs/planning/team-responsibilities.md`, and `docs/planning/phases.md`.

## Important decisions

Proposed baseline: feature-based monorepo; React/TypeScript/Vite frontend; Python 3.12/FastAPI backend; PostgreSQL; Celery/Redis MVP queue with SQS migration boundary; STS cross-account read-only scan roles; deterministic rules; separate approved remediation permissions; advisory provider-neutral AI. ADRs remain Proposed until reviewed.

## Open architectural questions

OIDC/provider and MFA enforcement; Celery/Redis approval versus SQS; PostgreSQL RLS; CloudFix AWS principal topology; external-ID storage/rotation; retention, residency, RPO/RTO; initial rule subset/thresholds; compliance licensing/mappings; notification priority; first remediation playbook; AI provider/data policy/budget.

## Known issues, risks, blockers, debt

No implementation exists. The repository is not initialized as Git. Stage 0 approval is the current gate, not a technical blocker. Major risks are tenant isolation, IAM/remediation blast radius, evidence quality, AI disclosure, audit integrity, cost, and knowledge silos. Technical debt: none in code; documentation decisions must not remain indefinitely provisional.

## Environment and ownership

No local runtime, database, cloud, CI, staging, or production environment exists. Ownership follows [team responsibilities](team-responsibilities.md); actual names/handles are unassigned.

## Update protocol

Update this document at the end of each working session, after a major decision, after a feature, when a blocker is found, and before handoff. Preserve prior facts in change history and link decisions/issues.

## Change history

- 2026-07-20 â€” Initialized Stage 0 memory; all implementation areas marked not started; set stakeholder/team review as next recommended task.
- 2026-07-20 â€” Completed the initial documentation draft and structural/consistency validation; Stage 0 remains in progress pending review and approval.
- 2026-07-20 â€” Added `NEW_CHAT_CONTEXT.md` for portable AI-chat handoff; no architecture or implementation status changed.
