# CloudOps Working Memory

> Update after every substantial coding session. The repository map in
> [architecture.md](architecture.md) explains organization; this file records where work stopped.

## Session state

- Date: 2026-07-30 (Asia/Calcutta)
- Worktree: `D:\learn\cdac\cloudfix-main-release`
- Starting branch: `fix/temporary-http-staging`
- Starting HEAD: `2306589c4eb4a136a6f2d75cfc909529d06e820e`
- Current task: validate and publish the demo-hardening changes on a focused feature branch
- Merge, deployment, live AWS, live Bedrock and live SES authorization: none
- Product name: CloudOps; CloudFix remains the repository/legacy identifier

## Implemented demo hardening

- One browser origin serves the SPA and relative `/api/` requests through Nginx.
- The API has no host-published port in the normal demo Compose file.
- A demo-only forwarded-origin mode is disabled by default and refused in staging/production.
- Nginx overwrites the trusted forwarded host, scheme and marker headers.
- Unauthenticated invitation links preserve pathname, query string and hash across login.
- Invitation links use `window.location.origin` and URL-encode the token.
- Synthetic discovery exercises the real persistence/evaluation pipeline without AWS.
- PostgreSQL-backed scheduler and job workers run by default with health checks.
- Remediation remains governed mock/dry-run only.
- Mailpit is local-only; the Quick Tunnel exposes only the web service.

## Verification completed

- Focused backend: 95 passed.
- Full backend: 621 collected tests reached 100% with no failures or stderr against disposable
  PostgreSQL. A focused PostgreSQL migration file also passed 9/9.
- Ruff: clean.
- Strict Mypy: clean across 160 source files.
- Frontend: clean install, lint, typecheck, 69 focused tests, 115 full tests and production build
  passed. The built bundle contains no temporary tunnel hostname.
- Compose base and tunnel-profile rendering: passed.
- Nginx built-image syntax check: passed.
- PowerShell parser: all three changed scripts passed; PSScriptAnalyzer was unavailable.
- Local demo: migrations, reset/seed, 23 rules, zero evaluation errors, five synthetic assets,
  seven critical, seven high and six medium findings.
- Local E2E through the web endpoint: health/readiness, SPA routes, three isolated user sessions,
  refresh/logout, role restrictions, forged-token rejection, core dashboards, Run now, notifications,
  audit, invitations and dry-run remediation passed.
- Quick Tunnel: real HTTPS URL worked; a tunnel-only restart produced a new registered URL without
  rebuilding or restarting the API/web. Windows DNS negative caching required validation through a
  resolver that had the new record.
- Dependency checks: `pip check`, `pip-audit` and `npm audit` passed with no known vulnerabilities.

## Known limitations

- Quick Tunnel hostnames are ephemeral and DNS propagation/cache behavior is outside the app.
- The emailed invitation uses configured `FRONTEND_URL`; for a remote Quick Tunnel guest, copy the
  UI-generated current-origin link.
- Demo inventory, users and provider behavior are synthetic.
- No live AWS account, customer account, Bedrock, SES, production email, Jira, staging deployment,
  production deployment, backup/restore drill, canary, rollback rehearsal or formal UAT was run.
- Node 23 emits an engine warning locally; the container/CI toolchain uses Node 22.

## Next exact task

1. Finish the redacted candidate-file secret scan.
2. Review `git diff`, create `fix/demo-hardening-validation`, and stage explicit reviewed paths.
3. Commit with `fix(demo): validate same-origin tunnel and multi-user flow`.
4. Push normally and open a non-draft pull request; do not merge automatically.

## Safe commands

```powershell
git status --short
git diff --check
docker compose -f compose.demo.yml config
docker compose -f compose.demo.yml --profile tunnel config
```

Do not bulk-stage, rewrite history, run live provider tests, or deploy from this session.
