# CloudOps Version 1 Demo Runbook

> **See [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md) first.** That file is the canonical operational runbook for
> the current two-day demo: prerequisites, one-command startup, health verification, credentials,
> temporary public URL, invitation flow, multi-user testing, logs, troubleshooting, validation
> sequence and limitations. Where the two documents disagree, `DEMO_RUNBOOK.md` wins.
>
> This file remains the longer-form Version 1 narrative — demo purpose, per-stage talking points and
> the historical rehearsal record. Section 0 below is a condensed quick start kept for continuity.
>
> **Stale evidence warning:** the "Verified in the current Codex rehearsal" list in section 4 describes
> the demo stack *before* the port-mapping, same-origin proxy, synthetic-metadata and `job-worker`
> fixes. Do not cite it as current. Tracked as DOC-02 in [KNOWN_ISSUES.md](KNOWN_ISSUES.md).

This is the authoritative runbook for the local CloudOps Version 1 demonstration. It assumes the
repository root is `D:\learn\cdac\cloudfix` and the product name is **CloudOps**.

## 0. Two-day demo (quick start)

Use this section for the two-day demo. The numbered sections below remain the
long-form runbook.

### Prerequisites

- Docker Desktop with Docker Compose
- PowerShell
- Ports free: 5173, 8000, 8025, 1025, 5432
- No AWS account, credentials, or network egress required

### One command to start and bootstrap

```powershell
.\scripts\demo_bootstrap.ps1 -Reset
```

This validates the Compose file, builds images, starts the stack, waits for
health, applies migrations (the `api` service runs `alembic upgrade head` before
uvicorn), seeds synthetic demo data, verifies both workers are running, and
prints the URLs and synthetic credentials. Any failing step aborts with a clear
message. Omit `-Reset` only on a first run against an empty database; the seed is
not additive and will tell you to re-run with `-Reset` if demo data exists.

### URLs

- Dashboard: <http://localhost:5173>
- Mailpit inbox: <http://localhost:8025>
- API health through the web origin: <http://localhost:5173/api/health>

The dashboard and the API share one origin: the SPA calls relative `/api/v1/...`
paths and Nginx proxies `/api/` to the API container. A single tunnel to port
5173 therefore serves both, and no rebuild is needed when a temporary public
hostname changes.

### Synthetic credentials

Demo-only values. These are **not** production defaults and must never be reused.

| Role | Email | Password |
| --- | --- | --- |
| Owner | `owner@cloudops-demo.testmail.com` | `CloudOps-Demo-Password-123!` |
| Security analyst | `analyst@cloudops-demo.testmail.com` | `CloudOps-Demo-Password-123!` |
| Cloud engineer | `engineer@cloudops-demo.testmail.com` | `CloudOps-Demo-Password-123!` |

### Demo sequence

1. **Login** — sign in as the owner at <http://localhost:5173>.
2. **AWS account** — the documentation-safe synthetic account `111122223333` is visible.
3. **Assets** — five synthetic assets: EC2 instance, security group, S3 bucket,
   CloudTrail trail, IAM user.
4. **Findings** — deterministic findings including CRITICAL open-SSH and public-S3.
5. **Security posture** — dashboard summary over those records.
6. **Compliance** — the seeded `cis_aws` assessment and its control snapshots.
7. **Risk** — the seeded deterministic risk assessment, scores and ranked findings.
8. **Schedules and Run now** — open the seeded "Daily demo scan", press **Run now**,
   then watch the scan run progress as `job-worker` processes the queued job.
   State it plainly: this is synthetic inventory, not a live AWS scan.
9. **Notifications** — the approval-gated critical-finding notification; the
   delivered message appears in Mailpit.
10. **Audit log** — filter events and export CSV.
11. **Dry-run remediation** — the seeded remediation request is `PENDING_APPROVAL`
    with `dry_run = true` and `execution_mode = mock_automation`. Approve, then
    execute; nothing in AWS is touched.
