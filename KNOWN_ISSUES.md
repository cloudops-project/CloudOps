# CloudOps Known Issues

Last reviewed: 2026-07-30 after executable demo-hardening validation.

## Active demo limitations

### DEMO-01 — Emailed links use the configured frontend URL

Mailpit receives the configured local `FRONTEND_URL`. A remote Quick Tunnel participant cannot open
that local hostname. The owner should copy the invitation link displayed in the UI; it is generated
from `window.location.origin` and URL-encodes the token. The complete link now survives login
redirection. Direct token entry remains available as a fallback.

### DEMO-02 — Quick Tunnel is intentionally ephemeral

The public hostname changes after a restart and stops when `cloudflared` stops. DNS propagation and
negative caching can briefly delay a newly registered hostname. No frontend rebuild, API restart,
CORS edit, or source change is required. Use a named tunnel or AWS staging hostname for stability.

### DEMO-03 — Synthetic scope only

Discovery inventory, identities, provider responses and remediation are synthetic. Remediation is
mock/dry-run only. The demo does not validate customer AWS, live Bedrock, live SES, Jira, backup
restore, canary, rollback, staging, production, or formal UAT.

### TOOL-01 — Local Node version warning

The host used Node 23 and emitted an engine warning. Frontend install, lint, typecheck, 115 tests and
build passed. Containers and CI use the supported Node 22 toolchain.

### PROVIDER-01 — Live provider validation pending

Bedrock and SES adapters have automated mock/Stubber coverage only. Do not infer service access,
sender verification, quotas, production delivery, or model availability from local tests.

## Resolved in this change

- Invitation query/hash loss across authentication.
- Direct host publishing of the demo API.
- Forwarded-origin spoofing paths covered by strict proxy marker, internal host and exact
  scheme/host comparison.
- Missing job worker, worker health checks, and stale Run-now UI status.
- Synthetic metadata drift that caused deterministic rule errors.
- Stale documentation claiming the demo was unvalidated.
