# CloudOps Demo Runbook

This runbook covers the synthetic Quick Tunnel demo only. Stable organization-managed hosting
uses a named tunnel and the separate
[self-hosting guide](docs/operations/self-hosted-cloudflare-deployment.md); it does not enable
synthetic discovery or expose Mailpit.

> Operational runbook for the two-day CloudOps demo. This is the **canonical** demo document.
> `demo_v1.md` remains the longer-form Version 1 narrative runbook; where the two disagree, this file
> wins.
>
> Everything in this demo uses **synthetic data**. Nothing here touches a real AWS account.
> Current defects: [KNOWN_ISSUES.md](KNOWN_ISSUES.md). Security posture:
> [SECURITY_MODEL.md](SECURITY_MODEL.md).

## Prerequisites

- Docker Desktop with Docker Compose
- PowerShell
- Free ports: **5173** (web), **8025** (Mailpit UI), **1025** (Mailpit SMTP),
  **5432** (PostgreSQL)
- No AWS account, credentials, Cloudflare account, or API token required
- Internet access only if you want the public tunnel

## One-command startup

```powershell
cd D:\learn\cdac\cloudfix-main-release

# Local only
.\scripts\demo_bootstrap.ps1 -Reset

# Local + temporary public URL
.\scripts\demo_bootstrap.ps1 -Reset -Tunnel
```

`-Reset` truncates and reseeds the demo database. The seed is **not** additive: without `-Reset` on a
database that already has demo data, it fails clearly and tells you to use `-Reset`. `-SkipBuild`
reuses existing images.

The script validates the Compose file, builds, starts the stack, waits for health, seeds synthetic
data, runs the multi-user checks, confirms both workers are running, and prints URLs and credentials.
Every step aborts loudly on failure.

## Services

| Service | Purpose | Host port |
| --- | --- | --- |
| `postgres` | Database and durable job queue | 5432 |
| `mailpit` | Local SMTP sink + inbox UI | 1025 / 8025 |
| `api` | FastAPI backend; internal only; applies migrations before starting | — |
| `scheduler-worker` | Enqueues due schedule occurrences | — |
| `job-worker` | Leases and processes platform jobs | — |
| `web` | Nginx serving the SPA and proxying `/api/` | 5173 → 8080 |
| `cloudflared` | Quick Tunnel (profile `tunnel`) | — |

Both workers start by default. Without `job-worker`, **"Run now" would never leave `pending`**,
because `run_schedule()` only enqueues a `SCHEDULED_SCAN` job and never scans inline.

## Health verification

```powershell
.\scripts\demo_check.ps1                      # health + same-origin proxy + SPA fallback
.\scripts\demo_check.ps1 -IncludeUserChecks   # also logs in all three roles (needs seeded data)
docker compose -f compose.demo.yml ps
```

Manual equivalents:

```powershell
curl.exe -sf http://localhost:5173/api/health # API liveness through Nginx
curl.exe -sf http://localhost:5173/api/ready  # API readiness through Nginx
curl.exe -sf http://localhost:5173/healthz    # nginx
curl.exe -sf http://localhost:8025/api/v1/info
```

`/health` is pure liveness. `/ready` returns `503 dependency_unavailable` when the database is
unreachable — a 503 from `/ready` with a 200 from `/health` means the process is up but the database
is not, so investigate the database rather than restarting the container.

## Seed and reset

```powershell
# Reseed without rebuilding
.\scripts\demo_bootstrap.ps1 -Reset -SkipBuild

# Or directly
docker compose -f compose.demo.yml exec -T api python /app/scripts/demo_seed.py --reset --deliver-email
```

The seed refuses `APP_ENV=staging` or `production`, and refuses any database whose name is not
`cloudops_demo` or `cloudops_demo_*`. It prints `evaluation_status`, `evaluation_errors` and
`findings_by_severity`, and **exits non-zero if any deterministic rule errored** — that would mean the
synthetic metadata has drifted from the rule contract in `apps/api/app/services/demo_inventory.py`.