12. **Members** — the owner, analyst and engineer with their roles.

### Inspect logs

```powershell
docker compose -f compose.demo.yml logs --tail=100 api
docker compose -f compose.demo.yml logs --tail=100 web
docker compose -f compose.demo.yml logs --tail=100 scheduler-worker
docker compose -f compose.demo.yml logs --tail=100 job-worker
docker compose -f compose.demo.yml --profile tunnel logs --tail=100 cloudflared
docker compose -f compose.demo.yml ps
```

The application audit log is in the UI (Audit page) and is the durable record;
container logs are operational only.

### Stop and reset

```powershell
# Stop, keep data
docker compose -f compose.demo.yml down

# Reseed synthetic data without rebuilding
.\scripts\demo_bootstrap.ps1 -Reset -SkipBuild

# Stop the tunnel only (the stack keeps running locally)
docker compose -f compose.demo.yml --profile tunnel stop cloudflared

# Stop and delete the demo database volume
docker compose -f compose.demo.yml --profile tunnel down -v
```

### Temporary multi-user public access (Cloudflare Quick Tunnel)

Several invited people can use the demo at the same time through one temporary
public URL.

```powershell
# Local stack first, then the tunnel
.\scripts\demo_bootstrap.ps1 -Reset -Tunnel

# Or start/refresh the tunnel on its own
.\scripts\demo_tunnel.ps1
.\scripts\demo_tunnel.ps1 -Restart   # new URL
```

The script prints the current `https://<random>.trycloudflare.com` URL, the
temporary-URL warning, and the invitation instructions, then keeps `cloudflared`
running in the foreground.

Quick Tunnel needs **no Cloudflare account, API token, or credentials.** The
`cloudflared` service sits behind the `tunnel` Compose profile, so the default
stack stays local-only.

#### Why a new URL just works

One origin serves everything: the SPA is built with an empty
`VITE_API_BASE_URL`, so the browser calls relative `/api/v1/...` paths against
whatever origin the page was loaded from, and Nginx proxies `/api/` to the API.
The tunnel hostname is therefore never compiled into the bundle.

Nginx forwards the browser-facing host and scheme as `X-Forwarded-Host` /
`X-Forwarded-Proto`, and `TRUST_FORWARDED_HOST_SAME_ORIGIN=true` lets the API
recognise a request whose `Origin` exactly equals that origin as same-origin on
the two cookie-authenticated POST routes. Consequently a new URL needs **no
source-code edit, image rebuild, CORS change, `TRUSTED_HOSTS` change, or API
restart**. The API itself always sees `Host: api`, which is already trusted.

This is not a wildcard: a mismatched `Origin`, a mismatched scheme, or a missing
forwarded host is still rejected with 403, and the setting is refused outright
when `APP_ENV` is `staging` or `production`.

#### Inviting additional demo members

1. Sign in as the owner and go to **Members → Invite**.
2. Enter the guest's email and choose a **CloudFix application role**: `admin`,
   `security_analyst`, `cloud_engineer`, `auditor`, or `viewer`.
3. The invitation email lands in Mailpit (<http://localhost:8025>, local only —
   it is deliberately not tunnelled).
4. **The emailed link points at `FRONTEND_URL` (`http://localhost:5173`), which a
   remote guest cannot open.** Do not change `FRONTEND_URL` for this; just copy
   the `token` value out of the emailed link and send the guest:

   ```text
   https://<current-tunnel-host>.trycloudflare.com/invitations/accept?token=<TOKEN>
   ```

   The accept page reads `token` from the query string, so the origin is
   interchangeable and the same token works on any tunnel URL.
5. The guest opens that link, accepts, registers if needed, and logs in **in
   their own browser**.

Each participant authenticates separately, holds their own access token in their
own browser memory, and keeps their own role, tenant, and organization scope. No
one inherits another person's session, and no one can read another
organization's data. There is no shared or automatic login, and no credentials
appear in any URL.

