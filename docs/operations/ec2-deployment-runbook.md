# Controlled sandbox EC2 deployment runbook

> **Warning:** This is a non-executing procedure. It does not authorize AWS calls, Terraform apply,
> costs, Cloudflare, or remediation. Use only a dedicated non-production account, never a management
> or payer account. Terraform state and saved plans are sensitive operational artifacts.

## 1. Prerequisites

- Human-approved 12-digit non-production account, short-lived AWS IAM Identity Center profile, and
  region `ap-south-1`.
- Terraform `1.10.5`, repository provider lock, explicit administrator CIDR such as
  `203.0.113.10/32`, secure plan directory outside all worktrees, and an approved spending ceiling.
- Successful CI for the exact `origin/main` commit and one Alembic head.
- No static AWS credential environment variables. Cloudflare authorization is separate.

## 2. Identity and offline validation

Verify the worktree is clean and equals `origin/main`. Validate the sandbox offline, then use the
repository preflight helper with the expected account/profile/region. Reject root, IAM-user static
keys, account mismatch, any region other than `ap-south-1`, wildcard administrator CIDR, and a
plan path inside the repository.

## 3. Saved plan review

Generate a binary plan only in the approved external directory. Record its SHA-256, resource
inventory, IAM permissions, public-address behavior, cost-sensitive resources, and narrow Checkov
exceptions. Confirm the plan has one `t3a.large` host, 50 GiB encrypted gp3, IMDSv2, SSH only from
the explicit `/32`, no public application ports, no NAT Gateway, ALB, managed database, Elastic IP,
AdministratorAccess, IAM mutation, or production resources.

Stop for explicit approval containing the exact account, region, spend ceiling, and reviewed hash.
Never regenerate a plan silently after approval.

## 4. Apply and host access

Apply only the reviewed plan using the repository wrapper. Prefer AWS Systems Manager Session
Manager; restricted SSH is a fallback. Confirm Ubuntu 24.04, IMDSv2, encrypted disk, instance
profile, expected main SHA, and absence of access-key files or static AWS variables.

## 5. Deploy CloudOps

Generate runtime secrets locally with restrictive permissions, deploy through the supported
self-host/container flow, and start with:

```text
REMEDIATION_EXECUTION_ENABLED=false
REMEDIATION_LIVE_AWS_ENABLED=false
REMEDIATION_EMERGENCY_STOP=true
```

Run the one-shot migration to `0019_live_remediation_data_model`; verify API health/readiness, web,
PostgreSQL, scheduler heartbeat, job-worker heartbeat, queue processing, logs, and a safe backup
smoke test. Verify the default credential chain resolves the instance profile and the platform role
can assume only the exact discovery/remediation roles, with no direct S3/EC2 mutation.

## 6. Cloudflare Tunnel egress

`aws_security_group.hosting` allows outbound UDP 7844 (QUIC) and TCP 7844
(HTTP/2 fallback) to `0.0.0.0/0`, alongside the existing outbound TCP 443
and VPC-resolver DNS rules. No inbound application port is added: the host
keeps SSH-only ingress from the approved administrator CIDR, and the
connector reaches the stack through the internal `web:8081` service.

Live AWS remediation remains disabled. Applying these rules requires a
separately reviewed plan and explicit apply authorization.

## 7. Post-deployment

Use synthetic users/data for smoke tests. Configure a named Cloudflare Tunnel only under separate
authorization and route only to internal web. Preserve evidence outside source control. Do not
grant sandbox approval, enable live flags, or run remediation as part of deployment.

Current status: identity preflight, plan, apply, EC2 creation, deployment, and smoke tests are
**Not yet verified**.
