# CloudOps Deployment (Index)

> Root-canonical pointer. The authoritative staging/production release path — OIDC, build-once,
> SBOM/scan, digest promotion, zero-task Terraform bootstrap, protected-environment production gate,
> and the staging HTTP-only escape hatch — lives at
> [docs/operations/deployment-strategy.md](docs/operations/deployment-strategy.md). This file states
> only how the local two-day demo relates to that path: it is a separate, local-only deployment mode
> that does not exercise it.

## Local demo is not a deployment

The demo runs entirely inside Docker Compose (`compose.demo.yml`) on the operator's machine. It:

- Does not use the GitHub Actions release pipeline, OIDC, ECR, or Terraform.
- Does not create, modify, or plan any AWS resource (Terraform under `infra/` is validated and
  Checkov-scanned but has never been applied — see `docs/operations/deployment-strategy.md` and
  `KNOWN_ISSUES.md` INFRA-01).
- Is reachable either purely on `localhost`, or temporarily and publicly through a Cloudflare Quick
  Tunnel (`docker compose -f compose.demo.yml --profile tunnel up -d cloudflared`) — never through
  an ALB, ACM certificate, or staging/production DNS name.

## What "staging" and "production" mean in this repository right now

Per `docs/operations/deployment-strategy.md`: the release workflow and Terraform exist and are
locally validated, but **have not been run against AWS staging or production**. No staging or
production environment currently exists in a deployed state. Any document that appears to imply
otherwise is stale — see `KNOWN_ISSUES.md` DOC-01/DOC-02 for tracked staleness.

## Demo-to-persistent-access migration path

The demo's Quick Tunnel is deliberately temporary (`ADR-D03`). Moving from "two-day demo" toward
something staging-shaped requires one of:

1. A **named Cloudflare Tunnel** (requires a Cloudflare account, zone, and a persistent connector
   credential) — the natural next step for continued *temporary, low-stakes* multi-user access
   without touching AWS.
2. The **AWS staging hostname**, following `docs/operations/deployment-strategy.md`'s actual release
   path (ALB + ACM + Terraform apply + OIDC), which is a materially larger undertaking requiring
   explicit authorization, a reviewed Terraform plan, and the staging UAT/observability evidence
   that path already requires.

Neither is implemented by, or a natural extension of, the demo's Docker Compose configuration —
stability requires one of the two paths above, not more application code layered onto the Quick
Tunnel. See `ADR-D03`'s "Consequences."

## What the demo does prove, and does not prove

The demo proves the application boots, migrates, seeds, and serves a same-origin UI+API from a
single container image build, using synthetic data. It does not prove: a successful Terraform
apply, a successful ECS service deployment, live Bedrock or SES validation, a rollback rehearsal, or
a backup/restore rehearsal. See `docs/operations/deployment-strategy.md` for what each of those
would require.