> **A CloudFix application role is not an AWS IAM permission.** Application
> roles (owner, admin, security analyst, cloud engineer, auditor, viewer) govern
> only what a user may do inside CloudFix. AWS access is entirely separate: it
> comes from cross-account IAM onboarding — a customer-created role plus a
> per-account External ID, assumed with temporary STS credentials. Inviting
> somebody to the demo grants them no AWS access of any kind, and the demo
> assumes no role at all because discovery replays synthetic inventory.

#### When the tunnel stops

The URL works only while `cloudflared` runs. If it exits, is interrupted, or the
host sleeps, the URL dies immediately and permanently — Quick Tunnel hostnames
are never reissued. Restart with:

```powershell
.\scripts\demo_tunnel.ps1 -Restart
```

The newly printed URL is usable straight away; the running stack needs no
change. Share the new link with participants. **No URL persistence is claimed.**

#### Quick Tunnel is demo-only

- The hostname is random and assigned by Cloudflare.
- It changes on every tunnel restart.
- There is no uptime, latency, or availability guarantee.
- Not suitable for sensitive or confidential information.
- Not suitable for production or for customer data.
- Share the active URL only with intended demo participants; anyone holding it
  can reach the login page, though they still need valid credentials.

#### After the demo

Replace Quick Tunnel with one of:

- **Named Cloudflare Tunnel** — a stable, controlled hostname on your own
  Cloudflare zone with a persistent connector credential, access policies, and
  optional Cloudflare Access in front of the login page.
- **AWS ALB + ACM on the staging domain** — an Application Load Balancer with an
  ACM certificate and a real DNS record, matching
  `docs/operations/local-staging-deployment.md`.

Either way, set `CORS_ALLOWED_ORIGINS` and `TRUSTED_HOSTS` to the real
browser-facing origin, enable `COOKIE_SECURE` and `HSTS_ENABLED`, and turn
`TRUST_FORWARDED_HOST_SAME_ORIGIN` **off** — it is refused in production-like
environments anyway.

### Limitations

- **Synthetic AWS data only.** `DEMO_SYNTHETIC_DISCOVERY=true` makes discovery
  replay seeded synthetic inventory instead of assuming a customer role. Never
  describe a demo scan as a live AWS scan. Settings refuse this flag when
  `APP_ENV` is `staging` or `production`.
- No Jira integration.
- No live Amazon Bedrock; the AI provider is the deterministic mock.
- No live Amazon SES; email goes to Mailpit over local SMTP.
- No production deployment, and no backup/restore or rollback drill.
- Remediation is dry-run/mock only and never mutates AWS.
- Temporary HTTP is acceptable for this demo. It is **not** suitable for
  sensitive or customer data.
- Public access uses a Cloudflare Quick Tunnel: random hostname, changes on
  restart, no uptime guarantee, demo participants only.
- Mailpit is intentionally **not** exposed through the tunnel; invitation links
  are read locally by the presenter.

## 1. Demo purpose

The demo proves the end-to-end CloudOps operating story:

- multi-user organization onboarding;
- invitations and invitation acceptance;
- role-based navigation and backend permissions;
- AWS cross-account onboarding;
- read-only discovery;
- deterministic CSPM evaluation;
- findings;
- compliance;
- risk and dashboard posture;
- approval-gated notifications;
- local SMTP delivery through Mailpit;
- remediation proposal, approval, and mock execution;
- scheduled scans and run-now;
- audit logs and CSV export.

The boundary statement for the presenter is:

> Rules detect. Risk scoring prioritizes. AI explains. Humans approve. Providers deliver.
> Remediation remains simulated.

CloudOps does not mutate AWS during this demo. The preferred route can use a verified read-only AWS
demo account. The deterministic fallback route uses synthetic data and must be described as
`DEMO DATA — NOT LIVE AWS DISCOVERY`.

