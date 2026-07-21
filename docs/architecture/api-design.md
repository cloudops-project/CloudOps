# API Design

## Purpose and audience

Backend, frontend, integration, and security engineers use these proposed contracts for a consistent `/api/v1` REST API.

## Resource conventions

Use plural resources: `/organizations`, `/aws-accounts`, `/assets`, `/scans`, `/findings`, `/remediations`, and `/audit-events`. HTTP methods and status codes reflect semantics; creation returns `201`, accepted background work `202`, empty deletion `204`, invalid input `422`, unauthenticated `401`, forbidden `403`, missing `404`, conflict `409`, and throttling `429` as applicable. Do not reveal whether another tenant's resource exists.

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

OIDC-compatible authentication is planned; every endpoint performs server-side permission and organization checks. Apply request-size limits, rate limits by subject/tenant/action, CSRF protection when cookie authentication is used, output encoding, safe CORS, and redacted errors. High-risk operations require confirmation and fresh authorization. OpenAPI documents schemas but never example secrets.

## Proposed endpoints and open questions

Nested action endpoints may include `POST /scans`, `POST /findings/{id}/risk-acceptances`, `POST /remediation-requests/{id}/approvals`, and `POST /findings/{id}/verification-scans`. Exact state machines, bulk operations, export delivery, version negotiation, webhook authentication, and asynchronous polling versus events require later design review.