Expected: `evaluation_errors: 0`, status `completed`, roughly 20 findings including 7 CRITICAL.

## Synthetic credentials

**Demo-only. Never production defaults. Never reuse these anywhere.**

| Application role | Email | Password |
| --- | --- | --- |
| Owner | `owner@cloudops-demo.testmail.com` | `CloudOps-Demo-Password-123!` |
| Security analyst | `analyst@cloudops-demo.testmail.com` | `CloudOps-Demo-Password-123!` |
| Cloud engineer | `engineer@cloudops-demo.testmail.com` | `CloudOps-Demo-Password-123!` |

## Local URLs

- Dashboard: <http://localhost:5173>
- Mailpit inbox: <http://localhost:8025>
- API health: <http://localhost:5173/api/health>

The SPA and the API share **one origin**: the bundle is built with an empty `VITE_API_BASE_URL`, so
the browser calls relative `/api/v1/...` paths, and Nginx proxies `/api/` to the API.

## Temporary public URL

```powershell
.\scripts\demo_tunnel.ps1            # start and print the URL
.\scripts\demo_tunnel.ps1 -Restart   # new URL
.\scripts\demo_tunnel.ps1 -NoFollow  # print and return, tunnel stays up in the background
```

The script prints `https://<random>.trycloudflare.com`.

> **The URL is temporary.** It is random, it **changes every time the tunnel restarts**, and it
> **stops working the moment `cloudflared` exits**. Quick Tunnel hostnames are never reissued. There
> is no uptime guarantee. Do not send sensitive or production data through it. Share it only with
> intended demo participants. **No persistence is claimed, and no amount of application code makes it
> stable** — that requires a named tunnel or the AWS staging hostname.

A new URL needs **no** source-code edit, image rebuild, CORS change,
`TRUSTED_HOSTS` change, or API restart. Nginx forwards the browser-facing host and scheme, and the API
recognises an exactly-matching `Origin` as same-origin. DNS propagation or negative caching can
briefly delay a newly registered hostname.

Mailpit is **not** tunnelled on purpose — an open mail UI would expose invitation tokens.

Stop the tunnel only:

```powershell
docker compose -f compose.demo.yml --profile tunnel stop cloudflared
```

## Member invitation flow

1. Sign in as the owner and go to **Members → Invite**.
2. Enter the guest's email and choose a **CloudOps application role**: `admin`, `security_analyst`,
   `cloud_engineer`, `auditor`, or `viewer`.