## 2. Architecture used during the demo

The demo uses `compose.demo.yml`:

- `web`: React/Vite CloudOps web application at `http://localhost:5173`.
- `api`: internal FastAPI service reached through the web `/api/` proxy; migrations run at startup.
- `postgres`: PostgreSQL database `cloudops_demo`.
- `scheduler-worker`: manual-profile one-shot scheduler tick service.
- `mailpit`: SMTP server on `localhost:1025` and browser inbox at `http://localhost:8025`.
- Optional live AWS read-only integration: uses the existing cross-account IAM role and STS flow.
- Deterministic fallback: uses `scripts/demo_seed.py` inside the API container.

No host Python virtual environment, host Node installation, manual API startup, manual web startup,
manual PostgreSQL startup, or manual Mailpit startup is required for the Docker demo.

## 3. Machine prerequisites

Supported host for this runbook:

- Windows 11 with PowerShell and Docker Desktop.
- Browser: current Chrome, Edge, or Firefox.
- Recommended resources: 8 GB RAM minimum, 16 GB preferred; 5 GB free disk.
- Docker Desktop must be running Linux containers.

Ports used:

| Service | URL/port |
| --- | --- |
| CloudOps web | `http://localhost:5173` |
| CloudOps API health | `http://localhost:5173/api/health` |
| PostgreSQL | `localhost:5432` |
| Mailpit web UI | `http://localhost:8025` |
| Mailpit SMTP | `localhost:1025` |

Check port conflicts:

```powershell
Get-NetTCPConnection -LocalPort 5173,8000,5432,8025,1025 -ErrorAction SilentlyContinue
```

Live AWS mode additionally requires:

- AWS account ID.
- IAM role ARN like `arn:aws:iam::<ACCOUNT_ID>:role/<ROLE_NAME>`.
- The external ID generated/stored by CloudOps for that AWS account.
- Trust policy allowing the configured CloudOps principal to assume the role.
- Read-only permissions for implemented discovery:
  - EC2 describe APIs for instances, security groups, and volumes.
  - S3 list/get bucket metadata used by the collector.
  - IAM list/get APIs for users, roles, groups, policies, tags, MFA, access keys, and policy
    summaries.
  - RDS, CloudWatch, and CloudTrail read APIs may also be collected by the current implementation.

Fallback mode requires no AWS account and no internet.

## 4. Clean startup instructions

Run from `D:\learn\cdac\cloudfix`:

```powershell
docker compose -f compose.demo.yml config
docker compose -f compose.demo.yml build
docker compose -f compose.demo.yml up -d
docker compose -f compose.demo.yml ps
.\scripts\demo_check.ps1
docker compose -f compose.demo.yml exec -T api python -m alembic current
.\scripts\demo_reset.ps1
```

`scheduler-worker` and `job-worker` are no longer behind a manual Compose
profile, so `up -d` starts every service the demo needs.

Equivalent one-command startup (preferred — see section 0):

```powershell
.\scripts\demo_bootstrap.ps1 -Reset
```

Acceptance check from the host, using the disposable verification database, remains:

```powershell
docker compose -f compose.verify.yml up -d
$env:APP_ENV="testing"
# Inject DATABASE_URL and POSTGRES_TEST_DATABASE_URL with the same disposable test-database endpoint.
$env:JWT_SECRET_KEY="replace-with-a-test-only-secret-at-least-32-characters"
$env:AWS_ACCESS_KEY_ID="testing"
$env:AWS_SECRET_ACCESS_KEY="testing"
$env:AWS_SESSION_TOKEN="testing"
$env:AWS_EC2_METADATA_DISABLED="true"
$env:AWS_DEFAULT_REGION="us-east-1"
$env:AI_PROVIDER="mock"
.\apps\api\.venv\Scripts\python.exe tests\end-to-end\verify_v1_demo.py
```

