# CloudOps Version 1 Demo Runbook

This is the authoritative runbook for the local CloudOps Version 1 demonstration. It assumes the
repository root is `D:\learn\cdac\cloudfix` and the product name is **CloudOps**.

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
- `api`: FastAPI service at `http://localhost:8000`, including migration execution at startup.
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
| CloudOps API | `http://localhost:8000` |
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
docker compose -f compose.demo.yml --profile manual config
docker compose -f compose.demo.yml build
docker compose -f compose.demo.yml up -d
docker compose -f compose.demo.yml ps
.\scripts\demo_check.ps1
docker compose -f compose.demo.yml exec -T api python -m alembic current
.\scripts\demo_reset.ps1
```

Equivalent one-command startup:

```powershell
.\scripts\demo_start.ps1
.\scripts\demo_reset.ps1
```

Acceptance check from the host, using the disposable verification database, remains:

```powershell
docker compose -f compose.verify.yml up -d
$env:APP_ENV="testing"
$env:DATABASE_URL="postgresql+psycopg://cloudops:cloudops_test_password@localhost:5433/cloudops_test"
$env:POSTGRES_TEST_DATABASE_URL=$env:DATABASE_URL
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

- `compose.demo.yml config` and `compose.demo.yml --profile manual config`: passed.
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
6. In development mode, CloudOps shows a `Development invitation token`.
7. With `NOTIFICATION_PROVIDER=smtp`, Mailpit also receives a `CloudOps demo invitation` email.
8. Open Mailpit at `http://localhost:8025`, open the invitation email, copy the accept link, or use
   `/invitations/accept?token=<token>`.
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

The tomorrow demo uses local SMTP through Mailpit. Amazon SES is not implemented; it is future
production adapter work.

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
- The manual Docker worker is one tick:

```powershell
docker compose -f compose.demo.yml --profile manual run --rm scheduler-worker
```

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
- The scheduler worker is a one-shot tick foundation, not a distributed queue or daemon.
- Password reset, email verification delivery, MFA, SSO, production deployment/IaC, and external
  production hardening remain future work.
- Compliance export is not implemented; audit CSV export is implemented.
- Online dependency audits require explicit metadata-egress authorization in this environment.
