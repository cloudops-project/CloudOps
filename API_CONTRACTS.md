# CloudOps API Contracts (Index)

> Root-canonical pointer. The full API surface — every implemented route group, its authorization
> requirement, the RBAC matrix, pagination/idempotency conventions, and the error-envelope shape —
> lives at [docs/architecture/api-design.md](docs/architecture/api-design.md). This file is a short
> index plus the one thing that document does not cover: how the demo exposes that same API.

## Authoritative route groups

All routes are under `/api/v1`. `docs/architecture/api-design.md` documents, per implemented stage:
authentication (`/auth/register|login|refresh|logout|me|change-password`), organizations and
members, invitations (including `/invitations/accept`), audit events, AWS account onboarding
(`/aws/accounts` and subpaths), discovery (`/aws/accounts/{id}/discover`, `/discovery/jobs`,
`/assets`), compliance (`/compliance/...`), and the probes `/health` and `/ready`. Later stages
(findings, risk, notifications, remediation, schedules) follow the same resource, pagination,
RBAC, and error-envelope conventions documented there; this index does not re-list every path to
avoid a second place for route lists to go stale.

The six-role RBAC matrix (owner/admin/security_analyst/cloud_engineer/auditor/viewer) and the
error-envelope shape (`error.code` / `message` / `correlation_id` / `details`) are defined once in
`docs/architecture/api-design.md` and referenced, not duplicated, by
[SECURITY_MODEL.md](SECURITY_MODEL.md).

## How the demo exposes this API (the one addition)

In the general architecture, the API is a separately addressable service. In the local demo, it is
**not** separately addressed by the browser: Nginx proxies `/api/` to `api:8000` with no trailing
slash on `proxy_pass` (preserving the `/api` prefix), so the browser only ever calls relative
`/api/v1/...` paths against whatever origin loaded the page — `http://localhost:5173` or the current
Cloudflare Quick Tunnel origin. The API's own route definitions, authorization, and response shapes
are unchanged; only the network path to reach them differs. See `ADR-D01` and the Nginx
configuration comments in `apps/web/nginx.conf` for why the trailing slash matters.

The normal demo Compose file does not publish port 8000 to the host. Health and readiness are
available through `/api/health` and `/api/ready` on the web origin; the API remains reachable only
inside the Compose network.

## What this file does not do

It does not restate individual endpoint paths, request/response schemas, or the RBAC matrix — those
belong in [docs/architecture/api-design.md](docs/architecture/api-design.md) alone.