The acceptance runner writes generated evidence under `%TEMP%\cloudops-v1-demo`; do not commit it.

Verified in the current Codex rehearsal:

- `compose.demo.yml config`: passed.
- `compose.demo.yml build`: passed.
- Docker start/readiness through `scripts/demo_check.ps1`: passed.
- Docker-only reset/seed through `scripts/demo_reset.ps1`: passed.
- Restart rehearsal: passed; PostgreSQL data persisted, Mailpit inbox was repopulated by reseed.
- Cold start after local demo volume removal: passed.
- Manual scheduler tick service: passed.
- V1 acceptance command: 18 PASS, 0 FAIL.

## 5. Shutdown and restart instructions

Normal stop, preserving demo data:

```powershell
.\scripts\demo_stop.ps1
```

PostgreSQL demo data is preserved by the named Docker volume. Mailpit messages are container-local
and may be cleared after stop/recreate; rerun `.\scripts\demo_reset.ps1` to repopulate the local
demo inbox before presenting.

Clean restart, preserving demo data:

```powershell
docker compose -f compose.demo.yml up -d
.\scripts\demo_check.ps1
```

Full reset of demo data:

```powershell
.\scripts\demo_reset.ps1
```

Delete only the local demo database volume and containers:

```powershell
docker compose -f compose.demo.yml down -v
```

Recover from a failed container start:

```powershell
docker compose -f compose.demo.yml ps
docker compose -f compose.demo.yml logs --tail 120 api
docker compose -f compose.demo.yml logs --tail 120 web
docker compose -f compose.demo.yml logs --tail 120 postgres
docker compose -f compose.demo.yml up -d
```

## 6. Demo users

LOCAL DEMO ONLY — NEVER USE IN PRODUCTION.

Seeded fallback credentials:

| Persona | Email | Password | Role | Demonstrates |
| --- | --- | --- | --- | --- |
| Owner/Admin | `owner@cloudops-demo.testmail.com` | `CloudOps-Demo-Password-123!` | owner | invites users, approves notifications, approves remediation, audit export |
| Cloud Engineer | `engineer@cloudops-demo.testmail.com` | `CloudOps-Demo-Password-123!` | cloud_engineer | AWS account/discovery/schedule/remediation request path |
| Security Analyst | `analyst@cloudops-demo.testmail.com` | `CloudOps-Demo-Password-123!` | security_analyst | findings, evaluation, notification actor recipient |

Optional invited users for a live UI invitation demonstration:

- `employee-engineer@cloudops-demo.testmail.com` as `cloud_engineer`.
- `employee-analyst@cloudops-demo.testmail.com` as `security_analyst`.
- `employee-auditor@cloudops-demo.testmail.com` as `auditor`.

## 7. Browser setup

Use separate browser profiles or private windows:

- Admin: `owner@cloudops-demo.testmail.com`.
- Cloud Engineer: `engineer@cloudops-demo.testmail.com`.
- Security Analyst: `analyst@cloudops-demo.testmail.com`.
- Mailpit: `http://localhost:8025`.

Avoid reusing the same browser profile for multiple users unless you click `Logout` first. The web
app stores the access token in memory and the refresh token as an HttpOnly cookie, so stale tabs can
look logged in until refresh fails.

## 8. Admin invitation flow

UI steps:

1. Log in as owner.
2. Open `Dashboard`, then use the invitation form section, or navigate to the invitation/member
   management area exposed by the Dashboard.
3. Enter an employee email, for example `employee-engineer@cloudops-demo.testmail.com`.
4. Select role `cloud_engineer`.
5. Click `Send invitation`.
6. In development mode, CloudOps shows a current-origin, URL-encoded invitation link and the raw
   token fallback.
