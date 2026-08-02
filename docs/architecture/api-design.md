# API design

FastAPI route definitions and Pydantic schemas are executable truth. This document summarizes the
current contract; [API_CONTRACTS.md](../../API_CONTRACTS.md) is the root index.

## Cross-cutting contract

- `/api/v1` JSON APIs use authenticated JWT access except public authentication/probe operations.
- Refresh/logout use an HttpOnly cookie; access tokens remain browser-memory only.
- Route dependencies require active organization membership and the specific capability.
- Every tenant-owned lookup includes organization scope or a verified tenant-owned parent.
- Cross-tenant identifiers use non-disclosing not-found behavior.
- Pydantic schemas bound strings/collections and reject client-owned execution fields.
- Lists use bounded pagination/filter allowlists and stable ordering.
- Background work returns durable identifiers; database idempotency and state transitions prevent
  duplicate outcomes.
- Safe error envelopes provide code, message, correlation ID, and bounded details without provider
  bodies, credentials, External IDs, or tenant-existence leaks.

## Capabilities by area

| Area | Typical read | Privileged change |
|---|---|---|
| Organization/members | Active roles as defined by RBAC | Owner/admin, with final-owner protections |
| AWS accounts/discovery | Active tenant roles according to capability | Account management by owner/admin; discovery by approved operator roles |
| Findings/compliance/risk/dashboard | Active authorized tenant roles | Context/control/suppression/assessment capabilities |
| AI | Authorized readers/generators | AI never grants business authorization |
| Notifications/Jira | Read capability | Separate approve/deliver/manage capabilities |
| Remediation | Read capability | Propose/approve/execute capabilities remain separate |
| Remediation administration | Owner only | Owner only; analysts/admins cannot grant sandbox approval |
| Audit/export | Audit capability | Export is bounded and audited |

`apps/api/app/security/rbac.py` is authoritative when role names differ from this summary.

## Remediation administration contract

The exact routes are listed in [remediation governance](../security/remediation-governance.md).
They validate tenant ownership at write time, lock the account/request row, reject IAM user or
wrong-account role ARNs, atomically revoke approval on trust change, require reasons, and record
audit evidence. Responses expose configuration/approval status, not either full External ID.
Preparation derives action, target, and immutable evidence from tenant-owned records; clients
cannot set executor, AWS operation, target ARN, evidence, verification, rollback, or request IDs.

## Important transitions

- Discovery/evaluation/schedule requests enqueue durable jobs; workers reload and reauthorize.
- Notification delivery rechecks approval before provider work.
- Remediation proposal, human approval, live preparation, second approval, enqueue, lease acquisition,
  execution, verification, and terminal evidence are distinct transitions.
- `prepare-live` does not execute or enqueue and returns the request to pending approval.
- Stale snapshots, leases, idempotency conflicts, unsupported actions, disabled flags, or emergency
  stop produce stable refusal errors.

The running API's OpenAPI document is the field-level reference. Do not include secret-bearing
example payloads in static documentation.
