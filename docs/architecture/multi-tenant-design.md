# Multi-Tenant Design

## Purpose and audience

Backend, database, security, and QA teams use this design to enforce organization isolation consistently.

## Isolation model

`organizations` is the tenant root. Every tenant-owned row carries `organization_id` directly where practical or reaches it through a mandatory foreign-key path. Authentication identifies the subject; a server-side membership lookup establishes allowed organizations and permissions. Client claims, URL IDs, queue payloads, report filters, and integration callbacks are never sufficient authorization.

## Enforcement layers

- Route dependencies require authenticated identity and selected organization context.
- Application services check permission and resource organization before state transitions.
- Repositories require `organization_id` in method signatures and predicates; unrestricted `get(id)` is prohibited for tenant data.
- Database constraints and composite unique keys preserve tenant ownership; PostgreSQL row-level security is defense-in-depth to evaluate, not a substitute for service checks.
- Worker messages carry opaque IDs; workers re-resolve ownership and connection state before work.
- Cache keys, object paths, logs, metrics, exports, Jira links, and AI metadata include a non-secret tenant partition key without exposing another tenant.

## Privileged access and deletion

Platform support access is deny-by-default, time-bound, justified, least-privilege, and audited; impersonation requires explicit design. Organization deletion is a staged, authorized workflow respecting retention/legal holds and provider cleanup. Soft deletion does not weaken query scoping.

## Verification

Test cross-tenant read/write IDs, list filters, nested resources, exports, jobs, webhooks, cached responses, error messages, and concurrency. Add repository contract tests that fail if organization scope is omitted.

## Open questions

Decide whether to adopt PostgreSQL RLS in the MVP, support a user in multiple organizations, define platform-admin break-glass policy, and approve retention/deletion semantics.
