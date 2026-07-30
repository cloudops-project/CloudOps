# API Design

> See [API_CONTRACTS.md](../../API_CONTRACTS.md) at the repository root for a short index into this
> document plus the one demo-specific note (the same-origin Nginx proxy path). This document remains
> the single authoritative source for route lists, the RBAC matrix, and the error envelope.

## Stage 1 implemented contract

Stage 1 uses application-managed access JWTs and opaque refresh cookies per ADR-008. Access tokens use `Authorization: Bearer`; refresh/logout use an HttpOnly cookie scoped to `/api/v1/auth`. Errors use an `error` object with code, safe message, correlation ID, and validation details.

| Area           | Paths                                                                          | Authorization                                        |
| -------------- | ------------------------------------------------------------------------------ | ---------------------------------------------------- |
| Authentication | `/api/v1/auth/register`, `login`, `refresh`, `logout`, `me`, `change-password` | Public, refresh cookie, or access JWT as appropriate |
| Organizations  | `/api/v1/organizations` and `/{organization_id}`                               | Authenticated active member; update owner/admin      |
| Members        | `/{organization_id}/members` and role/status/delete subpaths                   | Capability policy; governance owner/admin            |
| Invitations    | organization create/list/cancel and `/api/v1/invitations/accept`               | Owner/admin; accept by matching authenticated user   |
| Audit          | `/{organization_id}/audit-events`                                              | Owner/admin/auditor                                  |
| Probes         | `/health`, `/ready`                                                            | Public, no infrastructure details                    |

## Stage 5 compliance contract

| Area        | Paths                                                                            | Authorization                                                |
| ----------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| Frameworks  | `/api/v1/compliance/frameworks`, `/{framework_key}`, `/{framework_key}/controls` | Every active organization member                             |
| Controls    | `/api/v1/compliance/controls/{id}`, `/rules`, `/findings`                        | Every active organization member; bounded finding pagination |
| Assessments | `/api/v1/aws/accounts/{id}/compliance/assess`                                    | Owner, admin, security analyst, cloud engineer               |
| History     | `/api/v1/compliance/assessments`, `/{id}`, `/{id}/controls/{snapshot_id}`        | Every active organization member                             |
| Summary     | `/api/v1/compliance/summary`                                                     | Every active organization member                             |

Assessment and traceability lists use validated filters, stable ordering, and bounded page sizes.
Cross-tenant identifiers return non-disclosing not-found responses. Runtime responses expose
CloudOps summaries and bounded identifiers, never raw policies, credentials, or provider errors.

### Stage 1 RBAC matrix

| Capability                      | Owner | Admin | Analyst | Engineer | Auditor | Viewer |
| ------------------------------- | ----- | ----- | ------- | -------- | ------- | ------ |
| Read organization               | Yes   | Yes   | Yes     | Yes      | Yes     | Yes    |
| Read members                    | Yes   | Yes   | Yes     | Yes      | Yes     | No     |
| Update organization             | Yes   | Yes   | No      | No       | No      | No     |
| Invite/manage non-owner members | Yes   | Yes   | No      | No       | No      | No     |
| Assign owner                    | Yes   | No    | No      | No       | No      | No     |
| Read audit activity             | Yes   | Yes   | No      | No       | Yes     | No     |

Admins may govern non-owner memberships only; an existing owner may be governed only by another owner. Independently, no action may demote, suspend, or remove the final active owner. Platform administration remains separate and never grants an implicit tenant bypass.

Invitation creation includes a one-time `development_token` only when `APP_ENV` is `development` or `testing`; production omits the field. Refresh rotation and invitation acceptance use PostgreSQL row locks across their complete transactions.

## Purpose and audience

Backend, frontend, integration, and security engineers use these proposed contracts for a consistent `/api/v1` REST API.

## Resource conventions

Use plural resources. Stage 2 AWS account routes are namespaced under `/aws/accounts`; later resources include `/assets`, `/scans`, `/findings`, `/remediations`, and `/audit-events`. HTTP methods and status codes reflect semantics; creation returns `201`, accepted background work `202`, empty deletion `204`, invalid input `422`, unauthenticated `401`, forbidden `403`, missing `404`, conflict `409`, and throttling `429` as applicable. Do not reveal whether another tenant's resource exists.

## Cross-cutting contract

Pydantic validates request and response schemas with explicit field allowlists. List endpoints use bounded cursor pagination, documented filtering/sorting, and stable ordering. A correlation ID is accepted/generated and returned. Scan creation, remediation requests/executions, and webhook processing require scoped idempotency keys. Optimistic version fields protect concurrent lifecycle updates.

```json
{
  "error": {
    "code": "finding_state_conflict",
    "message": "The finding changed; refresh and retry.",
    "correlation_id": "opaque-id",
    "details": []
  }
}
```

## Security and lifecycle

Stage 1 uses ADR-008 local access JWTs and opaque refresh sessions; future OIDC integration must preserve the same subject and tenant boundaries. Every endpoint performs server-side permission and organization checks. Apply request-size limits, rate limits by subject/tenant/action, origin/CSRF protection when cookie authentication is used, output encoding, safe CORS, and redacted errors. High-risk operations require confirmation and fresh authorization. OpenAPI documents schemas but never example secrets.

## Proposed endpoints and open questions

## Stage 2 implemented AWS onboarding API

All routes require authentication, active organization membership, and the centralized owner/admin AWS-account-management capability:

- `POST /api/v1/aws/accounts`
- `GET /api/v1/aws/accounts?organization_id={uuid}`
- `GET /api/v1/aws/accounts/{id}`
- `PATCH /api/v1/aws/accounts/{id}`
- `POST /api/v1/aws/accounts/{id}/validate`
- `POST /api/v1/aws/accounts/{id}/disconnect`
- `DELETE /api/v1/aws/accounts/{id}`

Creation returns a pending record, unique external ID, trust policy, permission guidance, and setup instructions. Validation calls AssumeRole and GetCallerIdentity. Responses never include AWS credentials; failures use stable sanitized reason codes.

## Proposed endpoints and open questions

Nested action endpoints may include `POST /scans`, `POST /findings/{id}/risk-acceptances`, `POST /remediation-requests/{id}/approvals`, and `POST /findings/{id}/verification-scans`. Exact state machines, bulk operations, export delivery, version negotiation, webhook authentication, and asynchronous polling versus events require later design review.

## Stage 3 implemented discovery API

- `POST /api/v1/aws/accounts/{account_id}/discover`
- `GET /api/v1/discovery/jobs` and `GET /api/v1/discovery/jobs/{job_id}`
- `GET /api/v1/assets`, `GET /api/v1/assets/summary`, and `GET /api/v1/assets/{asset_id}`

List calls require `organization_id`, stable page/page-size parameters, and a maximum page size
of 100. Assets filter by AWS account, type, region, status, active/stale, and text search. All
reads require active membership; discovery start allows owner, admin, security analyst, and
cloud engineer. Cross-tenant identifiers use not-found semantics.

Discovery lists use stable `(created_at, id)` ordering, bounded page sizes, and allowlisted
filters. Starting discovery for an account with a pending or running job returns `409`. Provider
failures expose sanitized codes only; temporary AWS credentials and raw botocore exceptions
never enter responses.