7. With `NOTIFICATION_PROVIDER=smtp`, Mailpit also receives a `CloudOps demo invitation` email.
8. For a remote guest, copy the link displayed in the UI; the Mailpit email uses configured
   `FRONTEND_URL`. The complete invitation URL survives login redirection.
9. Register the employee account with the same email.
10. Log in as the employee and submit the token on `Accept invitation`.

Expected errors:

- Duplicate pending invite: `active_invitation_exists`.
- Expired invite: `invitation_expired`.
- Reused accepted invite by same user: idempotent accepted membership.
- Wrong email/account: `invitation_email_mismatch`.
- Unauthorized role assignment: `unsafe_role_assignment` or HTTP 403.

## 9. Live AWS onboarding requirements

CloudOps stores account metadata, role ARN, external ID reservation, connection status, and
temporary validation result metadata. It does not store AWS access keys or long-lived AWS secrets.

UI steps:

1. Open `AWS Accounts`.
2. Create or select an account.
3. Enter:
   - organization context from the logged-in tenant;
   - AWS account ID;
   - account name;
   - role ARN such as `arn:aws:iam::<ACCOUNT_ID>:role/<ROLE_NAME>`.
4. Validate/connect the role.

Expected success:

- STS AssumeRole succeeds using the CloudOps external ID.
- Account status becomes `connected`.

Expected failure:

- Invalid role ARN or trust/external ID mismatch leaves the account failed/disconnected with a safe
  error. Switch to fallback mode if live AWS is unavailable.

## 10. Live scan steps

1. Open `AWS Accounts`.
2. Select the connected account.
3. Start discovery from the discovery/account action.
4. Wait for completion; use bounded waiting and refresh rather than promising exact duration.
5. Open `Assets` to view EC2, S3, IAM, and any other discovered metadata.
6. Open `Security` and click/run evaluation for the account.
7. Review generated findings.
8. Open `Compliance` and run/view the CIS AWS assessment.
9. Open `Risk` and run/view the deterministic risk assessment.
10. Open `Security Posture` to show dashboard changes.

If STS or discovery fails, say: `Live AWS is unavailable; switching to deterministic demo data.`

## 11. Fallback demo-data mode

Clearly say: `DEMO DATA — NOT LIVE AWS DISCOVERY`.

Reset and seed:

```powershell
.\scripts\demo_reset.ps1
```

The fallback includes EC2, S3, IAM, CloudTrail, findings, compliance, risk, notifications,
remediation, schedule, scan history/audit examples, and a delivered Mailpit message when
`--deliver-email` is used.

Open:

- Web: `http://localhost:5173`.
- Mailpit: `http://localhost:8025`.

Use the seeded local demo users from section 6.

## 12. Compliance report

Open `Compliance`.

Show:

- Framework key/name/version.
- Control totals.
- Passed/failed/not assessed/error counts.
- Failed controls mapped to deterministic findings.
- Assessment timestamp and account context.
- Related risk score from `Risk` or `Security Posture`.

CSV compliance export is not implemented in Version 1; audit CSV export is implemented.

## 13. Notification and email flow

Open `Notifications`.

1. Locate the notification in `pending approval` or `delivered` state.
2. Owner/admin/security analyst may approve.
3. Click `Approve`.
4. Click `Deliver`.
5. Confirm status `delivered`.
6. Confirm provider fields show the configured provider; local demo uses `smtp`.
7. Open Mailpit at `http://localhost:8025`.
8. Open the message with subject `CloudOps security notification for CloudOps Demo`.
9. Verify recipients include:
   - `owner@cloudops-demo.testmail.com`;
   - `analyst@cloudops-demo.testmail.com` when the analyst triggered the evaluation.
10. Verify body includes organization, masked AWS account, finding count, compliance summary,
    risk summary, and simulated-remediation warning.

The local demo uses SMTP through Mailpit. Amazon SES is implemented and Stubber-tested, but live
SES delivery remains external production-readiness work.

## 14. Remediation flow

