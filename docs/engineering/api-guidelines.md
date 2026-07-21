# API Engineering Guidelines

## Purpose and audience

Backend and frontend engineers use these rules to implement the planned [API design](../architecture/api-design.md) consistently.

Use `/api/v1` and plural REST resources. Pydantic request/response models must reject or ignore no unexpected mass-assignable security fields; prefer rejecting unknown input for command schemas. Authentication, active membership, permission, organization scope, and resource state are checked server-side for every request.

Use cursor pagination with bounded limits, allowlisted filters/sorts, correlation IDs, safe structured errors, and OpenAPI descriptions. Require idempotency keys for scan creation, remediation, webhook processing, notification retry, and similar retried commands. Use optimistic versions/ETags where races matter. Never expose provider errors, secrets, another tenant's existence, or raw stack traces.

Apply TLS, safe CORS, request/body limits, endpoint-appropriate rate limits, CSRF protections for cookie-authenticated writes, and content-type validation. Webhooks verify signature, timestamp, and replay window before parsing tenant context. Version or compatibly evolve schemas; record breaking decisions.

Open questions: cursor encoding, API version deprecation, bulk endpoints, export delivery, and machine-to-machine authentication.
