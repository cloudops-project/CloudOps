# Component Design

## Purpose and audience

Engineering leads use this planned decomposition to preserve feature ownership, dependency direction, and security boundaries.

## Planned modules

### Stage 2 AWS onboarding implementation

The `/api/v1/aws` router remains thin and delegates to `AWSOnboardingService`. The service owns validation, external-ID generation, RBAC, state transitions, STS orchestration, and audit writes; `Repository` owns organization-scoped persistence. Boto3 is injected at the service boundary for deterministic tests. Temporary credentials remain local variables passed only to an assumed-role STS client and never cross into models, schemas, logs, or responses.

The web onboarding pages use the existing credentialed API client and TanStack Query. Reusable account cards, status badges, policy viewers, IAM instructions, and validation results use centralized design tokens. Stage 2 contains no worker, collector, scanner, or background job.

| Component | Owns | Must not do |
|---|---|---|
| Web features | Accessible views, route guards, query adapters | Decide authorization or call APIs from visual components |
| Identity/tenancy | Local JWT claims, refresh sessions, memberships, roles, permissions; future OIDC adapter | Trust organization IDs supplied without membership checks |
| AWS accounts | Onboarding state, connection validation, revocation | Persist temporary credentials |
| Scanning | Jobs, runs, schedules, cancellation, collectors | Mutate customer resources |
| Inventory | Normalized EC2/S3/IAM asset snapshots | Collect application payloads |
| Rules/findings | Versioned deterministic evaluation and lifecycle | Delegate detection to AI |
| Compliance | Reviewed rule-control mappings | Claim certification |
| Remediation | Requests, approvals, playbooks, executions, verification | Reuse broad scan role or bypass approval |
| Integrations | AI/Jira/email/Teams provider adapters | Leak tenant data or block core scanning indefinitely |
| Audit/reporting | Append events, archive exports, derived reports | Silently rewrite historical events |

## Dependency rules

Feature modules expose application interfaces and typed contracts. Routes call application services; services coordinate domain policy; repositories perform tenant-scoped persistence; adapters implement external ports. No route calls Boto3 or AI directly, no feature accesses another feature's internal repository, shared code stays limited to stable primitives, and a generic `utils` dumping ground is prohibited.

## Background processing

The API stores a scan job transactionally, then publishes a minimal opaque job identifier. A worker re-fetches tenant context, claims a run lease, assumes the registered role, collects paginated metadata, evaluates pinned rule versions, commits bounded batches, and emits audit/operational events. Queue messages contain no credentials or asset payloads.

## Proposals and open questions

Celery/Redis is proposed for MVP; an SQS adapter is a planned migration option. Transactional outbox, schema ownership, report generation placement, and scheduler implementation need design spikes before coding.