MOCK EXECUTION — NO REAL AWS RESOURCE IS CHANGED.

1. Open `Security`.
2. Open a finding.
3. Use remediation actions to propose/request remediation.
4. Open `Remediation`.
5. Owner/admin/security analyst may approve or reject.
6. Click `Approve`.
7. Click `Execute`.
8. Confirm status `succeeded`.
9. Open `Audit log` to show proposal, approval, and execution audit events.

Rollback guidance: because execution is simulated, no AWS rollback is required. If a demo mistake
occurs, rerun `.\scripts\demo_reset.ps1`.

## 15. Scheduling flow

Open `Schedules`.

- Create schedule: select AWS account, enter schedule name, interval at least 15 minutes, click
  `Create schedule`.
- Enable/disable: click `Enable` or `Disable`.
- Run-now: click `Run now`.
- Recent scan runs appear below schedules.
- Overlap protection prevents multiple pending/running scans for the same account.
- `Run now` only *enqueues* a `SCHEDULED_SCAN` platform job; it never scans inline.
  `job-worker` picks the job up and drives discovery then evaluation. Both
  `scheduler-worker` and `job-worker` now start with the stack, so no
  `--profile manual` step is required. To watch the run progress:

```powershell
docker compose -f compose.demo.yml logs -f job-worker
```

If neither worker is running, a scan run stays at `pending` forever — confirm
with `docker compose -f compose.demo.yml ps`.

If the account is disconnected, run-now reports a safe failure.

## 16. Audit flow

Open `Audit log`.

- Owner, admin, and auditor can read audit logs.
- Filter by event type, resource type, result, since, and until.
- Pagination uses `Previous` and `Next`.
- Click `Export CSV`; browser downloads `audit-events.csv`.
- The export is bounded to 5,000 matching rows.

## 17. Full presentation script

Minute 0-2:

> CloudOps is a multi-tenant AWS security posture product. Rules detect findings from persisted
> read-only inventory. Deterministic compliance and risk engines calculate posture. AI explains
> existing records only. Humans approve notifications and remediation. Providers deliver, and
> remediation is simulated in Version 1.

Minute 2-5:

> I am logging in as the organization owner. I can invite teammates, assign roles, and see the
> development invitation token. In local demo mode, Mailpit receives the invitation email too.

Minute 5-8:

> Now I switch to the employee profile. The employee accepts the invitation and sees only the
> navigation and actions allowed for that role. Frontend hiding is not the security boundary; the
> API enforces RBAC.

Minute 8-12:

> If the verified AWS role is available, we connect through STS and run read-only discovery. If
> not, I will clearly switch to deterministic demo data: DEMO DATA — NOT LIVE AWS DISCOVERY.

Minute 12-17:

> Assets feed deterministic rules. Findings feed compliance and risk. The dashboard visualizes
> existing records; it does not discover, score, or recalculate anything.

Minute 17-20:

> A critical finding created an approval-gated notification. The owner approves it, and local SMTP
> sends it to Mailpit. This proves provider delivery without sending a real external email. Amazon
> SES would be a future production adapter, not something implemented today.

Minute 20-23:

> Remediation is mock execution. It records intent, approval, and result without touching AWS.

Minute 23-25:

> Finally, scheduled scans and audit export show operational traceability. The CSV export is
> bounded and role-gated.

## 18. Troubleshooting

