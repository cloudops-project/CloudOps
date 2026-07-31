# CloudOps Known Issues

Last reviewed: 2026-07-31 after documentation synchronization for PRs #18-#21.

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
mock/dry-run only. The demo does not validate customer AWS, live Bedrock, live SES, live Jira
Cloud, backup restore, canary, rollback, staging, production, or formal UAT.

### TOOL-01 — Local Node version warning

The host used Node 23 and emitted an engine warning. Frontend install, lint, typecheck, 115 tests and
build passed. Containers and CI use the supported Node 22 toolchain.

### SELFHOST-01 — External named-tunnel validation pending

The production-mode one-command self-host path is implemented on its feature branch, but a real
named Cloudflare Tunnel and a separate clean supported host must be exercised before those claims
are externally verified. Local Compose/container results and pull-request CI are recorded
separately. Operators must copy local PostgreSQL backups off-host; the initial backup command is
not a managed disaster-recovery service.

### PROVIDER-01 — Live provider validation pending

Bedrock, SES and Jira Cloud adapters have automated mock/Stubber/CI test coverage only. Do not
infer service access, sender verification, quotas, production delivery, connection validity, or
model availability from local or CI tests.

### INFRA-01 — AWS bootstrap and staging state not independently verified

A prior session reported that `infra/bootstrap` had already been applied to AWS (state bucket,
lock table, KMS key, GitHub OIDC provider, publish role, staging deployment role). This is
user-reported historical information only, not independently verified in this environment with AWS
CLI access, live account/region identity, or Terraform remote-state inspection. Staging application
infrastructure (VPC/ALB/ECS/ECR/RDS) has not been deployed, and the expected
`cloudops-staging-api`/`cloudops-staging-web` ECR repositories are not confirmed to exist. Do not
treat any AWS infrastructure state as current until revalidated from an environment with working
AWS CLI access.

## Resolved in this change

- Invitation query/hash loss across authentication.
- Direct host publishing of the demo API.
- Forwarded-origin spoofing paths covered by strict proxy marker, internal host and exact
  scheme/host comparison.
- Missing job worker, worker health checks, and stale Run-now UI status.
- Synthetic metadata drift that caused deterministic rule errors.
- Stale documentation claiming the demo was unvalidated.
- Documentation drift after PRs #19-#21 (Jira integration and cryptography security repair) merged
  without a corresponding documentation update — resolved by this documentation-synchronization
  branch.

## Resolved dependency issues

- The `cryptography` package was upgraded from `>=43,<46` to `>=48.0.1,<49` (PR #21). Evidenced
  validation: `cryptography 48.0.1` installed locally, `pip check` passed, `pip-audit
--skip-editable` reported no known vulnerabilities, Ruff passed, Mypy passed, backend tests
  passed, and all five GitHub PR checks passed. No vulnerability identifiers are reproduced here
  because none are present in retained evidence available to this session.