3. The invitation email arrives in Mailpit (<http://localhost:8025>).
4. The emailed link uses `FRONTEND_URL`. For a remote guest, copy the complete link displayed by the
   invitation UI. It is built from the presenter's current browser origin and URL-encodes the token:

   ```text
   https://<current-tunnel-host>.trycloudflare.com/invitations/accept?token=<TOKEN>
   ```

5. The guest opens that link and logs in or registers. The complete pathname, query and hash survive
   authentication, so the invitation token reaches the accept page. Direct token entry remains a
   fallback.

> A **CloudOps application role is not an AWS IAM permission.** Inviting somebody grants them no AWS
> access of any kind. See [SECURITY_MODEL.md](SECURITY_MODEL.md#application-roles-versus-aws-iam-roles).

## Multi-user test flow

Automated: `.\scripts\demo_check.ps1 -IncludeUserChecks` logs in all three roles through the
same-origin proxy and asserts role fidelity, distinct tokens, three rounds of interleaved reads, and
401 for unauthenticated and forged tokens.

Manual, using separate browsers or private windows:

1. Browser A — owner logs in. Browser B — analyst. Browser C — engineer.
2. Confirm each session shows its **own** email and role; nobody inherits another session.
3. Confirm role-restricted controls: the analyst cannot manage members; the engineer can propose but
   not approve remediation; an auditor/viewer cannot start evaluations.
4. Read pages simultaneously in all three browsers; data must stay correct per session.
5. Press **Run now** as the owner and confirm authorization is enforced for lower roles.
6. Confirm no cross-organization data is visible to a user outside the demo organization.

## Demo presentation sequence

1. **Login** — <http://localhost:5173> (or the tunnel URL) as the owner.
2. **AWS account** — the documentation-safe synthetic account `111122223333` is visible.
3. **Assets** — five synthetic assets: EC2 instance, security group, S3 bucket, CloudTrail trail,
   IAM user.
4. **Findings** — deterministic findings, including CRITICAL open-SSH and public-S3.
5. **Security posture** — dashboard summary over those authoritative records.
6. **Compliance** — the seeded `cis_aws` assessment and its immutable control snapshots.
7. **Risk** — deterministic scores, component reasons, ranked findings.
8. **Schedules → Run now** — see below.
9. **Notifications** — approval-gated critical-finding notification; delivered message in Mailpit.
10. **Audit log** — filter, then export CSV.
11. **Dry-run remediation** — see below.
12. **Members** — the three roles.

Say the boundary out loud:

> Deterministic rules detect. Risk scoring prioritizes. AI explains. Humans approve. Providers
> deliver. Remediation is simulated.

## Scheduler demonstration

1. Open **Schedules**; the seeded "Daily demo scan" is visible.
2. Press **Run now**. This creates a `ScanRun` and enqueues a `SCHEDULED_SCAN` platform job — it does
   **not** scan inline.
3. `job-worker` leases the job and drives discovery, then evaluation.
4. The scan-run list polls every 2s while a run is `pending`/`running`, so the status advances without
   a manual refresh.
5. Follow along in the worker log:

   ```powershell
   docker compose -f compose.demo.yml logs -f job-worker
   ```

6. Audit events are recorded for the enqueue and the discovery start.

**State plainly that this is synthetic inventory, not a live AWS scan.** `DEMO_SYNTHETIC_DISCOVERY`
replays seeded inventory instead of assuming a customer role.

If a run stays at `pending` forever, `job-worker` is not running — check
`docker compose -f compose.demo.yml ps`.

## Notifications

Delivery is approval-gated: a critical finding creates a `PENDING_APPROVAL` notification, an
authorized user approves it, and only then does a provider deliver. The demo provider is SMTP to
Mailpit; open <http://localhost:8025> to show the delivered message. Delivery evidence records a
template version and a content hash — not the body.

## Audit evidence

The in-app **Audit** page is the durable record: filterable and paginated, with a bounded CSV export
(5,000 rows). Container logs are operational only and are not the audit trail. Show an audit event
created by the demo itself — for example the schedule enqueue or the discovery start.

## Dry-run remediation

1. Open **Remediation**; the seeded request is `PENDING_APPROVAL` with a **Dry run** badge and
   `mock automation`.
2. Approve it as the owner — proposal never self-approves.
3. Execute. The deterministic mock executor runs; **nothing in AWS is touched**.
4. Point out the audit trail and the immutable request snapshot.

`execute()` refuses anything that is not `mock_automation`, refuses when the
`REMEDIATION_EXECUTION_ENABLED` kill switch is off, and refuses when `REMEDIATION_LIVE_AWS_ENABLED` is
set. The demo enables only the mock switch.

## Logs

```powershell
docker compose -f compose.demo.yml logs --tail=100 api
docker compose -f compose.demo.yml logs --tail=100 web
docker compose -f compose.demo.yml logs --tail=100 scheduler-worker
docker compose -f compose.demo.yml logs --tail=100 job-worker
docker compose -f compose.demo.yml --profile tunnel logs --tail=100 cloudflared
docker compose -f compose.demo.yml logs -f job-worker           # follow
docker compose -f compose.demo.yml ps
```

Signals worth pointing at: `readiness.failed` (database unreachable),
`platform.job.stale_completion_ignored` (expected under lease contention; a sustained spike means a
worker is crash-looping), growing `dead_lettered` counts (a job type failing every retry).

## Troubleshooting

| Symptom | Cause | Action |
| --- | --- | --- |
| Browser cannot reach the app | Port mapping or web container down | `docker compose -f compose.demo.yml ps`; expect `5173:8080` |
| `Failed to fetch` in the browser | `/api/` proxy not working | `docker compose -f compose.demo.yml logs web`; confirm `location /api/` in `apps/web/nginx.conf` |
| API returns HTML instead of JSON | SPA fallback is catching `/api/` | The `/api/` location is missing or `proxy_pass` gained a trailing slash |
| `/ready` 503 but `/health` 200 | Database unreachable, or migrations did not run | Check `postgres` health and the `api` log; do not restart blindly |
| Run now stays `pending` | `job-worker` not running | `docker compose -f compose.demo.yml up -d job-worker` |
| Scheduled scans never fire | `scheduler-worker` not running | Same, for `scheduler-worker` |
| Seed says data already exists | Seed is not additive | Re-run with `-Reset` |
| Seed exits non-zero with a rule-error warning | Synthetic metadata drifted from the rule contract | Fix `apps/api/app/services/demo_inventory.py`; see `test_demo_stack.py` |
| `Expected string or URL object, got SecretStr` | Regression: `database_url` used instead of `database_dsn` | Restore `settings.database_dsn` in `scripts/demo_seed.py` |
| Execute returns 409 | `REMEDIATION_EXECUTION_ENABLED` off | Confirm it is `true` for `api` and `job-worker` |
| Tunnel URL 404s or refuses | `cloudflared` exited | `.\scripts\demo_tunnel.ps1 -Restart`, share the new URL |
| Guest cannot open the emailed invitation link | Email uses local `FRONTEND_URL` | Copy the current-origin link displayed by the invitation UI |
| Web container will not start | Nginx could not resolve `api` at boot | `docker compose -f compose.demo.yml restart web` |

## Shutdown and reset

```powershell
# Stop, keep data
docker compose -f compose.demo.yml down

# Stop the tunnel only
docker compose -f compose.demo.yml --profile tunnel stop cloudflared

# Stop everything and delete the demo database volume
docker compose -f compose.demo.yml --profile tunnel down -v
```

## Validation sequence

Run before trusting the demo. **No result is claimed here** — capture real output.

```powershell
cd D:\learn\cdac\cloudfix-main-release
git diff --check

cd apps\api
# Adjust the venv path if the API's virtual environment lives somewhere else on this machine.
.venv\Scripts\ruff.exe check app ..\..\scripts\demo_seed.py
.venv\Scripts\mypy.exe app
.venv\Scripts\python.exe -m pytest app\tests\test_demo_stack.py app\tests\test_demo_tunnel_access.py -v
.venv\Scripts\python.exe -m pytest app\tests -ra
.venv\Scripts\python.exe -m alembic heads    # expect 0017 only

cd ..\web
npm ci; npm run lint; npm run typecheck; npm run test; npm run build

cd ..\..
docker compose -f compose.demo.yml config
docker compose -f compose.demo.yml --profile tunnel config
.\scripts\demo_bootstrap.ps1 -Reset
.\scripts\demo_check.ps1 -IncludeUserChecks
docker compose -f compose.demo.yml down
```

Run Alembic from `apps\api`; from the repository root it fails to resolve its relative script path.

## Limitations

- **Synthetic AWS data only.** Never present a demo scan as a live AWS scan.
- **Cloudflare Quick Tunnel**: random hostname, changes on restart, dies with the process, no uptime
  guarantee, demo participants only. **Not a deployment.**
- Temporary HTTP is acceptable locally; `COOKIE_SECURE` is false in the demo.
- **No Jira.** AI Jira output is a draft string; no ticket is created.
- **No live Bedrock.** The AI provider is the deterministic mock.
- **No live SES.** Email goes to Mailpit.
- **No production deployment.** Terraform exists under `infra/` but has never been applied.
- **No backup/restore drill, no full rollback drill, no enterprise-grade UAT.**
- Remediation is dry-run/mock only and never mutates AWS.
- Not suitable for sensitive, confidential, or customer data.