| Symptom | Diagnostic | Repair | Fallback |
| --- | --- | --- | --- |
| Docker unavailable | `docker version` | Start Docker Desktop | Use screenshots only, disclose no live run |
| Port busy | `Get-NetTCPConnection -LocalPort 5173,8000,5432,8025,1025` | Stop conflicting app or change only local ports | Use already-running stack |
| Container unhealthy | `docker compose -f compose.demo.yml ps` | `docker compose -f compose.demo.yml logs --tail 120 <service>` | Restart service |
| DB connection failure | `docker compose -f compose.demo.yml logs --tail 120 postgres` | Restart Postgres/container | `down -v`, then reseed |
| Pending migrations | `docker compose -f compose.demo.yml exec -T api python -m alembic current` | Restart API; it runs `alembic upgrade head` | Rebuild API |
| Seed exists | `.\scripts\demo_reset.ps1` | Reset uses demo DB only | `down -v` then start |
| Login failure | Check email/password | Use section 6 credentials | Reset/seed |
| Stale session | Browser profile shows wrong user | Click `Logout`; use separate profile | Incognito |
| Invitation email missing | Mailpit message count | Use development token displayed by UI | Accept token manually |
| Mailpit unavailable | `Invoke-WebRequest http://localhost:8025/api/v1/info` | Restart Mailpit | Use UI token |
| Mailpit inbox empty after restart | `Invoke-RestMethod http://localhost:8025/api/v1/messages` | Rerun `.\scripts\demo_reset.ps1` before presenting email evidence | Use newly generated Mailpit message |
| SMTP failure | Notification status `failed` | Check `SMTP_HOST=mailpit`, port `1025` | Use mock provider and disclose |
| AWS STS failure | Account validation error | Check ARN/trust/external ID | Switch to fallback |
| Invalid role ARN | API validation error | Use `arn:aws:iam::<ACCOUNT_ID>:role/<ROLE_NAME>` | Fallback |
| External ID mismatch | STS access denied | Update AWS trust policy only, never from CloudOps | Fallback |
| Disconnected account | Account status not connected | Revalidate or use seeded connected demo account | Fallback |
| Discovery failure | Discovery job failed | Check read-only AWS permissions | Fallback |
| Evaluation failure | Evaluation status failed | Check assets exist | Reseed |
| Empty findings | Findings total zero | Verify risky demo assets exist | Reseed |
| CORS issue | Browser console/API network | Confirm `CORS_ALLOWED_ORIGINS=http://localhost:5173` | Restart API |
| Scheduler not running | No scan run appears | Use run-now or manual worker command | Show existing scan history |
| CSV export failure | Audit export alert | Check owner/admin/auditor role | Use owner |
| Git index lock | `Test-Path .git\index.lock` | Confirm no Git process, remove only stale lock | Do not run Git demo steps |

## 19. Emergency fallback plan

No panic path:

1. Say: `Live AWS is unavailable; switching to deterministic demo data.`
2. Run:

   ```powershell
   docker compose -f compose.demo.yml up -d
   .\scripts\demo_reset.ps1
   ```

3. Continue from `Security Posture`, `Assets`, `Security`, `Compliance`, and `Risk`.
4. Show the Mailpit security notification.
5. Show remediation mock execution and audit evidence.
6. Disclose the fallback honestly.

## 20. Remaining after tomorrow's demo

- Live AWS discovery is optional and depends on a pre-provisioned AWS demo account, role ARN, trust
  policy, external ID, and read-only permissions.
- Production SMTP, Amazon SES, Slack, Teams, webhooks, Gmail, and Microsoft Graph delivery are not
  implemented.
- Invitation email delivery is local-demo/development-only through Mailpit.
- Remediation execution is simulated; no AWS resources are modified.
- The scheduler and job workers use PostgreSQL-backed durable jobs with leases, heartbeats,
  retries, idempotency, and dead-letter handling. Redis/Celery are not required.
- Password reset, email verification delivery, MFA, SSO, production deployment/IaC, and external
  production hardening remain future work.
- Compliance export is not implemented; audit CSV export is implemented.
- Dependency audits passed after explicit metadata-egress authorization: Python `pip-audit`
  checked 80 installed non-editable distributions with 0 known vulnerabilities; frontend
  `npm audit --registry=https://registry.npmjs.org --json` checked 381 dependencies with 0
  vulnerabilities after the reviewed development-only ESLint upgrade to 10.8.0.
